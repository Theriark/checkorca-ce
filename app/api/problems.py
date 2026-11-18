"""Errors as RFC 9457 problem details, each with the request id.

Validation errors list the location and message of each problem but never the
submitted value, which may be a password or a token (D-6).
"""

from collections.abc import Callable, Coroutine, Mapping
from http import HTTPStatus
from typing import Any

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from app.access import AccessDenied
from app.logging import request_id_var

PROBLEM_MEDIA_TYPE = "application/problem+json"


class FieldProblem(BaseModel):
    """One invalid input: where it is (for example body.email) and why."""

    field: str
    message: str


class Problem(BaseModel):
    """An RFC 9457 problem details document."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    request_id: str | None = None
    errors: list[FieldProblem] | None = None


# Shared by every /api/v1 route in the OpenAPI document; problem_media_type
# then declares them with the media type the handlers send.
PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    "4XX": {"model": Problem, "description": "Problem details (RFC 9457)"},
}


def problem_media_type(document: dict[str, Any]) -> dict[str, Any]:
    """Move the 4XX answers of an OpenAPI document to application/problem+json.

    FastAPI files a response model under application/json; the handlers below
    send application/problem+json, and the frontend types follow the document.
    """
    for operations in document.get("paths", {}).values():
        for operation in operations.values():
            content = operation.get("responses", {}).get("4XX", {}).get("content")
            if content and "application/json" in content:
                content[PROBLEM_MEDIA_TYPE] = content.pop("application/json")
    return document


class ProblemError(Exception):
    """Raise to answer with a problem document."""

    def __init__(
        self,
        status: int,
        title: str,
        detail: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(title)
        self.status = status
        self.title = title
        self.detail = detail
        self.headers = headers


def problem_response(
    path: str,
    status: int,
    title: str | None = None,
    detail: str | None = None,
    headers: Mapping[str, str] | None = None,
    errors: list[FieldProblem] | None = None,
) -> JSONResponse:
    problem = Problem(
        title=title or HTTPStatus(status).phrase,
        status=status,
        detail=detail,
        instance=path,
        request_id=request_id_var.get(),
        errors=errors,
    )
    return JSONResponse(
        problem.model_dump(exclude_none=True),
        status_code=status,
        headers=headers,
        media_type=PROBLEM_MEDIA_TYPE,
    )


async def handle_problem(request: Request, error: ProblemError) -> JSONResponse:
    return problem_response(
        request.url.path, error.status, error.title, error.detail, error.headers
    )


async def handle_http_error(request: Request, error: HTTPException) -> JSONResponse:
    phrase = HTTPStatus(error.status_code).phrase
    detail = error.detail if error.detail and error.detail != phrase else None
    return problem_response(
        request.url.path, error.status_code, phrase, detail, error.headers
    )


async def handle_validation_error(
    request: Request, error: RequestValidationError
) -> JSONResponse:
    errors = [
        FieldProblem(
            field=".".join(str(part) for part in item.get("loc", ())),
            message=str(item.get("msg", "invalid")),
        )
        for item in error.errors()
    ]
    return problem_response(
        request.url.path,
        422,
        "Invalid request",
        "One or more fields are invalid.",
        errors=errors,
    )


async def handle_access_denied(request: Request, error: AccessDenied) -> JSONResponse:
    return problem_response(request.url.path, 403, "Forbidden")


ExceptionHandler = Callable[[Request, Any], Coroutine[Any, Any, Response]]

EXCEPTION_HANDLERS: dict[int | type[Exception], ExceptionHandler] = {
    ProblemError: handle_problem,
    HTTPException: handle_http_error,
    RequestValidationError: handle_validation_error,
    AccessDenied: handle_access_denied,
}
