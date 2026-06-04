> **Parent**: [API Integration Guide](README.md)

# WebSocket Real-Time Streaming

Agentic Hybrid Search uses WebSocket for real-time token-by-token response streaming and pipeline observability events.

## Connection

**URL:**
```
wss://agentic-hybrid-search-<hash>.run.app/ws/{thread_id}
```

**Local dev:**
```
ws://localhost:8000/ws/{thread_id}
```

**Requirements:**
- Valid session cookie (obtained via `POST /api/auth/login`)
- `thread_id`: unique conversation identifier (e.g., `conv-123` or UUID)

---

## JavaScript Browser Example

```javascript
const threadId = 'my-conversation-' + Date.now();
const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const ws = new WebSocket(`${protocol}//${window.location.host}/ws/${threadId}`);

ws.onopen = () => {
  console.log('Connected');
  ws.send(JSON.stringify({
    type: 'chat_message',
    message: 'wireless earbuds under $100',
    thread_id: threadId
  }));
};

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  console.log(`[${msg.node}] ${msg.type}:`, msg);
  
  switch(msg.type) {
    case 'agent_response_chunk':
      document.querySelector('#response').textContent += msg.chunk;
      break;
    case 'agent_complete':
      console.log('Response complete. Citations:', msg.citations);
      break;
    case 'error':
      console.error('Error:', msg.error);
      break;
  }
};

ws.onerror = (error) => console.error('WebSocket error:', error);

ws.onclose = (event) => {
  if (event.code === 4401) {
    console.log('Unauthorized — re-login required');
  } else {
    console.log('Connection closed:', event.code, event.reason);
  }
};
```

---

## Python Example (asyncio)

```python
import asyncio
import json
import websockets
from http.cookies import SimpleCookie

async def search(query: str, thread_id: str, auth_cookie: str):
    # Parse cookie string: "ahs_session=xyz; Path=/; ..."
    cookie = SimpleCookie()
    cookie.load(auth_cookie.split(';')[0])  # Get first cookie
    
    url = f"ws://localhost:8000/ws/{thread_id}"
    headers = {"Cookie": str(cookie.output(header=''))}
    
    async with websockets.connect(url, additional_headers=headers) as ws:
        # Send query
        await ws.send(json.dumps({
            "type": "chat_message",
            "message": query,
            "thread_id": thread_id
        }))
        
        # Stream responses
        async for message in ws:
            msg = json.loads(message)
            print(f"[{msg.get('node')}] {msg.get('type')}: {msg}")
            
            if msg['type'] == 'agent_response_chunk':
                print(msg['chunk'], end='', flush=True)
            elif msg['type'] == 'error':
                print(f"Error: {msg['error']}")
                break
            elif msg['type'] == 'agent_complete':
                print("\n\nDone.")
                break

# Usage
import subprocess
auth_response = subprocess.run([
    'curl', '-X', 'POST', 'http://localhost:8000/api/auth/login',
    '-H', 'Content-Type: application/json',
    '-d', '{"password": "your-password"}',
    '-c', '/tmp/cookies.txt'
], check=True)

with open('/tmp/cookies.txt') as f:
    cookie = f.read()

asyncio.run(search("wireless headphones", "test-conv-1", cookie))
```

---

## Message Contracts

### Inbound (Client → Server)

**Send a query:**
```json
{
  "type": "chat_message",
  "message": "wireless earbuds under $100",
  "thread_id": "conv-123"
}
```

**Cancel ongoing request:**
```json
{
  "type": "cancel_request",
  "thread_id": "conv-123"
}
```

---

### Outbound (Server → Client)

Events are streamed in real-time. Each event has:
- `type` — event category (see table below)
- `node` — pipeline node that emitted it (intent_classifier, retriever, etc.)
- Additional fields depend on `type`

| Event Type | Node | Payload | Description |
|-----------|------|---------|-------------|
| `search_progress` | retriever | `status: "fetching"` | Retriever starting |
| `reranker_progress` | reranker | `count: 40, status: "scoring"` | Reranker progress |
| `quality_gate` | quality_gate | `pass: true, alpha_adjusted: null` | Quality gate verdict |
| `query_expansion` | query_evaluator | `original: "...", expanded: "..."` | Query rewrite |
| `agent_response_chunk` | agent | `chunk: "The"` | Response token |
| `agent_complete` | agent | `citations: [{url, title}]` | Response done |
| `clarification_requested` | intent_classifier | `question: "Did you mean...?"` | Needs clarification |
| `error` | (any) | `error: "str", type: "str"` | Error occurred |
| `connection_established` | (system) | `thread_id: "...", timestamp: ...` | Connected |

**Example sequence for a query:**

```json
{"type": "connection_established", "thread_id": "conv-123", "timestamp": "2026-06-04T12:00:00Z"}
{"type": "search_progress", "node": "retriever", "status": "fetching"}
{"type": "reranker_progress", "node": "reranker", "count": 40, "status": "scoring"}
{"type": "quality_gate", "node": "quality_gate", "pass": true, "alpha_adjusted": null}
{"type": "agent_response_chunk", "node": "agent", "chunk": "The"}
{"type": "agent_response_chunk", "node": "agent", "chunk": " top"}
...
{"type": "agent_complete", "node": "agent", "citations": [
  {"url": "https://www.amazon.com/s?k=wireless+earbuds", "title": "Wireless Earbuds"}
]}
```

---

## Close Codes

| Code | Reason | Action |
|------|--------|--------|
| `1000` | Normal closure | Client or server closed cleanly |
| `1011` | Server error | Retry after exponential backoff |
| `4401` | Unauthorized | Session expired; re-login via `POST /api/auth/login` |
| `4403` | Forbidden | Origin or auth rejected; check allow-list |

Example reconnection logic:

```javascript
ws.onclose = (event) => {
  if (event.code === 4401) {
    // Re-login
    await login();
    reconnect();
  } else if (event.code === 1011) {
    // Retry with backoff
    setTimeout(reconnect, 5000);
  }
};
```

---

## Performance Tips

1. **Send one message at a time** — WebSocket is half-duplex; wait for `agent_complete` before sending the next query
2. **Set client timeout to 60s minimum** — searches can take 15–45 seconds depending on model load
3. **Reconnect on 4401** — don't silently drop; prompt the user to log in again
4. **Discard old events** — if UI updates cause lag, skip rendering old events; only process the latest from each `node`
5. **Use `additional_headers` for cookies in Python** — don't include the entire Cookie header; `websockets` will merge them correctly
