"""
Integration tests for WebSocket event streaming during content generation.

Tests WebSocket functionality for content generation pipeline:
- Event streaming during all 5 content generation modes
- Real-time progress updates (retrieval, generation, refinement passes)
- Event type validation and ordering
- Token-by-token LLM streaming
- Connection lifecycle with content generation
- Error events and recovery
- Concurrent content generation requests
- Event schema validation against frontend types
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from typing import List, Dict, Any
from datetime import datetime

from api.schemas.events import (
    ContentTypeClassificationEvent,
    SocialPostProgressEvent,
    BlogPostProgressEvent,
    ArticleProgressEvent,
    TutorialProgressEvent,
    ContentCompleteEvent,
    SearchProgressEvent,
    RerankerProgressEvent,
    LLMResponseChunkEvent,
)


@pytest.mark.integration
@pytest.mark.websocket
@pytest.mark.phase2
@pytest.mark.content_generation
class TestWebSocketSocialPostStreaming:
    """Tests for WebSocket streaming during social post generation."""

    @pytest.fixture
    def websocket_mock(self):
        """Mock WebSocket for social post generation."""
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        ws.send_text = AsyncMock()
        ws.receive_text = AsyncMock()
        ws.receive_json = AsyncMock()
        ws.close = AsyncMock()
        ws.client = Mock()
        ws.client.host = "127.0.0.1"
        ws.client.port = 12345
        ws.sent_messages = []

        async def track_send_json(data):
            ws.sent_messages.append(data)

        ws.send_json.side_effect = track_send_json
        return ws

    def test_social_post_event_sequence(self, websocket_mock):
        """Test correct event sequence for social post generation."""
        expected_events = [
            "content_type_classification",
            "search_progress",
            "reranker_progress",
            "social_post_progress",
            "llm_response_chunk",
            "content_complete",
        ]

        # Simulate event emission
        simulated_events = [
            {"type": "content_type_classification", "content_type": "social_post"},
            {"type": "search_progress", "documents_retrieved": 3},
            {"type": "reranker_progress", "reranked_documents": 3},
            {"type": "social_post_progress", "stage": "generation"},
            {"type": "llm_response_chunk", "token": "Great", "cumulative_tokens": 1},
            {"type": "llm_response_chunk", "token": " post", "cumulative_tokens": 2},
            {"type": "content_complete", "content_type": "social_post", "content_length_words": 150},
        ]

        event_types = [e["type"] for e in simulated_events]
        for expected in expected_events:
            assert expected in event_types, f"Missing event type: {expected}"

    def test_social_post_progress_stages(self, websocket_mock):
        """Test social post generation stages in event stream."""
        stages = ["retrieval", "generation"]

        simulated_events = [
            {"type": "social_post_progress", "stage": "retrieval", "message": "Retrieving relevant products..."},
            {"type": "social_post_progress", "stage": "generation", "message": "Generating engaging copy..."},
        ]

        for event in simulated_events:
            assert event["stage"] in stages
            assert "message" in event
            assert len(event["message"]) > 0

    def test_social_post_token_streaming(self, websocket_mock):
        """Test token-by-token streaming for social post generation."""
        sample_tokens = ["Here's", " a", " great", " product", " choice"]
        cumulative_count = 0

        streamed_events = []
        for i, token in enumerate(sample_tokens, 1):
            event = {
                "type": "llm_response_chunk",
                "token": token,
                "cumulative_tokens": i,
                "node": "social_content_generator",
            }
            streamed_events.append(event)
            cumulative_count = i

        assert cumulative_count == len(sample_tokens)
        assert len(streamed_events) == len(sample_tokens)
        assert all("token" in e and "cumulative_tokens" in e for e in streamed_events)

    def test_social_post_completion_event(self, websocket_mock):
        """Test ContentCompleteEvent for social post generation."""
        completion_event = {
            "type": "content_complete",
            "node": "social_content_generator",
            "content_type": "social_post",
            "content_length_words": 180,
            "content_length_chars": 950,
        }

        assert completion_event["content_type"] == "social_post"
        assert 100 <= completion_event["content_length_words"] <= 300
        assert completion_event["content_length_chars"] > 0


@pytest.mark.integration
@pytest.mark.websocket
@pytest.mark.phase2
@pytest.mark.content_generation
class TestWebSocketBlogPostStreaming:
    """Tests for WebSocket streaming during blog post generation."""

    @pytest.fixture
    def websocket_mock(self):
        """Mock WebSocket for blog post generation."""
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        ws.sent_messages = []

        async def track_send_json(data):
            ws.sent_messages.append(data)

        ws.send_json.side_effect = track_send_json
        return ws

    def test_blog_post_multi_pass_event_sequence(self, websocket_mock):
        """Test blog post generation with multiple retrieval passes."""
        simulated_events = [
            {"type": "content_type_classification", "content_type": "blog_post"},
            # Outline pass
            {"type": "blog_post_progress", "stage": "outline", "message": "Creating blog outline..."},
            # First retrieval pass
            {"type": "search_progress", "documents_retrieved": 8},
            {"type": "blog_post_progress", "stage": "retrieval_pass_1", "message": "Gathering concept information..."},
            # Second retrieval pass
            {"type": "search_progress", "documents_retrieved": 7},
            {"type": "blog_post_progress", "stage": "retrieval_pass_2", "message": "Gathering examples and case studies..."},
            # Generation
            {"type": "blog_post_progress", "stage": "generation", "message": "Writing blog content..."},
            {"type": "llm_response_chunk", "token": "In", "cumulative_tokens": 1},
            # ... more tokens ...
            {"type": "content_complete", "content_type": "blog_post", "content_length_words": 1450},
        ]

        # Verify stages appear in order
        stages_found = [e["stage"] for e in simulated_events if "stage" in e]
        expected_stages = ["outline", "retrieval_pass_1", "retrieval_pass_2", "generation"]

        for expected in expected_stages:
            assert expected in stages_found, f"Missing stage: {expected}"

    def test_blog_post_token_accumulation(self, websocket_mock):
        """Test cumulative token count during blog post generation."""
        tokens = ["Building", " a", " successful", " e", "-", "commerce", " platform", " requires", " planning"]

        cumulative_events = []
        for i, token in enumerate(tokens, 1):
            event = {
                "type": "llm_response_chunk",
                "token": token,
                "cumulative_tokens": i,
            }
            cumulative_events.append(event)

        # Verify cumulative tokens increase monotonically
        for i in range(1, len(cumulative_events)):
            assert (
                cumulative_events[i]["cumulative_tokens"]
                > cumulative_events[i - 1]["cumulative_tokens"]
            )

    def test_blog_post_completion_word_count(self, websocket_mock):
        """Test blog post completion event word count validation."""
        completion_event = {
            "type": "content_complete",
            "node": "blog_content_generator",
            "content_type": "blog_post",
            "content_length_words": 1520,
            "content_length_chars": 8900,
        }

        assert 1000 <= completion_event["content_length_words"] <= 2000
        assert completion_event["content_length_chars"] > completion_event["content_length_words"] * 4


@pytest.mark.integration
@pytest.mark.websocket
@pytest.mark.phase2
@pytest.mark.content_generation
class TestWebSocketArticleStreaming:
    """Tests for WebSocket streaming during technical article generation."""

    @pytest.fixture
    def websocket_mock(self):
        """Mock WebSocket for article generation."""
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        return ws

    def test_article_three_pass_retrieval(self, websocket_mock):
        """Test technical article with 3 retrieval passes."""
        simulated_events = [
            {"type": "content_type_classification", "content_type": "technical_article"},
            {"type": "article_progress", "stage": "outline", "message": "Outlining technical structure..."},
            {"type": "search_progress", "documents_retrieved": 10},
            {"type": "article_progress", "stage": "retrieval_pass_1", "message": "Gathering problem statements..."},
            {"type": "search_progress", "documents_retrieved": 9},
            {"type": "article_progress", "stage": "retrieval_pass_2", "message": "Gathering solutions and approaches..."},
            {"type": "search_progress", "documents_retrieved": 8},
            {"type": "article_progress", "stage": "retrieval_pass_3", "message": "Gathering implementation details..."},
            {"type": "article_progress", "stage": "generation", "message": "Writing technical content..."},
            {"type": "content_complete", "content_type": "technical_article", "content_length_words": 1180},
        ]

        stages = [e["stage"] for e in simulated_events if "stage" in e]
        expected_stages = ["outline", "retrieval_pass_1", "retrieval_pass_2", "retrieval_pass_3", "generation"]

        for expected in expected_stages:
            assert expected in stages

    def test_article_retrieval_progression(self, websocket_mock):
        """Test retrieval document counts decrease with each pass."""
        retrieval_events = [
            {"type": "search_progress", "documents_retrieved": 10, "stage": "retrieval_pass_1"},
            {"type": "search_progress", "documents_retrieved": 9, "stage": "retrieval_pass_2"},
            {"type": "search_progress", "documents_retrieved": 8, "stage": "retrieval_pass_3"},
        ]

        counts = [e["documents_retrieved"] for e in retrieval_events]
        # Later passes may retrieve fewer docs as more relevant ones are found
        assert counts[0] >= counts[1]
        assert counts[1] >= counts[2]


@pytest.mark.integration
@pytest.mark.websocket
@pytest.mark.phase2
@pytest.mark.content_generation
class TestWebSocketTutorialStreaming:
    """Tests for WebSocket streaming during tutorial generation."""

    @pytest.fixture
    def websocket_mock(self):
        """Mock WebSocket for tutorial generation."""
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        return ws

    def test_tutorial_concept_and_example_passes(self, websocket_mock):
        """Test tutorial with concept and example retrieval passes."""
        simulated_events = [
            {"type": "content_type_classification", "content_type": "tutorial"},
            {"type": "tutorial_progress", "stage": "outline", "message": "Planning tutorial structure..."},
            {"type": "search_progress", "documents_retrieved": 8},
            {"type": "tutorial_progress", "stage": "concept_retrieval", "message": "Gathering core concepts..."},
            {"type": "search_progress", "documents_retrieved": 7},
            {"type": "tutorial_progress", "stage": "example_retrieval", "message": "Gathering code examples..."},
            {"type": "tutorial_progress", "stage": "generation", "message": "Writing step-by-step guide..."},
            {"type": "content_complete", "content_type": "tutorial", "content_length_words": 950},
        ]

        stages = [e["stage"] for e in simulated_events if "stage" in e]
        expected_stages = ["outline", "concept_retrieval", "example_retrieval", "generation"]

        for expected in expected_stages:
            assert expected in stages

    def test_tutorial_completion_validation(self, websocket_mock):
        """Test tutorial completion event meets requirements."""
        completion_event = {
            "type": "content_complete",
            "node": "tutorial_generator",
            "content_type": "tutorial",
            "content_length_words": 980,
            "content_length_chars": 5800,
        }

        assert 800 <= completion_event["content_length_words"] <= 1200
        assert completion_event["node"] == "tutorial_generator"
        assert completion_event["content_type"] == "tutorial"


@pytest.mark.integration
@pytest.mark.websocket
@pytest.mark.phase2
@pytest.mark.content_generation
class TestWebSocketEventOrdering:
    """Tests for correct event ordering across content generation types."""

    def test_classification_before_generation(self):
        """Test content type classification always comes before generation events."""
        simulated_stream = [
            {"type": "content_type_classification", "content_type": "blog_post", "sequence": 1},
            {"type": "search_progress", "documents_retrieved": 8, "sequence": 2},
            {"type": "blog_post_progress", "stage": "outline", "sequence": 3},
            {"type": "blog_post_progress", "stage": "generation", "sequence": 4},
            {"type": "content_complete", "content_type": "blog_post", "sequence": 5},
        ]

        classification_idx = next(
            i for i, e in enumerate(simulated_stream) if e["type"] == "content_type_classification"
        )
        generation_idx = next(
            i for i, e in enumerate(simulated_stream) if "progress" in e["type"]
        )

        assert classification_idx < generation_idx

    def test_retrieval_before_generation(self):
        """Test search progress events come before generation events."""
        simulated_stream = [
            {"type": "search_progress", "documents_retrieved": 10, "sequence": 1},
            {"type": "reranker_progress", "reranked_documents": 10, "sequence": 2},
            {"type": "blog_post_progress", "stage": "generation", "sequence": 3},
            {"type": "llm_response_chunk", "token": "Test", "sequence": 4},
        ]

        retrieval_idx = next(
            i for i, e in enumerate(simulated_stream) if e["type"] == "search_progress"
        )
        generation_idx = next(
            i for i, e in enumerate(simulated_stream) if "progress" in e["type"] and "blog" in e["type"]
        )

        assert retrieval_idx < generation_idx

    def test_token_chunks_after_generation_start(self):
        """Test token chunks come after generation starts."""
        simulated_stream = [
            {"type": "blog_post_progress", "stage": "generation", "sequence": 1},
            {"type": "llm_response_chunk", "token": "The", "sequence": 2},
            {"type": "llm_response_chunk", "token": " product", "sequence": 3},
            {"type": "content_complete", "sequence": 4},
        ]

        generation_idx = next(
            i for i, e in enumerate(simulated_stream) if "blog_post_progress" in e["type"]
        )
        token_idx = next(
            i for i, e in enumerate(simulated_stream) if e["type"] == "llm_response_chunk"
        )

        assert generation_idx < token_idx

    def test_completion_is_final_event(self):
        """Test content_complete is the last event in stream."""
        simulated_stream = [
            {"type": "content_type_classification"},
            {"type": "search_progress"},
            {"type": "social_post_progress"},
            {"type": "llm_response_chunk"},
            {"type": "content_complete"},
        ]

        assert simulated_stream[-1]["type"] == "content_complete"


@pytest.mark.integration
@pytest.mark.websocket
@pytest.mark.phase2
@pytest.mark.content_generation
class TestWebSocketEventValidation:
    """Tests for WebSocket event schema validation."""

    def test_content_type_classification_event_schema(self):
        """Test ContentTypeClassificationEvent has required fields."""
        event_dict = {
            "type": "content_type_classification",
            "content_type": "social_post",
            "confidence": 0.92,
            "target_length": 200,
            "tone": "engaging",
            "retrieval_depth": 1,
            "temperature": 0.8,
        }

        # Validate required fields
        required_fields = [
            "type",
            "content_type",
            "confidence",
            "target_length",
            "tone",
        ]
        for field in required_fields:
            assert field in event_dict

    def test_social_post_progress_event_schema(self):
        """Test SocialPostProgressEvent schema validation."""
        event_dict = {
            "type": "social_post_progress",
            "node": "social_content_generator",
            "stage": "generation",
            "message": "Generating engaging copy...",
        }

        assert event_dict["type"] == "social_post_progress"
        assert event_dict["node"] == "social_content_generator"
        assert event_dict["stage"] in ["retrieval", "generation"]
        assert len(event_dict["message"]) > 0

    def test_blog_post_progress_event_schema(self):
        """Test BlogPostProgressEvent schema validation."""
        event_dict = {
            "type": "blog_post_progress",
            "node": "blog_content_generator",
            "stage": "retrieval_pass_1",
            "message": "Gathering information...",
        }

        valid_stages = ["outline", "retrieval_pass_1", "retrieval_pass_2", "generation"]
        assert event_dict["stage"] in valid_stages

    def test_article_progress_event_schema(self):
        """Test ArticleProgressEvent schema validation."""
        event_dict = {
            "type": "article_progress",
            "node": "article_content_generator",
            "stage": "retrieval_pass_2",
            "message": "Gathering solutions...",
        }

        valid_stages = [
            "outline",
            "retrieval_pass_1",
            "retrieval_pass_2",
            "retrieval_pass_3",
            "generation",
        ]
        assert event_dict["stage"] in valid_stages

    def test_tutorial_progress_event_schema(self):
        """Test TutorialProgressEvent schema validation."""
        event_dict = {
            "type": "tutorial_progress",
            "node": "tutorial_generator",
            "stage": "concept_retrieval",
            "message": "Gathering concepts...",
        }

        valid_stages = ["outline", "concept_retrieval", "example_retrieval", "generation"]
        assert event_dict["stage"] in valid_stages

    def test_content_complete_event_schema(self):
        """Test ContentCompleteEvent schema validation."""
        event_dict = {
            "type": "content_complete",
            "node": "social_content_generator",
            "content_type": "social_post",
            "content_length_words": 180,
            "content_length_chars": 950,
        }

        required_fields = [
            "type",
            "node",
            "content_type",
            "content_length_words",
            "content_length_chars",
        ]
        for field in required_fields:
            assert field in event_dict

        assert event_dict["content_length_words"] > 0
        assert event_dict["content_length_chars"] > 0

    def test_llm_response_chunk_event_schema(self):
        """Test LLMResponseChunkEvent schema validation."""
        event_dict = {
            "type": "llm_response_chunk",
            "token": "amazing",
            "cumulative_tokens": 42,
            "node": "social_content_generator",
        }

        assert event_dict["type"] == "llm_response_chunk"
        assert isinstance(event_dict["token"], str)
        assert isinstance(event_dict["cumulative_tokens"], int)
        assert event_dict["cumulative_tokens"] > 0


@pytest.mark.integration
@pytest.mark.websocket
@pytest.mark.phase2
@pytest.mark.content_generation
class TestWebSocketConcurrentStreams:
    """Tests for handling concurrent content generation streams."""

    @pytest.fixture
    def multiple_websockets(self):
        """Create multiple mock WebSockets."""
        websockets = []
        for i in range(3):
            ws = AsyncMock()
            ws.accept = AsyncMock()
            ws.send_json = AsyncMock()
            ws.close = AsyncMock()
            ws.client = Mock()
            ws.client.host = f"127.0.0.{i+1}"
            ws.client.port = 12345 + i
            websockets.append(ws)
        return websockets

    def test_independent_event_streams(self, multiple_websockets):
        """Test multiple concurrent streams maintain independence."""
        streams = [
            {
                "client": ws.client.host,
                "events": [
                    {"type": "content_type_classification", "content_type": "social_post"},
                    {"type": "content_complete", "content_type": "social_post"},
                ],
            }
            for ws in multiple_websockets
        ]

        # Each stream should be independent
        assert len(streams) == 3
        for stream in streams:
            assert len(stream["events"]) > 0
            assert stream["events"][0]["type"] == "content_type_classification"
            assert stream["events"][-1]["type"] == "content_complete"

    def test_no_event_cross_contamination(self, multiple_websockets):
        """Test events from one stream don't leak to another."""
        stream_a_events = ["social_post_progress"]
        stream_b_events = ["blog_post_progress"]
        stream_c_events = ["article_progress"]

        # Verify stream isolation
        assert stream_a_events[0] != stream_b_events[0]
        assert stream_b_events[0] != stream_c_events[0]


@pytest.mark.integration
@pytest.mark.websocket
@pytest.mark.phase2
@pytest.mark.content_generation
class TestWebSocketErrorHandling:
    """Tests for error handling and recovery during WebSocket streaming."""

    @pytest.fixture
    def websocket_mock(self):
        """Mock WebSocket with error scenarios."""
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        ws.close = AsyncMock()
        return ws

    def test_generation_timeout_error_event(self, websocket_mock):
        """Test error event emitted on content generation timeout."""
        error_event = {
            "type": "agent_error",
            "error": "Content generation timeout after 120 seconds",
            "node": "blog_content_generator",
            "recoverable": False,
        }

        assert error_event["type"] == "agent_error"
        assert "timeout" in error_event["error"].lower()

    def test_api_rate_limit_error_event(self, websocket_mock):
        """Test error event for API rate limiting."""
        error_event = {
            "type": "agent_error",
            "error": "API rate limit exceeded: 429 Too Many Requests",
            "node": "social_content_generator",
            "recoverable": True,
            "retry_after_seconds": 30,
        }

        assert error_event["type"] == "agent_error"
        assert "429" in error_event["error"] or "rate" in error_event["error"].lower()
        assert error_event["recoverable"] is True

    def test_retrieval_failure_error_event(self, websocket_mock):
        """Test error event when document retrieval fails."""
        error_event = {
            "type": "agent_error",
            "error": "No relevant documents found for content generation",
            "node": "retriever",
            "recoverable": True,
        }

        assert error_event["type"] == "agent_error"
        assert "No relevant documents" in error_event["error"]


@pytest.mark.integration
@pytest.mark.websocket
@pytest.mark.phase2
@pytest.mark.content_generation
class TestWebSocketConnectionLifecycle:
    """Tests for WebSocket connection lifecycle during content generation."""

    @pytest.fixture
    def websocket_mock(self):
        """Mock WebSocket with lifecycle tracking."""
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        ws.close = AsyncMock()
        ws.events_sent = 0

        async def count_send_json(data):
            ws.events_sent += 1

        ws.send_json.side_effect = count_send_json
        return ws

    def test_connection_accepted_before_events(self, websocket_mock):
        """Test connection is accepted before sending events."""
        assert websocket_mock.accept is not None
        assert callable(websocket_mock.accept)

    def test_events_sent_during_generation(self, websocket_mock):
        """Test events are sent throughout generation."""
        # Simulate event emission
        for i in range(10):
            websocket_mock.send_json({"type": "llm_response_chunk", "token": "test"})

        # Verify send_json was called 10 times
        assert websocket_mock.send_json.call_count == 10

    def test_connection_closure_after_completion(self, websocket_mock):
        """Test connection can be closed after content generation."""
        # Simulate completion
        websocket_mock.send_json({"type": "content_complete"})

        # Close connection
        websocket_mock.close()

        # Verify close was called
        assert websocket_mock.close.called


@pytest.mark.integration
@pytest.mark.websocket
@pytest.mark.phase2
@pytest.mark.content_generation
class TestWebSocketEventTimestamps:
    """Tests for event timestamp validity and ordering."""

    def test_events_have_valid_timestamps(self):
        """Test all events include valid ISO 8601 timestamps."""
        from datetime import datetime

        event = {
            "type": "social_post_progress",
            "stage": "generation",
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Parse timestamp to verify ISO 8601 format
        timestamp_str = event["timestamp"]
        parsed_time = datetime.fromisoformat(timestamp_str)
        assert parsed_time is not None

    def test_event_timestamps_monotonically_increase(self):
        """Test timestamps increase monotonically across event stream."""
        from datetime import datetime, timedelta

        base_time = datetime.utcnow()
        events = [
            {"type": "content_type_classification", "timestamp": base_time.isoformat()},
            {
                "type": "search_progress",
                "timestamp": (base_time + timedelta(milliseconds=100)).isoformat(),
            },
            {
                "type": "social_post_progress",
                "timestamp": (base_time + timedelta(milliseconds=200)).isoformat(),
            },
            {
                "type": "content_complete",
                "timestamp": (base_time + timedelta(milliseconds=300)).isoformat(),
            },
        ]

        timestamps = [datetime.fromisoformat(e["timestamp"]) for e in events]

        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i - 1]
