# Implementation Plan: Loxone MCP Server for AI Integration

**Branch**: `001-loxone-mcp-server` | **Date**: 2026-02-10 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `/specs/001-loxone-mcp-server/spec.md`

## Summary

Implement an MCP (Model Context Protocol) server that bridges AI systems with Loxone miniserver home automation. The server exposes Loxone components and controls through MCP Resources and Tools, enabling AI assistants to query component states and execute control commands. Uses hybrid MCP architecture (Resources for data queries, Tools for actions) with real-time MCP notifications for state changes. Supports multi-tier Loxone authentication (token-based via WebSocket/HTTP for firmware 9.x+, hash-based for legacy 8.x firmware) with RSA-2048/AES-256-CBC encryption. Provides operational metrics endpoint and comprehensive audit logging.

## Technical Context

**Language/Version**: Python 3.14  
**Runtime Container**: python:3.14-alpine  
**Primary Dependencies**:
- **mcp** (Model Context Protocol SDK) - MCP server implementation
- **websockets** - WebSocket client for Loxone real-time updates
- **aiohttp** - Async HTTP client for Loxone API and MCP HTTP transport
- **cryptography** - RSA/AES encryption for Loxone authentication
- **prometheus-client** - Metrics export
- **pydantic** - Configuration and data validation
- **structlog** - Structured logging with audit trail support

**Storage**: In-memory caching (Loxone structure file, component state), file-based audit logs (JSON lines)  
**Testing**: pytest, pytest-asyncio, pytest-cov, pytest-mock (target: 80% coverage)  
**Target Platform**: Linux containers (Docker/Podman), Alpine-based image  
**Project Type**: Server (async Python service with MCP protocol endpoints)

**Performance Goals**: 
- <1s response time for MCP Resource reads
- <2s for control Tool execution
- Handle 100 concurrent MCP client connections  
- <1s MCP notification delivery after Loxone state change

**Constraints**: 
- <200MB container memory footprint
- <10% CPU single-core utilization at steady state
- Support Loxone firmware 8.x through 9.x+
- Server-wide access control only (not per-user permissions)
- No external dependencies beyond Loxone miniserver

**Scale/Scope**: 
- Single Loxone miniserver per MCP server instance  
- Up to 500 components per miniserver
- Support 50 concurrent MCP clients
- Structure file up to 5MB

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Local-First Architecture ✅

- **Pass**: Entire solution runs locally in containers
- **Pass**: Only communicates with configured Loxone miniserver (no cloud dependencies)
- **Pass**: No telemetry or external API calls
- **Pass**: Configuration via local files (YAML/environment variables)
- **Note**: MCP protocol is local-first by design; clients connect directly to server

### Self-Contained Solution ✅

- **Pass**: Single container deployment
- **Pass**: All dependencies are open-source Python packages
- **Pass**: No external databases or message queues required
- **Pass**: In-memory state management with file-based audit logs
- **Minor Concern**: Dependency count is moderate (7 primary + transitive) - justified by:
  - MCP SDK: essential for protocol implementation
  - websockets/aiohttp: standard async libraries
  - cryptography: required for Loxone authentication security
  - prometheus-client: standard metrics library

### Observable Metrics Export ✅

- **Pass**: Metrics endpoint at `/metrics`
- **Pass**: Includes MCP server health metrics (connection counts, request latencies, error rates)
- **Pass**: Includes Loxone integration metrics (WebSocket status, authentication failures, API call duration)
- **Pass**: Prometheus-compatible format with proper naming conventions
- **Implementation Note**: Use prometheus-client library

### Test-First Development ✅

- **Planned**: Unit tests for MCP Resource/Tool handlers
- **Planned**: Integration tests with mock Loxone API responses
- **Planned**: Contract tests for MCP protocol compliance
- **Planned**: Authentication flow tests (all three fallback tiers)
- **Target**: 80% code coverage minimum
- **CI**: GitHub Actions workflow with pytest execution

### Simplicity & Maintainability ✅

- **Pass**: Clear architectural layers (MCP protocol / Loxone client / State manager)
- **Pass**: Explicit error handling with context (audit logging)
- **Pass**: Configuration validation on startup with helpful messages
- **Pass**: YAGN I: Implementing only requested features (no UI, no multi-miniserver)
- **Implementation Note**: Use type hints throughout, structured logging

### Phase 1 Re-check (Post-Design)

**Status**: ✅ PASSED (evaluated 2026-02-10)

**Areas verified**:

1. **Dependency count remains justified** ✅
   - 7 primary dependencies documented in data-model.md
   - All dependencies are standard, well-maintained libraries
   - No additional dependencies introduced during design
   - Rationale remains valid: MCP SDK (required), websockets/aiohttp (standard async), cryptography (auth requirement), prometheus-client/pydantic/structlog (operational)

2. **No accidental external API integrations introduced** ✅
   - Confirmed: Only Loxone miniserver communication (local network)
   - No cloud services in contracts
   - No telemetry endpoints in data model
   - Audit logs are file-based (no external logging services)

3. **Test strategy covers all critical paths** ✅
   - Unit tests planned for: MCP handlers, Loxone auth (all 3 tiers), structure cache, state manager
   - Integration tests planned for: Loxone client, MCP lifecycle, notifications
   - Contract tests for MCP protocol compliance
   - 80% coverage target enforced in CI
   - Fixtures prepared for mock Loxone responses

4. **Cache invalidation strategy is simple and correct** ✅
   - Structure file: Simple TTL-based (1 hour, configurable)
   - Component states: Event-driven from WebSocket (no TTL)
   - Invalidation triggers: TTL expiry, manual endpoint, WebSocket reconnect
   - No complex distributed cache coordination
   - Thread-safe implementation with Lock (StateCache class)

**Additional Constitution Checks**:

5. **Local-First Architecture** ✅
   - Reconfirmed: No cloud dependencies in any contract
   - All communication stays within local network (Loxone miniserver)
   - Configuration via local files or environment variables

6. **Self-Contained Solution** ✅
   - Reconfirmed: Single container deployment
   - No external databases (in-memory + file-based audit)
   - All state management is internal (StateCache)

7. **Observable Metrics Export** ✅
   - Comprehensive metrics defined in data-model.md (Metrics class)
   - Covers MCP server, Loxone integration, and cache metrics
   - Prometheus-compatible format

8. **Test-First Development** ✅
   - Test structure defined in quickstart.md
   - Fixtures directory planned (tests/fixtures/)
   - CI pipeline includes pytest, coverage, mypy, ruff

9. **Simplicity & Maintainability** ✅
   - Clear data model with 17 well-defined classes
   - Contracts are explicit and documented
   - Configuration uses Pydantic validation
   - No over-engineering detected

**Conclusion**: Phase 1 design fully complies with all 5 constitution principles. Ready to proceed to Phase 2 task generation.

## Project Structure

### Documentation (this feature)

```text
specs/001-loxone-mcp-server/
├── plan.md              # This file
├── research.md          # Phase 0: Technology research and decisions
├── data-model.md        # Phase 1: Data structures and state management
├── quickstart.md        # Phase 1: Developer quickstart guide
├── contracts/           # Phase 1: Protocol contracts
│   ├── mcp-resources.md # MCP Resources schema
│   ├── mcp-tools.md     # MCP Tools schema
│   └── loxone-api.md    # Loxone API integration patterns
└── tasks.md             # Phase 2: Implementation tasks (via /speckit.tasks)
```

### Source Code (repository root)

```text
loxone-mcp/
├── src/
│   ├── loxone_mcp/
│   │   ├── __init__.py
│   │   ├── __main__.py          # Entry point
│   │   ├── config.py            # Configuration management (Pydantic)
│   │   ├── server.py            # MCP server initialization
│   │   ├── mcp/
│   │   │   ├── __init__.py
│   │   │   ├── resources.py    # MCP Resource handlers
│   │   │   ├── tools.py        # MCP Tool handlers
│   │   │   ├── notifications.py # MCP notification sender
│   │   │   └── lifecycle.py    # MCP lifecycle management
│   │   ├── loxone/
│   │   │   ├── __init__.py
│   │   │   ├── client.py       # Loxone API client
│   │   │   ├── auth.py         # Multi-tier authentication
│   │   │   ├── websocket.py    # WebSocket connection handler
│   │   │   ├── structure.py    # Structure file parser & cache
│   │   │   └── models.py       # Loxone data models
│   │   ├── state/
│   │   │   ├── __init__.py
│   │   │   ├── manager.py      # State cache manager
│   │   │   └── cache.py        # In-memory cache implementation
│   │   ├── metrics/
│   │   │   ├── __init__.py
│   │   │   └── collector.py    # Prometheus metrics collector
│   │   ├── audit/
│   │   │   ├── __init__.py
│   │   │   └── logger.py       # Audit log writer
│   │   └── transport/
│   │       ├── __init__.py
│   │       ├── stdio.py        # stdio transport
│   │       └── http_sse.py     # HTTP with SSE transport
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py          # Pytest fixtures
│       ├── unit/
│       │   ├── test_config.py
│       │   ├── test_mcp_resources.py
│       │   ├── test_mcp_tools.py
│       │   ├── test_loxone_auth.py
│       │   ├── test_structure_cache.py
│       │   └── test_state_manager.py
│       ├── integration/
│       │   ├── test_loxone_client.py
│       │   ├── test_mcp_lifecycle.py
│       │   └── test_notifications.py
│       └── fixtures/
│           ├── loxone_structure_file.json
│           └── loxone_responses.json
├── config/
│   └── example-config.yaml      # Example configuration
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml       # Example deployment
├── .github/
│   ├── workflows/
│   │   ├── ci.yml              # CI/CD pipeline
│   │   └── security.yml        # Security scanning
│   └── dependabot.yml          # Dependency updates
├── pyproject.toml              # Poetry/pip config
├── requirements.txt            # Pinned dependencies
├── requirements-dev.txt        # Development dependencies
├── README.md
├── LICENSE
└── .python-version             # 3.14
```

**Structure Decision**: Single project structure chosen. This is a backend server application with no frontend component. All code lives under `src/loxone_mcp/` with clear module separation: MCP protocol layer, Loxone integration layer, state management, metrics, audit, and transport implementations.

## Phase 0: Research

**Objective**: Resolve all unknowns from Technical Context and gather implementation patterns.

### Research Topics

1. **MCP SDK Selection**
   - Evaluate official Python MCP SDK
   - Verify stdio and HTTP+SSE transport support
   - Document lifecycle management patterns
   - Deliverable: SDK decision in research.md

2. **Loxone WebSocket Protocol**
   - Research WebSocket command structure
   - Document state update message format
   - Identify keepalive/reconnection patterns
   - Deliverable: Integration patterns in research.md

3. **Cryptography Implementation**
   - RSA-2048 key exchange implementation
   - AES-256-CBC session encryption
   - Hash-based HMAC-SHA1 fallback
   - Deliverable: Auth strategy in research.md

4. **Container Optimization**
   - Alpine package requirements
   - Multi-stage build pattern for < 200MB image
   - Security hardening (non-root user, minimal capabilities)
   - Deliverable: Dockerfile best practices in research.md

5. **Structured Logging Strategy**
   - structlog configuration for audit trails
   - JSON output format for log aggregation
   - Sensitive data redaction patterns
   - Deliverable: Logging standards in research.md

**Deliverable**: `research.md` with all decisions documented.

## Phase 1: Design & Contracts

**Prerequisites**: `research.md` complete, Constitution Check passed.

### 1.1 Data Model

Create `data-model.md` with:

**Loxone Domain Models**:
- `Component`: UUID, name, type, room, category, state, capabilities
- `Room`: UUID, name, type, components
- `Category`: UUID, name, components
- `StructureFile`: version, components, rooms, categories, lastModified

**MCP Domain Models**:
- `MCPResource`: URI, mimeType, description, metadata
- `MCPTool`: name, description, inputSchema, handler
- `MCPNotification`: method, params (resource URI, changeType)

**Configuration Models** (Pydantic):
- `ServerConfig`: host, port, transports (stdio/http)
- `LoxoneConfig`: host, port, username, password, useTLS
- `AccessControl`: mode (read-only/write-only/read-write)
- `MetricsConfig`: enabled, endpoint path
- `AuditConfig`: enabled, log file path, retention days

**State Management**:
- Cache strategy: TTL for structure file (1 hour default), state cache (realtime via WebSocket)
- Invalidation: Manual trigger + automatic on WebSocket disconnection
- Notification flow: Loxone WebSocket → State Manager → MCP notification sender

### 1.2 API Contracts

Create `contracts/` directory:

**contracts/mcp-resources.md**:
```text
Resource URIs:
- loxone://structure - Full structure file (JSON)
- loxone://components - List all components
- loxone://rooms - List all rooms
- loxone://categories - List all categories

Schema: MCP Resource schema (JSON Schema format)
```

**contracts/mcp-tools.md**:
```text
Tools:
1. get_component_state(component_uuid: str) → state: object
2. control_component(component_uuid: str, action: str, params: object) → success: bool
3. get_room_components(room_uuid: str) → components: list
4. get_components_by_type(component_type: str) → components: list

Schema: MCP Tool input/output schemas (JSON Schema format)
```

**contracts/loxone-api.md**:
```text
Authentication flow:
1. Token-based (WebSocket): getkey → encrypt credentials → gettoken → JWT
2. Token-based (HTTP): Same flow via HTTP API
3. Hash-based (legacy): getsalt → HMAC-SHA1(password, salt) → authenticate

WebSocket commands:
- jdev/sps/enablebinstatusupdate - Enable state updates
- jdev/sys/getkey - Get public key
- jdev/sys/gettoken/{hash}/{user} - Get JWT token

State update format: Binary protocol (header + payload)
```

### 1.3 Quickstart Guide

Create `quickstart.md`:
- Prerequisites (Python 3.14, Docker)
- Local development setup
- Configuration file example
- Running tests
- Building container
- Running with docker-compose

### 1.4 Update Agent Context

Run update script:
```bash
.specify/scripts/bash/update-agent-context.sh copilot
```

This updates `.specify/memory/copilot-instructions.md` with:
- Python 3.14 + MCP SDK
- websockets + aiohttp
- cryptography library
- pytest testing stack

### 1.5 Phase 1 Constitution Re-check

Re-evaluate all 5 constitution principles against the data model and contracts. Document any concerns in plan.md.

**Deliverables**:
- `data-model.md`
- `contracts/mcp-resources.md`, `contracts/mcp-tools.md`, `contracts/loxone-api.md`
- `quickstart.md`
- Updated agent context file

## Phase 2: Implementation Tasks

**Prerequisites**: Phase 1 complete, Constitution re-check passed.

Phase 2 tasks will be generated using `/speckit.tasks` command after Phase 1 design is approved. Tasks will be organized by priority (P0/P1/P2) and tracked in `tasks.md`.

Expected task categories:
1. **Foundation** (P0): Project setup, configuration, logging
2. **Loxone Integration** (P0): Authentication, WebSocket client, structure file parser
3. **MCP Protocol** (P0): Resource handlers, Tool handlers, lifecycle
4. **Transports** (P1): stdio implementation, HTTP+SSE implementation
5. **State Management** (P1): Cache implementation, notification sender
6. **Operational Features** (P1): Metrics collector, audit logger
7. **Testing** (P1): Unit tests, integration tests, contract tests
8. **Deployment** (P2): Dockerfile, docker-compose, documentation
9. **CI/CD Pipeline** (P2): GitHub Actions, security scanning, SBOM generation

Estimated timeline: 4-5 weeks across phases 2A-2D.

## Docker Configuration

### Dockerfile (Multi-Stage Build)

```dockerfile
# Stage 1: Build dependencies
FROM python:3.14-alpine AS builder
WORKDIR /build
RUN apk add --no-cache gcc musl-dev libffi-dev openssl-dev
COPY requirements.txt .
RUN pip install --prefix=/install --no-warn-script-location -r requirements.txt

# Stage 2: Runtime
FROM python:3.14-alpine
RUN apk add --no-cache libffi openssl && \
    adduser -D -u 1000 loxone
WORKDIR /app
COPY --from=builder /install /usr/local
COPY src/ /app/src/
USER loxone
EXPOSE 8080
ENTRYPOINT ["python", "-m", "loxone_mcp"]
```

Target size: < 200MB

### docker-compose.yml

```yaml
version: '3.8'
services:
  loxone-mcp:
    build: .
    image: loxone-mcp:latest
    container_name: loxone-mcp-server
    ports:
      - "8080:8080"
    environment:
      - LOXONE_HOST=${LOXONE_HOST}
      - LOXONE_USERNAME=${LOXONE_USERNAME}
      - LOXONE_PASSWORD=${LOXONE_PASSWORD}
      - MCP_TRANSPORT=http
      - LOG_LEVEL=INFO
    volumes:
      - ./config/config.yaml:/app/config.yaml:ro
      - ./logs:/app/logs
    restart: unless-stopped
    mem_limit: 200m
    cpus: 0.5
    read_only: true
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
```

### Example .env file

```bash
LOXONE_HOST=192.168.1.10
LOXONE_USERNAME=admin
LOXONE_PASSWORD=secret
```

## CI/CD Configuration

### GitHub Actions Workflow

`.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main, '0*']
  pull_request:

jobs:
  lint-and-type-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.14'
      - run: pip install ruff mypy
      - run: ruff check src/
      - run: mypy src/

  security-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.14'
      - run: pip install pip-audit
      - run: pip-audit -r requirements.txt
      - uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'fs'
          scan-ref: '.'

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.14'
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: pytest --cov=src/loxone_mcp --cov-report=xml
      - uses: codecov/codecov-action@v4
        with:
          token: ${{ secrets.CODECOV_TOKEN }}

  sbom-generation:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.14'
      - run: pip install cyclonedx-bom
      - run: cyclonedx-py -r -i requirements.txt -o sbom.json
      - uses: actions/upload-artifact@v4
        with:
          name: sbom
          path: sbom.json

  build-container:
    runs-on: ubuntu-latest
    needs: [lint-and-type-check, security-scan, test]
    steps:
      - uses: actions/checkout@v4
      - uses: docker/build-push-action@v5
        with:
          context: .
          file: docker/Dockerfile
          tags: loxone-mcp:${{ github.sha }}
          push: false

  security-container-scan:
    runs-on: ubuntu-latest
    needs: build-container
    steps:
      - uses: aquasecurity/trivy-action@master
        with:
          image-ref: 'loxone-mcp:${{ github.sha }}'
          format: 'sarif'
          output: 'trivy-results.sarif'
      - uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: 'trivy-results.sarif'
```

### Dependabot Configuration

`.github/dependabot.yml`:

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 10

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"

  - package-ecosystem: "docker"
    directory: "/docker"
    schedule:
      interval: "weekly"
```

## Risk Mitigation

### Risk 1: Loxone Authentication Complexity

**Impact**: High - Without proper auth, server cannot connect  
**Mitigation**:
- Implement all three auth tiers with fallback logic
- Create integration tests with mock Loxone responses
- Document auth troubleshooting in quickstart.md

**Monitoring**: Track authentication failures in metrics

### Risk 2: MCP Protocol Compatibility

**Impact**: Medium - Protocol changes could break clients  
**Mitigation**:
- Pin MCP SDK version in requirements.txt
- Create contract tests against MCP spec
- Document supported MCP version in README

**Monitoring**: Track MCP protocol errors in metrics

### Risk 3: Memory Leak from Cache

**Impact**: Medium - Could exceed 200MB memory limit  
**Mitigation**:
- Implement cache eviction policy (LRU with size limit)
- Add memory usage metrics
- Create load tests with large structure files

**Monitoring**: Track cache size and memory usage in metrics

### Risk 4: WebSocket Reconnection Storms

**Impact**: Medium - Could overwhelm Loxone miniserver  
**Mitigation**:
- Implement exponential backoff (1s, 2s, 4s, 8s, max 60s)
- Add circuit breaker pattern
- Log reconnection attempts with context

**Monitoring**: Track WebSocket disconnections and reconnection delays

### Risk 5: Container Image Size

**Impact**: Low - Exceeding 200MB target  
**Mitigation**:
- Use multi-stage Dockerfile with Alpine base
- Remove build dependencies from runtime image
- Measure image size in CI pipeline

**Monitoring**: CI job fails if image > 200MB

### Risk 6: Concurrent Client Scalability

**Impact**: Low - Performance degradation with many clients  
**Mitigation**:
- Use async I/O throughout (aiohttp, asyncio)
- Create load tests with 50+ concurrent clients
- Document resource limits in docker-compose

**Monitoring**: Track concurrent connections and request latencies

## Next Steps

As per mode instructions, this command ends after Phase 2 planning. Implementation will proceed through:

1. **Phase 0: Research** - Create `research.md` with technology decisions
2. **Phase 1: Design** - Create `data-model.md`, `contracts/`, `quickstart.md`, update agent context
3. **Phase 1: Constitution Re-check** - Verify design against all 5 principles
4. **Phase 2: Task Generation** - Run `/speckit.tasks` to generate implementation tasks
5. **Phase 2: Implementation** - Execute tasks from `tasks.md`

**Ready for**: Phase 0 - Research

---

**Plan Version**: 1.0  
**Last Updated**: 2026-02-10  
**Status**: Planning Complete - Ready for Phase 0
