# --- Build Stage ---
FROM python:3.14-alpine AS builder

WORKDIR /build

# Install build dependencies
RUN apk add --no-cache gcc musl-dev libffi-dev

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ src/

# Build wheel
RUN pip install --no-cache-dir build && \
    python -m build --wheel --outdir /build/dist


# --- Runtime Stage ---
FROM python:3.14-alpine

LABEL maintainer="loxone-mcp"
LABEL description="Loxone MCP Server - Bridge AI systems with Loxone home automation"

# Security: run as non-root user
RUN addgroup -g 1000 mcp && \
    adduser -u 1000 -G mcp -D mcp

WORKDIR /app

# Copy wheel from builder
COPY --from=builder /build/dist/*.whl /tmp/

# Install runtime dependencies only
RUN pip install --no-cache-dir /tmp/*.whl && \
    rm -rf /tmp/*.whl

# Create directories for logs and config
RUN mkdir -p /app/logs /app/config && \
    chown -R mcp:mcp /app

# Switch to non-root user
USER mcp

# Environment variables (can be overridden)
ENV LOXONE_HOST=""
ENV LOXONE_USERNAME=""
ENV LOXONE_PASSWORD=""
ENV LOXONE_PORT="80"
ENV MCP_TRANSPORT="http"
ENV MCP_HOST="0.0.0.0"
ENV MCP_PORT="8080"
ENV LOG_LEVEL="INFO"

# Expose HTTP port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost:8080/health || exit 1

# Run the MCP server
ENTRYPOINT ["python", "-m", "loxone_mcp"]
CMD ["--transport", "http"]
