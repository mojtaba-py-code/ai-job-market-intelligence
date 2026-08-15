"""Custom middleware: security headers and rate limiting.

Two subtleties drive the design here.

**Client identity cannot be taken on trust.** ``X-Forwarded-For`` is a request
header, so a client can send whatever it likes. Keying a rate limiter on it
without knowing a proxy actually rewrote it turns the limiter into a no-op — the
attacker simply varies the header and gets a fresh budget each time. We honour
the header only when the operator states how many proxies sit in front of the
app (``JMI_TRUSTED_PROXY_HOPS``), and then read the hop *that proxy appended*
rather than the leftmost, client-supplied entry.

**The limiter itself must not become the DoS.** A dictionary keyed by client
address grows without bound under a distributed flood, so entries are held in an
LRU capped at ``JMI_RATE_LIMIT_MAX_TRACKED_CLIENTS``.
"""

from __future__ import annotations

import secrets
import time
from collections import OrderedDict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ..config import Settings

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    # Explicitly disabled: the legacy auditor is itself an XSS vector, and CSP
    # is the real defence. See OWASP's guidance on X-XSS-Protection.
    "X-XSS-Protection": "0",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(), interest-cohort=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "X-Permitted-Cross-Domain-Policies": "none",
}

#: Locked-down policy for our own pages: no external anything, scripts and
#: styles only from a per-response nonce, and the page may not be framed.
_CSP_TEMPLATE = (
    "default-src 'none'; "
    "script-src 'nonce-{nonce}'; "
    "style-src 'nonce-{nonce}'; "
    "connect-src 'self'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "base-uri 'none'; "
    "form-action 'none'; "
    "frame-ancestors 'none'; "
    "object-src 'none'"
)

#: Swagger UI / ReDoc are third-party bundles served from a CDN with inline
#: bootstrap code, so they get their own narrowly-scoped policy instead of the
#: strict one above.
_DOCS_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://fastapi.tiangolo.com https://cdn.jsdelivr.net; "
    "worker-src 'self' blob:; "
    "frame-ancestors 'none'; "
    "base-uri 'none'; "
    "object-src 'none'"
)

_DOCS_PATHS = frozenset({"/docs", "/redoc", "/docs/oauth2-redirect"})

#: API responses can carry job data, analytics and exports tied to the caller's
#: token. Shared caches and browser back/forward stores must not retain them.
_NO_STORE = "no-store, no-cache, must-revalidate, private"

#: Endpoints that accept credentials and therefore get the tighter budget.
_AUTH_PATHS = frozenset(
    {
        "/api/v1/auth/login",
        "/api/v1/auth/token",
        "/api/v1/auth/register",
    }
)

#: Never rate limited — the platform's own liveness probe.
_EXEMPT_PATHS = frozenset({"/health"})


def client_ip(request: Request, *, trusted_proxy_hops: int = 0) -> str:
    """Return the caller's address, honouring proxies only when configured.

    Args:
        request: the incoming request.
        trusted_proxy_hops: how many reverse proxies are known to sit in front
            of this app. ``0`` (the default) means ``X-Forwarded-For`` is
            ignored entirely, because nothing is guaranteed to have sanitised it.

    Returns:
        The client address, or ``"anonymous"`` when it cannot be determined.
    """
    peer = request.client.host if request.client else "anonymous"
    if trusted_proxy_hops <= 0:
        return peer

    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        return peer

    hops = [part.strip() for part in forwarded.split(",") if part.strip()]
    if not hops:
        return peer

    # The rightmost entry was written by the proxy nearest to us. Stepping
    # `trusted_proxy_hops` in from the right lands on the address that the
    # outermost *trusted* proxy observed; anything further left is client-supplied
    # and forgeable. If the chain is shorter than advertised, the client did not
    # traverse the full set of proxies, so fall back to the peer address.
    if len(hops) < trusted_proxy_hops:
        return peer
    return hops[-trusted_proxy_hops]


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach a conservative set of security headers to every response.

    A fresh CSP nonce is minted per request and published on ``request.state``
    so HTML routes can stamp it onto their inline ``<script>``/``<style>`` tags.
    """

    def __init__(self, app, *, hsts: bool = False) -> None:
        super().__init__(app)
        self._hsts = hsts

    async def dispatch(self, request: Request, call_next) -> Response:
        nonce = secrets.token_urlsafe(16)
        request.state.csp_nonce = nonce

        response = await call_next(request)

        for header, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)

        # The server banner names the software and version running here, which
        # is free reconnaissance for matching a public CVE to this host.
        response.headers["Server"] = "jmi"

        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", _NO_STORE)
            response.headers.setdefault("Pragma", "no-cache")

        if request.url.path in _DOCS_PATHS:
            response.headers.setdefault("Content-Security-Policy", _DOCS_CSP)
        else:
            response.headers.setdefault(
                "Content-Security-Policy", _CSP_TEMPLATE.format(nonce=nonce)
            )

        if self._hsts:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
            )
        return response


class BodySizeLimitMiddleware:
    """Reject request bodies larger than *max_bytes*.

    Pydantic caps individual fields, but that check runs only *after* the whole
    body has been received and buffered — so a 2 GB POST to a field capped at
    50 KB is still 2 GB of memory spent before anything rejects it.

    Implemented as raw ASGI rather than ``BaseHTTPMiddleware`` so it can wrap the
    receive channel and count bytes as they arrive. A declared ``Content-Length``
    is rejected up front; a chunked body with no declared length is cut off the
    moment the running total crosses the limit, instead of being trusted.
    """

    def __init__(self, app, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    @staticmethod
    async def _reject(scope, receive, send) -> None:
        response = JSONResponse(
            status_code=413,
            content={"error": "payload_too_large", "detail": "Request body is too large."},
        )
        await response(scope, receive, send)

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        declared = headers.get("content-length")
        if declared is not None:
            try:
                if int(declared) > self.max_bytes:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                # A malformed Content-Length is not something to guess about.
                await self._reject(scope, receive, send)
                return

        received = 0
        too_large = False

        async def counting_receive():
            nonlocal received, too_large
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    too_large = True
                    # Stop the stream so the app sees a truncated body and
                    # returns rather than waiting for a sender that will not stop.
                    return {"type": "http.disconnect"}
            return message

        await self.app(scope, counting_receive, send)


class _SlidingWindow:
    """Per-client sliding-window counters with an LRU bound on memory."""

    def __init__(self, *, limit: int, window: int, max_clients: int) -> None:
        self.limit = limit
        self.window = window
        self._max_clients = max_clients
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()

    def check(self, key: str, now: float) -> tuple[bool, int, int]:
        """Record a hit for *key*.

        Returns:
            ``(allowed, remaining, retry_after_seconds)``.
        """
        hits = self._hits.get(key)
        if hits is None:
            hits = deque()
            self._hits[key] = hits
        self._hits.move_to_end(key)

        window_start = now - self.window
        while hits and hits[0] < window_start:
            hits.popleft()

        if len(hits) >= self.limit:
            retry_after = max(1, int(hits[0] + self.window - now) + 1)
            return False, 0, retry_after

        hits.append(now)

        # Evict the least-recently-seen clients once the table is full. Their
        # counters reset, which is the correct trade-off: bounded memory beats
        # perfect accounting for clients we have not heard from in a while.
        while len(self._hits) > self._max_clients:
            self._hits.popitem(last=False)

        return True, max(0, self.limit - len(hits)), 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window in-memory rate limiter keyed by client address.

    Credential-accepting endpoints (`/auth/login`, `/auth/token`, `/auth/register`)
    are metered against a second, much smaller budget so the generous global
    limit cannot double as a password-guessing allowance.

    Suitable for single-instance deployments and development. For multi-instance
    production use, back this with Redis (the ``jmi[tasks]`` extra ships redis).
    """

    def __init__(self, app, *, settings: Settings) -> None:
        super().__init__(app)
        self._trusted_proxy_hops = settings.trusted_proxy_hops
        self._general = _SlidingWindow(
            limit=settings.rate_limit_requests,
            window=settings.rate_limit_window_seconds,
            max_clients=settings.rate_limit_max_tracked_clients,
        )
        self._auth = _SlidingWindow(
            limit=settings.auth_rate_limit_requests,
            window=settings.auth_rate_limit_window_seconds,
            max_clients=settings.rate_limit_max_tracked_clients,
        )

    @staticmethod
    def _too_many(retry_after: int) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={"error": "rate_limited", "detail": "Too many requests."},
            headers={"Retry-After": str(retry_after)},
        )

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if path in _EXEMPT_PATHS:
            return await call_next(request)

        key = client_ip(request, trusted_proxy_hops=self._trusted_proxy_hops)
        now = time.monotonic()

        if path in _AUTH_PATHS:
            allowed, _, retry_after = self._auth.check(key, now)
            if not allowed:
                return self._too_many(retry_after)

        allowed, remaining, retry_after = self._general.check(key, now)
        if not allowed:
            return self._too_many(retry_after)

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self._general.limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
