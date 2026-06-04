> **Parent**: [API Integration Guide](README.md)

# REST API Reference

## Base URL

**Local development:**
```
http://localhost:8000
```

**Cloud Run:**
```
https://agentic-hybrid-search-<hash>.run.app
```

## Authentication

All endpoints require **session authentication** OR **admin token**.

| Auth Type | Method | Example |
|-----------|--------|---------|
| **Session cookie** | Login first, cookie sent automatically | See [Auth Patterns](auth-patterns.md) |
| **Admin token** | `X-Admin-Token` header | `X-Admin-Token: <32+ char token>` |

---

## Endpoints

### Auth

#### `POST /api/auth/login`

Log in with shared password. Returns session cookie.

**Request:**
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"password": "your-login-password"}' \
  -c cookies.txt
```

**Response (200):**
```json
{"message": "Login successful"}
```

**Subsequent requests** automatically include the cookie:
```bash
curl http://localhost:8000/api/suggest?q=wireless \
  -b cookies.txt
```

---

### Conversations

#### `GET /api/conversations`

List all conversations.

**Request:**
```bash
curl http://localhost:8000/api/conversations \
  -b cookies.txt
```

**Response (200):**
```json
[
  {
    "id": "conv-123",
    "title": "Laptop search",
    "created_at": "2026-06-04T12:00:00Z",
    "updated_at": "2026-06-04T12:05:00Z"
  }
]
```

#### `GET /api/conversations/{id}`

Get conversation history.

**Request:**
```bash
curl http://localhost:8000/api/conversations/conv-123 \
  -b cookies.txt
```

**Response (200):**
```json
{
  "id": "conv-123",
  "messages": [
    {"role": "user", "content": "wireless earbuds under $100"},
    {"role": "assistant", "content": "...", "citations": []}
  ]
}
```

#### `POST /api/conversations/{id}/messages`

Send a message (REST polling; use WebSocket for real-time streaming).

**Request:**
```bash
curl -X POST http://localhost:8000/api/conversations/conv-123/messages \
  -H "Content-Type: application/json" \
  -d '{"message": "compare these with Bose"}' \
  -b cookies.txt
```

**Response (202 Accepted):**
```json
{"status": "processing", "message_id": "msg-456"}
```

Use WebSocket (`/ws/{thread_id}`) for real-time response streaming instead (see [WebSocket](websocket.md)).

---

### Search & Suggest

#### `GET /api/suggest`

Typeahead autocomplete. Returns product title suggestions.

**Request:**
```bash
curl "http://localhost:8000/api/suggest?q=wireless+head" \
  -b cookies.txt
```

**Response (200):**
```json
{
  "suggestions": [
    {"text": "Wireless Headphones", "type": "title"},
    {"text": "Wireless Headset", "type": "title"}
  ]
}
```

---

### Admin Endpoints

#### `GET /api/health`

Service health check. Returns index document count, shard status, etc.

**Request (with session cookie):**
```bash
curl http://localhost:8000/api/health \
  -b cookies.txt
```

**Request (with admin token):**
```bash
curl http://localhost:8000/api/health \
  -H "X-Admin-Token: your-admin-token-here"
```

**Response (200):**
```json
{
  "status": "healthy",
  "index": {
    "name": "agentic_hybrid_search_docs",
    "doc_count": 9618,
    "shards": {"active": 4, "unassigned": 0}
  },
  "database": "connected",
  "openai_api": "reachable"
}
```

#### `GET /api/admin/diagnose`

Detailed field-level diagnostics (hit counts by field).

**Request:**
```bash
curl http://localhost:8000/api/admin/diagnose \
  -H "X-Admin-Token: your-admin-token"
```

**Response (200):**
```json
{
  "fields": {
    "product_title": {"hits": 8500, "missing": 0},
    "product_brand": {"hits": 9100, "missing": 518}
  }
}
```

---

## Error Responses

### `400 Bad Request`

Invalid query or malformed JSON.

```json
{
  "detail": "Invalid query parameter: q"
}
```

### `401 Unauthorized`

Missing or invalid authentication.

```json
{
  "detail": "Session expired or invalid"
}
```

### `403 Forbidden`

Not authenticated (session or token required).

```json
{
  "detail": "Login required"
}
```

### `500 Internal Server Error`

Server error (check [logs](../operations/monitoring.md)).

```json
{
  "detail": "Internal server error"
}
```

---

## Rate Limiting

No built-in rate limiting. On high-traffic deployments, Cloud Run will enforce quota limits via the GCP API.

---

## Best Practices

1. **Use WebSocket for real-time searches** — REST polling is slower and increases load
2. **Reuse session cookies** — login once, send cookie with all subsequent requests
3. **Use admin token for automation** — CI/CD jobs should use `X-Admin-Token` header, not session cookies
4. **Handle 502 gracefully** — Cloud Run cold starts (first request after deploy) may cause brief timeouts; retry with exponential backoff
5. **Monitor latency** — single search can take 15–45 seconds depending on FETCH_K and model load time; set client timeouts accordingly
