# Quickstart Guide: Loxone MCP Server

**Date**: 2026-02-10  
**Phase**: Phase 1 - Design  
**Audience**: Developers

This guide helps developers quickly set up a local development environment for the Loxone MCP Server.

## Prerequisites

### Required Software

- **Python 3.14** (installed and in PATH)
- **Docker** (v20.10+) or Podman
- **docker-compose** (v2.0+) or podman-compose
- **Git** (for cloning repository)
- **Make** (optional, for shortcuts)

### Loxone Requirements

- **Loxone Miniserver** (firmware 8.x or 9.x+)
- **Network Access**: Miniserver accessible from development machine
- **Credentials**: Username and password with sufficient permissions

### Recommended Tools

- **VS Code** with Python extension
- **Postman** or **curl** for API testing
- **MCP Inspector** (for testing MCP protocol)

---

## Quick Start (5 minutes)

### 1. Clone Repository

```bash
git clone https://github.com/your-org/loxone-mcp.git
cd loxone-mcp
```

### 2. Set Up Python Environment

```bash
# Create virtual environment
python3.14 -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # macOS/Linux
# or
.venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 3. Configure Loxone Connection

Create `.env` file in project root:

```bash
# Loxone Miniserver
LOXONE_HOST=192.168.1.10
LOXONE_PORT=80
LOXONE_USE_TLS=false
LOXONE_USERNAME=admin
LOXONE_PASSWORD=your_password

# MCP Server
MCP_HOST=0.0.0.0
MCP_PORT=8080
MCP_TRANSPORT=http

# Access Control
ACCESS_MODE=read-write

# Logging
LOG_LEVEL=INFO
```

**⚠️ Security**: Never commit `.env` to version control! Add to `.gitignore`.

### 4. Run Server (Development Mode)

```bash
# Run directly
python -m loxone_mcp

# Or with auto-reload (needs watchfiles)
python -m watchfiles 'python -m loxone_mcp' src/
```

**Output**:
```
2026-02-10 14:30:00 [INFO] loxone_mcp.server: Starting Loxone MCP Server v1.0.0
2026-02-10 14:30:00 [INFO] loxone_mcp.loxone.client: Connecting to Loxone at 192.168.1.10:80
2026-02-10 14:30:01 [INFO] loxone_mcp.loxone.auth: Authentication successful (token-based)
2026-02-10 14:30:02 [INFO] loxone_mcp.loxone.structure: Structure file loaded (256 components)
2026-02-10 14:30:02 [INFO] loxone_mcp.mcp.server: MCP server listening on http://0.0.0.0:8080
2026-02-10 14:30:02 [INFO] loxone_mcp.metrics: Metrics available at http://0.0.0.0:8080/metrics
```

### 5. Test MCP Resources

```bash
# Check server health
curl http://localhost:8080/health

# Get structure file (MCP Resource)
curl http://localhost:8080/mcp/resources/loxone://structure

# Get components list
curl http://localhost:8080/mcp/resources/loxone://components

# Check metrics
curl http://localhost:8080/metrics
```

### 6. Test MCP Tools

```bash
# Get component state
curl -X POST http://localhost:8080/mcp/tools/get_component_state \
  -H "Content-Type: application/json" \
  -d '{"component_uuid": "0f1e2c44-0004-1a2b-ffff403fb0c34b9e"}'

# Control component (turn on light)
curl -X POST http://localhost:8080/mcp/tools/control_component \
  -H "Content-Type: application/json" \
  -d '{
    "component_uuid": "0f1e2c44-0004-1a2b-ffff403fb0c34b9e",
    "action": "On"
  }'
```

**Success!** ✅ Server is running and responding to MCP requests.

---

## Configuration Options

### Configuration File (Alternative to .env)

Create `config/config.yaml`:

```yaml
server:
  name: loxone-mcp
  version: 1.0.0
  host: 0.0.0.0
  port: 8080
  transport: http  # 'stdio', 'http', or 'both'

loxone:
  host: 192.168.1.10
  port: 80
  use_tls: false
  username: admin
  password: your_password
  reconnect_interval: 5
  max_reconnect_attempts: 10
  connection_timeout: 10
  command_timeout: 30

access_control:
  mode: read-write  # 'read-only', 'write-only', or 'read-write'

metrics:
  enabled: true
  endpoint: /metrics
  include_loxone_metrics: true

audit:
  enabled: true
  log_file: logs/audit.jsonl
  retention_days: 90
  log_authentication: true
  log_control_commands: true
  log_config_changes: true

# Cache TTL in seconds
structure_cache_ttl: 3600
```

**Run with config file**:
```bash
python -m loxone_mcp --config config/config.yaml
```

---

## Running Tests

### Unit Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/loxone_mcp --cov-report=html

# Open coverage report
open htmlcov/index.html  # macOS
# or
start htmlcov/index.html  # Windows
```

### Integration Tests

```bash
# Requires running Loxone miniserver (or mock)
pytest tests/integration/

# With mock Loxone server
LOXONE_MOCK_MODE=true pytest tests/integration/
```

### Specific Test Files

```bash
# Test authentication
pytest tests/unit/test_loxone_auth.py -v

# Test MCP resources
pytest tests/unit/test_mcp_resources.py -v

# Test state management
pytest tests/unit/test_state_manager.py -v
```

### Type Checking

```bash
# Run mypy
mypy src/loxone_mcp

# Strict mode
mypy --strict src/loxone_mcp
```

### Linting

```bash
# Run ruff
ruff check src/

# Auto-fix
ruff check --fix src/

# Format code
ruff format src/
```

---

## Docker Development

### Build Container

```bash
# Build image
docker build -f docker/Dockerfile -t loxone-mcp:dev .

# Check image size
docker images loxone-mcp:dev
```

**Expected size**: ~135-155MB

### Run Container (Development)

```bash
# Run with environment variables
docker run --rm -it \
  -p 8080:8080 \
  -e LOXONE_HOST=192.168.1.10 \
  -e LOXONE_USERNAME=admin \
  -e LOXONE_PASSWORD=your_password \
  loxone-mcp:dev

# Run with config file mounted
docker run --rm -it \
  -p 8080:8080 \
  -v $(pwd)/config/config.yaml:/app/config.yaml:ro \
  loxone-mcp:dev
```

### Run with docker-compose

Create `docker-compose.dev.yml`:

```yaml
version: '3.8'

services:
  loxone-mcp:
    build:
      context: .
      dockerfile: docker/Dockerfile
    image: loxone-mcp:dev
    container_name: loxone-mcp-dev
    ports:
      - "8080:8080"
    env_file:
      - .env
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

**Start services**:
```bash
docker-compose -f docker-compose.dev.yml up -d

# View logs
docker-compose -f docker-compose.dev.yml logs -f

# Stop services
docker-compose -f docker-compose.dev.yml down
```

---

## Development Workflow

### 1. Create Feature Branch

```bash
git checkout -b feature/my-new-feature
```

### 2. Make Changes

Edit files in `src/loxone_mcp/`

### 3. Run Tests

```bash
pytest
ruff check src/
mypy src/loxone_mcp
```

### 4. Commit Changes

```bash
git add .
git commit -m "feat: add new feature"
```

### 5. Push and Create Pull Request

```bash
git push origin feature/my-new-feature
```

Then create PR on GitHub.

---

## Debugging

### VS Code Launch Configuration

Create `.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: Loxone MCP Server",
      "type": "python",
      "request": "launch",
      "module": "loxone_mcp",
      "console": "integratedTerminal",
      "envFile": "${workspaceFolder}/.env",
      "justMyCode": false
    }
  ]
}
```

**Set breakpoints** in code and press F5 to debug.

### Logging Configuration

Set `LOG_LEVEL=DEBUG` in `.env` for verbose output:

```bash
LOG_LEVEL=DEBUG python -m loxone_mcp
```

**Output includes**:
- WebSocket messages (redacted)
- State update events
- MCP protocol exchanges
- Cache operations

### Common Issues

**Issue: "Connection refused" to Loxone**
- **Solution**: Check `LOXONE_HOST` is correct and miniserver is reachable (`ping 192.168.1.10`)

**Issue: "Authentication failed"**
- **Solution**: Verify credentials, check Loxone user permissions

**Issue: "Port 8080 already in use"**
- **Solution**: Change `MCP_PORT` to different port (e.g., 8081)

**Issue: "Module not found: mcp"**
- **Solution**: Install dependencies (`pip install -r requirements.txt`)

---

## Testing with MCP Clients

### MCP Inspector (Recommended)

```bash
# Install MCP Inspector
npm install -g @modelcontextprotocol/inspector

# Test server
mcp-inspector http://localhost:8080
```

### Claude Desktop (MCP Client)

Add to Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "loxone": {
      "command": "python",
      "args": ["-m", "loxone_mcp"],
      "env": {
        "LOXONE_HOST": "192.168.1.10",
        "LOXONE_USERNAME": "admin",
        "LOXONE_PASSWORD": "your_password"
      }
    }
  }
}
```

Restart Claude Desktop and test:
- "Query all Loxone components"
- "Turn on living room light"
- "Get state of component <UUID>"

---

## Performance Profiling

### Profile with cProfile

```bash
python -m cProfile -o profile.stats -m loxone_mcp

# Analyze results
python -m pstats profile.stats
```

### Memory Profiling

```bash
pip install memray

memray run -m loxone_mcp
memray flamegraph memray-*.bin
```

---

## Next Steps

After completing quickstart:

1. **Read contracts**: Review [contracts/](contracts/) for API specifications
2. **Read data model**: Understand [data-model.md](data-model.md)
3. **Review implementation plan**: See [plan.md](plan.md) for architecture
4. **Contribute**: Check [../../../CONTRIBUTING.md](../../../CONTRIBUTING.md) for guidelines

---

## Useful Commands Cheatsheet

```bash
# Start server
python -m loxone_mcp

# Run tests
pytest

# Lint code
ruff check src/

# Type check
mypy src/loxone_mcp

# Build Docker image
docker build -f docker/Dockerfile -t loxone-mcp:dev .

# Run container
docker run --rm -it -p 8080:8080 --env-file .env loxone-mcp:dev

# Check metrics
curl http://localhost:8080/metrics

# Check audit logs
tail -f logs/audit.jsonl | jq
```

---

## Support

- **Issues**: https://github.com/your-org/loxone-mcp/issues
- **Discussions**: https://github.com/your-org/loxone-mcp/discussions
- **Documentation**: https://docs.your-org.com/loxone-mcp

---

**Quickstart Version**: 1.0  
**Last Updated**: 2026-02-10  
**Status**: Complete
