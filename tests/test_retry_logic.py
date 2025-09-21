"""Tests for message retry logic."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from meshcore_mqtt.config import Config, ConnectionType, MeshCoreConfig, MQTTConfig
from meshcore_mqtt.meshcore_worker import MeshCoreWorker


@pytest.fixture
def mock_config() -> Config:
    """Create test configuration."""
    return Config(
        mqtt=MQTTConfig(broker="test-broker"),
        meshcore=MeshCoreConfig(
            connection_type=ConnectionType.TCP,
            address="test-address",
            port=12345,
            message_retry_count=3,
            message_retry_delay=1.0,
            reset_path_on_failure=True,
        ),
    )


@pytest.fixture
def worker(mock_config: Config) -> MeshCoreWorker:
    """Create MeshCore worker instance."""
    return MeshCoreWorker(mock_config)


class TestRetryConfiguration:
    """Test retry configuration parameters."""

    def test_default_retry_config(self) -> None:
        """Test default retry configuration values."""
        config = MeshCoreConfig(
            connection_type=ConnectionType.TCP, address="test", port=12345
        )
        assert config.message_retry_count == 3
        assert config.message_retry_delay == 2.0
        assert config.reset_path_on_failure is True

    def test_custom_retry_config(self) -> None:
        """Test custom retry configuration values."""
        config = MeshCoreConfig(
            connection_type=ConnectionType.TCP,
            address="test",
            port=12345,
            message_retry_count=5,
            message_retry_delay=3.5,
            reset_path_on_failure=False,
        )
        assert config.message_retry_count == 5
        assert config.message_retry_delay == 3.5
        assert config.reset_path_on_failure is False

    def test_retry_config_validation(self) -> None:
        """Test retry configuration validation."""
        # Valid range
        config = MeshCoreConfig(
            connection_type=ConnectionType.TCP,
            address="test",
            port=12345,
            message_retry_count=10,
            message_retry_delay=30.0,
        )
        assert config.message_retry_count == 10
        assert config.message_retry_delay == 30.0

        # Invalid retry count
        with pytest.raises(ValueError):
            MeshCoreConfig(
                connection_type=ConnectionType.TCP,
                address="test",
                port=12345,
                message_retry_count=11,
            )

        # Invalid retry delay
        with pytest.raises(ValueError):
            MeshCoreConfig(
                connection_type=ConnectionType.TCP,
                address="test",
                port=12345,
                message_retry_delay=31.0,
            )


class TestMessageRetryLogic:
    """Test message retry functionality."""

    @pytest.mark.asyncio
    async def test_send_msg_with_retry_success_first_attempt(
        self, worker: MeshCoreWorker
    ) -> None:
        """Test successful message send on first attempt."""
        # Mock MeshCore commands
        mock_result = MagicMock()
        mock_result.payload = {"expected_ack": "test_ack", "suggested_timeout": 5000}

        worker.meshcore = MagicMock()
        worker.meshcore.commands = MagicMock()
        worker.meshcore.commands.send_msg = AsyncMock(return_value=mock_result)

        # Mock ack received
        with patch.object(worker, "_wait_for_ack", return_value=True):
            result = await worker._send_msg_with_retry("destination", "message")

        assert result == mock_result
        worker.meshcore.commands.send_msg.assert_called_once_with(
            "destination", "message"
        )

    @pytest.mark.asyncio
    async def test_send_msg_with_retry_success_after_retries(
        self, worker: MeshCoreWorker
    ) -> None:
        """Test successful message send after retries."""
        # Mock MeshCore commands
        mock_result = MagicMock()
        mock_result.payload = {"expected_ack": "test_ack", "suggested_timeout": 5000}

        worker.meshcore = MagicMock()
        worker.meshcore.commands = MagicMock()
        worker.meshcore.commands.send_msg = AsyncMock(return_value=mock_result)

        # Mock ack not received first two times, then received
        ack_results = [False, False, True]
        with patch.object(worker, "_wait_for_ack", side_effect=ack_results):
            result = await worker._send_msg_with_retry("destination", "message")

        assert result == mock_result
        assert worker.meshcore.commands.send_msg.call_count == 3

    @pytest.mark.asyncio
    async def test_send_msg_with_retry_failure(self, worker: MeshCoreWorker) -> None:
        """Test message send failure after all retries."""
        # Mock MeshCore commands
        mock_result = MagicMock()
        mock_result.payload = {"expected_ack": "test_ack", "suggested_timeout": 5000}

        worker.meshcore = MagicMock()
        worker.meshcore.commands = MagicMock()
        worker.meshcore.commands.send_msg = AsyncMock(return_value=mock_result)

        # Mock ack never received
        with patch.object(worker, "_wait_for_ack", return_value=False):
            with patch.object(worker, "_reset_path", new_callable=AsyncMock):
                result = await worker._send_msg_with_retry("destination", "message")

        assert result is None
        # Should try initial + 3 retries + 1 after path reset = 5 total
        assert worker.meshcore.commands.send_msg.call_count == 4

    @pytest.mark.asyncio
    async def test_send_msg_with_path_reset(self, worker: MeshCoreWorker) -> None:
        """Test path reset after max retries."""
        # Mock MeshCore commands
        mock_result = MagicMock()
        mock_result.payload = {"expected_ack": "test_ack", "suggested_timeout": 5000}

        worker.meshcore = MagicMock()
        worker.meshcore.commands = MagicMock()
        worker.meshcore.commands.send_msg = AsyncMock(return_value=mock_result)

        # Mock ack never received
        mock_reset_path = AsyncMock()
        with patch.object(worker, "_wait_for_ack", return_value=False):
            with patch.object(worker, "_reset_path", mock_reset_path):
                await worker._send_msg_with_retry("destination", "message")

        # Path reset should be called once
        mock_reset_path.assert_called_once_with("destination")

    @pytest.mark.asyncio
    async def test_send_msg_no_ack_info(self, worker: MeshCoreWorker) -> None:
        """Test message send when no ack info is provided."""
        # Mock MeshCore commands - no ack info in response
        mock_result = MagicMock()
        mock_result.payload = {}

        worker.meshcore = MagicMock()
        worker.meshcore.commands = MagicMock()
        worker.meshcore.commands.send_msg = AsyncMock(return_value=mock_result)

        result = await worker._send_msg_with_retry("destination", "message")

        assert result == mock_result
        # Should only send once since no ack tracking
        worker.meshcore.commands.send_msg.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_chan_msg_with_retry_success(
        self, worker: MeshCoreWorker
    ) -> None:
        """Test successful channel message send with retry."""
        # Mock MeshCore commands
        mock_result = MagicMock()
        mock_result.payload = {"expected_ack": "test_ack", "suggested_timeout": 5000}

        worker.meshcore = MagicMock()
        worker.meshcore.commands = MagicMock()
        worker.meshcore.commands.send_chan_msg = AsyncMock(return_value=mock_result)

        # Mock ack received
        with patch.object(worker, "_wait_for_ack", return_value=True):
            result = await worker._send_chan_msg_with_retry(0, "message")

        assert result == mock_result
        worker.meshcore.commands.send_chan_msg.assert_called_once_with(0, "message")

    @pytest.mark.asyncio
    async def test_wait_for_ack_timeout(self, worker: MeshCoreWorker) -> None:
        """Test acknowledgement timeout."""
        ack_key = "test_ack"
        event = asyncio.Event()
        worker._pending_acks[ack_key] = event

        # Test timeout
        result = await worker._wait_for_ack(ack_key, 0.1)
        assert result is False
        assert ack_key not in worker._pending_acks

    @pytest.mark.asyncio
    async def test_wait_for_ack_received(self, worker: MeshCoreWorker) -> None:
        """Test acknowledgement received."""
        ack_key = "test_ack"

        async def set_ack() -> None:
            await asyncio.sleep(0.05)
            worker._ack_results[ack_key] = True
            if ack_key in worker._pending_acks:
                worker._pending_acks[ack_key].set()

        # Start the ack setter
        asyncio.create_task(set_ack())

        # Wait for ack
        result = await worker._wait_for_ack(ack_key, 1.0)
        assert result is True

    def test_on_ack_received(self, worker: MeshCoreWorker) -> None:
        """Test acknowledgement event handler."""
        ack_key = "test_ack"
        event = asyncio.Event()
        worker._pending_acks[ack_key] = event

        # Mock ack data
        ack_data = MagicMock()
        ack_data.payload = {"ack": "test_ack"}

        # Process ack
        worker._on_ack_received(ack_data)

        assert worker._ack_results[ack_key] is True
        assert event.is_set()

    @pytest.mark.asyncio
    async def test_reset_path(self, worker: MeshCoreWorker) -> None:
        """Test path reset functionality."""
        worker.meshcore = MagicMock()
        worker.meshcore.commands = MagicMock()
        worker.meshcore.commands.send_trace = AsyncMock()

        await worker._reset_path("destination")

        worker.meshcore.commands.send_trace.assert_called_once_with(flags=1)

    @pytest.mark.asyncio
    async def test_exponential_backoff(self, worker: MeshCoreWorker) -> None:
        """Test exponential backoff timing."""
        # Set shorter delays for testing
        worker.config.meshcore.message_retry_delay = 0.1

        # Mock MeshCore commands
        mock_result = MagicMock()
        mock_result.payload = {"expected_ack": "test_ack", "suggested_timeout": 5000}

        worker.meshcore = MagicMock()
        worker.meshcore.commands = MagicMock()
        worker.meshcore.commands.send_msg = AsyncMock(return_value=mock_result)

        # Track timing
        call_times = []

        async def mock_send_msg(*args: str) -> MagicMock:
            call_times.append(asyncio.get_event_loop().time())
            return mock_result

        worker.meshcore.commands.send_msg = mock_send_msg

        # Mock ack never received
        with patch.object(worker, "_wait_for_ack", return_value=False):
            with patch.object(worker, "_reset_path", new_callable=AsyncMock):
                await worker._send_msg_with_retry("destination", "message")

        # Check exponential backoff timing
        assert len(call_times) == 4  # Initial + 3 retries
        if len(call_times) > 1:
            # First retry after base_delay (0.1s)
            assert 0.05 < (call_times[1] - call_times[0]) < 0.2
        if len(call_times) > 2:
            # Second retry after base_delay * 2 (0.2s)
            assert 0.15 < (call_times[2] - call_times[1]) < 0.3
        if len(call_times) > 3:
            # Third attempt happens immediately after path reset (no delay)
            assert (call_times[3] - call_times[2]) < 0.1
