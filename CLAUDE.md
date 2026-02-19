# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Agentic Hybrid Search** — a production-grade LangGraph RAG agent for Lucille documentation. Features hybrid search (vector + BM25), LLM-based reranking, multi-capability intent routing, real-time streaming via WebSocket, and multi-format content generation. Deployed on GCP Cloud Run with Google Gemini AI.

## Repository Layout

- `langchain_agent/` — Main application (all development happens here)
  - `main.py` — LangGraph agent core (~4500 lines): intent classifier, query evaluator, retriever, reranker, agent nodes
  - `agent_state.py` — `CustomAgentState` TypedDict (40+ fields, only `messages` guaranteed)
  - `config.py` — All configuration constants loaded from `.env`
  - `exceptions.py` — Exception hierarchy, all inherit from `AgenticHybridSearchError`
  - `vector_store.py` — `OpenSearchVectorStore` + `OpenSearchRetriever` with RRF fusion
  - `reranker.py` — `GeminiReranker` with Pydantic-validated 0.0–1.0 scoring
  - `content_generators.py` — 5 content types with varying temperature/retrieval depth
  - `config_builder.py` — Natural language → Lucille HOCON config generation
  - `link_verifier.py` — URL validation with thread-safe cache (60-min TTL)
  - `embedding_cache.py` — Query embedding cache for performance
  - `retry_utils.py` — Retry logic utilities
  - `doc_replacer.py` — Document replacement logic
  - `logging_config.py` — Structured logging with structlog (JSON/console output)
  - `ingest_lucille_docs.py` — Documentation ingestion into OpenSearch
  - `api/` — FastAPI backend
    - `api/routes/chat.py` — WebSocket chat endpoint
    - `api/routes/conversations.py` — Conversation CRUD
    - `api/routes/health.py` — Health check
    - `api/schemas/events.py` — Pydantic event models for observability streaming
    - `api/middleware/auth.py` — API key authentication
    - `api/services/observable_agent.py` — Observable agent wrapper (emits typed events)
  - `web/` — React 18 + TypeScript + Tailwind frontend
    - `web/src/stores/` — Zustand state (chatStore, observabilityStore)
    - `web/src/types/events.ts` — Frontend event types (must match `api/schemas/events.py`)
    - `web/src/hooks/useWebSocket.ts` — WebSocket connection hook
    - `web/src/components/ObservabilityPanel/` — Real-time pipeline visualization
  - `tests/` — pytest suites: `unit/`, `integration/`, `e2e/`
  - `scripts/` — `setup.sh`, `start.sh`, `stop.sh`, `deploy.sh`, `gcp-init.sh`, `gcp-teardown.sh`
- `web/` — Skeleton web app (separate from `langchain_agent/web/`, less developed)
- `esci/` — Amazon Shopping Queries Dataset (external data source, not actively developed)

## Common Commands

All backend commands run from `langchain_agent/`:

```bash
# Local services (PostgreSQL + OpenSearch via Docker)
docker compose up -d          # from repo root
docker compose down

# Setup & run
cd langchain_agent
python3 setup.py              # one-time DB + OpenSearch index setup
make dev-api                  # FastAPI on :8000 (with --reload)
make dev-web                  # React frontend on :5173
make dev                      # both (backend backgrounded)
make stop                     # kill all dev processes

# Full lifecycle scripts
./scripts/setup.sh            # one-time: Docker, venv, deps, DB init, doc ingestion
./scripts/start.sh            # start Docker + backend + frontend
./scripts/stop.sh             # stop everything

# Testing — PYTHONPATH=. is required (modules use bare imports like `from config import ...`)
PYTHONPATH=. pytest tests/unit/                    # unit tests (~0.5s, no services needed)
PYTHONPATH=. pytest tests/integration/             # integration tests (needs PostgreSQL + OpenSearch)
PYTHONPATH=. pytest tests/unit/test_reranker.py    # single file
PYTHONPATH=. pytest tests/ -m phase1               # by marker
PYTHONPATH=. pytest tests/ -k "test_auth"          # by name pattern
PYTHONPATH=. pytest --cov=. --cov-report=html      # with coverage

# Legacy standalone tests
make test-reranker
make test-hybrid
make test-query

# Linting & formatting
make lint                     # pylint
make format                   # black
make type-check               # mypy

# Frontend (from langchain_agent/web/)
npm install
npm run dev                   # vite dev server
npm run build                 # tsc + vite build
npm run lint                  # eslint

# Deployment
./scripts/deploy.sh --project <GCP_PROJECT_ID>
./scripts/gcp-init.sh --project <GCP_PROJECT_ID>  # first-time: Cloud SQL tables + doc ingestion
```

## Architecture

### LangGraph Pipeline Flow

```
Intent Classifier → Query Evaluator → Retriever → Alpha Refiner → Reranker → Agent
```

- **Intent classification**: 5 classes — `question`, `config_request`, `documentation_request`, `summary`, `follow_up`. Keyword fast-path + LLM fallback. Confidence < 0.7 triggers clarification.
- **Dynamic alpha**: Controls lexical/semantic balance (0.0 = pure lexical, 1.0 = pure semantic). Default 0.25.
- **Alpha refinement**: If max reranker score < 0.5, retries with opposite search strategy.
- **Streaming**: WebSocket emits typed Pydantic events (`SearchProgressEvent`, `RerankerProgressEvent`, `LinkVerificationEvent`, `LLMResponseChunkEvent`, etc.) rendered in the React ObservabilityPanel.

### Tech Stack

| Layer | Technology |
|-------|-----------|
| LLM | Google Gemini 2.5 Flash |
| Classifier/Reranker | Gemini 2.5 Flash Lite |
| Embeddings | Gemini Embedding 001 (768-dim) |
| Agent Framework | LangGraph + LangChain |
| Vector DB | OpenSearch 2.19.1 (HNSW knn + BM25) |
| Checkpoints | PostgreSQL 16 (LangGraph checkpoints) |
| API | FastAPI + WebSocket |
| Frontend | React 18 + TypeScript + Tailwind + Zustand |
| Deployment | GCP Cloud Run (multi-stage Docker build) |

### Key Patterns

- **State access**: `CustomAgentState` uses `total=False`. Only `messages` is guaranteed. Always use `state.get("field", default)`, never `state["field"]` for optional fields.
- **Bare imports**: Python modules use bare imports (`from config import ...`, `from exceptions import ...`). This requires `PYTHONPATH=.` when running from `langchain_agent/`, or `PYTHONPATH` set to the `langchain_agent/` directory.
- **Observable events**: Pipeline emits Pydantic-typed events over WebSocket for real-time UI visualization. Event schemas in `api/schemas/events.py` must stay in sync with frontend types in `web/src/types/events.ts`.
- **Hybrid search**: Vector + full-text results fused via Reciprocal Rank Fusion (k=60). The `alpha` parameter controls weighting.
- **Error hierarchy**: Custom exceptions in `exceptions.py` — all inherit from `AgenticHybridSearchError`. Used by `reranker.py`, `vector_store.py`, `retry_utils.py`, and test files.
- **Auth**: API_KEY env var required; validated via middleware on protected routes (`api/middleware/auth.py`).

## Testing

- Python 3.13 required (`minversion = 3.13` in pytest.ini)
- Markers: `phase1`, `phase2`, `phase3`, `unit`, `integration`, `slow`, `auth`, `search`, `rerank`, `websocket`, `database`
- CI runs on push/PR to `main`/`develop` for paths under `langchain_agent/`
- Unit tests have no external dependencies (all mocked via `conftest.py` fixtures)
- Integration tests require running PostgreSQL 16 + OpenSearch + `GOOGLE_API_KEY`

## Environment

Copy `langchain_agent/.env.example` to `langchain_agent/.env`. Key variables:
- `GOOGLE_API_KEY` — required for LLM/embeddings (from https://aistudio.google.com/apikey)
- `POSTGRES_HOST/PORT/USER/PASSWORD` — checkpoint storage (default: localhost Docker)
- `OPENSEARCH_HOST/PORT/USE_SSL` — vector search (default: localhost Docker)
- `API_KEY` — API authentication (auto-generated by `setup.sh`)
