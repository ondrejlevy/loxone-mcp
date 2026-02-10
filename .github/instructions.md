# Copilot Instructions — Loxone MCP Server

## Project Overview

MCP (Model Context Protocol) server bridging AI systems with Loxone Miniserver home automation. Exposes Loxone components and state through MCP Resources (data sources) and MCP Tools (executable actions). Supports real-time state updates via WebSocket, multiple transport modes (HTTP+SSE for remote clients, stdio for local), secure authentication with credential passthrough, audit logging, and Prometheus metrics.

- **Language**: Python 3.14 (strict typing, `from __future__ import annotations`)
- **Runtime**: Single `asyncio` event loop — all I/O is async
- **Package layout**: `src/loxone_mcp/` (setuptools with `src` layout)
- **Entry point**: `python -m loxone_mcp [--config config.yaml] [--transport http|stdio|both]`
- **Container**: `python:3.13-slim` multi-stage Docker build, non-root user
- **License**: MIT

## Architecture

```
__main__.py          CLI parsing, config loading, transport selection, signal handling
    │
config.py            YAML + env-var config with Pydantic models, validation
    │
server.py            LoxoneMCPServer orchestration: MCP server + Loxone integration lifecycle
    │                    ├── MCP handlers (Resources, Tools, Prompts, Notifications)
    │                    └── Loxone client lifecycle (connect, auth, sync, updates)
    │
transport/
    ├── stdio.py         stdio transport for local AI clients (Claude Desktop, etc.)
    └── http_sse.py      HTTP+SSE transport for remote clients (aiohttp server)
    │
mcp/
    ├── models.py        MCP protocol types (Resources, Tools, Prompts)
    ├── resources.py     Resource handlers (structure, components, rooms, categories)
    ├── tools.py         Tool handlers (get_component_state, control_component, etc.)
    └── notifications.py MCP notification triggers (resource/tool changes)
    │
loxone/
    ├── auth.py          Token-based (RSA+AES+HMAC, fw ≥9.x) + hash-based fallback (fw 8.x)
    ├── client.py        HTTP API client (structure file download, control commands)
    ├── websocket.py     WebSocket lifecycle: connect → auth → enablebinstatusupdate → event loop
    ├── models.py        Pydantic models for Loxone API responses (LoxAPP3.json structure)
    └── structure.py     Structure file parser (components, rooms, categories)
    │
state/
    ├── cache.py         In-memory state cache (structure file, component states)
    └── manager.py       State management layer (queries, updates, change detection)
    │
audit/
    └── logger.py        JSONL audit trail (user, action, timestamp, result) with rotation
    │
metrics/
    └── collector.py     Prometheus metrics exposure (/metrics endpoint)
```

### Key Data Flow

1. **Initialization**: `LoxoneMCPServer` loads config, creates MCP server with handlers
2. **Authentication**: `LoxoneAuthenticator` performs token or hash-based auth with Miniserver
3. **Structure Sync**: `LoxoneClient` downloads `LoxAPP3.json`, `parse_structure_file()` populates cache
4. **WebSocket Subscription**: `LoxoneWebSocket` sends `enablebinstatusupdate`, receives state events
5. **MCP Requests**: AI client queries Resources or calls Tools → `StateManager` reads cache
6. **State Updates**: WebSocket events → cache update → MCP notification sent to clients
7. **Control Actions**: Tool call → `LoxoneClient` sends HTTP command → state event → notification
8. **Audit Trail**: All operations logged to JSONL with user identity, action, result

## Code Conventions

- **Typing**: All functions have full type annotations. `mypy --strict` must pass.
- **Imports**: Use `from __future__ import annotations` in every module. Use `TYPE_CHECKING` guard for import-only types.
- **Models**: Use Pydantic `BaseModel` for config/API models with validation. Dataclasses for internal data structures. Prefer immutability where possible.
- **Async**: All I/O uses `asyncio`. WebSocket via `websockets` library. HTTP via `aiohttp`. MCP SDK handles stdio transport.
- **Error handling**: Domain-specific exceptions defined in module-level. Re-raise with context, never silently swallow errors.
- **Logging**: Use `structlog.get_logger()` with structured logging (JSON or console). Sensitive data (passwords, tokens) auto-redacted in audit logs.
- **Line length**: 100 chars (`ruff` enforced).
- **Naming**: PEP 8. Private functions prefixed with `_`. Constants in `UPPER_SNAKE_CASE`.
- **MCP Protocol**: Follow MCP SDK patterns - use `@server.list_resources()`, `@server.call_tool()` decorators. Return proper MCP types (`Resource`, `Tool`, `TextContent`).

## Linting & Static Analysis

```bash
ruff check src/ tests/          # Lint (E, W, F, I, N, UP, B, S, SIM, TCH, RUF rules)
ruff format src/ tests/         # Format
mypy src/                       # Strict type checking (Python 3.13)
```

- Ruff rules are configured in `pyproject.toml` `[tool.ruff.lint]`
- Security rules (flake8-bandit `S`) enabled; `S101` (assert) suppressed in tests
- `S104` (bind to 0.0.0.0) suppressed in `config.py` (intentional default)

## Testing

- **Framework**: `pytest` + `pytest-asyncio` (auto mode) + `pytest-cov` + `pytest-mock`
- **Coverage target**: ≥80% with branch coverage
- **Test structure**:
  - `src/tests/unit/` — Pure logic tests (config, models, structure, auth, state management)
  - `src/tests/integration/` — WebSocket client, HTTP server, full MCP request/response cycles
  - `src/tests/contract/` — MCP protocol contract tests (Resources, Tools follow spec)
- **Shared fixtures**: `src/tests/conftest.py` provides sample configs, mock Loxone responses, MCP test clients
- **Markers**: `@pytest.mark.integration`, `@pytest.mark.contract`, `@pytest.mark.unit`, `@pytest.mark.slow`
- **TDD**: Write tests first. Tests must fail before implementation.

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=loxone_mcp --cov-report=term-missing --cov-report=html

# Skip integration tests
pytest -m "not integration"

# Run only unit tests
pytest src/tests/unit/

# Run specific test file
pytest src/tests/unit/test_config.py
```

## Mandatory Pre-Commit Validation

**EVERY code change MUST pass linting and tests before committing.** After modifying any source or test file, always run the following commands and verify they succeed:

```bash
# 1. Lint check — must report "All checks passed!"
ruff check src/

# 2. Format check — must produce no changes
ruff format --check src/

# 3. Unit tests — must all pass with ≥80% coverage
pytest src/tests/unit/
```

If any of these commands fail, fix the issues before committing. **Do not commit code that fails linting or tests.** This applies to production code as well as test code.

## MCP Resources (Data Sources)

MCP Resources expose Loxone data for AI context:

| URI | Description | Content Type |
|-----|-------------|--------------|
| `loxone://structure` | Complete Loxone structure file (LoxAPP3.json) | JSON |
| `loxone://components` | All components with current states, room/category names | JSON |
| `loxone://rooms` | All rooms with component lists and counts | JSON |
| `loxone://categories` | All categories with component lists and counts | JSON |

## MCP Tools (Executable Actions)

MCP Tools enable AI to interact with Loxone:

| Tool | Parameters | Description |
|------|---------|-------------|
| `get_component_state` | `uuid` (str) | Get current state of specific component |
| `get_room_components` | `room_uuid` (str) | Get all components in a room with states |
| `get_components_by_type` | `component_type` (str) | Get all components of given type |
| `control_component` | `uuid` (str), `action` (str), `value?` (float) | Execute control action |

### Control Actions by Component Type

| Component Type | Actions | Value Parameter |
|---------------|---------|-----------------|
| `LightController` | `On`, `Off` | — |
| `Dimmer` | `On`, `Off`, `Dim` | 0–100 (for Dim) |
| `Jalousie` | `FullUp`, `FullDown`, `Shade`, `Stop` | — |
| `Switch` | `On`, `Off`, `Pulse` | — |

## Prometheus Metrics

Self-monitoring metrics exposed at `/metrics` (when using HTTP transport):

| Metric | Type | Labels |
|---|---|---|
| `loxone_mcp_up` | gauge | — |
| `loxone_mcp_connected` | gauge | `miniserver` |
| `loxone_mcp_last_update_timestamp_seconds` | gauge | `miniserver` |
| `loxone_mcp_components_discovered` | gauge | `miniserver` |
| `loxone_mcp_request_duration_seconds` | histogram | `method`, `status` |
| `loxone_mcp_requests_total` | counter | `method`, `status` |
| `loxone_mcp_errors_total` | counter | `error_type` |

## Configuration

- **YAML file**: `config.yaml` or `--config path/to/config.yaml`
- **Env vars**: `LOXONE_HOST`, `LOXONE_PORT`, `LOXONE_USERNAME`, `LOXONE_PASSWORD`, `MCP_TRANSPORT`, `MCP_HOST`, `MCP_PORT`, `MCP_DEBUG`, `LOG_LEVEL`
- **Env-var only mode**: No YAML needed if all required env vars are set (default: reads from `.env` file)
- **Validation**: Pydantic models with descriptive validation errors
- **Config structure**: `RootConfig` contains `LoxoneConfig`, `ServerConfig`, `AuditConfig`, `StructureCacheConfig`
- See `config/example-config.yaml` and `.env.example`

### Required Configuration

| Setting | Env Var | Description |
|---------|---------|-------------|
| `loxone.host` | `LOXONE_HOST` | Miniserver IP or hostname |
| `loxone.username` | `LOXONE_USERNAME` | Loxone user (for API auth) |
| `loxone.password` | `LOXONE_PASSWORD` | Loxone password |

### Optional Configuration

| Setting | Env Var | Default | Description |
|---------|---------|---------|-------------|
| `loxone.port` | `LOXONE_PORT` | `80` | Miniserver port |
| `server.transport` | `MCP_TRANSPORT` | `http` | Transport mode (`http`, `stdio`, `both`) |
| `server.host` | `MCP_HOST` | `0.0.0.0` | HTTP server bind address |
| `server.port` | `MCP_PORT` | `8080` | HTTP server port |
| `server.debug` | `MCP_DEBUG` | `false` | Enable debug mode |
| `server.log_level` | `LOG_LEVEL` | `INFO` | Logging level |

## Specification Documents

Detailed design documents live in `specs/001-loxone-mcp-server/`:

| File | Content |
|---|---|
| `spec.md` | Feature specification, user stories, acceptance criteria, MCP architecture |
| `plan.md` | Implementation plan, tech stack decisions, constitution checks |
| `tasks.md` | Task breakdown by user story (T001–T030+) |
| `research.md` | Loxone protocol research, auth flows, binary format, MCP protocol details |
| `data-model.md` | Entity relationship diagram, Pydantic models |
| `quickstart.md` | Development setup guide, environment setup |
| `contracts/` | API contracts for MCP Resources, Tools, Loxone API, audit log format |
| `checklists/` | Requirements checklists, testing checklists |

**Always consult these specs** when making changes to ensure consistency with the design.

## Dependencies

### Runtime
- `mcp>=1.9.0` — Model Context Protocol SDK (Resources, Tools, Prompts, Notifications)
- `websockets>=15.0` — WebSocket client for Loxone real-time events
- `aiohttp>=3.11.0` — HTTP client (Loxone API) + server (MCP HTTP+SSE transport)
- `cryptography>=44.0.0` — Loxone auth crypto (RSA, AES, HMAC)
- `prometheus-client>=0.22.0` — Metrics exposure
- `pydantic>=2.11.0` — Config and data models with validation
- `pydantic-settings>=2.8.0` — Env var and YAML config loading
- `structlog>=25.1.0` — Structured JSON logging
- `pyyaml>=6.0.0` — YAML config parsing

### Dev
- `pytest>=8.3.0`, `pytest-asyncio>=1.0.0`, `pytest-cov>=6.0.0`, `pytest-mock>=3.14.0`
- `mypy>=1.15.0` — Static type checking
- `ruff>=0.11.0` — Linting and formatting
- `pip-audit>=2.9.0` — Security vulnerability scanning

---

## Local Development

### Prerequisites

- **Python**: 3.14+ (managed via `pyenv` or system Python)
- **Container runtime**: Docker or Podman (for containerized deployment)
- **Git**: Version control

### Python Setup

```bash
# Install Python 3.14+ via pyenv (if using pyenv)
pyenv install 3.14
pyenv local 3.14

# Create virtual environment
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
# or
.venv\Scripts\activate      # Windows

# Install the project in editable mode with dev dependencies
pip install -e ".[dev]"
```

### Development Workflow

```bash
# Activate the virtual environment
source .venv/bin/activate

# Configure Loxone credentials
cp .env.example .env
# Edit .env with your Miniserver credentials

# Run the MCP server locally
python -m loxone_mcp                    # HTTP transport (default)
python -m loxone_mcp --transport stdio  # stdio for local AI (Claude Desktop)
python -m loxone_mcp --transport both   # Both transports
python -m loxone_mcp --debug            # Debug mode

# Run tests
pytest                                  # All tests
pytest src/tests/unit/                  # Unit tests only
pytest -m "not integration"             # Skip integration tests
pytest --cov=loxone_mcp                 # With coverage

# Linting and format
ruff check src/ src/tests/              # Lint
ruff format src/ src/tests/             # Format
mypy src/                               # Type check

# Security audit
pip-audit
```

### Container Development

```bash
# Build Docker image
docker build -t loxone-mcp .

# Run with docker-compose
cd docker
cp ../config/example-config.yaml ../config/config.yaml
# Edit config.yaml with your credentials
docker compose up -d

# View logs
docker compose logs -f loxone-mcp

# Stop services
docker compose down
```

### Connecting AI Clients

#### Claude Desktop (stdio transport)

Add to Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "loxone": {
      "command": "python",
      "args": ["-m", "loxone_mcp", "--transport", "stdio"],
      "env": {
        "LOXONE_HOST": "192.168.1.100",
        "LOXONE_USERNAME": "admin",
        "LOXONE_PASSWORD": "your-password"
      }
    }
  }
}
```

#### Remote AI Client (HTTP+SSE transport)

```bash
# Start MCP server with HTTP transport
python -m loxone_mcp --transport http --host 0.0.0.0 --port 8080

# AI client connects to http://localhost:8080/sse
# Pass Loxone credentials in HTTP headers:
# X-Loxone-Host: 192.168.1.100
# X-Loxone-Username: admin
# X-Loxone-Password: your-password
```

---

## MCP Protocol Integration

### MCP Server Implementation Pattern

This project uses the MCP Python SDK's low-level API for maximum flexibility:

```python
# server.py - Server initialization with MCP handlers
from mcp.server.lowlevel import Server

server = Server("loxone-mcp")

@server.list_resources()
async def list_resources() -> list[Resource]:
    """Return all MCP Resources (data sources)."""
    return [
        Resource(uri="loxone://structure", name="Loxone Structure", ...),
        Resource(uri="loxone://components", name="All Components", ...),
    ]

@server.read_resource()
async def read_resource(uri: AnyUrl) -> str:
    """Fetch content for a specific Resource URI."""
    if str(uri) == "loxone://structure":
        return state_manager.get_structure_json()
    # ... more handlers

@server.list_tools()
async def list_tools() -> list[Tool]:
    """Return all MCP Tools (executable actions)."""
    return [
        Tool(name="get_component_state", description="Get state of component", ...),
        Tool(name="control_component", description="Control a component", ...),
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Execute a Tool and return results."""
    if name == "get_component_state":
        state = await state_manager.get_component_state(arguments["uuid"])
        return [TextContent(type="text", text=json.dumps(state))]
    # ... more handlers
```

### Notification Flow

```python
# notifications.py - Trigger MCP notifications on state changes
async def notify_resource_updated(server: Server, resource_uri: str) -> None:
    """Notify clients that a Resource has been updated."""
    notification = types.ResourceUpdatedNotification(
        method="notifications/resources/updated",
        params={"uri": resource_uri},
    )
    await server.send_notification(notification)

# Called from WebSocket event handler when component state changes:
await notify_resource_updated(server, "loxone://components")
```

### Transport Layers

#### stdio Transport (Local AI)

```python
# Used by Claude Desktop, other local AI clients
from mcp.server.stdio import stdio_server

async with stdio_server() as (read_stream, write_stream):
    init_options = server.create_initialization_options()
    await server.run(read_stream, write_stream, init_options)
```

#### HTTP+SSE Transport (Remote AI)

```python
# transport/http_sse.py - HTTP server with Server-Sent Events
from aiohttp import web

async def sse_handler(request: web.Request) -> web.StreamResponse:
    """SSE endpoint for MCP over HTTP."""
    # Extract Loxone credentials from headers
    loxone_host = request.headers.get("X-Loxone-Host")
    loxone_username = request.headers.get("X-Loxone-Username")
    loxone_password = request.headers.get("X-Loxone-Password")
    
    # Create SSE stream
    response = web.StreamResponse()
    response.headers['Content-Type'] = 'text/event-stream'
    await response.prepare(request)
    
    # Route MCP messages through SSE
    # ... implementation
```

---

## Important Patterns for Copilot

### Mandatory: Lint, Type-Check & Format After Every Change

**After every code change you make**, you MUST run the full quality gate before considering the task complete:

```bash
ruff check --fix src/ src/tests/
ruff format src/ src/tests/
mypy src/
ruff check src/ src/tests/   # Final verification - must show "All checks passed!"
```

- `ruff check` must show **"All checks passed!"** with zero errors.
- `mypy src/` must show **"Success: no issues found"** with zero errors.

If either tool reports remaining errors after auto-fix, you MUST resolve them manually before committing or finishing the task. **Never leave ruff or mypy violations in the codebase.** This is a hard gate - treat any failure as a blocking error.

### When Adding a New Module

1. Add type annotations to all functions (full `mypy --strict` compliance)
2. Use `from __future__ import annotations` at the top
3. Add module docstring explaining purpose
4. Use `TYPE_CHECKING` guard for import-only types
5. Write tests first in `src/tests/unit/` or `src/tests/integration/`
6. Update relevant specification documents if module affects public API

### When Modifying MCP Resources or Tools

1. Update handler functions in `server.py`
2. Update model definitions in `mcp/models.py`
3. Add/update contract documentation in `docs/api/` or `specs/001-loxone-mcp-server/contracts/`
4. Add contract tests in `src/tests/contract/`
5. Update this instructions file if behavior changes

### When Modifying Configuration

1. Update Pydantic models in `config.py` (`RootConfig`, `LoxoneConfig`, `ServerConfig`, etc.)
2. Add field validation using Pydantic validators
3. Update `config/example-config.yaml` with annotated example
4. Update `.env.example` if adding new env vars
5. Add/update tests in `src/tests/unit/test_config.py`

### When Modifying Loxone Integration

1. Refer to `specs/001-loxone-mcp-server/research.md` for Loxone protocol details
2. Binary WebSocket format: 8-byte header + payload (UUIDs are little-endian)
3. Auth: Token-based (RSA+AES+HMAC) for fw ≥9.x, hash-based fallback for fw 8.x
4. Structure file: `LoxAPP3.json` contains all components, parse with `structure.py`
5. Update tests in `src/tests/integration/test_loxone_client.py`

### When Working with Secrets / Credentials

1. Never log credentials — `structlog` processors should redact sensitive fields
2. Passwords come from config YAML, `.env` file, or env vars
3. The `config/config.yaml` and `.env` files are gitignored; only examples are committed
4. Auth uses `cryptography` library for RSA/AES/HMAC operations
5. HTTP transport: credentials passed in headers, never in URLs or logs

### When Modifying Audit Logging

1. All write operations must be audited
2. Audit format: JSONL with structured fields (timestamp, user, action, result, sensitive fields redacted)
3. Log rotation configured via `AuditConfig`
4. Update `docs/api/audit-log.md` if adding new audit event types
5. Add tests in `src/tests/unit/test_audit_logger.py`

### When Modifying Docker Setup

1. Base image: `python:3.13-slim` (or latest stable)
2. Multi-stage build: builder stage → final stage
3. Non-root user for security
4. Health check via `/metrics` or custom health endpoint
5. Update `docker/Dockerfile` and `docker/docker-compose.yml` together
