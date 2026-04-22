"""
Integration tests for /api/suggest — typeahead autocomplete endpoint.

The OpenSearch client is mocked; we only verify the route contract:
query-param validation, response shape, dedup, highlight round-trip,
spell-correction detection, and graceful error handling.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _mk_hit(title: str, brand: str = "Sony", score: float = 5.0, highlight=None) -> dict:
    hit = {
        "_source": {"title": title, "product_brand": brand},
        "_score": score,
    }
    if highlight:
        hit["highlight"] = highlight
    return hit


def _mk_response(hits, max_score: float = 10.0) -> dict:
    return {"hits": {"hits": hits, "max_score": max_score}}


@patch("api.routes.suggest.create_opensearch_client")
def test_happy_path_returns_suggestion_items(mock_client_factory, client):
    """Eight hits → eight SuggestionItem objects with titles, brands, normalized scores."""
    mock_os = MagicMock()
    mock_os.search.return_value = _mk_response(
        [_mk_hit(f"Sony Product {i}", score=9.0 - i * 0.1) for i in range(8)],
        max_score=9.0,
    )
    mock_client_factory.return_value = mock_os

    r = client.get("/api/suggest?q=sony")
    assert r.status_code == 200
    body = r.json()
    assert len(body["suggestions"]) == 8
    for item in body["suggestions"]:
        assert "title" in item
        assert item["brand"] == "Sony"
        assert 0.0 <= item["score"] <= 1.0
    assert body["spell_correction"] is None


def test_empty_query_returns_422(client):
    """FastAPI's min_length=1 should reject empty q."""
    r = client.get("/api/suggest?q=")
    assert r.status_code == 422


@patch("api.routes.suggest.create_opensearch_client")
def test_limit_param_honored(mock_client_factory, client):
    """?limit=1 should return at most one suggestion even if more hits exist."""
    mock_os = MagicMock()
    mock_os.search.return_value = _mk_response(
        [_mk_hit(f"Item {i}") for i in range(5)], max_score=5.0
    )
    mock_client_factory.return_value = mock_os

    r = client.get("/api/suggest?q=son&limit=1")
    assert r.status_code == 200
    assert len(r.json()["suggestions"]) == 1


@patch("api.routes.suggest.create_opensearch_client")
def test_duplicate_titles_deduplicated(mock_client_factory, client):
    """Two hits with the same title collapse to one entry."""
    mock_os = MagicMock()
    mock_os.search.return_value = _mk_response(
        [_mk_hit("Sony WH-1000XM5"), _mk_hit("Sony WH-1000XM5"), _mk_hit("Sony Other")],
        max_score=5.0,
    )
    mock_client_factory.return_value = mock_os

    r = client.get("/api/suggest?q=sony")
    assert r.status_code == 200
    titles = [s["title"] for s in r.json()["suggestions"]]
    assert titles == ["Sony WH-1000XM5", "Sony Other"]


@patch("api.routes.suggest.create_opensearch_client")
def test_opensearch_exception_returns_empty(mock_client_factory, client):
    """Upstream failure must not leak — endpoint returns 200 with empty list."""
    mock_os = MagicMock()
    mock_os.search.side_effect = RuntimeError("cluster unreachable")
    mock_client_factory.return_value = mock_os

    r = client.get("/api/suggest?q=sony")
    assert r.status_code == 200
    assert r.json() == {"suggestions": [], "spell_correction": None}


@patch("api.routes.suggest.create_opensearch_client")
def test_spell_correction_detected_for_misspelled_query(mock_client_factory, client):
    """Query 'sonie' against a hit titled 'Sony ...' should surface spell_correction."""
    mock_os = MagicMock()
    mock_os.search.return_value = _mk_response(
        [_mk_hit("Sony WH-1000XM5 Wireless Headphones", score=8.0)],
        max_score=10.0,
    )
    mock_client_factory.return_value = mock_os

    r = client.get("/api/suggest?q=sonie")
    assert r.status_code == 200
    correction = r.json()["spell_correction"]
    assert correction is not None
    assert correction["title"].lower() == "sony"
    assert correction["score"] >= 0.5


@patch("api.routes.suggest.create_opensearch_client")
def test_highlight_fragments_round_trip(mock_client_factory, client):
    """Highlight fragments from OpenSearch should appear in the response."""
    mock_os = MagicMock()
    mock_os.search.return_value = _mk_response(
        [
            _mk_hit(
                "Sony WH-1000XM5",
                highlight={"title_suggest": ["<mark data-th>Son</mark>y WH-1000XM5"]},
            )
        ],
        max_score=5.0,
    )
    mock_client_factory.return_value = mock_os

    r = client.get("/api/suggest?q=son")
    assert r.status_code == 200
    item = r.json()["suggestions"][0]
    assert item["highlight"] == ["<mark data-th>Son</mark>y WH-1000XM5"]
