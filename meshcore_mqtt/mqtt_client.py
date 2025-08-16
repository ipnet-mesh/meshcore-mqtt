"""MQTT client management for MeshCore bridge."""

import asyncio
import logging
import time
import uuid
from typing import Any, Callable, Dict, Optional

import paho.mqtt.client as mqtt

from .config import Config


class MQTTClientManager:
    """Manages MQTT client connection, reconnection, and message handling."""

    def __init__(self, config: Config) -> None:
        """Initialize MQTT client manager."""
        self.config = config
        self.logger = logging.getLogger(__name__)

        # MQTT client
        self.client: Optional[mqtt.Client] = None

        # Connection state
        self._connected = False
        self._reconnecting = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
        self._last_activity: Optional[float] = None

        # Message handlers
        self._message_handlers: Dict[str, Callable[[str, str], None]] = {}
        self._default_command_handler: Optional[Callable[[str, str], None]] = None

        # Running state
        self._running = False

    async def start(self) -> None:
        """Start the MQTT client."""
        if self._running:
            self.logger.warning("MQTT client is already running")
            return

        self.logger.info("Starting MQTT client")
        self._running = True

        # Create and configure client
        self.client = self._create_client()

        # Connect with retry logic
        try:
            await self._connect_with_retry()
        except Exception as e:
            self.logger.error(f"Initial MQTT connection failed: {e}")
            await self._recover_connection()

        # Start client loop
        if self.client:
            self.client.loop_start()

    async def stop(self) -> None:
        """Stop the MQTT client."""
        if not self._running:
            return

        self.logger.info("Stopping MQTT client")
        self._running = False

        if self.client:
            try:
                # Stop the loop first
                if hasattr(self.client, "_loop_started"):
                    self.client.loop_stop()
                    delattr(self.client, "_loop_started")

                # Then disconnect
                if self.client.is_connected():
                    self.client.disconnect()
            except Exception as e:
                self.logger.error(f"Error stopping MQTT client: {e}")

        self.logger.info("MQTT client stopped")

    def _create_client(self) -> mqtt.Client:
        """Create and configure a new MQTT client."""
        # Generate a unique client ID
        client_id = f"meshcore-mqtt-{uuid.uuid4().hex[:8]}"
        self.logger.debug(f"Using MQTT client ID: {client_id}")

        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            clean_session=True,
            reconnect_on_failure=True,
        )

        # Set up callbacks
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect  # type: ignore
        client.on_message = self._on_message
        client.on_publish = self._on_publish
        client.on_log = self._on_log

        # Set authentication if provided
        if self.config.mqtt.username and self.config.mqtt.password:
            client.username_pw_set(self.config.mqtt.username, self.config.mqtt.password)

        # Configure TLS if enabled
        if self.config.mqtt.tls_enabled:
            self._configure_tls(client)

        # Set connection parameters
        client.keepalive = 60
        client.max_inflight_messages_set(1)
        client.max_queued_messages_set(100)
        client.reconnect_delay_set(min_delay=1, max_delay=30)

        return client

    def _configure_tls(self, client: mqtt.Client) -> None:
        """Configure TLS settings for MQTT client."""
        self.logger.info("Configuring MQTT TLS connection")

        try:
            # Use paho-mqtt's tls_set() method
            # For simple TLS (like Let's Encrypt), no arguments needed
            if (
                not self.config.mqtt.tls_ca_cert
                and not self.config.mqtt.tls_client_cert
                and not self.config.mqtt.tls_client_key
            ):
                # Simple TLS setup (e.g., Let's Encrypt)
                client.tls_set()
                self.logger.info("Using default TLS configuration")
            else:
                # Custom certificate setup
                client.tls_set(
                    ca_certs=self.config.mqtt.tls_ca_cert,
                    certfile=self.config.mqtt.tls_client_cert,
                    keyfile=self.config.mqtt.tls_client_key,
                )
                self.logger.info("Using custom TLS certificates")

            # Handle insecure mode
            if self.config.mqtt.tls_insecure:
                self.logger.warning("TLS certificate verification disabled")
                client.tls_insecure_set(True)

            self.logger.info("MQTT TLS configuration completed successfully")

        except Exception as e:
            self.logger.error(f"Failed to configure MQTT TLS: {e}")
            raise RuntimeError(f"TLS configuration failed: {e}")

    async def _connect_with_retry(self, max_retries: int = 5) -> None:
        """Connect to MQTT broker with retry logic."""
        for attempt in range(max_retries):
            try:
                if self.client:
                    await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: self.client.connect(  # type: ignore
                            self.config.mqtt.broker, self.config.mqtt.port, 60
                        ),
                    )
                    self.logger.info(
                        f"Connected to MQTT broker on attempt {attempt + 1}"
                    )
                    return
            except Exception as e:
                self.logger.warning(
                    f"MQTT connection attempt {attempt + 1} failed: {e}"
                )
                if attempt < max_retries - 1:
                    delay = min(2**attempt, 30)
                    self.logger.info(f"Retrying MQTT connection in {delay} seconds")
                    await asyncio.sleep(delay)
                else:
                    raise RuntimeError(
                        f"Failed to connect to MQTT broker after "
                        f"{max_retries} attempts: {e}"
                    )

    async def _recover_connection(self) -> None:
        """Recover MQTT connection with complete client recreation."""
        if self._reconnecting:
            self.logger.debug("MQTT recovery already in progress")
            return

        if self._reconnect_attempts >= self._max_reconnect_attempts:
            self.logger.error("Max MQTT reconnection attempts reached")
            return

        self._reconnecting = True
        self._reconnect_attempts += 1

        self.logger.warning(
            f"Starting MQTT recovery (attempt "
            f"{self._reconnect_attempts}/{self._max_reconnect_attempts})"
        )

        try:
            # Destroy old client
            await self._destroy_client()

            # Wait with exponential backoff
            delay = min(2**self._reconnect_attempts, 30)
            self.logger.info(f"Waiting {delay}s before MQTT reconnection")
            await asyncio.sleep(delay)

            # Create fresh client and connection
            await self._create_fresh_connection()

            # Success - reset counters
            self._reconnect_attempts = 0
            self._reconnecting = False
            self._connected = True
            self._last_activity = time.time()

            self.logger.info("MQTT connection recovery successful")

        except Exception as e:
            self.logger.error(
                f"MQTT recovery attempt {self._reconnect_attempts} failed: {e}"
            )
            self._reconnecting = False

            # Schedule retry if we haven't hit max attempts
            if self._reconnect_attempts < self._max_reconnect_attempts:
                retry_delay = min(5 * self._reconnect_attempts, 60)
                self.logger.info(f"Scheduling MQTT retry in {retry_delay}s")
                await asyncio.sleep(retry_delay)
                if self._running:
                    asyncio.create_task(self._recover_connection())
            else:
                self.logger.error("🚨 MQTT recovery failed permanently")

    async def _destroy_client(self) -> None:
        """Destroy the existing MQTT client."""
        if not self.client:
            return

        self.logger.debug("Destroying old MQTT client")

        try:
            if hasattr(self.client, "_loop_started"):
                self.client.loop_stop()
                delattr(self.client, "_loop_started")

            if self.client.is_connected():
                self.client.disconnect()

            # Remove callbacks
            self.client.on_connect = None
            self.client.on_disconnect = None
            self.client.on_message = None
            self.client.on_publish = None
            self.client.on_log = None

        except Exception as e:
            self.logger.debug(f"Error during MQTT client destruction: {e}")
        finally:
            self.client = None
            self._connected = False

    async def _create_fresh_connection(self) -> None:
        """Create fresh client and establish connection."""
        self.logger.info("Creating fresh MQTT client")

        # Create and configure new client
        self.client = self._create_client()
        # We handle reconnection manually

        # Connect
        self.logger.debug(
            f"Connecting to {self.config.mqtt.broker}:{self.config.mqtt.port}"
        )

        if self.client:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.connect(  # type: ignore
                    self.config.mqtt.broker, self.config.mqtt.port, 60
                ),
            )

        # Start client loop
        self.client.loop_start()

        # Wait for connection
        await asyncio.sleep(2)

        if not self.client.is_connected():
            raise RuntimeError("MQTT client failed to connect")

        self.logger.info("Fresh MQTT client connected")

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: Dict[str, Any],
        rc: int,
        properties: Any = None,
    ) -> None:
        """Handle MQTT connection."""
        if rc == 0:
            self.logger.info("Connected to MQTT broker")
            self._connected = True
            self._last_activity = time.time()

            # Subscribe to command topics
            command_topic = f"{self.config.mqtt.topic_prefix}/command/+"
            client.subscribe(command_topic, self.config.mqtt.qos)
            self.logger.info(f"Subscribed to MQTT topic: {command_topic}")
        else:
            self.logger.error(f"Failed to connect to MQTT broker: {rc}")
            self._connected = False

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: Dict[str, Any],
        rc: int,
        properties: Any = None,
    ) -> None:
        """Handle MQTT disconnection."""
        self._connected = False
        if rc != 0:
            self.logger.warning(
                f"🔴 Unexpected MQTT disconnection: {mqtt.error_string(rc)} (code: {rc})"
            )
            if self._running and not self._reconnecting:
                self.logger.info("Triggering MQTT recovery from disconnect callback")
                asyncio.create_task(self._recover_connection())
        else:
            self.logger.info("MQTT client disconnected cleanly")

    def _on_message(
        self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage
    ) -> None:
        """Handle incoming MQTT messages."""
        try:
            topic_parts = message.topic.split("/")
            if len(topic_parts) >= 3 and topic_parts[1] == "command":
                command_type = topic_parts[2]
                payload = message.payload.decode("utf-8")

                self.logger.info(f"Received MQTT command: {command_type} = {payload}")

                # Call registered handler if available
                if command_type in self._message_handlers:
                    self._message_handlers[command_type](command_type, payload)
                elif self._default_command_handler:
                    self._default_command_handler(command_type, payload)
                else:
                    self.logger.warning(
                        f"No handler registered for command: {command_type}"
                    )

        except Exception as e:
            self.logger.error(f"Error processing MQTT message: {e}")

    def _on_publish(
        self,
        client: mqtt.Client,
        userdata: Any,
        mid: int,
        reason_codes: Any = None,
        properties: Any = None,
    ) -> None:
        """Handle MQTT publish confirmation."""
        self.logger.debug(f"MQTT message published: {mid}")

    def _on_log(self, client: mqtt.Client, userdata: Any, level: int, buf: str) -> None:
        """Handle MQTT logging."""
        if level == mqtt.MQTT_LOG_DEBUG:
            self.logger.debug(f"MQTT: {buf}")
        elif level == mqtt.MQTT_LOG_INFO:
            self.logger.info(f"MQTT: {buf}")
        elif level == mqtt.MQTT_LOG_NOTICE:
            self.logger.info(f"MQTT: {buf}")
        elif level == mqtt.MQTT_LOG_WARNING:
            self.logger.warning(f"MQTT: {buf}")
        elif level == mqtt.MQTT_LOG_ERR:
            self.logger.error(f"MQTT: {buf}")
        else:
            self.logger.debug(f"MQTT ({level}): {buf}")

    def register_command_handler(
        self, command_type: str, handler: Callable[[str, str], None]
    ) -> None:
        """Register a handler for MQTT commands."""
        if command_type == "*":
            # Special case: register handler for all command types
            self._default_command_handler = handler
        else:
            self._message_handlers[command_type] = handler
        self.logger.debug(f"Registered handler for command: {command_type}")

    def publish(
        self,
        topic: str,
        payload: str,
        qos: Optional[int] = None,
        retain: Optional[bool] = None,
    ) -> bool:
        """Publish message to MQTT broker."""
        if not self.client:
            self.logger.error("MQTT client not initialized")
            return False

        try:
            if not self.client.is_connected():
                self.logger.warning(
                    f"MQTT client not connected, skipping publish to {topic}"
                )
                if self._running:
                    self.logger.debug(
                        "Triggering MQTT reconnection from publish method"
                    )
                    asyncio.create_task(self._recover_connection())
                return False

            qos = qos if qos is not None else self.config.mqtt.qos
            retain = retain if retain is not None else self.config.mqtt.retain

            self.logger.debug(
                f"Publishing to MQTT: topic={topic}, qos={qos}, retain={retain}, "
                f"payload_length={len(payload)}"
            )

            result = self.client.publish(topic, payload, qos=qos, retain=retain)

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self.logger.info(f"Successfully published to MQTT topic: {topic}")
                self._last_activity = time.time()
                if qos > 0:
                    result.wait_for_publish(timeout=5.0)
                return True
            elif result.rc == mqtt.MQTT_ERR_NO_CONN:
                self.logger.warning(f"MQTT not connected while publishing to {topic}")
                if self._running:
                    asyncio.create_task(self._recover_connection())
                return False
            else:
                self.logger.error(
                    f"Failed to publish to MQTT topic {topic}: "
                    f"{mqtt.error_string(result.rc)} ({result.rc})"
                )
                return False

        except (ConnectionError, OSError, BrokenPipeError) as e:
            self.logger.error(f"Connection error during MQTT publish to {topic}: {e}")
            if self._running:
                self.logger.info("Triggering MQTT reconnection due to connection error")
                asyncio.create_task(self._recover_connection())
            return False
        except Exception as e:
            self.logger.error(
                f"Unexpected exception during MQTT publish to {topic}: {e}"
            )
            return False

    def is_connected(self) -> bool:
        """Check if MQTT client is connected."""
        return (
            self._connected and self.client is not None and self.client.is_connected()
        )

    def is_stale(self, timeout_seconds: int = 300) -> bool:
        """Check if connection appears stale."""
        if not self._last_activity:
            return False
        return time.time() - self._last_activity > timeout_seconds

    async def health_check(self) -> bool:
        """Perform health check and trigger recovery if needed."""
        if not self.is_connected():
            if self._connected and not self._reconnecting:
                self.logger.warning("🔴 MQTT connection lost, starting recovery")
                self._connected = False
                asyncio.create_task(self._recover_connection())
            return False

        if self.is_stale():
            self.logger.warning("MQTT connection appears stale, forcing reconnection")
            asyncio.create_task(self._recover_connection())
            return False

        return True
