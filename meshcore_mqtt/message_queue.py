"""Message queue system for inbox/outbox communication between threads."""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class MessageType(Enum):
    """Types of messages that can be sent between components."""

    # MeshCore to MQTT
    MESHCORE_MESSAGE = "meshcore_message"
    MESHCORE_STATUS = "meshcore_status"
    MESHCORE_EVENT = "meshcore_event"

    # MQTT to MeshCore
    MQTT_COMMAND = "mqtt_command"
    MQTT_STATUS = "mqtt_status"

    # Control messages
    SHUTDOWN = "shutdown"
    HEALTH_CHECK = "health_check"


class ComponentStatus(Enum):
    """Status of a component."""

    STARTING = "starting"
    RUNNING = "running"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    STOPPING = "stopping"
    STOPPED = "stopped"


@dataclass
class Message:
    """A message in the inbox/outbox system."""

    id: str
    message_type: MessageType
    source: str
    target: str
    payload: Any
    timestamp: float
    metadata: Optional[Dict[str, Any]] = None

    @classmethod
    def create(
        cls,
        message_type: MessageType,
        source: str,
        target: str,
        payload: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "Message":
        """Create a new message with auto-generated ID and timestamp."""
        import uuid

        return cls(
            id=uuid.uuid4().hex[:8],
            message_type=message_type,
            source=source,
            target=target,
            payload=payload,
            timestamp=time.time(),
            metadata=metadata or {},
        )


class MessageQueue:
    """Thread-safe message queue for component communication."""

    def __init__(self, name: str, max_size: int = 1000) -> None:
        """Initialize the message queue."""
        self.name = name
        self.max_size = max_size
        self.logger = logging.getLogger(f"{__name__}.{name}")

        # Use asyncio.Queue for thread-safe async operations
        self._queue: asyncio.Queue[Message] = asyncio.Queue(maxsize=max_size)
        self._dropped_messages = 0

    async def put(self, message: Message, timeout: Optional[float] = None) -> bool:
        """Put a message in the queue. Returns True if successful."""
        try:
            if timeout is None:
                await self._queue.put(message)
            else:
                await asyncio.wait_for(self._queue.put(message), timeout=timeout)

            self.logger.debug(
                f"Queued {message.message_type.value} from {message.source} "
                f"to {message.target} (id: {message.id})"
            )
            return True

        except asyncio.TimeoutError:
            self.logger.warning(
                f"Timeout queueing message {message.id} "
                f"({message.message_type.value})"
            )
            return False
        except asyncio.QueueFull:
            self._dropped_messages += 1
            self.logger.warning(
                f"Queue {self.name} full, dropping message {message.id} "
                f"(total dropped: {self._dropped_messages})"
            )
            return False
        except Exception as e:
            self.logger.error(f"Error queueing message {message.id}: {e}")
            return False

    async def get(self, timeout: Optional[float] = None) -> Optional[Message]:
        """Get a message from the queue. Returns None on timeout or error."""
        try:
            if timeout is None:
                message = await self._queue.get()
            else:
                message = await asyncio.wait_for(self._queue.get(), timeout=timeout)

            self.logger.debug(
                f"Dequeued {message.message_type.value} from {message.source} "
                f"to {message.target} (id: {message.id})"
            )
            return message

        except asyncio.TimeoutError:
            return None
        except Exception as e:
            self.logger.error(f"Error getting message from queue: {e}")
            return None

    async def get_nowait(self) -> Optional[Message]:
        """Get a message without waiting. Returns None if queue is empty."""
        try:
            message = self._queue.get_nowait()
            self.logger.debug(
                f"Dequeued (nowait) {message.message_type.value} from "
                f"{message.source} to {message.target} (id: {message.id})"
            )
            return message
        except asyncio.QueueEmpty:
            return None
        except Exception as e:
            self.logger.error(f"Error getting message nowait: {e}")
            return None

    def qsize(self) -> int:
        """Get the approximate size of the queue."""
        return self._queue.qsize()

    def empty(self) -> bool:
        """Check if the queue is empty."""
        return self._queue.empty()

    def full(self) -> bool:
        """Check if the queue is full."""
        return self._queue.full()

    def stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        return {
            "name": self.name,
            "size": self.qsize(),
            "max_size": self.max_size,
            "dropped_messages": self._dropped_messages,
            "empty": self.empty(),
            "full": self.full(),
        }


class MessageBus:
    """Central message bus coordinating inbox/outbox between components."""

    def __init__(self) -> None:
        """Initialize the message bus."""
        self.logger = logging.getLogger(__name__)

        # Component queues
        self._queues: Dict[str, MessageQueue] = {}

        # Component status tracking
        self._component_status: Dict[str, ComponentStatus] = {}

        # Running state
        self._running = False
        self._shutdown_event = asyncio.Event()

    def register_component(self, name: str, queue_size: int = 1000) -> MessageQueue:
        """Register a component and get its message queue."""
        if name in self._queues:
            self.logger.warning(f"Component {name} already registered")
            return self._queues[name]

        queue = MessageQueue(name, max_size=queue_size)
        self._queues[name] = queue
        self._component_status[name] = ComponentStatus.STARTING

        self.logger.info(f"Registered component: {name}")
        return queue

    def update_component_status(self, name: str, status: ComponentStatus) -> None:
        """Update the status of a component."""
        old_status = self._component_status.get(name, ComponentStatus.STARTING)
        self._component_status[name] = status

        if old_status != status:
            self.logger.info(f"Component {name}: {old_status.value} -> {status.value}")

    def get_component_status(self, name: str) -> Optional[ComponentStatus]:
        """Get the status of a component."""
        return self._component_status.get(name)

    async def send_message(
        self, message: Message, timeout: Optional[float] = 1.0
    ) -> bool:
        """Send a message to the target component."""
        target_queue = self._queues.get(message.target)
        if not target_queue:
            self.logger.error(f"Unknown target component: {message.target}")
            return False

        return await target_queue.put(message, timeout=timeout)

    async def broadcast_message(
        self,
        message_type: MessageType,
        source: str,
        payload: Any,
        exclude: Optional[list[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Broadcast a message to all components except excluded ones."""
        exclude = exclude or []
        exclude.append(source)  # Don't send to self

        sent_count = 0
        for target in self._queues.keys():
            if target not in exclude:
                message = Message.create(
                    message_type=message_type,
                    source=source,
                    target=target,
                    payload=payload,
                    metadata=metadata,
                )
                if await self.send_message(message):
                    sent_count += 1

        return sent_count

    async def shutdown(self) -> None:
        """Shutdown the message bus and notify all components."""
        self.logger.info("Shutting down message bus")
        self._running = False

        # Send shutdown messages to all components
        await self.broadcast_message(
            MessageType.SHUTDOWN,
            source="message_bus",
            payload={"reason": "shutdown_requested"},
        )

        self._shutdown_event.set()

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics for all queues and components."""
        return {
            "components": {
                name: {"status": status.value, "queue": queue.stats()}
                for name, (status, queue) in zip(
                    self._component_status.keys(),
                    [
                        (self._component_status[name], self._queues[name])
                        for name in self._component_status.keys()
                    ],
                )
            },
            "total_components": len(self._queues),
            "running": self._running,
        }


# Global message bus instance
_message_bus: Optional[MessageBus] = None


def get_message_bus() -> MessageBus:
    """Get the global message bus instance."""
    global _message_bus
    if _message_bus is None:
        _message_bus = MessageBus()
    return _message_bus


def reset_message_bus() -> None:
    """Reset the global message bus (mainly for testing)."""
    global _message_bus
    _message_bus = None
