# Testing Strategy: Loxone MCP Server

## Overview

This test suite follows **Test-First Development** (Constitution Principle IV) targeting **80% minimum code coverage**.

## Test Categories

### Unit Tests (`tests/unit/`)
- **Scope**: Individual functions and classes in isolation
- **Speed**: Fast (~1ms per test)
- **Dependencies**: Mocked (no network, no filesystem)
- **Naming**: `test_<module>_<function>_<scenario>`
- **Files**:
  - `test_us1_query_states.py` - Resource handlers, query Tools
  - `test_us2_control_components.py` - Control Tool, validations
  - `test_us4_metrics.py` - Metrics collector, instrumentation  
  - `test_us5_audit.py` - Audit logging, rotation, redaction

### Integration Tests (`tests/integration/`)
- **Scope**: Multiple components working together
- **Speed**: Moderate (~100ms per test)
- **Dependencies**: Mock external services (Loxone API), real internal wiring
- **Files**:
  - `test_us3_remote_access.py` - HTTP transport, auth, SSE
  - `test_us6_local_mode.py` - stdio transport, lifecycle

### Contract Tests (`tests/contract/`)
- **Scope**: MCP protocol compliance, JSON-RPC validation
- **Speed**: Fast
- **Dependencies**: None (pure schema validation)
- **Files**:
  - `test_mcp_protocol.py` - JSON-RPC, Resource/Tool schema checks

## Fixtures (`tests/fixtures/`)
- `loxone_structure_file.json` - Mock Loxone miniserver structure
- `loxone_responses.py` - Factory functions for mock API responses

## Mocking Approach

### Loxone API (External)
- Use `MockWebSocket` class (see `conftest.py`) for WebSocket connections
- Use `MockHTTPSession` class for HTTP API calls
- Queue specific responses for each test scenario

### MCP Protocol (Internal)  
- Use the MCP SDK's test client where available
- Validate JSON-RPC messages against schema
- Test notification delivery via mock transport

## Running Tests

```bash
# All tests
pytest

# Unit tests only
pytest src/tests/unit/ -m unit

# Integration tests
pytest src/tests/integration/ -m integration

# Contract tests
pytest src/tests/contract/ -m contract

# With coverage report
pytest --cov=loxone_mcp --cov-report=html

# Specific user story
pytest -k "us1"
```

## Coverage Goals

| Module | Target | Notes |
|--------|--------|-------|
| `mcp/resources.py` | 90% | Critical path |
| `mcp/tools.py` | 90% | Critical path |
| `loxone/auth.py` | 85% | All 3 auth tiers |
| `loxone/websocket.py` | 80% | Reconnection logic |
| `state/cache.py` | 85% | Thread safety |
| `config.py` | 80% | Validation paths |
| **Overall** | **80%** | **Minimum** |
