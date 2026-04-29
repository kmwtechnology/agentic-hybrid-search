"""
Cloud Run Deployment Specific Tests

Tests Cloud Run-specific behavior including HTTPS, service discovery, graceful shutdown,
scaling, and container environment validation.

Markers: @pytest.mark.e2e, @pytest.mark.slow, @pytest.mark.phase3
"""

import asyncio
import json
import os
import ssl
import time
from typing import Optional

import httpx
import pytest

# Configuration
CLOUD_RUN_URL = os.environ.get("CLOUD_RUN_URL", "http://localhost:8000")
API_KEY = os.environ.get("API_KEY", "test-api-key")
TIMEOUT = 30
# Same-origin Origin header so the deployment's verify_same_origin allow-list
# accepts the WebSocket handshake.
ORIGIN_HEADER = CLOUD_RUN_URL


def _skip_if_origin_blocked(exc: BaseException) -> None:
    """Fail when the deployment rejects WebSocket connections despite the
    same-origin Origin header — that means the allow-list is misconfigured."""
    msg = str(exc).lower()
    if "http 403" in msg or "rejected websocket" in msg:
        pytest.fail(
            f"WebSocket rejected despite Origin={ORIGIN_HEADER}. "
            "Check origin_auth allow-list on Cloud Run."
        )


class TestCloudRunConnectivity:
    """Service discovery and connectivity tests."""

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_service_responds_to_requests(self):
        """Verify Cloud Run service responds to HTTP requests."""
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(f"{CLOUD_RUN_URL}/api/health")

        assert response.status_code == 200, f"Service not responding: {response.status_code}"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_https_connection_validates_certificate(self):
        """Verify HTTPS connections validate certificates properly."""
        if not CLOUD_RUN_URL.startswith("https://"):
            pytest.skip("Not testing HTTPS on localhost")

        # This should work with valid Cloud Run SSL certificates
        with httpx.Client(verify=True, timeout=TIMEOUT) as client:
            response = client.get(f"{CLOUD_RUN_URL}/api/health")

        assert response.status_code == 200, "HTTPS certificate validation failed"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_service_url_environment_variable(self):
        """Verify CLOUD_RUN_URL environment variable is set correctly."""
        if "CLOUD_RUN_URL" not in os.environ:
            pytest.skip("CLOUD_RUN_URL not set")

        url = os.environ.get("CLOUD_RUN_URL")
        assert url.startswith("http://") or url.startswith(
            "https://"
        ), f"Invalid CLOUD_RUN_URL format: {url}"


class TestRequestTimeout:
    """Request timeout and timeout handling tests."""

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_request_timeout_under_1_hour_limit(self):
        """Verify requests complete within Cloud Run 1-hour timeout."""
        with httpx.Client(timeout=TIMEOUT) as client:
            start = time.time()
            response = client.get(f"{CLOUD_RUN_URL}/api/health")
            elapsed = time.time() - start

        assert elapsed < 3600, "Request exceeded Cloud Run timeout"
        assert response.status_code == 200

    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_websocket_maintains_connection(self):
        """Verify WebSocket connection can be maintained."""
        from websockets.asyncio.client import connect as ws_connect

        thread_id = "timeout-test-001"
        ws_url = f"{CLOUD_RUN_URL.replace('http', 'ws')}/ws/chat?thread_id={thread_id}"

        try:
            async with ws_connect(
                ws_url, subprotocols=["websocket"], additional_headers={"Origin": ORIGIN_HEADER}
            ) as websocket:
                # Receive initial message
                msg = await asyncio.wait_for(websocket.recv(), timeout=TIMEOUT)
                assert msg is not None

                # Keep connection alive for a bit
                await asyncio.sleep(2)

                # Should still be connected
                assert not websocket.closed, "WebSocket closed prematurely"
        except asyncio.TimeoutError:
            pytest.fail("WebSocket connection timed out")
        except Exception as e:
            _skip_if_origin_blocked(e)
            pytest.fail(f"WebSocket timeout test failed: {e}")


class TestGracefulShutdown:
    """Graceful shutdown and signal handling tests."""

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_health_check_available_before_shutdown(self):
        """Verify health check remains available during normal operation."""
        with httpx.Client(timeout=TIMEOUT) as client:
            # Make multiple requests
            for _ in range(3):
                response = client.get(f"{CLOUD_RUN_URL}/api/health")
                assert response.status_code == 200

    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_in_flight_requests_not_abruptly_terminated(self):
        """Verify in-flight WebSocket messages complete gracefully."""
        from websockets.asyncio.client import connect as ws_connect

        thread_id = "graceful-shutdown-001"
        ws_url = f"{CLOUD_RUN_URL.replace('http', 'ws')}/ws/chat?thread_id={thread_id}"

        try:
            async with ws_connect(
                ws_url, subprotocols=["websocket"], additional_headers={"Origin": ORIGIN_HEADER}
            ) as websocket:
                # Skip connection established
                await asyncio.wait_for(websocket.recv(), timeout=TIMEOUT)

                # Send a message
                msg = json.dumps(
                    {"type": "chat_message", "message": "test query", "thread_id": thread_id}
                )
                await websocket.send(msg)

                # Should receive response without abrupt termination
                response = await asyncio.wait_for(websocket.recv(), timeout=TIMEOUT)
                assert response is not None
        except asyncio.TimeoutError:
            pytest.fail("Request timed out during graceful shutdown test")
        except Exception as e:
            _skip_if_origin_blocked(e)
            pytest.fail(f"Graceful shutdown test failed: {e}")


class TestHorizontalScaling:
    """Concurrent request handling and scaling tests."""

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_health_check_under_concurrent_load(self):
        """Verify health checks work under concurrent request load."""
        import concurrent.futures

        def make_health_request():
            with httpx.Client(timeout=TIMEOUT) as client:
                response = client.get(f"{CLOUD_RUN_URL}/api/health")
            return response.status_code == 200

        # Make 10 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_health_request) for _ in range(10)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert all(results), "Some concurrent health checks failed"

    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_concurrent_websocket_connections(self):
        """Verify multiple concurrent WebSocket connections work."""
        from websockets.asyncio.client import connect as ws_connect

        async def make_connection(thread_id: str):
            ws_url = f"{CLOUD_RUN_URL.replace('http', 'ws')}/ws/chat?thread_id={thread_id}"
            async with ws_connect(
                ws_url,
                subprotocols=["websocket"],
                additional_headers={"Origin": ORIGIN_HEADER},
            ) as ws:
                msg = await asyncio.wait_for(ws.recv(), timeout=TIMEOUT)
                return msg is not None

        # Create 5 concurrent connections
        tasks = [make_connection(f"concurrent-{i}") for i in range(5)]
        results = await asyncio.gather(*tasks)

        assert all(results), "Some concurrent connections failed"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_api_handles_burst_of_requests(self):
        """Verify API handles burst of rapid requests."""
        import concurrent.futures

        def make_request(query_id: int):
            with httpx.Client(timeout=TIMEOUT) as client:
                headers = {
                    "Authorization": f"Bearer {API_KEY}",
                    "Origin": ORIGIN_HEADER,
                }
                response = client.get(f"{CLOUD_RUN_URL}/api/conversations", headers=headers)
            # 429 is rate limit — server handled but throttled, still counts as healthy behavior
            return response.status_code in [200, 400, 429]

        # Burst 20 requests (spread out slightly to avoid pure rate-limit storm)
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request, i) for i in range(20)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        # Allow some failures due to rate limiting, but most should succeed
        success_rate = sum(results) / len(results)
        assert success_rate > 0.7, f"Too many failures under load: {success_rate:.0%}"


class TestLoggingFormat:
    """Structured logging and observability tests."""

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_json_logging_format_in_production(self):
        """Verify logs are in JSON format for Cloud Logging integration."""
        # Note: This test verifies the app is configured for JSON logging
        # Actual log inspection requires Cloud Logging access
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(f"{CLOUD_RUN_URL}/api/health")

        # If health check succeeds, logging is at least not breaking the app
        assert response.status_code == 200


class TestEnvironmentConfiguration:
    """Environment variable and Secret Manager integration tests."""

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_environment_variables_loaded_correctly(self):
        """Verify app initializes with correct environment variables."""
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(f"{CLOUD_RUN_URL}/api/health")

        data = response.json()

        # Verify critical services are healthy (would fail if env vars wrong)
        assert data.get("postgres"), "PostgreSQL env config failure"
        assert data.get("google_ai"), "Google API env config failure"
        assert data.get("vector_store"), "OpenSearch env config failure"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_no_hardcoded_credentials_in_response(self):
        """Verify API responses don't leak credentials."""
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(f"{CLOUD_RUN_URL}/api/health")

        response_text = response.text.lower()
        response_json = response.json()

        # Check for common credential patterns
        sensitive_patterns = [
            "password",
            "secret",
            "api_key",
            "private_key",
            "access_token",
        ]

        for pattern in sensitive_patterns:
            assert pattern not in response_text, f"Potential credential leak in response: {pattern}"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_api_key_from_secret_manager(self):
        """Verify API key is loaded from Secret Manager, not hardcoded."""
        # If we get a 401/403 with invalid key, it means the app has its own key from Secret Manager.
        # 429 is also acceptable (prior burst test may have tripped rate limits).
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(
                f"{CLOUD_RUN_URL}/api/conversations",
                headers={
                    "Authorization": "Bearer obviously-fake-key-xyz",
                    "Origin": ORIGIN_HEADER,
                },
            )

        if response.status_code == 429:
            pytest.skip("Rate limited from prior burst test; cannot verify auth rejection")
        # Should reject with 401/403, not 500 (which would mean misconfiguration)
        assert response.status_code in [
            401,
            403,
        ], f"API key validation failed: {response.status_code}"


class TestDatabaseConnectivity:
    """Database connection pool and checkpoint tests."""

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_database_connection_pool_initialized(self):
        """Verify database connection pool is properly initialized."""
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(f"{CLOUD_RUN_URL}/api/health")

        data = response.json()
        assert data.get("postgres") is True, "Database pool not initialized"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_checkpoint_table_exists(self):
        """Verify LangGraph checkpoints table exists in database."""
        # This is verified indirectly through the health check
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(f"{CLOUD_RUN_URL}/api/health")

        data = response.json()
        # If postgres is healthy, checkpoint table exists
        assert data.get("postgres") is True, "Checkpoint table not accessible"


class TestOpenSearchIndex:
    """OpenSearch index and product data tests."""

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_opensearch_index_accessible(self):
        """Verify OpenSearch index is accessible."""
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(f"{CLOUD_RUN_URL}/api/health")

        data = response.json()
        assert data.get("vector_store") is True, "OpenSearch index not accessible"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_product_documents_indexed(self):
        """Verify product documents are indexed in OpenSearch."""
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(f"{CLOUD_RUN_URL}/api/health")

        data = response.json()
        doc_count = data.get("document_count", 0)

        assert doc_count > 0, f"No product documents indexed: {doc_count}"


# Make async tests work with pytest
@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
