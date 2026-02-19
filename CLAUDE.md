# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Agentic Hybrid Search** — a production-grade LangGraph RAG agent for Lucille documentation. Features hybrid search (vector + BM25), LLM-based reranking, multi-capability intent routing (5 intents), real-time streaming via WebSocket, and multi-format content generation. Deployed on GCP Cloud Run with Google Gemini AI.

## Repository Layout

- `langchain_agent/` — Main application (all development happens here)
  - `main.py` — LangGraph agent core (~4500 lines): intent classifier, query evaluator, retriever, reranker, agent nodes
  - `agent_state.py` — `CustomAgentState` TypedDict (40+ fields, only `messages` guaranteed; always use `state.get(key, default)`)
  - `config.py` — All configuration constants loaded from `.env`
  - `vector_store.py` — OpenSearch hybrid search with RRF fusion (`score = Σ 1/(rank + 60)`)
  - `reranker.py` — `GeminiReranker` with Pydantic-validated 0.0–1.0 scoring
  - `content_generators.py` — 5 content types with varying temperature/retrieval depth
  - `config_builder.py` — Natural language → Lucille HOCON config generation
  - `link_verifier.py` — URL validation with thread-safe cache (60-min TTL)
  - `api/` — FastAPI backend (REST + WebSocket streaming)
  - `web/` — React 18 + TypeScript + Tailwind frontend (Zustand state, Vite build)
  - `tests/` — pytest test suites (unit, integration, e2e)
  - `scripts/` — Setup, start, stop, deploy, GCP init/teardown scripts
- `web/` — Secondary/skeleton web app (separate from `langchain_agent/web/`)
- `esci/` — Amazon Shopping Queries Dataset (data source, not actively developed)

## Common Commands

All backend commands run from `langchain_agent/`:

```bash
# Local services (PostgreSQL + OpenSearch)
docker compose up -d          # from repo root
docker compose down           # stop services

# Backend setup & run
cd langchain_agent
python3 setup.py              # one-time DB setup
make dev-api                  # FastAPI on :8000 (with --reload)
make dev-web                  # React frontend on :5173 (from web/)
make dev                      # both (backend backgrounded)
make stop                     # kill all dev processes

# Testing (pytest, from langchain_agent/)
pytest tests/unit/                          # unit tests
pytest tests/integration/                   # integration tests
pytest tests/unit/test_reranker.py          # single test file
pytest tests/ -m phase1                     # by marker
pytest tests/ -k "test_auth"               # by name pattern
pytest --cov=. --cov-report=html           # with coverage

# Legacy standalone tests (from langchain_agent/)
make test-reranker
make test-hybrid
make test-query

# Linting & formatting
make lint                     # pylint
make format                   # black
make type-check               # mypy

# Frontend (from langchain_agent/web/)
npm install                   # install deps
npm run dev                   # vite dev server
npm run build                 # production build
npm run lint                  # eslint

# Deployment
./scripts/deploy.sh --project <GCP_PROJECT_ID>
```

## Architecture

### LangGraph Pipeline Flow

```
Intent Classifier → Query Evaluator → Retriever → Alpha Refiner → Reranker → Agent
```

- **Intent classification**: 5 classes — `question`, `config_request`, `documentation_request`, `summary`, `follow_up`. Keyword fast-path with LLM fallback. Confidence < 0.7 triggers clarification.
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
- **Observable events**: Pipeline emits Pydantic-typed events over WebSocket for real-time UI visualization. Event schemas in `api/schemas/events.py`, frontend types in `web/src/types/events.ts`.
- **Hybrid search**: Vector + full-text results fused via Reciprocal Rank Fusion (k=60). The `alpha` parameter controls weighting.
- **Error hierarchy**: Custom exceptions in `exceptions.py` — all inherit from `AgenticHybridSearchError`.
- **Auth**: API_KEY required via middleware on protected routes.

## Testing

- Python 3.13 required (`minversion = 3.13` in pytest.ini)
- Markers: `phase1`, `phase2`, `phase3`, `unit`, `integration`, `slow`, `auth`, `search`, `rerank`, `websocket`, `database`
- CI runs on push/PR to `main`/`develop` for paths under `langchain_agent/`
- Services needed for integration tests: PostgreSQL 16, OpenSearch

## Environment

Copy `langchain_agent/.env.example` to `.env`. Key variables:
- `GOOGLE_API_KEY` — required for LLM/embeddings
- `POSTGRES_HOST/PORT/USER/PASSWORD` — checkpoint storage
- `OPENSEARCH_HOST/PORT/USE_SSL` — vector search
- `API_KEY` — API authentication
