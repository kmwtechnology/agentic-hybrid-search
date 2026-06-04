> **Parent**: [Contributing Guide](README.md)

# Code Patterns

Core patterns and conventions used throughout Agentic Hybrid Search.

---

## PYTHONPATH

All Python commands from `langchain_agent/` must set `PYTHONPATH=.`:

```bash
cd langchain_agent
PYTHONPATH=. python script.py
PYTHONPATH=. pytest tests/unit/
```

**Why?** Modules use bare imports like `from config import ...` instead of `from langchain_agent.config import ...`. Omitting `PYTHONPATH=.` causes `ModuleNotFoundError`.

---

## State Access Pattern

`CustomAgentState` is a TypedDict with `total=False` — only `messages` is guaranteed.

Always use `.get()` with a default:

```python
# ✓ Correct
intent = state.get("intent", "search")
alpha = state.get("alpha", 0.25)

# ✗ Wrong (will KeyError if field not set)
intent = state["intent"]
```

State is populated stage-by-stage:
- **Classifier**: adds `intent`, `confidence`, `user_query`
- **Query Evaluator**: adds `alpha`, `intent_description`
- **Retriever**: adds `retrieved_documents`, `pre_rerank_documents`, `bm25_documents`, `judgments`, latency fields
- **Reranker**: adds `reranker_max_score`, `reranked_documents`, `reranker_latency_ms`
- **Quality Gate**: adds `quality_gate_retried`, `alpha_adjusted_value`

---

## Exception Hierarchy

All exceptions inherit from `AgenticHybridSearchError`.

| Exception | `recoverable` | When to use |
|-----------|---------------|-----------|
| `LLMError` | True | LLM API timeouts, quota exceeded |
| `OpenSearchError` | True | Search query failures, shard unavailable |
| `DatabaseError` | True | Connection lost, locks |
| `RetrievalError` | True | Hybrid search failures |
| `RerankerError` | True | Cross-encoder timeouts |
| `SearchFailureError` | True | Query execution failed |
| `ConfigurationError` | False | Missing or invalid env var |
| `StateError` | False | Invalid pipeline state |
| `AgentError` | False | Response generation failure |
| `RerankerValidationError` | False | Score validation failed |

**Pattern:**

```python
from exceptions import LLMError

try:
    response = await llm_api.call(...)
except TimeoutError as e:
    raise LLMError(
        message="LLM timeout",
        details={"model": LLM_MODEL, "timeout_ms": 3000},
        recoverable=True
    ) from e
```

**When catching:**
```python
try:
    docs = retriever.fetch(query)
except RetrievalError as e:
    if e.recoverable:
        # Retry with adjusted alpha
        alpha = state.get("alpha", 0.25) + 0.15
        docs = retriever.fetch(query, alpha=alpha)
    else:
        # Non-recoverable; raise
        raise
```

---

## LLM Content Flattening

Gemini sometimes returns LLM responses as `List[ContentBlock]` instead of a flat string. Always flatten:

```python
from main import _flatten_llm_content

# When extracting intent from LLM response
intent_text = _flatten_llm_content(llm_message)
# Now `intent_text` is a string; safe to parse as JSON

# In observability_agent.py when emitting events
text = _flatten_llm_content(msg.content)
emit_event({"text": text})
```

**Why?** Prevents silent failures when `.content` is a list instead of a string.

---

## Event Parity Rule

**Critical:** `api/schemas/events.py` must stay in sync with `web/src/types/events.ts`.

Every event emitted by the backend must have a matching TypeScript type in the frontend.

**Verification:**
```bash
PYTHONPATH=. pytest tests/unit/test_frontend_backend_event_parity.py -v
```

**When adding a new event:**
1. Add the Pydantic model to `api/schemas/events.py`
2. Add the TS type to `web/src/types/events.ts` (same fields, same `type` Literal)
3. Run the parity test; must pass
4. Emit the event in `api/services/observable_agent.py`

---

## Auth Patterns

**DO:**
- Use `verify_same_origin` + `verify_session` for protected routes
- Use `verify_session` for WebSocket handshakes
- Use `verify_admin_token` for automation endpoints (`/api/admin/*`, `/api/health`)

**DON'T:**
- Wire new routes through `verify_api_key` (dead code; being removed)
- Skip auth on endpoints that serve user data
- Mix auth methods on the same route (choose one: session OR admin token)

```python
from api.middleware.session_auth import verify_session, verify_admin_token

@app.get("/api/health")
async def health(request: Request):
    try:
        verify_session(request)  # Try session first
    except HTTPException:
        verify_admin_token(request)  # Fall back to admin token
    
    return {"status": "healthy"}
```

---

## State Return Pattern

All nodes must return a dict with keys that match their expected outputs.

**Critical:** `agent_node` must ALWAYS include a `"citations"` key (even if empty):

```python
# ✓ Correct — all paths include "citations"
def agent_node(state):
    if summary_mode:
        return {"text": "...", "citations": []}
    
    if no_results:
        return {"text": "No results", "citations": []}
    
    return {"text": response, "citations": extracted_citations}

# ✗ Wrong — missing "citations" on some paths
def agent_node(state):
    if summary_mode:
        return {"text": "..."}  # Missing citations!
    
    return {"text": response, "citations": extracted_citations}
```

This prevents observability from silently dropping events.

---

## Logging Pattern

Use structured logging (via `structlog`):

```python
import logging
logger = logging.getLogger(__name__)

# Good
logger.warning("Query evaluation failed", extra={
    "intent": intent,
    "alpha_fallback": 0.25,
    "error": str(e)
})

# Not ideal (loses structure)
logger.warning(f"Query evaluation failed for {intent}")
```

---

## Testing Patterns

See [Testing](testing.md) for full test strategy. Quick reference:

- **Unit tests** — no external deps, `PYTHONPATH=. pytest tests/unit/`
- **Integration tests** — requires Postgres + OpenSearch, `docker compose up -d`, then test
- **E2E tests** — requires full Cloud Run deploy or localhost backend
- **Smoke tests** — quick sanity checks, `make smoke-local`

Never commit with `make ci` warnings or test failures.
