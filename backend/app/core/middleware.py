"""Request context middleware: correlation IDs, timing and access logs."""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

access_logger = logging.getLogger("loopmesh.access")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a validated correlation id to each request and log its outcome."""

    def __init__(self, app, header_name: str = "X-Request-ID", skip_paths: tuple[str, ...] = ()) -> None:
        super().__init__(app)
        self.header_name = header_name
        self.skip_paths = skip_paths

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get(self.header_name, "")
        request_id = incoming if REQUEST_ID_PATTERN.match(incoming) else uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers[self.header_name] = request_id
        response.headers["X-Response-Time-ms"] = str(duration_ms)

        if request.url.path not in self.skip_paths:
            access_logger.info(
                "%s %s -> %s",
                request.method,
                request.url.path,
                response.status_code,
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
        return response
