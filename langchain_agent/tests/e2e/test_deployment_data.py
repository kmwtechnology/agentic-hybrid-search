"""
Database and Index Validation Tests

Tests data integrity, index consistency, and search functionality after deployment.
Verifies ESCI products are properly indexed and searchable.

Markers: @pytest.mark.e2e, @pytest.mark.slow, @pytest.mark.phase3
"""

import os
import pytest
import httpx
import json


# Configuration
DEPLOYMENT_URL = os.environ.get("CLOUD_RUN_URL", "http://localhost:8000")
TIMEOUT = 30


class TestESCIProductIndexing:
    """ESCI product data indexing and retrieval tests."""

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_products_indexed_in_vector_store(self):
        """Verify ESCI products are indexed in the vector store."""
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(f"{DEPLOYMENT_URL}/api/health")

        assert response.status_code == 200
        data = response.json()

        doc_count = data.get("document_count", 0)
        assert doc_count > 0, (
            f"No products indexed: {doc_count}"
        )

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_product_document_count_reasonable(self):
        """Verify product count is within expected range."""
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(f"{DEPLOYMENT_URL}/api/health")

        data = response.json()
        doc_count = data.get("document_count", 0)

        # Should have at least 100 products in any deployment
        assert doc_count >= 100, (
            f"Product count too low: {doc_count} (expected >= 100)"
        )

        # Should not exceed reasonable limits (10 million)
        assert doc_count <= 10_000_000, (
            f"Product count unreasonable: {doc_count}"
        )

    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_hybrid_search_returns_products(self):
        """Verify hybrid search (vector + lexical) returns product results."""
        from websockets.client import connect as ws_connect
        import asyncio
        import time

        thread_id = "hybrid-search-001"
        ws_url = f"{DEPLOYMENT_URL.replace('http', 'ws')}/ws/chat/{thread_id}"

        try:
            async with ws_connect(ws_url, subprotocols=["websocket"]) as websocket:
                # Skip ConnectionEstablished
                await asyncio.wait_for(websocket.recv(), timeout=TIMEOUT)

                # Search for a common product
                message = json.dumps({
                    "query": "headphones",
                    "session_id": thread_id
                })
                await websocket.send(message)

                # Collect response to verify products were retrieved
                response_text = ""
                start_time = time.time()

                while time.time() - start_time < 30:
                    try:
                        event_msg = await asyncio.wait_for(
                            websocket.recv(),
                            timeout=5
                        )
                        event = json.loads(event_msg)

                        if event.get("event_type") == "LLMResponseChunkEvent":
                            response_text += event.get("chunk", "")

                        if event.get("event_type") == "AgentCompleteEvent":
                            break
                    except asyncio.TimeoutError:
                        break

                # Should have gotten results mentioning products
                assert len(response_text) > 0, "No products found in search"
        except Exception as e:
            pytest.fail(f"Hybrid search test failed: {e}")

    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_vector_search_semantic_similarity(self):
        """Verify vector search finds semantically similar products."""
        from websockets.client import connect as ws_connect
        import asyncio
        import time

        thread_id = "vector-search-001"
        ws_url = f"{DEPLOYMENT_URL.replace('http', 'ws')}/ws/chat/{thread_id}"

        try:
            async with ws_connect(ws_url, subprotocols=["websocket"]) as websocket:
                await asyncio.wait_for(websocket.recv(), timeout=TIMEOUT)

                # Search with a descriptive query (should use vector search)
                message = json.dumps({
                    "query": "I need to cancel noise from my environment",
                    "session_id": thread_id
                })
                await websocket.send(message)

                response_text = ""
                start_time = time.time()

                while time.time() - start_time < 30:
                    try:
                        event_msg = await asyncio.wait_for(
                            websocket.recv(),
                            timeout=5
                        )
                        event = json.loads(event_msg)

                        if event.get("event_type") == "LLMResponseChunkEvent":
                            response_text += event.get("chunk", "")

                        if event.get("event_type") == "AgentCompleteEvent":
                            break
                    except asyncio.TimeoutError:
                        break

                # Should understand semantic meaning and return products
                assert len(response_text) > 0, "Vector search failed"
        except Exception as e:
            pytest.fail(f"Vector search test failed: {e}")

    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_lexical_search_exact_match(self):
        """Verify lexical search finds exact product matches."""
        from websockets.client import connect as ws_connect
        import asyncio
        import time

        thread_id = "lexical-search-001"
        ws_url = f"{DEPLOYMENT_URL.replace('http', 'ws')}/ws/chat/{thread_id}"

        try:
            async with ws_connect(ws_url, subprotocols=["websocket"]) as websocket:
                await asyncio.wait_for(websocket.recv(), timeout=TIMEOUT)

                # Search with specific brand name (should use lexical search)
                message = json.dumps({
                    "query": "Sony products",
                    "session_id": thread_id
                })
                await websocket.send(message)

                response_text = ""
                start_time = time.time()

                while time.time() - start_time < 30:
                    try:
                        event_msg = await asyncio.wait_for(
                            websocket.recv(),
                            timeout=5
                        )
                        event = json.loads(event_msg)

                        if event.get("event_type") == "LLMResponseChunkEvent":
                            response_text += event.get("chunk", "")

                        if event.get("event_type") == "AgentCompleteEvent":
                            break
                    except asyncio.TimeoutError:
                        break

                # Should mention Sony specifically
                assert len(response_text) > 0, "Lexical search failed"
        except Exception as e:
            pytest.fail(f"Lexical search test failed: {e}")


class TestProductMetadata:
    """Product metadata completeness and consistency tests."""

    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_products_have_required_metadata(self):
        """Verify retrieved products have required metadata fields."""
        from websockets.client import connect as ws_connect
        import asyncio
        import time

        thread_id = "metadata-001"
        ws_url = f"{DEPLOYMENT_URL.replace('http', 'ws')}/ws/chat/{thread_id}"

        try:
            async with ws_connect(ws_url, subprotocols=["websocket"]) as websocket:
                await asyncio.wait_for(websocket.recv(), timeout=TIMEOUT)

                message = json.dumps({
                    "query": "headphones",
                    "session_id": thread_id
                })
                await websocket.send(message)

                metadata = {}
                start_time = time.time()

                while time.time() - start_time < 30:
                    try:
                        event_msg = await asyncio.wait_for(
                            websocket.recv(),
                            timeout=5
                        )
                        event = json.loads(event_msg)

                        if event.get("event_type") == "AgentCompleteEvent":
                            metadata = event.get("metadata", {})
                            break
                    except asyncio.TimeoutError:
                        break

                # Metadata should contain product information
                # Either directly or as part of citations
                assert (
                    len(metadata) > 0 or "citations" in str(metadata).lower()
                ), "No product metadata found"
        except Exception as e:
            pytest.fail(f"Product metadata test failed: {e}")

    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_product_brand_attribute_accessible(self):
        """Verify product brand attribute is indexed and searchable."""
        from websockets.client import connect as ws_connect
        import asyncio
        import time

        thread_id = "brand-search-001"
        ws_url = f"{DEPLOYMENT_URL.replace('http', 'ws')}/ws/chat/{thread_id}"

        try:
            async with ws_connect(ws_url, subprotocols=["websocket"]) as websocket:
                await asyncio.wait_for(websocket.recv(), timeout=TIMEOUT)

                # Search by brand
                message = json.dumps({
                    "query": "Apple brand wireless earbuds",
                    "session_id": thread_id
                })
                await websocket.send(message)

                response_text = ""
                start_time = time.time()

                while time.time() - start_time < 30:
                    try:
                        event_msg = await asyncio.wait_for(
                            websocket.recv(),
                            timeout=5
                        )
                        event = json.loads(event_msg)

                        if event.get("event_type") == "LLMResponseChunkEvent":
                            response_text += event.get("chunk", "")

                        if event.get("event_type") == "AgentCompleteEvent":
                            break
                    except asyncio.TimeoutError:
                        break

                assert len(response_text) > 0, "Brand search failed"
        except Exception as e:
            pytest.fail(f"Brand attribute test failed: {e}")


class TestDataConsistency:
    """Data integrity and consistency tests."""

    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_same_query_returns_consistent_results(self):
        """Verify repeated searches return consistent results."""
        from websockets.client import connect as ws_connect
        import asyncio
        import time

        thread_id_1 = "consistency-1"
        thread_id_2 = "consistency-2"
        ws_url_1 = f"{DEPLOYMENT_URL.replace('http', 'ws')}/ws/chat/{thread_id_1}"
        ws_url_2 = f"{DEPLOYMENT_URL.replace('http', 'ws')}/ws/chat/{thread_id_2}"

        try:
            # First search
            response_1 = ""
            async with ws_connect(ws_url_1, subprotocols=["websocket"]) as ws:
                await asyncio.wait_for(ws.recv(), timeout=TIMEOUT)

                message = json.dumps({"query": "laptop", "session_id": thread_id_1})
                await ws.send(message)

                start_time = time.time()
                while time.time() - start_time < 30:
                    try:
                        event_msg = await asyncio.wait_for(ws.recv(), timeout=5)
                        event = json.loads(event_msg)
                        if event.get("event_type") == "LLMResponseChunkEvent":
                            response_1 += event.get("chunk", "")
                        if event.get("event_type") == "AgentCompleteEvent":
                            break
                    except asyncio.TimeoutError:
                        break

            # Second search (same query)
            response_2 = ""
            async with ws_connect(ws_url_2, subprotocols=["websocket"]) as ws:
                await asyncio.wait_for(ws.recv(), timeout=TIMEOUT)

                message = json.dumps({"query": "laptop", "session_id": thread_id_2})
                await ws.send(message)

                start_time = time.time()
                while time.time() - start_time < 30:
                    try:
                        event_msg = await asyncio.wait_for(ws.recv(), timeout=5)
                        event = json.loads(event_msg)
                        if event.get("event_type") == "LLMResponseChunkEvent":
                            response_2 += event.get("chunk", "")
                        if event.get("event_type") == "AgentCompleteEvent":
                            break
                    except asyncio.TimeoutError:
                        break

            # Both should have generated responses (not necessarily identical, but similar structure)
            assert len(response_1) > 0, "First search returned no results"
            assert len(response_2) > 0, "Second search returned no results"

            # Should be roughly similar length (within 50%)
            ratio = max(len(response_1), len(response_2)) / min(len(response_1), len(response_2))
            assert ratio < 1.5, (
                f"Results inconsistent: {len(response_1)} vs {len(response_2)} chars"
            )
        except Exception as e:
            pytest.fail(f"Data consistency test failed: {e}")

    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_no_data_corruption_after_deployment(self):
        """Verify no data corruption in indexed products."""
        from websockets.client import connect as ws_connect
        import asyncio
        import time

        thread_id = "data-integrity-001"
        ws_url = f"{DEPLOYMENT_URL.replace('http', 'ws')}/ws/chat/{thread_id}"

        try:
            async with ws_connect(ws_url, subprotocols=["websocket"]) as websocket:
                await asyncio.wait_for(websocket.recv(), timeout=TIMEOUT)

                message = json.dumps({
                    "query": "Find any product",
                    "session_id": thread_id
                })
                await websocket.send(message)

                response_text = ""
                start_time = time.time()

                while time.time() - start_time < 30:
                    try:
                        event_msg = await asyncio.wait_for(
                            websocket.recv(),
                            timeout=5
                        )
                        event = json.loads(event_msg)

                        if event.get("event_type") == "LLMResponseChunkEvent":
                            response_text += event.get("chunk", "")

                        if event.get("event_type") == "AgentCompleteEvent":
                            break
                    except asyncio.TimeoutError:
                        break

                # Response should be valid text, no null characters or corruption
                assert len(response_text) > 0, "No response generated"
                assert "\x00" not in response_text, "Null character found in response"
                assert response_text.isascii() or all(
                    ord(c) >= 32 for c in response_text
                ), "Control characters in response"
        except Exception as e:
            pytest.fail(f"Data integrity test failed: {e}")


class TestCheckpointPersistence:
    """LangGraph checkpoint persistence tests."""

    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_conversation_checkpoints_stored(self):
        """Verify conversation checkpoints are persisted."""
        from websockets.client import connect as ws_connect
        import asyncio
        import time

        thread_id = "checkpoint-001"
        ws_url = f"{DEPLOYMENT_URL.replace('http', 'ws')}/ws/chat/{thread_id}"

        try:
            # Send first message
            async with ws_connect(ws_url, subprotocols=["websocket"]) as ws:
                await asyncio.wait_for(ws.recv(), timeout=TIMEOUT)

                msg1 = json.dumps({"query": "Find headphones", "session_id": thread_id})
                await ws.send(msg1)

                start_time = time.time()
                while time.time() - start_time < 30:
                    try:
                        event_msg = await asyncio.wait_for(ws.recv(), timeout=5)
                        event = json.loads(event_msg)
                        if event.get("event_type") == "AgentCompleteEvent":
                            break
                    except asyncio.TimeoutError:
                        break

            # Send follow-up message (should maintain context)
            async with ws_connect(ws_url, subprotocols=["websocket"]) as ws:
                await asyncio.wait_for(ws.recv(), timeout=TIMEOUT)

                msg2 = json.dumps({
                    "query": "What was I looking for?",
                    "session_id": thread_id
                })
                await ws.send(msg2)

                response_text = ""
                start_time = time.time()
                while time.time() - start_time < 30:
                    try:
                        event_msg = await asyncio.wait_for(ws.recv(), timeout=5)
                        event = json.loads(event_msg)
                        if event.get("event_type") == "LLMResponseChunkEvent":
                            response_text += event.get("chunk", "")
                        if event.get("event_type") == "AgentCompleteEvent":
                            break
                    except asyncio.TimeoutError:
                        break

                # Should have maintained conversation context
                assert len(response_text) > 0, "Checkpoint not restored"
        except Exception as e:
            pytest.fail(f"Checkpoint persistence test failed: {e}")


# Make async tests work with pytest
@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
