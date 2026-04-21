# Agentic Hybrid Search — E-Commerce Product Search Agent

A production-grade LangGraph agent with two specialized capabilities:
**RAG Q&A** and **Product Comparison Writer**. Both modes share the same
data layer, LangGraph graph, and frontend. Uses Google Gemini for LLM
inference and embeddings, OpenSearch for hybrid vector + BM25 search, and
PostgreSQL for LangGraph checkpoints.

**Capabilities:**

- **RAG Q&A** — 6-intent classification, hybrid retrieval, LLM reranking, and a quality gate that retries on low-relevance hits. Data is the Amazon ESCI / Shopping Queries Dataset.
- **Product Comparison Writer** — 5 content types, classified automatically and routed to specialized generators:
  - **Social post** (100–300 words, 1 retrieval pass, ~6 s)
  - **Blog post** (1000–2000 words, 2 passes, ~20 s)
  - **Technical article** (800–1500 words, 3 passes, ~25 s)
  - **Tutorial** (~1000 words, 2 passes, ~20 s)
  - **Comprehensive docs** (2500+ words, 5 passes, ~50 s)

**Stack:**

- **Backend:** Python 3.13, FastAPI, LangGraph, LangChain
- **Frontend:** React 18, TypeScript, Tailwind, Zustand
- **Data layer:** OpenSearch 2.19.1 (HNSW + BM25) · PostgreSQL 16 (LangGraph checkpoints only)
- **LLM:** Google Gemini 3 Flash (generation) + Gemini 3.1 Flash Lite (classify/rerank) · `text-embedding-005` (embeddings)

---

## Quick Start

### Prerequisites

```bash
docker --version      # Docker Desktop
python3 --version     # Python 3.13+
node --version        # Node.js 18+
```

You'll also need a Google API key from <https://aistudio.google.com/apikey>
(set `GOOGLE_API_KEY` in `.env`).

### Setup (one-time)

```bash
cd langchain_agent
./scripts/setup.sh
```

Takes 10–20 min on first run:

1. Generates a secure `API_KEY`
2. Creates `.venv`, installs Python + frontend dependencies
3. Starts PostgreSQL and OpenSearch via Docker
4. Initializes the checkpoint DB and OpenSearch index
5. Validates the Google AI API key
6. Ingests an ESCI product sample (default 10 k)

### Start / Stop

```bash
./scripts/start.sh    # → http://localhost:5173
./scripts/stop.sh
```

Backend FastAPI runs on `:8000`, React frontend on `:5173` (Vite proxies
`/api` to the backend).

### Teardown

```bash
./scripts/teardown.sh
```

Removes running services, the Docker volumes, `.venv`, `node_modules`, and
log files. Keeps `.env` by default (prompted separately).

---

## Usage

### Web UI

Open <http://localhost:5173> and chat. The observability panel on the right
streams every pipeline stage in real time.

### CLI

```bash
source .venv/bin/activate
PYTHONPATH=. python main.py
```

### API

All endpoints require `X-API-Key` (or `?api_key=` query param):

```bash
curl -H "X-API-Key: $(grep ^API_KEY .env | cut -d= -f2)" \
  http://localhost:8000/api/health
```

The primary surface is the WebSocket endpoint under `/api/chat` — see
`api/routes/chat.py`. REST routes cover health (`/api/health`) and
conversation CRUD (`/api/conversations`).

### Example Queries

**RAG Q&A:**

```text
Find wireless headphones under $50
Show me Nike running shoes
Compare Sony WH-1000XM5 vs Bose QuietComfort 45
Make them waterproof                  ← refinement of prior search
Any cheaper options?                  ← follow-up
Summarize our conversation
```

**Product Comparison Writer:**

```text
Write a LinkedIn post about the top wireless earbuds of 2025
Create a buying guide for mechanical keyboards
Write a technical comparison of OLED vs LED monitors
Create a tutorial for choosing the right running shoe
Document all product categories in home electronics
```

---

## Configuration

Everything lives in `config.py` with `.env` overrides (see `.env.example`).

### Models

```bash
LLM_MODEL=gemini-3-flash-preview                   # generation
RERANKER_MODEL=gemini-3.1-flash-lite-preview       # reranking
QUERY_EVAL_MODEL=gemini-3.1-flash-lite-preview     # query evaluator
EMBEDDINGS_MODEL=models/text-embedding-005         # 768-dim embeddings
VECTOR_DIMENSION=768
LLM_TEMPERATURE=0
QUERY_EVAL_TEMPERATURE=0
QUERY_EVAL_MAX_TOKENS=1024
```

### Data stores

```bash
# OpenSearch (hybrid search)
OPENSEARCH_HOST=localhost
OPENSEARCH_PORT=9200
OPENSEARCH_INDEX_NAME=agentic_hybrid_search_docs
OPENSEARCH_USE_SSL=false

# PostgreSQL (LangGraph checkpoints only)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=langchain_agent
```

### Retrieval / reranking

```bash
RETRIEVER_K=10              # Final docs
RETRIEVER_FETCH_K=40        # Candidates before reranking
RETRIEVER_ALPHA=0.25        # Default α (evaluator usually overrides)
ENABLE_RERANKING=true
RERANKER_FETCH_K=40         # Candidates reranked
RERANKER_TOP_K=10           # Final top-K
ENABLE_QUERY_EVALUATION=true
QUERY_EVAL_TIMEOUT_MS=3000
```

### Content generation

```bash
ENABLE_CONTENT_TYPE_CLASSIFICATION=true
```

When enabled, documentation-style requests are routed to the Product
Comparison Writer; the content type classifier picks one of the five
generators. Disable for RAG-only deployments (writer requests fall back
to the RAG Q&A pipeline).

### Intent routing

The 6-intent classifier routes every turn:

| Intent | Pipeline | Examples |
|--------|----------|----------|
| `search` | RAG Q&A | "Find wireless headphones" |
| `comparison` | RAG Q&A (fast-path α=0.60) | "Compare Sony vs Bose" |
| `attribute_filter` | RAG Q&A (fast-path α=0.25) | "Blue running shoes size 10" |
| `refinement` | RAG Q&A (fast-path α=0.35) | "Make them waterproof" |
| `follow_up` | RAG Q&A (LLM-path α, context-aware) | "Any cheaper ones?" |
| `summary` | Summary node (no retrieval) | "Recap our conversation" |

Documentation-style asks ("write a guide", "create a comparison") are
detected during content-type classification inside the generator pipeline
rather than as a separate intent class.

---

## GCP Deployment

### Deploy to Cloud Run

```bash
./scripts/deploy.sh --project <GCP_PROJECT_ID>
```

This will:

1. Build the multi-stage Docker image locally
2. Push to Artifact Registry
3. Deploy to Cloud Run
4. Wire secrets (`GOOGLE_API_KEY`, `API_KEY`, OpenSearch creds) via Secret Manager
5. Connect to Cloud SQL via the built-in proxy

### One-time Cloud SQL + product ingestion

```bash
./scripts/gcp-init.sh --project <GCP_PROJECT_ID>
```

### Check Cloud Run logs

```bash
gcloud logging read resource.type=cloud_run_revision --project=<GCP_PROJECT_ID>
```

Useful signals:

- `POST /api/chat` 200 — successful request
- `AgentCompleteEvent` — generation finished
- `DocReplacer` — broken citation link auto-fixed
- `ERROR` — investigate

### Live Deployment

- **Service URL:** <https://agentic-hybrid-search-gyx7duaosq-uc.a.run.app>
- **Health:** `/api/health`
- **API docs:** `/docs`
- **OpenSearch:** hosted externally on GCP VM, ESCI products indexed
- **PostgreSQL:** Cloud SQL (checkpoints only)

---

## Features

### Conversational query rewriting

Resolves pronouns ("it", "those"), comparatives ("which is cheaper"), and
short attribute questions ("how much?") using conversation history before
retrieval. Skips expansion when the query already names a specific
brand/product. Emits `QueryExpansionEvent` for the observability panel.

### Context-validated refinement

"Make them waterproof" narrows the prior result set, not a fresh search.
A continuity score combines category matching and document-ID overlap:

- `> 0.7` — refine against prior products (α=0.35)
- `0.3–0.7` — ambiguous; ask the user to clarify
- `< 0.3` — pivot detected; reset prior context, treat as new search

### Quality gate with α adjustment

If the top reranker score is below 0.5 after reranking, the quality gate
adjusts α by ±0.3 (toward the opposite strategy) and retries retrieval
once. Prevents low-relevance outputs without an infinite loop.

### Link verification

Every citation URL is validated before reaching the LLM. Results cached
for 60 minutes (thread-safe); URLs timing out above 2 s are marked
invalid. Broken links are replaced with valid alternatives via
`doc_replacer.py`.

### Observable events

Full pipeline is instrumented with Pydantic-typed events streamed over
WebSocket:

| Event | Purpose |
|-------|---------|
| `intent_classification` | 6 intents + confidence + keyword/LLM path |
| `query_evaluation` | Assigned α, reasoning |
| `query_expansion` | Original vs rewritten query |
| `opensearch_query` | Full DSL, α, intent, applied filters |
| `hybrid_search_start` / `hybrid_search_result` | Candidates + scores |
| `reranker_start` / `reranker_progress` / `reranker_result` | Per-doc 0.0–1.0 |
| `quality_gate` | pass / retry / α adjusted |
| `content_type_classification` | Content type, target length, tone |
| `social_post_progress` / `blog_post_progress` / `article_progress` / `tutorial_progress` | Per-type generation progress |
| `llm_response_start` / `llm_response_chunk` | Token streaming |
| `content_complete` | Word/char counts |
| `doc_outline` / `doc_section_progress` / `doc_complete` | Comprehensive docs pipeline |
| `agent_complete` | Final response + citations |

Schemas in [api/schemas/events.py](api/schemas/events.py) must stay in sync
with [web/src/types/events.ts](web/src/types/events.ts).

---

## Architecture

### LangGraph Pipeline

Seven nodes wired into a graph:

```text
START → intent_classifier
  ├── search / comparison / attribute_filter /
  │   refinement / follow_up   → query_evaluator → retriever → reranker → quality_gate → agent → END
  │                                                                               │
  │                                                                               └─(retry)→ retriever
  ├── summary                  → summary → agent → END
  └── clarify (confidence<0.7) → agent (requests disambiguation) → END
```

Documentation requests bifurcate inside the generator pipeline via the
content-type classifier:

```text
documentation request → content_type_classifier
  ├── social_post          → social generator           (1 pass, ~6 s)
  ├── blog_post            → blog generator             (2 passes, ~20 s)
  ├── technical_article    → article generator          (3 passes, ~25 s)
  ├── tutorial             → tutorial generator         (2 passes, ~20 s)
  └── comprehensive_docs   → doc planner → gatherer → synthesizer (5 passes, ~50 s)
```

All generators stream: `LLMResponseStartEvent` (placeholder) →
`LLMResponseChunkEvent` (tokens) → `ContentCompleteEvent` (final counts).

### Hybrid Search

Reciprocal Rank Fusion combines vector and BM25 rankings:

```text
rrf_score = Σ 1 / (rank + k)      where k = 60
```

The **α parameter** controls weighting:

| α | Strategy | Best for |
|---|----------|----------|
| 0.0–0.15 | Pure lexical | ASINs, model numbers, UPCs |
| 0.15–0.40 | Lexical-heavy | Brand + category, attributes |
| 0.40–0.60 | Balanced | Feature combinations |
| 0.60–0.75 | Semantic-heavy | "Best for X", use-case queries |
| 0.75–1.0 | Pure semantic | Gift ideas, mood/style, exploration |

The query evaluator picks α per turn. If the top reranker score is still
below 0.5, the quality gate retries with α adjusted by ±0.3.

### State

`CustomAgentState` (see [agent_state.py](agent_state.py)) is a `total=False`
TypedDict — only `messages` is guaranteed. Always use `state.get(...)`.

| Added by | Fields |
|----------|--------|
| Classifier | `intent`, `confidence`, `user_query` |
| Query Evaluator | `alpha`, `intent_description` |
| Retriever | `retrieved_documents` |
| Reranker | `reranker_max_score`, `reranked_documents` |
| Quality Gate | `quality_gate_retried`, `alpha_adjusted_value` |
| Other | `thread_id`, `current_node`, `retrieved_products`, `citations` |

---

## Development

### Re-ingest ESCI products

```bash
PYTHONPATH=. python ingest_esci_products.py              # default 10 k sample
PYTHONPATH=. python ingest_esci_products.py --limit 500
PYTHONPATH=. python ingest_esci_products.py --all        # all ~1.2 M US products
PYTHONPATH=. python ingest_esci_products.py --resample   # force new sample
PYTHONPATH=. python ingest_esci_products.py --stats
```

Sample parquets are cached at `esci/shopping_queries_dataset/esci_products_sample_{N}.parquet`.

### Batch embedding via BigQuery

For large ingestions, `bigquery_batch_embeddings.py` offloads embedding
generation to BigQuery ML (`AI.GENERATE_EMBEDDING`) — ~15–30 min for
1.2 M products vs ~4.5 h serially. See the script's `--help` for the
one-time GCP setup and flags.

### Benchmarks

```bash
PYTHONPATH=. python benchmark_search.py
```

### Checkpoint maintenance

```bash
PYTHONPATH=. python checkpoint_maintenance.py   # garbage-collect old checkpoints
PYTHONPATH=. python checkpoint_optimizer.py     # tune checkpoint performance
```

### Testing

```bash
PYTHONPATH=. pytest tests/unit/           # no external deps, ~0.5 s
PYTHONPATH=. pytest tests/integration/    # requires Postgres + OpenSearch
PYTHONPATH=. pytest tests/e2e/            # requires deployed Cloud Run
PYTHONPATH=. pytest --cov=. --cov-report=html
```

See [tests/README.md](tests/README.md) for the full layout and fixtures.

### Lint / format / types

```bash
make lint            # pylint
make format          # black
make type-check      # mypy
```

### Frontend (from `web/`)

```bash
npm install
npm run dev          # vite dev server on :5173
npm run build        # tsc + vite build → dist/
npm run lint         # eslint
```

---

## Performance

| Operation | Typical |
|-----------|---------|
| Hybrid search (BM25 + kNN) | ~300–800 ms |
| LLM reranking (40 → 10) | ~1–3 s |
| Query evaluation (α + expansion) | ~300–500 ms |
| Quality Gate retry | +1–2 s |
| LLM response (streaming) | ~3–8 s |
| **Total per query** | **~6–15 s** local; ~10–30 s Cloud Run cold start |
| Link verification (cached) | ~50 ms / URL |

Optimizations: HNSW vector index · embedding cache (60-min TTL) ·
thread-safe link cache · streaming WebSocket generation · fast-path α
for comparison/attribute_filter/refinement to skip the LLM evaluator.

---

## Directory Layout

```text
langchain_agent/
├── scripts/
│   ├── setup.sh           # One-time local setup
│   ├── start.sh           # Start services
│   ├── stop.sh            # Stop services
│   ├── teardown.sh        # Full local cleanup
│   ├── logs.sh            # View backend/frontend logs
│   ├── deploy.sh          # GCP Cloud Run deploy
│   ├── gcp-init.sh        # Cloud SQL + product ingestion (one-time)
│   ├── gcp-teardown.sh    # Remove GCP resources
│   └── smoke_test.sh      # Post-deploy smoke test
├── api/
│   ├── main.py            # FastAPI lifespan
│   ├── routes/            # chat (WebSocket), conversations, health
│   ├── middleware/auth.py # Constant-time API key check
│   ├── schemas/events.py  # Pydantic event models
│   └── services/          # Observable agent wrapper
├── web/                   # React frontend (Zustand, WebSocket, ObservabilityPanel)
├── tests/                 # unit / integration / e2e (see tests/README.md)
├── main.py                # LangGraph agent core (~2,600 lines)
├── agent_state.py         # CustomAgentState TypedDict
├── config.py              # All configuration constants
├── exceptions.py          # Custom exception hierarchy
├── vector_store.py        # OpenSearchVectorStore + retriever (RRF)
├── reranker.py            # GeminiReranker (Pydantic-validated scoring)
├── content_generators.py  # 5-format content generation
├── embedding_cache.py     # Thread-safe query embedding cache
├── link_verifier.py       # URL validation w/ TTL cache
├── doc_replacer.py        # Broken-link replacement
├── retry_utils.py         # Tenacity decorators
├── logging_config.py      # structlog setup (JSON/console)
├── setup.py               # DB + index init + ingestion orchestration
├── ingest_esci_products.py
├── bigquery_batch_embeddings.py   # Parallel embedding via BigQuery ML
├── generate_embeddings.py         # Serial embedding fallback
├── benchmark_search.py            # Latency benchmarks
├── checkpoint_maintenance.py      # Checkpoint GC
├── checkpoint_optimizer.py        # Checkpoint tuning
├── migrate_to_hnsw.py             # Index migration utility
├── Dockerfile             # Multi-stage (Node + Python)
├── cloudbuild.yaml
├── Makefile
├── requirements.txt
├── requirements-dev.txt
└── pytest.ini
```

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'config'`

Bare imports require `PYTHONPATH=.`:

```bash
cd langchain_agent
PYTHONPATH=. python ingest_esci_products.py
PYTHONPATH=. pytest tests/unit/
```

### View logs

```bash
./scripts/logs.sh backend
./scripts/logs.sh frontend
./scripts/logs.sh all
```

### Backend won't start

```bash
grep ^API_KEY .env       # must exist
./scripts/logs.sh backend

# If the port is stuck:
lsof -ti :8000 | xargs kill -9
./scripts/start.sh
```

### Frontend shows connection error

```bash
curl http://localhost:8000/api/health
./scripts/logs.sh frontend
```

### Google AI API issues

```bash
echo $GOOGLE_API_KEY
python -c "from langchain_google_genai import GoogleGenerativeAIEmbeddings; \
  e = GoogleGenerativeAIEmbeddings(model='models/text-embedding-005'); \
  print(len(e.embed_query('test')))"
```

### Database issues

```bash
docker compose ps
# Restart:
cd .. && docker compose down && docker compose up -d postgres && cd langchain_agent
PYTHONPATH=. python setup.py
```

### Content stops streaming after generation completes

Backend logs should show `LLM STREAMING STARTED` followed by
`Emitting AgentCompleteEvent: N chars`. If they don't, pull latest,
`./scripts/stop.sh` and `./scripts/start.sh`.

### Verify the stack

```bash
docker compose ps                              # PostgreSQL + OpenSearch
curl http://localhost:9200/_cluster/health     # OpenSearch
curl http://localhost:8000/api/health          # Backend
```

---

## Security

- **API key** required on all endpoints (`X-API-Key` header)
- **Timing-attack resistant** comparison via `hmac.compare_digest`
- **Input validation** — thread IDs validated by regex
- **Thread safety** — all caches use `threading.Lock`
- **Rate limiting** — configurable via `slowapi`

---

## External References

- Amazon ESCI dataset: <https://github.com/amazon-science/esci-data>
- LangGraph: <https://langchain-ai.github.io/langgraph/>
- LangChain: <https://python.langchain.com/>
- OpenSearch: <https://opensearch.org/docs/latest/>
- OpenSearch Python client: <https://opensearch-project.github.io/opensearch-py/>
- Google Gemini: <https://ai.google.dev/>
- Google AI Studio: <https://aistudio.google.com/>
- Google Cloud Run: <https://cloud.google.com/run/docs>
