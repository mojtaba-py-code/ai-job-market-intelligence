"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .. import __version__
from ..config import Settings, get_settings
from ..crawler import sources  # noqa: F401  register bundled sources
from ..infrastructure.db.session import create_all
from ..logging import configure_logging, get_logger
from .errors import register_exception_handlers
from .middleware import RateLimitMiddleware, SecurityHeadersMiddleware
from .routers import analytics, auth, crawler, health, jobs, recommendations, search

logger = get_logger(__name__)

_DESCRIPTION = """
AI-Powered Job Market Intelligence Platform API.

Ingests public job postings, extracts skills with NLP, powers semantic search
and resume matching, and serves market analytics — all behind JWT auth,
role-based authorization and rate limiting.
"""

_STATIC_DIR = Path(__file__).with_name("static")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = settings or get_settings()
    configure_logging(debug=settings.debug, json_logs=settings.is_production)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Auto-create tables for the SQLite quick-start; production uses Alembic.
        if settings.is_sqlite:
            create_all()
        logger.info("api_startup", env=settings.env.value, version=__version__)
        yield
        logger.info("api_shutdown")

    app = FastAPI(
        title="JMI Platform API",
        description=_DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # -- Middleware (order matters: outermost first) ------------------------
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_production)
    app.add_middleware(RateLimitMiddleware, settings=settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    # -- Routers ------------------------------------------------------------
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(jobs.router)
    app.include_router(search.router)
    app.include_router(analytics.router)
    app.include_router(recommendations.router)
    app.include_router(crawler.router)

    # -- Dashboard (served as a self-contained static page) -----------------
    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def dashboard() -> HTMLResponse:
        index = _STATIC_DIR / "dashboard.html"
        if index.exists():
            return HTMLResponse(index.read_text(encoding="utf-8"))
        return HTMLResponse("<h1>JMI Platform</h1><p>See <a href='/docs'>/docs</a>.</p>")

    return app


app = create_app()
