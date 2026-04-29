"""
FastAPI application with WebSocket support for real-time agent streaming.

This is the main entry point for the LangChain Agent API.
Run with: uvicorn api.main:app --reload --port 8000
"""

import warnings

# Suppress Pydantic V1 compatibility warning on Python 3.14+
# langchain-core imports pydantic.v1 for backward compatibility, but we use Pydantic V2
warnings.filterwarnings(
    "ignore",
    message="Core Pydantic V1 functionality isn't compatible with Python 3.14",
    category=UserWarning,
)

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Add parent directory to path for config import
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.sessions import SessionMiddleware

from api.middleware.auth import AuthConfigurationError
from api.routes import admin, auth, chat, conversations, health, suggest
from config import (
    API_KEY,
    LOGIN_PASSWORD,
    RATE_LIMIT_ENABLED,
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_SECURE,
    SESSION_MAX_AGE_SECONDS,
    SESSION_SECRET,
)
from logging_config import configure_logging, get_logger

# Configure structured logging
configure_logging()
logger = get_logger(__name__)

# Initialize rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    enabled=RATE_LIMIT_ENABLED,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager for startup and shutdown.

    Replaces deprecated @app.on_event("startup") and @app.on_event("shutdown")
    decorators with a modern async context manager pattern.
    """
    # Startup
    if not API_KEY:
        raise AuthConfigurationError(
            "API_KEY environment variable is not set. "
            "Authentication is required. Set API_KEY in your .env file."
        )
    if not LOGIN_PASSWORD:
        raise AuthConfigurationError(
            "LOGIN_PASSWORD environment variable is not set. "
            "The shared-password login gate is required. "
            "Set LOGIN_PASSWORD in your .env file."
        )
    if not SESSION_SECRET or len(SESSION_SECRET) < 32:
        raise AuthConfigurationError(
            "SESSION_SECRET must be set to a value of at least 32 characters. "
            "Generate one with `openssl rand -hex 32`."
        )

    logger.info(
        "api_started",
        rest_api="http://localhost:8000/api",
        websocket="ws://localhost:8000/ws/chat",
        docs="http://localhost:8000/docs",
        auth_required=True,
        login_gate=True,
    )

    yield  # Application runs here

    # Shutdown
    logger.info("api_shutting_down")
    try:
        await chat.manager.shutdown()
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
    logger.info("api_shutdown_complete")


tags_metadata = [
    {
        "name": "health",
        "description": (
            "System and index health probes. `/api/health` reports Postgres + OpenSearch + "
            "Google AI reachability; `/api/admin/health` reports current index document count."
        ),
    },
    {
        "name": "suggest",
        "description": (
            "Typeahead autocomplete with spell correction. Edge-ngram prefix matching on "
            "`title_suggest` and `brand_suggest` fields, with Levenshtein + SequenceMatcher "
            "spell correction and a distance-1 fuzzy fallback for single-character typos."
        ),
    },
    {
        "name": "auth",
        "description": (
            "Shared-password login gate. `POST /api/auth/login` validates the password and "
            "sets an HttpOnly session cookie; `POST /api/auth/logout` clears it; "
            "`GET /api/auth/status` reports whether the current request is authenticated."
        ),
    },
    {
        "name": "conversations",
        "description": "Conversation history CRUD (LangGraph checkpoints in Postgres).",
    },
    {
        "name": "admin",
        "description": (
            "Operational endpoints: background reindex trigger + status polling, index "
            "diagnostics. Used by the `reindex.yml` GitHub Actions workflow."
        ),
    },
    {
        "name": "chat",
        "description": (
            "Real-time streaming chat. WebSocket at `/ws/chat` is the primary surface; "
            "a synchronous REST fallback lives at `/api/chat`."
        ),
    },
]

app = FastAPI(
    title="Agentic Hybrid Search API",
    description=(
        "Production-grade RAG agent for Amazon ESCI e-commerce product search, "
        "deployed on GCP Cloud Run.\n\n"
        "**Features:**\n"
        "- **Hybrid search**: BM25 + vector (RRF fusion) with dynamic alpha per intent\n"
        "- **Intent routing**: 6 classes (search, comparison, attribute_filter, refinement, "
        "follow_up, summary)\n"
        "- **Reranking + quality gate**: Gemini-scored 0.0–1.0, with adaptive alpha retry\n"
        "- **Typeahead autocomplete**: `/api/suggest` edge-ngram prefix matching with "
        "spell correction and distance-1 fuzzy fallback\n"
        "- **Admin reindex**: `/api/admin/reindex` background re-ingestion with polling\n"
        "- **BM25 optimizations**: synonyms, phrase boosting, field boosting, phonetic matching\n"
        "- **Per-query optimization toggles**: 9 flags (hybrid, fuzzy, synonyms, phonetic, "
        "phrase_boost, field_boost, typeahead, reranking, llm) sent on every WebSocket chat "
        "message; the pipeline collapses skipped stages out of the observability panel.\n"
        "- **Pipeline Quality Summary**: end-of-pipeline `PipelineSummaryEvent` carrying "
        "BM25 / Hybrid / Reranked NDCG@10, MRR, Recall@20, Precision@10 against ESCI "
        "ground-truth judgments (`esci_judgments` index), plus per-stage latency lift-per-100ms. "
        "Falls back to a self-referential confidence proxy when no ground truth exists.\n"
        "- **Real-time streaming**: token-by-token output over WebSocket\n\n"
        "See [openapi.yaml](https://github.com/kmwtechnology/agentic-hybrid-search/blob/main/"
        "langchain_agent/openapi.yaml) for the full hand-authored spec."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=tags_metadata,
    contact={
        "name": "KMW Technology",
        "url": "https://github.com/kmwtechnology/agentic-hybrid-search",
    },
    lifespan=lifespan,
)

# Add rate limiter to app state
app.state.limiter = limiter

# Register rate limit exceeded handler
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS configuration
# Accept localhost for development plus this service's Cloud Run URL
cors_origins = [
    "http://localhost:5173",  # Vite dev server
    "http://localhost:3000",  # Alternative dev port
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]

# Add explicitly configured origins (e.g., custom domains)
if os.environ.get("CORS_ORIGINS"):
    configured_origins = [
        o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()
    ]
    cors_origins.extend(configured_origins)

# Determine this service's URL for Cloud Run
# The frontend will request from the same origin, so we need to allow it
# This is set dynamically via the /api/config endpoint at runtime
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_origin_regex=r"https://.*\.a\.run\.app",  # Accept all Cloud Run URLs
)

# Session cookie for the shared-password login gate. Added AFTER CORS so it
# runs first on the incoming request (Starlette middleware is reverse-add
# order on the way in), populating ``request.session`` before any route or
# WebSocket handler reads it. The lifespan check above kills startup if
# SESSION_SECRET is missing/short, so the placeholder below is only ever
# consulted during boot before traffic is served.
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET or "unconfigured-startup-will-fail",
    session_cookie=SESSION_COOKIE_NAME,
    https_only=SESSION_COOKIE_SECURE,
    same_site="lax",
    max_age=SESSION_MAX_AGE_SECONDS,
)

# Register REST routes
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(conversations.router, prefix="/api", tags=["conversations"])
app.include_router(suggest.router, prefix="/api", tags=["suggest"])
app.include_router(admin.router, tags=["admin"])

# Register WebSocket route
app.include_router(chat.router, tags=["chat"])

# Mount static files for React frontend (if built)
static_dir = Path(__file__).parent.parent / "web" / "dist"
if static_dir.exists():
    # Mount assets directory
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    # Serve React app for all non-API routes
    @app.get("/{full_path:path}")
    async def serve_react(full_path: str):
        """Serve React frontend for all non-API routes"""
        # Skip API routes and documentation
        if (
            full_path.startswith("api/")
            or full_path.startswith("ws/")
            or full_path in ("docs", "redoc", "openapi.json")
        ):
            return JSONResponse({"error": "Not Found"}, status_code=404)

        # Serve index.html for all other routes (React Router will handle)
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(index_file)

        return JSONResponse({"error": "Frontend not built"}, status_code=404)
