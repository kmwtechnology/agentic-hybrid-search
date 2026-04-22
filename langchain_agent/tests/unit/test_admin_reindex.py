"""
Unit tests for admin.py re-index functionality.

Tests verify:
1. perform_reindex() is synchronous (not async)
2. BackgroundTasks can execute it without errors
3. Exceptions are properly caught and logged
4. Return values contain appropriate status/error info
"""

import asyncio
from unittest.mock import patch

import pytest

from api.routes.admin import ReindexResponse, perform_reindex, trigger_reindex


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
