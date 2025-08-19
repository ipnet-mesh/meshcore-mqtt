"""Independent MeshCore worker with inbox/outbox message handling."""

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    import serial
else:
    try:
        import serial
    except ImportError:
        serial = None

from meshcore import (
    BLEConnection,
    ConnectionManager,
    EventType,
    MeshCore,
    SerialConnection,
    TCPConnection,
)

from .config import Config, ConnectionType
from .message_queue import (
    ComponentStatus,
    Message,
    MessageBus,
    MessageQueue,
    MessageType,
    get_message_bus,
)


class MeshCoreWorker:
    """Independent MeshCore worker managing device connection and messaging."""

    def __init__(self, config: Config) -> None:
        """Initialize MeshCore worker."""
        self.config = config
        self.logger = logging.getLogger(__name__)

        # Component identification
        self.component_name = "meshcore"

        # Message bus
        self.message_bus: MessageBus = get_message_bus()
        self.inbox: MessageQueue = self.message_bus.register_component(
            self.component_name, queue_size=1000
        )

        # MeshCore components
        self.meshcore: Optional[MeshCore] = None
        self.connection_manager: Optional[ConnectionManager] = None

        # Connection state
        self._connected = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
        self._last_activity: Optional[float] = None
        self._auto_fetch_running = False
        self._last_health_check: Optional[float] = None
        self._consecutive_health_failures = 0
        self._max_health_failures = 3

        # Worker state
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._tasks: list[asyncio.Task[Any]] = []

    async def start(self) -> None:
        """Start the MeshCore worker."""
        if self._running:
            self.logger.warning("MeshCore worker is already running")
            return

        self.logger.info("Starting MeshCore worker")
        self._running = True

        # Update status
        self.message_bus.update_component_status(
            self.component_name, ComponentStatus.STARTING
        )

        try:
            # Setup MeshCore connection
            await self._setup_connection()

            # Start worker tasks
            tasks = [
                asyncio.create_task(
                    self._message_processor(), name="meshcore_processor"
                ),
                asyncio.create_task(self._health_monitor(), name="meshcore_health"),
                asyncio.create_task(
                    self._auto_fetch_monitor(), name="meshcore_autofetch"
                ),
            ]
            self._tasks.extend(tasks)

            # Update status to running
            self.message_bus.update_component_status(
                self.component_name, ComponentStatus.RUNNING
            )

            self.logger.info("MeshCore worker started successfully")

            # Wait for shutdown
            await self._shutdown_event.wait()

        except Exception as e:
            self.logger.error(f"Error starting MeshCore worker: {e}")
            self.message_bus.update_component_status(
                self.component_name, ComponentStatus.ERROR
            )
            raise
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the MeshCore worker."""
        if not self._running:
            return

        self.logger.info("Stopping MeshCore worker")
        self.message_bus.update_component_status(
            self.component_name, ComponentStatus.STOPPING
        )

        self._running = False
        self._shutdown_event.set()

        # Cancel all tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        # Stop MeshCore connection
        if self.meshcore:
            try:
                await self.meshcore.stop_auto_message_fetching()
                await self.meshcore.disconnect()
            except Exception as e:
                self.logger.error(f"Error stopping MeshCore connection: {e}")

        self.message_bus.update_component_status(
            self.component_name, ComponentStatus.STOPPED
        )
        self.logger.info("MeshCore worker stopped")

    async def _setup_connection(self) -> None:
        """Set up MeshCore connection."""
        self.logger.info("Setting up MeshCore connection")

        # Create appropriate connection based on configuration
        if self.config.meshcore.connection_type == ConnectionType.TCP:
            connection = TCPConnection(
                self.config.meshcore.address, self.config.meshcore.port or 12345
            )
        elif self.config.meshcore.connection_type == ConnectionType.SERIAL:
            connection = SerialConnection(
                self.config.meshcore.address, self.config.meshcore.baudrate
            )
        elif self.config.meshcore.connection_type == ConnectionType.BLE:
            connection = BLEConnection(self.config.meshcore.address)
        else:
            raise ValueError(
                f"Unsupported connection type: {self.config.meshcore.connection_type}"
            )

        # Initialize connection manager and MeshCore
        self.connection_manager = ConnectionManager(connection)

        # Enable debug logging only if log level is DEBUG
        debug_logging = self.config.log_level == "DEBUG"

        self.meshcore = MeshCore(
            self.connection_manager,
            debug=debug_logging,
            auto_reconnect=True,
            default_timeout=self.config.meshcore.timeout,
        )

        # Configure MeshCore logger
        meshcore_logger = logging.getLogger("meshcore")
        meshcore_logger.setLevel(getattr(logging, self.config.log_level))

        # Set up event subscriptions
        await self._setup_event_subscriptions()

        # Connect to MeshCore device
        try:
            await self.meshcore.connect()
            self.logger.info("Connected to MeshCore device")
            self._connected = True
            self._last_activity = time.time()

            # Send connection status
            await self._send_status_update(ComponentStatus.CONNECTED, "connected")

            # Start auto message fetching
            await self.meshcore.start_auto_message_fetching()
            self.logger.info("Started auto message fetching")
            self._auto_fetch_running = True

        except Exception as e:
            await self._send_status_update(
                ComponentStatus.ERROR, f"connection_failed: {e}"
            )
            raise RuntimeError(f"Failed to connect to MeshCore device: {e}")

    async def _setup_event_subscriptions(self) -> None:
        """Set up MeshCore event subscriptions."""
        self.logger.info("Setting up MeshCore event subscriptions")
        configured_events = set(self.config.meshcore.events)

        # Subscribe to configured events
        if self.meshcore:
            for event_name in configured_events:
                try:
                    event_type = getattr(EventType, event_name)
                    self.meshcore.subscribe(event_type, self._on_meshcore_event)
                    self.logger.info(f"Subscribed to event: {event_name}")
                except AttributeError:
                    self.logger.warning(f"Unknown event type: {event_name}")

            # Always subscribe to NO_MORE_MSGS for auto-fetch management
            try:
                no_more_msgs_event = getattr(EventType, "NO_MORE_MSGS")
                self.meshcore.subscribe(no_more_msgs_event, self._on_meshcore_event)
                self.logger.info(
                    "Subscribed to NO_MORE_MSGS event for auto-fetch management"
                )
            except AttributeError:
                self.logger.warning("NO_MORE_MSGS event type not available")

    async def _message_processor(self) -> None:
        """Process messages from the inbox."""
        self.logger.info("Starting MeshCore message processor")

        while self._running:
            try:
                # Get message from inbox with timeout
                message = await self.inbox.get(timeout=1.0)
                if message is None:
                    continue

                await self._handle_inbox_message(message)

            except Exception as e:
                self.logger.error(f"Error in message processor: {e}")
                await asyncio.sleep(1)

    async def _handle_inbox_message(self, message: Message) -> None:
        """Handle a message from the inbox."""
        self.logger.debug(f"Processing message: {message.message_type.value}")

        try:
            if message.message_type == MessageType.MQTT_COMMAND:
                await self._handle_mqtt_command(message)
            elif message.message_type == MessageType.HEALTH_CHECK:
                await self._handle_health_check(message)
            elif message.message_type == MessageType.SHUTDOWN:
                self.logger.info("Received shutdown message")
                self._shutdown_event.set()
            else:
                self.logger.warning(
                    f"Unknown message type: {message.message_type.value}"
                )

        except Exception as e:
            self.logger.error(f"Error handling message {message.id}: {e}")

    async def _handle_mqtt_command(self, message: Message) -> None:
        """Handle MQTT command forwarded from MQTT worker."""
        if not self.meshcore:
            self.logger.error("MeshCore not initialized, cannot process command")
            return

        command_data = message.payload
        command_type = command_data.get("command_type", "")

        self.logger.info(f"Processing MQTT command: {command_type}")

        try:
            result = None

            if command_type == "send_msg":
                destination = command_data.get("destination")
                msg_text = command_data.get("message", "")
                if not destination or not msg_text:
                    self.logger.error(
                        "send_msg requires 'destination' and 'message' fields"
                    )
                    return
                result = await self.meshcore.commands.send_msg(destination, msg_text)

            elif command_type == "device_query":
                result = await self.meshcore.commands.send_device_query()

            elif command_type == "get_battery":
                result = await self.meshcore.commands.get_bat()

            elif command_type == "set_name":
                name = command_data.get("name", "")
                if not name:
                    self.logger.error("set_name requires 'name' field")
                    return
                result = await self.meshcore.commands.set_name(name)

            elif command_type == "send_chan_msg":
                channel = command_data.get("channel")
                msg_text = command_data.get("message", "")
                if channel is None or not msg_text:
                    self.logger.error(
                        "send_chan_msg requires 'channel' and 'message' fields"
                    )
                    return
                result = await self.meshcore.commands.send_chan_msg(channel, msg_text)

            elif command_type == "ping":
                destination = command_data.get("destination")
                if not destination:
                    self.logger.error("ping requires 'destination' field")
                    return
                result = await self.meshcore.commands.ping(destination)

            elif command_type == "send_advert":
                flood = command_data.get("flood", False)
                result = await self.meshcore.commands.send_advert(flood=flood)

            elif command_type == "send_trace":
                auth_code = command_data.get("auth_code", 0)
                tag = command_data.get("tag")  # Optional, will be auto-generated
                flags = command_data.get("flags", 0)
                path = command_data.get("path")  # Optional path specification
                result = await self.meshcore.commands.send_trace(
                    auth_code=auth_code, tag=tag, flags=flags, path=path
                )

            elif command_type == "send_telemetry_req":
                destination = command_data.get("destination")
                if not destination:
                    self.logger.error("send_telemetry_req requires 'destination' field")
                    return
                result = await self.meshcore.commands.send_telemetry_req(destination)

            else:
                self.logger.warning(f"Unknown command type: {command_type}")
                return

            # Handle result and update activity
            if result and hasattr(result, "type"):
                if result.type == EventType.ERROR:
                    self.logger.error(
                        f"MeshCore command '{command_type}' failed: {result.payload}"
                    )
                else:
                    self.logger.info(f"MeshCore command '{command_type}' successful")
                    self.update_activity()
            else:
                self.logger.info(f"MeshCore command '{command_type}' completed")
                self.update_activity()

        except AttributeError as e:
            self.logger.error(f"MeshCore command '{command_type}' unavailable: {e}")
        except Exception as e:
            self.logger.error(f"Error executing command '{command_type}': {e}")

    async def _handle_health_check(self, message: Message) -> None:
        """Handle health check request."""
        healthy = await self._perform_health_check()

        # Send health status back
        response = Message.create(
            message_type=MessageType.HEALTH_CHECK,
            source=self.component_name,
            target=message.source,
            payload={
                "healthy": healthy,
                "connected": self._connected,
                "last_activity": self._last_activity,
                "auto_fetch_running": self._auto_fetch_running,
            },
        )
        await self.message_bus.send_message(response)

    async def _health_monitor(self) -> None:
        """Monitor MeshCore connection health."""
        self.logger.info("Starting MeshCore health monitor")

        # Wait for initial connection to stabilize
        await asyncio.sleep(5)

        while self._running:
            try:
                healthy = await self._perform_health_check()

                if not healthy and self._connected:
                    self.logger.warning(
                        "MeshCore health check failed, attempting recovery"
                    )
                    await self._recover_connection()

                await asyncio.sleep(10)  # Health check every 10 seconds

            except Exception as e:
                self.logger.error(f"Error in health monitor: {e}")
                await asyncio.sleep(30)

    async def _perform_health_check(self) -> bool:
        """Perform comprehensive health check."""
        if not self.meshcore:
            self._consecutive_health_failures += 1
            return False

        try:
            # Check basic connectivity
            basic_healthy = (
                hasattr(self.meshcore, "connection_manager")
                and self.meshcore.connection_manager is not None
            )

            # Enhanced health check for different connection types
            connection_healthy = await self._check_connection_health()

            healthy = basic_healthy and connection_healthy

            if healthy:
                self._consecutive_health_failures = 0
            else:
                self._consecutive_health_failures += 1

            # Check for stale connections
            if healthy and self._is_stale(timeout_seconds=180):
                self.logger.warning("MeshCore connection appears stale")
                return False

            return healthy

        except Exception as e:
            self.logger.debug(f"Health check exception: {e}")
            self._consecutive_health_failures += 1
            return False

    async def _check_connection_health(self) -> bool:
        """Check if the underlying connection is healthy."""
        if not self.meshcore or not self.meshcore.connection_manager:
            return False

        try:
            connection = self.meshcore.connection_manager.connection
            current_time = time.time()

            # Check if we should perform an intensive health check
            should_deep_check = (
                self._last_health_check is None
                or (current_time - self._last_health_check) > 10
            )

            # For serial connections, perform more rigorous checks
            if hasattr(connection, "port") and hasattr(connection, "is_open"):
                if not connection.is_open:
                    self.logger.warning("Serial connection is closed")
                    return False

                if should_deep_check:
                    try:
                        # Check if serial port still exists
                        if serial:
                            import serial.tools.list_ports

                            available_ports = [
                                port.device
                                for port in serial.tools.list_ports.comports()
                            ]
                            if connection.port not in available_ports:
                                self.logger.warning(
                                    f"Serial port {connection.port} no longer available"
                                )
                                return False

                        # Try to check if the serial connection is responsive
                        if hasattr(connection, "in_waiting"):
                            _ = connection.in_waiting
                        if hasattr(connection, "out_waiting"):
                            _ = connection.out_waiting

                    except (ImportError, OSError) as e:
                        self.logger.warning(f"Serial port health check failed: {e}")
                        return False

                    self._last_health_check = current_time

            # For TCP connections
            elif hasattr(connection, "host") and hasattr(connection, "port"):
                if should_deep_check:
                    self._last_health_check = current_time

            # For BLE connections
            elif hasattr(connection, "address"):
                if should_deep_check:
                    self._last_health_check = current_time

            return True

        except Exception as e:
            self.logger.debug(f"Connection health check failed: {e}")
            return False

    async def _auto_fetch_monitor(self) -> None:
        """Monitor and maintain auto-fetch functionality."""
        self.logger.info("Starting auto-fetch monitor")

        while self._running:
            try:
                if self.meshcore and self._connected and not self._auto_fetch_running:
                    self.logger.info("Restarting MeshCore auto-fetch")
                    try:
                        await self.meshcore.start_auto_message_fetching()
                        self._auto_fetch_running = True
                        self.update_activity()
                    except Exception as e:
                        self.logger.error(f"Failed to restart auto-fetch: {e}")

                await asyncio.sleep(60)  # Check every minute

            except Exception as e:
                self.logger.error(f"Error in auto-fetch monitor: {e}")
                await asyncio.sleep(60)

    async def _recover_connection(self) -> None:
        """Recover MeshCore connection."""
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            self.logger.error("Max MeshCore reconnection attempts reached")
            await self._send_status_update(
                ComponentStatus.ERROR, "max_reconnect_attempts"
            )
            return

        self._reconnect_attempts += 1
        self.logger.warning(
            f"Starting MeshCore recovery (attempt "
            f"{self._reconnect_attempts}/{self._max_reconnect_attempts})"
        )

        # Update status
        await self._send_status_update(ComponentStatus.DISCONNECTED, "reconnecting")

        try:
            # Stop existing connection
            if self.meshcore:
                try:
                    await self.meshcore.stop_auto_message_fetching()
                    await self.meshcore.disconnect()
                except Exception as e:
                    self.logger.debug(f"Error stopping old MeshCore connection: {e}")

            # Wait before attempting reconnection with exponential backoff
            delay = min(2 ** (self._reconnect_attempts - 1), 300)
            self.logger.info(f"Waiting {delay}s before MeshCore reconnection")
            await asyncio.sleep(delay)

            # Re-setup connection
            await self._setup_connection()
            self._reconnect_attempts = 0
            self.logger.info("MeshCore connection recovery successful")

        except Exception as e:
            self.logger.error(
                f"MeshCore recovery attempt {self._reconnect_attempts} failed: {e}"
            )
            await self._send_status_update(
                ComponentStatus.ERROR, f"recovery_failed: {e}"
            )

            if self._reconnect_attempts < self._max_reconnect_attempts:
                # Schedule retry
                retry_delay = min(2**self._reconnect_attempts, 300)
                self.logger.info(f"Scheduling MeshCore retry in {retry_delay}s")
                await asyncio.sleep(retry_delay)
                if self._running:
                    asyncio.create_task(self._recover_connection())
            else:
                self.logger.error("🚨 MeshCore recovery failed permanently")

    def _on_meshcore_event(self, event_data: Any) -> None:
        """Handle MeshCore events and forward them to MQTT."""
        try:
            self.update_activity()

            # Log the event for debugging
            event_type_name = getattr(event_data, "type", "UNKNOWN")
            event_name = (
                str(event_type_name).split(".")[-1] if event_type_name else "UNKNOWN"
            )

            # Handle NO_MORE_MSGS for auto-fetch management
            if event_name == "NO_MORE_MSGS":
                self.logger.debug(f"Received NO_MORE_MSGS event: {event_data}")
                self._auto_fetch_running = False
                # Don't forward NO_MORE_MSGS to MQTT as it's internal
                return

            # Add extra logging for connection events to help debug
            if event_name in ["CONNECTED", "DISCONNECTED"]:
                self.logger.info(f"MeshCore {event_name} event received: {event_data}")

            # Create message for MQTT worker
            message = Message.create(
                message_type=MessageType.MESHCORE_EVENT,
                source=self.component_name,
                target="mqtt",
                payload={"event_data": event_data, "timestamp": time.time()},
            )

            # Send to message bus (non-blocking)
            asyncio.create_task(self.message_bus.send_message(message))

        except Exception as e:
            self.logger.error(f"Error processing MeshCore event: {e}")

    async def _send_status_update(self, status: ComponentStatus, details: str) -> None:
        """Send status update to other components."""
        self.message_bus.update_component_status(self.component_name, status)

        message = Message.create(
            message_type=MessageType.MESHCORE_STATUS,
            source=self.component_name,
            target="mqtt",
            payload={
                "status": status.value,
                "details": details,
                "connected": self._connected,
                "timestamp": time.time(),
            },
        )
        await self.message_bus.send_message(message)

    def update_activity(self) -> None:
        """Update the last activity timestamp."""
        self._last_activity = time.time()

    def _is_stale(self, timeout_seconds: int = 300) -> bool:
        """Check if connection appears stale."""
        if not self._last_activity:
            return False
        return time.time() - self._last_activity > timeout_seconds

    def serialize_to_json(self, data: Any) -> str:
        """Safely serialize any data to JSON string."""
        import json
        from datetime import datetime, timezone

        try:
            # Handle common data types
            if isinstance(data, (dict, list, str, int, float, bool)) or data is None:
                return json.dumps(data, ensure_ascii=False)

            # Handle objects with custom serialization
            if hasattr(data, "__dict__"):
                obj_dict = {
                    key: value
                    for key, value in data.__dict__.items()
                    if not key.startswith("_")
                }
                if obj_dict:
                    return json.dumps(obj_dict, ensure_ascii=False, default=str)

            # Handle iterables
            if hasattr(data, "__iter__") and not isinstance(data, (str, bytes)):
                try:
                    return json.dumps(list(data), ensure_ascii=False, default=str)
                except (TypeError, ValueError):
                    pass

            # Fallback: structured JSON with metadata
            return json.dumps(
                {
                    "type": type(data).__name__,
                    "value": str(data),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                ensure_ascii=False,
            )

        except Exception as e:
            self.logger.warning(f"Failed to serialize data to JSON: {e}")
            return json.dumps(
                {
                    "error": f"Serialization failed: {str(e)}",
                    "raw_value": str(data)[:1000],
                    "type": type(data).__name__,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                ensure_ascii=False,
            )
