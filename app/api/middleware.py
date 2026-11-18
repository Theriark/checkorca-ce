"""Per-request ASGI middleware: request id, security headers, access log, and
the last-resort answer to an unhandled error.

The access log names the route template (/api/v1/users/{user_id}), never the
raw path or query, which can carry tokens. An unhandled error is logged with its
class and stack frames (app/logging.py drops the text) and answered with a 500
problem document; it is not re-raised, so the server never logs it again.
"""

import logging
import re
import time
import uuid

from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.problems import problem_response
from app.logging import request_id_var
from app.security.headers import SECURITY_HEADERS

logger = logging.getLogger("app.http")

REQUEST_ID_HEADER = b"x-request-id"
# A request id from the proxy is kept when it looks like one; else a new one.
_SAFE_REQUEST_ID = re.compile(rb"[A-Za-z0-9._-]{8,64}")
_OWN_HEADERS = frozenset(
    {name.encode("latin-1") for name, _ in SECURITY_HEADERS}
    | {REQUEST_ID_HEADER, b"cache-control"}
)
# Probes of the container and the proxy: logged at debug level only.
_QUIET_ROUTES = frozenset({"/healthz", "/readyz"})


def _request_id(scope: Scope) -> str:
    for name, value in scope.get("headers", []):
        if name == REQUEST_ID_HEADER and _SAFE_REQUEST_ID.fullmatch(value):
            return str(value.decode("ascii"))
    return uuid.uuid4().hex


def _route_template(scope: Scope) -> str:
    """The path with every path parameter replaced by its name, never its value;
    "static" for the web app files, "unmatched" when no route matched."""
    if isinstance(scope.get("endpoint"), StaticFiles):
        return "static"
    if scope.get("route") is None:
        return "unmatched"
    names = {str(value): name for name, value in scope.get("path_params", {}).items()}
    parts = str(scope.get("path", "")).split("/")
    return "/".join(f"{{{names[part]}}}" if part in names else part for part in parts)


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = _request_id(scope)
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status = 500
        response_started = False
        api = str(scope.get("path", "")).startswith("/api/")

        async def send_with_headers(message: Message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status = int(message["status"])
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() not in _OWN_HEADERS
                    or (name.lower() == b"cache-control" and not api)
                ]
                headers.extend(
                    (name.encode("latin-1"), value.encode("latin-1"))
                    for name, value in SECURITY_HEADERS
                )
                headers.append((REQUEST_ID_HEADER, request_id.encode("ascii")))
                if api:
                    headers.append((b"cache-control", b"no-store"))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        except Exception as error:
            logger.error("unhandled error", exc_info=error)
            if response_started:
                return
            response = problem_response(str(scope.get("path", "")), 500)
            await response(scope, receive, send_with_headers)
        finally:
            route = _route_template(scope)
            level = logging.DEBUG if route in _QUIET_ROUTES else logging.INFO
            logger.log(
                level,
                "request",
                extra={
                    "method": scope.get("method"),
                    "route": route,
                    "status": status,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            request_id_var.reset(token)
