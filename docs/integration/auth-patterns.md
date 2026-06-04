> **Parent**: [API Integration Guide](README.md)

# Authentication Patterns

Two authentication flows are supported: **session cookie** (interactive users) and **admin token** (automation/CI).

---

## Pattern A: Session Cookie (Interactive Users)

Browsers and web clients use this flow.

### Step 1: Login

Send the shared password to `POST /api/auth/login`:

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"password": "your-login-password"}' \
  -c cookies.txt  # Save cookie to file
```

Response:
```json
{"message": "Login successful"}
```

The server sets an `HttpOnly`, `Secure`, `SameSite=Lax` cookie named `ahs_session`.

### Step 2: All Subsequent Requests

Include the cookie automatically with every request:

**REST:**
```bash
curl http://localhost:8000/api/conversations \
  -b cookies.txt
```

**WebSocket (JavaScript):**
```javascript
const ws = new WebSocket(`ws://${host}/ws/${threadId}`);
// Browser automatically sends session cookie with handshake
```

**WebSocket (Python):**
```python
import websockets
from http.cookies import SimpleCookie

# Parse cookie from login response
cookie_str = "ahs_session=xyz; Path=/; SameSite=Lax; HttpOnly"
headers = {"Cookie": cookie_str.split(';')[0]}

await websockets.connect(url, additional_headers=headers)
```

### Session Expiry

Sessions expire after **24 hours** (configurable via `SESSION_MAX_AGE_SECONDS` in `.env`).

**WebSocket close code `4401`** signals session expiration:

```javascript
ws.onclose = (event) => {
  if (event.code === 4401) {
    console.log('Session expired. Please log in again.');
    // Redirect to login screen or call login() again
  }
};
```

---

## Pattern B: Admin Token (Automation/CI)

GitHub Actions, scheduled jobs, and server-to-server integrations use this flow.

### Step 1: Obtain Token

Admin token is a 32+ character secret set in the environment:

```bash
# In .env or GitHub Secrets
ADMIN_TOKEN="your-32-or-more-char-random-string"
```

Local dev generates a token on first run; production uses a manually set secret.

### Step 2: Send Token Header

Include `X-Admin-Token` with every request:

**REST:**
```bash
curl http://localhost:8000/api/health \
  -H "X-Admin-Token: your-admin-token"
```

**WebSocket:**
```python
import websockets

headers = {
  "X-Admin-Token": "your-admin-token"
}

await websockets.connect(url, additional_headers=headers)
```

### Admin Routes

Only these routes accept `X-Admin-Token`:

- `GET /api/health` — Service health
- `GET /api/admin/diagnose` — Field-level diagnostics

### Token Rotation

Tokens are **not rotatable** without a deploy (the token is read from `ADMIN_TOKEN` env var at startup).

To rotate:
1. Update `ADMIN_TOKEN` in Secret Manager or `.env`
2. Redeploy the service (token becomes active immediately)

---

## Origin & CORS

### Same-Origin Policy

All requests (REST and WebSocket) are checked against an allow-list of **allowed origins**.

**Default allow-list (local dev):**
```
http://localhost:5173
http://localhost:8000
http://127.0.0.1:8000
```

**Cloud Run allow-list:**
```
https://*.run.app
```

### What Happens on Disallowed Origin

If a browser makes a request from an origin NOT in the allow-list:
- Origin header **present** → `403 Forbidden`
- Origin header **absent** (AND Referer absent) → Request proceeds (legacy fallback for scripts)

To add a custom origin (e.g., `https://my-app.com`), update `CORS_ORIGINS` in `.env`:

```bash
CORS_ORIGINS=https://my-app.com,https://another.com
```

Redeploy after changing.

---

## Comparing the Two Flows

| Feature | Session Cookie | Admin Token |
|---------|----------------|------------|
| **User type** | Interactive (browser) | Automation (CI, jobs) |
| **Login required** | Yes; password needed | No; token in header |
| **Expiry** | 24 hours | None (env var-based) |
| **Routes** | REST + WebSocket | `/api/health`, `/api/admin/*` only |
| **Security** | HttpOnly cookie, SameSite=Lax | Constant-time comparison (timing-attack safe) |
| **Use case** | Web UI, WebSocket chat | GitHub Actions, internal services |

---

## Best Practices

1. **Store passwords securely** — Never hardcode `LOGIN_PASSWORD` in code; use environment variables or Secret Manager
2. **Rotate admin tokens periodically** — Set a calendar reminder to refresh `ADMIN_TOKEN` every 90 days
3. **Use HTTPS in production** — Cookies and tokens are transmitted; always use TLS
4. **Set `SESSION_COOKIE_SECURE=true` on Cloud Run** — Ensures cookies are only sent over HTTPS
5. **Monitor auth failures** — Check logs for `401` errors; could signal token leakage or password guess attempts
6. **WebSocket reconnection** — Implement exponential backoff (3s, 6s, 12s, ..., max 60s) when WebSocket closes unexpectedly
