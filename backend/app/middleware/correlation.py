"""
Correlation ID middleware — LawMate
====================================
Injects a unique X-Correlation-ID into every request so that all log lines
for a single HTTP call share the same identifier regardless of which tab,
service, or retry produced it.

Also echoes X-Tab-ID back in the response if the client sent one, enabling
per-tab log tracing.
"""
from __future__ import annotations

import uuid
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # Accept from client or generate fresh
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        tab_id = request.headers.get("X-Tab-ID", "")

        # Make available to endpoint handlers via request.state
        request.state.correlation_id = correlation_id
        request.state.tab_id = tab_id

        # Structured log on every request
        logger.info(
            "request",
            extra={
                "correlation_id": correlation_id,
                "tab_id": tab_id or None,
                "method": request.method,
                "path": request.url.path,
            },
        )

        response = await call_next(request)

        # Echo IDs in response headers for client-side log correlation
        response.headers["X-Correlation-ID"] = correlation_id
        if tab_id:
            response.headers["X-Tab-ID"] = tab_id

        return response
