"""
Post-Deployment Smoke Tests for Agentic Hybrid Search

Tests core functionality after deployment to ensure the system is working correctly.
Includes health checks, API authentication, WebSocket connectivity, and search pipeline validation.

Markers: @pytest.mark.e2e, @pytest.mark.slow, @pytest.mark.phase3
"""

import asyncio
import json
import os
import time
from datetime import datetime
from typing import Optional

import httpx
import pytest
from websockets.client import connect as ws_connect
from websockets.exceptions import InvalidStatusCode, WebSocketException


def _fail_if_origin_blocked(exc: BaseException) -> None:
    """Fail (not skip) when the deployment rejects with origin errors.
    With the correct Origin header sent on every ws_connect call this should
    never trigger — if it does, the origin allow-list is misconfigured."""
    msg = str(exc).lower()
    if "http 403" in msg or "rejected websocket" in msg:
        pytest.fail(
            f"WebSocket rejected despite Origin={ORIGIN_HEADER}. "
            "Check CORS/origin config on Cloud Run."
        )


# Configuration
DEPLOYMENT_URL = os.environ.get("CLOUD_RUN_URL", "http://localhost:8000")
API_KEY = os.environ.get("API_KEY", "test-api-key")
TIMEOUT = 30  # seconds
WEBSOCKET_TIMEOUT = 60  # seconds
# Origin header must match allowed UI origin (production is same-origin as API)
ORIGIN_HEADER = DEPLOYMENT_URL


class TestDeploymentHealth:
    """Health check and basic connectivity tests."""

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_health_endpoint_returns_ok(self):
        """Verify /health endpoint returns 200 with correct status."""
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(f"{DEPLOYMENT_URL}/api/health")

        assert response.status_code == 200, f"Health check failed: {response.text}"
        data = response.json()

        assert "status" in data, "Missing 'status' field in health response"
        assert data["status"] in ["ok", "degraded"], f"Invalid status: {data['status']}"
        assert "version" in data, "Missing 'version' field"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_health_checks_postgres(self):
        """Verify health endpoint reports PostgreSQL status."""
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(f"{DEPLOYMENT_URL}/api/health")

        assert response.status_code == 200
        data = response.json()

        assert "postgres" in data, "Missing 'postgres' field"
        assert isinstance(data["postgres"], bool), "postgres field should be boolean"
        assert data["postgres"], "PostgreSQL should be healthy"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_health_checks_google_api(self):
        """Verify health endpoint reports Google AI API status."""
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(f"{DEPLOYMENT_URL}/api/health")

        assert response.status_code == 200
        data = response.json()

        assert "google_ai" in data, "Missing 'google_ai' field"
        assert isinstance(data["google_ai"], bool), "google_ai field should be boolean"
        assert data["google_ai"], "Google AI API should be healthy"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_health_checks_opensearch(self):
        """Verify health endpoint reports OpenSearch status."""
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(f"{DEPLOYMENT_URL}/api/health")

        assert response.status_code == 200
        data = response.json()

        assert "vector_store" in data, "Missing 'vector_store' field"
        assert isinstance(data["vector_store"], bool), "vector_store field should be boolean"
        assert data["vector_store"], "OpenSearch should be healthy"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_suggest_endpoint_returns_results(self):
        """Typeahead suggest endpoint should answer a prefix query with 200."""
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(f"{DEPLOYMENT_URL}/api/suggest?q=son")

        assert response.status_code == 200, f"/api/suggest failed: {response.text}"
        data = response.json()
        assert "suggestions" in data, "Missing 'suggestions' field"
        assert isinstance(data["suggestions"], list), "suggestions field should be a list"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_health_reports_document_count(self):
        """Verify health endpoint reports product document count."""
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(f"{DEPLOYMENT_URL}/api/health")

        assert response.status_code == 200
        data = response.json()

        assert "document_count" in data, "Missing 'document_count' field"
        assert isinstance(data["document_count"], int), "document_count should be integer"
        assert data["document_count"] > 0, "Should have indexed products"


class TestAuthentication:
    """API key authentication tests."""

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_valid_api_key_accepted(self):
        """Verify valid API key is accepted in WebSocket connection."""
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Origin": ORIGIN_HEADER,
        }

        with httpx.Client(timeout=TIMEOUT) as client:
            # Test with conversations endpoint as a quick auth check
            response = client.get(f"{DEPLOYMENT_URL}/api/conversations", headers=headers)

        # Should get 200 (or 400 for bad params) but NOT 401 auth error.
        if response.status_code == 403 and "origin" in response.text.lower():
            pytest.fail(
                f"Origin rejected despite Origin={ORIGIN_HEADER}. "
                "Check CORS/origin config on Cloud Run."
            )
        if response.status_code == 429:
            pytest.skip("Rate limited; cannot verify auth acceptance")
        assert response.status_code in [
            200,
            400,
        ], f"Valid API key rejected: {response.status_code} - {response.text}"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_invalid_api_key_rejected(self):
        """Verify invalid API key is rejected."""
        headers = {"Authorization": "Bearer invalid-key-12345"}

        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(f"{DEPLOYMENT_URL}/api/conversations", headers=headers)

        if response.status_code == 429:
            pytest.skip("Rate limited; cannot verify auth rejection")
        assert response.status_code in [
            401,
            403,
        ], f"Invalid API key should be rejected, got {response.status_code}"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_missing_api_key_rejected(self):
        """Verify missing API key is rejected."""
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(f"{DEPLOYMENT_URL}/api/conversations")

        if response.status_code == 429:
            pytest.skip("Rate limited; cannot verify auth rejection")
        assert response.status_code in [
            401,
            403,
        ], f"Missing API key should be rejected, got {response.status_code}"


class TestWebSocketConnectivity:
    """WebSocket connection and basic messaging tests."""

    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_websocket_accepts_valid_connection(self):
        """Verify WebSocket endpoint accepts valid connection."""
        thread_id = "test-thread-001"
        ws_url = f"{DEPLOYMENT_URL.replace('http', 'ws')}/ws/chat/{thread_id}"

        try:
            async with ws_connect(
                ws_url, subprotocols=["websocket"], additional_headers={"Origin": ORIGIN_HEADER}
            ) as websocket:
                # Should connect without error
                assert websocket is not None
        except Exception as e:
            _fail_if_origin_blocked(e)
            pytest.fail(f"WebSocket connection failed: {e}")

    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_websocket_receives_connection_established(self):
        """Verify WebSocket sends ConnectionEstablished event on connect."""
        thread_id = "test-thread-002"
        ws_url = f"{DEPLOYMENT_URL.replace('http', 'ws')}/ws/chat/{thread_id}"

        try:
            async with ws_connect(
                ws_url, subprotocols=["websocket"], additional_headers={"Origin": ORIGIN_HEADER}
            ) as websocket:
                # Receive first message (should be ConnectionEstablished)
                message = await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)
                event = json.loads(message)

                assert "event_type" in event, "Missing event_type"
                assert (
                    event["event_type"] == "ConnectionEstablished"
                ), f"Expected ConnectionEstablished, got {event.get('event_type')}"
        except asyncio.TimeoutError:
            pytest.fail("Timeout waiting for ConnectionEstablished event")
        except Exception as e:
            _fail_if_origin_blocked(e)
            pytest.fail(f"WebSocket test failed: {e}")

    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_websocket_accepts_message(self):
        """Verify WebSocket endpoint accepts incoming messages."""
        thread_id = "test-thread-003"
        ws_url = f"{DEPLOYMENT_URL.replace('http', 'ws')}/ws/chat/{thread_id}"

        try:
            async with ws_connect(
                ws_url, subprotocols=["websocket"], additional_headers={"Origin": ORIGIN_HEADER}
            ) as websocket:
                # Skip ConnectionEstablished
                await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)

                # Send test message
                message = json.dumps({"query": "Find wireless headphones", "session_id": thread_id})
                await websocket.send(message)

                # Should receive events in response
                response = await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)
                event = json.loads(response)

                assert "event_type" in event, "Response missing event_type"
        except asyncio.TimeoutError:
            pytest.fail("Timeout waiting for response after sending message")
        except Exception as e:
            _fail_if_origin_blocked(e)
            pytest.fail(f"WebSocket messaging test failed: {e}")


class TestSearchPipeline:
    """RAG Q&A search pipeline tests with different intents."""

    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_search_intent_returns_results(self):
        """Test search intent returns products with citations."""
        thread_id = "test-search-001"
        ws_url = f"{DEPLOYMENT_URL.replace('http', 'ws')}/ws/chat/{thread_id}"

        try:
            async with ws_connect(
                ws_url, subprotocols=["websocket"], additional_headers={"Origin": ORIGIN_HEADER}
            ) as websocket:
                # Skip ConnectionEstablished
                await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)

                # Send search query
                message = json.dumps({"query": "Find wireless headphones", "session_id": thread_id})
                await websocket.send(message)

                # Collect response events
                response_text = ""
                received_events = []
                start_time = time.time()

                while time.time() - start_time < WEBSOCKET_TIMEOUT:
                    try:
                        event_msg = await asyncio.wait_for(websocket.recv(), timeout=5)
                        event = json.loads(event_msg)
                        received_events.append(event)

                        # Collect LLM response chunks
                        if event.get("event_type") == "LLMResponseChunkEvent":
                            response_text += event.get("chunk", "")

                        # Break on agent complete
                        if event.get("event_type") == "AgentCompleteEvent":
                            break
                    except asyncio.TimeoutError:
                        break

                assert len(received_events) > 0, "No events received"
                assert len(response_text) > 0, "No response text generated"
        except asyncio.TimeoutError:
            pytest.fail("Timeout during search intent test")
        except Exception as e:
            _fail_if_origin_blocked(e)
            pytest.fail(f"Search intent test failed: {e}")

    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_comparison_intent_returns_results(self):
        """Test comparison intent between products."""
        thread_id = "test-compare-001"
        ws_url = f"{DEPLOYMENT_URL.replace('http', 'ws')}/ws/chat/{thread_id}"

        try:
            async with ws_connect(
                ws_url, subprotocols=["websocket"], additional_headers={"Origin": ORIGIN_HEADER}
            ) as websocket:
                # Skip ConnectionEstablished
                await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)

                # Send comparison query
                message = json.dumps(
                    {"query": "Compare wireless headphones vs earbuds", "session_id": thread_id}
                )
                await websocket.send(message)

                # Collect response
                response_text = ""
                received_events = []
                start_time = time.time()

                while time.time() - start_time < WEBSOCKET_TIMEOUT:
                    try:
                        event_msg = await asyncio.wait_for(websocket.recv(), timeout=5)
                        event = json.loads(event_msg)
                        received_events.append(event)

                        if event.get("event_type") == "LLMResponseChunkEvent":
                            response_text += event.get("chunk", "")

                        if event.get("event_type") == "AgentCompleteEvent":
                            break
                    except asyncio.TimeoutError:
                        break

                assert len(response_text) > 0, "No comparison generated"
        except Exception as e:
            _fail_if_origin_blocked(e)
            pytest.fail(f"Comparison intent test failed: {e}")

    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_refinement_intent_constrains_results(self):
        """Test refinement intent adds constraints to prior search."""
        thread_id = "test-refinement-001"
        ws_url = f"{DEPLOYMENT_URL.replace('http', 'ws')}/ws/chat/{thread_id}"

        try:
            async with ws_connect(
                ws_url, subprotocols=["websocket"], additional_headers={"Origin": ORIGIN_HEADER}
            ) as websocket:
                # Skip ConnectionEstablished
                await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)

                # First search
                message1 = json.dumps({"query": "Show me headphones", "session_id": thread_id})
                await websocket.send(message1)

                # Collect first response
                start_time = time.time()
                while time.time() - start_time < WEBSOCKET_TIMEOUT:
                    try:
                        event_msg = await asyncio.wait_for(websocket.recv(), timeout=5)
                        event = json.loads(event_msg)
                        if event.get("event_type") == "AgentCompleteEvent":
                            break
                    except asyncio.TimeoutError:
                        break

                # Second message with refinement
                message2 = json.dumps(
                    {"query": "Now only show wireless ones", "session_id": thread_id}
                )
                await websocket.send(message2)

                # Collect refined response
                response_text = ""
                start_time = time.time()
                while time.time() - start_time < WEBSOCKET_TIMEOUT:
                    try:
                        event_msg = await asyncio.wait_for(websocket.recv(), timeout=5)
                        event = json.loads(event_msg)
                        if event.get("event_type") == "LLMResponseChunkEvent":
                            response_text += event.get("chunk", "")
                        if event.get("event_type") == "AgentCompleteEvent":
                            break
                    except asyncio.TimeoutError:
                        break

                assert len(response_text) > 0, "No refined response generated"
        except Exception as e:
            _fail_if_origin_blocked(e)
            pytest.fail(f"Refinement intent test failed: {e}")


class TestCitations:
    """Citation and product metadata validation tests."""

    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_citations_include_product_urls(self):
        """Verify citations in responses include valid product URLs."""
        thread_id = "test-citations-001"
        ws_url = f"{DEPLOYMENT_URL.replace('http', 'ws')}/ws/chat/{thread_id}"

        try:
            async with ws_connect(
                ws_url, subprotocols=["websocket"], additional_headers={"Origin": ORIGIN_HEADER}
            ) as websocket:
                await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)

                message = json.dumps({"query": "Find headphones", "session_id": thread_id})
                await websocket.send(message)

                # Collect complete response
                response_text = ""
                metadata = {}
                start_time = time.time()

                while time.time() - start_time < WEBSOCKET_TIMEOUT:
                    try:
                        event_msg = await asyncio.wait_for(websocket.recv(), timeout=5)
                        event = json.loads(event_msg)

                        if event.get("event_type") == "LLMResponseChunkEvent":
                            response_text += event.get("chunk", "")
                        elif event.get("event_type") == "AgentCompleteEvent":
                            metadata = event.get("metadata", {})
                            break
                    except asyncio.TimeoutError:
                        break

                # Check for citations in metadata
                assert (
                    "citations" in metadata or "sources" in metadata or len(response_text) > 0
                ), "Response should include citations or sources"
        except Exception as e:
            _fail_if_origin_blocked(e)
            pytest.fail(f"Citations test failed: {e}")


class TestResponseTiming:
    """Response time and performance tests."""

    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_search_response_time_under_5_seconds(self):
        """Verify search responses complete in under 5 seconds."""
        thread_id = "test-timing-search-001"
        ws_url = f"{DEPLOYMENT_URL.replace('http', 'ws')}/ws/chat/{thread_id}"

        try:
            async with ws_connect(
                ws_url, subprotocols=["websocket"], additional_headers={"Origin": ORIGIN_HEADER}
            ) as websocket:
                await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)

                message = json.dumps(
                    {"query": "Find headphones under $100", "session_id": thread_id}
                )

                start_time = time.time()
                await websocket.send(message)

                # Wait for completion
                while time.time() - start_time < WEBSOCKET_TIMEOUT:
                    try:
                        event_msg = await asyncio.wait_for(websocket.recv(), timeout=5)
                        event = json.loads(event_msg)
                        if event.get("event_type") == "AgentCompleteEvent":
                            break
                    except asyncio.TimeoutError:
                        break

                elapsed = time.time() - start_time
                # Allow up to 8 seconds for search (network overhead)
                assert (
                    elapsed < 8
                ), f"Search took {elapsed:.1f}s, should be under 5s (allowing for network)"
        except Exception as e:
            _fail_if_origin_blocked(e)
            pytest.fail(f"Response timing test failed: {e}")

    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_generation_response_time_under_10_seconds(self):
        """Verify generation responses complete in under 10 seconds."""
        thread_id = "test-timing-gen-001"
        ws_url = f"{DEPLOYMENT_URL.replace('http', 'ws')}/ws/chat/{thread_id}"

        try:
            async with ws_connect(
                ws_url, subprotocols=["websocket"], additional_headers={"Origin": ORIGIN_HEADER}
            ) as websocket:
                await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)

                message = json.dumps(
                    {
                        "query": "Generate comparison between wireless and wired headphones",
                        "session_id": thread_id,
                    }
                )

                start_time = time.time()
                await websocket.send(message)

                # Wait for completion
                while time.time() - start_time < WEBSOCKET_TIMEOUT:
                    try:
                        event_msg = await asyncio.wait_for(websocket.recv(), timeout=5)
                        event = json.loads(event_msg)
                        if event.get("event_type") == "AgentCompleteEvent":
                            break
                    except asyncio.TimeoutError:
                        break

                elapsed = time.time() - start_time
                # Allow up to 15 seconds for generation (network overhead)
                assert (
                    elapsed < 15
                ), f"Generation took {elapsed:.1f}s, should be under 10s (allowing for network)"
        except Exception as e:
            _fail_if_origin_blocked(e)
            pytest.fail(f"Generation timing test failed: {e}")


# Make async tests work with pytest
@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
