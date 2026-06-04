> **Parent**: [Contributing Guide](README.md)

# Testing Strategy

Agentic Hybrid Search uses a **test pyramid**: unit → integration → e2e → smoke.

---

## Test Pyramid

| Level | Scope | Service Deps | Time | Where |
|-------|-------|-------------|------|-------|
| **Unit** | Single function/class | None | ~3s | `tests/unit/` |
| **Integration** | Multi-component | Postgres + OpenSearch | ~30s | `tests/integration/` |
| **E2E** | Full system | Cloud Run | ~60s per test | `tests/e2e/` |
| **Smoke** | Sanity checks | Local backend or Cloud Run | ~90s | `tests/e2e/` (marked with `@pytest.mark.slow`) |

---

## Unit Tests

No external services required.

```bash
cd langchain_agent
PYTHONPATH=. pytest tests/unit/ -v
```

Expected output:
```
708 passed in 3.2s
```

**Add a unit test:** Create a new file in `tests/unit/test_*.py` or add to existing file.

```python
import pytest
from main import _flatten_llm_content

def test_flatten_llm_content_with_string():
    msg = "hello"
    assert _flatten_llm_content(msg) == "hello"

def test_flatten_llm_content_with_list():
    msg = [{"text": "hello"}, {"text": " world"}]
    assert _flatten_llm_content(msg) == "hello world"
```

---

## Integration Tests

Require **live PostgreSQL + OpenSearch**.

```bash
docker compose up -d
cd langchain_agent
PYTHONPATH=. pytest tests/integration/ -v
```

**When to run:** After changes to middleware, WebSocket handlers, or database operations.

**Note:** `make ci` only runs `--collect-only` on integration tests (validates imports). Run the actual tests manually before pushing:

```bash
PYTHONPATH=. pytest tests/integration/test_auth.py -v
```

---

## E2E Tests

Full system test against Cloud Run or localhost backend.

### Local E2E (against localhost:8000)

```bash
# In one terminal, start the backend
make dev-api

# In another terminal, run e2e tests
export CLOUD_RUN_URL=http://localhost:8000
export LOGIN_PASSWORD=$(grep '^LOGIN_PASSWORD=' .env | cut -d= -f2)

PYTHONPATH=. pytest tests/e2e/test_search.py -v -m "e2e and not slow" --timeout=120
```

### Cloud Run E2E

```bash
export CLOUD_RUN_URL=https://agentic-hybrid-search-xyz.run.app
export LOGIN_PASSWORD=<password-from-cloud-run>

PYTHONPATH=. pytest tests/e2e/ -v --timeout=120
```

---

## Smoke Tests

Focused sanity checks for critical paths.

```bash
# Quick smoke (search-only, ~13s)
make smoke-local-quick

# Full smoke (all 20 tests, ~90s)
make smoke-local
```

**Git hooks run smoke tests automatically:**
- **Pre-commit:** `smoke-local-quick` when `api/services/`, `api/routes/`, `api/main.py`, `main.py`, or `agent_state.py` staged
- **Pre-push:** `smoke-local` (full 20 tests) when backend paths modified

### Smoke Test Budget

Each chat message round-trip = **16–25 seconds** (LLM generation + cross-encoder reranking).

Pytest timeout is set to **120 seconds** per test file, accommodating 2–5 sequential messages per test.

If you add a new smoke test with >2 messages, increase `pytest --timeout=180`.

---

## CI/CD Gates

### Local CI Gate

```bash
make ci  # Runs: format, lint, type-check, unit tests, frontend tests, collect-only integration+e2e
```

**Expected:** All pass before pushing.

### GitHub Actions CI

- **On every PR/push:** `test.yml` runs unit + integration + frontend tests (no e2e)
- **On main only:** `build-deploy.yml` builds Docker, deploys to Cloud Run, runs smoke tests

---

## Test Markers

Filter tests by marker:

```bash
# Only unit tests
PYTHONPATH=. pytest tests/ -m "unit" -v

# Only integration
PYTHONPATH=. pytest tests/ -m "integration" -v

# Only e2e (not slow)
PYTHONPATH=. pytest tests/e2e/ -m "e2e and not slow" -v

# Only slow tests (smoke tests)
PYTHONPATH=. pytest tests/e2e/ -m "slow" -v

# Search-specific tests
PYTHONPATH=. pytest tests/ -m "search" -v
```

---

## Adding a New Test

### Unit Test

```python
# tests/unit/test_my_feature.py
import pytest
from my_module import my_function

def test_my_function_basic():
    result = my_function("input")
    assert result == "expected"

def test_my_function_error():
    with pytest.raises(ValueError):
        my_function("bad input")
```

### Integration Test

```python
# tests/integration/test_my_feature.py
import pytest
import psycopg
from opensearchpy import OpenSearch

@pytest.fixture
def db():
    conn = psycopg.connect("postgresql://postgres:postgres@localhost/langchain_agent")
    yield conn
    conn.close()

def test_database_insert(db):
    cur = db.cursor()
    cur.execute("INSERT INTO checkpoints (thread_id, data) VALUES (%s, %s)", ("test", "{}"))
    db.commit()
    assert True
```

### Smoke Test

Smoke tests live in `tests/e2e/` and use `@pytest.mark.slow`:

```python
# tests/e2e/test_my_feature.py
import pytest
from tests.e2e.conftest import auth_ws_headers

@pytest.mark.slow
@pytest.mark.e2e
async def test_my_scenario(websocket_fixture):
    """Smoke test for my feature."""
    ws = await websocket_fixture.connect()
    await ws.send(json.dumps({
        "type": "chat_message",
        "message": "my query",
        "thread_id": "test-conv"
    }))
    
    events = []
    async for msg in ws:
        events.append(json.loads(msg))
        if msg.get("type") == "agent_complete":
            break
    
    assert any(e["type"] == "agent_response_chunk" for e in events)
```

---

## Pre-Commit & Pre-Push Hooks

The project uses two-tier git hooks (in `.git/hooks/`):

| Hook | Runs | When |
|------|------|------|
| **pre-commit** | black + isort + flake8 + `smoke-local-quick` | Every commit on changed Python files |
| **pre-push** | `make ci` + `make smoke-local` | Once per push when backend files changed |

**Bypass (not recommended):** `git commit --no-verify` or `git push --no-verify`

---

## Troubleshooting Tests

### `ModuleNotFoundError: No module named 'config'`

Missing `PYTHONPATH=.`:

```bash
PYTHONPATH=. pytest tests/unit/  # ✓ Correct
pytest tests/unit/                # ✗ Wrong
```

### Test hangs or times out

Check if Docker services are up:

```bash
docker compose ps
# Should see postgres, opensearch, opensearch-dashboards running
```

If not:

```bash
docker compose up -d
```

### WebSocket test fails with `ConnectionRefusedError`

Backend not running on `:8000`:

```bash
make dev-api  # Starts backend
# Then run test in another terminal
```

### Integration test fails with `psycopg.OperationalError`

PostgreSQL connection lost:

```bash
docker compose restart postgres
PYTHONPATH=. pytest tests/integration/ -v
```

---

## Coverage Report

Generate HTML coverage report:

```bash
cd langchain_agent
PYTHONPATH=. pytest tests/unit/ --cov=. --cov-report=html
open htmlcov/index.html
```

Current coverage: ~75% (unit tests only; integration/e2e not included in coverage%).
