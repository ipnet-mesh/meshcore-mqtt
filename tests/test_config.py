"""Tests for configuration system."""

import json
import tempfile
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from meshcore_mqtt.config import Config, ConnectionType, MeshCoreConfig, MQTTConfig


class TestMQTTConfig:
    """Test MQTT configuration."""

    def test_valid_config(self) -> None:
        """Test valid MQTT configuration."""
        config = MQTTConfig(broker="localhost")
        assert config.broker == "localhost"
        assert config.port == 1883
        assert config.username is None
        assert config.password is None
        assert config.topic_prefix == "meshcore"
        assert config.qos == 0
        assert config.retain is False

    def test_invalid_port(self) -> None:
        """Test invalid port numbers."""
        with pytest.raises(ValidationError):
            MQTTConfig(broker="localhost", port=0)

        with pytest.raises(ValidationError):
            MQTTConfig(broker="localhost", port=65536)

    def test_invalid_qos(self) -> None:
        """Test invalid QoS values."""
        with pytest.raises(ValidationError):
            MQTTConfig(broker="localhost", qos=-1)

        with pytest.raises(ValidationError):
            MQTTConfig(broker="localhost", qos=3)

    def test_tls_config_default(self) -> None:
        """Test default TLS configuration."""
        config = MQTTConfig(broker="localhost")
        assert config.tls_enabled is False
        assert config.tls_ca_cert is None
        assert config.tls_client_cert is None
        assert config.tls_client_key is None
        assert config.tls_insecure is False

    def test_tls_enabled(self) -> None:
        """Test TLS enabled configuration."""
        config = MQTTConfig(broker="localhost", tls_enabled=True)
        assert config.tls_enabled is True

    def test_tls_with_certificates(self) -> None:
        """Test TLS configuration with certificates."""
        # Create temporary certificate files for testing
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".pem", delete=False
        ) as ca_cert:
            ca_cert.write("dummy ca cert")
            ca_cert_path = ca_cert.name

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".pem", delete=False
        ) as client_cert:
            client_cert.write("dummy client cert")
            client_cert_path = client_cert.name

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".key", delete=False
        ) as client_key:
            client_key.write("dummy client key")
            client_key_path = client_key.name

        try:
            config = MQTTConfig(
                broker="localhost",
                tls_enabled=True,
                tls_ca_cert=ca_cert_path,
                tls_client_cert=client_cert_path,
                tls_client_key=client_key_path,
            )
            assert config.tls_enabled is True
            assert config.tls_ca_cert == ca_cert_path
            assert config.tls_client_cert == client_cert_path
            assert config.tls_client_key == client_key_path
        finally:
            # Clean up temporary files
            Path(ca_cert_path).unlink()
            Path(client_cert_path).unlink()
            Path(client_key_path).unlink()

    def test_tls_invalid_certificate_path(self) -> None:
        """Test TLS configuration with invalid certificate paths."""
        with pytest.raises(ValidationError):
            MQTTConfig(
                broker="localhost",
                tls_enabled=True,
                tls_ca_cert="/nonexistent/path/ca.pem",
            )


class TestMeshCoreConfig:
    """Test MeshCore configuration."""

    def test_valid_tcp_config(self) -> None:
        """Test valid TCP configuration."""
        config = MeshCoreConfig(
            connection_type=ConnectionType.TCP, address="192.168.1.100", port=5000
        )
        assert config.connection_type == ConnectionType.TCP
        assert config.address == "192.168.1.100"
        assert config.port == 5000
        assert config.timeout == 5

    def test_valid_serial_config(self) -> None:
        """Test valid serial configuration."""
        config = MeshCoreConfig(
            connection_type=ConnectionType.SERIAL, address="/dev/ttyUSB0"
        )
        assert config.connection_type == ConnectionType.SERIAL
        assert config.address == "/dev/ttyUSB0"
        assert config.port is None
        assert config.baudrate == 115200

    def test_valid_ble_config(self) -> None:
        """Test valid BLE configuration."""
        config = MeshCoreConfig(
            connection_type=ConnectionType.BLE, address="AA:BB:CC:DD:EE:FF"
        )
        assert config.connection_type == ConnectionType.BLE
        assert config.address == "AA:BB:CC:DD:EE:FF"
        assert config.port is None
        assert config.baudrate == 115200

    def test_tcp_sets_default_port(self) -> None:
        """Test that TCP connections get a default port."""
        config = MeshCoreConfig(
            connection_type=ConnectionType.TCP, address="192.168.1.100", port=None
        )
        assert config.port == 5000

    def test_custom_baudrate(self) -> None:
        """Test custom baudrate for serial connections."""
        config = MeshCoreConfig(
            connection_type=ConnectionType.SERIAL,
            address="/dev/ttyUSB0",
            baudrate=9600,
        )
        assert config.baudrate == 9600

    def test_invalid_port(self) -> None:
        """Test invalid port numbers."""
        with pytest.raises(ValidationError):
            MeshCoreConfig(
                connection_type=ConnectionType.TCP, address="192.168.1.100", port=0
            )

        with pytest.raises(ValidationError):
            MeshCoreConfig(
                connection_type=ConnectionType.TCP, address="192.168.1.100", port=65536
            )

    def test_invalid_timeout(self) -> None:
        """Test invalid timeout values."""
        with pytest.raises(ValidationError):
            MeshCoreConfig(
                connection_type=ConnectionType.SERIAL, address="/dev/ttyUSB0", timeout=0
            )


class TestConfig:
    """Test main configuration."""

    def test_valid_config(self) -> None:
        """Test valid complete configuration."""
        config = Config(
            mqtt=MQTTConfig(broker="localhost"),
            meshcore=MeshCoreConfig(
                connection_type=ConnectionType.TCP, address="192.168.1.100", port=12345
            ),
        )
        assert config.mqtt.broker == "localhost"
        assert config.meshcore.connection_type == ConnectionType.TCP
        assert config.log_level == "INFO"

    def test_invalid_log_level(self) -> None:
        """Test invalid log level."""
        with pytest.raises(ValidationError, match="log_level must be one of"):
            Config(
                mqtt=MQTTConfig(broker="localhost"),
                meshcore=MeshCoreConfig(
                    connection_type=ConnectionType.TCP,
                    address="192.168.1.100",
                    port=12345,
                ),
                log_level="INVALID",
            )

    def test_log_level_case_normalization(self) -> None:
        """Test that log levels are normalized to uppercase."""
        config = Config(
            mqtt=MQTTConfig(broker="localhost"),
            meshcore=MeshCoreConfig(
                connection_type=ConnectionType.TCP, address="192.168.1.100", port=12345
            ),
            log_level="debug",
        )
        assert config.log_level == "DEBUG"

    def test_from_json_file(self) -> None:
        """Test loading configuration from JSON file."""
        config_data = {
            "mqtt": {
                "broker": "test-broker",
                "port": 1883,
                "topic_prefix": "test",
                "qos": 1,
                "retain": True,
            },
            "meshcore": {
                "connection_type": "serial",
                "address": "/dev/ttyUSB0",
                "timeout": 10,
            },
            "log_level": "DEBUG",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            temp_path = Path(f.name)

        try:
            config = Config.from_file(temp_path)
            assert config.mqtt.broker == "test-broker"
            assert config.mqtt.port == 1883
            assert config.mqtt.topic_prefix == "test"
            assert config.mqtt.qos == 1
            assert config.mqtt.retain is True
            assert config.meshcore.connection_type == ConnectionType.SERIAL
            assert config.meshcore.address == "/dev/ttyUSB0"
            assert config.meshcore.timeout == 10
            assert config.log_level == "DEBUG"
        finally:
            temp_path.unlink()

    def test_from_yaml_file(self) -> None:
        """Test loading configuration from YAML file."""
        config_data = {
            "mqtt": {
                "broker": "yaml-broker",
                "port": 8883,
            },
            "meshcore": {
                "connection_type": "ble",
                "address": "AA:BB:CC:DD:EE:FF",
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = Path(f.name)

        try:
            config = Config.from_file(temp_path)
            assert config.mqtt.broker == "yaml-broker"
            assert config.mqtt.port == 8883
            assert config.meshcore.connection_type == ConnectionType.BLE
            assert config.meshcore.address == "AA:BB:CC:DD:EE:FF"
        finally:
            temp_path.unlink()

    def test_from_nonexistent_file(self) -> None:
        """Test loading from non-existent file."""
        with pytest.raises(FileNotFoundError):
            Config.from_file("/nonexistent/config.json")

    def test_from_invalid_json(self) -> None:
        """Test loading from invalid JSON file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("invalid json {")
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="Invalid JSON configuration"):
                Config.from_file(temp_path)
        finally:
            temp_path.unlink()

    def test_from_invalid_yaml(self) -> None:
        """Test loading from invalid YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content: [")
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="Invalid YAML configuration"):
                Config.from_file(temp_path)
        finally:
            temp_path.unlink()


class TestConnectionType:
    """Test connection type enum."""

    def test_valid_values(self) -> None:
        """Test valid connection type values."""
        assert ConnectionType.SERIAL.value == "serial"
        assert ConnectionType.BLE.value == "ble"
        assert ConnectionType.TCP.value == "tcp"

    def test_from_string(self) -> None:
        """Test creating connection type from string."""
        assert ConnectionType("serial") == ConnectionType.SERIAL
        assert ConnectionType("ble") == ConnectionType.BLE
        assert ConnectionType("tcp") == ConnectionType.TCP
