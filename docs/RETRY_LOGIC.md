# Message Retry Logic

This document describes the retry logic implementation for message sending in the MeshCore MQTT bridge.

## Overview

The bridge now includes automatic retry logic for both direct messages (`send_msg`) and channel messages (`send_chan_msg`) to improve reliability, especially for multi-hop mesh network scenarios where messages may fail to reach their destination.

## Features

### Acknowledgement Tracking
- Monitors `MSG_SENT` events from MeshCore that include `expected_ack` and `suggested_timeout`
- Waits for acknowledgement (ACK) events with the specified timeout
- Tracks pending acknowledgements to determine message delivery success

### Retry Mechanism
- Automatically retries failed message sends up to a configurable number of times
- Uses exponential backoff between retries to avoid network congestion
- Provides detailed logging of retry attempts and outcomes

### Path Reset
- After exhausting regular retries, can reset the routing path and try once more
- Useful when the mesh network topology has changed or cached routes are stale
- Only applies to direct messages (not channel messages)

## Configuration

### Configuration Parameters

| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| `message_retry_count` | int | 3 | 0-10 | Number of retry attempts after initial send |
| `message_retry_delay` | float | 2.0 | 0.5-30.0 | Base delay in seconds between retries |
| `reset_path_on_failure` | bool | true | - | Reset routing path after max retries |

### Configuration Methods

#### 1. Configuration File (YAML)
```yaml
meshcore:
  connection_type: tcp
  address: 192.168.1.100
  port: 12345
  message_retry_count: 5
  message_retry_delay: 3.0
  reset_path_on_failure: true
```

#### 2. Environment Variables
```bash
export MESHCORE_MESSAGE_RETRY_COUNT=5
export MESHCORE_MESSAGE_RETRY_DELAY=3.0
export MESHCORE_RESET_PATH_ON_FAILURE=true
```

#### 3. Command Line Arguments
```bash
python -m meshcore_mqtt.main \
  --meshcore-message-retry-count 5 \
  --meshcore-message-retry-delay 3.0 \
  --meshcore-reset-path-on-failure
```

## How It Works

### Retry Flow

1. **Initial Send**: Message is sent using MeshCore's `send_msg()` or `send_chan_msg()`
2. **Check Response**: If response includes `expected_ack` and `suggested_timeout`:
   - Wait for acknowledgement with the suggested timeout
   - If ACK received → Success
   - If timeout → Continue to retry logic
3. **Retry Logic**:
   - Retry up to `message_retry_count` times
   - Wait `message_retry_delay * (2^attempt)` seconds between retries (exponential backoff)
   - Log each retry attempt
4. **Path Reset** (direct messages only):
   - After exhausting regular retries, if `reset_path_on_failure` is true
   - Reset the routing path (sends a trace packet to refresh routing)
   - Try sending once more with the new path
5. **Final Result**: Return success or failure after all attempts

### Exponential Backoff

The delay between retries increases exponentially to avoid overwhelming the network:
- 1st retry: `message_retry_delay` seconds (default 2s)
- 2nd retry: `message_retry_delay * 2` seconds (default 4s)
- 3rd retry: `message_retry_delay * 4` seconds (default 8s)
- And so on...

### Example Timeline

With default settings (3 retries, 2s base delay, path reset enabled):
1. 0s: Initial send attempt
2. 2s: First retry (if initial failed)
3. 6s: Second retry (2s + 4s delay)
4. 14s: Third retry (2s + 4s + 8s delay)
5. 15s: Path reset and final attempt (if enabled)

## Logging

The retry logic provides detailed logging at different levels:

- **INFO**: Retry attempts, successful acknowledgements
- **WARNING**: Missing acknowledgements, retry notifications
- **ERROR**: Final failure after all retries exhausted
- **DEBUG**: ACK tracking details, timeout information

Example log output:
```
INFO - Sending message to Alice (attempt 1/4)
WARNING - No acknowledgement received for message to Alice
INFO - Retrying in 2.0 seconds...
INFO - Sending message to Alice (attempt 2/4)
INFO - Message to Alice acknowledged successfully
```

## Use Cases

### Multi-Hop Networks
In mesh networks where messages must traverse multiple nodes, the retry logic significantly improves delivery reliability by:
- Handling temporary routing failures
- Adapting to topology changes
- Working around intermittent node availability

### Network Congestion
Exponential backoff helps prevent network congestion by:
- Spacing out retry attempts
- Giving the network time to recover
- Avoiding message storms

### Dynamic Topologies
Path reset functionality helps with:
- Stale routing tables
- Node mobility
- Network reconfiguration

## Limitations

- Retry logic only applies to `send_msg` and `send_chan_msg` commands
- ACK tracking depends on MeshCore library providing acknowledgement events
- Path reset may not be effective for all network issues
- Maximum total time for all retries depends on configuration but could exceed 30 seconds with aggressive settings

## Testing

The implementation includes comprehensive unit tests covering:
- Successful message delivery on first attempt
- Retry after initial failure
- Exponential backoff timing
- Path reset functionality
- ACK timeout handling
- Configuration validation

Run tests with:
```bash
pytest tests/test_retry_logic.py -v
```