# MeshCore MQTT Bridge - OpenCode Context

## Instructions for OpenCode

- Run `pre-commit run --all-files` to ensure code quality and tests pass after making changes.
- Activate and use Python virtual environment located at `./venv` before any development or running commands.

## Project Overview

This project is a **MeshCore MQTT Bridge** - a robust Python application that bridges MeshCore mesh networking devices to MQTT brokers, enabling seamless integration with IoT platforms and message processing systems.

### Key Features
- **Inbox/Outbox Architecture**: Independent MeshCore and MQTT workers with message bus coordination
- **Multi-connection support**: TCP, Serial, and BLE connections to MeshCore devices
- **TLS/SSL Support**: Secure MQTT connections with configurable certificates
- **Flexible configuration**: JSON/YAML files, environment variables, CLI arguments
- **Configurable event system**: Subscribe to specific MeshCore event types
- **Robust MQTT integration**: Authentication, QoS, retention, auto-reconnection
- **Message rate limiting**: Configurable rate limiting to prevent network flooding and ensure reliable message delivery
- **Health monitoring**: Built-in health checks and automatic recovery for both workers
- **Async architecture**: Built with Python asyncio for high performance
- **Type safety**: Full type annotations with mypy support
- **Comprehensive testing**: 70+ tests with pytest and pytest-asyncio including rate limiting tests
- **Streamlined CI/CD**: Single pre-commit based CI workflow with automated quality checks

## Architecture

The bridge uses an **Inbox/Outbox Architecture** with independent workers coordinated by a message bus.

### Core Components

1. **Bridge Coordinator** (`meshcore_mqtt/bridge_coordinator.py`)
   - Coordinates independent MeshCore and MQTT workers
   - Manages shared message bus for inter-worker communication
   - Provides health monitoring and system statistics
   - Handles graceful startup and shutdown

2. **Message Bus System** (`meshcore_mqtt/message_queue.py`)
   - Async message queue system for worker communication
   - Thread-safe inbox/outbox pattern with asyncio.Queue
   - Component status tracking and health monitoring
   - Message types: MESHCORE_EVENT, MQTT_COMMAND, STATUS, HEALTH_CHECK, SHUTDOWN

3. **MeshCore Worker** (`meshcore_mqtt/meshcore_worker.py`)
   - Independent worker managing MeshCore device connection
   - Handles device commands forwarded from MQTT worker with rate limiting
   - Auto-reconnection with exponential backoff and health monitoring
   - Forwards MeshCore events to MQTT worker via message bus
   - Manages auto-fetch restart after NO_MORE_MSGS events
   - Configurable message rate limiting to prevent network flooding

4. **MQTT Worker** (`meshcore_mqtt/mqtt_worker.py`)
   - Independent worker managing MQTT broker connection
   - Subscribes to command topics and publishes events/status
   - TLS/SSL support with configurable certificates
   - Auto-reconnection with complete client recreation
   - Forwards MQTT commands to MeshCore worker via message bus

5. **Configuration System** (`meshcore_mqtt/config.py`)
   - Pydantic-based configuration with validation
   - Support for multiple input methods (file, env, CLI)
   - Event type validation and normalization
   - TLS/SSL configuration validation

6. **CLI Interface** (`meshcore_mqtt/main.py`)
   - Click-based command line interface
   - Logging configuration for third-party libraries
   - Configuration loading with precedence handling

### Event System

The bridge supports configurable event subscriptions:

**Default Events**:
- `CONTACT_MSG_RECV`, `CHANNEL_MSG_RECV` (messages)
- `DEVICE_INFO`, `BATTERY`, `NEW_CONTACT` (device info)
- `ADVERTISEMENT`, `TRACE_DATA` (network diagnostics)
- `TELEMETRY_RESPONSE`, `CHANNEL_INFO` (device details)

**Additional Events**:
- `CONNECTED`, `DISCONNECTED` (connection status, can be noisy)
- `LOGIN_SUCCESS`, `LOGIN_FAILED` (authentication)
- `MESSAGES_WAITING` (notifications)
- `CONTACTS`, `SELF_INFO` (contact and device information)

### Auto-Fetch Restart Feature

The bridge automatically handles `NO_MORE_MSGS` events from MeshCore by restarting the auto-fetch mechanism after a configurable delay:

- **Purpose**: Prevents message fetching from stopping when MeshCore reports no more messages
- **Configuration**: `auto_fetch_restart_delay` (1-60 seconds, default: 5)
- **Behavior**: When `NO_MORE_MSGS` is received, waits the configured delay then restarts auto-fetching
- **Environment Variable**: `MESHCORE_AUTO_FETCH_RESTART_DELAY=10`
- **CLI Argument**: `--meshcore-auto-fetch-restart-delay 10`

### Message Rate Limiting Feature

The bridge includes configurable message rate limiting to prevent network flooding and ensure reliable message delivery:

- **Purpose**: Prevents overwhelming the MeshCore device with rapid message sending commands
- **Initial Delay**: `message_initial_delay` (0.0-60.0 seconds, default: 15.0) - delay before sending the first message
- **Send Delay**: `message_send_delay` (0.0-60.0 seconds, default: 15.0) - delay between consecutive message sends
- **Behavior**: Messages are queued and sent with appropriate delays using an async rate-limiting system
- **Environment Variables**:
  - `MESHCORE_MESSAGE_INITIAL_DELAY=15.0`
  - `MESHCORE_MESSAGE_SEND_DELAY=15.0`
- **CLI Arguments**:
  - `--meshcore-message-initial-delay 15.0`
  - `--meshcore-message-send-delay 15.0`

### MQTT Topics

The bridge publishes to structured MQTT topics:
- `{prefix}/message/channel/{channel_idx}` - Channel messages (public channels)
- `{prefix}/message/direct/{pubkey_prefix}` - Direct messages (private messages)
- `{prefix}/status` - Connection status
- `{prefix}/advertisement` - Device advertisements
- `{prefix}/battery` - Battery updates
- `{prefix}/device_info` - Device information
- `{prefix}/new_contact` - Contact discovery
- `{prefix}/login` - Authentication status
- `{prefix}/command/{type}` - Commands (subscribed)

**Message Topic Structure:**
- For channel messages: `{prefix}/message/channel/{channel_idx}` where `channel_idx` is the numeric channel identifier
- For direct messages: `{prefix}/message/direct/{pubkey_prefix}` where `pubkey_prefix` is the sender's 6-byte public key prefix (hex encoded)
- This allows subscribers to:
  - Subscribe to all messages: `{prefix}/message/+/+`
  - Subscribe to all channel messages: `{prefix}/message/channel/+`
  - Subscribe to specific channel: `{prefix}/message/channel/0`
  - Subscribe to all direct messages: `{prefix}/message/direct/+`
  - Subscribe to messages from specific node: `{prefix}/message/direct/{specific_pubkey_prefix}`

### MQTT Command System

The bridge supports bidirectional communication via MQTT commands. Send commands to `{prefix}/command/{command_type}` with JSON payloads:

**Available Commands** (implemented in `meshcore_worker.py:_handle_mqtt_command`):

| Command | Description | Required Fields | MeshCore Method |
|---------|-------------|-----------------|------------------|
| `send_msg` | Send direct message | `destination`, `message` | `meshcore.commands.send_msg()` |
| `send_chan_msg` | Send channel message | `channel`, `message` | `meshcore.commands.send_chan_msg()` |
| `device_query` | Query device information | None | `meshcore.commands.send_device_query()` |
| `get_battery` | Get battery status | None | `meshcore.commands.get_bat()` |
| `set_name` | Set device name | `name` | `meshcore.commands.set_name()` |
| `send_advert` | Send device advertisement | None (optional: `flood`) | `meshcore.commands.send_advert()` |
| `send_trace` | Send trace packet for routing diagnostics | None (optional: `auth_code`, `tag`, `flags`, `path`) | `meshcore.commands.send_trace()` |
| `send_telemetry_req` | Request telemetry data from a node | `destination` | `meshcore.commands.send_telemetry_req()` |

**Command Examples**:
```json
// Send direct message
{"destination": "node_id_or_contact_name", "message": "Hello!"}

// Send channel message
{"channel": 0, "message": "Hello channel!"}

// Device query
{}

// Get battery
{}

// Set device name
{"name": "MyDevice"}

// Send advertisement
{}

// Send advertisement with flood
{"flood": true}

// Send trace packet (basic)
{}

// Send trace packet with parameters
{"auth_code": 12345, "tag": 67890, "flags": 1, "path": "23,5f,3a"}
```

**Command Examples**:
```bash
# Send direct message
mosquitto_pub -h localhost -t "meshcore/command/send_msg" \
  -m '{"destination": "Alice", "message": "Hello Alice!"}'

# Send channel message
mosquitto_pub -h localhost -t "meshcore/command/send_chan_msg" \
  -m '{"channel": 0, "message": "Hello everyone on channel 0!"}'

# Get device info
mosquitto_pub -h localhost -t "meshcore/command/device_query" -m '{}'

# Get battery status
mosquitto_pub -h localhost -t "meshcore/command/get_battery" -m '{}'

# Set device name
mosquitto_pub -h localhost -t "meshcore/command/set_name" \
  -m '{"name": "MyMeshDevice"}'

# Send device advertisement
mosquitto_pub -h localhost -t "meshcore/command/send_advert" -m '{}'

# Send device advertisement with flood
mosquitto_pub -h localhost -t "meshcore/command/send_advert" \
  -m '{"flood": true}'

# Send trace packet (basic)
mosquitto_pub -h localhost -t "meshcore/command/send_trace" -m '{}'

# Send trace packet with routing path
mosquitto_pub -h localhost -t "meshcore/command/send_trace" \
  -m '{"auth_code": 12345, "path": "23,5f,3a"}'

# Request telemetry data from a node
mosquitto_pub -h localhost -t "meshcore/command/send_telemetry_req" \
  -m '{"destination": "node123"}'
```

## Development Guidelines

### Code Quality Tools

The project uses these tools (configured in `pyproject.toml` and `.pre-commit-config.yaml`):
- **Black**: Code formatting (line length: 88)
- **Flake8**: Linting with custom rules
- **MyPy**: Type checking with strict settings
- **isort**: Import sorting and organization
- **Pytest**: Testing with asyncio support
- **Pre-commit**: Automated code quality checks and hooks
- **Streamlined CI**: Single pre-commit based CI workflow replacing multiple separate workflows

### Testing Strategy

**Test Structure**:
- `tests/test_config.py` - Configuration system (18 tests)
- `tests/test_bridge.py` - Bridge coordinator functionality (10 tests)
- `tests/test_configurable_events.py` - Event configuration (13 tests)
- `tests/test_json_serialization.py` - JSON handling (10 tests)
- `tests/test_logging.py` - Logging configuration (6 tests)
- `tests/test_rate_limiting.py` - Message rate limiting functionality (9 tests)

**Key Test Areas**:
- Configuration validation and loading
- Worker coordination and message bus functionality
- Event handler mapping and subscription
- JSON serialization edge cases
- MQTT topic generation and command handling
- Message rate limiting and queue management
- Health monitoring and recovery mechanisms
- Logging setup and third-party library control

### Architecture Benefits

**Inbox/Outbox Pattern**:
- **Resilience**: Workers operate independently, one can fail without affecting the other
- **Scalability**: Easy to add new workers or modify existing ones
- **Testability**: Each worker can be tested in isolation
- **Monitoring**: Built-in health checks and statistics for each component
- **Recovery**: Automatic reconnection and error recovery for both workers

**Message Bus Design**:
- **Thread-safe**: Uses asyncio.Queue for safe async operations
- **Typed messages**: Structured message types with validation
- **Component tracking**: Status monitoring for all registered components
- **Graceful shutdown**: Coordinated shutdown with cleanup

### Running Commands

**Development Setup**:
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
pre-commit install
```

**Testing**:
```bash
pytest                      # Run all tests
pytest -v                   # Verbose output
pytest --cov=meshcore_mqtt  # With coverage
pytest tests/test_config.py # Specific test file
```

**Code Quality**:
```bash
black meshcore_mqtt/ tests/     # Format code
flake8 meshcore_mqtt/ tests/    # Lint code
mypy meshcore_mqtt/ tests/      # Type check
pre-commit run --all-files      # Run all checks
```

**Running the Application**:
```bash
# With config file
python -m meshcore_mqtt.main --config-file config.yaml

# With CLI arguments
python -m meshcore_mqtt.main \
  --mqtt-broker localhost \
  --meshcore-connection tcp \
  --meshcore-address 192.168.1.100 \
  --meshcore-events "CONNECTED,BATTERY,ADVERTISEMENT"

# With environment variables
python -m meshcore_mqtt.main --env
```

## Recent Development History

### Major Features Implemented

1. **Message Rate Limiting (Latest)**
   - Configurable rate limiting for message sending commands
   - Initial delay and send delay configuration options
   - Async message queue with proper timing controls
   - Comprehensive test coverage for rate limiting functionality

2. **Streamlined CI/CD Pipeline**
   - Consolidated multiple CI workflows into single pre-commit based pipeline
   - Reduced from 3 separate workflows (ci.yml, test.yml, code-quality.yml) to 1
   - Improved maintainability and faster CI execution
   - Full integration with existing pre-commit configuration

3. **Inbox/Outbox Architecture**
   - Complete restructure to independent worker pattern
   - Message bus system for inter-worker communication
   - Enhanced health monitoring and recovery
   - Improved resilience and testability

4. **TLS/SSL Support**
   - Secure MQTT connections with configurable certificates
   - Support for custom CA, client certificates, and private keys
   - Optional certificate verification bypass for testing

6. **JSON Serialization**
   - Robust JSON serialization handling all Python data types
   - Fallback mechanisms for complex objects
   - Comprehensive error handling and validation

7. **Configurable Events**
   - Made MeshCore event types configurable
   - Support for config files, env vars, and CLI args
   - Case-insensitive event parsing with validation
   - Enhanced logging configuration for third-party libraries

### Code Patterns

**Worker Message Handling**:
```python
async def _handle_inbox_message(self, message: Message) -> None:
    """Handle messages from the inbox."""
    if message.message_type == MessageType.MQTT_COMMAND:
        await self._handle_mqtt_command(message)
    elif message.message_type == MessageType.MESHCORE_EVENT:
        await self._handle_meshcore_event(message)
```

**Event Forwarding Pattern**:
```python
def _on_meshcore_event(self, event_data: Any) -> None:
    """Forward MeshCore events to MQTT worker."""
    message = Message.create(
        message_type=MessageType.MESHCORE_EVENT,
        source=self.component_name,
        target="mqtt",
        payload={"event_data": event_data, "timestamp": time.time()}
    )
    asyncio.create_task(self.message_bus.send_message(message))
```

**Rate Limited Command Execution**:
```python
async def _queue_rate_limited_command(
    self, command_type: str, command_data: dict
) -> Any:
    """Queue a command for rate-limited execution."""
    future: asyncio.Future[Any] = asyncio.Future()
    message_data = {
        "command_type": command_type,
        "future": future,
        **command_data,
    }
    await self._message_queue.put(message_data)
    return await future
```

**Configuration Validation**:
```python
@field_validator("field_name")
@classmethod
def validate_field(cls, v: Type) -> Type:
    """Validate field with custom logic."""
    # Validation logic here
    return v
```

## Important Notes for OpenCode

### When Making Changes

1. **Always run tests** after changes: `pytest -v`
2. **Follow worker patterns** for new functionality
3. **Update message bus** if adding new message types
4. **Use type hints** for all new code
5. **Handle errors gracefully** with proper logging
6. **Test worker isolation** and message passing

### Configuration Precedence
1. Command-line arguments (highest)
2. Configuration file
3. Environment variables (lowest)

### Worker Development Guidelines
- **Message Handling**: Use inbox/outbox pattern for all inter-worker communication
- **Health Monitoring**: Implement health checks in `_perform_health_check()`
- **Recovery Logic**: Add automatic reconnection with exponential backoff
- **Status Updates**: Send status updates via message bus
- **Graceful Shutdown**: Handle shutdown messages and clean up resources

### Command Implementation
- Add new commands to `meshcore_worker.py:_handle_mqtt_command()`
- Validate required fields before calling MeshCore methods
- Handle command results and errors appropriately
- Update activity timestamp on successful operations

### Testing Requirements
- Test worker components in isolation
- Test message bus communication
- Test configuration validation
- Test error conditions and recovery scenarios
- Test health monitoring and status updates
- Maintain high test coverage

### Logging Best Practices
- Use structured logging with proper levels
- Configure third-party library logging appropriately
- Provide meaningful log messages for debugging
- Use `self.logger` instance for consistency
- Log worker status changes and health events

This project demonstrates modern Python development practices with async programming, inbox/outbox architecture, comprehensive testing, and robust error handling. The codebase is well-structured and maintainable, with clear separation of concerns, independent workers, and extensive documentation.

### Key Architectural Decisions

1. **Inbox/Outbox Pattern**: Ensures worker independence and resilience
2. **Message Bus**: Provides typed, thread-safe communication between components
3. **Health Monitoring**: Built-in health checks and automatic recovery
4. **TLS/SSL Support**: Secure MQTT connections for production deployments
5. **Async-First Design**: All I/O operations are asynchronous for maximum performance
6. **Type Safety**: Comprehensive type annotations with mypy validation
7. **Configuration Flexibility**: Multiple input methods with proper validation
