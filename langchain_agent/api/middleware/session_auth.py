"""
Session-cookie authentication for the shared-password login gate.

The gate is a single shared password — when validated server-side it sets
``request.session["authenticated"] = True`` via Starlette's SessionMiddleware
(signed cookie). This module verifies the cookie on protected REST routes
and on the WebSocket handshake.

Layered with ``origin_auth.verify_same_origin`` (defense in depth):
* origin auth blocks cross-site usage
* session auth blocks anyone-with-the-URL who hasn't entered the password
"""

import logging

from fastapi import HTTPException, Request, WebSocket, status

logger = logging.getLogger(__name__)

# WebSocket close codes (4xxx range is application-defined per RFC 6455)
WS_CLOSE_UNAUTHORIZED = 4401


def _is_session_authenticated(session_like) -> bool:
    """Return True iff the session mapping carries ``authenticated=True``.

    Starlette stores ``session`` on both the HTTP scope and the WS scope as
    a plain dict-like object once SessionMiddleware is registered. We accept
    anything that supports ``.get`` so the helper is unit-testable without a
    real Starlette scope.
    """
    if session_like is None:
        return False
    try:
        return bool(session_like.get("authenticated"))
    except AttributeError:
        return False


async def verify_session(request: Request) -> bool:
    """Require an authenticated session for a REST route.

    Raises 401 when the session cookie is missing/invalid/unauthenticated.
    Returns True on success so callers can early-return cleanly.
    """
    session = getattr(request, "session", None)
    if _is_session_authenticated(session):
        return True

    logger.info(
        "session_auth_rejected",
        extra={
            "path": request.url.path,
            "method": request.method,
            "client": request.client.host if request.client else None,
        },
    )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Please log in.",
        headers={"WWW-Authenticate": "Session"},
    )


async def verify_websocket_session(websocket: WebSocket) -> bool:
    """Require an authenticated session before accepting a WebSocket.

    Returns True on success. On failure closes the connection with code 4401
    (custom unauthorized) and returns False so the caller can early-return.

    The browser sends the session cookie automatically on same-origin WS
    upgrades — no frontend code change needed.
    """
    session = getattr(websocket, "session", None)
    if _is_session_authenticated(session):
        return True

    logger.info(
        "websocket_session_auth_rejected",
        extra={"client": websocket.client.host if websocket.client else None},
    )
    await websocket.close(
        code=WS_CLOSE_UNAUTHORIZED,
        reason="Authentication required. Please log in.",
    )
    return False
