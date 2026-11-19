"""Per-request ASGI middleware: request id, security headers, body size limit,
access log, and the last-resort answer to an unhandled error.

The access log names the route template (/api/v1/users/{user_id}), never the
raw path or query, which can carry tokens. An unhandled error is logged with its
class and stack frames (app/logging.py drops the text) and answered with a 500
problem document; it is not re-raised, so the server never logs it again.
Request bodies under /api/ are limited to 64 KiB (413): sign-in and first run
are anonymous and would otherwise read any body into memory. The CSV import
takes up to 1 MiB of file (BODY_LIMITS).
"""

import logging
import re
import time
import uuid

from fastapi import HTTPException
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.problems import problem_response
from app.logging import request_id_var
from app.security.headers import SECURITY_HEADERS

logger = logging.getLogger("app.http")

REQUEST_ID_HEADER = b"x-request-id"
MAX_API_BODY = 64 * 1024
# Routes that take more: the file plus room for the multipart framing.
BODY_LIMITS = {"/api/v1/jobs/import.csv": 1024 * 1024 + 16 * 1024}
# Sent only when BASE_URL is https: a plain-http install must not pin HTTPS.
HSTS_HEADER = (b"strict-transport-security", b"max-age=31536000")
# A request id from the proxy is kept when it looks like one; else a new one.
_SAFE_REQUEST_ID = re.compile(rb"[A-Za-z0-9._-]{8,64}")
_OWN_HEADERS = frozenset(
    {name.encode("latin-1") for name, _ in SECURITY_HEADERS}
    | {REQUEST_ID_HEADER, HSTS_HEADER[0], b"cache-control"}
)
# Probes of the container and the proxy: logged at debug level only.
_QUIET_ROUTES = frozenset({"/healthz", "/readyz"})


class BodyTooLarge(HTTPException):
    """A request body past the limit. FastAPI passes an HTTPException raised
    while it reads the body through unchanged, so the answer is a 413 problem."""

    def __init__(self, limit: int) -> None:
        super().__init__(413, f"The request body is larger than {limit} bytes.")


def _request_id(scope: Scope) -> str:
    for name, value in scope.get("headers", []):
        if name == REQUEST_ID_HEADER and _SAFE_REQUEST_ID.fullmatch(value):
            return str(value.decode("ascii"))
    return uuid.uuid4().hex


def _content_length(scope: Scope) -> int:
    """The declared body length; -1 when it is missing or not a number."""
    for name, value in scope.get("headers", []):
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return -1
    return -1


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
    def __init__(
        self, app: ASGIApp, *, hsts: bool = False, max_body: int = MAX_API_BODY
    ) -> None:
        self.app = app
        self.hsts = hsts
        self.max_body = max_body

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = _request_id(scope)
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status = 500
        response_started = False
        path = str(scope.get("path", ""))
        api = path.startswith("/api/")
        max_body = BODY_LIMITS.get(path, self.max_body)
        received = 0

        async def limited_receive() -> Message:
            # Counts streamed bytes too: a chunked body declares no length.
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > max_body:
                    raise BodyTooLarge(max_body)
            return message

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
                if self.hsts:
                    headers.append(HSTS_HEADER)
                if api:
                    headers.append((b"cache-control", b"no-store"))
                message = {**message, "headers": headers}
            await send(message)

        try:
            if not api:
                await self.app(scope, receive, send_with_headers)
            elif _content_length(scope) > max_body:
                too_large = BodyTooLarge(max_body)
                response = problem_response(path, 413, detail=too_large.detail)
                await response(scope, receive, send_with_headers)
            else:
                await self.app(scope, limited_receive, send_with_headers)
        except Exception as error:
            logger.error("unhandled error", exc_info=error)
            if response_started:
                return
            response = problem_response(path, 500)
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
