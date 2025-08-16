#!/bin/bash

# Example script for running MeshCore MQTT Bridge with Docker
# Docker containers use environment variables for configuration (12-factor app)

echo "Building MeshCore MQTT Bridge Docker image..."
docker build -t meshcore-mqtt:latest .

echo "Running MeshCore MQTT Bridge with serial connection (default)..."

# Option 1: Serial connection (default) - most common for MeshCore devices
docker run -d \
  --name meshcore-mqtt-bridge \
  --restart unless-stopped \
  --device=/dev/ttyUSB0:/dev/ttyUSB0 \
  -e LOG_LEVEL=INFO \
  -e MQTT_BROKER=192.168.1.100 \
  -e MQTT_USERNAME=meshcore \
  -e MQTT_PASSWORD=meshcore123 \
  -e MESHCORE_CONNECTION=serial \
  -e MESHCORE_ADDRESS=/dev/ttyUSB0 \
  -e MESHCORE_BAUDRATE=115200 \
  -e MESHCORE_EVENTS=CONTACT_MSG_RECV,CHANNEL_MSG_RECV,CONNECTED,DISCONNECTED,DEVICE_INFO \
  meshcore-mqtt:latest

echo "Container started. Check logs with: docker logs -f meshcore-mqtt-bridge"

# Option 2: Using environment file (recommended for production)
# docker run -d \
#   --name meshcore-mqtt-bridge \
#   --restart unless-stopped \
#   --device=/dev/ttyUSB0:/dev/ttyUSB0 \
#   --env-file .env.docker \
#   meshcore-mqtt:latest

# Option 3: Using Docker Compose (recommended for multi-container setup)
# docker-compose up -d

# Option 4: TCP connection example (for network-connected MeshCore devices)
# docker run -d \
#   --name meshcore-mqtt-bridge \
#   --restart unless-stopped \
#   -e LOG_LEVEL=INFO \
#   -e MQTT_BROKER=192.168.1.100 \
#   -e MESHCORE_CONNECTION=tcp \
#   -e MESHCORE_ADDRESS=192.168.1.200 \
#   -e MESHCORE_PORT=4403 \
#   meshcore-mqtt:latest
