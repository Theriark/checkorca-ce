"""The built web app (frontend/dist) with a single-page fallback.

It answers what no route of the app matched (it is the router's default):

- GET or HEAD of a built file: the file.
- GET or HEAD of any other path outside /api/: HTTP 200 with index.html, so a
  deep link such as /login or /clients/ID boots the app and its router shows
  the screen (or its own not-found page).
- Anything else, and every unknown path under /api/: the router's own answer,
  a 404 (or 405) problem document, never HTML.

The security headers come from the request middleware for every answer.
"""

from pathlib import Path

from starlette.exceptions import HTTPException
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send

API_PREFIX = "/api"
# index.html names the hashed bundle files, so it must never be cached for
# long; the bundle files themselves can be.
INDEX_CACHE_CONTROL = "no-cache"


def is_api_path(path: str) -> bool:
    return path == API_PREFIX or path.startswith(API_PREFIX + "/")


class SinglePageApp:
    """Serves the build folder; index.html for paths that are not files."""

    def __init__(self, directory: Path, fallback: ASGIApp) -> None:
        self.files = StaticFiles(directory=directory)
        self.index = directory / "index.html"
        self.fallback = fallback

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = str(scope.get("path", ""))
        if (
            scope["type"] != "http"
            or scope.get("method") not in ("GET", "HEAD")
            or is_api_path(path)
        ):
            await self.fallback(scope, receive, send)
            return
        # Marks the request for the access log (route "static").
        scope["endpoint"] = self.files
        try:
            response = await self.files.get_response(self.files.get_path(scope), scope)
        except HTTPException as error:
            if error.status_code != 404:
                raise
            response = FileResponse(
                self.index,
                media_type="text/html",
                headers={"cache-control": INDEX_CACHE_CONTROL},
            )
        await response(scope, receive, send)
