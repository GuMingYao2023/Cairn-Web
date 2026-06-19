"""HTTP Basic Auth middleware for Cairn API server.

Credentials are read from environment variables:
    CAIRN_USER  — username for Basic Auth
    CAIRN_PASS  — password for Basic Auth

If either variable is unset or empty, authentication is **disabled**
so the server runs freely for local development.

Usage in app.py:
    from cairn.server.auth import AuthMiddleware
    app.add_middleware(AuthMiddleware)
"""

import base64
import os
import secrets
from typing import ClassVar

from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.status import HTTP_401_UNAUTHORIZED

# ── Paths that never require authentication ──────────────────────────────
# Healthcheck endpoint used by docker-compose; no credentials needed.
PUBLIC_PATHS: set[str] = {"/health"}


class AuthMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that enforces HTTP Basic Auth when env vars are set."""

    _realm: ClassVar[str] = "Cairn"

    @staticmethod
    def _load_credentials() -> tuple[str | None, str | None]:
        user = os.environ.get("CAIRN_USER") or None
        passwd = os.environ.get("CAIRN_PASS") or None
        return user, passwd

    def _unauthorized(self, headers: Headers) -> Response:
        """Return 401 with WWW-Authenticate header, respecting X-Requested-With."""
        accept = headers.get("accept", "")
        detail = "Unauthorized"

        # API clients get JSON; browsers see a plain-text fallback.
        if "application/json" in accept or "text/plain" in accept:
            body = detail
            content_type = "text/plain"
        else:
            body = detail
            content_type = "text/plain"

        return Response(
            content=body,
            status_code=HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": f'Basic realm="{self._realm}"'},
            media_type=content_type,
        )

    async def dispatch(self, request: Request, call_next):
        # ── 1. Auth disabled when env vars are unset ────────────────────
        user, passwd = self._load_credentials()
        if user is None or passwd is None:
            return await call_next(request)

        # ── 2. Public paths (healthcheck etc.) ──────────────────────────
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        # ── 3. Read and validate Basic Auth header ──────────────────────
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Basic "):
            return self._unauthorized(request.headers)

        try:
            decoded = base64.b64decode(auth_header.removeprefix("Basic ")).decode("utf-8")
        except Exception:
            return self._unauthorized(request.headers)

        if ":" not in decoded:
            return self._unauthorized(request.headers)

        provided_user, provided_pass = decoded.split(":", 1)

        user_ok = secrets.compare_digest(provided_user, user)
        pass_ok = secrets.compare_digest(provided_pass, passwd)
        if not (user_ok and pass_ok):
            return self._unauthorized(request.headers)

        return await call_next(request)
