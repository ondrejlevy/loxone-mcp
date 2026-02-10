# Research: Loxone MCP Server

**Date**: 2026-02-10  
**Phase**: Phase 0 - Research  
**Status**: Complete

This document captures all technical research and decisions made to resolve unknowns from the Technical Context.

## 1. MCP SDK Selection

### Decision
Use **official `mcp` Python SDK** from Model Context Protocol project.

### Rationale
- Official SDK maintained by MCP specification authors
- Native support for both stdio and HTTP+SSE transports
- Built-in lifecycle management (initialize, shutdown, error handling)
- Resource and Tool registration APIs
- Notification mechanism for real-time updates
- Type hints and async/await support

### Implementation Notes
- Install via pip: `mcp>=1.0.0`
- Server creation: `mcp.server.Server(name="loxone-mcp")`
- Resource registration: `@server.list_resources()` decorator
- Tool registration: `@server.call_tool()` decorator
- Notification sending: `server.request_context.session.send_resource_updated(uri)`
- Lifecycle hooks: Server initialization in `__main__.py`, cleanup on shutdown

### Alternatives Considered
- Building custom MCP implementation: Too complex, violates simplicity principle
- Using generic JSON-RPC library: Lacks MCP-specific features (Resources, Tools, notifications)

### References
- MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk
- MCP Specification (2025-06-18): https://spec.modelcontextprotocol.io/

---

## 2. Loxone WebSocket Protocol

### Decision
Use **websockets** library for WebSocket client with custom Loxone protocol parser.

### Rationale
- Loxone uses proprietary WebSocket command protocol (not just JSON-RPC)
- websockets library is standard Python async WebSocket client
- Requires custom message framing for Loxone binary state updates
- Need to handle Loxone-specific commands (getkey, gettoken, enablebinstatusupdate)

### Loxone WebSocket Command Structure

**Text Commands** (JSON):
```json
{
  "LL": {
    "control": "jdev/sys/getkey",
    "code": 200,
    "value": "-----BEGIN CERTIFICATE-----..."
  }
}
```

**Binary State Updates**:
- Header: 8 bytes (identifier, length, flags)
- Payload: Variable length (UUIDs + state values)
- Format: `0x03` (text command) or `0x00`-`0x02` (state updates)

### Integration Pattern

```python
import websockets
import json

async def connect_loxone(host, token):
    uri = f"wss://{host}/ws/rfc6455"
    async with websockets.connect(uri) as websocket:
        # Authenticate with token
        await websocket.send(f"jdev/sys/authwithtoken/{token}/edfc5f9a-df3f-4cad-9dff-c1e4dc2abf55")
        
        # Enable binary state updates
        await websocket.send("jdev/sps/enablebinstatusupdate")
        
        # Listen for updates
        async for message in websocket:
            if isinstance(message, bytes):
                # Parse binary state update
                handle_state_update(message)
            else:
                # Parse JSON response
                handle_command_response(json.loads(message))
```

### Reconnection Strategy
- Exponential backoff: 1s, 2s, 4s, 8s, 16s, 32s, max 60s
- Reset backoff on successful connection lasting >5 minutes
- Circuit breaker: After 10 consecutive failures, require manual intervention
- Log all reconnection attempts with context

### Implementation Notes
- WebSocket connection in `loxone/websocket.py`
- Binary parser for state updates (header + UUID mapping)
- Command queue for outgoing commands
- State update callback to State Manager
- Health check: ping/pong every 30 seconds

### Alternatives Considered
- HTTP polling: Too slow for real-time updates, violates <1s notification requirement
- MQTT bridge: Not supported by Loxone miniserver natively

### References
- Loxone WebSocket API: https://www.loxone.com/enen/kb/api/
- websockets library: https://websockets.readthedocs.io/

---

## 3. Cryptography Implementation

### Decision
Use **cryptography** library for RSA-2048 and AES-256-CBC implementation with three-tier fallback.

### Rationale
- cryptography is industry-standard Python crypto library
- Supports RSA public key encryption (PKCS#1 v1.5)
- Supports AES-256-CBC with PKCS7 padding
- HMAC-SHA1 for hash-based fallback
- Well-tested, maintained by PyCA

### Three-Tier Authentication Strategy

#### Tier 1: Token-Based via WebSocket (Primary)

1. **Get Public Key**:
   ```python
   response = await websocket.send("jdev/sys/getkey")
   public_key_pem = response["LL"]["value"]
   ```

2. **Encrypt Credentials**:
   ```python
   from cryptography.hazmat.primitives import serialization, hashes
   from cryptography.hazmat.primitives.asymmetric import padding
   
   public_key = serialization.load_pem_public_key(public_key_pem.encode())
   credentials = f"{username}:{password}".encode()
   encrypted = public_key.encrypt(credentials, padding.PKCS1v15())
   encrypted_hex = encrypted.hex()
   ```

3. **Get Token**:
   ```python
   token_response = await websocket.send(f"jdev/sys/gettoken/{encrypted_hex}/{username}")
   token = token_response["LL"]["value"]["token"]  # JWT
   session_key = token_response["LL"]["value"]["key"]  # AES key (hex)
   ```

4. **Authenticate**:
   ```python
   await websocket.send(f"jdev/sys/authwithtoken/{token}/{session_id}")
   ```

#### Tier 2: Token-Based via HTTP (Fallback)

Same flow as Tier 1 but via HTTP endpoints:
- `GET http://{host}/jdev/sys/getkey`
- `GET http://{host}/jdev/sys/gettoken/{hash}/{user}`
- WebSocket authentication with obtained token

#### Tier 3: Hash-Based via HTTP (Legacy 8.x)

1. **Get Salt**:
   ```python
   response = requests.get(f"http://{host}/jdev/sys/getsalt/{username}")
   salt = response.json()["LL"]["value"]
   ```

2. **Compute Hash**:
   ```python
   import hmac
   import hashlib
   
   # Hash = HMAC-SHA1(password, salt) then hex
   hash_value = hmac.new(password.encode(), salt.encode(), hashlib.sha1).hexdigest()
   ```

3. **Authenticate**:
   ```python
   response = requests.get(f"http://{host}/jdev/sys/authenticate/{hash_value}")
   ```

### Fallback Logic

```python
async def authenticate_loxone(config):
    try:
        # Try Tier 1: Token via WebSocket
        return await auth_token_websocket(config)
    except Exception as e:
        logger.warning(f"Tier 1 failed: {e}, trying Tier 2")
        
        try:
            # Try Tier 2: Token via HTTP
            return await auth_token_http(config)
        except Exception as e:
            logger.warning(f"Tier 2 failed: {e}, trying Tier 3")
            
            # Try Tier 3: Hash-based (legacy)
            return await auth_hash_http(config)
```

### Implementation Notes
- Authentication module: `loxone/auth.py`
- Store token in memory (never log it)
- Re-authenticate on token expiry (typically 24 hours)
- Test all three tiers in integration tests with mocked responses

### Security Considerations
- Never log passwords or tokens (redact in structured logs)
- Use TLS for all communication (verify certificates)
- Store credentials in environment variables, not config files
- Implement token rotation

### Alternatives Considered
- OAuth2: Not supported by Loxone
- Basic Auth: Supported but less secure than token-based

### References
- Loxone Authentication: https://www.loxone.com/enen/kb/api/authentication/
- cryptography library: https://cryptography.io/

---

## 4. Container Optimization

### Decision
Use **multi-stage Dockerfile** with python:3.14-alpine base, targeting <200MB image.

### Rationale
- Alpine Linux: Minimal base image (~5MB vs ~150MB for Debian)
- Multi-stage build: Separates build dependencies from runtime
- python:3.14-alpine: Official Python image with security updates
- Non-root user: Security best practice

### Multi-Stage Build Pattern

```dockerfile
# Stage 1: Builder - Install dependencies with build tools
FROM python:3.14-alpine AS builder

WORKDIR /build

# Install build dependencies (gcc, musl-dev for compiling C extensions)
RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    openssl-dev \
    cargo \
    rust

# Install Python dependencies to /install prefix
COPY requirements.txt .
RUN pip install --prefix=/install --no-warn-script-location --no-cache-dir -r requirements.txt

# Stage 2: Runtime - Minimal image with only runtime dependencies
FROM python:3.14-alpine

# Install runtime dependencies only
RUN apk add --no-cache \
    libffi \
    openssl \
    ca-certificates

# Create non-root user
RUN adduser -D -u 1000 -h /app loxone

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY --chown=loxone:loxone src/ /app/src/
COPY --chown=loxone:loxone config/example-config.yaml /app/config.yaml

# Switch to non-root user
USER loxone

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8080/metrics')" || exit 1

# Expose HTTP transport port
EXPOSE 8080

# Entry point
ENTRYPOINT ["python", "-m", "loxone_mcp"]
```

### Size Optimization Techniques

1. **Remove build dependencies from final image**: gcc, musl-dev, cargo only in builder
2. **Use --no-cache-dir**: Don't cache pip downloads
3. **Single RUN command**: Reduces layers
4. **Copy only necessary files**: Don't copy tests, docs, .git
5. **Use .dockerignore**:
   ```
   .git
   .github
   .vscode
   __pycache__
   *.pyc
   tests/
   specs/
   .pytest_cache
   .mypy_cache
   .ruff_cache
   ```

### Security Hardening

1. **Non-root user**: Run as UID 1000
2. **Read-only filesystem**: Use `--read-only` flag in docker-compose
3. **Drop capabilities**: `cap_drop: ALL` in docker-compose
4. **No new privileges**: `security_opt: no-new-privileges:true`
5. **Resource limits**: `mem_limit: 200m`, `cpus: 0.5`

### Expected Image Size
- Base python:3.14-alpine: ~50MB
- Python dependencies: ~80-100MB (mcp, websockets, aiohttp, cryptography)
- Application code: ~5MB
- **Total: ~135-155MB** (within <200MB target)

### Implementation Notes
- Dockerfile location: `docker/Dockerfile`
- Build command: `docker build -f docker/Dockerfile -t loxone-mcp:latest .`
- CI check: Fail if image > 200MB
- Document build process in quickstart.md

### Alternatives Considered
- Debian slim base: Too large (~150MB base)
- Distroless: No package manager for debugging, harder to maintain
- Scratch image: Can't install Python runtime

### References
- Docker multi-stage builds: https://docs.docker.com/build/building/multi-stage/
- Alpine packages: https://pkgs.alpinelinux.org/

---

## 5. Structured Logging Strategy

### Decision
Use **structlog** for structured logging with JSON output and audit trail support.

### Rationale
- structlog: Industry-standard structured logging for Python
- JSON output: Machine-readable, integrates with log aggregation (Loki, ELK)
- Context propagation: Automatically includes request context in logs
- Sensitive data redaction: Configurable processors to redact passwords/tokens
- Audit trail: Structured format perfect for audit logs

### Logging Configuration

```python
import structlog
from structlog.processors import JSONRenderer, TimeStamper, add_log_level

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        RedactSensitiveDataProcessor(),  # Custom processor
        JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)
```

### Log Levels

- **DEBUG**: Internal state changes, WebSocket messages (redacted)
- **INFO**: Startup, configuration, successful operations
- **WARNING**: Retries, fallback auth tier, cache evictions
- **ERROR**: Authentication failures, WebSocket disconnections, MCP errors
- **CRITICAL**: Unrecoverable errors, shutdown events

### Structured Log Format

```json
{
  "event": "component_control_executed",
  "level": "info",
  "timestamp": "2026-02-10T14:32:01.123Z",
  "logger": "loxone_mcp.mcp.tools",
  "component_uuid": "0f1e2c44-0004-...",
  "action": "On",
  "success": true,
  "duration_ms": 152,
  "user": "ai_assistant",
  "client_id": "mcp-client-abc123"
}
```

### Sensitive Data Redaction

Custom processor to redact:
- Passwords: Replace with `***REDACTED***`
- Tokens: Show only first 8 chars: `eyJhbGc...***`
- IP addresses: Optional redaction for privacy

```python
class RedactSensitiveDataProcessor:
    def __call__(self, logger, method_name, event_dict):
        # Redact password fields
        if 'password' in event_dict:
            event_dict['password'] = '***REDACTED***'
        
        # Redact tokens (show prefix only)
        if 'token' in event_dict and event_dict['token']:
            token = event_dict['token']
            event_dict['token'] = f"{token[:8]}***" if len(token) > 8 else "***"
        
        return event_dict
```

### Audit Logging

Separate audit log file for security events:

**File**: `logs/audit.jsonl` (JSON Lines format)  
**Rotation**: Daily, keep 90 days  
**Events**:
- Authentication attempts (success/failure)
- Component control commands
- Configuration changes
- Access control mode changes

**Example Audit Entry**:
```json
{
  "event": "authentication_success",
  "timestamp": "2026-02-10T14:30:00.000Z",
  "user": "admin",
  "source_ip": "192.168.1.50",
  "auth_method": "token_websocket",
  "loxone_host": "192.168.1.10"
}
```

### Implementation Notes
- Logging setup in `config.py`
- Bind context to logger: `logger = logger.bind(component_uuid=uuid)`
- Audit logger separate: `audit_logger = structlog.get_logger("audit")`
- Console output: Human-readable for development, JSON for production
- Environment variable: `LOG_LEVEL` (default: INFO)

### Log Aggregation Integration

structlog JSON output works with:
- **Grafana Loki**: Label extraction from JSON fields
- **ELK Stack**: Logstash JSON codec
- **Splunk**: JSON source type
- **CloudWatch Logs**: Custom log format

### Alternatives Considered
- Standard logging: Not structured, hard to parse
- loguru: Similar features but structlog more widely adopted
- Custom JSON logger: Reinventing the wheel, violates simplicity

### References
- structlog documentation: https://www.structlog.org/
- JSON Lines format: https://jsonlines.org/

---

## Summary

All five research topics have been resolved:

| Topic | Decision | Rationale | Status |
|-------|----------|-----------|--------|
| MCP SDK | Official `mcp` Python SDK | Native support for Resources/Tools/notifications | ✅ Resolved |
| Loxone WebSocket | `websockets` + custom parser | Required for binary state updates | ✅ Resolved |
| Cryptography | `cryptography` lib with 3-tier fallback | RSA-2048/AES-256-CBC + legacy support | ✅ Resolved |
| Container | Multi-stage Alpine Docker | <200MB target, security hardened | ✅ Resolved |
| Logging | `structlog` with JSON output | Structured logs + audit trail | ✅ Resolved |

**NEEDS CLARIFICATION count**: 0 (all resolved)

**Constitution Check**: All decisions maintain compliance with 5 principles:
- ✅ Local-first: No cloud dependencies
- ✅ Self-contained: All libraries are standard Python packages
- ✅ Observable: structlog enables comprehensive metrics
- ✅ Test-first: All libraries have mocking support
- ✅ Simplicity: Using standard, well-maintained libraries

---

**Research Version**: 1.0  
**Last Updated**: 2026-02-10  
**Status**: Complete - Ready for Phase 1
