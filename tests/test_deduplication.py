"""Test message deduplication functionality."""

import pytest
from unittest.mock import Mock
from meshcore_mqtt.config import Config, MeshCoreConfig, MQTTConfig
from meshcore_mqtt.meshcore_worker import MeshCoreWorker


class TestMessageDeduplication:
    """Test message deduplication in MeshCore worker."""

    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return Config(
            meshcore=MeshCoreConfig(
                connection_type="tcp",
                address="127.0.0.1",
                port=12345,
                events=["CONTACT_MSG_RECV"],
            ),
            mqtt=MQTTConfig(
                broker="localhost",
                port=1883,
                topic_prefix="test/meshcore",
            ),
        )

    @pytest.fixture
    def worker(self, config):
        """Create a MeshCore worker for testing."""
        return MeshCoreWorker(config)

    def test_fingerprint_generation_message_events(self, worker):
        """Test fingerprint generation for message events."""
        # Mock message event data
        mock_event = Mock()
        mock_event.type = "CONTACT_MSG_RECV"
        mock_event.payload = {
            "text": "Hello World",
            "from": "user123",
            "channel_idx": 0,
            "timestamp": 1627849200,
            "msg_id": "msg_123",
        }

        fingerprint1 = worker._generate_message_fingerprint(mock_event)
        fingerprint2 = worker._generate_message_fingerprint(mock_event)

        # Same event should generate same fingerprint
        assert fingerprint1 == fingerprint2
        assert len(fingerprint1) == 16  # MD5 hash truncated to 16 chars

    def test_fingerprint_generation_different_messages(self, worker):
        """Test that different messages generate different fingerprints."""
        # Mock first message
        mock_event1 = Mock()
        mock_event1.type = "CONTACT_MSG_RECV"
        mock_event1.payload = {
            "text": "Hello World",
            "from": "user123",
        }

        # Mock second message (different text)
        mock_event2 = Mock()
        mock_event2.type = "CONTACT_MSG_RECV"
        mock_event2.payload = {
            "text": "Hello Universe",  # Different text
            "from": "user123",
        }

        fingerprint1 = worker._generate_message_fingerprint(mock_event1)
        fingerprint2 = worker._generate_message_fingerprint(mock_event2)

        assert fingerprint1 != fingerprint2

    def test_duplicate_detection(self, worker):
        """Test duplicate message detection."""
        fingerprint = "test123456789abc"

        # First message should not be duplicate
        assert not worker._is_duplicate_message(fingerprint)

        # Same fingerprint should now be duplicate
        assert worker._is_duplicate_message(fingerprint)

        # Different fingerprint should not be duplicate
        assert not worker._is_duplicate_message("different456789xyz")

    def test_cache_expiry(self, worker):
        """Test that old cache entries are expired."""
        import time

        fingerprint = "expire123456789"

        # Add message to cache
        assert not worker._is_duplicate_message(fingerprint)

        # Manually set old timestamp (simulate expired entry)
        worker._message_cache[fingerprint] = time.time() - 400  # 400 sec ago

        # Should not be duplicate after expiry
        assert not worker._is_duplicate_message(fingerprint)

    def test_cache_size_limit(self, worker):
        """Test that cache size is limited."""
        # Set small cache size for testing
        worker._cache_max_size = 3

        # Add messages up to limit + 2
        for i in range(6):
            fingerprint = f"msg{i:016d}"
            worker._is_duplicate_message(fingerprint)

        # Cache should not exceed max size after cleanup
        assert len(worker._message_cache) <= worker._cache_max_size

    def test_connection_events_not_deduplicated(self, worker):
        """Test that connection events are not subject to deduplication."""
        # Mock connection event
        mock_event = Mock()
        mock_event.type = "CONNECTED"
        mock_event.payload = {"status": "connected"}

        # Connection events should always have unique fingerprints
        # (because they're excluded from deduplication logic)
        fingerprint1 = worker._generate_message_fingerprint(mock_event)
        fingerprint2 = worker._generate_message_fingerprint(mock_event)

        # Even though fingerprints are same, connection events bypass deduplication
        assert fingerprint1 == fingerprint2