# Agentic Hybrid Search

A production-grade **LangGraph RAG agent** for Amazon ESCI e-commerce product search
with hybrid search (vector + BM25), LLM-based reranking, intent routing, and
real-time streaming. Deployed on **GCP Cloud Run** with Google Gemini AI.

## Quick Start

### Local Development

```bash
cd langchain_agent
./scripts/setup.sh    # One-time setup (10-20 min)
./scripts/start.sh    # Start backend + frontend → http://localhost:5173
```

### Cloud Deployment (GCP)

```bash
cd langchain_agent
./scripts/deploy.sh --project <GCP_PROJECT_ID>
```

Deploys to Cloud Run with Cloud SQL (PostgreSQL), OpenSearch (document search),
Secret Manager, and Artifact Registry. Scales to zero when idle.

## What is It?

A conversational RAG agent powered by Google Gemini AI for e-commerce product discovery:

- **Product Search** - Hybrid search combining vector embeddings + full-text (BM25)
- **Intent Classification** - 3 intents (question, summary, follow_up) with keyword fast-path + LLM fallback
- **LangGraph Pipeline** - Deterministic graph-based orchestration with dynamic alpha refinement
- **Hybrid Search** - Vector + full-text search with Reciprocal Rank Fusion (RRF, k=60)
- **LLM-Based Reranking** - Gemini Flash Lite reranker for relevance scoring (0.0-1.0)
- **Dynamic Alpha** - Query-aware lexical/semantic balance (α = 0.0 pure lexical, 1.0 pure semantic)
- **Alpha Refinement** - If max score < 0.5, retries with opposite search strategy
- **Real-Time Streaming** - Token-by-token output via WebSocket with cancellation support
- **Observability Panel** - Live visualization of intent classification, search scores, reranking results
- **ESCI Data** - 1.8M+ Amazon product listings with deterministic sampling for reproducibility

## Architecture

### System Overview

```mermaid
flowchart TB
    subgraph UI["User Interfaces"]
        WEB["Web UI<br/>(React + TypeScript)"]
        API["FastAPI<br/>(WebSocket)"]
    end

    subgraph Pipeline["LangGraph Pipeline"]
        IC["Intent Classifier<br/>(question/summary/follow_up)"]
        QE["Query Evaluator<br/>Set α balance"]
        RET["Retriever<br/>Hybrid Search"]
        REFINE["Alpha Refiner<br/>(bidirectional retry)"]
        RERANK["Reranker<br/>(LLM scoring)"]
        AGENT["LLM Agent<br/>(response generation)"]
    end

    subgraph Search["Hybrid Search"]
        VS["Vector Search<br/>(768-dim Gemini)"]
        BM25["BM25 Lexical<br/>(OpenSearch)"]
        RRF["RRF Fusion<br/>(k=60)"]
    end

    subgraph Storage["Data Layer"]
        PRODUCTS["ESCI Products<br/>(chunked + embedded)"]
        IDX["OpenSearch<br/>(vector + BM25)"]
        CHECKPOINTS["PostgreSQL<br/>(conversation state)"]
    end

    subgraph GoogleAI["Google Gemini"]
        LLM["gemini-2.5-flash<br/>(generation)"]
        CLASSIFIER["gemini-2.5-flash-lite<br/>(intent + reranking)"]
        EMB["gemini-embedding-001<br/>(768-dim)"]
    end

    UI --> IC
    IC --> QE
    QE --> RET
    RET --> Search
    VS --> RRF
    BM25 --> RRF
    RRF --> REFINE
    REFINE --> RERANK
    RERANK --> AGENT
    AGENT --> LLM
    AGENT --> UI
    PRODUCTS --> IDX
    PRODUCTS --> EMB
    AGENT --> CHECKPOINTS
    CLASSIFIER --> IC
    CLASSIFIER --> RERANK
```

### Agent Pipeline Flow

```text
intent_classifier
  ├── question         → query_evaluator (set α) → retriever (hybrid search) → alpha_refiner → reranker → agent
  ├── summary          → summarize conversation history → agent response
  └── follow_up        → expand with context → query_evaluator → retriever → alpha_refiner → reranker → agent

Key Decision Points:
  - Query Evaluator: Classifies query type and sets optimal α (0.0-1.0)
  - Alpha Refiner: If max relevance < 0.5, retry with opposite strategy (lexical → semantic or vice versa)
  - Reranker: LLM-based scoring of top-K documents (0.0-1.0 relevance)
```

### Search Balance (Alpha Parameter)

The Query Evaluator dynamically sets `α` based on query characteristics:

| α Range | Strategy | Best For |
|---------|----------|----------|
| 0.0-0.2 | Pure Lexical | Brand names, product IDs, specific models |
| 0.2-0.4 | Lexical-Heavy | Specific attributes, colors, materials |
| 0.4-0.6 | Balanced | Feature combinations ("wireless AND blue") |
| 0.6-0.8 | Semantic-Heavy | Use-case queries ("headphones for running") |
| 0.8-1.0 | Pure Semantic | Conceptual queries ("best outdoor gear") |

If initial search scores are low (max < 0.5), Alpha Refiner automatically
retries with opposite strategy to ensure good results.

## Tech Stack

| Category | Technology | Purpose |
|----------|-----------|---------|
| **LLM** | Google Gemini 2.5 Flash | Response generation |
| **Intent Classifier** | Gemini 2.5 Flash Lite | Intent detection (question/summary/follow_up) |
| **Reranker** | Gemini 2.5 Flash Lite | LLM-based relevance scoring (0.0-1.0) |
| **Embeddings** | Gemini Embedding 001 | 768-dimensional product chunk vectors |
| **Vector Database** | OpenSearch 2.19.1 | HNSW knn_vector index + BM25 lexical |
| **Search Algorithm** | Reciprocal Rank Fusion | Hybrid fusion of vector + lexical scores |
| **Checkpoints** | PostgreSQL 16 | LangGraph state checkpoints + conversation history |
| **Agent Framework** | LangGraph + LangChain | Graph-based pipeline with typed state |
| **Backend API** | FastAPI + WebSocket | REST/WebSocket with real-time streaming |
| **Frontend** | React 18 + TypeScript + Tailwind | Web UI with Zustand state management |
| **Data Source** | ESCI Dataset | 1.8M+ Amazon product listings (parquet) |
| **Deployment** | GCP Cloud Run | Serverless auto-scaling container |
| **Containerization** | Docker (multi-stage) | Frontend (Node) + Backend (Python) build |

## Example Queries

**Product Search** (question intent):

```text
Find me wireless headphones under $100
Show me blue running shoes for women
What waterproof backpacks do you have?
```

**Refinement** (follow_up intent with context expansion):

```text
How about ones from Nike?         → expands to full previous query context
Can you show me the red ones?     → auto-expands color filter
```

**Conversation Summary** (summary intent):

```text
Summarize what we've discussed so far
```

**Search Strategy Adaptation**:

The agent automatically adjusts search strategy based on query:
- `"Samsung Galaxy S21"` → lexical focus (α=0.1) for brand/model matching
- `"phone for outdoor photography"` → semantic focus (α=0.8) for use-case understanding
- If results are poor, Alpha Refiner retries with opposite strategy

## Observability Panel

The web UI includes a real-time observability panel showing each pipeline stage:

- **Intent Classification** - Detected intent with confidence score and keyword/LLM path
- **Query Evaluation** - Assigned α value (lexical/semantic balance) and reasoning
- **Hybrid Search** - Vector scores, BM25 scores, RRF fusion results
- **Alpha Refinement** - Shows if retry occurred (due to low max score < 0.5)
- **Reranker Results** - Per-document relevance scores (0.0-1.0) and top-K selection
- **LLM Generation** - Token-by-token output streaming with timing metrics
- **Timing Breakdown** - Latency per pipeline node (search, reranking, generation)
- **Execution Status** - Running/complete/skipped indicators for each node

Developers can inspect intermediate search scores, reranking decisions, and
reason about why certain products were ranked higher than others.

## Key Techniques

| Technique | Description |
|-----------|-------------|
| **Intent Classification** | 3-intent detection (question/summary/follow_up) with keyword fast-path + LLM fallback |
| **Query Expansion** | Enriches vague follow-ups with full conversation history for context |
| **Dynamic Alpha** | Query evaluator analyzes query type and sets optimal α (0.0-1.0) for lexical/semantic balance |
| **Reciprocal Rank Fusion** | Fuses vector + BM25 rankings: `score = Σ 1/(rank + k)` where k=60 |
| **LLM-Based Reranking** | Gemini Flash Lite scores query-product relevance on 0.0-1.0 scale |
| **Alpha Refinement** | If max reranker score < 0.5, automatically retries with opposite search strategy |
| **Embedding Cache** | Caches query embeddings (60-min TTL) to reduce embedding API calls |
| **Deterministic Sampling** | ESCI products sampled with `random_state=42` for reproducibility across runs |
| **Idempotent Ingestion** | Cached sample parquets ensure product dataset ingestion is deterministic and fast on re-runs |
| **Streaming Responses** | WebSocket token-by-token generation with cancellation support |
| **Observability Events** | Real-time Pydantic-typed events for search, reranking, and generation stages |

## Directory Structure

```text
agentic-hybrid-search/
├── README.md                     # This file
├── docker-compose.yml            # PostgreSQL + OpenSearch (local dev)
├── langchain_agent/
│   ├── scripts/
│   │   ├── setup.sh              # One-time: Docker + venv + DB init + ingestion
│   │   ├── start.sh              # Start backend + frontend
│   │   ├── stop.sh               # Stop all services
│   │   ├── deploy.sh             # GCP Cloud Run deployment
│   │   ├── gcp-init.sh           # Cloud SQL + product ingestion (one-time)
│   │   ├── gcp-teardown.sh       # Remove all GCP resources
│   │   └── teardown.sh           # Full local cleanup
│   ├── api/                      # FastAPI backend
│   │   ├── main.py               # API routes + WebSocket
│   │   ├── schemas/events.py     # Observable event models
│   │   └── services/             # Observable agent wrapper
│   ├── web/                      # React frontend
│   │   └── src/components/
│   │       └── ObservabilityPanel/  # Real-time pipeline visualization
│   ├── main.py                   # LangGraph agent (EcommerceSearchAgent)
│   ├── config.py                 # Configuration constants (ESCI-focused)
│   ├── vector_store.py           # Hybrid search + RRF fusion
│   ├── reranker.py               # LLM-based relevance scoring
│   ├── agent_state.py            # LangGraph CustomAgentState TypedDict
│   ├── setup.py                  # Database initialization
│   ├── ingest_esci_products.py   # ESCI product ingestion (deterministic sampling)
│   ├── embedding_cache.py        # Query embedding cache
│   ├── link_verifier.py          # URL validation with TTL cache
│   ├── Dockerfile                # Multi-stage build (Node + Python)
│   └── tests/                    # pytest suites (unit, integration, e2e)
├── esci/                         # Amazon ESCI dataset (gitignored, local only)
│   └── shopping_queries_dataset/
│       └── shopping_queries_dataset_products.parquet  # 1.8M+ products
└── web/                          # Skeleton web app (less developed)
```

## Search Optimization

### Hybrid Search Strategy

Products are indexed with both vector embeddings and lexical (BM25) tokens:

- **Vector Search**: 768-dim Gemini embeddings capture semantic meaning
  - Best for: "phone for hiking", "comfortable work shoes"
  - Fast: ~200-500ms via HNSW index

- **Lexical Search**: BM25 tokenization captures exact matches
  - Best for: "Samsung Galaxy", "Nike Air Max", "color:blue"
  - Fast: ~100-300ms via Lucene analyzer

- **RRF Fusion**: Reciprocal Rank Fusion (k=60) combines both
  - Normalizes scores from both methods
  - Formula: `score = Σ 1/(rank + 60)` for each result
  - Balances precision + recall

### Dynamic Alpha Refinement

If top-result relevance < 0.5 after reranking, the Alpha Refiner automatically
retries the opposite search strategy (vector ↔ lexical) to ensure good results.

### Configurable Parameters

```bash
# In langchain_agent/.env
RRF_K=60                           # RRF constant (higher = less dominance of rank 1)
ENABLE_EMBEDDING_CACHE=true        # Cache query embeddings (default: true)
EMBEDDING_CACHE_MAX_SIZE=100       # Max cached embeddings
ESCI_INGEST_LIMIT=10000           # Default product sample size
```

## Deployment

### GCP Cloud Run

The `deploy.sh` script handles production deployment:

1. Enables GCP APIs (Cloud Run, SQL, Artifact Registry, Secret Manager)
2. Creates Cloud SQL PostgreSQL instance (conversation checkpoints)
3. Stores secrets in Secret Manager (GOOGLE_API_KEY, API_KEY, OpenSearch credentials)
4. Builds multi-stage Docker image (React frontend + Python backend)
5. Pushes to Artifact Registry
6. Deploys to Cloud Run with Cloud SQL proxy

**Cost Optimization**:

- `min-instances=0` — scales to zero when idle (no ongoing charges)
- `max-instances=2` — prevents runaway scaling
- CPU throttling — CPU only allocated during request processing
- Cloud SQL `db-f1-micro` tier — minimal checkpoint storage

```bash
# First deployment
./scripts/deploy.sh --project <PROJECT_ID>

# One-time: Initialize Cloud SQL + ingest ESCI products to OpenSearch
./scripts/gcp-init.sh --project <PROJECT_ID>

# View logs
gcloud logging read resource.type=cloud_run_revision --project=<PROJECT_ID>

# Teardown all GCP resources
./scripts/gcp-teardown.sh --project <PROJECT_ID>
```

**OpenSearch**: Hosted externally on GCP VM (34.138.97.13:9200). Credentials stored
in Secret Manager as `agentic-hybrid-search-opensearch-user/password`.

### Local Development

```bash
cd langchain_agent
cp .env.example .env        # Edit .env with GOOGLE_API_KEY and API_KEY
./scripts/setup.sh         # One-time: Docker + venv + DB + product ingestion
./scripts/start.sh         # Start backend (8000) + frontend (5173)
./scripts/stop.sh          # Stop services
./scripts/teardown.sh      # Full cleanup (containers, venv, data)
```

**Prerequisites**:
- Docker Desktop
- Python 3.13+
- Node.js 18+
- Google API Key ([get here](https://aistudio.google.com/apikey))
- ~1GB disk space for ESCI dataset (local development)


## Performance

| Operation | Time |
|-----------|------|
| Product Search (end-to-end) | 6-15s |
| Vector search (768-dim, HNSW) | ~200-500ms |
| BM25 lexical search | ~100-300ms |
| RRF fusion + reranking | ~1-2s |
| Query embedding (cached) | ~50ms (cached), ~500ms (fresh) |
| Alpha evaluation | ~300-500ms |
| LLM response generation (streaming) | ~3-8s |
| Alpha Refinement (full retry) | +1-2s if triggered |

**Typical Flow**:
1. Embedding + RRF fusion: ~600-700ms
2. Reranking top-40 products: ~1-2s
3. LLM generation: ~3-8s
4. Total: ~5-12s for typical query

**Cached queries** (within 1-hour window): ~2-3s faster due to embedding cache

---

**Status**: Production Deployed on GCP Cloud Run
