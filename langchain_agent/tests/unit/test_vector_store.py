"""Unit tests for key methods in vector_store.py."""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

from vector_store import OpenSearchRetriever, OpenSearchVectorStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc(product_id=None, score=None, source="", title=""):
    metadata = {"source": source, "title": title}
    if product_id is not None:
        metadata["product_id"] = product_id
    if score is not None:
        metadata["retrieval_score"] = score
    return Document(page_content="content", metadata=metadata)


def _make_store():
    mock_client = MagicMock()
    mock_embeddings = MagicMock()
    mock_embeddings.embed_query.return_value = [0.1] * 768
    store = OpenSearchVectorStore.__new__(OpenSearchVectorStore)
    store.client = mock_client
    store.index_name = "test_index"
    store.embedding_function = mock_embeddings
    store.collection_id = "esci_products"
    return store, mock_client


def _make_search_response(judgments):
    """Build a mock OpenSearch search response with the given judgments list."""
    return {
        "hits": {
            "hits": [
                {
                    "_source": {
                        "judgments": judgments,
                    }
                }
            ]
        }
    }


# ---------------------------------------------------------------------------
# TestCollapseByDocument
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCollapseByDocument:

    def test_deduplicates_by_product_id(self):
        docs = [_make_doc("A"), _make_doc("A"), _make_doc("B")]
        result = OpenSearchRetriever.collapse_by_document(docs)
        assert len(result) == 2
        assert result[0].metadata["product_id"] == "A"
        assert result[1].metadata["product_id"] == "B"

    def test_keeps_first_occurrence(self):
        doc_high = _make_doc("A", score=0.9)
        doc_low = _make_doc("A", score=0.5)
        result = OpenSearchRetriever.collapse_by_document([doc_high, doc_low])
        assert len(result) == 1
        assert result[0].metadata["retrieval_score"] == 0.9

    def test_docs_without_product_id_pass_through(self):
        doc_no_id = Document(page_content="no id", metadata={"title": "x"})
        doc_with_id = _make_doc("A")
        result = OpenSearchRetriever.collapse_by_document([doc_no_id, doc_with_id])
        assert len(result) == 2

    def test_empty_list_returns_empty(self):
        assert OpenSearchRetriever.collapse_by_document([]) == []

    def test_different_collapse_field(self):
        docs = [
            Document(page_content="a", metadata={"source": "s1"}),
            Document(page_content="b", metadata={"source": "s1"}),
            Document(page_content="c", metadata={"source": "s2"}),
        ]
        result = OpenSearchRetriever.collapse_by_document(docs, collapse_field="source")
        assert len(result) == 2
        assert result[0].metadata["source"] == "s1"
        assert result[1].metadata["source"] == "s2"

    def test_preserves_order(self):
        docs = [_make_doc("A"), _make_doc("B"), _make_doc("A"), _make_doc("C")]
        result = OpenSearchRetriever.collapse_by_document(docs)
        assert [d.metadata["product_id"] for d in result] == ["A", "B", "C"]


# ---------------------------------------------------------------------------
# TestLookupJudgments
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLookupJudgments:

    def test_returns_none_for_empty_query(self):
        store, mock_client = _make_store()
        result = store.lookup_judgments("")
        assert result is None
        mock_client.search.assert_not_called()

    def test_returns_none_when_no_hits(self):
        store, mock_client = _make_store()
        mock_client.search.return_value = {"hits": {"hits": []}}
        result = store.lookup_judgments("blue shoes")
        assert result is None

    def test_returns_judgment_dict_on_hit(self):
        store, mock_client = _make_store()
        mock_client.search.return_value = _make_search_response(
            [{"product_id": "p1", "relevance": 0.8}]
        )
        result = store.lookup_judgments("blue shoes")
        assert result == {"p1": 0.8}

    def test_filters_entries_without_product_id(self):
        store, mock_client = _make_store()
        mock_client.search.return_value = _make_search_response(
            [
                {"product_id": "p1", "relevance": 1.0},
                {"relevance": 0.5},  # no product_id
            ]
        )
        result = store.lookup_judgments("query")
        assert result == {"p1": 1.0}
        assert len(result) == 1

    def test_returns_none_on_client_exception(self):
        store, mock_client = _make_store()
        mock_client.search.side_effect = Exception("connection refused")
        result = store.lookup_judgments("query")
        assert result is None

    def test_relevance_defaults_to_zero_when_missing(self):
        store, mock_client = _make_store()
        mock_client.search.return_value = _make_search_response(
            [{"product_id": "p1"}]  # no relevance key
        )
        result = store.lookup_judgments("query")
        assert result == {"p1": 0.0}


# ---------------------------------------------------------------------------
# TestHitToDocument
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHitToDocument:

    def _make_hit(self, chunk_text="hello world", score=0.75, **extra_src):
        src = {
            "chunk_text": chunk_text,
            "source": "test_source",
            "title": "Test Title",
            "doc_type": "product",
            "url": "http://example.com",
            "collection_id": "esci_products",
            "product_id": "ASIN123",
            "product_brand": "BrandX",
            "product_color": "blue",
            **extra_src,
        }
        return {"_source": src, "_score": score}

    def test_converts_hit_to_document(self):
        hit = self._make_hit()
        doc = OpenSearchVectorStore._hit_to_document(hit)
        assert isinstance(doc, Document)
        assert doc.page_content == "hello world"
        assert doc.metadata["title"] == "Test Title"
        assert doc.metadata["product_id"] == "ASIN123"
        assert doc.metadata["product_brand"] == "BrandX"
        assert doc.metadata["product_color"] == "blue"
        assert doc.metadata["collection_id"] == "esci_products"

    def test_retrieval_score_from_hit_score(self):
        hit = self._make_hit(score=0.42)
        doc = OpenSearchVectorStore._hit_to_document(hit)
        assert doc.metadata["retrieval_score"] == pytest.approx(0.42)

    def test_retrieval_score_override(self):
        hit = self._make_hit(score=0.42)
        doc = OpenSearchVectorStore._hit_to_document(hit, retrieval_score=0.99)
        assert doc.metadata["retrieval_score"] == pytest.approx(0.99)

    def test_missing_fields_default_to_empty_string(self):
        hit = {"_source": {"chunk_text": "text"}, "_score": 0.5}
        doc = OpenSearchVectorStore._hit_to_document(hit)
        assert doc.metadata["title"] == ""
        assert doc.metadata["source"] == ""
        assert doc.metadata["product_id"] == ""

    def test_no_score_when_both_none(self):
        hit = {"_source": {"chunk_text": "text"}}  # no _score key
        doc = OpenSearchVectorStore._hit_to_document(hit, retrieval_score=None)
        assert "retrieval_score" not in doc.metadata
