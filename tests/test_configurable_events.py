"""Tests for configurable MeshCore events functionality."""

import json
import tempfile
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from meshcore_mqtt.config import Config, ConnectionType, MeshCoreConfig


class TestConfigurableEvents:
    """Test configurable MeshCore events feature."""

    def test_default_events(self) -> None:
        """Test that default events are properly configured."""
        config = MeshCoreConfig(
            connection_type=ConnectionType.TCP, address="127.0.0.1", port=12345
        )

        expected_events = [
            "CONTACT_MSG_RECV",
            "CHANNEL_MSG_RECV",
            "LOGIN_SUCCESS",
            "LOGIN_FAILED",
            "DEVICE_INFO",
            "BATTERY",
            "NEW_CONTACT",
            "ADVERTISEMENT",
            "TRACE_DATA",
        ]

        assert config.events == expected_events

    def test_custom_events_list(self) -> None:
        """Test custom events list configuration."""
        custom_events = ["CONNECTED", "DISCONNECTED", "BATTERY"]

        config = MeshCoreConfig(
            connection_type=ConnectionType.TCP,
            address="127.0.0.1",
            port=12345,
            events=custom_events,
        )

        assert config.events == custom_events

    def test_valid_event_types(self) -> None:
        """Test validation accepts valid event types."""
        valid_events = [
            "CONTACT_MSG_RECV",
            "CHANNEL_MSG_RECV",
            "LOGIN_SUCCESS",
            "LOGIN_FAILED",
            "MESSAGES_WAITING",
            "DEVICE_INFO",
            "BATTERY",
            "NEW_CONTACT",
            "NODE_LIST_CHANGED",
            "CONFIG_CHANGED",
            "TELEMETRY",
            "POSITION",
            "USER",
            "ROUTING",
            "ADMIN",
        ]

        config = MeshCoreConfig(
            connection_type=ConnectionType.TCP,
            address="127.0.0.1",
            port=12345,
            events=valid_events,
        )

        assert config.events == valid_events

    def test_invalid_event_types(self) -> None:
        """Test validation rejects invalid event types."""
        invalid_events = ["CONNECTED", "INVALID_EVENT", "ANOTHER_INVALID"]

        with pytest.raises(ValidationError, match="Invalid event types"):
            MeshCoreConfig(
                connection_type=ConnectionType.TCP,
                address="127.0.0.1",
                port=12345,
                events=invalid_events,
            )

    def test_empty_events_list(self) -> None:
        """Test empty events list is allowed."""
        config = MeshCoreConfig(
            connection_type=ConnectionType.TCP,
            address="127.0.0.1",
            port=12345,
            events=[],
        )

        assert config.events == []

    def test_parse_events_string(self) -> None:
        """Test parsing comma-separated event strings."""
        test_cases = [
            (
                "CONNECTED,DISCONNECTED,BATTERY",
                ["CONNECTED", "DISCONNECTED", "BATTERY"],
            ),
            (
                "connected, disconnected , battery ",
                ["CONNECTED", "DISCONNECTED", "BATTERY"],
            ),
            ("CONNECTED", ["CONNECTED"]),
            ("", []),
            ("  ", []),
        ]

        for input_str, expected in test_cases:
            result = Config.parse_events_string(input_str)
            assert result == expected

    def test_parse_events_string_with_empty_parts(self) -> None:
        """Test parsing handles empty parts correctly."""
        result = Config.parse_events_string("CONNECTED,,DISCONNECTED,")
        assert result == ["CONNECTED", "DISCONNECTED"]

    def test_events_from_json_config(self) -> None:
        """Test loading events from JSON configuration file."""
        config_data = {
            "mqtt": {
                "broker": "localhost",
                "port": 1883,
            },
            "meshcore": {
                "connection_type": "tcp",
                "address": "127.0.0.1",
                "port": 12345,
                "events": ["CONNECTED", "DISCONNECTED", "BATTERY"],
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            temp_path = Path(f.name)

        try:
            config = Config.from_file(temp_path)
            assert config.meshcore.events == ["CONNECTED", "DISCONNECTED", "BATTERY"]
        finally:
            temp_path.unlink()

    def test_events_from_yaml_config(self) -> None:
        """Test loading events from YAML configuration file."""
        config_data = {
            "mqtt": {
                "broker": "localhost",
                "port": 1883,
            },
            "meshcore": {
                "connection_type": "tcp",
                "address": "127.0.0.1",
                "port": 12345,
                "events": ["LOGIN_SUCCESS", "LOGIN_FAILED", "DEVICE_INFO"],
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = Path(f.name)

        try:
            config = Config.from_file(temp_path)
            assert config.meshcore.events == [
                "LOGIN_SUCCESS",
                "LOGIN_FAILED",
                "DEVICE_INFO",
            ]
        finally:
            temp_path.unlink()

    def test_events_from_environment_variable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test loading events from environment variable."""
        # Set up environment variables
        monkeypatch.setenv("MQTT_BROKER", "localhost")
        monkeypatch.setenv("MESHCORE_CONNECTION", "tcp")
        monkeypatch.setenv("MESHCORE_ADDRESS", "127.0.0.1")
        monkeypatch.setenv(
            "MESHCORE_EVENTS", "CONNECTED,BATTERY,NEW_CONTACT,ADVERTISEMENT"
        )

        config = Config.from_env()
        assert config.meshcore.events == [
            "CONNECTED",
            "BATTERY",
            "NEW_CONTACT",
            "ADVERTISEMENT",
        ]

    def test_events_environment_variable_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that default events are used when env var is not set."""
        # Set up required environment variables without MESHCORE_EVENTS
        monkeypatch.setenv("MQTT_BROKER", "localhost")
        monkeypatch.setenv("MESHCORE_CONNECTION", "tcp")
        monkeypatch.setenv("MESHCORE_ADDRESS", "127.0.0.1")

        config = Config.from_env()
        # Should use default events
        expected_events = [
            "CONTACT_MSG_RECV",
            "CHANNEL_MSG_RECV",
            "LOGIN_SUCCESS",
            "LOGIN_FAILED",
            "DEVICE_INFO",
            "BATTERY",
            "NEW_CONTACT",
            "ADVERTISEMENT",
            "TRACE_DATA",
        ]
        assert config.meshcore.events == expected_events

    def test_case_insensitive_event_parsing(self) -> None:
        """Test that event parsing is case insensitive."""
        result = Config.parse_events_string("connected,Disconnected,BATTERY")
        assert result == ["CONNECTED", "DISCONNECTED", "BATTERY"]

    def test_mixed_case_events_in_config(self) -> None:
        """Test that mixed case events in config are normalized."""
        config = MeshCoreConfig(
            connection_type=ConnectionType.TCP,
            address="127.0.0.1",
            port=12345,
            events=["connected", "Disconnected", "BATTERY"],  # Mixed case
        )

        # The validator should normalize these to uppercase
        assert all(event.isupper() for event in config.events)
        assert "CONNECTED" in config.events
        assert "DISCONNECTED" in config.events
        assert "BATTERY" in config.events
