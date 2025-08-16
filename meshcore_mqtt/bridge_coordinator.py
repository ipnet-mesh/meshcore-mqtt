"""Bridge coordinator managing independent MeshCore and MQTT workers."""

import asyncio
import logging
from typing import Any, Optional

from .config import Config
from .meshcore_worker import MeshCoreWorker
from .message_queue import (
    ComponentStatus,
    MessageBus,
    get_message_bus,
    reset_message_bus,
)
from .mqtt_worker import MQTTWorker


class BridgeCoordinator:
    """Coordinates independent MeshCore and MQTT workers with shared messaging."""

    def __init__(self, config: Config) -> None:
        """Initialize the bridge coordinator."""
        self.config = config
        self.logger = logging.getLogger(__name__)

        # Reset message bus for clean start
        reset_message_bus()

        # Message bus
        self.message_bus: MessageBus = get_message_bus()

        # Workers
        self.meshcore_worker: Optional[MeshCoreWorker] = None
        self.mqtt_worker: Optional[MQTTWorker] = None

        # Coordinator state
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._worker_tasks: list[asyncio.Task[Any]] = []

    async def start(self) -> None:
        """Start the bridge coordinator and all workers."""
        if self._running:
            self.logger.warning("Bridge coordinator is already running")
            return

        self.logger.info("Starting MeshCore MQTT Bridge Coordinator")
        self._running = True

        try:
            # Initialize workers
            self.meshcore_worker = MeshCoreWorker(self.config)
            self.mqtt_worker = MQTTWorker(self.config)

            # Start MQTT worker first and wait for it to be connected
            self.logger.info("Starting MQTT worker first...")
            mqtt_task = asyncio.create_task(
                self.mqtt_worker.start(), name="mqtt_worker"
            )
            self._worker_tasks.append(mqtt_task)

            # Wait for MQTT to be connected before starting MeshCore
            await self._wait_for_mqtt_connection()

            # Now start MeshCore worker
            self.logger.info("Starting MeshCore worker...")
            meshcore_task = asyncio.create_task(
                self.meshcore_worker.start(), name="meshcore_worker"
            )
            self._worker_tasks.append(meshcore_task)

            # Start coordinator monitoring
            monitor_task = asyncio.create_task(
                self._monitor_workers(), name="coordinator_monitor"
            )
            self._worker_tasks.append(monitor_task)

            self.logger.info("Bridge coordinator started successfully")

            # Wait for shutdown signal
            await self._shutdown_event.wait()

        except Exception as e:
            self.logger.error(f"Error starting bridge coordinator: {e}")
            raise
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the bridge coordinator and all workers."""
        if not self._running:
            return

        self.logger.info("Stopping MeshCore MQTT Bridge Coordinator")
        self._running = False
        self._shutdown_event.set()

        try:
            # Signal shutdown to message bus
            await self.message_bus.shutdown()

            # Cancel all worker tasks
            for task in self._worker_tasks:
                if not task.done():
                    task.cancel()

            # Wait for tasks to complete
            if self._worker_tasks:
                await asyncio.gather(*self._worker_tasks, return_exceptions=True)
            self._worker_tasks.clear()

            # Stop workers explicitly if they exist
            if self.meshcore_worker:
                await self.meshcore_worker.stop()
            if self.mqtt_worker:
                await self.mqtt_worker.stop()

        except Exception as e:
            self.logger.error(f"Error during coordinator shutdown: {e}")

        self.logger.info("Bridge coordinator stopped")

    async def _monitor_workers(self) -> None:
        """Monitor worker health and overall system status."""
        self.logger.info("Starting coordinator monitoring")

        last_stats_log = 0.0
        stats_interval = 60.0  # Log stats every 60 seconds

        while self._running:
            try:
                current_time = asyncio.get_event_loop().time()

                # Check worker status
                meshcore_status = self.message_bus.get_component_status("meshcore")
                mqtt_status = self.message_bus.get_component_status("mqtt")

                # Log status changes
                if meshcore_status == ComponentStatus.ERROR:
                    self.logger.error("MeshCore worker is in error state")
                if mqtt_status == ComponentStatus.ERROR:
                    self.logger.error("MQTT worker is in error state")

                # Log periodic stats
                if current_time - last_stats_log >= stats_interval:
                    self._log_system_stats()
                    last_stats_log = current_time

                # Check if both workers are in error state
                if (
                    meshcore_status == ComponentStatus.ERROR
                    and mqtt_status == ComponentStatus.ERROR
                ):
                    self.logger.critical(
                        "Both workers are in error state, shutting down"
                    )
                    self._shutdown_event.set()
                    break

                await asyncio.sleep(10)  # Monitor every 10 seconds

            except Exception as e:
                self.logger.error(f"Error in coordinator monitoring: {e}")
                await asyncio.sleep(30)

    def _log_system_stats(self) -> None:
        """Log system statistics."""
        try:
            stats = self.message_bus.get_stats()

            self.logger.info("=== Bridge System Status ===")
            self.logger.info(f"Total components: {stats['total_components']}")

            for name, component_info in stats["components"].items():
                status = component_info["status"]
                queue_stats = component_info["queue"]

                self.logger.info(
                    f"{name.upper()}: {status} | "
                    f"Queue: {queue_stats['size']}/{queue_stats['max_size']} | "
                    f"Dropped: {queue_stats['dropped_messages']}"
                )

            self.logger.info("========================")

        except Exception as e:
            self.logger.error(f"Error logging system stats: {e}")

    async def _wait_for_mqtt_connection(self, timeout: float = 30.0) -> None:
        """Wait for MQTT worker to be connected before proceeding."""
        self.logger.info("Waiting for MQTT worker to connect...")
        start_time = asyncio.get_event_loop().time()

        while self._running:
            mqtt_status = self.message_bus.get_component_status("mqtt")

            if mqtt_status == ComponentStatus.CONNECTED:
                self.logger.info(
                    "MQTT worker is connected, proceeding with MeshCore startup"
                )
                return
            elif mqtt_status == ComponentStatus.ERROR:
                self.logger.warning("MQTT worker is in error state, proceeding anyway")
                return

            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                self.logger.warning(
                    f"Timeout waiting for MQTT connection after {timeout}s, "
                    "proceeding with MeshCore startup"
                )
                return

            await asyncio.sleep(0.5)

    async def health_check(self) -> dict[str, Any]:
        """Perform overall system health check."""
        try:
            stats = self.message_bus.get_stats()

            # Get component statuses
            meshcore_status = self.message_bus.get_component_status("meshcore")
            mqtt_status = self.message_bus.get_component_status("mqtt")

            # Determine overall health
            healthy_statuses = {ComponentStatus.RUNNING, ComponentStatus.CONNECTED}
            meshcore_healthy = meshcore_status in healthy_statuses
            mqtt_healthy = mqtt_status in healthy_statuses
            overall_healthy = meshcore_healthy and mqtt_healthy

            return {
                "healthy": overall_healthy,
                "running": self._running,
                "components": {
                    "meshcore": {
                        "status": (
                            meshcore_status.value if meshcore_status else "unknown"
                        ),
                        "healthy": meshcore_healthy,
                    },
                    "mqtt": {
                        "status": mqtt_status.value if mqtt_status else "unknown",
                        "healthy": mqtt_healthy,
                    },
                },
                "message_bus": stats,
            }

        except Exception as e:
            self.logger.error(f"Error in health check: {e}")
            return {"healthy": False, "error": str(e), "running": self._running}

    def get_stats(self) -> dict[str, Any]:
        """Get comprehensive system statistics."""
        try:
            bus_stats = self.message_bus.get_stats()

            return {
                "coordinator": {
                    "running": self._running,
                    "worker_tasks": len(self._worker_tasks),
                    "active_tasks": sum(1 for t in self._worker_tasks if not t.done()),
                },
                "message_bus": bus_stats,
                "config": {
                    "mqtt_broker": f"{self.config.mqtt.broker}:{self.config.mqtt.port}",
                    "mqtt_topic_prefix": self.config.mqtt.topic_prefix,
                    "meshcore_connection": {
                        "type": self.config.meshcore.connection_type.value,
                        "address": self.config.meshcore.address,
                        "port": getattr(self.config.meshcore, "port", None),
                    },
                    "events": self.config.meshcore.events,
                },
            }

        except Exception as e:
            self.logger.error(f"Error getting stats: {e}")
            return {"error": str(e)}

    # Compatibility methods for existing tests
    @property
    def meshcore(self) -> Any:
        """Compatibility property for tests."""
        return self.meshcore_worker.meshcore if self.meshcore_worker else None

    @property
    def connection_manager(self) -> Any:
        """Compatibility property for tests."""
        if self.meshcore_worker and self.meshcore_worker.meshcore:
            return self.meshcore_worker.meshcore.connection_manager
        return None

    @property
    def mqtt_client(self) -> Any:
        """Compatibility property for tests."""
        return self.mqtt_worker.client if self.mqtt_worker else None

    def _serialize_to_json(self, data: Any) -> str:
        """Compatibility method for tests."""
        if self.meshcore_worker:
            return self.meshcore_worker.serialize_to_json(data)
        return "{}"

    async def _setup_mqtt(self) -> None:
        """Compatibility method for tests."""
        if self.mqtt_worker:
            await self.mqtt_worker._setup_connection()
