"""Tests for JSON serialization functionality."""

import json

import pytest

from meshcore_mqtt.config import Config, ConnectionType, MeshCoreConfig, MQTTConfig
from meshcore_mqtt.meshcore_worker import MeshCoreWorker


class TestJSONSerialization:
    """Test JSON serialization helper."""

    @pytest.fixture
    def worker(self) -> MeshCoreWorker:
        """Create a MeshCore worker instance for testing."""
        config = Config(
            mqtt=MQTTConfig(broker="localhost"),
            meshcore=MeshCoreConfig(
                connection_type=ConnectionType.TCP, address="127.0.0.1", port=12345
            ),
        )
        return MeshCoreWorker(config)

    def test_serialize_dict(self, worker: MeshCoreWorker) -> None:
        """Test serialization of dictionary data."""
        data = {"message": "hello", "id": 123, "active": True}
        result = worker.serialize_to_json(data)

        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed == data

    def test_serialize_list(self, worker: MeshCoreWorker) -> None:
        """Test serialization of list data."""
        data = [1, 2, "three", {"nested": True}]
        result = worker.serialize_to_json(data)

        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed == data

    def test_serialize_primitive_types(self, worker: MeshCoreWorker) -> None:
        """Test serialization of primitive types."""
        test_cases = [
            "string",
            123,
            45.67,
            True,
            False,
            None,
        ]

        for data in test_cases:
            result = worker.serialize_to_json(data)
            parsed = json.loads(result)
            assert parsed == data

    def test_serialize_object_with_attributes(self, worker: MeshCoreWorker) -> None:
        """Test serialization of objects with attributes."""

        class TestObject:
            def __init__(self) -> None:
                self.public_attr = "visible"
                self.number = 42
                self._private_attr = "hidden"

        obj = TestObject()
        result = worker.serialize_to_json(obj)

        # Should be valid JSON
        parsed = json.loads(result)
        assert "public_attr" in parsed
        assert "number" in parsed
        assert "_private_attr" not in parsed  # Private attributes excluded
        assert parsed["public_attr"] == "visible"
        assert parsed["number"] == 42

    def test_serialize_complex_object_fallback(self, worker: MeshCoreWorker) -> None:
        """Test serialization fallback for complex objects."""

        class ComplexObject:
            def __str__(self) -> str:
                return "complex_representation"

        obj = ComplexObject()
        result = worker.serialize_to_json(obj)

        # Should be valid JSON with metadata structure
        parsed = json.loads(result)
        assert "type" in parsed
        assert "value" in parsed
        assert "timestamp" in parsed
        assert parsed["type"] == "ComplexObject"
        assert parsed["value"] == "complex_representation"

    def test_serialize_iterable_object(self, worker: MeshCoreWorker) -> None:
        """Test serialization of iterable objects."""
        data = range(3)  # Creates an iterable but not list/dict
        result = worker.serialize_to_json(data)

        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed == [0, 1, 2]

    def test_serialize_exception_handling(self, worker: MeshCoreWorker) -> None:
        """Test serialization with objects that cause exceptions."""

        class ProblematicObject:
            def __init__(self) -> None:
                self.circular_ref = self

            def __str__(self) -> str:
                return "problematic"

        obj = ProblematicObject()
        result = worker.serialize_to_json(obj)

        # Should still produce valid JSON - circular refs are handled by default=str
        parsed = json.loads(result)

        # Result should always be valid JSON
        assert isinstance(parsed, dict)

        # Should contain the circular reference as a string representation
        assert "circular_ref" in parsed
        assert isinstance(parsed["circular_ref"], str)

    def test_serialize_long_string_truncation(self, worker: MeshCoreWorker) -> None:
        """Test that very long strings are properly handled."""

        class LongStringObject:
            def __str__(self) -> str:
                return "x" * 2000  # Very long string

        obj = LongStringObject()
        result = worker.serialize_to_json(obj)

        # Should be valid JSON
        parsed = json.loads(result)

        # If it falls back to error handling, raw_value should be truncated
        if "raw_value" in parsed:
            assert len(parsed["raw_value"]) <= 1000

    def test_serialize_unicode_handling(self, worker: MeshCoreWorker) -> None:
        """Test serialization handles Unicode correctly."""
        data = {"message": "Hello 世界", "emoji": "🚀"}
        result = worker.serialize_to_json(data)

        # Should be valid JSON with Unicode preserved
        parsed = json.loads(result)
        assert parsed["message"] == "Hello 世界"
        assert parsed["emoji"] == "🚀"

    def test_all_results_are_valid_json(self, worker: MeshCoreWorker) -> None:
        """Test that all serialization results are valid JSON."""
        test_data = [
            {"normal": "dict"},
            [1, 2, 3],
            "simple string",
            42,
            True,
            None,
            range(5),
            set([1, 2, 3]),  # Non-JSON-serializable by default
            complex(1, 2),  # Non-JSON-serializable type
        ]

        for data in test_data:
            result = worker.serialize_to_json(data)

            # Every result should be valid JSON
            try:
                parsed = json.loads(result)
                assert isinstance(
                    parsed, (dict, list, str, int, float, bool, type(None))
                )
            except json.JSONDecodeError:
                pytest.fail(f"Invalid JSON produced for {type(data)}: {result}")
