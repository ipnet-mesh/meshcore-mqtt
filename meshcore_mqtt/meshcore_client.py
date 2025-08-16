"""MeshCore client management for bridge."""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

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


class MeshCoreClientManager:
    """Manages MeshCore device connection, event handling, and recovery."""

    def __init__(self, config: Config) -> None:
        """Initialize MeshCore client manager."""
        self.config = config
        self.logger = logging.getLogger(__name__)

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

        # Event handlers
        self._event_handlers: Dict[str, Callable[[Any], None]] = {}

        # Running state
        self._running = False

    async def start(self) -> None:
        """Start the MeshCore client."""
        if self._running:
            self.logger.warning("MeshCore client is already running")
            return

        self.logger.info("Starting MeshCore client")
        self._running = True

        # Setup MeshCore connection
        await self._setup_connection()

    async def stop(self) -> None:
        """Stop the MeshCore client."""
        if not self._running:
            return

        self.logger.info("Stopping MeshCore client")
        self._running = False

        if self.meshcore:
            try:
                await self.meshcore.stop_auto_message_fetching()
                await self.meshcore.disconnect()
            except Exception as e:
                self.logger.error(f"Error stopping MeshCore client: {e}")

        self.logger.info("MeshCore client stopped")

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

            # Start auto message fetching
            await self.meshcore.start_auto_message_fetching()
            self.logger.info("Started auto message fetching")
            self._auto_fetch_running = True
        except Exception as e:
            raise RuntimeError(f"Failed to connect to MeshCore device: {e}")

    async def _setup_event_subscriptions(self) -> None:
        """Set up MeshCore event subscriptions."""
        self.logger.info("Setting up MeshCore event subscriptions")
        configured_events = set(self.config.meshcore.events)

        # Always subscribe to NO_MORE_MSGS to restart auto-fetching
        if self.meshcore:
            try:
                no_more_msgs_event = getattr(EventType, "NO_MORE_MSGS")
                self.meshcore.subscribe(no_more_msgs_event, self._on_no_more_msgs)
                self.logger.info(
                    "Subscribed to NO_MORE_MSGS event for auto-fetch restart"
                )
            except AttributeError:
                self.logger.warning("NO_MORE_MSGS event type not available")

        # Subscribe to configured events
        subscribed_events = set()
        if self.meshcore:
            for event_name in configured_events:
                try:
                    event_type = getattr(EventType, event_name)
                    # Use registered handler or default debug handler
                    handler = self._event_handlers.get(event_name, self._on_debug_event)
                    self.meshcore.subscribe(event_type, handler)
                    subscribed_events.add(event_name)
                    self.logger.info(f"Subscribed to event: {event_name}")
                except AttributeError:
                    self.logger.warning(f"Unknown event type: {event_name}")

    async def _recover_connection(self) -> None:
        """Recover MeshCore connection."""
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            self.logger.error("Max MeshCore reconnection attempts reached")
            return

        self._reconnect_attempts += 1
        self.logger.warning(
            f"Starting MeshCore recovery (attempt "
            f"{self._reconnect_attempts}/{self._max_reconnect_attempts})"
        )

        try:
            # Stop existing connection
            if self.meshcore:
                try:
                    await self.meshcore.stop_auto_message_fetching()
                    await self.meshcore.disconnect()
                except Exception as e:
                    self.logger.debug(f"Error stopping old MeshCore connection: {e}")

            # Wait before attempting reconnection with exponential backoff
            delay = min(2 ** (self._reconnect_attempts - 1), 300)  # Max 5 minutes
            self.logger.info(
                f"Waiting {delay}s before MeshCore reconnection (exponential backoff)"
            )
            await asyncio.sleep(delay)

            # Re-setup connection
            await self._setup_connection()
            self._reconnect_attempts = 0
            self.logger.info("MeshCore connection recovery successful")

        except Exception as e:
            self.logger.error(
                f"MeshCore recovery attempt {self._reconnect_attempts} failed: {e}"
            )
            if self._reconnect_attempts < self._max_reconnect_attempts:
                retry_delay = min(
                    2**self._reconnect_attempts, 300
                )  # Exponential backoff, max 5 minutes
                self.logger.info(
                    f"Scheduling MeshCore retry in {retry_delay}s (exponential backoff)"
                )
                await asyncio.sleep(retry_delay)
                if self._running:
                    asyncio.create_task(self._recover_connection())
            else:
                self.logger.error("🚨 MeshCore recovery failed permanently")

    async def _maintain_auto_fetch(self) -> None:
        """Continuously maintain auto-fetch, restarting if it stops."""
        self.logger.info("Starting persistent auto-fetch maintenance")

        while self._running:
            try:
                if self.meshcore and self._connected and not self._auto_fetch_running:
                    self.logger.info("Starting/restarting MeshCore auto-fetch")
                    try:
                        await self.meshcore.start_auto_message_fetching()
                        self._auto_fetch_running = True
                        self._last_activity = time.time()
                    except Exception as e:
                        self.logger.error(f"Failed to start auto-fetch: {e}")
                        self._auto_fetch_running = False

                await asyncio.sleep(60)  # Check every minute

            except Exception as e:
                self.logger.error(f"Error in auto-fetch maintenance: {e}")
                await asyncio.sleep(60)

    def _on_no_more_msgs(self, event_data: Any) -> None:
        """Handle NO_MORE_MSGS events - mark auto-fetch as stopped."""
        self.logger.info(f"Received NO_MORE_MSGS event: {event_data}")
        self.logger.info(
            "Auto-fetch has stopped - persistent maintenance will restart it"
        )

        self._auto_fetch_running = False
        self._last_activity = time.time()

    def _on_debug_event(self, event_data: Any) -> None:
        """Handle any other MeshCore events for debugging."""
        event_info = f"type: {type(event_data)}, data: {event_data}"
        self.logger.debug(f"MeshCore debug event: {event_info}")
        print(f"DEBUG EVENT: {event_info}")

    def serialize_to_json(self, data: Any) -> str:
        """Safely serialize any data to JSON string."""
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

    def register_event_handler(
        self, event_name: str, handler: Callable[[Any], None]
    ) -> None:
        """Register an event handler for a specific MeshCore event."""
        self._event_handlers[event_name] = handler
        self.logger.debug(f"Registered handler for event: {event_name}")

    async def _safe_command_call(
        self,
        command_func: Callable[..., Any],
        command_type: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Safely call a MeshCore command with proper error handling."""
        try:
            return await command_func(*args, **kwargs)
        except AttributeError as e:
            self.logger.error(
                f"Command '{command_type}' not supported by MeshCore version: {e}"
            )
            return None
        except Exception as e:
            self.logger.error(f"Error executing command '{command_type}': {e}")
            return None

    async def send_command(self, command_type: str, command_data: Any) -> None:
        """Send command to MeshCore device."""
        if not self.meshcore:
            self.logger.error("MeshCore not initialized")
            return

        try:
            self.logger.info(
                f"Sending command to MeshCore: {command_type} -> {command_data}"
            )

            result = None

            if command_type == "send_msg":
                # Send direct message
                destination = command_data.get("destination")
                message = command_data.get("message", "")
                if not destination or not message:
                    self.logger.error(
                        "send_msg requires 'destination' and 'message' fields"
                    )
                    return
                result = await self._safe_command_call(
                    self.meshcore.commands.send_msg, "send_msg", destination, message
                )

            elif command_type == "device_query":
                # Query device information
                result = await self._safe_command_call(
                    self.meshcore.commands.send_device_query, "device_query"
                )

            elif command_type == "get_battery":
                # Get battery status
                result = await self._safe_command_call(
                    self.meshcore.commands.get_bat, "get_battery"
                )

            elif command_type == "set_name":
                # Set device name
                name = command_data.get("name", "")
                if not name:
                    self.logger.error("set_name requires 'name' field")
                    return
                result = await self._safe_command_call(
                    self.meshcore.commands.set_name, "set_name", name
                )

            elif command_type == "send_chan_msg":
                # Send channel message
                channel = command_data.get("channel")
                message = command_data.get("message", "")
                if channel is None or not message:
                    self.logger.error(
                        "send_chan_msg requires 'channel' and 'message' fields"
                    )
                    return
                result = await self._safe_command_call(
                    self.meshcore.commands.send_chan_msg,
                    "send_chan_msg",
                    channel,
                    message,
                )

            elif command_type == "ping":
                # Ping a node
                destination = command_data.get("destination")
                if not destination:
                    self.logger.error("ping requires 'destination' field")
                    return
                result = await self._safe_command_call(
                    self.meshcore.commands.ping, "ping", destination
                )

            else:
                self.logger.warning(f"Unknown command type: {command_type}")
                return

            # Handle result
            if result and hasattr(result, "type"):
                if result.type == EventType.ERROR:
                    self.logger.error(
                        f"MeshCore command '{command_type}' failed: {result.payload}"
                    )
                else:
                    self.logger.info(f"MeshCore command '{command_type}' successful")
                    # Update activity timestamp on successful command
                    self.update_activity()
            else:
                self.logger.info(f"MeshCore command '{command_type}' completed")
                self.update_activity()

        except AttributeError as e:
            # Handle case where commands attribute doesn't exist
            self.logger.error(f"MeshCore command '{command_type}' unavailable: {e}")
        except Exception as e:
            self.logger.error(
                f"Error sending command '{command_type}' to MeshCore: {e}"
            )

    def is_connected(self) -> bool:
        """Check if MeshCore client is connected."""
        return self._connected

    def is_stale(self, timeout_seconds: int = 300) -> bool:
        """Check if connection appears stale."""
        if not self._last_activity:
            return False
        return time.time() - self._last_activity > timeout_seconds

    async def health_check(self) -> bool:
        """Perform health check and trigger recovery if needed."""
        # Basic health check
        if not self.meshcore:
            self._consecutive_health_failures += 1
            return False

        try:
            # Check if MeshCore and connection manager exist
            basic_healthy = (
                hasattr(self.meshcore, "connection_manager")
                and self.meshcore.connection_manager is not None
            )

            # Enhanced health check for serial connections
            connection_healthy = await self._check_connection_health()

            healthy = basic_healthy and connection_healthy

            if healthy:
                # Reset failure counter on successful health check
                self._consecutive_health_failures = 0
            else:
                self._consecutive_health_failures += 1
                self.logger.debug(
                    f"Health check failed (attempt {self._consecutive_health_failures}"
                    f"/{self._max_health_failures})"
                )

            # Only trigger recovery after multiple consecutive failures
            if (
                self._consecutive_health_failures >= self._max_health_failures
                and self._connected
            ):
                self.logger.warning(
                    f"MeshCore connection lost after "
                    f"{self._consecutive_health_failures} "
                    "failed health checks, attempting recovery"
                )
                self._connected = False
                self._consecutive_health_failures = 0
                asyncio.create_task(self._recover_connection())
                return False

            # Check for stale connections with more aggressive detection
            if healthy and self.is_stale(timeout_seconds=180):  # 3 minutes
                self.logger.warning(
                    "MeshCore connection appears stale, forcing reconnection"
                )
                self._consecutive_health_failures = 0
                asyncio.create_task(self._recover_connection())
                return False

            return healthy

        except Exception as e:
            self.logger.debug(f"Health check exception: {e}")
            self._consecutive_health_failures += 1
            return False

    async def _check_connection_health(self) -> bool:
        """Check if the underlying connection is healthy, especially for serial."""
        if not self.meshcore or not self.meshcore.connection_manager:
            return False

        try:
            connection = self.meshcore.connection_manager.connection
            current_time = time.time()

            # Check if we should perform an intensive health check
            should_deep_check = (
                self._last_health_check is None
                or (current_time - self._last_health_check)
                > 10  # Deep check every 10 seconds
            )

            # Basic connection manager check
            if not hasattr(self.meshcore.connection_manager, "is_connected"):
                # Check if connection manager has basic connectivity indicators
                try:
                    # Try to access connection manager state
                    if hasattr(self.meshcore.connection_manager, "connection"):
                        conn = self.meshcore.connection_manager.connection
                        if conn is None:
                            self.logger.warning("Connection manager has no connection")
                            return False
                except Exception as e:
                    self.logger.warning(f"Connection manager check failed: {e}")
                    return False

            # For serial connections, perform more rigorous checks
            if hasattr(connection, "port") and hasattr(connection, "is_open"):
                # This is likely a SerialConnection
                if not connection.is_open:
                    self.logger.warning("Serial connection is closed")
                    return False

                if should_deep_check:
                    # Check if the serial port still exists in the system
                    try:
                        import serial.tools.list_ports

                        available_ports = [
                            port.device for port in serial.tools.list_ports.comports()
                        ]
                        if connection.port not in available_ports:
                            self.logger.warning(
                                f"Serial port {connection.port} no longer available"
                            )
                            return False
                    except ImportError:
                        # pyserial not available for port checking, skip this test
                        pass
                    except Exception as e:
                        self.logger.debug(
                            f"Error checking serial port availability: {e}"
                        )

                    # Try to check if the serial connection is actually responsive
                    try:
                        # Check serial port properties that indicate connection health
                        if hasattr(connection, "in_waiting"):
                            # This property access can fail if device is unplugged
                            _ = connection.in_waiting
                        if hasattr(connection, "out_waiting"):
                            _ = connection.out_waiting
                    except OSError as e:
                        self.logger.warning(f"Serial port appears disconnected: {e}")
                        return False
                    except Exception as e:
                        self.logger.debug(f"Serial health check error: {e}")
                        # Don't fail on unexpected errors, but log them
                        pass

                    self._last_health_check = current_time

            # For TCP connections, check socket state
            elif hasattr(connection, "host") and hasattr(connection, "port"):
                # This is likely a TCPConnection
                if should_deep_check:
                    try:
                        # Check if the underlying socket exists and is connected
                        if hasattr(connection, "_socket") and connection._socket:
                            # Try to check socket state
                            pass  # The meshcore library should handle this
                    except Exception as e:
                        self.logger.debug(f"TCP health check error: {e}")

                    self._last_health_check = current_time

            # For BLE connections
            elif hasattr(connection, "address"):
                # This is likely a BLEConnection
                if should_deep_check:
                    # BLE connection health is handled by the meshcore library
                    self._last_health_check = current_time

            # Check activity staleness more aggressively
            if self._last_activity and should_deep_check:
                time_since_activity = current_time - self._last_activity
                if time_since_activity > 120:  # 2 minutes of no activity
                    self.logger.warning(
                        f"No MeshCore activity for {time_since_activity:.1f}s, "
                        "connection may be stale"
                    )
                    return False

            return True

        except Exception as e:
            self.logger.debug(f"Connection health check failed: {e}")
            return False

    def get_auto_fetch_task(self) -> asyncio.Task[None]:
        """Get the auto-fetch maintenance task."""
        return asyncio.create_task(self._maintain_auto_fetch())

    def update_activity(self) -> None:
        """Update the last activity timestamp."""
        self._last_activity = time.time()
