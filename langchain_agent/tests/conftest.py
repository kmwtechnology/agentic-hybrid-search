"""
Pytest configuration and fixtures for e-commerce pipeline tests.
Provides reusable fixtures for all test levels (unit, integration, E2E).
"""

import os
import sys
import pytest
from unittest.mock import Mock, MagicMock
from pathlib import Path

# Add langchain_agent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set test environment
os.environ.setdefault("ENABLE_RERANKING", "true")
os.environ.setdefault("ENABLE_QUALITY_GATE", "true")
os.environ.setdefault("QUALITY_GATE_THRESHOLD", "0.50")


@pytest.fixture
def mock_llm():
    """Mock LLM for fast unit tests (no API calls)."""
    llm = MagicMock()
    llm.invoke = MagicMock(return_value=MagicMock(content="Mock response"))
    llm.with_structured_output = MagicMock(return_value=llm)
    return llm


@pytest.fixture
def mock_embeddings():
    """Mock embeddings for fast unit tests."""
    embeddings = MagicMock()
    embeddings.embed_query = MagicMock(return_value=[0.1] * 768)
    embeddings.embed_documents = MagicMock(return_value=[[0.1] * 768] * 10)
    return embeddings


@pytest.fixture
def sample_documents():
    """Sample retrieved documents for testing."""
    from langchain_core.documents import Document

    return [
        Document(
            page_content="Sony WH-1000XM5 wireless headphones with noise canceling",
            metadata={
                "title": "Sony WH-1000XM5",
                "source": "product_1",
                "doc_type": "product",
                "product_id": "B09YLRKTRL",
                "product_brand": "Sony",
                "price": 399.99,
            }
        ),
        Document(
            page_content="Bose QuietComfort 45 premium noise-canceling headphones",
            metadata={
                "title": "Bose QuietComfort 45",
                "source": "product_2",
                "doc_type": "product",
                "product_id": "B097BQ5LYH",
                "product_brand": "Bose",
                "price": 379.00,
            }
        ),
    ]


@pytest.fixture
def intent_test_cases():
    """Test cases for intent classifier."""
    return [
        ("Find wireless headphones under $100", "search", "General product search"),
        ("Compare Sony WH-1000XM5 vs Bose QuietComfort 45", "comparison", "Product comparison"),
        ("Show me blue wireless headphones under $200", "attribute_filter", "Filtered search"),
        ("Any cheaper alternatives?", "follow_up", "Vague expansion"),
        ("Summarize our conversation", "summary", "Conversation recap"),
        ("Oh, they should also be waterproof", "refinement", "Constraint added to prior search"),
    ]


@pytest.fixture
def alpha_test_cases():
    """Test cases for query evaluator alpha selection."""
    return [
        ("Sony WH-1000XM5", 0.05, 0.15, "exact model number"),
        ("blue running shoes size 10", 0.15, 0.35, "specific attributes"),
        ("best headphones for running", 0.40, 0.60, "balanced activity-based"),
        ("comfortable office chair", 0.60, 0.75, "conceptual need"),
        ("gift ideas for music lovers", 0.75, 1.0, "semantic exploration"),
    ]


@pytest.fixture
def quality_gate_test_cases():
    """Test cases for quality gate decisions."""
    return [
        (0.67, "comparison", "pass", 0.55),
        (0.52, "search", "pass", 0.50),
        (0.32, "search", "retry", 0.50),
        (0.42, "comparison", "retry", 0.55),
        (0.46, "refinement", "pass", 0.45),
        (0.35, "refinement", "retry", 0.45),
    ]


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: mark test as a unit test")
    config.addinivalue_line("markers", "integration: mark test as an integration test")
    config.addinivalue_line("markers", "e2e: mark test as an end-to-end test")
    config.addinivalue_line("markers", "intent: mark test as intent classifier test")
    config.addinivalue_line("markers", "evaluator: mark test as query evaluator test")
    config.addinivalue_line("markers", "quality_gate: mark test as quality gate test")
    config.addinivalue_line("markers", "slow: mark test as slow")
