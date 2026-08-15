"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .. import __version__
from ..config import Settings, get_settings
from ..crawler import sources  # noqa: F401  register bundled sources
from ..infrastructure.db.session import create_all
from ..logging import configure_logging, get_logger
from .errors import register_exception_handlers
from .middleware import (
    BodySizeLimitMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
)
from .routers import analytics, auth, crawler, health, jobs, recommendations, search

logger = get_logger(__name__)

_DESCRIPTION = """
AI-Powered Job Market Intelligence Platform API.

Ingests public job postings, extracts skills with NLP, powers semantic search
and resume matching, and serves market analytics — all behind JWT auth,
role-based authorization and rate limiting.
"""

_STATIC_DIR = Path(__file__).with_name("static")
_NONCE_PLACEHOLDER = "__CSP_NONCE__"


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

    # Interactive docs enumerate every endpoint and payload shape, so they are
    # off by default in production (JMI_DOCS_ENABLED re-enables them).
    expose_docs = settings.expose_docs

    app = FastAPI(
        title="JMI Platform API",
        description=_DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if expose_docs else None,
        redoc_url="/redoc" if expose_docs else None,
        openapi_url="/openapi.json" if expose_docs else None,
    )

    # -- Middleware (order matters: outermost first) ------------------------
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_production)
    app.add_middleware(RateLimitMiddleware, settings=settings)
    # Innermost of the three, but still ahead of routing and validation: an
    # oversized body is refused before anything buffers it.
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_body_bytes)
    # `cors_allow_credentials` is validated against a wildcard origin in
    # Settings: the two together would let any site read authenticated responses.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=600,
    )

    # Routes must read the settings this app was built with, not the cached
    # process-wide ones: create_app(settings) would otherwise be silently
    # ignored downstream, and a route deciding what to disclose based on the
    # environment would read the wrong environment.
    app.state.settings = settings

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
    def dashboard(request: Request) -> HTMLResponse:
        """Serve the dashboard with a per-request CSP nonce stamped in.

        The page's inline ``<style>``/``<script>`` carry a ``__CSP_NONCE__``
        placeholder; swapping it for the nonce that
        :class:`SecurityHeadersMiddleware` minted lets the strict
        ``script-src 'nonce-…'`` policy apply without ever falling back to
        ``'unsafe-inline'``.
        """
        nonce = getattr(request.state, "csp_nonce", "")
        index = _STATIC_DIR / "dashboard.html"
        if index.exists():
            html = index.read_text(encoding="utf-8").replace(_NONCE_PLACEHOLDER, nonce)
            return HTMLResponse(html)
        return HTMLResponse("<h1>JMI Platform</h1><p>The API is running.</p>")

    return app


app = create_app()
