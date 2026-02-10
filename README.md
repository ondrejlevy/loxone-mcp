# Loxone MCP Server

Bridge AI systems with [Loxone](https://www.loxone.com/) home automation through the [Model Context Protocol](https://modelcontextprotocol.io/).

## Features

- **Query States** — Read component states, rooms, and categories via MCP Resources
- **Control Components** — Operate lights, blinds, switches via MCP Tools
- **Real-Time Updates** — WebSocket-driven state change notifications
- **Secure Remote Access** — HTTP+SSE transport with credential passthrough
- **Local Mode** — stdio transport for same-machine AI clients
- **Prometheus Metrics** — Operational health at `/metrics`
- **Audit Logging** — JSONL audit trail with rotation and sensitive data redaction

## Quick Start

### Prerequisites

- Python 3.13+
- Access to a Loxone Miniserver on your local network

### Install

```bash
# Clone and install
git clone https://github.com/ondrejlevy/loxone-mcp.git
cd loxone-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Configure

Copy the example environment file and set your Loxone credentials:

```bash
cp .env.example .env
# Edit .env with your miniserver IP, username, and password
```

Or use a YAML config file:

```bash
cp config/example-config.yaml config/config.yaml
# Edit config/config.yaml
```

### Run

```bash
# HTTP transport (default) — for remote AI clients
python -m loxone_mcp

# stdio transport — for local AI clients (e.g., Claude Desktop)
python -m loxone_mcp --transport stdio

# Both transports simultaneously
python -m loxone_mcp --transport both

# With YAML config
python -m loxone_mcp --config config/config.yaml

# Debug mode
python -m loxone_mcp --debug
```

### Docker

```bash
cd docker
docker compose up -d
```

## MCP Resources

| URI | Description |
|-----|-------------|
| `loxone://structure` | Full Loxone structure file |
| `loxone://components` | All components with enriched room/category names |
| `loxone://rooms` | All rooms with component counts |
| `loxone://categories` | All categories with component counts |

## MCP Tools

| Tool | Description |
|------|-------------|
| `get_component_state` | Get current state of a specific component |
| `get_room_components` | Get all components in a room with states |
| `get_components_by_type` | Get all components of a given type |
| `control_component` | Execute a control action on a component |

### Control Actions by Component Type

| Component Type | Actions |
|---------------|---------|
| LightController | `On`, `Off` |
| Dimmer | `On`, `Off`, `Dim` (value: 0–100) |
| Jalousie | `FullUp`, `FullDown`, `Shade`, `Stop` |
| Switch | `On`, `Off`, `Pulse` |
| IRoomControllerV2 | `SetTemperature` (value: 5.0–40.0) |


## Access Control

Set the access mode to restrict operations:

| Mode | Resources | Tools (read) | Tools (control) |
|------|-----------|-------------|-----------------|
| `read-write` | ✓ | ✓ | ✓ |
| `read-only` | ✓ | ✓ | ✗ |
| `write-only` | ✗ | ✗ | ✓ |

Configure via `LOXONE_ACCESS_MODE` env var or `access_control.mode` in YAML.

## Monitoring

Prometheus metrics are exposed at `GET /metrics`:

- `mcp_requests_total` — Request count by method and status
- `mcp_request_duration_seconds` — Request latency histogram
- `mcp_active_connections` — Current connection count
- `loxone_websocket_connected` — WebSocket connection status
- `loxone_api_duration_seconds` — Loxone API call latency
- `loxone_auth_attempts_total` — Authentication attempts
- `loxone_state_updates_total` — State update count
- `structure_cache_hits_total` / `structure_cache_misses_total` — Cache performance
- `cache_size_bytes` — Cache memory usage

## Audit Logging

All operations are logged to `logs/audit.jsonl` in JSON Lines format:

```json
{"timestamp": "2026-02-10T12:00:00Z", "event_type": "TOOL_EXECUTION", "user": "admin", "action": "control_component", "target": "0a1b2c3d-...", "success": true, "duration_ms": 145}
```

Features:
- Daily log rotation (`audit-YYYY-MM-DD.jsonl`)
- Configurable retention (default: 90 days)
- Automatic sensitive data redaction (passwords, tokens)

## Architecture

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────┐
│   AI Client  │────▶│  Loxone MCP      │────▶│   Loxone     │
│  (Claude,    │◀────│  Server          │◀────│  Miniserver  │
│   Cursor)    │     │                  │     │              │
│              │     │  ┌─Resources─┐   │     │  ┌─HTTP──┐   │
│  MCP Proto   │     │  ├─Tools────┤   │     │  ├─WS────┤   │
│  (stdio/HTTP)│     │  ├─Metrics──┤   │     │  └───────┘   │
│              │     │  ├─Audit────┤   │     │              │
└──────────────┘     │  └──────────┘   │     └──────────────┘
                     └──────────────────┘
```

## CI/CD Pipeline

[![CI](https://github.com/ondrejlevy/loxone-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/ondrejlevy/loxone-mcp/actions/workflows/ci.yml)
[![Security](https://github.com/ondrejlevy/loxone-mcp/actions/workflows/security.yml/badge.svg)](https://github.com/ondrejlevy/loxone-mcp/actions/workflows/security.yml)
[![Docker](https://github.com/ondrejlevy/loxone-mcp/actions/workflows/docker.yml/badge.svg)](https://github.com/ondrejlevy/loxone-mcp/actions/workflows/docker.yml)

### Workflows

#### CI (`ci.yml`)
**Runs on:** push to main/develop, pull requests

- **Lint Code**: Code style and format check with Ruff
- **Type Check**: Static analysis with Mypy
- **Run Tests**: Unit and integration tests with Pytest (requires 80% coverage)
- **Generate SBOM**: Software Bill of Materials (CycloneDX format)

#### Docker Build (`docker.yml`)
**Runs on:** push to main, version tags (v*)

- Multi-platform build (linux/amd64, linux/arm64)
- Push to GitHub Container Registry (`ghcr.io`)
- SLSA provenance attestation for supply chain security
- Container vulnerability scan with Trivy
- Automated Docker SBOM generation

**Pull image:**
```bash
docker pull ghcr.io/ondrejlevy/loxone-mcp:latest
```

#### Security (`security.yml`)
**Runs on:** push, pull requests, weekly schedule (Monday 06:00 UTC)

- **Python Security Audit**: Dependency vulnerabilities with pip-audit
- **Trivy Filesystem**: Source code and dependency scanning
- **Trivy Container**: Docker image vulnerability scanning
- **CodeQL Analysis**: Advanced static security analysis

All security findings are automatically uploaded to the Security tab.

### Running Locally

```bash
# Lint
ruff check src/ tests/

# Format
ruff format src/ tests/

# Type check
mypy src/

# Tests with coverage
pytest --cov=loxone_mcp --cov-report=term

# Security audit
pip-audit
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all checks (like CI)
ruff check src/ tests/ && \
mypy src/loxone_mcp/ && \
pytest --cov=loxone_mcp --cov-report=term

# Auto-fix linting issues
ruff check src/ tests/ --fix

# Format code
ruff format src/ tests/
```

See [CI/CD Pipeline](#cicd-pipeline) section for available workflows and local testing commands.

## Configuration Reference

See [config/example-config.yaml](config/example-config.yaml) for all available settings with documentation.

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LOXONE_HOST` | Yes | — | Miniserver IP or hostname |
| `LOXONE_USERNAME` | Yes | — | Loxone username |
| `LOXONE_PASSWORD` | Yes | — | Loxone password |
| `LOXONE_PORT` | No | `80` | Miniserver port |
| `LOXONE_USE_TLS` | No | `false` | Use TLS for Loxone connections |
| `LOXONE_ACCESS_MODE` | No | `read-write` | Access control mode |
| `MCP_HOST` | No | `0.0.0.0` | Server bind address |
| `MCP_PORT` | No | `8080` | Server port |
| `MCP_TRANSPORT` | No | `http` | Transport: http, stdio, both |
| `MCP_LOG_LEVEL` | No | `INFO` | Log level |
| `MCP_DEBUG` | No | `false` | Debug mode |
| `METRICS_ENABLED` | No | `true` | Enable Prometheus metrics |
| `AUDIT_ENABLED` | No | `true` | Enable audit logging |
| `AUDIT_LOG_FILE` | No | `logs/audit.jsonl` | Audit log path |
| `AUDIT_RETENTION_DAYS` | No | `90` | Audit log retention |
| `STRUCTURE_CACHE_TTL` | No | `3600` | Structure cache TTL (seconds) |
| `STRUCTURE_CHANGE_INTERVAL` | No | `300` | Structure change poll interval |

## License

MIT License. See [LICENSE](LICENSE) for details.
