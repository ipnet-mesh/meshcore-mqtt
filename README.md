# MeshCore MQTT Bridge

[![License](https://img.shields.io/badge/License-GPL_v3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![CI](https://github.com/ipnet-mesh/meshcore-mqtt/actions/workflows/ci.yml/badge.svg)](https://github.com/ipnet-mesh/meshcore-mqtt/actions/workflows/ci.yml)
[![Docker Build and Push](https://github.com/ipnet-mesh/meshcore-mqtt/actions/workflows/docker-build.yml/badge.svg)](https://github.com/ipnet-mesh/meshcore-mqtt/actions/workflows/docker-build.yml)
[![Code style: black](https://img.shields.io/badge/Code%20style-black-000000.svg)](https://github.com/psf/black)
[![Typing: mypy](https://img.shields.io/badge/Typing-mypy-blue.svg)](https://mypy.readthedocs.io/)

A robust bridge service that connects MeshCore devices to MQTT brokers, enabling seamless integration with IoT platforms and message processing systems.

## Features

- **Inbox/Outbox Architecture**: Independent MeshCore and MQTT workers with message bus coordination
- **Multiple Connection Types**: Support for TCP, Serial, and BLE connections to MeshCore devices
- **Full Command Support**: Send messages, query device information, and network operations via MQTT
- **TLS/SSL Support**: Secure MQTT connections with configurable certificates
- **Flexible Configuration**: JSON, YAML, environment variables, and command-line configuration options
- **MQTT Integration**: Full MQTT client with authentication, QoS, retention, and auto-reconnection
- **Configurable Event Monitoring**: Subscribe to specific MeshCore event types for optimal performance
- **Message Rate Limiting**: Configurable rate limiting to prevent network flooding and ensure reliable message delivery
- **Health Monitoring**: Built-in health checks and automatic recovery for both workers
- **Async Architecture**: Built with Python asyncio for high performance and concurrent operations
- **Type Safety**: Full type annotations with mypy support
- **Comprehensive Testing**: 70+ unit tests with pytest and pytest-asyncio including rate limiting tests
- **Code Quality**: Streamlined CI/CD with pre-commit hooks for black formatting, flake8 linting, mypy type checking, and automated testing

## Installation

### From Source

```bash
git clone <repository-url>
cd meshcore-mqtt
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Development Installation

```bash
pip install -r requirements-dev.txt
pre-commit install
```

## Configuration

The bridge supports multiple configuration methods with the following precedence:
1. Command-line arguments (highest priority)
2. Configuration file (JSON or YAML)
3. Environment variables (lowest priority)

### Configuration Options

#### MQTT Settings
- `mqtt_broker`: MQTT broker address (required)
- `mqtt_port`: MQTT broker port (default: 1883)
- `mqtt_username`: MQTT authentication username (optional)
- `mqtt_password`: MQTT authentication password (optional)
- `mqtt_topic_prefix`: MQTT topic prefix (default: "meshcore")
- `mqtt_qos`: Quality of Service level 0-2 (default: 0)
- `mqtt_retain`: Message retention flag (default: false)

#### MeshCore Settings
- `meshcore_connection`: Connection type (serial, ble, tcp)
- `meshcore_address`: Device address (required)
- `meshcore_port`: Device port for TCP connections (default: 12345)
- `meshcore_baudrate`: Baudrate for serial connections (default: 115200)
- `meshcore_timeout`: Operation timeout in seconds (default: 5)
- `meshcore_auto_fetch_restart_delay`: Delay in seconds before restarting auto-fetch after NO_MORE_MSGS (default: 5, range: 1-60)
- `meshcore_message_initial_delay`: Initial delay in seconds before sending the first message (default: 15.0, range: 0.0-60.0)
- `meshcore_message_send_delay`: Delay in seconds between consecutive message sends (default: 15.0, range: 0.0-60.0)
- `meshcore_events`: List of MeshCore event types to subscribe to (see [Event Types](#event-types))

#### General Settings
- `log_level`: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

### Configuration Examples

#### JSON Configuration (config.json)
```json
{
  "mqtt": {
    "broker": "mqtt.example.com",
    "port": 1883,
    "username": "myuser",
    "password": "mypass",
    "topic_prefix": "meshcore",
    "qos": 1,
    "retain": false
  },
  "meshcore": {
    "connection_type": "tcp",
    "address": "192.168.1.100",
    "port": 12345,
    "baudrate": 115200,
    "timeout": 10,
    "auto_fetch_restart_delay": 10,
    "message_initial_delay": 15.0,
    "message_send_delay": 15.0,
    "events": [
      "CONTACT_MSG_RECV",
      "CHANNEL_MSG_RECV",
      "CONNECTED",
      "DISCONNECTED",
      "BATTERY",
      "DEVICE_INFO"
    ]
  },
  "log_level": "INFO"
}
```

#### YAML Configuration (config.yaml)
```yaml
mqtt:
  broker: mqtt.example.com
  port: 1883
  username: myuser
  password: mypass
  topic_prefix: meshcore
  qos: 1
  retain: false

meshcore:
  connection_type: tcp
  address: "192.168.1.100"
  port: 12345
  baudrate: 115200
  timeout: 10
  auto_fetch_restart_delay: 10
  message_initial_delay: 15.0
  message_send_delay: 15.0
  events:
    - CONTACT_MSG_RECV
    - CHANNEL_MSG_RECV
    - CONNECTED
    - DISCONNECTED
    - BATTERY
    - DEVICE_INFO

log_level: INFO
```

#### Environment Variables
```bash
export MQTT_BROKER=mqtt.example.com
export MQTT_PORT=1883
export MQTT_USERNAME=myuser
export MQTT_PASSWORD=mypass
export MESHCORE_CONNECTION=tcp
export MESHCORE_ADDRESS=192.168.1.100
export MESHCORE_PORT=12345
export MESHCORE_BAUDRATE=115200
export MESHCORE_AUTO_FETCH_RESTART_DELAY=10
export MESHCORE_MESSAGE_INITIAL_DELAY=15.0
export MESHCORE_MESSAGE_SEND_DELAY=15.0
export MESHCORE_EVENTS="CONNECTED,DISCONNECTED,BATTERY,DEVICE_INFO"
export LOG_LEVEL=INFO
```

## Usage

### Command Line Interface

#### Using Configuration File
```bash
python -m meshcore_mqtt.main --config-file config.json
```

#### Using Command Line Arguments
```bash
python -m meshcore_mqtt.main \
  --mqtt-broker mqtt.example.com \
  --mqtt-username myuser \
  --mqtt-password mypass \
  --meshcore-connection tcp \
  --meshcore-address 192.168.1.100 \
  --meshcore-port 12345 \
  --meshcore-auto-fetch-restart-delay 10 \
  --meshcore-events "CONNECTED,DISCONNECTED,BATTERY"
```

#### Using Environment Variables
```bash
python -m meshcore_mqtt.main --env
```

### Connection Types

#### TCP Connection
```bash
python -m meshcore_mqtt.main \
  --mqtt-broker localhost \
  --meshcore-connection tcp \
  --meshcore-address 192.168.1.100 \
  --meshcore-port 12345
```

#### Serial Connection
```bash
python -m meshcore_mqtt.main \
  --mqtt-broker localhost \
  --meshcore-connection serial \
  --meshcore-address /dev/ttyUSB0 \
  --meshcore-baudrate 9600
```

#### BLE Connection
```bash
python -m meshcore_mqtt.main \
  --mqtt-broker localhost \
  --meshcore-connection ble \
  --meshcore-address AA:BB:CC:DD:EE:FF
```

## Event Types

The bridge can subscribe to various MeshCore event types. You can configure which events to monitor using the `events` configuration option.

### Default Events
If no events are specified, the bridge subscribes to these default events:
- `CONTACT_MSG_RECV` - Contact messages received
- `CHANNEL_MSG_RECV` - Channel messages received
- `DEVICE_INFO` - Device information updates
- `BATTERY` - Battery status updates
- `NEW_CONTACT` - New contact discovered
- `ADVERTISEMENT` - Device advertisement broadcasts
- `TRACE_DATA` - Network trace information
- `TELEMETRY_RESPONSE` - Telemetry data responses
- `CHANNEL_INFO` - Channel configuration details

### Additional Supported Events
You can also subscribe to these additional event types:
- `CONNECTED` - Device connection events (can be noisy)
- `DISCONNECTED` - Device disconnection events (can be noisy)
- `LOGIN_SUCCESS` - Successful authentication
- `LOGIN_FAILED` - Failed authentication
- `MESSAGES_WAITING` - Pending messages notification
- `CONTACTS` - Contact list updates
- `SELF_INFO` - Own device information

### Configuration Examples

#### Minimal Events (Performance Optimized)
```yaml
meshcore:
  events:
    - CONNECTED
    - DISCONNECTED
    - BATTERY
```

#### Message-Focused Events
```yaml
meshcore:
  events:
    - CONTACT_MSG_RECV
    - CHANNEL_MSG_RECV
    - TEXT_MESSAGE_RX
```

#### Full Monitoring
```yaml
meshcore:
  events:
    - CONTACT_MSG_RECV
    - CHANNEL_MSG_RECV
    - CONNECTED
    - DISCONNECTED
    - BATTERY
    - DEVICE_INFO
    - ADVERTISEMENT
```

**Note**: Event names are case-insensitive. You can use `connected`, `CONNECTED`, or `Connected` - they will all be normalized to uppercase.

## MQTT Topics

The bridge provides full bidirectional communication between MQTT and MeshCore devices. Using the configured topic prefix (default: "meshcore"):

### Published Topics (MeshCore → MQTT)
The bridge publishes to these topics based on configured MeshCore events:

- `{prefix}/message/channel/{channel_idx}` - Channel messages from CHANNEL_MSG_RECV events
- `{prefix}/message/direct/{pubkey_prefix}` - Direct messages from CONTACT_MSG_RECV events
- `{prefix}/status` - Connection status from CONNECTED/DISCONNECTED events

**Message Topic Subscription Patterns:**
- Subscribe to all messages: `{prefix}/message/+/+`
- Subscribe to all channel messages: `{prefix}/message/channel/+`
- Subscribe to specific channel: `{prefix}/message/channel/0`
- Subscribe to all direct messages: `{prefix}/message/direct/+`
- Subscribe to messages from specific node: `{prefix}/message/direct/{specific_pubkey_prefix}`

**Trace Topic Subscription Patterns:**
- Subscribe to all trace responses: `{prefix}/traceroute/+`
- Subscribe to specific trace tag: `{prefix}/traceroute/12345`

Where:
- `{channel_idx}` is the numeric channel identifier (e.g., 0, 1, 2)
- `{pubkey_prefix}` is the sender's 6-byte public key prefix (hex encoded, e.g., `a1b2c3d4e5f6`)
- `{tag}` is the trace identifier (32-bit integer, e.g., 12345)

**Other Published Topics:**
- `{prefix}/login` - Authentication status from LOGIN_SUCCESS/LOGIN_FAILED events
- `{prefix}/device_info` - Device information from DEVICE_INFO events
- `{prefix}/battery` - Battery status from BATTERY events
- `{prefix}/new_contact` - Contact discovery from NEW_CONTACT events
- `{prefix}/advertisement` - Device advertisements from ADVERTISEMENT events
- `{prefix}/telemetry` - Telemetry data from TELEMETRY_RESPONSE events
- `{prefix}/contacts` - Contact list updates from CONTACTS events
- `{prefix}/self_info` - Own device information from SELF_INFO events
- `{prefix}/channel_info` - Channel configuration from CHANNEL_INFO events

### Command Topics (MQTT → MeshCore)
Send commands to MeshCore devices via MQTT using `{prefix}/command/{command_type}` with JSON payloads:

#### Message Commands
- `{prefix}/command/send_msg` - Send direct message to contact/node
  ```json
  {"destination": "contact_name_or_node_id", "message": "Hello!"}
  ```

- `{prefix}/command/send_chan_msg` - Send channel message
  ```json
  {"channel": 0, "message": "Hello channel!"}
  ```

#### Device Management Commands
- `{prefix}/command/device_query` - Query device information
  ```json
  {}
  ```
- `{prefix}/command/get_battery` - Get battery status
  ```json
  {}
  ```
- `{prefix}/command/set_name` - Set device name
  ```json
  {"name": "MyDevice"}
  ```

#### Network Commands
- `{prefix}/command/ping` - Ping a specific node
  ```json
  {"destination": "node_id"}
  ```
- `{prefix}/command/send_trace` - Send trace packet for routing diagnostics
  ```json
  // Basic trace
  {}

  // Trace with specific routing path through repeaters
  {"auth_code": 12345, "path": "23,5f,3a", "flags": 1}
  ```

### MQTT Command Examples

Using `mosquitto_pub` client:

```bash
# Send direct message
mosquitto_pub -h localhost -t "meshcore/command/send_msg" \
  -m '{"destination": "Alice", "message": "Hello Alice!"}'

# Send channel message
mosquitto_pub -h localhost -t "meshcore/command/send_chan_msg" \
  -m '{"channel": 0, "message": "Hello everyone on channel 0!"}'

# Get device information
mosquitto_pub -h localhost -t "meshcore/command/device_query" -m '{}'

# Set device name
mosquitto_pub -h localhost -t "meshcore/command/set_name" \
  -m '{"name": "MyMeshDevice"}'

# Send device advertisement
mosquitto_pub -h localhost -t "meshcore/command/send_advert" -m '{}'

# Send device advertisement with flood
mosquitto_pub -h localhost -t "meshcore/command/send_advert" \
  -m '{"flood": true}'

# Send trace packet (basic routing diagnostics)
mosquitto_pub -h localhost -t "meshcore/command/send_trace" -m '{}'

# Request telemetry data from a node
mosquitto_pub -h localhost -t "meshcore/command/send_telemetry_req" \
  -m '{"destination": "node123"}'

# Send trace packet with routing path through specific repeaters
mosquitto_pub -h localhost -t "meshcore/command/send_trace" \
  -m '{"auth_code": 12345, "path": "23,5f,3a"}'

# Send trace with specific tag for tracking responses
mosquitto_pub -h localhost -t "meshcore/command/send_trace" \
  -m '{"tag": 67890, "path": "a0,b1,c2"}'

# Subscribe to all trace responses
mosquitto_sub -h localhost -t "meshcore/traceroute/+"

# Subscribe to specific trace tag responses
mosquitto_sub -h localhost -t "meshcore/traceroute/67890"
```

### Available MeshCore Commands

The bridge supports these MeshCore commands via MQTT:

| Command | Description | Required Fields | Example |
|---------|-------------|-----------------|----------|
| `send_msg` | Send direct message | `destination`, `message` | `{"destination": "Alice", "message": "Hello!"}` |
| `send_chan_msg` | Send channel message | `channel`, `message` | `{"channel": 0, "message": "Hello channel!"}` |
| `device_query` | Query device information | None | `{}` |
| `get_battery` | Get battery status | None | `{}` |
| `set_name` | Set device name | `name` | `{"name": "MyDevice"}` |
| `send_advert` | Send device advertisement | None (optional: `flood`) | `{}` or `{"flood": true}` |
| `send_trace` | Send trace packet for routing diagnostics | None (optional: `auth_code`, `tag`, `flags`, `path`) | `{}` or `{"auth_code": 12345, "path": "23,5f,3a"}` |
| `send_telemetry_req` | Request telemetry data from a node | `destination` | `{"destination": "node123"}` |

### Topic Examples
- `meshcore/message/channel/0` - Channel 0 messages
- `meshcore/message/direct/a1b2c3` - Direct messages from node a1b2c3
- `meshcore/status` - Bridge connection status ("connected"/"disconnected")
- `meshcore/events/connection` - Raw MeshCore connection events (JSON)
- `meshcore/battery` - Battery level updates
- `meshcore/device_info` - Device specifications and capabilities
- `meshcore/advertisement` - Device advertisement broadcasts
- `meshcore/traceroute/{tag}` - Network trace responses (tag-specific)
- `meshcore/command/send_msg` - Send message command (subscribed)
- `meshcore/command/ping` - Ping command (subscribed)
- `meshcore/command/send_trace` - Send trace packet command (subscribed)

## Docker Deployment

The MeshCore MQTT Bridge provides multi-stage Docker support with Alpine Linux for minimal image size and enhanced security. Following 12-factor app principles, the Docker container is configured entirely through environment variables.

### Docker Features

- **Multi-stage build**: Optimized Alpine-based images with minimal attack surface
- **Non-root user**: Runs as dedicated `meshcore` user for security
- **Environment variables**: Full configuration via environment variables (12-factor app)
- **Health checks**: Built-in container health monitoring
- **Signal handling**: Proper init system with tini for clean shutdowns
- **Container logging**: Logs output to stdout/stderr for Docker log drivers

### Quick Start with Docker

#### Using Pre-built Images from GHCR

Pre-built Docker images are available from GitHub Container Registry:

**Available Tags:**
- `latest` - Latest stable release from main branch
- `develop` - Latest development build
- `v1.0.0` - Specific version tags
- `v1.0` - Major.minor version tags
- `v1` - Major version tags

```bash
# Pull the latest image
docker pull ghcr.io/ipnet-mesh/meshcore-mqtt:latest

# Run with serial connection (default for MeshCore devices)
docker run -d \
  --name meshcore-mqtt-bridge \
  --restart unless-stopped \
  --device=/dev/ttyUSB0:/dev/ttyUSB0 \
  -e MQTT_BROKER=192.168.1.100 \
  -e MQTT_USERNAME=meshcore \
  -e MQTT_PASSWORD=meshcore123 \
  -e MESHCORE_CONNECTION=serial \
  -e MESHCORE_ADDRESS=/dev/ttyUSB0 \
  ghcr.io/ipnet-mesh/meshcore-mqtt:latest
```

#### Building Locally

```bash
# Build the image locally
docker build -t meshcore-mqtt:latest .

# Run with local image
docker run -d \
  --name meshcore-mqtt-bridge \
  --restart unless-stopped \
  --device=/dev/ttyUSB0:/dev/ttyUSB0 \
  -e MQTT_BROKER=192.168.1.100 \
  -e MQTT_USERNAME=meshcore \
  -e MQTT_PASSWORD=meshcore123 \
  -e MESHCORE_CONNECTION=serial \
  -e MESHCORE_ADDRESS=/dev/ttyUSB0 \
  meshcore-mqtt:latest
```

#### Using Environment File

```bash
# Create environment file from example
cp .env.docker.example .env.docker
# Edit .env.docker with your configuration

# Run with environment file (includes device mount for serial)
docker run -d \
  --name meshcore-mqtt-bridge \
  --restart unless-stopped \
  --device=/dev/ttyUSB0:/dev/ttyUSB0 \
  --env-file .env.docker \
  ghcr.io/ipnet-mesh/meshcore-mqtt:latest
```

#### Option 3: Using Docker Compose
```bash
# Start the entire stack with MQTT broker
docker-compose up -d

# View logs
docker-compose logs -f meshcore-mqtt

# Stop the stack
docker-compose down
```


### Docker Environment Variables

All configuration options can be set via environment variables:

```bash
# Logging Configuration
LOG_LEVEL=INFO

# MQTT Broker Configuration
MQTT_BROKER=localhost
MQTT_PORT=1883
MQTT_USERNAME=user
MQTT_PASSWORD=pass
MQTT_TOPIC_PREFIX=meshcore
MQTT_QOS=1
MQTT_RETAIN=true

# MQTT TLS/SSL Configuration (optional)
MQTT_TLS_ENABLED=false
MQTT_TLS_CA_CERT=/path/to/ca.crt
MQTT_TLS_CLIENT_CERT=/path/to/client.crt
MQTT_TLS_CLIENT_KEY=/path/to/client.key
MQTT_TLS_INSECURE=false

# MeshCore Device Configuration (serial default)
MESHCORE_CONNECTION=serial
MESHCORE_ADDRESS=/dev/ttyUSB0    # Serial port, IP address, or BLE MAC address
MESHCORE_BAUDRATE=115200         # For serial connections
MESHCORE_PORT=4403              # Only for TCP connections
MESHCORE_TIMEOUT=30
MESHCORE_AUTO_FETCH_RESTART_DELAY=10  # Restart delay after NO_MORE_MSGS (1-60 seconds)
MESHCORE_MESSAGE_INITIAL_DELAY=15.0    # Initial delay before first message (0.0-60.0 seconds)
MESHCORE_MESSAGE_SEND_DELAY=15.0      # Delay between consecutive messages (0.0-60.0 seconds)

# Event Configuration (comma-separated)
MESHCORE_EVENTS=CONNECTED,DISCONNECTED,BATTERY,DEVICE_INFO
```

#### Connection Type Examples

**Serial Connection (Default):**
```bash
MESHCORE_CONNECTION=serial
MESHCORE_ADDRESS=/dev/ttyUSB0
MESHCORE_BAUDRATE=115200
# Note: Use --device=/dev/ttyUSB0 in docker run for device access
```

**TCP Connection:**
```bash
MESHCORE_CONNECTION=tcp
MESHCORE_ADDRESS=192.168.1.100
MESHCORE_PORT=4403
```

**BLE Connection:**
```bash
MESHCORE_CONNECTION=ble
MESHCORE_ADDRESS=AA:BB:CC:DD:EE:FF
```


### Health Monitoring

The container includes health checks:

```bash
# Check container health
docker inspect --format='{{.State.Health.Status}}' meshcore-mqtt-bridge

# View health check logs
docker inspect --format='{{range .State.Health.Log}}{{.Output}}{{end}}' meshcore-mqtt-bridge
```

### Container Management

```bash
# View container logs
docker logs -f meshcore-mqtt-bridge

# Execute commands in container
docker exec -it meshcore-mqtt-bridge sh

# Stop container
docker stop meshcore-mqtt-bridge

# Remove container
docker rm meshcore-mqtt-bridge
```

## Development

### Running Tests
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=meshcore_mqtt

# Run specific test file
pytest tests/test_config.py -v
```

### Code Quality
```bash
# Format code
black meshcore_mqtt/ tests/

# Lint code
flake8 meshcore_mqtt/ tests/

# Type checking
mypy meshcore_mqtt/ tests/

# Run pre-commit hooks
pre-commit run --all-files
```

## Architecture

The bridge uses an **Inbox/Outbox Architecture** with independent workers:

### Core Components

1. **Bridge Coordinator** (`bridge_coordinator.py`)
   - Coordinates independent MeshCore and MQTT workers
   - Manages shared message bus for inter-worker communication
   - Provides health monitoring and system statistics
   - Handles graceful startup and shutdown

2. **Message Bus System** (`message_queue.py`)
   - Async message queue system for worker communication
   - Thread-safe inbox/outbox pattern
   - Component status tracking and health monitoring
   - Message types: events, commands, status updates

3. **MeshCore Worker** (`meshcore_worker.py`)
   - Independent worker managing MeshCore device connection
   - Handles device commands and event subscriptions
   - Auto-reconnection and health monitoring
   - Forwards events to MQTT worker via message bus

4. **MQTT Worker** (`mqtt_worker.py`)
   - Independent worker managing MQTT broker connection
   - Subscribes to command topics and publishes events
   - TLS/SSL support with configurable certificates
   - Auto-reconnection and connection recovery

5. **Configuration System** (`config.py`)
   - Pydantic-based configuration with validation
   - Support for JSON, YAML, environment variables, and CLI args
   - Type-safe configuration with proper defaults

6. **CLI Interface** (`main.py`)
   - Click-based command line interface
   - Configuration loading and validation
   - Logging setup and error handling

### Benefits of Inbox/Outbox Architecture

- **Resilience**: Workers operate independently, one can fail without affecting the other
- **Scalability**: Easy to add new workers or modify existing ones
- **Testability**: Each worker can be tested in isolation
- **Monitoring**: Built-in health checks and statistics for each component
- **Recovery**: Automatic reconnection and error recovery for both workers

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Support

For issues and questions, please open an issue on the GitHub repository.
