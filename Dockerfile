# Multi-stage Dockerfile for MeshCore MQTT Bridge
# Stage 1: Build stage with development dependencies
FROM python:3.12-alpine AS builder

LABEL maintainer="MeshCore MQTT Bridge Team"
LABEL description="Build stage for MeshCore MQTT Bridge"

# Install build dependencies
RUN apk add --no-cache \
    gcc \
    musl-dev \
    linux-headers \
    libffi-dev \
    openssl-dev \
    cargo \
    rust

# Set working directory
WORKDIR /app

# Copy requirements files
COPY requirements.txt requirements-dev.txt ./

# Install Python dependencies in a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install production dependencies
RUN pip install --no-cache-dir --upgrade pip wheel setuptools && \
    pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY meshcore_mqtt/ ./meshcore_mqtt/
COPY pyproject.toml ./

# Install the package
RUN pip install --no-cache-dir .

# Stage 2: Runtime stage with minimal Alpine image
FROM python:3.12-alpine AS runtime

LABEL maintainer="MeshCore MQTT Bridge Team"
LABEL description="Production runtime for MeshCore MQTT Bridge"
LABEL version="1.0.0"

# Install runtime dependencies only
RUN apk add --no-cache \
    ca-certificates \
    tzdata \
    tini

# Create non-root user for security
RUN addgroup -g 1000 meshcore && \
    adduser -D -u 1000 -G meshcore -s /bin/sh meshcore

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app"

# Create directories for logs only
RUN mkdir -p /app/logs && \
    chown -R meshcore:meshcore /app

# Set working directory
WORKDIR /app

# Add user to dialout group for serial port access
RUN adduser meshcore dialout

# Switch to non-root user
USER meshcore

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import meshcore_mqtt; print('Health check passed')" || exit 1

# Default environment variables (can be overridden)
ENV LOG_LEVEL=INFO \
    MQTT_BROKER=localhost \
    MQTT_PORT=1883 \
    MQTT_TOPIC_PREFIX=meshcore \
    MESHCORE_CONNECTION=serial \
    MESHCORE_ADDRESS=/dev/ttyUSB0 \
    MESHCORE_BAUDRATE=115200

# Expose default MQTT port (informational)
EXPOSE 1883

# Use tini as init system for proper signal handling
ENTRYPOINT ["/sbin/tini", "--"]

# Default command - can be overridden
CMD ["python", "-m", "meshcore_mqtt.main", "--env"]
