"""HTTP application: health endpoints and the built web app."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import PRODUCT_NAME, __version__
from app.db.engine import check_database, make_engine
from app.settings import Settings, get_settings

# Where the Dockerfile puts the Vite build (frontend/dist).
DEFAULT_STATIC_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def create_app(
    settings: Settings | None = None,
    static_dir: Path | None = DEFAULT_STATIC_DIR,
) -> FastAPI:
    """Build the application. The engine connects on first use only."""
    config = settings or get_settings()
    engine = make_engine(config.database_url.get_secret_value())

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(
        title=PRODUCT_NAME,
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str | None]:
        """Liveness, version and the commit the image was built from."""
        return {
            "status": "ok",
            "version": __version__,
            "revision": config.revision or None,
        }

    @app.get("/readyz")
    async def readyz() -> JSONResponse:
        """Ready when the database answers (phase C4 adds the worker heartbeat)."""
        if await check_database(engine):
            return JSONResponse({"status": "ready", "database": "ok"})
        return JSONResponse(
            {"status": "unavailable", "database": "unreachable"},
            status_code=503,
        )

    # Mounted last so the API routes above always win.
    if static_dir is not None and (static_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="web")
    return app
