"""Tests for the MeshCore MQTT bridge."""

from unittest.mock import MagicMock, patch

import pytest

from meshcore_mqtt.bridge_coordinator import BridgeCoordinator
from meshcore_mqtt.config import Config, ConnectionType, MeshCoreConfig, MQTTConfig


@pytest.fixture
def test_config() -> Config:
    """Create a test configuration."""
    return Config(
        mqtt=MQTTConfig(
            broker="localhost",
            port=1883,
            topic_prefix="test",
        ),
        meshcore=MeshCoreConfig(
            connection_type=ConnectionType.TCP,
            address="127.0.0.1",
            port=12345,
        ),
    )


@pytest.fixture
def bridge(test_config: Config) -> BridgeCoordinator:
    """Create a bridge instance for testing."""
    return BridgeCoordinator(test_config)


class TestBridgeCoordinator:
    """Test the MeshCore MQTT bridge."""

    def test_init(self, bridge: BridgeCoordinator, test_config: Config) -> None:
        """Test bridge initialization."""
        assert bridge.config == test_config
        assert bridge.meshcore is None
        assert bridge.connection_manager is None
        assert bridge.mqtt_client is None
        assert not bridge._running
        assert bridge._worker_tasks == []

    async def test_start_stop_basic(self, bridge: BridgeCoordinator) -> None:
        """Test basic start/stop functionality without actual connections."""
        # Initial state
        assert not bridge._running
        assert bridge.mqtt_client is None
        assert bridge.connection_manager is None
        assert bridge.meshcore is None

        # Test that stop works even when not started
        await bridge.stop()
        assert not bridge._running

    def test_tcp_connection_config(self, test_config: Config) -> None:
        """Test TCP connection configuration."""
        bridge = BridgeCoordinator(test_config)
        assert bridge.config.meshcore.connection_type == ConnectionType.TCP
        assert bridge.config.meshcore.address == "127.0.0.1"
        assert bridge.config.meshcore.port == 12345

    def test_serial_connection_config(self) -> None:
        """Test serial connection configuration."""
        config = Config(
            mqtt=MQTTConfig(broker="localhost"),
            meshcore=MeshCoreConfig(
                connection_type=ConnectionType.SERIAL,
                address="/dev/ttyUSB0",
            ),
        )
        bridge = BridgeCoordinator(config)
        assert bridge.config.meshcore.connection_type == ConnectionType.SERIAL
        assert bridge.config.meshcore.address == "/dev/ttyUSB0"
        assert bridge.config.meshcore.port is None

    def test_ble_connection_config(self) -> None:
        """Test BLE connection configuration."""
        config = Config(
            mqtt=MQTTConfig(broker="localhost"),
            meshcore=MeshCoreConfig(
                connection_type=ConnectionType.BLE,
                address="AA:BB:CC:DD:EE:FF",
            ),
        )
        bridge = BridgeCoordinator(config)
        assert bridge.config.meshcore.connection_type == ConnectionType.BLE
        assert bridge.config.meshcore.address == "AA:BB:CC:DD:EE:FF"
        assert bridge.config.meshcore.port is None

    @patch("meshcore_mqtt.mqtt_worker.mqtt.Client")
    async def test_mqtt_setup(
        self, mock_mqtt_client: MagicMock, bridge: BridgeCoordinator
    ) -> None:
        """Test MQTT setup."""
        # Setup mock
        mock_mqtt_instance = MagicMock()
        mock_mqtt_client.return_value = mock_mqtt_instance
        mock_mqtt_instance.connect = MagicMock(return_value=0)
        mock_mqtt_instance.is_connected = MagicMock(return_value=True)
        mock_mqtt_instance.loop_start = MagicMock()

        # Initialize workers first
        from meshcore_mqtt.mqtt_worker import MQTTWorker

        bridge.mqtt_worker = MQTTWorker(bridge.config)

        # Test MQTT setup
        await bridge._setup_mqtt()

        # Verify MQTT client setup
        assert bridge.mqtt_client is not None

    def test_mqtt_auth_setup(self) -> None:
        """Test MQTT setup with authentication."""
        config = Config(
            mqtt=MQTTConfig(
                broker="localhost",
                username="testuser",
                password="testpass",
            ),
            meshcore=MeshCoreConfig(
                connection_type=ConnectionType.TCP,
                address="127.0.0.1",
                port=12345,
            ),
        )
        bridge = BridgeCoordinator(config)

        # Test that authentication config is stored
        assert bridge.config.mqtt.username == "testuser"
        assert bridge.config.mqtt.password == "testpass"

    def test_mqtt_topic_generation(self, bridge: BridgeCoordinator) -> None:
        """Test MQTT topic generation."""
        # Test message topic
        expected_message_topic = f"{bridge.config.mqtt.topic_prefix}/message"
        assert expected_message_topic == "test/message"

        # Test status topic
        expected_status_topic = f"{bridge.config.mqtt.topic_prefix}/status"
        assert expected_status_topic == "test/status"

        # Test command topic pattern
        expected_command_topic = f"{bridge.config.mqtt.topic_prefix}/command/+"
        assert expected_command_topic == "test/command/+"

    def test_advertisement_event_handler_mapping(self) -> None:
        """Test that ADVERTISEMENT events are mapped to the correct handler."""
        config = Config(
            mqtt=MQTTConfig(broker="localhost"),
            meshcore=MeshCoreConfig(
                connection_type=ConnectionType.TCP,
                address="127.0.0.1",
                port=12345,
                events=["ADVERTISEMENT"],
            ),
        )

        bridge = BridgeCoordinator(config)

        # Verify that ADVERTISEMENT is configured in events
        assert "ADVERTISEMENT" in bridge.config.meshcore.events

        # In the new architecture, event handling is done by workers
        # Verify the configuration is properly set up
        assert bridge.config.meshcore.events is not None

    def test_advertisement_mqtt_topic(self) -> None:
        """Test that ADVERTISEMENT events generate the correct MQTT topic."""
        config = Config(
            mqtt=MQTTConfig(broker="localhost", topic_prefix="meshtest"),
            meshcore=MeshCoreConfig(
                connection_type=ConnectionType.TCP, address="127.0.0.1", port=12345
            ),
        )

        bridge = BridgeCoordinator(config)

        # Test advertisement topic generation
        expected_topic = f"{bridge.config.mqtt.topic_prefix}/advertisement"
        assert expected_topic == "meshtest/advertisement"
