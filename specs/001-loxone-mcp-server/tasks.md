# Tasks: Loxone MCP Server for AI Integration

**Input**: Design documents from `/specs/001-loxone-mcp-server/`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Tests**: Following Test-First Development (Constitution Principle IV), test infrastructure and test tasks are included throughout this plan to achieve 80% code coverage minimum.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [x] T001 Create project structure with src/loxone_mcp/ and src/tests/ directories
- [x] T002 Initialize Python 3.14 project with pyproject.toml and requirements.txt (mcp, websockets, aiohttp, cryptography, prometheus-client, pydantic, structlog)
- [x] T003 [P] Configure ruff for linting in pyproject.toml
- [x] T004 [P] Configure mypy for type checking in pyproject.toml
- [x] T005 [P] Create pytest configuration in pyproject.toml
- [x] T006 [P] Create .python-version file with 3.14
- [x] T007 [P] Create .gitignore for Python project

---

## Phase 1.5: Test Infrastructure (Quality Foundation)

**Purpose**: Set up testing framework and fixtures to support Test-First Development (Constitution Principle IV)

**⚠️ CRITICAL**: This phase MUST be complete before implementing any user story features to enable TDD workflow

- [x] T007a [P] Create pytest fixtures for mock Loxone API responses in src/tests/fixtures/loxone_responses.py (structure file, component states, WebSocket messages)
- [x] T007b [P] Create mock Loxone structure file in src/tests/fixtures/loxone_structure_file.json (sample miniserver config with rooms, categories, components)
- [x] T007c [P] Create test utilities in src/tests/conftest.py (async test helpers, mock WebSocket server, mock HTTP server)
- [x] T007d [P] Create MCP protocol contract test framework in src/tests/contract/ (JSON-RPC validation, Resource/Tool schema verification)
- [x] T007e [P] Document testing strategy in src/tests/README.md (unit vs integration, mocking approach, coverage goals)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T008 Create configuration models in src/loxone_mcp/config.py (ServerConfig, LoxoneConfig, AccessControlConfig with mode field accepting 'read-write'|'read-only'|'write-only' via LOXONE_ACCESS_MODE env var or config.yaml access_control.mode, MetricsConfig, AuditConfig, StructureCacheConfig with change_detection_interval, RootConfig with Pydantic)
- [x] T009 Implement configuration loading from YAML and environment variables in src/loxone_mcp/config.py
- [x] T010 [P] Setup structured logging with structlog in src/loxone_mcp/config.py (JSON output, sensitive data redaction)
- [x] T011 [P] Create Loxone data models in src/loxone_mcp/loxone/models.py (Component, Room, Category, StructureFile dataclasses)
- [x] T012 [P] Create MCP domain models in src/loxone_mcp/mcp/__init__.py (MCPResource, MCPTool, MCPNotification classes)
- [x] T013 Create StateCache class in src/loxone_mcp/state/cache.py (thread-safe in-memory cache with event-driven invalidation: WebSocket reconnect + manual trigger, TTL fallback 1 hour, structure file <5MB, real-time updates for component states)
- [x] T014 Create StateManager in src/loxone_mcp/state/manager.py (coordinates cache updates, notification triggers)
- [x] T015 Implement Loxone authentication (3-tier fallback) in src/loxone_mcp/loxone/auth.py (token WebSocket, token HTTP, hash-based for 8.x)
- [x] T016 Implement RSA-2048 key exchange and AES-256-CBC encryption in src/loxone_mcp/loxone/auth.py using cryptography library
- [x] T016a Implement automatic token refresh in src/loxone_mcp/loxone/auth.py (refresh 5min before expiry, retry on failure, re-authenticate if refresh fails) - Implements FR-017
- [x] T017 Create Loxone HTTP client for structure file retrieval in src/loxone_mcp/loxone/client.py (GET /jdev/sps/LoxAPP3.json with retry logic: 3 attempts with exponential backoff 1s, 2s, 4s)
- [x] T018 Create structure file parser in src/loxone_mcp/loxone/structure.py (parse JSON to StructureFile model)
- [x] T019 Create Loxone WebSocket client in src/loxone_mcp/loxone/websocket.py (connection, binary state update parser, keepalive)
- [x] T020 Implement WebSocket binary state update parser in src/loxone_mcp/loxone/websocket.py (header + UUID + value parsing)
- [x] T021 Implement WebSocket reconnection with exponential backoff in src/loxone_mcp/loxone/websocket.py (1s, 2s, 4s... max 60s)
- [x] T022 Create MCP server initialization in src/loxone_mcp/server.py (mcp.server.Server setup, lifecycle management)
- [x] T023 Create application entry point in src/loxone_mcp/__main__.py (load config, initialize services, start server)
- [x] T024 Implement error handling framework in src/loxone_mcp/server.py (global exception handler, structured error responses)
- [x] T024a [P] Implement HTTP transport with SSE in src/loxone_mcp/transport/http_sse.py (aiohttp server, MCP protocol over HTTP) - Required for MCP notifications (FR-032)
- [x] T024b Implement HTTP header authentication extraction in src/loxone_mcp/transport/http_sse.py (extract username/password from Authorization header or custom headers)
- [x] T024c Pass authenticated user credentials to Loxone client in src/loxone_mcp/loxone/client.py (use per-request credentials for Loxone API)
- [x] T024d Implement SSE streaming for MCP notifications in src/loxone_mcp/transport/http_sse.py (Server-Sent Events for resources/updated notifications)

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Query Component States (Priority: P1) 🎯 MVP

**Goal**: AI systems can read Loxone component states through MCP Resources and Tools to understand current smart home status

**Independent Test**: Query MCP Resources (loxone://components, loxone://structure) and call get_component_state Tool to verify returned data matches Loxone miniserver states

### Implementation for User Story 1

- [x] T025 [P] [US1] Implement MCP Resource handler for loxone://structure in src/loxone_mcp/mcp/resources.py (@server.list_resources decorator, return cached structure file)
- [x] T026 [P] [US1] Implement MCP Resource handler for loxone://components in src/loxone_mcp/mcp/resources.py (list all components with enriched data: roomName, categoryName)
- [x] T027 [P] [US1] Implement MCP Resource handler for loxone://rooms in src/loxone_mcp/mcp/resources.py (list all rooms with component counts)
- [x] T028 [P] [US1] Implement MCP Resource handler for loxone://categories in src/loxone_mcp/mcp/resources.py (list all categories with component counts)
- [x] T029 [P] [US1] Implement MCP Tool get_component_state in src/loxone_mcp/mcp/tools.py (input: component_uuid, output: component with current state from cache)
- [x] T030 [P] [US1] Implement MCP Tool get_room_components in src/loxone_mcp/mcp/tools.py (input: room_uuid, output: all components in room with states)
- [x] T031 [P] [US1] Implement MCP Tool get_components_by_type in src/loxone_mcp/mcp/tools.py (input: component_type, output: all components of type with states)
- [x] T032 [US1] Integrate WebSocket state updates with StateManager to update cache in src/loxone_mcp/state/manager.py
- [x] T033 [US1] Implement MCP notification sender in src/loxone_mcp/mcp/notifications.py (send resources/updated when states change)
- [x] T034 [US1] Wire WebSocket state updates to trigger MCP notifications in src/loxone_mcp/loxone/websocket.py
- [x] T035 [US1] Add structure file cache invalidation on WebSocket reconnect in src/loxone_mcp/state/manager.py
- [x] T035a [US1] Implement structure file change detection in src/loxone_mcp/loxone/client.py (poll hash comparison every 5min configurable via StructureCacheConfig.change_detection_interval, trigger cache reload and MCP notification) - Implements FR-036, FR-037
- [x] T036 [US1] Implement access control check for read operations in src/loxone_mcp/mcp/resources.py (respect AccessControlConfig mode)
- [x] T036a [P] [US1] Write unit tests for US1 in src/tests/unit/test_us1_query_states.py (test all Resource handlers, Tools, state cache integration, notification flow, access control) - Target: 80% coverage

**Checkpoint**: At this point, User Story 1 should be fully functional - AI can query all component states via MCP Resources and Tools

---

## Phase 4: User Story 2 - Control Components (Priority: P1)

**Goal**: AI systems can control Loxone components (lights, switches, etc.) via MCP Tools to execute user commands

**Independent Test**: Call control_component Tool with various actions (On, Off, Dim) and verify Loxone components change states accordingly

### Implementation for User Story 2

- [x] T037 [P] [US2] Implement control command execution via WebSocket in src/loxone_mcp/loxone/client.py (jdev/sps/io/{uuid}/{action} format)
- [x] T038 [US2] Implement MCP Tool control_component in src/loxone_mcp/mcp/tools.py (input: component_uuid + action + params, execute Loxone command, return success + new state)
- [x] T039 [US2] Add action validation for component types in src/loxone_mcp/mcp/tools.py (LightController: On/Off/Dim, Jalousie: FullUp/FullDown/Shade, etc.)
- [x] T040 [US2] Implement parameter validation for control actions in src/loxone_mcp/mcp/tools.py (e.g., Dim requires value 0-100)
- [x] T041 [US2] Add access control check for write operations in src/loxone_mcp/mcp/tools.py (respect AccessControlConfig mode, return 403 if read-only)
- [x] T042 [US2] Implement error handling for control failures in src/loxone_mcp/mcp/tools.py (component not found, action not supported, Loxone API error)
- [x] T043 [US2] Add command timeout handling (30s) in src/loxone_mcp/loxone/client.py for control operations
- [x] T043a [P] [US2] Write unit tests for US2 in src/tests/unit/test_us2_control_components.py (test control_component Tool, action validation, parameter validation, access control, error handling) - Target: 80% coverage

**Checkpoint**: At this point, User Stories 1 AND 2 should both work - AI can query AND control Loxone components

---

## Phase 5: User Story 3 - Secure Remote Access (Priority: P2)

**Goal**: Enable remote access to MCP server via HTTP+SSE transport with authentication using user credentials passed to Loxone API

**Independent Test**: Connect to MCP server remotely with valid/invalid credentials via HTTP and verify authentication behavior and SSE streaming

**Note**: Core HTTP/SSE transport (T024a-T024d) implemented in Foundation phase. This phase adds remaining remote access features.

### Implementation for User Story 3

- [x] T044 Implement authentication failure handling in src/loxone_mcp/transport/http_sse.py (return 401 Unauthorized with clear error message)
- [x] T044a [P] Add health check endpoint in src/loxone_mcp/transport/http_sse.py (GET /health returns server status)
- [x] T044b [P] [US3] Write integration tests for US3 in src/tests/integration/test_us3_remote_access.py (test HTTP transport, SSE streaming, authentication success/failure, credential passthrough) - Target: 80% coverage

**Checkpoint**: AI systems can now access MCP server remotely with proper authentication

---

## Phase 6: User Story 4 - Monitor Server Health (Priority: P2)

**Goal**: Expose operational metrics at /metrics endpoint for monitoring MCP server health and performance

**Independent Test**: Access /metrics endpoint and verify metrics include request counts, latencies, error rates, connection status, and Loxone integration metrics

### Implementation for User Story 4

- [x] T051 [P] [US4] Create Prometheus metrics collector in src/loxone_mcp/metrics/collector.py (define all metrics: mcp_requests_total, mcp_request_duration, mcp_active_connections, loxone_websocket_connected, loxone_auth_attempts_total, cache_hits/misses)
- [x] T052 [US4] Implement /metrics HTTP endpoint in src/loxone_mcp/transport/http_sse.py (prometheus_client exposition, return metrics in Prometheus format)
- [x] T053 [US4] Add metrics instrumentation to MCP Resource handlers in src/loxone_mcp/mcp/resources.py (increment counters, record durations)
- [x] T054 [US4] Add metrics instrumentation to MCP Tool handlers in src/loxone_mcp/mcp/tools.py (increment counters, record durations, track errors)
- [x] T055 [US4] Add metrics instrumentation to Loxone client in src/loxone_mcp/loxone/client.py (track auth attempts, API call durations, WebSocket status)
- [x] T056 [US4] Add metrics instrumentation to StateCache in src/loxone_mcp/state/cache.py (track cache hits/misses, cache size)
- [x] T057 [US4] Add active connection tracking in src/loxone_mcp/server.py (increment/decrement mcp_active_connections gauge)
- [x] T057a [P] [US4] Write unit tests for US4 in src/tests/unit/test_us4_metrics.py (test metrics collector, instrumentation, /metrics endpoint format) - Target: 80% coverage

**Checkpoint**: /metrics endpoint exposes comprehensive operational metrics for monitoring

---

## Phase 7: User Story 5 - Audit User Actions (Priority: P3)

**Goal**: Generate comprehensive audit logs of all operations with user, action, timestamp, and result for security compliance

**Independent Test**: Perform various read/write operations and verify audit log (logs/audit.jsonl) contains correct entries with all required fields

### Implementation for User Story 5

- [x] T058 [P] [US5] Create audit log writer in src/loxone_mcp/audit/logger.py (write JSON Lines to logs/audit.jsonl with rotation)
- [x] T059 [P] [US5] Define AuditEntry model in src/loxone_mcp/audit/logger.py (timestamp, event_type, user, source_ip, success, details)
- [x] T060 [US5] Implement audit logging for authentication events in src/loxone_mcp/loxone/auth.py (log auth success/failure with username, method)
- [x] T061 [US5] Implement audit logging for control operations in src/loxone_mcp/mcp/tools.py (log control_component calls with user, component_uuid, action, success, duration)
- [x] T062 [US5] Implement audit logging for read operations in src/loxone_mcp/mcp/resources.py (log Resource reads with user, resource URI)
- [x] T063 [US5] Implement audit logging for access denied events in src/loxone_mcp/mcp/resources.py and tools.py (log when read-only/write-only mode blocks operations)
- [x] T064 [US5] Add log file rotation and retention management in src/loxone_mcp/audit/logger.py (daily rotation, keep retention_days from config)
- [x] T065 [US5] Implement sensitive data redaction in audit logs in src/loxone_mcp/audit/logger.py (passwords, full tokens)
- [x] T065a [P] [US5] Write unit tests for US5 in src/tests/unit/test_us5_audit.py (test audit entry creation, log file writing, rotation, sensitive data redaction) - Target: 80% coverage

**Checkpoint**: All operations are fully audited with security compliance details

---

## Phase 8: User Story 6 - Local Operation Mode (Priority: P3)

**Goal**: Enable local stdio transport for AI systems running on the same machine as MCP server without HTTP overhead

**Independent Test**: Run MCP server in stdio mode and verify local AI client can communicate via stdin/stdout without remote transport configuration

### Implementation for User Story 6

- [x] T066 [P] [US6] Implement stdio transport in src/loxone_mcp/transport/stdio.py (read from stdin, write to stdout, MCP JSON-RPC protocol)
- [x] T067 [US6] Add transport selection logic in src/loxone_mcp/server.py (choose stdio, http, or both based on ServerConfig.transport)
- [x] T068 [US6] Implement stdio lifecycle management in src/loxone_mcp/transport/stdio.py (graceful shutdown on EOF)
- [x] T069 [US6] Add stdio notification delivery in src/loxone_mcp/transport/stdio.py (send MCP notifications via stdout)
- [x] T070 [US6] Configure local mode defaults in src/loxone_mcp/config.py (disable HTTP auth requirements for stdio transport)
- [x] T070a [P] [US6] Write integration tests for US6 in src/tests/integration/test_us6_local_mode.py (test stdio transport, lifecycle management, notification delivery) - Target: 80% coverage

**Checkpoint**: Local AI systems can use MCP server via stdio transport with minimal configuration

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories and final deployment readiness

- [x] T071 [P] Create Dockerfile with multi-stage build in docker/Dockerfile (python:3.14-alpine base, <200MB target)
- [x] T072 [P] Create docker-compose.yml example in docker/docker-compose.yml (environment variables, resource limits, security options)
- [x] T073 [P] Create example configuration file in config/example-config.yaml (all settings documented including access_control.mode: 'read-write'|'read-only'|'write-only', structure_cache.change_detection_interval: 300)
- [x] T074 [P] Create .env.example file with required environment variables
- [x] T075 [P] Create README.md with project overview, features, and quick start instructions
- [x] T076 [P] Create GitHub Actions CI workflow in .github/workflows/ci.yml (lint: ruff, type-check: mypy, security: pip-audit + trivy, SBOM: cyclonedx-bom)
- [x] T077 [P] Create GitHub Actions security workflow in .github/workflows/security.yml (trivy container scan, CodeQL)
- [x] T078 [P] Create dependabot configuration in .github/dependabot.yml (pip, github-actions, docker ecosystems)
- [x] T079 Implement graceful shutdown in src/loxone_mcp/server.py (close WebSocket, flush audit logs, stop metrics)
- [x] T080 Add environment variable validation on startup in src/loxone_mcp/config.py (fail fast with clear error messages)
- [x] T081 Add connection retry limits and circuit breaker in src/loxone_mcp/loxone/websocket.py (max 10 failures → require restart)
- [x] T082 Optimize structure file cache memory usage in src/loxone_mcp/state/cache.py (LRU eviction if > 5MB)
- [x] T083 Add request/response logging in development mode in src/loxone_mcp/server.py (LOG_LEVEL=DEBUG)
- [x] T084 Document API contracts in docs/api/ (copy from specs/001-loxone-mcp-server/contracts/)
- [x] T085 Verify quickstart.md instructions work end-to-end (developer setup guide validation)
- [x] T086 Add LICENSE file (select appropriate license)
- [x] T087 Add CONTRIBUTING.md with development guidelines
- [x] T088 [P] Optional: Add TLS/SSL support configuration in src/loxone_mcp/config.py (optional HTTPS via aiohttp ssl_context for production hardening)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Test Infrastructure (Phase 1.5)**: Depends on Setup completion - REQUIRED for TDD workflow per constitution
- **Foundational (Phase 2)**: Depends on Setup + Test Infrastructure - BLOCKS all user stories
- **User Stories (Phase 3-8)**: All depend on Foundational phase completion
  - User stories can proceed in parallel (if staffed)
  - Or sequentially in priority order: US1 (P1 MVP) → US2 (P1) → US3 (P2) → US4 (P2) → US5 (P3) → US6 (P3)
- **Polish (Phase 9)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational - No dependencies on other stories ✅ MVP DELIVERABLE
- **User Story 2 (P1)**: Can start after Foundational - Uses Loxone client from US1 but independently testable
- **User Story 3 (P2)**: Can start after Foundational - HTTP/SSE transport already in Foundation
- **User Story 4 (P2)**: Can start after Foundational - Independent metrics instrumentation, works alongside any story
- **User Story 5 (P3)**: Can start after Foundational - Independent audit logging, works alongside any story
- **User Story 6 (P3)**: Can start after Foundational - Independent transport layer, no dependency on other stories

### Within Each User Story

- Models before services (Foundation phase covered this)
- Services before Tools/Resources (Foundation phase covered this)
- Core Resource/Tool implementation before access control
- Core functionality before error handling enhancements
- Story complete before moving to next priority

### Parallel Opportunities

**Phase 1 (Setup)**: T003, T004, T005, T006, T007 can all run in parallel

**Phase 1.5 (Test Infrastructure)**: T007a, T007b, T007c, T007d, T007e can all run in parallel

**Phase 2 (Foundational)**: 
- T010 (logging), T011 (models), T012 (MCP models) can run in parallel
- T015-T016a (auth + token refresh) run sequentially
- T017-T018 (HTTP client + parser) can run in parallel
- T019-T021 (WebSocket) run sequentially
- T024a (HTTP transport) can start in parallel with auth tasks

**Phase 3 (US1)**: T025, T026, T027, T028, T029, T030, T031, T036a (test task) can all run in parallel (different Resource/Tool handlers)

**Phase 4 (US2)**: T037 can run in parallel with T038-T040, T043a (test task) runs after implementation

**Phase 5 (US3)**: T044, T044a, T044b (test task) can run in parallel

**Phase 6 (US4)**: T051 creates foundation, then T053-T057, T057a (test task) can all run in parallel (instrumenting different modules)

**Phase 7 (US5)**: T058, T059 create foundation, then T060-T063, T065a (test task) can all run in parallel (audit logging in different modules)

**Phase 8 (US6)**: T066 can run in parallel with T067, T070a (test task) runs after implementation

**Phase 9 (Polish)**: T071, T072, T073, T074, T075, T076, T077, T078, T084, T086, T087, T088 can all run in parallel

**Cross-Story Parallelism**: Once Foundation is complete, US1, US3, US4, US5, US6 can start simultaneously (if team capacity allows). US2 should wait for US1's Loxone client to be complete.

---

## Parallel Example: User Story 1

```bash
# After Foundation phase completes, launch all US1 Resource/Tool handlers together:

# Terminal 1: Structure Resource
Implement: "MCP Resource handler for loxone://structure in src/loxone_mcp/mcp/resources.py"

# Terminal 2: Components Resource
Implement: "MCP Resource handler for loxone://components in src/loxone_mcp/mcp/resources.py"

# Terminal 3: Rooms Resource  
Implement: "MCP Resource handler for loxone://rooms in src/loxone_mcp/mcp/resources.py"

# Terminal 4: Categories Resource
Implement: "MCP Resource handler for loxone://categories in src/loxone_mcp/mcp/resources.py"

# Terminal 5: get_component_state Tool
Implement: "MCP Tool get_component_state in src/loxone_mcp/mcp/tools.py"

# Terminal 6: Unit tests in parallel
Implement: "Write unit tests for US1 in src/tests/unit/test_us1_query_states.py"

# Then sequentially: integrate state updates + notifications (T032-T036)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (Tasks T001-T007)
2. Complete Phase 1.5: Test Infrastructure (Tasks T007a-T007e) **TDD FOUNDATION**
3. Complete Phase 2: Foundational (Tasks T008-T024d) **CRITICAL GATE**
4. Complete Phase 3: User Story 1 (Tasks T025-T036a including tests)
5. **STOP and VALIDATE**: Test User Story 1 independently
   - Can AI query all components via loxone://components Resource?
   - Can AI get component states via get_component_state Tool?
   - Do MCP notifications arrive when Loxone states change?
   - Does test suite achieve 80% coverage?
6. **MVP READY**: Deploy/demo read-only AI integration

### Incremental Delivery

1. **Foundation** (Phase 1+1.5+2) → Tasks T001-T024d → Foundation ready with TDD support
2. **MVP** (+ Phase 3: US1) → Add Tasks T025-T036a → Read-only AI working + tests → Deploy/Demo
3. **Core** (+ Phase 4: US2) → Add Tasks T037-T043a → Full read-write control + tests → Deploy/Demo
4. **Production** (+ Phase 5: US3) → Add Tasks T044-T044b → Remote access secured + tests → Deploy/Demo
5. **Observable** (+ Phase 6: US4) → Add Tasks T051-T057a → Monitoring enabled + tests → Deploy/Demo
6. **Compliant** (+ Phase 7: US5) → Add Tasks T058-T065a → Audit logging + tests → Deploy/Demo
7. **Complete** (+ Phase 8: US6) → Add Tasks T066-T070a → Local mode supported + tests → Deploy/Demo
8. **Production-Ready** (+ Phase 9: Polish) → Add Tasks T071-T088 → Container + CI/CD → Final Release

Each increment adds value without breaking previous functionality.

### Parallel Team Strategy

With 3 developers after Foundation completes:

- **Developer A**: User Story 1 (Tasks T025-T036a) → MVP with tests
- **Developer B**: User Story 3 (Tasks T044-T044b) → Remote transport with tests
- **Developer C**: User Story 4 (Tasks T051-T057a) → Metrics with tests

Then converge for integration testing.

---

## Summary

- **Total Tasks**: 98 tasks across 10 phases (includes test infrastructure and test tasks per TDD constitution requirement)
- **MVP Tasks**: 46 tasks (Setup + Test Infrastructure + Foundation + US1) → Tasks T001-T036a
- **Core Functionality**: +8 tasks (US2) → Tasks T037-T043a
- **Production Readiness**: +3 tasks (US3) → Tasks T044-T044b
- **Parallel Tasks**: 40+ tasks marked [P] can run in parallel within their phase
- **Independent Stories**: 6 user stories, each independently testable with dedicated test tasks
- **Test Coverage**: 80% minimum per Constitution Principle IV (Test-First Development)
- **Estimated Timeline**: 
  - MVP (Phases 1-3): 3 weeks (includes test infrastructure and TDD workflow)
  - Core (+ Phase 4): +1 week
  - Production (+ Phases 5-6): +1.5 weeks
  - Complete (+ Phases 7-9): +1.5 weeks
  - **Total: 7 weeks to production-ready with full test coverage**

---

**Task List Version**: 2.0  
**Generated**: 2026-02-10  
**Updated**: 2026-02-10 (Added TDD infrastructure, resolved specification analysis findings)  
**Status**: Ready for implementation with constitution compliance
