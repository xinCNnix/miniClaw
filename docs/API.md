# miniClaw API Documentation

## Base URL

```
http://localhost:8002
```

## Overview

miniClaw provides a REST API for chat interactions, file management, and session management. All responses are in JSON format.

---

## Chat API

### POST /api/chat

Send a message to the AI agent and receive a streaming response via Server-Sent Events (SSE).

**Request Body:**

```json
{
  "session_id": "optional-session-uuid",
  "messages": [
    {
      "role": "user",
      "content": "Your message here"
    }
  ]
}
```

**Response:**

Server-Sent Events stream with the following event types:

#### `thinking_start`

Indicates the agent has started processing.

```json
{
  "type": "thinking_start"
}
```

#### `tool_call`

Indicates the agent is calling a tool.

```json
{
  "type": "tool_call",
  "tool_calls": [
    {
      "name": "terminal",
      "arguments": {
        "command": "ls -la"
      }
    }
  ]
}
```

#### `content_delta`

Streamed content chunk from the agent.

```json
{
  "type": "content_delta",
  "content": "Hello"
}
```

#### `tool_output`

Output from a tool execution.

```json
{
  "type": "tool_output",
  "tool_name": "terminal",
  "output": "file1.txt\nfile2.txt",
  "status": "success"
}
```

#### `session_id`

Returns the session ID (new or existing).

```json
{
  "type": "session_id",
  "session_id": "uuid-here"
}
```

#### `error`

An error occurred during processing.

```json
{
  "type": "error",
  "error": "Error message"
}
```

#### `done`

Stream completed.

```json
{
  "type": "done"
}
```

**Example (cURL):**

```bash
curl -N http://localhost:8002/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "What is 2 + 2?"}
    ]
  }'
```

---

## Files API

### GET /api/files

List all available files in the workspace.

**Query Parameters:**

- `path` (optional): Filter by directory path

**Response:**

```json
[
  {
    "path": "README.md",
    "size": 1024,
    "modified": "2024-01-01T00:00:00Z"
  }
]
```

### GET /api/files?path={file_path}

Read a specific file.

**Query Parameters:**

- `path` (required): File path

**Response:**

```json
{
  "path": "README.md",
  "content": "File content here...",
  "size": 1024
}
```

### POST /api/files

Create or update a file.

**Request Body:**

```json
{
  "path": "test.txt",
  "content": "File content"
}
```

**Response:**

```json
{
  "path": "test.txt",
  "content": "File content",
  "size": 12
}
```

### DELETE /api/files?path={file_path}

Delete a file.

**Query Parameters:**

- `path` (required): File path

**Response:** `204 No Content`

**Example (cURL):**

```bash
# List files
curl http://localhost:8002/api/files

# Read file
curl "http://localhost:8002/api/files?path=README.md"

# Write file
curl -X POST http://localhost:8002/api/files \
  -H "Content-Type: application/json" \
  -d '{"path": "test.txt", "content": "Hello"}'

# Delete file
curl -X DELETE "http://localhost:8002/api/files?path=test.txt"
```

---

## Sessions API

### GET /api/sessions

List all chat sessions.

**Response:**

```json
[
  {
    "id": "uuid-1",
    "title": "Chat about Python",
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T01:00:00Z",
    "message_count": 10
  }
]
```

### POST /api/sessions

Create a new session.

**Response:**

```json
{
  "id": "new-uuid",
  "title": "New Conversation",
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z",
  "message_count": 0
}
```

### GET /api/sessions/{session_id}

Get session details including messages.

**Response:**

```json
{
  "id": "uuid-1",
  "title": "Chat about Python",
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T01:00:00Z",
  "messages": [
    {
      "role": "user",
      "content": "Hello",
      "timestamp": "2024-01-01T00:00:00Z"
    },
    {
      "role": "assistant",
      "content": "Hi there!",
      "timestamp": "2024-01-01T00:00:01Z"
    }
  ]
}
```

### PUT /api/sessions/{session_id}

Update session title.

**Request Body:**

```json
{
  "title": "New Title"
}
```

**Response:** Updated session object

### DELETE /api/sessions/{session_id}

Delete a session.

**Response:** `204 No Content`

**Example (cURL):**

```bash
# List sessions
curl http://localhost:8002/api/sessions

# Create session
curl -X POST http://localhost:8002/api/sessions

# Get session
curl http://localhost:8002/api/sessions/{session_id}

# Update session
curl -X PUT http://localhost:8002/api/sessions/{session_id} \
  -H "Content-Type: application/json" \
  -d '{"title": "Updated Title"}'

# Delete session
curl -X DELETE http://localhost:8002/api/sessions/{session_id}
```

---

## Health Check

### GET /health

Check API health status.

**Response:**

```json
{
  "status": "healthy",
  "version": "0.1.0"
}
```

### GET /

Get API information.

**Response:**

```json
{
  "name": "miniClaw API",
  "version": "0.1.0",
  "description": "Lightweight, transparent AI Agent system"
}
```

---

## Error Responses

All endpoints may return error responses:

**400 Bad Request:**

```json
{
  "detail": "Invalid request data"
}
```

**404 Not Found:**

```json
{
  "detail": "Resource not found"
}
```

**422 Validation Error:**

```json
{
  "detail": [
    {
      "loc": ["body", "messages"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

**500 Internal Server Error:**

```json
{
  "detail": "Internal server error"
}
```

---

## Rate Limiting

Currently, there are no rate limits enforced. Consider implementing rate limiting for production use.

---

## Authentication

Current version does not include authentication. For production use, implement API key or OAuth authentication.

---

## WebSocket Support

SSE (Server-Sent Events) is used for streaming chat responses. WebSocket support may be added in future versions.
