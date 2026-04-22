"""
Autocomplete suggestion endpoint for product titles and brands.

Provides typeahead suggestions using edge-ngram prefix matching.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from config import OPENSEARCH_INDEX_NAME
from vector_store import create_opensearch_client

logger = logging.getLogger(__name__)

router = APIRouter()


class SuggestResponse(BaseModel):
    """Response model for autocomplete suggestions."""

    suggestions: List[str]


@router.get("/suggest", response_model=SuggestResponse)
async def suggest(
    q: str = Query(..., min_length=1, max_length=100, description="Query prefix for suggestions")
) -> SuggestResponse:
    """
    Get autocomplete suggestions for product titles and brands.

    Args:
        q: Query prefix to search for (e.g., "sony wh")

    Returns:
        SuggestResponse with up to 8 deduplicated suggestions
    """
    if not q or len(q.strip()) == 0:
        return SuggestResponse(suggestions=[])

    try:
        client = create_opensearch_client()

        # Search both title_suggest and brand_suggest fields
        body = {
            "size": 8,
            "_source": ["title", "product_brand"],
            "query": {
                "bool": {
                    "should": [
                        {
                            "match": {
                                "title_suggest": {
                                    "query": q,
                                    "boost": 2.0,
                                }
                            }
                        },
                        {
                            "match": {
                                "brand_suggest": {
                                    "query": q,
                                    "boost": 1.5,
                                }
                            }
                        },
                    ],
                    "filter": [{"term": {"collection_id": "esci_products"}}],
                }
            },
        }

        response = client.search(index=OPENSEARCH_INDEX_NAME, body=body)

        # Extract suggestions from results, deduplicating by title
        seen_titles = set()
        suggestions = []
        for hit in response["hits"]["hits"]:
            source = hit["_source"]
            title = source.get("title", "").strip()
            if title and title not in seen_titles:
                seen_titles.add(title)
                suggestions.append(title)

        logger.info(f"Suggest query='{q}' returned {len(suggestions)} unique suggestions")
        return SuggestResponse(suggestions=suggestions)

    except Exception as e:
        logger.error(f"Error during suggest query: {e}")
        return SuggestResponse(suggestions=[])
