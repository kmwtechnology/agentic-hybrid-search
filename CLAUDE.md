# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Agentic Hybrid Search** — a production-grade LangGraph RAG agent for Amazon ESCI e-commerce product search. Features hybrid search (vector + BM25), LLM-based reranking, intent routing, real-time streaming via WebSocket, and conversational product discovery. Deployed on GCP Cloud Run with Google Gemini AI.

## Repository Layout

- `langchain_agent/` — Main application (all development happens here)
  - `main.py` — LangGraph agent core (~4500 lines): intent classifier, query evaluator, retriever, reranker, agent nodes
  - `agent_state.py` — `CustomAgentState` TypedDict (40+ fields, only `messages` guaranteed)
  - `config.py` — All configuration constants loaded from `.env`
  - `exceptions.py` — Exception hierarchy, all inherit from `AgenticHybridSearchError`
  - `vector_store.py` — `OpenSearchVectorStore` + `OpenSearchRetriever` with RRF fusion
  - `reranker.py` — `GeminiReranker` with Pydantic-validated 0.0–1.0 scoring
  - `link_verifier.py` — URL validation with thread-safe cache (60-min TTL)
  - `embedding_cache.py` — Query embedding cache for performance
  - `retry_utils.py` — Retry logic utilities
  - `doc_replacer.py` — Document replacement logic
  - `logging_config.py` — Structured logging with structlog (JSON/console output)
  - `ingest_esci_products.py` — ESCI e-commerce product ingestion into OpenSearch (idempotent sampling, whole-product embedding)
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
./scripts/setup.sh            # one-time: Docker, venv, deps, DB init, product ingestion
./scripts/start.sh            # start Docker + backend + frontend
./scripts/stop.sh             # stop everything

# ESCI Product Ingestion (requires OpenSearch running via docker compose)
# Note: PYTHONPATH must be set for bare imports to work
PYTHONPATH=. python ingest_esci_products.py              # Ingest default 10K sample
PYTHONPATH=. python ingest_esci_products.py --limit 100 # Custom sample size (100 products)
PYTHONPATH=. python ingest_esci_products.py --all       # Ingest all US products (~1.2M)
PYTHONPATH=. python ingest_esci_products.py --resample  # Force re-sample even if cached
PYTHONPATH=. python ingest_esci_products.py --stats     # Show current index statistics

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
./scripts/gcp-init.sh --project <GCP_PROJECT_ID>  # first-time: Cloud SQL tables + product ingestion
```

## Architecture

### LangGraph Pipeline Flow

```
Intent Classifier → Query Evaluator → Retriever → Alpha Refiner → Reranker → Agent
```

- **Intent classification**: 3 classes — `question` (product/search queries), `summary` (summarize results), `follow_up` (continuation). Keyword fast-path + LLM fallback. Confidence < 0.7 triggers clarification.
- **Dynamic alpha**: Controls lexical/semantic balance (0.0 = pure lexical, 1.0 = pure semantic). Collection-aware defaults via `SEARCH_DEFAULTS` in config.py (esci_products: α=0.65).
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

- **Bare imports & PYTHONPATH**: All Python modules use bare imports (`from config import ...`, `from exceptions import ...`). This requires `PYTHONPATH=.` when running Python scripts from `langchain_agent/`. Set it explicitly: `PYTHONPATH=. python script.py` or `export PYTHONPATH=. && python script.py`. This includes: `pytest`, `ingest_esci_products.py`, `main.py`, and any custom scripts. Omitting it causes `ModuleNotFoundError`.
- **State access**: `CustomAgentState` uses `total=False`. Only `messages` is guaranteed. Always use `state.get("field", default)`, never `state["field"]` for optional fields.
- **Observable events**: Pipeline emits Pydantic-typed events over WebSocket for real-time UI visualization. Event schemas in `api/schemas/events.py` must stay in sync with frontend types in `web/src/types/events.ts`.
- **Hybrid search**: Vector + full-text results fused via Reciprocal Rank Fusion (k=60). The `alpha` parameter controls weighting (0.0 = pure lexical, 1.0 = pure semantic).
- **Product deduplication**: `OpenSearchRetriever.collapse_by_document()` removes duplicate product chunks from results. Applied automatically for `esci_products` collection.
- **No chunking for products**: ESCI products are indexed as whole units (not chunked). Controlled by `CHUNKING_STRATEGY` in config.py. Products are short (50-500 words) and don't benefit from 1000-char chunking.
- **Dual-mapped attributes**: `product_brand` and `product_color` are mapped as both `text` (for BM25 search) and `keyword` (for faceting/filtering). Use `.keyword` suffix for aggregations.
- **Faceting**: `OpenSearchVectorStore.get_facets()` returns aggregated attribute values (brands, colors) for the collection.
- **Error hierarchy**: Custom exceptions in `exceptions.py` — all inherit from `AgenticHybridSearchError`. Used by `reranker.py`, `vector_store.py`, `retry_utils.py`, and test files.
- **Auth**: API_KEY env var required; validated via middleware on protected routes (`api/middleware/auth.py`).

## ESCI Product Ingestion

The `ingest_esci_products.py` script loads Amazon ESCI e-commerce products from local parquet files into OpenSearch:

### Data Flow
1. **Load**: Reads `esci/shopping_queries_dataset/shopping_queries_dataset_products.parquet` (1.8M+ products)
2. **Filter**: Selects English (US) products only (`product_locale == "us"`)
3. **Sample**: Deterministic sampling with `random_state=42` for reproducibility
4. **Cache**: Saves sample as `esci/shopping_queries_dataset/esci_products_sample_{limit}.parquet` (idempotent — cached parquets reused on subsequent runs)
5. **Concatenate**: Combines product title + description + bullet points into a single document (no chunking — products are 50-500 words)
6. **Embed**: Generates one 768-dim Gemini embedding per product
7. **Index**: Bulk uploads to OpenSearch with dual-mapped metadata (product_id, product_brand, product_color, product_locale)

### Configuration
Key environment variables in `.env` (see `langchain_agent/.env.example`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `ESCI_DATASET_DIR` | `../esci/shopping_queries_dataset` | Path to parquet files |
| `ESCI_PRODUCT_LOCALE` | `us` | Filter to this locale (language/region) |
| `ESCI_INGEST_LIMIT` | `10000` | Default sample size for ingestion |
| `OPENSEARCH_HOST` | `localhost` | OpenSearch server (Docker: localhost, Cloud: IP) |
| `OPENSEARCH_PORT` | `9200` | OpenSearch port |
| `GOOGLE_API_KEY` | (required) | For embedding generation |

### Ingestion Commands
```bash
# Requires: Docker running (docker compose up -d) for OpenSearch
PYTHONPATH=. python ingest_esci_products.py              # Default 10K sample
PYTHONPATH=. python ingest_esci_products.py --limit 500  # 500-product sample
PYTHONPATH=. python ingest_esci_products.py --all        # All ~1.2M US products
PYTHONPATH=. python ingest_esci_products.py --resample   # Force re-sample (ignore cache)
PYTHONPATH=. python ingest_esci_products.py --stats      # Show index statistics
```

### Sample Parquet Caching
- First run with `--limit 100` creates `esci_products_sample_100.parquet` and ingests 100 products
- Second run with `--limit 100` reuses cached parquet (idempotent, fast)
- Run with `--resample` to force new sampling even if cache exists
- All cached parquets ignored by `.gitignore` (large binary files)

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
- `ESCI_DATASET_DIR` — path to ESCI parquet files (default: `../esci/shopping_queries_dataset`)
- `ESCI_PRODUCT_LOCALE` — filter products by locale (default: `us`)
- `ESCI_INGEST_LIMIT` — default sample size (default: `10000`)

## Troubleshooting

### `ModuleNotFoundError: No module named 'config'`
**Cause**: Missing `PYTHONPATH=.` when running Python scripts
**Fix**: Always prefix with `PYTHONPATH=.` when running from `langchain_agent/`:
```bash
cd langchain_agent
PYTHONPATH=. python ingest_esci_products.py
PYTHONPATH=. pytest tests/unit/
```

### `ConnectionError: Error connecting to OpenSearch`
**Cause**: OpenSearch not running or misconfigured
**Fix**:
1. Start Docker services: `docker compose up -d` (from repo root)
2. Verify running: `docker ps` (should show opensearch-node1)
3. Check `OPENSEARCH_HOST/PORT` in `.env` (default: localhost:9200)
4. Test connectivity: `curl http://localhost:9200`

### `ConnectionError: Error connecting to database`
**Cause**: PostgreSQL not running
**Fix**:
1. Start Docker services: `docker compose up -d`
2. Verify: `docker ps` (should show postgres)
3. Check `POSTGRES_HOST/PORT/USER` in `.env`

### `Google AI API validation failed`
**Cause**: Missing or invalid `GOOGLE_API_KEY`
**Fix**:
1. Get API key from https://aistudio.google.com/apikey
2. Add to `.env`: `GOOGLE_API_KEY=your-key-here`
3. Re-run setup: `python3 setup.py`

### No `.txt` files found in documents directory
**Cause**: ESCI dataset not downloaded or parquet files missing
**Fix**:
1. Ensure parquet file exists: `ls ../esci/shopping_queries_dataset/shopping_queries_dataset_products.parquet`
2. If missing, download ESCI dataset from Amazon (large file ~1GB)
3. Place in `../esci/shopping_queries_dataset/` directory
4. Run ingestion: `PYTHONPATH=. python ingest_esci_products.py`

### `FileNotFoundError: ESCI dataset not found`
**Cause**: Parquet file not in expected location
**Fix**:
1. Check path: `PYTHONPATH=. python -c "from config import ESCI_DATASET_DIR; print(ESCI_DATASET_DIR)"`
2. Verify file: `ls $ESCI_DATASET_DIR/shopping_queries_dataset_products.parquet`
3. Update `ESCI_DATASET_DIR` in `.env` if using non-standard location

### Tests failing with import errors
**Cause**: Running pytest without `PYTHONPATH=.`
**Fix**:
```bash
cd langchain_agent
export PYTHONPATH=.
pytest tests/unit/
```

### WebSocket connection refused in browser
**Cause**: Backend not running or frontend pointing to wrong URL
**Fix**:
1. Check backend running: `make dev-api` (should see "Uvicorn running on 0.0.0.0:8000")
2. Check frontend config (usually auto-proxied to localhost:8000)
3. Verify no other process using port 8000: `lsof -i :8000`
