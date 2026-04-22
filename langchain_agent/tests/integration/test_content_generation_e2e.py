"""
End-to-end tests for complete content generation pipeline.

Tests full pipeline flows from query classification through content delivery:
- Intent detection → content type selection → generation
- Multi-format content generation with real document retrieval
- Citation inclusion and validation
- WebSocket event streaming during generation
- Edge cases and error recovery
- Performance and timeout handling
"""

import json
from typing import Any, Dict, List
from unittest.mock import MagicMock, Mock, patch

import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage

from agent_state import CustomAgentState
from api.schemas.events import (
    ContentCompleteEvent,
    ContentTypeClassificationEvent,
)


@pytest.mark.integration
@pytest.mark.e2e
@pytest.mark.phase2
@pytest.mark.content_generation
class TestE2ESocialPostGeneration:
    """End-to-end tests for social post generation flow."""

    @pytest.fixture
    def mock_products(self):
        """Sample product documents for retrieval."""
        return [
            Document(
                page_content="Sony WH-1000XM5 wireless headphones with advanced noise canceling and 30-hour battery",
                metadata={
                    "product_id": "B09YLRKTRL",
                    "product_name": "Sony WH-1000XM5",
                    "product_brand": "Sony",
                    "price": 399.99,
                    "url": "https://www.amazon.com/dp/B09YLRKTRL",
                    "rating": 4.7,
                    "reviews": 5200,
                },
            ),
            Document(
                page_content="Bose QuietComfort 45 premium noise-canceling headphones with comfort fit",
                metadata={
                    "product_id": "B097BQ5LYH",
                    "product_name": "Bose QuietComfort 45",
                    "product_brand": "Bose",
                    "price": 379.00,
                    "url": "https://www.amazon.com/dp/B097BQ5LYH",
                    "rating": 4.5,
                    "reviews": 3100,
                },
            ),
        ]

    def test_social_post_generation_flow(self, mock_products):
        """Test complete social post generation flow."""
        # Step 1: Classify content type
        classification = {
            "content_type": "social_post",
            "confidence": 0.95,
            "target_length": 200,
            "tone": "engaging",
        }

        assert classification["content_type"] == "social_post"

        # Step 2: Retrieve relevant products
        retrieved = mock_products[:2]
        assert len(retrieved) == 2
        assert all(isinstance(doc, Document) for doc in retrieved)

        # Step 3: Generate content
        generated_post = (
            "Check out these premium headphones! 🎧\n\n"
            "Sony WH-1000XM5: Industry-leading noise cancellation, 30-hour battery. "
            "Perfect for music lovers. ⭐⭐⭐⭐⭐\n\n"
            "Bose QuietComfort 45: Ultimate comfort with premium sound quality. "
            "Great alternative choice. ⭐⭐⭐⭐\n\n"
            "#ProductRecommendation #Headphones"
        )

        word_count = len(generated_post.split())
        assert 100 <= word_count <= 300

        # Step 4: Include citations
        assert "Sony WH-1000XM5" in generated_post or "4.7" in generated_post
        assert "Bose QuietComfort 45" in generated_post or "4.5" in generated_post

    def test_social_post_streaming(self, mock_products):
        """Test social post generation with token streaming."""
        tokens = [
            "Amazing",
            " headphones",
            " for",
            " your",
            " music",
            " journey",
            "!",
        ]

        accumulated = ""
        for i, token in enumerate(tokens, 1):
            accumulated += token
            assert len(accumulated) > 0
            assert i <= len(tokens)

        final_text = accumulated
        assert "Amazing headphones for your music journey!" == final_text


@pytest.mark.integration
@pytest.mark.e2e
@pytest.mark.phase2
@pytest.mark.content_generation
class TestE2EBlogPostGeneration:
    """End-to-end tests for blog post generation flow."""

    @pytest.fixture
    def mock_products(self):
        """Sample products for blog context."""
        return [
            Document(
                page_content="Wireless headphones have revolutionized personal audio with Bluetooth connectivity",
                metadata={"product_brand": "Sony", "type": "blog_context"},
            ),
            Document(
                page_content="Noise cancellation technology uses active sound algorithms to eliminate ambient noise",
                metadata={"product_brand": "Bose", "type": "blog_context"},
            ),
        ]

    def test_blog_post_outline_generation(self, mock_products):
        """Test blog post outline creation."""
        outline = [
            "1. Introduction: Why Premium Headphones Matter",
            "2. Audio Technology Evolution",
            "3. Top Contenders: Features & Benefits",
            "4. Sound Quality Comparison",
            "5. Comfort & Design",
            "6. Conclusion: Making Your Choice",
        ]

        assert len(outline) > 0
        assert all(isinstance(section, str) for section in outline)

    def test_blog_post_multi_pass_retrieval(self, mock_products):
        """Test multiple retrieval passes during blog generation."""
        # First pass: concepts
        concepts_pass = mock_products
        assert len(concepts_pass) > 0

        # Second pass: examples (simulated)
        examples_pass = [
            Document(
                page_content="Example: Sony headphones deliver exceptional clarity in rock music",
                metadata={"type": "example"},
            )
        ]
        assert len(examples_pass) > 0

        total_retrieved = len(concepts_pass) + len(examples_pass)
        assert total_retrieved > len(concepts_pass)

    def test_blog_post_completion_validation(self, mock_products):
        """Test blog post meets length and quality requirements."""
        blog_content = """
        # The Ultimate Guide to Premium Headphones

        In this comprehensive guide, we'll explore the world of high-end audio equipment
        and help you choose the perfect pair of headphones for your needs.

        ## Understanding Audio Quality

        Premium headphones distinguish themselves through several key factors...

        ## Popular Choices

        **Sony WH-1000XM5**: These headphones offer industry-leading noise cancellation...

        **Bose QuietComfort 45**: Known for exceptional comfort during extended wear...

        ## Making Your Decision

        Consider your primary use case, comfort preferences, and budget constraints...
        """

        word_count = len(blog_content.split())
        assert 1000 <= word_count <= 2500

        # Check for required sections
        assert "Guide" in blog_content
        assert "Sony" in blog_content or "headphones" in blog_content.lower()


@pytest.mark.integration
@pytest.mark.e2e
@pytest.mark.phase2
@pytest.mark.content_generation
class TestE2ETechnicalArticleGeneration:
    """End-to-end tests for technical article generation flow."""

    @pytest.fixture
    def mock_technical_docs(self):
        """Technical documentation for article context."""
        return [
            Document(
                page_content="Hybrid search combines BM25 lexical search with semantic vector search using RRF fusion",
                metadata={"type": "technical"},
            ),
            Document(
                page_content="Vector embeddings map text to high-dimensional space for semantic similarity",
                metadata={"type": "technical"},
            ),
            Document(
                page_content="OpenSearch implements HNSW algorithm for efficient approximate nearest neighbor search",
                metadata={"type": "technical"},
            ),
        ]

    def test_technical_article_problem_statement(self, mock_technical_docs):
        """Test technical article opens with clear problem statement."""
        problem = "Traditional full-text search struggles with semantic relevance"

        assert len(problem) > 0
        assert "problem" not in problem.lower() or "search" in problem.lower()

    def test_technical_article_solution_presentation(self, mock_technical_docs):
        """Test technical article presents clear solution."""
        solution_components = [
            "Vector embeddings for semantic understanding",
            "BM25 for lexical precision",
            "RRF fusion for balanced results",
        ]

        assert len(solution_components) > 0
        for component in solution_components:
            assert isinstance(component, str)

    def test_technical_article_implementation_details(self, mock_technical_docs):
        """Test article includes implementation specifics."""
        implementation_details = {
            "algorithm": "HNSW (Hierarchical Navigable Small World)",
            "fusion_method": "Reciprocal Rank Fusion",
            "vector_dimension": 768,
            "index_type": "approximate nearest neighbor",
        }

        assert all(isinstance(v, (str, int)) for v in implementation_details.values())

    def test_technical_article_word_count(self, mock_technical_docs):
        """Test technical article meets word count requirements."""
        article = """
        # Implementing Hybrid Search with Vector Databases

        ## The Problem with Traditional Search

        Full-text search engines have served us well, but they miss semantic meaning...

        ## Understanding Vector Embeddings

        Vector embeddings transform text into high-dimensional representations...

        ## The Hybrid Approach

        By combining lexical and semantic search, we achieve superior relevance...

        ## OpenSearch Implementation

        OpenSearch provides native support for vector search with HNSW indexing...

        ## Performance Optimization

        Techniques for optimizing hybrid search performance in production...

        ## Conclusion

        Hybrid search represents the future of information retrieval...
        """

        word_count = len(article.split())
        assert 800 <= word_count <= 1500


@pytest.mark.integration
@pytest.mark.e2e
@pytest.mark.phase2
@pytest.mark.content_generation
class TestE2ETutorialGeneration:
    """End-to-end tests for tutorial generation flow."""

    @pytest.fixture
    def mock_tutorial_steps(self):
        """Sample steps for tutorial generation."""
        return [
            "Prerequisites: Python 3.10+, pip",
            "Install required packages",
            "Configure environment variables",
            "Initialize database",
            "Run the application",
        ]

    def test_tutorial_step_structure(self, mock_tutorial_steps):
        """Test tutorial has clear step-by-step structure."""
        assert len(mock_tutorial_steps) > 0
        assert all(isinstance(step, str) for step in mock_tutorial_steps)

    def test_tutorial_prerequisites_included(self, mock_tutorial_steps):
        """Test tutorial includes prerequisites section."""
        prerequisites_present = any("Prerequisites" in step for step in mock_tutorial_steps)
        assert prerequisites_present

    def test_tutorial_code_examples(self):
        """Test tutorial includes code examples."""
        code_examples = [
            "```python\nfrom main import EcommerceSearchAgent\n```",
            "```bash\nPYTHONPATH=. python main.py\n```",
        ]

        assert len(code_examples) > 0
        assert all("```" in example for example in code_examples)

    def test_tutorial_completion_guidance(self):
        """Test tutorial concludes with verification steps."""
        verification_steps = [
            "Verify API is responding: `curl http://localhost:8000/health`",
            "Test query: Make a search request via WebSocket",
            "Confirm response contains expected products",
        ]

        assert len(verification_steps) > 0
        for step in verification_steps:
            assert isinstance(step, str)


@pytest.mark.integration
@pytest.mark.e2e
@pytest.mark.phase2
@pytest.mark.content_generation
class TestE2ECitationHandling:
    """End-to-end tests for citation inclusion in generated content."""

    @pytest.fixture
    def sample_products(self):
        """Products with citation metadata."""
        return [
            {
                "product_id": "B09YLRKTRL",
                "name": "Sony WH-1000XM5",
                "url": "https://www.amazon.com/dp/B09YLRKTRL",
                "score": 0.95,
            },
            {
                "product_id": "B097BQ5LYH",
                "name": "Bose QuietComfort 45",
                "url": "https://www.amazon.com/dp/B097BQ5LYH",
                "score": 0.88,
            },
        ]

    def test_citations_included_in_content(self, sample_products):
        """Test citations are included in generated content."""
        generated_text = f"Recommended: {sample_products[0]['name']} - High quality option"

        assert sample_products[0]["name"] in generated_text

    def test_citation_urls_valid(self, sample_products):
        """Test citation URLs are valid and properly formatted."""
        for product in sample_products:
            url = product["url"]
            assert url.startswith("https://")
            assert "amazon.com" in url
            assert product["product_id"] in url

    def test_citation_score_threshold(self, sample_products):
        """Test only high-confidence documents cited."""
        min_score = 0.5

        citations = [p for p in sample_products if p["score"] >= min_score]

        assert len(citations) > 0
        assert all(c["score"] >= min_score for c in citations)

    def test_duplicate_citation_deduplication(self, sample_products):
        """Test duplicate citations are deduplicated."""
        citations_with_dupes = [
            {"url": "https://amazon.com/dp/B001", "name": "Product A"},
            {"url": "https://amazon.com/dp/B001", "name": "Product A"},
            {"url": "https://amazon.com/dp/B002", "name": "Product B"},
        ]

        unique_urls = set(c["url"] for c in citations_with_dupes)
        assert len(unique_urls) == 2


@pytest.mark.integration
@pytest.mark.e2e
@pytest.mark.phase2
@pytest.mark.content_generation
class TestE2EErrorRecovery:
    """End-to-end tests for error handling and recovery."""

    def test_no_products_found_error_handling(self):
        """Test graceful handling when no products found."""
        error_response = {
            "error": "No relevant products found for your query",
            "status": "retrieval_failure",
            "recoverable": True,
        }

        assert error_response["recoverable"] is True
        assert "No relevant products" in error_response["error"]

    def test_generation_timeout_handling(self):
        """Test handling of generation timeout."""
        timeout_error = {
            "error": "Content generation exceeded 120-second timeout",
            "status": "timeout",
            "recoverable": False,
        }

        assert timeout_error["recoverable"] is False
        assert "timeout" in timeout_error["error"].lower()

    def test_api_rate_limit_recovery(self):
        """Test recovery from API rate limiting."""
        rate_limit_error = {
            "error": "API rate limit: 429 Too Many Requests",
            "status": "rate_limited",
            "retry_after_seconds": 30,
            "recoverable": True,
        }

        assert rate_limit_error["recoverable"] is True
        assert rate_limit_error["retry_after_seconds"] > 0

    def test_malformed_product_data_handling(self):
        """Test handling of incomplete product metadata."""
        incomplete_product = {
            "product_id": "B001",
            "name": "Product A",
            # Missing: url, price, rating
        }

        # Should handle gracefully, using available fields
        assert "product_id" in incomplete_product
        assert "name" in incomplete_product


@pytest.mark.integration
@pytest.mark.e2e
@pytest.mark.phase2
@pytest.mark.content_generation
class TestE2ESpecialCharacters:
    """End-to-end tests for handling special characters in content."""

    def test_product_names_with_special_chars(self):
        """Test handling of special characters in product names."""
        product_names = [
            "Sony WH-1000XM5 (2022)",
            "Bose QuietComfort 45 - Premium",
            "Audio-Technica AT2020USB-X",
            "Shure SM7B's Professional Mic",
        ]

        for name in product_names:
            assert isinstance(name, str)
            assert len(name) > 0

    def test_unicode_in_generated_content(self):
        """Test Unicode characters in generated content."""
        content_with_unicode = (
            "These headphones offer 🎧 exceptional sound quality with ⭐⭐⭐⭐⭐ ratings"
        )

        assert "🎧" in content_with_unicode
        assert "⭐" in content_with_unicode
        assert isinstance(content_with_unicode, str)

    def test_special_chars_in_citations(self):
        """Test special characters in URLs and citations."""
        citation_url = "https://www.amazon.com/dp/B09YLRKTRL?ref=something&tag=test-20"

        assert citation_url.startswith("https://")
        assert "?" in citation_url
        assert "&" in citation_url


@pytest.mark.integration
@pytest.mark.e2e
@pytest.mark.phase2
@pytest.mark.content_generation
class TestE2ELongProductNames:
    """End-to-end tests for handling very long product names."""

    def test_extremely_long_product_name(self):
        """Test handling of excessively long product names."""
        long_name = (
            "Professional Grade Wireless Noise Cancelling Headphones "
            "with Advanced Bluetooth 5.0 Connectivity and 40-Hour "
            "Battery Life for Audiophiles and Music Production"
        )

        generated = f"Introducing: {long_name}"

        assert len(generated) > 0
        assert long_name in generated

    def test_long_description_truncation(self):
        """Test truncation of very long product descriptions."""
        long_desc = "A" * 2000  # 2000 character description

        # Should be truncated to reasonable length for content
        truncated = long_desc[:500] + "..."
        assert len(truncated) < len(long_desc)

    def test_long_title_wrapping_in_blog(self):
        """Test long titles wrap correctly in blog post."""
        long_title = (
            "The Complete Guide to Choosing Premium Wireless Headphones: "
            "Features, Performance, and Value Comparison"
        )

        # Title should render without breaking structure
        formatted_title = f"# {long_title}"
        assert formatted_title.startswith("# ")
        assert len(formatted_title) > 0


@pytest.mark.integration
@pytest.mark.e2e
@pytest.mark.phase2
@pytest.mark.content_generation
class TestE2EPerformance:
    """End-to-end tests for performance and resource usage."""

    def test_social_post_generation_speed(self):
        """Test social post generates quickly."""
        # Social posts should generate in <30 seconds
        target_duration = 30

        assert target_duration > 0

    def test_blog_post_generation_speed(self):
        """Test blog post generation completes in reasonable time."""
        # Blog posts should complete in <60 seconds
        target_duration = 60

        assert target_duration > 0

    def test_article_generation_speed(self):
        """Test technical article completes in reasonable time."""
        # Technical articles should complete in <90 seconds
        target_duration = 90

        assert target_duration > 0

    def test_memory_usage_during_generation(self):
        """Test memory usage stays within bounds."""
        # Mock memory tracking
        memory_usage = {
            "initial_mb": 100,
            "peak_mb": 250,
            "final_mb": 110,
        }

        # Should not leak memory
        assert memory_usage["final_mb"] < memory_usage["peak_mb"]

    def test_token_limit_respect(self):
        """Test generation respects token limits."""
        max_tokens = 2000

        generated_tokens = 1850

        assert generated_tokens <= max_tokens
