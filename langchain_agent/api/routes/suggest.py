"""
Autocomplete suggestion endpoint for product titles and brands.

Provides typeahead suggestions using edge-ngram prefix matching, with optional
phonetic-based spell correction when the top hit is plausibly a misspelling
of the user's query.
"""

import logging
import re
from difflib import SequenceMatcher
from typing import List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from config import OPENSEARCH_INDEX_NAME
from vector_store import create_opensearch_client

logger = logging.getLogger(__name__)

router = APIRouter()

_HIGHLIGHT_PRE = "<mark data-th>"
_HIGHLIGHT_POST = "</mark>"
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


class SuggestionItem(BaseModel):
    """A single autocomplete suggestion."""

    title: str
    brand: Optional[str] = None
    score: Optional[float] = None
    highlight: Optional[List[str]] = None


class SuggestResponse(BaseModel):
    """Response model for autocomplete suggestions."""

    suggestions: List[SuggestionItem]
    spell_correction: Optional[SuggestionItem] = None


def _levenshtein(a: str, b: str) -> int:
    """Small Levenshtein distance (iterative DP). a/b expected short (query tokens)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1]


def _detect_spell_correction(
    query: str, top_hits: List[dict], max_score: float
) -> Optional[SuggestionItem]:
    """
    Detect a likely spell correction for a single-token query.

    Strategy: for each of the top hits, tokenize the title; keep any token
    that sounds similar to the query (SequenceMatcher ratio >= 0.6) but
    is spelled differently (Levenshtein >= 2). Pick the token with the
    highest ratio. If the resulting confidence is >= 0.5, surface it.

    Multi-word queries are skipped — phrase-level correction needs more
    machinery (n-gram indexes, edit graphs) than this endpoint warrants.
    """
    q = query.strip().lower()
    if " " in q or len(q) < 4:
        return None

    best_token: Optional[str] = None
    best_hit: Optional[dict] = None
    best_ratio = 0.0

    for hit in top_hits[:3]:
        source = hit.get("_source", {})
        title = (source.get("title") or "").strip()
        if not title:
            continue
        for match in _TOKEN_RE.finditer(title.lower()):
            token = match.group(0)
            if len(token) < 4:
                continue
            if _levenshtein(q, token) < 2:
                continue
            ratio = SequenceMatcher(None, q, token).ratio()
            if ratio >= 0.6 and ratio > best_ratio:
                best_ratio = ratio
                best_token = token
                best_hit = hit

    if not best_token or not best_hit:
        return None

    raw_score = best_hit.get("_score") or 0.0
    normalized = min(raw_score / max_score, 1.0) if max_score else best_ratio
    confidence = min(normalized, best_ratio)
    if confidence < 0.5:
        return None

    source = best_hit.get("_source", {})
    return SuggestionItem(
        title=best_token,
        brand=source.get("product_brand") or None,
        score=round(confidence, 3),
    )


@router.get("/suggest", response_model=SuggestResponse)
async def suggest(
    q: str = Query(..., min_length=1, max_length=100, description="Query prefix for suggestions"),
    limit: int = Query(8, ge=1, le=20, description="Max suggestions to return"),
) -> SuggestResponse:
    """
    Get autocomplete suggestions for product titles and brands.

    Returns up to `limit` deduplicated SuggestionItem objects, plus an
    optional spell_correction suggestion if the query looks misspelled.
    """
    if not q or len(q.strip()) == 0:
        return SuggestResponse(suggestions=[])

    try:
        client = create_opensearch_client()

        body = {
            "size": max(limit, 3),
            "_source": ["title", "product_brand"],
            "query": {
                "bool": {
                    "should": [
                        {"match": {"title_suggest": {"query": q, "boost": 2.0}}},
                        {"match": {"brand_suggest": {"query": q, "boost": 1.5}}},
                    ],
                    "filter": [{"term": {"collection_id": "esci_products"}}],
                }
            },
            "highlight": {
                "pre_tags": [_HIGHLIGHT_PRE],
                "post_tags": [_HIGHLIGHT_POST],
                "fields": {
                    "title_suggest": {"number_of_fragments": 0},
                    "brand_suggest": {"number_of_fragments": 0},
                },
            },
        }

        response = client.search(index=OPENSEARCH_INDEX_NAME, body=body)
        hits = response["hits"]["hits"]
        max_score = response["hits"].get("max_score") or 1.0

        seen_titles = set()
        suggestions: List[SuggestionItem] = []
        for hit in hits:
            if len(suggestions) >= limit:
                break
            source = hit.get("_source", {})
            title = (source.get("title") or "").strip()
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)

            raw_score = hit.get("_score") or 0.0
            hl = hit.get("highlight") or {}
            fragments = (hl.get("title_suggest") or []) + (hl.get("brand_suggest") or [])

            suggestions.append(
                SuggestionItem(
                    title=title,
                    brand=(source.get("product_brand") or None),
                    score=min(raw_score / max_score, 1.0) if max_score else None,
                    highlight=fragments or None,
                )
            )

        spell_correction = _detect_spell_correction(q, hits, max_score)

        logger.info(
            "Suggest query=%r returned %d suggestions (correction=%s)",
            q,
            len(suggestions),
            spell_correction.title if spell_correction else None,
        )
        return SuggestResponse(suggestions=suggestions, spell_correction=spell_correction)

    except Exception as e:
        logger.error("Error during suggest query: %s", e)
        return SuggestResponse(suggestions=[])
