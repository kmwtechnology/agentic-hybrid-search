# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Agentic Hybrid Search** — a production-grade LangGraph RAG agent for Amazon ESCI e-commerce product search. Hybrid BM25 + vector retrieval with dynamic alpha per intent, reranking with quality gate, and real-time WebSocket streaming. Deployed on GCP Cloud Run with Google Gemini AI.

## Repository Layout

- `langchain_agent/` — Main application (all development happens here)
  - `main.py` — LangGraph agent core: intent classifier, query evaluator, retriever, reranker, quality gate, agent nodes (~2,600 lines)
  - `agent_state.py` — `CustomAgentState` TypedDict (~15 fields, only `messages` guaranteed)
  - `config.py` — All configuration constants loaded from `.env`
  - `exceptions.py` — Exception hierarchy, all inherit from `AgenticHybridSearchError`
  - `vector_store.py` — `OpenSearchVectorStore` + `OpenSearchRetriever` with RRF fusion
  - `reranker.py` — `GeminiReranker` with Pydantic-validated 0.0–1.0 scoring
  - `link_verifier.py` — URL validation with thread-safe cache (60-min TTL)
  - `embedding_cache.py` — Query embedding cache for performance
  - `retry_utils.py` — Retry logic utilities
  - `doc_replacer.py` — Document replacement logic
  - `logging_config.py` — Structured logging with structlog (JSON/console output)
  - `ingest_esci_products.py` — ESCI e-commerce product ingestion into OpenSearch (batched embedding, idempotent sampling, rate-limit pacing)
  - `setup.py` — Database and index initialization, API validation, data ingestion
  - `benchmark_search.py` — Performance benchmarking and latency analysis
  - `checkpoint_maintenance.py` — Checkpoint cleanup and garbage collection
  - `checkpoint_optimizer.py` — Checkpoint performance tuning utilities
  - `migrate_to_hnsw.py` — Index migration script to HNSW algorithm
  - `api/` — FastAPI backend
    - `api/main.py` — FastAPI app initialization
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
    - `web/vite.config.ts` — Vite build configuration
  - `tests/` — pytest suites: `unit/`, `integration/`, `e2e/` with ~100+ test cases
  - `scripts/` — `setup.sh`, `teardown.sh`, `start.sh`, `stop.sh`, `deploy.sh`, `gcp-init.sh`, `gcp-teardown.sh`
  - `Dockerfile` — Multi-stage Docker build for Cloud Run deployment
  - `Makefile` — Development commands (test, lint, format, dev server orchestration)
  - `.env.example` — Environment configuration template
  - `cloudbuild.yaml` — GCP Cloud Build configuration
  - `docker-compose.yml` — Local PostgreSQL + OpenSearch + Dashboards stack (in repo root)
- `web/` — Skeleton web app (separate from `langchain_agent/web/`, less developed)
- `esci/` — Amazon Shopping Queries Dataset (external data source, not actively developed)

## Pipeline

The agent handles product search and question answering via six intent classes:
- `search`, `comparison`, `attribute_filter`, `refinement`, `follow_up`, `summary`

Each query is classified, evaluated for optimal hybrid-search α, retrieved, reranked, gated on quality, and answered with citations — all streamed over WebSocket. See `ARCHITECTURE.md` for node-by-node detail.

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

# Full lifecycle scripts (non-interactive, no prompts)
./scripts/setup.sh            # one-time: ESCI clone, venv, deps, Docker, DB init, product ingestion
./scripts/teardown.sh         # remove everything (keeps .env by default)
./scripts/start.sh            # start Docker + backend + frontend
./scripts/stop.sh             # stop everything

# ESCI Product Ingestion (requires OpenSearch running via docker compose)
# Note: PYTHONPATH must be set for bare imports to work
PYTHONPATH=. python ingest_esci_products.py              # Ingest default 10K sample
PYTHONPATH=. python ingest_esci_products.py --limit 100 # Custom sample size (100 products)
PYTHONPATH=. python ingest_esci_products.py --all       # Ingest all US products (~1.2M)
PYTHONPATH=. python ingest_esci_products.py --resample  # Force re-sample even if cached
PYTHONPATH=. python ingest_esci_products.py --stats     # Show current index statistics

# Benchmarking & Performance Analysis
PYTHONPATH=. python benchmark_search.py                 # Run search latency benchmarks

# Checkpoint Maintenance
PYTHONPATH=. python checkpoint_maintenance.py           # Clean up old checkpoints
PYTHONPATH=. python checkpoint_optimizer.py             # Optimize checkpoint performance

# Testing — PYTHONPATH=. is required (modules use bare imports like `from config import ...`)
PYTHONPATH=. pytest tests/unit/                    # unit tests (~0.5s, no services needed)
PYTHONPATH=. pytest tests/integration/             # integration tests (needs PostgreSQL + OpenSearch)
PYTHONPATH=. pytest tests/e2e/                     # end-to-end tests (full system)
PYTHONPATH=. pytest tests/unit/test_reranker.py    # single file
PYTHONPATH=. pytest tests/ -m phase1               # by marker
PYTHONPATH=. pytest tests/ -k "test_auth"          # by name pattern
PYTHONPATH=. pytest --cov=. --cov-report=html      # with coverage

# Legacy standalone tests (older test interface)
make test-reranker
make test-hybrid
make test-query

# Linting & formatting
make lint                     # pylint
make format                   # black
make type-check               # mypy

# Frontend (from langchain_agent/web/)
npm install
npm run dev                   # vite dev server on :5173
npm run build                 # tsc + vite build → dist/
npm run lint                  # eslint
npm run test                  # frontend tests (if configured)

# Deployment
./scripts/deploy.sh --project <GCP_PROJECT_ID>
./scripts/gcp-init.sh --project <GCP_PROJECT_ID>  # first-time: Cloud SQL tables + product ingestion
./scripts/gcp-teardown.sh --project <GCP_PROJECT_ID>  # cleanup GCP resources
```

## Architecture

### LangGraph Pipeline Flow (RAG Q&A Mode)

```
Intent Classifier → Query Rewriter → Query Evaluator → Retriever → Reranker → Quality Gate → Agent
```

**Node Details:**

- **Intent Classifier**: 6 classes — `search` (product discovery), `comparison` (compare products), `attribute_filter` (filter by brand/color/size), `refinement` (add constraint to prior search), `follow_up` (vague continuation), `summary` (summarize results). Keyword fast-path + LLM fallback. Confidence < 0.7 triggers clarification request.

- **Query Rewriter** (`_expand_vague_query`): Resolves follow-up references before search. Detects pronouns ("does it", "those"), comparatives ("which is cheaper"), short attribute questions ("how much?"), and action requests without context. Uses LLM to rewrite with product names from conversation history. Skips expansion when query contains a specific brand/product topic (e.g., "Sony WH-1000XM5"). Emits `QueryExpansionEvent` for observability.

- **Query Evaluator**: Determines optimal hybrid search balance via `dynamic alpha`. Fast-path for comparison (α=0.60), attribute_filter (α=0.25), and refinement (α=0.35). LLM path for search/follow_up. Alpha guide uses e-commerce vocabulary:
  - Exact model numbers/ASINs → pure lexical (α=0.0)
  - Attribute filter (brand/color/size) → lexical-heavy (α=0.25)
  - Refinement (constraint on prior search) → lexical-heavy with context (α=0.35)
  - Comparison → semantic-heavy (α=0.60)
  - Activity-based queries → balanced (α=0.5–0.65)
  - Conceptual needs → semantic-heavy (α=0.7–0.85)
  - Gift ideas/exploration → pure semantic (α=1.0)

- **Retriever**: Hybrid search combining vector embeddings + BM25 lexical search, fused via Reciprocal Rank Fusion (k=60). Returns `retrieved_documents` + `user_query` to state.

- **Reranker**: Dedicated node that scores/reorders documents via LLM. Assigns relevance scores (0.0–1.0) and sets `reranker_max_score` in state.

- **Quality Gate**: If `reranker_max_score < 0.5` and not yet retried, adjusts alpha ±0.3 and retries retriever→reranker. Otherwise continues to agent. Prevents low-quality outputs.

- **Agent**: Generates conversational response with product citations. For ESCI products (no `url` metadata), citations use Amazon canonical URLs derived from product ASIN (`https://www.amazon.com/dp/{product_id}`). Citations deduplicated by URL, filtered by minimum reranker relevance (0.10).

### Observable Events

Pipeline emits typed Pydantic events over WebSocket for real-time UI visualization:

- `SearchProgressEvent` — Search initiated and in progress
- `RerankerProgressEvent` — Reranking results
- `QualityGateEvent` — Quality gate decision (pass/retry/alpha adjusted)
- `QueryExpansionEvent` — Vague query expanded with context
- `OpenSearchQueryEvent` — Full query details (DSL, alpha, intent, applied filters)
- `LLMResponseChunkEvent` — Token-by-token streaming output
- `ClarificationRequestedEvent` — Low-confidence intent requires user clarification
- `ClarificationResolvedEvent` — Clarification provided by user

**Critical**: Event schemas in `api/schemas/events.py` must stay in sync with frontend types in `web/src/types/events.ts`. Events are assigned to their specified `node` step (e.g., `OpenSearchQueryEvent` with `node="retriever"` always goes to the retriever step, even if emitted after another node starts).

### Tech Stack

| Layer | Technology |
|-------|-----------|
| LLM (Generation) | Google Gemini 3 Flash (preview) |
| LLM (Classification/Reranking) | Gemini 3.1 Flash Lite (preview) |
| Embeddings | Gemini Embedding 001 (768-dim) |
| Agent Framework | LangGraph + LangChain |
| Vector DB | OpenSearch 2.19.1 (HNSW knn + BM25) |
| Checkpoints | PostgreSQL 16 (LangGraph checkpoints) |
| API | FastAPI + WebSocket |
| Frontend | React 18 + TypeScript + Tailwind + Zustand |
| Deployment | GCP Cloud Run (multi-stage Docker build) |

### Key Patterns

- **Bare imports & PYTHONPATH**: All Python modules use bare imports (`from config import ...`, `from exceptions import ...`). This requires `PYTHONPATH=.` when running Python scripts from `langchain_agent/`. Set it explicitly: `PYTHONPATH=. python script.py` or `export PYTHONPATH=. && python script.py`. This includes: `pytest`, `ingest_esci_products.py`, `main.py`, and any custom scripts. Omitting it causes `ModuleNotFoundError`.

- **State access**: `CustomAgentState` uses `total=False` with ~15 fields. Only `messages` is guaranteed to exist. Always use `state.get("field", default)`, never `state["field"]` for optional fields.
  - **Required**: `messages` (BaseMessage[])
  - **Classifier adds**: `intent`, `confidence`, `user_query`
  - **Query Evaluator adds**: `alpha`, `intent_description`
  - **Retriever adds**: `retrieved_documents`
  - **Reranker adds**: `reranker_max_score`, `reranked_documents`
  - **Quality Gate adds**: `quality_gate_retried`, `alpha_adjusted_value`
  - **Other**: `thread_id`, `current_node`, `retrieved_products`, `citations`

- **Observable events**: Pipeline emits Pydantic-typed events over WebSocket for real-time UI visualization. Event schemas in `api/schemas/events.py` must stay in sync with frontend types in `web/src/types/events.ts`. Events are assigned to their specified `node` step (e.g., `OpenSearchQueryEvent` with `node="retriever"` always goes to the retriever step, even if emitted after another node starts). Frontend `SearchDetails` component displays `OpenSearchQueryEvent` with query, alpha, intent, and applied filters in Knowledge Search stage.

- **Hybrid search**: Vector + full-text results fused via Reciprocal Rank Fusion (k=60). The `alpha` parameter controls weighting (0.0 = pure lexical/BM25, 1.0 = pure semantic/vector).

- **Product deduplication**: `OpenSearchRetriever.collapse_by_document()` removes duplicate product chunks from results. Applied automatically for `esci_products` collection.

- **No chunking for products**: ESCI products are indexed as whole units (not chunked). Controlled by `CHUNKING_STRATEGY` in config.py. Products are short (50-500 words) and don't benefit from 1000-char chunking.

- **Dual-mapped attributes**: `product_brand` and `product_color` are mapped as both `text` (for BM25 search) and `keyword` (for faceting/filtering). Use `.keyword` suffix for aggregations.

- **Faceting**: `OpenSearchVectorStore.get_facets()` returns aggregated attribute values (brands, colors) for the collection.

- **Error hierarchy**: Custom exceptions in `exceptions.py` — all inherit from `AgenticHybridSearchError`. Used by `reranker.py`, `vector_store.py`, `retry_utils.py`, and test files.

- **Auth**: API_KEY env var required; validated via middleware on protected routes (`api/middleware/auth.py`). Generated by `setup.sh`, also available as VITE_API_KEY for frontend.

## ESCI Product Ingestion

The `ingest_esci_products.py` script loads Amazon ESCI e-commerce products from local parquet files into OpenSearch:

### Data Flow
1. **Load**: Reads `esci/shopping_queries_dataset/shopping_queries_dataset_products.parquet` (1.8M+ products)
2. **Filter**: Selects English (US) products only (`product_locale == "us"`)
3. **Sample**: Deterministic sampling with `random_state=42` for reproducibility
4. **Cache**: Saves sample as `esci/shopping_queries_dataset/esci_products_sample_{limit}.parquet` (idempotent — cached parquets reused on subsequent runs)
5. **Concatenate**: Combines product title + description + bullet points into a single document (no chunking — products are 50-500 words)
6. **Embed**: Batched via `embed_documents()` (100 products per API call). Rate-limit pacing: on first 429, parses API's "retry in Xs" delay, then adds inter-batch throttling (25% buffer) for remaining batches
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

## Scripts

### `setup.sh` — Fully non-interactive one-time setup
Runs end-to-end without prompts or manual intervention:
1. Checks prerequisites (Docker, Python 3.13, Node.js)
2. Clones ESCI dataset from GitHub (~1GB) if not present
3. Creates `.venv` at `langchain_agent/.venv`, installs Python dependencies
4. Installs frontend `node_modules`
5. Starts Docker containers (PostgreSQL, OpenSearch, OpenSearch Dashboards)
6. Runs `setup.py` (DB init, index creation, API validation, product ingestion)

The `.env` file is created from `.env.example` if missing (with auto-generated `API_KEY`), but `GOOGLE_API_KEY` must be set manually before running. Uses `set -e` with proper `if`-wrapped commands for error handling.

### `teardown.sh` — Full cleanup
Removes all installed components. Keeps `.env` by default (separate prompt). Removes:
- Running services (ports 8000, 5173)
- Docker containers and data volumes
- Python virtual environment (`langchain_agent/.venv`)
- `node_modules` and log files

### `start.sh` — Start local dev environment
Starts Docker services, backend FastAPI server, and React frontend. Serves frontend on :5173 with automatic API proxy to backend on :8000.

### `stop.sh` — Stop all services
Gracefully stops Docker containers and terminates backend/frontend processes.

### `deploy.sh` — GCP Cloud Run deployment
Builds and deploys the application to Google Cloud Run with:
- Multi-stage Docker build (optimized image size)
- Cloud SQL (PostgreSQL) provisioning
- OpenSearch cluster setup
- Secret Manager integration for API keys and credentials
- Automatic scaling (0 to N replicas)

### `gcp-init.sh` — First-time GCP setup
One-time initialization for GCP Cloud Run deployment:
1. Creates Cloud SQL instance (PostgreSQL 16)
2. Initializes database schema and LangGraph checkpoints table
3. Runs product ingestion to Cloud SQL + OpenSearch
4. Validates Google AI API key and endpoints

### `gcp-teardown.sh` — GCP resource cleanup
Removes all GCP resources created by `gcp-init.sh` and `deploy.sh`:
- Cloud Run service
- Cloud SQL instance and backups
- OpenSearch domain
- Artifact Registry images
- Secret Manager secrets

## CI/CD — GitHub Actions Workflow

### Overview

Automated build and deployment pipeline using GitHub Actions:
- **Pull Requests** → Docker build test (validates image builds)
- **Merge to `main`** → Docker build + push to Artifact Registry + deploy to Cloud Run

### Workflows

1. **`.github/workflows/test.yml`** — Runs on every PR/push
   - Backend unit tests + integration tests (with PostgreSQL + OpenSearch)
   - Backend linting (flake8, black, isort, mypy)
   - E2E tests (Playwright)
   - Coverage reporting

2. **`.github/workflows/build-deploy.yml`** — Runs on main branch
   - Docker build (cache-enabled for speed)
   - Push to `us-central1-docker.pkg.dev/<PROJECT_ID>/agentic-hybrid-search/agentic-hybrid-search:latest`
   - Deploy to Cloud Run (blue-green deployment with health check)
   - Smoke tests (verify `/health` endpoint)
   - Promote to production (100% traffic)

### One-Time Setup: Workload Identity Federation

GitHub Actions uses Workload Identity Federation (WIF) for secure GCP authentication (no long-lived service account keys).

**Step 1: Create GCP service account**
```bash
PROJECT_ID=gen-lang-client-0250737934
REGION=us-central1

gcloud iam service-accounts create github-actions \
  --display-name="GitHub Actions CI/CD" \
  --project=$PROJECT_ID

# Grant necessary roles
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-actions@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-actions@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.developer"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-actions@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"
```

**Step 2: Configure WIF pool and provider**
```bash
PROVIDER_ID=github
POOL_ID=github-actions

# Create identity pool
gcloud iam workload-identity-pools create $POOL_ID \
  --project=$PROJECT_ID \
  --location=global \
  --display-name="GitHub Actions"

# Create OIDC provider
gcloud iam workload-identity-pools providers create-oidc $PROVIDER_ID \
  --project=$PROJECT_ID \
  --location=global \
  --workload-identity-pool=$POOL_ID \
  --display-name="GitHub" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.aud=assertion.aud,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
  --issuer-uri="https://token.actions.githubusercontent.com"

# Get provider resource name
PROVIDER=$(gcloud iam workload-identity-pools providers describe $PROVIDER_ID \
  --project=$PROJECT_ID \
  --location=global \
  --workload-identity-pool=$POOL_ID \
  --format="value(name)")
echo $PROVIDER  # Save this as WIF_PROVIDER secret
```

**Step 3: Create service account credentials configuration**
```bash
# Get the service account email
SA_EMAIL="github-actions@$PROJECT_ID.iam.gserviceaccount.com"

# Create a credential configuration file for WIF
gcloud iam service-accounts add-iam-policy-binding $SA_EMAIL \
  --project=$PROJECT_ID \
  --role="roles/iam.workloadIdentityUser" \
  --subject="principalSet://iam.googleapis.com/projects/$PROJECT_ID/locations/global/workloadIdentityPools/$POOL_ID/attribute.repository/kmwtechnology/agentic-hybrid-search"
```

**Step 4: Add GitHub Secrets**
Add to repository `Settings` → `Secrets and variables` → `Actions`:
- `WIF_PROVIDER` — The provider resource name from Step 2
- `WIF_SERVICE_ACCOUNT` — `github-actions@gen-lang-client-0250737934.iam.gserviceaccount.com`

### Development Workflow

```bash
# Create feature branch
git checkout -b feature/my-feature

# Make changes
vim langchain_agent/main.py
git add langchain_agent/main.py
git commit -m "feat: add feature"

# Create PR (triggers test.yml)
git push origin feature/my-feature
# → GitHub Actions runs tests, linting, type checks

# Merge to main (triggers build-deploy.yml)
# → Docker build, push to Artifact Registry, deploy to Cloud Run
# → Smoke tests verify deployment
# → 100% traffic promotion

git checkout main
git merge feature/my-feature
git push origin main
# → Deployment automated via GitHub Actions
```

### Local Development (unchanged)

Local development with Docker Compose works as before:
```bash
docker compose up -d              # PostgreSQL + OpenSearch
cd langchain_agent
make dev                           # FastAPI + React frontend
# Visit http://localhost:5173
```

### Monitoring Deployments

**GitHub Actions**:
```bash
# View workflow runs
https://github.com/kmwtechnology/agentic-hybrid-search/actions

# View specific workflow
https://github.com/kmwtechnology/agentic-hybrid-search/actions/workflows/build-deploy.yml
```

**Cloud Run**:
```bash
# View logs
gcloud run services logs read agentic-hybrid-search \
  --region=us-central1 \
  --project=gen-lang-client-0250737934 \
  --limit 50

# Check service status
gcloud run services describe agentic-hybrid-search \
  --region=us-central1 \
  --project=gen-lang-client-0250737934
```

### Troubleshooting

**If deployment fails:**
1. Check GitHub Actions logs: https://github.com/kmwtechnology/agentic-hybrid-search/actions
2. Look for step failure (Docker build, push, or deploy)
3. Check Cloud Run logs for startup errors
4. Verify WIF secrets are correctly configured

**Common issues:**
- WIF secrets missing → Add `WIF_PROVIDER` and `WIF_SERVICE_ACCOUNT` to GitHub Secrets
- Artifact Registry auth failure → Check WIF service account has `artifactregistry.writer` role
- Cloud Run startup timeout → Check container logs for database/OpenSearch connection errors

## Testing

- **Python version**: 3.13 required (`minversion = 3.13` in pytest.ini)
- **Test markers**: `phase1`, `phase2`, `phase3`, `unit`, `integration`, `e2e`, `slow`, `auth`, `search`, `rerank`, `websocket`, `database`, `content_generation`
- **CI runs** on push/PR to `main`/`develop` for paths under `langchain_agent/`
- **Unit tests** (~100+ tests): No external dependencies, all mocked via `conftest.py` fixtures (~0.5s)
- **Integration tests**: Require running PostgreSQL 16 + OpenSearch + `GOOGLE_API_KEY`
- **E2E tests**: Full system tests with real API calls and WebSocket streaming
- **Test organization**:
  - `tests/unit/` — Isolated component tests (intent classifier, reranker, query evaluator, etc.)
  - `tests/integration/` — Service integration (retriever + reranker, full pipeline)
  - `tests/e2e/` — End-to-end scenarios (all intents, conversation flows)

## Environment

Copy `langchain_agent/.env.example` to `langchain_agent/.env`.

### Required Variables
- **`GOOGLE_API_KEY`** — required for LLM/embeddings (from https://aistudio.google.com/apikey)

### Database (Checkpoints)
- `POSTGRES_USER=postgres`
- `POSTGRES_PASSWORD=postgres`
- `POSTGRES_HOST=localhost`
- `POSTGRES_PORT=5432`
- `POSTGRES_DB=langchain_agent`

### OpenSearch (Vector Search)
- `OPENSEARCH_HOST=localhost`
- `OPENSEARCH_PORT=9200`
- `OPENSEARCH_USER=` (empty for local Docker)
- `OPENSEARCH_PASSWORD=` (empty for local Docker)
- `OPENSEARCH_USE_SSL=false`
- `OPENSEARCH_VERIFY_CERTS=false`
- `OPENSEARCH_INDEX_NAME=agentic_hybrid_search_docs`

### LLM & Embeddings Model Selection
- `LLM_MODEL=gemini-3-flash-preview` — Main generation model (3x faster than 2.5-flash)
- `LLM_TEMPERATURE=0` — Output determinism (0 = deterministic, 1.0 = creative)
- `EMBEDDINGS_MODEL=models/gemini-embedding-001` — Embedding model (stable GA, no re-embedding needed)
- `RERANKER_MODEL=gemini-3.1-flash-lite-preview` — Reranking model (45% faster output, 2.5x lower TTFT)
- `QUERY_EVAL_MODEL=gemini-3.1-flash-lite-preview` — Query evaluator model
- `VECTOR_DIMENSION=768` — Gemini embedding output dimensionality

### Retrieval & Reranking
- `RETRIEVER_K=4` — Final documents to return
- `RETRIEVER_FETCH_K=30` — Candidates to fetch before reranking
- `RETRIEVER_ALPHA=0.25` — Default hybrid search balance (0.0=lexical, 1.0=semantic)
- `ENABLE_RERANKING=true` — Always enabled for best quality
- `RERANKER_FETCH_K=15` — Candidates to rerank
- `RERANKER_TOP_K=4` — Final documents after reranking

### Query & Context Management
- `ENABLE_QUERY_EVALUATION=true` — Dynamic alpha based on query type
- `QUERY_EVAL_TIMEOUT_MS=3000` — Timeout for query evaluation
- `ENABLE_COMPACTION=true` — Smart context management for long conversations
- `MAX_CONTEXT_TOKENS=3000` — Conservative estimate for context window
- `DEFAULT_THREAD_ID=default_thread` — Default conversation ID

### API & Security
- `API_KEY=your-secure-api-key-here` — API authentication (auto-generated by setup.sh)
- `CORS_ORIGINS=` — Comma-separated allowed origins (leave empty for local, set for Cloud Run)

### ESCI Data Configuration
- `ESCI_DATASET_DIR=../esci/shopping_queries_dataset` — Path to parquet files
- `ESCI_PRODUCT_LOCALE=us` — Filter products by locale
- `ESCI_INGEST_LIMIT=10000` — Default sample size

### Logging
- `LOG_LEVEL=INFO` — Options: DEBUG, INFO, WARNING, ERROR
- `LOG_FORMAT=console` — Options: console (dev), json (production)

### Frontend Configuration (Auto-set by setup.sh)
- `VITE_API_KEY` — Matches API_KEY, used by frontend
- `VITE_API_URL` — Backend URL for frontend (auto-configured for local dev, optional for Cloud Run)

### LangSmith Observability (Optional)
- `LANGSMITH_API_KEY=` — Get from https://smith.langchain.com
- `LANGSMITH_PROJECT=agentic-hybrid-search` — LangSmith project name (for tracing and debugging)

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

### ESCI dataset not found or parquet files missing
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

### npm install fails in web/ directory
**Cause**: Node.js version mismatch or dependency issues
**Fix**:
1. Check Node.js version: `node --version` (should be 18+)
2. Clear npm cache: `npm cache clean --force`
3. Delete node_modules: `rm -rf node_modules package-lock.json`
4. Reinstall: `npm install`
