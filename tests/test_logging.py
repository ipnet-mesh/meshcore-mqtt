"""Tests for logging configuration."""

import logging

from meshcore_mqtt.config import Config, ConnectionType, MeshCoreConfig, MQTTConfig
from meshcore_mqtt.main import setup_logging


class TestLoggingConfiguration:
    """Test logging setup and configuration."""

    def test_setup_logging_info_level(self) -> None:
        """Test logging setup with INFO level."""
        setup_logging("INFO")

        # Check root logger level
        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO

        # Check that third-party loggers are configured
        assert logging.getLogger("meshcore").level == logging.INFO
        assert logging.getLogger("paho").level == logging.INFO

        # Check that urllib3 is set to WARNING to reduce noise
        assert logging.getLogger("urllib3").level == logging.WARNING

    def test_setup_logging_debug_level(self) -> None:
        """Test logging setup with DEBUG level."""
        setup_logging("DEBUG")

        # Check root logger level
        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG

        # Check that third-party loggers are configured
        assert logging.getLogger("meshcore").level == logging.DEBUG
        assert logging.getLogger("paho").level == logging.DEBUG

        # In DEBUG mode, urllib3 should not be suppressed
        assert logging.getLogger("urllib3").level == logging.DEBUG

    def test_setup_logging_warning_level(self) -> None:
        """Test logging setup with WARNING level."""
        setup_logging("WARNING")

        # Check root logger level
        root_logger = logging.getLogger()
        assert root_logger.level == logging.WARNING

        # Check that third-party loggers are configured
        assert logging.getLogger("meshcore").level == logging.WARNING
        assert logging.getLogger("paho").level == logging.WARNING

    def test_bridge_respects_debug_setting(self) -> None:
        """Test that bridge respects debug setting based on log level."""
        from meshcore_mqtt.bridge_coordinator import BridgeCoordinator

        # Test with DEBUG level
        debug_config = Config(
            mqtt=MQTTConfig(broker="localhost"),
            meshcore=MeshCoreConfig(
                connection_type=ConnectionType.TCP, address="127.0.0.1", port=12345
            ),
            log_level="DEBUG",
        )

        debug_bridge = BridgeCoordinator(debug_config)
        # The bridge should be initialized without errors
        assert debug_bridge.config.log_level == "DEBUG"

        # Test with INFO level
        info_config = Config(
            mqtt=MQTTConfig(broker="localhost"),
            meshcore=MeshCoreConfig(
                connection_type=ConnectionType.TCP, address="127.0.0.1", port=12345
            ),
            log_level="INFO",
        )

        info_bridge = BridgeCoordinator(info_config)
        assert info_bridge.config.log_level == "INFO"

    def test_third_party_loggers_configured(self) -> None:
        """Test that all expected third-party loggers are configured."""
        setup_logging("INFO")

        expected_loggers = [
            "meshcore",
            "paho",
            "paho.mqtt",
            "paho.mqtt.client",
            "asyncio",
        ]

        for logger_name in expected_loggers:
            logger = logging.getLogger(logger_name)
            assert (
                logger.level == logging.INFO
            ), f"Logger {logger_name} not configured correctly"

    def test_logging_force_override(self) -> None:
        """Test that logging configuration overrides existing settings."""
        # Set up initial logging
        logging.basicConfig(level=logging.ERROR)

        # Our setup should override this
        setup_logging("DEBUG")

        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG
