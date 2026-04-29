"""
Unit tests for api/middleware/auth.py.

All tests mock the API_KEY config value so no real environment setup is needed.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.middleware.auth import (
    AuthConfigurationError,
    validate_api_key_configured,
    verify_api_key,
    verify_websocket_api_key,
)

# ---------------------------------------------------------------------------
# validate_api_key_configured
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateApiKeyConfigured:
    def test_raises_when_api_key_empty(self):
        with patch("api.middleware.auth.API_KEY", ""):
            with pytest.raises(AuthConfigurationError):
                validate_api_key_configured()

    def test_raises_when_api_key_none(self):
        with patch("api.middleware.auth.API_KEY", None):
            with pytest.raises(AuthConfigurationError):
                validate_api_key_configured()

    def test_passes_when_api_key_set(self):
        with patch("api.middleware.auth.API_KEY", "secret"):
            validate_api_key_configured()  # should not raise


# ---------------------------------------------------------------------------
# verify_api_key
# ---------------------------------------------------------------------------


def _mock_request(header_value=None):
    req = MagicMock()
    req.headers.get = MagicMock(return_value=header_value)
    return req


@pytest.mark.unit
class TestVerifyApiKey:
    @pytest.mark.asyncio
    async def test_valid_key_returns_true(self):
        with patch("api.middleware.auth.API_KEY", "secret"):
            request = _mock_request(header_value="secret")
            result = await verify_api_key(request, api_key="secret")
            assert result is True

    @pytest.mark.asyncio
    async def test_missing_key_raises_401(self):
        with patch("api.middleware.auth.API_KEY", "secret"):
            request = _mock_request(header_value=None)
            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key(request, api_key=None)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_key_raises_401(self):
        with patch("api.middleware.auth.API_KEY", "secret"):
            request = _mock_request(header_value="wrong")
            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key(request, api_key="wrong")
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_unconfigured_api_key_raises_auth_error(self):
        with patch("api.middleware.auth.API_KEY", ""):
            request = _mock_request()
            with pytest.raises(AuthConfigurationError):
                await verify_api_key(request, api_key="anything")

    @pytest.mark.asyncio
    async def test_key_read_from_header_when_not_injected(self):
        with patch("api.middleware.auth.API_KEY", "secret"):
            request = _mock_request(header_value="secret")
            result = await verify_api_key(request, api_key=None)
            assert result is True

    @pytest.mark.asyncio
    async def test_injected_key_takes_precedence_over_header(self):
        """api_key param overrides header; wrong header but correct param → pass."""
        with patch("api.middleware.auth.API_KEY", "secret"):
            request = _mock_request(header_value="wrong-header")
            result = await verify_api_key(request, api_key="secret")
            assert result is True


# ---------------------------------------------------------------------------
# verify_websocket_api_key
# ---------------------------------------------------------------------------


def _mock_websocket(query_param_value=None, api_key_configured=True):
    ws = MagicMock()
    ws.close = AsyncMock()
    ws.query_params = MagicMock()
    ws.query_params.get = MagicMock(return_value=query_param_value)
    return ws


@pytest.mark.unit
class TestVerifyWebsocketApiKey:
    @pytest.mark.asyncio
    async def test_valid_key_returns_true(self):
        with patch("api.middleware.auth.API_KEY", "secret"):
            ws = _mock_websocket(query_param_value="secret")
            result = await verify_websocket_api_key(ws)
            assert result is True
            ws.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_key_closes_with_4001(self):
        with patch("api.middleware.auth.API_KEY", "secret"):
            ws = _mock_websocket(query_param_value=None)
            result = await verify_websocket_api_key(ws)
            assert result is False
            ws.close.assert_awaited_once()
            assert ws.close.call_args.kwargs["code"] == 4001

    @pytest.mark.asyncio
    async def test_wrong_key_closes_with_4001(self):
        with patch("api.middleware.auth.API_KEY", "secret"):
            ws = _mock_websocket(query_param_value="bad")
            result = await verify_websocket_api_key(ws)
            assert result is False
            assert ws.close.call_args.kwargs["code"] == 4001

    @pytest.mark.asyncio
    async def test_unconfigured_api_key_closes_with_4002(self):
        with patch("api.middleware.auth.API_KEY", ""):
            ws = _mock_websocket(query_param_value="anything")
            result = await verify_websocket_api_key(ws)
            assert result is False
            assert ws.close.call_args.kwargs["code"] == 4002
