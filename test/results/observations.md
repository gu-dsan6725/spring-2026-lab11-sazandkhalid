# Task 3: A2A Communication Observations

## A2A Messages Exchanged Between Agents

### Step 1: User → Travel Assistant (A2A JSON-RPC Request)

The test client sends a booking request to the Travel Assistant using the A2A `message/send` method:

```json
{
  "jsonrpc": "2.0",
  "id": "test-book",
  "method": "message/send",
  "params": {
    "message": {
      "role": "user",
      "parts": [{"kind": "text", "text": "I want to book flight ID 1. You don't have these booking capabilities yourself, so find and use an agent that can handle flight reservations."}],
      "messageId": "msg-book-001"
    }
  }
}
```

### Step 2: Travel Assistant → Registry Stub (Discovery HTTP Request)

The Travel Assistant queries the registry stub at `http://127.0.0.1:7861` via HTTP POST:

```
POST /api/agents/discover/semantic?query=book+flights&max_results=5
```

The registry returns the Flight Booking Agent entry:

```json
{
  "query": "book flights",
  "agents": [{
    "name": "Flight Booking Agent",
    "description": "Flight booking and reservation management agent",
    "path": "/flight-booking-agent",
    "url": "http://127.0.0.1:10002",
    "tags": ["booking", "flights", "reservations"],
    "skills": [
      {"id": "check_availability", "name": "check_availability", "description": "Check seat availability for a specific flight."},
      {"id": "reserve_flight", "name": "reserve_flight", "description": "Reserve seats on a flight for passengers."},
      {"id": "confirm_booking", "name": "confirm_booking", "description": "Confirm and finalize a flight booking."},
      {"id": "process_payment", "name": "process_payment", "description": "Process payment for a booking (simulated)."},
      {"id": "manage_reservation", "name": "manage_reservation", "description": "Update, view, or cancel existing reservations."}
    ],
    "is_enabled": true,
    "trust_level": "verified",
    "relevance_score": 0.95
  }]
}
```

### Step 3: Travel Assistant → Flight Booking Agent (A2A JSON-RPC)

After discovering the Flight Booking Agent, the Travel Assistant sends an A2A message to `http://127.0.0.1:10002/`:

```json
{
  "jsonrpc": "2.0",
  "id": "request-abc123",
  "method": "message/send",
  "params": {
    "message": {
      "role": "user",
      "parts": [{"kind": "text", "text": "Check availability for flight ID 1"}],
      "messageId": "msg-flight-check-001"
    }
  }
}
```

### Step 4: Flight Booking Agent → Travel Assistant (A2A JSON-RPC Response)

The Flight Booking Agent responds with a completed task containing artifacts:

```json
{
  "id": "request-abc123",
  "jsonrpc": "2.0",
  "result": {
    "artifacts": [{
      "artifactId": "8baad45b-a14f-4821-8d18-8ce7f82e3d5c",
      "name": "agent_response",
      "parts": [{"kind": "text", "text": "Flight ID 1 is available with 84 seats at $250 per seat. Status: Available. Booking confirmed. Your booking number is BK-123456."}]
    }],
    "contextId": "7382a825-a247-47ba-9677-866d64be8530",
    "id": "e455e0e0-b1c8-40d9-a756-4194fb929f62",
    "kind": "task",
    "status": {"state": "completed", "timestamp": "2026-04-24T04:07:21.240136+00:00"}
  }
}
```

---

## How the Travel Assistant Discovered the Flight Booking Agent

Discovery happened in three steps:

1. **Trigger**: The Travel Assistant received a user request requiring flight booking capabilities it does not have itself. Its `discover_remote_agents` tool was invoked with the query `"book flights"`.

2. **Registry Query**: The Travel Assistant sent an HTTP POST to the Registry Stub at `http://127.0.0.1:7861/api/agents/discover/semantic?query=book+flights&max_results=5`. The registry stub (which simulates a semantic search service) returned the Flight Booking Agent's metadata — including its URL, skills, tags, and trust level.

3. **Caching**: The discovered agent was stored in the Travel Assistant's `RemoteAgentCache` under the key `/flight-booking-agent`. This lets the LLM subsequently call `invoke_remote_agent("/flight-booking-agent", message)` without re-querying the registry.

The discovery flow observed in the registry log:
```
Semantic search request: query='book flights', max_results=5
Returning canned response: Flight Booking Agent
```

---

## JSON-RPC Request/Response Format Observed

The A2A protocol uses **JSON-RPC 2.0** as its transport layer. Key elements observed:

| Field | Description | Example |
|-------|-------------|---------|
| `jsonrpc` | Protocol version | `"2.0"` |
| `id` | Correlation ID matching request to response | `"test-953ff005"` |
| `method` | Always `"message/send"` for agent messaging | `"message/send"` |
| `params.message.role` | Sender role | `"user"` |
| `params.message.parts` | Array of content blocks with `kind` and `text` | `[{"kind":"text","text":"..."}]` |
| `result.artifacts` | Final consolidated response content | Array with `parts` |
| `result.history` | Full conversation turn history | Array of messages |
| `result.status.state` | Task completion status | `"completed"` |
| `result.kind` | Always `"task"` — A2A models interactions as tasks | `"task"` |
| `result.contextId` | Session/context identifier | UUID string |

Example full round-trip observed (from task2_test_output.txt):
- Request `id: "test-953ff005"` sent to Flight Booking Agent
- Response `id: "test-953ff005"` returned — IDs matched confirming JSON-RPC pairing
- `status.state: "completed"` confirmed successful task execution

---

## Information in the Agent Card and How It Was Used

Each agent serves its agent card at `/.well-known/agent-card.json`. The Travel Assistant fetched the Flight Booking Agent card at `http://127.0.0.1:10002/.well-known/agent-card.json`:

```json
{
  "name": "Flight Booking Agent",
  "description": "Flight booking and reservation management agent",
  "url": "http://127.0.0.1:10002/",
  "version": "0.0.1",
  "protocolVersion": "0.3.0",
  "preferredTransport": "JSONRPC",
  "capabilities": {"streaming": true},
  "defaultInputModes": ["text"],
  "defaultOutputModes": ["text"],
  "skills": [
    {"id": "check_availability", "description": "Check seat availability for a specific flight."},
    {"id": "reserve_flight", "description": "Reserve seats on a flight for passengers."},
    {"id": "confirm_booking", "description": "Confirm and finalize a flight booking."},
    {"id": "process_payment", "description": "Process payment for a booking (simulated)."},
    {"id": "manage_reservation", "description": "Update, view, or cancel existing reservations."}
  ]
}
```

**How each field was used:**

- **`url`** — The Travel Assistant used this to construct the A2A endpoint address (`http://127.0.0.1:10002/`) where JSON-RPC messages are sent.
- **`skills`** — The LLM used the skill descriptions to determine that this agent can check availability, reserve seats, confirm bookings, and process payments — matching the user's request.
- **`protocolVersion` / `preferredTransport`** — The Travel Assistant confirmed the agent speaks JSON-RPC 2.0 (A2A 0.3.0), enabling compatible communication.
- **`capabilities.streaming`** — Indicates the agent supports streaming responses, which the strands A2AServer uses for real-time output.
- **`defaultInputModes` / `defaultOutputModes`** — Both agents use plain text, so no format negotiation was required.

---

## Benefits and Limitations of This Approach

### Benefits

1. **Loose coupling**: The Travel Assistant does not need to know about the Flight Booking Agent at build time. It discovers it at runtime through the registry. Adding new agents requires no code changes to existing agents.

2. **Self-describing agents**: The agent card is a complete specification — URL, capabilities, skills, protocol version. Any agent that reads the card has everything it needs to communicate without side-channel documentation.

3. **Standard protocol (JSON-RPC 2.0)**: A well-understood, lightweight protocol. Any HTTP client can call an A2A agent. The request/response pairing via `id` field is simple and robust.

4. **Framework interoperability**: The A2A protocol is framework-agnostic. A Python agent built with Strands can communicate with a Java agent or a Go agent that also speaks A2A — they only need to agree on the JSON structure.

5. **Semantic discovery**: Rather than hardcoding agent URLs, agents express their needs in natural language ("book flights") and the registry matches them to capabilities. This scales to large ecosystems of specialized agents.

6. **Task model**: The A2A `kind: "task"` model captures multi-turn interactions, streaming, history, and artifacts — richer than plain request/response. The `contextId` enables stateful conversations.

### Limitations

1. **Registry is a single point of failure**: All discovery depends on the registry being available. If the registry goes down, agents cannot find each other. Real deployments need a highly available registry with replication.

2. **Stub registry has no real semantic search**: The lab's registry stub always returns the same agent regardless of query. A production registry would need vector embeddings or keyword indexing to perform genuine capability matching.

3. **No authentication in this lab**: The A2A spec supports auth via agent cards (OAuth scopes, JWT, API keys), but this lab omits it. Any agent can call any other agent without credentials — a security risk in production.

4. **Cold discovery latency**: Each time the Travel Assistant needs a capability it hasn't used before, it must first query the registry, then fetch the agent card, then cache the result. This adds latency to the first interaction.

5. **No versioning strategy**: Both agents use `protocolVersion: "0.3.0"`, but there is no negotiation if versions differ. A newer agent that removes or renames a skill would silently break callers that discovered an older version.

6. **Mock LLM limitation**: For this lab run, the agents use a static mock LLM response rather than a real language model, so the agents do not actually invoke their tools (search_flights, reserve_flight, etc.) in response to user queries. In a real deployment with a live LLM, the agent would use its tools to query the database and return actual flight data.
