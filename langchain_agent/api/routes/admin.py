"""
Admin routes for operational tasks: re-indexing, health checks, index management.
Provides endpoints to manage the search index and re-ingest data when mappings change.
"""

import logging
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Debug: Verify router is being created
router = APIRouter(prefix="/api/admin", tags=["admin"])
logger.info(f"Admin router created with prefix: {router.prefix}")


# In-process reindex job state. The trigger endpoint resets this to "queued"
# synchronously before returning, so polling workflows can distinguish a fresh
# run from stale terminal state left behind by a previous invocation on the
# same container.
_reindex_state_lock = Lock()
_reindex_state: dict[str, Any] = {
    "status": "idle",  # idle | queued | running | success | error
    "started_at": None,
    "finished_at": None,
    "limit": None,
    "reset_index": None,
    "documents_ingested": None,
    "chunks_created": None,
    "error": None,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _update_reindex_state(**kwargs: Any) -> None:
    with _reindex_state_lock:
        _reindex_state.update(kwargs)


def _read_reindex_state() -> dict[str, Any]:
    with _reindex_state_lock:
        return dict(_reindex_state)


class ReindexRequest(BaseModel):
    """Request to trigger re-indexing of the OpenSearch index."""

    limit: int = 10000
    force_resample: bool = False
    reset_index: bool = True


class ReindexResponse(BaseModel):
    """Response from re-index operation."""

    status: str
    message: str
    documents_ingested: int | None = None
    chunks_created: int | None = None
    error: str | None = None


def perform_reindex(limit: int, force_resample: bool, reset_index: bool) -> ReindexResponse:
    """
    Perform re-indexing of OpenSearch index (synchronous for BackgroundTasks).

    BackgroundTasks.add_task() requires a synchronous callable. This runs inline
    in the background thread pool, blocking other background tasks serially.

    Args:
        limit: Number of products to ingest
        force_resample: Force re-sampling of dataset
        reset_index: Delete and recreate index (for schema changes)

    Returns:
        ReindexResponse with status and document counts
    """
    logger.info(
        f"[perform_reindex] Starting re-index: limit={limit}, force_resample={force_resample}, reset_index={reset_index}"
    )

    _update_reindex_state(
        status="running",
        started_at=_now_iso(),
        finished_at=None,
        limit=limit,
        reset_index=reset_index,
        documents_ingested=None,
        chunks_created=None,
        error=None,
    )

    try:
        from ingest_esci_products import ingest_esci_products

        docs, chunks = ingest_esci_products(
            limit=limit,
            force_resample=force_resample,
            reset_index=reset_index,
        )

        logger.info(
            f"[perform_reindex] Results: {docs} documents ingested, {chunks} chunks created"
        )
        _update_reindex_state(
            status="success",
            finished_at=_now_iso(),
            documents_ingested=docs,
            chunks_created=chunks,
        )
        return ReindexResponse(
            status="success",
            message=f"Successfully re-indexed {docs} documents into {chunks} chunks",
            documents_ingested=docs,
            chunks_created=chunks,
        )

    except FileNotFoundError as e:
        error_msg = f"Dataset file not found: {e}"
        logger.error(f"[perform_reindex] FileNotFoundError: {error_msg}", exc_info=True)
        _update_reindex_state(status="error", finished_at=_now_iso(), error=error_msg)
        return ReindexResponse(
            status="error",
            message="Re-index failed",
            error=error_msg,
        )
    except Exception as e:
        error_msg = f"Re-index failed: {type(e).__name__}: {e}"
        logger.error(f"[perform_reindex] Unexpected error: {error_msg}", exc_info=True)
        _update_reindex_state(status="error", finished_at=_now_iso(), error=error_msg)
        return ReindexResponse(
            status="error",
            message="Re-index failed",
            error=error_msg,
        )


@router.get("/reindex", response_model=ReindexResponse)
async def trigger_reindex(
    background_tasks: BackgroundTasks,
    limit: int = 10000,
    reset_index: bool = True,
    force_resample: bool = False,
) -> ReindexResponse:
    """
    Trigger re-indexing of OpenSearch index.

    Use when:
    - Index mappings have changed (e.g., added new fields for BM25 optimizations)
    - Index schema needs to be recreated
    - Data needs to be re-ingested with new field mappings

    Query Parameters:
    - `limit`: Number of products to ingest (default: 10000)
    - `reset_index`: Delete and recreate index (default: true, required for schema changes)
    - `force_resample`: Force re-sampling of dataset even if cached (default: false)

    Returns:
    - `status`: "success" or "error"
    - `documents_ingested`: Number of products loaded
    - `chunks_created`: Number of text chunks created
    - `error`: Error message if failed

    Example:
    ```
    GET /api/admin/reindex?reset_index=true&limit=10000
    ```

    This will:
    1. Delete the existing index
    2. Create a new index with current mappings (including BM25 optimizations)
    3. Load and embed 10,000 products
    4. Index them with new fields (title_suggest, title_phrase, title_phonetic, etc.)
    """
    logger.info(
        f"Re-index triggered: limit={limit}, reset_index={reset_index}, "
        f"force_resample={force_resample}"
    )

    # Reset state to "queued" synchronously before returning. Poll-based
    # automation (e.g. the Re-Index OpenSearch GitHub Action) relies on this
    # to avoid treating a previous run's terminal state as its own.
    _update_reindex_state(
        status="queued",
        started_at=None,
        finished_at=None,
        limit=limit,
        reset_index=reset_index,
        documents_ingested=None,
        chunks_created=None,
        error=None,
    )

    # Add task to background queue (FastAPI handles execution)
    background_tasks.add_task(
        perform_reindex,
        limit=limit,
        force_resample=force_resample,
        reset_index=reset_index,
    )

    return ReindexResponse(
        status="started",
        message=f"Re-index job started (limit={limit}, reset_index={reset_index}). "
        "Poll /api/admin/reindex/status for progress.",
    )


@router.get("/reindex/status")
async def reindex_status() -> dict[str, Any]:
    """
    Return the current state of the in-process re-index job.

    Status values:
    - `idle`    — no re-index has ever run in this container.
    - `queued`  — trigger was accepted; the background task has not yet started.
    - `running` — the ETL is actively ingesting documents.
    - `success` — the ETL finished; see `documents_ingested` / `chunks_created`.
    - `error`   — the ETL failed; see `error`.

    Multi-instance caveat: state is per-container, so polling must reach the
    same Cloud Run instance that accepted the trigger. In practice this holds
    for low-concurrency admin workflows (default Cloud Run routing reuses the
    warm instance), but is not guaranteed under load.
    """
    return _read_reindex_state()


@router.get("/diagnose")
async def diagnose(q: str = "sony") -> dict:
    """
    Probe the live index for a query across multiple fields.

    Diagnostic-only: answers "is there Sony data in the index, and which fields
    index it?" Compares hit counts for the suggest fields (title_suggest /
    brand_suggest) against the primary lexical fields (title / product_brand).
    If primary fields return hits while suggest fields don't, the mapping
    pre-dates the suggest fields and a re-index with reset_index=true is
    required.

    Also returns whether the mapping includes the suggest fields at all.
    """
    try:
        from config import OPENSEARCH_INDEX_NAME
        from vector_store import create_opensearch_client

        client = create_opensearch_client()

        def count(field: str) -> dict:
            try:
                body = {"query": {"match": {field: q}}}
                res = client.count(index=OPENSEARCH_INDEX_NAME, body=body)
                return {"count": res.get("count", 0)}
            except Exception as exc:  # noqa: BLE001
                return {"error": f"{type(exc).__name__}: {exc}"}

        # Inspect mapping for suggest fields.
        mapping_fields: dict = {}
        try:
            mapping = client.indices.get_mapping(index=OPENSEARCH_INDEX_NAME)
            index_key = next(iter(mapping))
            properties = mapping[index_key].get("mappings", {}).get("properties", {})
            for f in ("title", "product_brand", "title_suggest", "brand_suggest"):
                mapping_fields[f] = f in properties
        except Exception as exc:  # noqa: BLE001
            mapping_fields = {"error": f"{type(exc).__name__}: {exc}"}

        return {
            "query": q,
            "index": OPENSEARCH_INDEX_NAME,
            "field_counts": {
                "title": count("title"),
                "product_brand": count("product_brand"),
                "title_suggest": count("title_suggest"),
                "brand_suggest": count("brand_suggest"),
            },
            "mapping_has_field": mapping_fields,
        }
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


@router.get("/health")
async def admin_health() -> dict:
    """Admin health check - verify system components."""
    try:
        from config import OPENSEARCH_INDEX_NAME
        from vector_store import create_opensearch_client

        client = create_opensearch_client()

        # Check index exists and get stats
        if client.indices.exists(index=OPENSEARCH_INDEX_NAME):
            stats = client.count(index=OPENSEARCH_INDEX_NAME)
            doc_count = stats.get("count", 0)

            return {
                "status": "healthy",
                "opensearch": {
                    "connected": True,
                    "index": OPENSEARCH_INDEX_NAME,
                    "documents": doc_count,
                },
            }
        else:
            return {
                "status": "degraded",
                "opensearch": {
                    "connected": True,
                    "index": OPENSEARCH_INDEX_NAME,
                    "error": "Index does not exist",
                },
            }

    except Exception as e:
        return {
            "status": "unhealthy",
            "opensearch": {
                "connected": False,
                "error": str(e),
            },
        }
