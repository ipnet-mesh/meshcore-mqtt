"""Tests for MeshCore worker rate limiting functionality."""

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from meshcore_mqtt.config import Config, ConnectionType, MeshCoreConfig, MQTTConfig
from meshcore_mqtt.meshcore_worker import MeshCoreWorker


@pytest.fixture
def test_config() -> Config:
    """Create a test configuration with rate limiting settings."""
    return Config(
        mqtt=MQTTConfig(broker="localhost"),
        meshcore=MeshCoreConfig(
            connection_type=ConnectionType.TCP,
            address="127.0.0.1",
            port=12345,
            message_initial_delay=0.1,  # 100ms for faster tests
            message_send_delay=0.2,     # 200ms for faster tests
        ),
    )


@pytest.fixture
def test_config_zero_delays() -> Config:
    """Create a test configuration with zero delays."""
    return Config(
        mqtt=MQTTConfig(broker="localhost"),
        meshcore=MeshCoreConfig(
            connection_type=ConnectionType.TCP,
            address="127.0.0.1",
            port=12345,
            message_initial_delay=0.0,
            message_send_delay=0.0,
        ),
    )


@pytest.fixture
def mock_meshcore_worker(test_config: Config) -> MeshCoreWorker:
    """Create a MeshCore worker with mocked MeshCore instance."""
    worker = MeshCoreWorker(test_config)

    # Mock the MeshCore instance
    mock_meshcore = MagicMock()
    mock_meshcore.commands = MagicMock()
    mock_meshcore.commands.send_msg = AsyncMock(return_value=MagicMock())
    mock_meshcore.commands.send_chan_msg = AsyncMock(return_value=MagicMock())
    mock_meshcore.commands.send_device_query = AsyncMock(return_value=MagicMock())
    worker.meshcore = mock_meshcore

    return worker


class TestRateLimiting:
    """Test message rate limiting functionality."""

    async def test_message_initial_delay(self, mock_meshcore_worker: MeshCoreWorker) -> None:
        """Test that initial delay is applied before the first message."""
        start_time = time.time()

        # Set worker to running state
        mock_meshcore_worker._running = True

        # Queue a message
        command_data = {"destination": "test", "message": "test"}
        future = asyncio.Future()
        message_data = {
            "command_type": "send_msg",
            "future": future,
            **command_data
        }

        await mock_meshcore_worker._message_queue.put(message_data)

        # Start the rate limiter
        rate_limiter_task = asyncio.create_task(mock_meshcore_worker._message_rate_limiter())

        # Wait for the message to be processed
        try:
            await asyncio.wait_for(future, timeout=1.0)
        except asyncio.TimeoutError:
            pass
        finally:
            mock_meshcore_worker._running = False  # Stop the rate limiter
            rate_limiter_task.cancel()
            try:
                await rate_limiter_task
            except asyncio.CancelledError:
                pass

        elapsed_time = time.time() - start_time

        # Should take at least the initial delay time
        assert elapsed_time >= mock_meshcore_worker.config.meshcore.message_initial_delay

    async def test_message_send_delay(self, mock_meshcore_worker: MeshCoreWorker) -> None:
        """Test that delay is applied between consecutive messages."""
        # Set worker to running state
        mock_meshcore_worker._running = True

        # Set the last message time to simulate a previous message
        mock_meshcore_worker._last_message_time = time.time()

        start_time = time.time()

        # Queue a message
        command_data = {"destination": "test", "message": "test"}
        future = asyncio.Future()
        message_data = {
            "command_type": "send_msg",
            "future": future,
            **command_data
        }

        await mock_meshcore_worker._message_queue.put(message_data)

        # Start the rate limiter
        rate_limiter_task = asyncio.create_task(mock_meshcore_worker._message_rate_limiter())

        # Wait for the message to be processed
        try:
            await asyncio.wait_for(future, timeout=1.0)
        except asyncio.TimeoutError:
            pass
        finally:
            mock_meshcore_worker._running = False  # Stop the rate limiter
            rate_limiter_task.cancel()
            try:
                await rate_limiter_task
            except asyncio.CancelledError:
                pass

        elapsed_time = time.time() - start_time

        # Should take at least the send delay time
        assert elapsed_time >= mock_meshcore_worker.config.meshcore.message_send_delay

    async def test_no_delay_with_zero_config(self, test_config_zero_delays: Config) -> None:
        """Test that no delays are applied when configured to zero."""
        worker = MeshCoreWorker(test_config_zero_delays)

        # Mock the MeshCore instance
        mock_meshcore = MagicMock()
        mock_meshcore.commands = MagicMock()
        mock_meshcore.commands.send_msg = AsyncMock(return_value=MagicMock())
        worker.meshcore = mock_meshcore

        # Set worker to running state
        worker._running = True

        start_time = time.time()

        # Queue a message
        command_data = {"destination": "test", "message": "test"}
        future = asyncio.Future()
        message_data = {
            "command_type": "send_msg",
            "future": future,
            **command_data
        }

        await worker._message_queue.put(message_data)

        # Start the rate limiter
        rate_limiter_task = asyncio.create_task(worker._message_rate_limiter())

        # Wait for the message to be processed
        try:
            await asyncio.wait_for(future, timeout=0.5)
        except asyncio.TimeoutError:
            pass
        finally:
            worker._running = False  # Stop the rate limiter
            rate_limiter_task.cancel()
            try:
                await rate_limiter_task
            except asyncio.CancelledError:
                pass

        elapsed_time = time.time() - start_time

        # Should complete quickly with no delays
        assert elapsed_time < 0.1

    async def test_rate_limited_command_execution(self, mock_meshcore_worker: MeshCoreWorker) -> None:
        """Test that rate-limited commands are executed correctly."""
        # Test send_msg command
        result = await mock_meshcore_worker._execute_rate_limited_message({
            "command_type": "send_msg",
            "destination": "test_user",
            "message": "Hello",
            "future": None
        })

        # Verify the command was called
        mock_meshcore_worker.meshcore.commands.send_msg.assert_called_once_with("test_user", "Hello")

        # Test send_chan_msg command
        await mock_meshcore_worker._execute_rate_limited_message({
            "command_type": "send_chan_msg",
            "channel": 0,
            "message": "Hello channel",
            "future": None
        })

        # Verify the command was called
        mock_meshcore_worker.meshcore.commands.send_chan_msg.assert_called_once_with(0, "Hello channel")

    async def test_queue_rate_limited_command(self, mock_meshcore_worker: MeshCoreWorker) -> None:
        """Test queuing and execution of rate-limited commands."""
        # Set worker to running state
        mock_meshcore_worker._running = True

        # Start the rate limiter in the background
        rate_limiter_task = asyncio.create_task(mock_meshcore_worker._message_rate_limiter())

        try:
            # Queue a command
            command_data = {"destination": "test_user", "message": "Hello"}
            result_task = asyncio.create_task(
                mock_meshcore_worker._queue_rate_limited_command("send_msg", command_data)
            )

            # Wait for completion
            result = await asyncio.wait_for(result_task, timeout=2.0)

            # Verify the command was executed
            mock_meshcore_worker.meshcore.commands.send_msg.assert_called_once_with("test_user", "Hello")

        finally:
            mock_meshcore_worker._running = False  # Stop the rate limiter
            rate_limiter_task.cancel()
            try:
                await rate_limiter_task
            except asyncio.CancelledError:
                pass

    async def test_multiple_messages_rate_limiting(self, mock_meshcore_worker: MeshCoreWorker) -> None:
        """Test that multiple messages are properly rate limited."""
        # Set worker to running state
        mock_meshcore_worker._running = True

        # Start the rate limiter
        rate_limiter_task = asyncio.create_task(mock_meshcore_worker._message_rate_limiter())

        try:
            start_time = time.time()

            # Queue multiple messages
            tasks = []
            for i in range(3):
                command_data = {"destination": f"user{i}", "message": f"Message {i}"}
                task = asyncio.create_task(
                    mock_meshcore_worker._queue_rate_limited_command("send_msg", command_data)
                )
                tasks.append(task)

            # Wait for all messages to complete
            await asyncio.gather(*tasks)

            elapsed_time = time.time() - start_time

            # Should take at least initial_delay + 2 * send_delay for 3 messages
            expected_min_time = (
                mock_meshcore_worker.config.meshcore.message_initial_delay +
                2 * mock_meshcore_worker.config.meshcore.message_send_delay
            )
            assert elapsed_time >= expected_min_time

            # Verify all commands were executed
            assert mock_meshcore_worker.meshcore.commands.send_msg.call_count == 3

        finally:
            mock_meshcore_worker._running = False  # Stop the rate limiter
            rate_limiter_task.cancel()
            try:
                await rate_limiter_task
            except asyncio.CancelledError:
                pass

    async def test_rate_limiter_error_handling(self, mock_meshcore_worker: MeshCoreWorker) -> None:
        """Test error handling in rate-limited message execution."""
        # Set worker to running state
        mock_meshcore_worker._running = True

        # Make the mock command raise an exception - but we need to bypass the retry logic
        # So we'll make it raise an exception in _execute_rate_limited_message directly
        original_execute = mock_meshcore_worker._execute_rate_limited_message

        async def mock_execute(message_data):
            future = message_data.get("future")
            if future and not future.done():
                future.set_exception(Exception("Test error"))

        mock_meshcore_worker._execute_rate_limited_message = mock_execute

        # Start the rate limiter
        rate_limiter_task = asyncio.create_task(mock_meshcore_worker._message_rate_limiter())

        try:
            # Queue a command that will fail
            command_data = {"destination": "test_user", "message": "Hello"}

            with pytest.raises(Exception, match="Test error"):
                await asyncio.wait_for(
                    mock_meshcore_worker._queue_rate_limited_command("send_msg", command_data),
                    timeout=2.0
                )

        finally:
            mock_meshcore_worker._running = False  # Stop the rate limiter
            mock_meshcore_worker._execute_rate_limited_message = original_execute  # Restore original
            rate_limiter_task.cancel()
            try:
                await rate_limiter_task
            except asyncio.CancelledError:
                pass

    async def test_configuration_validation(self) -> None:
        """Test that rate limiting configuration is properly validated."""
        # Test valid configuration
        config = Config(
            mqtt=MQTTConfig(broker="localhost"),
            meshcore=MeshCoreConfig(
                connection_type=ConnectionType.TCP,
                address="127.0.0.1",
                message_initial_delay=5.0,
                message_send_delay=10.0,
            ),
        )
        assert config.meshcore.message_initial_delay == 5.0
        assert config.meshcore.message_send_delay == 10.0

        # Test that values are within valid range
        config = Config(
            mqtt=MQTTConfig(broker="localhost"),
            meshcore=MeshCoreConfig(
                connection_type=ConnectionType.TCP,
                address="127.0.0.1",
                message_initial_delay=0.0,  # Minimum
                message_send_delay=60.0,    # Maximum
            ),
        )
        assert config.meshcore.message_initial_delay == 0.0
        assert config.meshcore.message_send_delay == 60.0

        # Test that invalid values raise validation errors
        with pytest.raises(Exception):
            Config(
                mqtt=MQTTConfig(broker="localhost"),
                meshcore=MeshCoreConfig(
                    connection_type=ConnectionType.TCP,
                    address="127.0.0.1",
                    message_initial_delay=-1.0,  # Invalid: negative
                ),
            )

        with pytest.raises(Exception):
            Config(
                mqtt=MQTTConfig(broker="localhost"),
                meshcore=MeshCoreConfig(
                    connection_type=ConnectionType.TCP,
                    address="127.0.0.1",
                    message_send_delay=61.0,  # Invalid: too large
                ),
            )