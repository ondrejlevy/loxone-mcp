# Feature Specification: Loxone MCP Server for AI Integration

**Feature Branch**: `001-loxone-mcp-server`  
**Created**: 10 February 2026  
**Status**: Draft  
**Input**: User description: "cilem je vytvorit MCP server pro integraci AI k Loxone miniserveru. Na strane Loxone miniserveru je mozne jeho bezne API. Dokumentaci je mozne najit na webu Loxone. MCP server by mel implementovat jak read operace tak i write. Mel by umoznovat dotazovat na stav jednotlivych komponent, filtrovat podle mistnosti nebo typu. mel by umoznosvat ovladat jednotlive komponenty. Tz zapinat/vypinat svetla, prepinat switche atd.. Malo by byt mozne pro MCP nastavit zde umoznuje pouze ready nebo write operace. MCP by mel podporovat jak lokalni provoz tak sse a http transport. Autorizace pro remote transporty by mela byt mozna predat pres http hlavicky. pro autorizaci by se mela pouzit konkretni identita uzivatele s jeho jmenem a heslem a tyto prihlasovaci udaje by se meli pouzit pro volani loxone api. aplikace by mela o sobe vystavovat /metric endpoint s internimi metrikami pro moznost monitoringu samotneho MCP serveru. apliakce by mela generovat auditni log s informacemi o uzivateli a provedene akci"

## Clarifications

### Session 2026-02-10

- Q: The MCP protocol defines three core primitives for exposing functionality: Tools (executable functions), Resources (data sources for context), and Prompts (interaction templates). For querying Loxone component states, which architectural approach should the MCP server use? → A: Use both Resources for queries (component lists, room info) and Tools for actions (get_component_state, control_component) - hybrid approach
- Q: Looking at the Loxone API documentation, the miniserver provides real-time state updates via WebSocket connections. The MCP protocol supports real-time notifications (like notifications/resources/list_changed or notifications/resources/updated). How should the MCP server handle real-time component state changes from Loxone? → A: Server sends MCP notification messages when Loxone component states change, triggering clients to refresh affected Resources
- Q: The Loxone API documentation shows multiple authentication methods: Token-based authentication (with token refresh), basic HTTP authentication, and hash-based authentication. Which Loxone authentication method should the MCP server use when connecting to the Loxone miniserver? → A: Multi-tier fallback strategy: (1) Token-based via WebSocket with RSA+AES encryption (getjwt/gettoken) for firmware ≥9.x, (2) Token-based via HTTP if WebSocket fails, (3) Hash-based auth for legacy firmware 8.x. Full protocol: RSA-2048 public key exchange, AES-256-CBC session encryption, HMAC-SHA256 password hashing, JWT token retrieval with fallback to gettoken for older firmware
- Q: The Loxone API structure file contains the complete system configuration including all controls, rooms, categories, and their relationships. This is a relatively large data structure that changes infrequently. How should the MCP server expose the Loxone structure file data? → A: Load structure file once at startup, cache parsed data, send MCP notifications when structure changes detected (balances performance with freshness)
- Q: The original requirements mentioned configuring the MCP server to allow "only read or write operations". What level of access control granularity should the MCP server support? → A: Server-wide configuration - entire server operates in either read-only, write-only, or read-write mode

## User Scenarios & Testing

### User Story 1 - Query Component States (Priority: P1)

AI systems need to understand the current state of home automation components (lights, switches, sensors) to provide accurate responses and make informed decisions. This includes viewing all components or filtering by specific rooms or component types through MCP Resources and Tools.

**Why this priority**: This is the foundation capability - AI systems must be able to read current states before they can effectively control or reason about the smart home system. This is the minimum viable functionality.

**Independent Test**: Can be fully tested by querying MCP Resources (component lists, structure data) and calling MCP Tools (get component states) to verify returned data matches actual Loxone miniserver states. Delivers immediate value for read-only AI assistants and monitoring use cases.

**Acceptance Scenarios**:

1. **Given** the MCP server is connected to a Loxone miniserver with multiple components, **When** AI system reads MCP Resources or calls query Tools, **Then** system returns complete list of components with their current states (on/off, values, etc.)

2. **Given** a Loxone miniserver with components organized by rooms, **When** AI system queries MCP Resources filtered by "Living Room", **Then** system returns only components associated with that room

3. **Given** a Loxone miniserver with various component types (lights, switches, sensors), **When** AI system queries MCP Resources filtered by type "light", **Then** system returns only light components with their current states

4. **Given** a component state changes in Loxone miniserver, **When** AI system receives MCP notification and re-reads affected Resource, **Then** system returns the updated current state

---

### User Story 2 - Control Components (Priority: P1)

AI systems need to control home automation components based on user commands or automation rules. This includes turning lights on/off, toggling switches, and setting component values through MCP Tools.

**Why this priority**: This completes the core read-write capability loop, enabling AI to not just observe but also act on the smart home system. Required for any useful AI assistant functionality.

**Independent Test**: Can be tested independently by calling MCP control Tools and verifying Loxone components change states accordingly. Delivers complete AI control functionality.

**Acceptance Scenarios**:

1. **Given** MCP server is configured in read-write mode, **When** AI system calls control Tool to turn on a light, **Then** the light turns on in the Loxone system and MCP Tool returns successful execution

2. **Given** a switch component in Loxone system, **When** AI system calls toggle Tool, **Then** switch changes to opposite state and MCP Tool returns new state

3. **Given** a dimmable light component, **When** AI system calls control Tool to set brightness to 50%, **Then** light adjusts to 50% brightness in Loxone system

4. **Given** MCP server is configured in read-only mode, **When** AI system attempts to call control Tool, **Then** MCP server rejects the request with clear error message indicating read-only mode

---

### User Story 3 - Secure Remote Access (Priority: P2)

System administrators and AI systems need to access the MCP server remotely over HTTP or SSE transports with proper authentication using specific user credentials that are passed through to the Loxone API.

**Why this priority**: Essential for production deployments where AI systems run on different machines or cloud services. Enables secure multi-user access with proper identity tracking.

**Independent Test**: Can be tested by connecting to MCP server remotely with valid/invalid credentials and verifying authentication behavior. Delivers secure remote access capability.

**Acceptance Scenarios**:

1. **Given** MCP server is configured for remote access via HTTP, **When** client connects with valid username and password in HTTP headers, **Then** client is authenticated and can access MCP server functions

2. **Given** MCP server receives authenticated request, **When** MCP server calls Loxone API, **Then** request includes the original user's credentials for authorization

3. **Given** client attempts to connect with invalid credentials, **When** authentication is validated, **Then** MCP server rejects connection with appropriate error message

4. **Given** MCP server is configured for HTTP transport with SSE, **When** client establishes connection with authentication headers, **Then** client receives MCP notification messages when Loxone component states change

---

### User Story 4 - Monitor Server Health (Priority: P2)

System administrators need to monitor the MCP server's operational health, performance metrics, and connection status to ensure reliable AI integration services.

**Why this priority**: Critical for production operations and troubleshooting, but system can function without monitoring initially. Enables proactive issue detection and performance optimization.

**Independent Test**: Can be tested by accessing /metrics endpoint and verifying metrics are correctly exposed. Delivers operational visibility independent of core MCP functionality.

**Acceptance Scenarios**:

1. **Given** MCP server is running, **When** administrator accesses /metrics endpoint, **Then** system returns metrics in standard format including request counts, response times, error rates, and connection status

2. **Given** MCP server experiences errors communicating with Loxone miniserver, **When** administrator checks metrics, **Then** metrics reflect error counts and failed connection attempts

3. **Given** monitoring system is configured to scrape /metrics endpoint, **When** MCP server processes requests, **Then** monitoring system receives updated metrics at regular intervals

---

### User Story 5 - Audit User Actions (Priority: P3)

System administrators need comprehensive audit logs of all operations performed through the MCP server, including which user performed which action and the outcome, for security compliance and troubleshooting.

**Why this priority**: Important for security and compliance, but not required for basic functionality. Can be added after core features are working.

**Independent Test**: Can be tested by performing various operations and verifying audit log entries contain correct user, action, timestamp, and result information. Delivers compliance and security tracking capability.

**Acceptance Scenarios**:

1. **Given** authenticated user performs a read operation, **When** operation completes, **Then** audit log records timestamp, username, action type (read), target component, and success/failure status

2. **Given** authenticated user performs a write operation, **When** operation completes, **Then** audit log records timestamp, username, action type (write), target component, command details, and success/failure status

3. **Given** authentication attempt fails, **When** failure is detected, **Then** audit log records timestamp, attempted username, and failure reason

4. **Given** administrator reviews audit logs, **When** filtering by username, **Then** all actions performed by that user are displayed in chronological order

---

### User Story 6 - Local Operation Mode (Priority: P3)

Developers and users running AI systems on the same network as the Loxone miniserver need to use the MCP server in local mode without remote transport overhead for reduced latency and simplified setup.

**Why this priority**: Useful for development and simple local deployments, but remote access is more common for production AI systems.

**Independent Test**: Can be tested by running MCP server in local mode and verifying it communicates with local Loxone miniserver without transport protocols. Delivers simplified local deployment option.

**Acceptance Scenarios**:

1. **Given** MCP server is configured for local operation, **When** local AI system connects, **Then** connection is established without requiring HTTP/SSE transport configuration

2. **Given** MCP server is in local mode, **When** operations are performed, **Then** latency is minimal compared to remote transport modes

3. **Given** developer is testing integration, **When** using local mode, **Then** no authentication headers or remote configuration is required

---

### Edge Cases

- What happens when Loxone miniserver becomes unreachable during an operation?
- How does system handle conflicting write operations from multiple AI clients?
- What happens when authentication credentials for Loxone API become invalid?
- How does system behave when MCP server is configured for read-only but receives write commands?
- What happens when component identifiers in requests don't match any existing Loxone components?
- How are partial failures handled when batch operations are requested?
- What happens when network connection is lost during SSE streaming?

## MCP Protocol Architecture

### Exposed MCP Resources (Data Sources)

The server will expose the following MCP Resources for contextual data queries:

- **loxone://structure** - Complete Loxone structure file data (cached, updated on changes)
- **loxone://components** - List of all components with metadata
- **loxone://rooms** - List of all rooms with assigned components
- **loxone://categories** - List of component categories/types

### Exposed MCP Tools (Executable Functions)

The server will expose the following MCP Tools for operations:

- **get_component_state** - Query current state of specific component(s)
- **control_component** - Execute control command on component (on/off, toggle, set value)
- **get_room_components** - List all components in specific room with current states
- **get_components_by_type** - List all components of specific type with current states

### MCP Notifications

The server will send MCP notifications for:

- **notifications/resources/updated** - When Loxone structure file changes
- **notifications/resources/updated** - When component states change (includes affected resource URIs)

### Transport Support

- **stdio** - Local transport for same-machine MCP clients
- **HTTP with SSE** - Remote transport (Streamable HTTP) with Server-Sent Events for streaming

## Requirements

### Functional Requirements

- **FR-001**: System MUST connect to Loxone miniserver using standard Loxone API
- **FR-002**: System MUST expose MCP Resources for contextual data queries (component lists, room information, structure file data)
- **FR-003**: System MUST expose MCP Tools for executable operations (querying specific component states, controlling components)
- **FR-004**: System MUST support filtering component queries by room identifier
- **FR-005**: System MUST support filtering component queries by component type
- **FR-006**: System MUST support write operations to control component states (on/off, toggle, set values)
- **FR-007**: System MUST provide server-wide configuration to set operation mode: read-only, write-only, or read-write
- **FR-008**: System MUST enforce configured access control mode globally across all clients and requests
- **FR-009**: System SHOULD support stdio transport for local operation mode
- **FR-010**: System MUST support HTTP transport for remote access (Streamable HTTP as per MCP specification)
- **FR-011**: System MUST support Server-Sent Events (SSE) for streaming updates via HTTP transport
- **FR-012**: System MUST accept authentication credentials via HTTP headers for remote transports
- **FR-013**: System MUST use provided user credentials when authenticating to Loxone API
- **FR-014**: System MUST implement multi-tier Loxone authentication with fallback strategy: primary token-based via WebSocket (RSA+AES), fallback token-based via HTTP, legacy hash-based for firmware 8.x
- **FR-015**: System MUST support RSA-2048 public key exchange and AES-256-CBC session encryption for modern Loxone firmware
- **FR-016**: System MUST support JWT token retrieval (getjwt) with fallback to gettoken for older firmware versions
- **FR-017**: System MUST handle token refresh automatically for long-running connections
- **FR-018**: System MUST expose /metrics endpoint with internal operational metrics
- **FR-019**: System MUST include in metrics: request count, response times, error rates (total errors counter + per-tool error counters with labels: tool_name, error_type), and active connections
- **FR-020**: System MUST generate audit log entries for all operations
- **FR-021**: System MUST record in audit logs: timestamp, username, action type, target component, and operation result
- **FR-022**: System MUST record failed authentication attempts in audit logs
- **FR-023**: System MUST return clear error messages when operations fail
- **FR-024**: System MUST validate component UUIDs before attempting operations (format validation + existence check)
- **FR-025**: System MUST handle network failures gracefully with appropriate retry logic
- **FR-026**: System MUST prevent write operations when configured in read-only mode
- **FR-027**: System MUST return component metadata including type, room assignment, and available operations
- **FR-028**: System MUST support querying list of all available rooms
- **FR-029**: System MUST support querying list of all available component types
- **FR-030**: System MUST implement MCP lifecycle management (initialization, capability negotiation)
- **FR-031**: System MUST establish WebSocket connection to Loxone miniserver for receiving real-time state updates
- **FR-032**: System MUST send MCP notification messages to connected clients when component states change in Loxone
- **FR-033**: System MUST support MCP notifications capability in server initialization response
- **FR-034**: System MUST retrieve and parse Loxone structure file on startup
- **FR-035**: System MUST cache parsed structure file data in memory for fast access
- **FR-036**: System MUST detect Loxone structure file changes and reload cached data when changes occur
- **FR-037**: System MUST send MCP resource update notifications to clients when structure file changes

### Key Entities

- **Component**: Represents a controllable or queryable element in the Loxone system (light, switch, sensor, dimmer). Key attributes: identifier, type, current state, room assignment, available operations, display name.

- **Room**: Represents a physical space grouping for components. Key attributes: identifier, display name, list of assigned components.

- **User**: Represents an authenticated entity making requests through the MCP server. Key attributes: username, authentication credentials (for Loxone API passthrough). Note: Access permissions are server-wide, not per-user.

- **Operation**: Represents an action performed through the MCP server. Key attributes: operation type (read/write), target component, timestamp, requesting user, parameters, result status.

- **Structure File Cache**: Represents cached Loxone structure file data. Key attributes: parsed component tree, room definitions, category mappings, last update timestamp, version hash.

- **MCP Resource**: Represents an MCP protocol resource exposed to clients. Key attributes: resource URI, content type, cached data, last modified timestamp.

- **Metrics Snapshot**: Represents current operational health data. Key attributes: request counts, average response times, error rates, active connections, last update timestamp.

- **Audit Entry**: Represents a logged operation for compliance and troubleshooting. Key attributes: timestamp, username, action type, target component, command details, success/failure status, error message if applicable.

## Success Criteria

### Measurable Outcomes

- **SC-001**: AI systems can successfully query component states and receive responses within 1 second under normal network conditions
- **SC-002**: AI systems can successfully control components with state changes reflected in Loxone system within 2 seconds
- **SC-003**: System maintains 99% uptime during continuous operation over 7-day period
- **SC-004**: System correctly handles 100 concurrent read operations without errors or significant performance degradation
- **SC-005**: Authentication failures are detected and rejected within 500 milliseconds
- **SC-006**: Metrics endpoint responds with current data within 200 milliseconds
- **SC-007**: Audit logs capture 100% of operations with complete required information
- **SC-008**: System successfully recovers from temporary Loxone miniserver disconnections without manual intervention
- **SC-009**: MCP notifications for component state changes are sent to connected clients within 1 second of changes occurring in Loxone system
- **SC-010**: Configuration changes between read-only, write-only, and read-write modes take effect without requiring system restart
- **SC-011**: Structure file cache updates complete within 5 seconds of Loxone configuration changes

## Assumptions

- Loxone miniserver firmware versions 8.x through 9.x+ are supported with appropriate authentication fallback mechanisms
- Loxone API supports WebSocket connections for real-time state updates and token-based authentication
- Network latency between MCP server and Loxone miniserver is typically under 100ms for local deployments
- Metrics format will be compatible with standard monitoring tools
- Audit log entries will use a structured, machine-readable format
- Component identifiers from Loxone API are stable and don't change during normal operation
- Loxone structure file provides notification mechanism for configuration changes
- MCP client applications support JSON-RPC 2.0 protocol as specified by MCP
- Loxone API provides real-time or near-real-time component state information
- Maximum expected concurrent clients is under 50 for initial deployment
- Audit logs will be managed by external log aggregation system (rotation and retention handled externally)

## Dependencies

- Access to Loxone miniserver with valid credentials
- Network connectivity between MCP server and Loxone miniserver
- Loxone API documentation for integration reference
- Available libraries supporting HTTP and SSE communication protocols

## Out of Scope

- Graphical user interface for MCP server administration
- Direct integration with specific AI platforms (server is platform-agnostic)
- Component grouping or scene management beyond Loxone's native capabilities
- Historical data storage or analysis
- Complex scheduling or automation rules (relies on AI system to implement logic)
- Multi-Loxone-system support (single miniserver per MCP server instance)
- Authentication mechanism other than username/password passthrough
- Real-time streaming of all state changes (SSE provides notification mechanism, not full state streaming)
- Automatic discovery of Loxone miniserver on network
- Configuration management UI (configuration via files or environment variables)
