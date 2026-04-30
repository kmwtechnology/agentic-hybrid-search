"""
Unit tests for admin.py re-index functionality.

Tests verify:
1. perform_reindex() is synchronous (not async)
2. BackgroundTasks can execute it without errors
3. Exceptions are properly caught and logged
4. Return values contain appropriate status/error info
5. In-process job state transitions correctly through queued → running → success/error
6. /api/admin/reindex/status returns the current state dict
"""

import asyncio
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.routes import admin as admin_module
from api.routes.admin import ReindexResponse, perform_reindex, trigger_reindex


@pytest.fixture(autouse=True)
def _reset_reindex_state():
    """Reset the module-level job state before and after every test."""
    fresh = {
        "status": "idle",
        "started_at": None,
        "finished_at": None,
        "limit": None,
        "reset_index": None,
        "documents_ingested": None,
        "chunks_created": None,
        "error": None,
    }
    with admin_module._reindex_state_lock:
        admin_module._reindex_state.clear()
        admin_module._reindex_state.update(fresh)
    yield
    with admin_module._reindex_state_lock:
        admin_module._reindex_state.clear()
        admin_module._reindex_state.update(fresh)


class TestPerformReindexSignature:
    """Verify perform_reindex is synchronous for BackgroundTasks compatibility."""

    def test_perform_reindex_is_not_async(self):
        """Verify function is not async (BackgroundTasks requires sync callables)."""
        import inspect

        assert not inspect.iscoroutinefunction(
            perform_reindex
        ), "perform_reindex must be synchronous for BackgroundTasks.add_task()"

    def test_perform_reindex_returns_reindex_response(self):
        """Verify return type annotation is ReindexResponse."""
        import inspect

        sig = inspect.signature(perform_reindex)
        assert sig.return_annotation == ReindexResponse


class TestPerformReindexExceptionHandling:
    """Verify exceptions are caught and logged with full traceback."""

    @patch("ingest_esci_products.ingest_esci_products")
    def test_file_not_found_caught_and_logged(self, mock_ingest):
        """FileNotFoundError should be caught and logged with context."""
        mock_ingest.side_effect = FileNotFoundError("Dataset not found")

        result = perform_reindex(limit=100, force_resample=False, reset_index=True)

        assert result.status == "error"
        assert result.error is not None
        assert "Dataset not found" in result.error

    @patch("ingest_esci_products.ingest_esci_products")
    def test_connection_error_caught_and_logged(self, mock_ingest):
        """ConnectionError should be caught and logged."""
        from requests.exceptions import ConnectionError

        mock_ingest.side_effect = ConnectionError("Failed to connect to OpenSearch")

        result = perform_reindex(limit=100, force_resample=False, reset_index=True)

        assert result.status == "error"
        assert result.error is not None
        assert "ConnectionError" in result.error

    @patch("ingest_esci_products.ingest_esci_products")
    def test_generic_exception_caught(self, mock_ingest):
        """Generic exceptions should be caught with type and message."""
        mock_ingest.side_effect = RuntimeError("Something went wrong")

        result = perform_reindex(limit=100, force_resample=False, reset_index=True)

        assert result.status == "error"
        assert "RuntimeError" in result.error
        assert "Something went wrong" in result.error

    @patch("ingest_esci_products.ingest_esci_products")
    def test_success_returns_document_counts(self, mock_ingest):
        """Successful ingestion should return document and chunk counts."""
        mock_ingest.return_value = (1000, 2500)

        result = perform_reindex(limit=1000, force_resample=False, reset_index=True)

        assert result.status == "success"
        assert result.documents_ingested == 1000
        assert result.chunks_created == 2500
        assert result.error is None


class TestBackgroundTasksCompatibility:
    """Verify perform_reindex works with FastAPI BackgroundTasks."""

    @patch("ingest_esci_products.ingest_esci_products")
    def test_can_be_called_by_background_tasks(self, mock_ingest):
        """Verify function can be called like BackgroundTasks.add_task() would call it."""
        from fastapi import BackgroundTasks

        background_tasks = BackgroundTasks()
        mock_ingest.return_value = (100, 250)

        result = perform_reindex(limit=100, force_resample=False, reset_index=True)

        assert result is not None
        assert isinstance(result, ReindexResponse)

    @patch("ingest_esci_products.ingest_esci_products")
    def test_parameters_passed_correctly_to_ingest(self, mock_ingest):
        """Verify parameters are passed through to ingest_esci_products."""
        mock_ingest.return_value = (100, 250)

        perform_reindex(limit=500, force_resample=True, reset_index=False)

        mock_ingest.assert_called_once_with(
            limit=500,
            force_resample=True,
            reset_index=False,
        )


class TestReindexResponse:
    """Verify ReindexResponse model."""

    def test_success_response_fields(self):
        """Verify success response has expected fields."""
        response = ReindexResponse(
            status="success",
            message="Test message",
            documents_ingested=100,
            chunks_created=250,
        )

        assert response.status == "success"
        assert response.message == "Test message"
        assert response.documents_ingested == 100
        assert response.chunks_created == 250
        assert response.error is None

    def test_error_response_fields(self):
        """Verify error response has expected fields."""
        response = ReindexResponse(
            status="error",
            message="Re-index failed",
            error="Connection refused",
        )

        assert response.status == "error"
        assert response.error == "Connection refused"
        assert response.documents_ingested is None
        assert response.chunks_created is None


class TestReindexStateTransitions:
    """Verify the in-process job state updates as the ETL progresses."""

    @patch("ingest_esci_products.ingest_esci_products")
    def test_success_transitions_state_to_success_with_counts(self, mock_ingest):
        mock_ingest.return_value = (500, 1200)

        perform_reindex(limit=500, force_resample=False, reset_index=True)

        state = admin_module._read_reindex_state()
        assert state["status"] == "success"
        assert state["documents_ingested"] == 500
        assert state["chunks_created"] == 1200
        assert state["error"] is None
        assert state["started_at"] is not None
        assert state["finished_at"] is not None
        assert state["limit"] == 500
        assert state["reset_index"] is True

    @patch("ingest_esci_products.ingest_esci_products")
    def test_generic_exception_transitions_state_to_error(self, mock_ingest):
        mock_ingest.side_effect = RuntimeError("boom")

        perform_reindex(limit=100, force_resample=False, reset_index=True)

        state = admin_module._read_reindex_state()
        assert state["status"] == "error"
        assert "RuntimeError" in state["error"]
        assert "boom" in state["error"]
        assert state["documents_ingested"] is None
        assert state["finished_at"] is not None

    @patch("ingest_esci_products.ingest_esci_products")
    def test_file_not_found_transitions_state_to_error(self, mock_ingest):
        mock_ingest.side_effect = FileNotFoundError("missing parquet")

        perform_reindex(limit=100, force_resample=False, reset_index=True)

        state = admin_module._read_reindex_state()
        assert state["status"] == "error"
        assert "missing parquet" in state["error"]


class TestReindexEndpoint:
    """End-to-end endpoint tests using FastAPI's TestClient."""

    @pytest.fixture
    def client(self) -> TestClient:
        from api.main import app

        return TestClient(app)

    def test_status_endpoint_returns_initial_idle_state(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-admin-token-12345")
        resp = client.get(
            "/api/admin/reindex/status",
            headers={
                "Host": "localhost:8000",
                "X-Admin-Token": "test-admin-token-12345",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "idle"
        assert body["documents_ingested"] is None
        assert body["error"] is None

    @patch("ingest_esci_products.ingest_esci_products")
    def test_trigger_then_status_reflects_success(self, mock_ingest, client, monkeypatch):
        """End-to-end: trigger runs the background task (TestClient drains it
        before returning), then the status endpoint reports success."""
        monkeypatch.setenv("ADMIN_TOKEN", "test-admin-token-12345")
        mock_ingest.return_value = (42, 101)

        auth_headers = {
            "Host": "localhost:8000",
            "X-Admin-Token": "test-admin-token-12345",
        }
        trigger_resp = client.get(
            "/api/admin/reindex?reset_index=true&limit=42",
            headers=auth_headers,
        )
        assert trigger_resp.status_code == 200
        assert trigger_resp.json()["status"] == "started"

        status_resp = client.get("/api/admin/reindex/status", headers=auth_headers)
        assert status_resp.status_code == 200
        state = status_resp.json()
        assert state["status"] == "success"
        assert state["documents_ingested"] == 42
        assert state["chunks_created"] == 101
        assert state["limit"] == 42
        assert state["reset_index"] is True

    @patch("ingest_esci_products.ingest_esci_products")
    def test_trigger_resets_previous_terminal_state(self, mock_ingest, client, monkeypatch):
        """After a successful run, triggering again must clear the prior
        success/error fields so polling can't mistake stale state for its
        own run."""
        monkeypatch.setenv("ADMIN_TOKEN", "test-admin-token-12345")
        # Seed a prior success directly in module state.
        admin_module._update_reindex_state(
            status="success",
            started_at="2020-01-01T00:00:00+00:00",
            finished_at="2020-01-01T00:05:00+00:00",
            documents_ingested=1,
            chunks_created=1,
            error=None,
        )

        # New trigger: mock raises before the task completes so we can inspect
        # state mid-flight. But TestClient drains background tasks synchronously,
        # so we inspect the final state after the error.
        mock_ingest.side_effect = RuntimeError("fresh failure")

        auth_headers = {
            "Host": "localhost:8000",
            "X-Admin-Token": "test-admin-token-12345",
        }
        client.get(
            "/api/admin/reindex?reset_index=false&limit=5",
            headers=auth_headers,
        )
        state = admin_module._read_reindex_state()

        # Prior success fields must be cleared; error from the new run surfaces.
        assert state["status"] == "error"
        assert state["documents_ingested"] is None
        assert state["chunks_created"] is None
        assert "fresh failure" in state["error"]
        # New trigger's params, not the old ones.
        assert state["limit"] == 5
        assert state["reset_index"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
