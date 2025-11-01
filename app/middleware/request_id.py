from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send
from fastapi import Request
import uuid
from typing import Callable

from app.core.logging import request_id_var


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Middleware that ensures a request id is present for every request and
    stores it in a contextvar so logging can include it.

    Adds/reads the `X-Request-ID` header and sets `request_id_var` for the
    duration of the request.
    """

    async def dispatch(self, request: Request, call_next: Callable):
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())

        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
            # Ensure the response has the request id header
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            # Reset the contextvar so it doesn't leak to other requests
            try:
                request_id_var.reset(token)
            except Exception:
                # If reset fails for some reason, ignore to avoid crashing
                pass
