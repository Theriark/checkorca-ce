"""HTTP application: health endpoints, the /api/v1 routes and the built web app.

The web app answers what no route matched (app/web.py): built files, and
index.html for every other path outside /api/, so deep links work. Unknown
paths under /api/ stay 404 problem documents.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.middleware import Middleware

from app import PRODUCT_NAME, __version__
from app.access import AccessPolicy, AllowAllPolicy
from app.api import v1
from app.api.deps import Services
from app.api.middleware import RequestContextMiddleware
from app.api.problems import EXCEPTION_HANDLERS, problem_media_type
from app.clock import Clock, SystemClock
from app.db.engine import check_database, make_engine
from app.ext.audit import AuditSink, DatabaseAuditSink
from app.security.crypto import SecretBox
from app.security.passwords import PasswordService
from app.security.ratelimit import RateLimiter
from app.settings import Settings, get_settings
from app.web import SinglePageApp
from app.worker.heartbeat import read_heartbeat

# Where the Dockerfile puts the Vite build (frontend/dist).
DEFAULT_STATIC_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"

# Sign-in and first run: 10 attempts a minute per client address.
LOGIN_RATE = (10, 60.0)
# API tokens: 120 requests a minute per token (rnd-report-2 5.7).
TOKEN_RATE = (120, 60.0)

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    static_dir: Path | None = DEFAULT_STATIC_DIR,
    *,
    clock: Clock | None = None,
    policy: AccessPolicy | None = None,
    audit: AuditSink | None = None,
) -> FastAPI:
    """Build the application. The engine connects on first use only.

    clock, policy and audit replace the CE defaults (tests, and EE through the
    extension seams).
    """
    config = settings or get_settings()
    engine = make_engine(config.database_url.get_secret_value())
    clock = clock or SystemClock()
    services = Services(
        settings=config,
        engine=engine,
        sessionmaker=async_sessionmaker(engine, expire_on_commit=False),
        clock=clock,
        policy=policy or AllowAllPolicy(),
        audit=audit or DatabaseAuditSink(),
        passwords=PasswordService(),
        secret_box=SecretBox(config.fernet_key.get_secret_value()),
        login_limiter=RateLimiter(*LOGIN_RATE, clock=clock),
        token_limiter=RateLimiter(*TOKEN_RATE, clock=clock),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await engine.dispose()

    # HSTS only for an https site, so a localhost install never pins HTTPS.
    context = Middleware(
        RequestContextMiddleware, hsts=config.base_url.startswith("https://")
    )
    app = FastAPI(
        title=PRODUCT_NAME,
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        middleware=[context],
        exception_handlers=EXCEPTION_HANDLERS,
    )
    app.state.services = services
    build_openapi = app.openapi

    def openapi() -> dict[str, Any]:
        return problem_media_type(build_openapi())

    app.openapi = openapi  # type: ignore[method-assign]

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
        """Ready when the database answers and the worker heartbeat is younger
        than 3 minutes (ROLE=all runs the worker in this process)."""
        if not await check_database(engine):
            return JSONResponse(
                {"status": "unavailable", "database": "unreachable"},
                status_code=503,
            )
        try:
            heartbeat = await read_heartbeat(
                services.sessionmaker, services.policy, clock.now()
            )
        except Exception as error:  # a missing table or a refusing policy
            logger.warning("heartbeat check failed: %s", type(error).__name__)
            worker = "unknown"
        else:
            worker = "ok"
            if heartbeat.at is None:
                worker = "missing"
            elif heartbeat.stale:
                worker = "stale"
        if worker == "ok":
            return JSONResponse({"status": "ready", "database": "ok", "worker": "ok"})
        return JSONResponse(
            {"status": "unavailable", "database": "ok", "worker": worker},
            status_code=503,
        )

    app.include_router(v1.router)

    # The router's default: it runs only when no route above matched.
    if static_dir is not None and (static_dir / "index.html").is_file():
        app.router.default = SinglePageApp(static_dir, fallback=app.router.default)
    return app
