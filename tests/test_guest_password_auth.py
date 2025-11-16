"""Tests for guest password authentication functionality."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from meshcore_mqtt.config import Config, ConnectionType, MeshCoreConfig, MQTTConfig
from meshcore_mqtt.meshcore_worker import MeshCoreWorker
from meshcore_mqtt.message_queue import Message, MessageType


@pytest.fixture
def test_config() -> Config:
    """Create a test configuration."""
    return Config(
        mqtt=MQTTConfig(broker="localhost"),
        meshcore=MeshCoreConfig(
            connection_type=ConnectionType.TCP,
            address="127.0.0.1",
            port=5000,
        ),
    )


@pytest.fixture
def meshcore_worker(test_config: Config) -> MeshCoreWorker:
    """Create a MeshCore worker instance for testing."""
    worker = MeshCoreWorker(test_config)
    # Override startup grace period to allow immediate command processing
    worker._startup_grace_period = 0
    return worker


class TestGuestPasswordAuthentication:
    """Test guest password authentication commands."""

    async def test_send_login_command_success(
        self, meshcore_worker: MeshCoreWorker
    ) -> None:
        """Test successful send_login command."""
        # Setup mock MeshCore instance
        mock_meshcore = MagicMock()
        mock_meshcore.commands = MagicMock()
        mock_meshcore.commands.send_login = AsyncMock()
        meshcore_worker.meshcore = mock_meshcore

        # Mock the rate limiting queue to execute immediately
        mock_queue_command = AsyncMock()
        meshcore_worker._queue_rate_limited_command = mock_queue_command

        # Create login command message
        command_data = {"destination": "repeater_node", "password": "guest_password"}
        message = Message.create(
            message_type=MessageType.MQTT_COMMAND,
            source="mqtt",
            target="meshcore",
            payload={"command_type": "send_login", **command_data},
        )

        # Process the command
        await meshcore_worker._handle_mqtt_command(message)

        # Verify the command was queued for rate-limited execution
        expected_data = {"command_type": "send_login", **command_data}
        mock_queue_command.assert_called_once_with(
            "send_login", expected_data
        )

    async def test_send_login_command_missing_destination(
        self, meshcore_worker: MeshCoreWorker
    ) -> None:
        """Test send_login command with missing destination."""
        # Setup mock MeshCore instance
        mock_meshcore = MagicMock()
        mock_meshcore.commands = MagicMock()
        mock_meshcore.commands.send_login = AsyncMock()
        meshcore_worker.meshcore = mock_meshcore

        # Create login command message without destination
        command_data = {"password": "guest_password"}  # Missing destination
        message = Message.create(
            message_type=MessageType.MQTT_COMMAND,
            source="mqtt",
            target="meshcore",
            payload={"command_type": "send_login", **command_data},
        )

        # Process the command
        await meshcore_worker._handle_mqtt_command(message)

        # Verify login command was NOT called due to validation
        mock_meshcore.commands.send_login.assert_not_called()

    async def test_send_login_command_missing_password(
        self, meshcore_worker: MeshCoreWorker
    ) -> None:
        """Test send_login command with missing password."""
        # Setup mock MeshCore instance
        mock_meshcore = MagicMock()
        mock_meshcore.commands = MagicMock()
        mock_meshcore.commands.send_login = AsyncMock()
        meshcore_worker.meshcore = mock_meshcore

        # Create login command message without password
        command_data = {"destination": "repeater_node"}  # Missing password
        message = Message.create(
            message_type=MessageType.MQTT_COMMAND,
            source="mqtt",
            target="meshcore",
            payload={"command_type": "send_login", **command_data},
        )

        # Process the command
        await meshcore_worker._handle_mqtt_command(message)

        # Verify login command was NOT called due to validation
        mock_meshcore.commands.send_login.assert_not_called()

    async def test_send_logoff_command_success(
        self, meshcore_worker: MeshCoreWorker
    ) -> None:
        """Test successful send_logoff command."""
        # Setup mock MeshCore instance
        mock_meshcore = MagicMock()
        mock_meshcore.commands = MagicMock()
        mock_meshcore.commands.send_logoff = AsyncMock()
        meshcore_worker.meshcore = mock_meshcore

        # Mock the rate limiting queue to execute immediately
        mock_queue_command = AsyncMock()
        meshcore_worker._queue_rate_limited_command = mock_queue_command

        # Create logoff command message
        command_data = {"destination": "repeater_node"}
        message = Message.create(
            message_type=MessageType.MQTT_COMMAND,
            source="mqtt",
            target="meshcore",
            payload={"command_type": "send_logoff", **command_data},
        )

        # Process the command
        await meshcore_worker._handle_mqtt_command(message)

        # Verify the command was queued for rate-limited execution
        expected_data = {"command_type": "send_logoff", **command_data}
        mock_queue_command.assert_called_once_with(
            "send_logoff", expected_data
        )

    async def test_send_logoff_command_missing_destination(
        self, meshcore_worker: MeshCoreWorker
    ) -> None:
        """Test send_logoff command with missing destination."""
        # Setup mock MeshCore instance
        mock_meshcore = MagicMock()
        mock_meshcore.commands = MagicMock()
        mock_meshcore.commands.send_logoff = AsyncMock()
        meshcore_worker.meshcore = mock_meshcore

        # Create logoff command message without destination
        command_data = {}  # Missing destination
        message = Message.create(
            message_type=MessageType.MQTT_COMMAND,
            source="mqtt",
            target="meshcore",
            payload={"command_type": "send_logoff", **command_data},
        )

        # Process the command
        await meshcore_worker._handle_mqtt_command(message)

        # Verify logoff command was NOT called due to validation
        mock_meshcore.commands.send_logoff.assert_not_called()

    async def test_send_telemetry_req_with_password(
        self, meshcore_worker: MeshCoreWorker
    ) -> None:
        """Test send_telemetry_req command with password (automatic login)."""
        # Setup mock MeshCore instance
        mock_meshcore = MagicMock()
        mock_meshcore.commands = MagicMock()
        mock_meshcore.commands.send_login = AsyncMock()
        mock_meshcore.commands.send_telemetry_req = AsyncMock()
        meshcore_worker.meshcore = mock_meshcore

        # Mock the rate limiting methods to execute immediately
        mock_queue_command = AsyncMock()
        meshcore_worker._queue_rate_limited_command = mock_queue_command
        
        # Create telemetry command message with password
        command_data = {"destination": "repeater_node", "password": "guest_password"}
        message = Message.create(
            message_type=MessageType.MQTT_COMMAND,
            source="mqtt",
            target="meshcore",
            payload={"command_type": "send_telemetry_req", **command_data},
        )

        # Process the command
        await meshcore_worker._handle_mqtt_command(message)

        # Verify the command was queued for rate-limited execution
        expected_data = {"command_type": "send_telemetry_req", **command_data}
        mock_queue_command.assert_called_once_with(
            "send_telemetry_req", expected_data
        )

    async def test_send_telemetry_req_without_password(
        self, meshcore_worker: MeshCoreWorker
    ) -> None:
        """Test send_telemetry_req command without password (direct request)."""
        # Setup mock MeshCore instance
        mock_meshcore = MagicMock()
        mock_meshcore.commands = MagicMock()
        mock_meshcore.commands.send_telemetry_req = AsyncMock()
        meshcore_worker.meshcore = mock_meshcore

        # Mock rate limiting methods to execute immediately
        mock_queue_command = AsyncMock()
        meshcore_worker._queue_rate_limited_command = mock_queue_command
        
        # Create telemetry command message without password
        command_data = {"destination": "node123"}
        message = Message.create(
            message_type=MessageType.MQTT_COMMAND,
            source="mqtt",
            target="meshcore",
            payload={"command_type": "send_telemetry_req", **command_data},
        )

        # Process the command
        await meshcore_worker._handle_mqtt_command(message)

        # Verify the command was queued for rate-limited execution
        expected_data = {"command_type": "send_telemetry_req", **command_data}
        mock_queue_command.assert_called_once_with(
            "send_telemetry_req", expected_data
        )

    async def test_execute_rate_limited_login_command(
        self, meshcore_worker: MeshCoreWorker
    ) -> None:
        """Test execution of rate-limited login command."""
        # Setup mock MeshCore instance
        mock_meshcore = MagicMock()
        mock_meshcore.commands = MagicMock()
        mock_meshcore.commands.send_login = AsyncMock(return_value="login_success")
        meshcore_worker.meshcore = mock_meshcore

        # Mock rate limiting to execute immediately
        meshcore_worker._rate_limited_send = AsyncMock(return_value="login_success")

        # Create message data for rate-limited execution
        message_data = {
            "command_type": "send_login",
            "destination": "repeater_node",
            "password": "guest_password",
            "future": AsyncMock(),
        }

        # Execute the rate-limited command
        await meshcore_worker._execute_rate_limited_message(message_data)

        # Verify the rate-limited send was called with correct parameters
        meshcore_worker._rate_limited_send.assert_called_once_with(
            "send_login(repeater_node)",
            mock_meshcore.commands.send_login,
            "repeater_node",
            "guest_password",
        )

    async def test_execute_rate_limited_logoff_command(
        self, meshcore_worker: MeshCoreWorker
    ) -> None:
        """Test execution of rate-limited logoff command."""
        # Setup mock MeshCore instance
        mock_meshcore = MagicMock()
        mock_meshcore.commands = MagicMock()
        mock_meshcore.commands.send_logoff = AsyncMock(return_value="logoff_success")
        meshcore_worker.meshcore = mock_meshcore

        # Mock rate limiting to execute immediately
        meshcore_worker._rate_limited_send = AsyncMock(return_value="logoff_success")

        # Create message data for rate-limited execution
        message_data = {
            "command_type": "send_logoff",
            "destination": "repeater_node",
            "future": AsyncMock(),
        }

        # Execute the rate-limited command
        await meshcore_worker._execute_rate_limited_message(message_data)

        # Verify the rate-limited send was called with correct parameters
        meshcore_worker._rate_limited_send.assert_called_once_with(
            "send_logoff(repeater_node)",
            mock_meshcore.commands.send_logoff,
            "repeater_node",
        )

    async def test_execute_rate_limited_telemetry_with_password(
        self, meshcore_worker: MeshCoreWorker
    ) -> None:
        """Test execution of rate-limited telemetry command with password."""
        # Setup mock MeshCore instance
        mock_meshcore = MagicMock()
        mock_meshcore.commands = MagicMock()
        mock_meshcore.commands.send_login = AsyncMock(return_value="login_success")
        mock_meshcore.commands.send_telemetry_req = AsyncMock(return_value="telemetry_data")
        meshcore_worker.meshcore = mock_meshcore

        # Mock rate limiting to execute immediately
        meshcore_worker._rate_limited_send = AsyncMock()
        meshcore_worker._rate_limited_send.side_effect = [
            "login_success",  # First call (login)
            "telemetry_data",  # Second call (telemetry)
        ]

        # Create message data for rate-limited execution
        message_data = {
            "command_type": "send_telemetry_req",
            "destination": "repeater_node",
            "password": "guest_password",
            "future": AsyncMock(),
        }

        # Execute the rate-limited command
        await meshcore_worker._execute_rate_limited_message(message_data)

        # Verify both login and telemetry were called
        assert meshcore_worker._rate_limited_send.call_count == 2
        
        # Check first call (login)
        first_call = meshcore_worker._rate_limited_send.call_args_list[0]
        assert first_call[0][0] == "send_login(repeater_node)"
        assert first_call[0][1] == mock_meshcore.commands.send_login
        assert first_call[0][2] == "repeater_node"
        assert first_call[0][3] == "guest_password"

        # Check second call (telemetry)
        second_call = meshcore_worker._rate_limited_send.call_args_list[1]
        assert second_call[0][0] == "send_telemetry_req(repeater_node)"
        assert second_call[0][1] == mock_meshcore.commands.send_telemetry_req
        assert second_call[0][2] == "repeater_node"

    async def test_execute_rate_limited_telemetry_without_password(
        self, meshcore_worker: MeshCoreWorker
    ) -> None:
        """Test execution of rate-limited telemetry command without password."""
        # Setup mock MeshCore instance
        mock_meshcore = MagicMock()
        mock_meshcore.commands = MagicMock()
        mock_meshcore.commands.send_telemetry_req = AsyncMock(return_value="telemetry_data")
        meshcore_worker.meshcore = mock_meshcore

        # Mock rate limiting to execute immediately
        meshcore_worker._rate_limited_send = AsyncMock(return_value="telemetry_data")

        # Create message data for rate-limited execution
        message_data = {
            "command_type": "send_telemetry_req",
            "destination": "node123",
            "future": AsyncMock(),
        }

        # Execute the rate-limited command
        await meshcore_worker._execute_rate_limited_message(message_data)

        # Verify only telemetry was called (no login)
        meshcore_worker._rate_limited_send.assert_called_once_with(
            "send_telemetry_req(node123)",
            mock_meshcore.commands.send_telemetry_req,
            "node123",
        )

    async def test_no_meshcore_instance_handling(
        self, meshcore_worker: MeshCoreWorker
    ) -> None:
        """Test command handling when MeshCore instance is None."""
        # Ensure meshcore is None
        meshcore_worker.meshcore = None

        # Create login command message
        command_data = {"destination": "repeater_node", "password": "guest_password"}
        message = Message.create(
            message_type=MessageType.MQTT_COMMAND,
            source="mqtt",
            target="meshcore",
            payload={"command_type": "send_login", **command_data},
        )

        # Process the command - should not raise exception
        await meshcore_worker._handle_mqtt_command(message)

    async def test_command_error_handling(
        self, meshcore_worker: MeshCoreWorker
    ) -> None:
        """Test error handling when authentication commands fail."""
        # Setup mock MeshCore instance that raises an exception
        mock_meshcore = MagicMock()
        mock_meshcore.commands = MagicMock()
        mock_meshcore.commands.send_login = AsyncMock(side_effect=Exception("Login failed"))
        meshcore_worker.meshcore = mock_meshcore

        # Mock the rate limiting to propagate the error
        async def mock_queue_command(command_type: str, command_data: dict) -> Any:
            raise Exception("Login failed")

        meshcore_worker._queue_rate_limited_command = mock_queue_command

        # Create login command message
        command_data = {"destination": "repeater_node", "password": "guest_password"}
        message = Message.create(
            message_type=MessageType.MQTT_COMMAND,
            source="mqtt",
            target="meshcore",
            payload={"command_type": "send_login", **command_data},
        )

        # Process the command - should not raise exception, just log error
        await meshcore_worker._handle_mqtt_command(message)

    async def test_invalid_parameter_types(
        self, meshcore_worker: MeshCoreWorker
    ) -> None:
        """Test validation of parameter types in rate-limited execution."""
        # Setup mock MeshCore instance
        mock_meshcore = MagicMock()
        mock_meshcore.commands = MagicMock()
        mock_meshcore.commands.send_login = AsyncMock()
        meshcore_worker.meshcore = mock_meshcore

        # Create message data with invalid parameter types
        message_data = {
            "command_type": "send_login",
            "destination": 123,  # Should be string, not int
            "password": "guest_password",
            "future": AsyncMock(),
        }

        # Execute rate-limited command - should handle error gracefully
        # The error should be caught and logged, not crash the worker
        await meshcore_worker._execute_rate_limited_message(message_data)

        # Verify login command was NOT called due to type validation
        mock_meshcore.commands.send_login.assert_not_called()
        
        # The main test is that the error is handled gracefully without crashing
        # The future handling may vary based on implementation details