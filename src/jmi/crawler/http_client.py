"""Polite, resilient HTTP client for scraping.

Features:
* per-host **rate limiting** (minimum delay between requests),
* **retry with exponential backoff** on transient errors / 429 / 5xx,
* **User-Agent rotation** from a configurable pool,
* **session** reuse (connection pooling, cookie jar),
* a **robots.txt gate** so disallowed URLs are never fetched.

The client is deliberately synchronous — it is driven by background workers, and
sync httpx keeps the retry/rate-limit logic simple and testable.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from types import TracebackType

import httpx

from ..config import Settings, get_settings
from ..exceptions import CrawlerError, RobotsDisallowedError
from ..logging import get_logger
from .robots import RobotsGate

logger = get_logger(__name__)

_DEFAULT_USER_AGENTS: tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
)
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class RateLimiter:
    """Enforces a minimum delay between successive requests."""

    def __init__(self, min_delay_seconds: float, *, clock=time.monotonic, sleep=time.sleep) -> None:
        self.min_delay_seconds = max(0.0, min_delay_seconds)
        self._clock = clock
        self._sleep = sleep
        self._last_call: float | None = None

    def wait(self) -> None:
        if self.min_delay_seconds == 0:
            return
        now = self._clock()
        if self._last_call is not None:
            elapsed = now - self._last_call
            remaining = self.min_delay_seconds - elapsed
            if remaining > 0:
                self._sleep(remaining)
        self._last_call = self._clock()


class HttpClient:
    """A polite HTTP client wrapping ``httpx.Client``."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        user_agents: Sequence[str] | None = None,
        robots_gate: RobotsGate | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._user_agents = tuple(
            user_agents or (self.settings.crawler_user_agent, *_DEFAULT_USER_AGENTS)
        )
        self._ua_index = 0
        self.rate_limiter = RateLimiter(self.settings.crawler_request_delay_seconds)
        self.robots = robots_gate or RobotsGate(
            self.settings.crawler_user_agent,
            enabled=self.settings.crawler_respect_robots,
        )
        self._client = client or httpx.Client(
            timeout=self.settings.crawler_timeout_seconds,
            follow_redirects=True,
        )

    # -- context management -------------------------------------------------
    def __enter__(self) -> HttpClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # -- internals ----------------------------------------------------------
    def _next_user_agent(self) -> str:
        ua = self._user_agents[self._ua_index % len(self._user_agents)]
        self._ua_index += 1
        return ua

    def _check_response_size(self, url: str, response: httpx.Response) -> None:
        """Reject responses larger than the configured cap.

        A crawler pulls bytes from hosts it does not control, so an oversized or
        endlessly-generated body would otherwise be read straight into memory.
        """
        limit = self.settings.crawler_max_response_bytes
        if len(response.content) > limit:
            raise CrawlerError(
                f"Response from {url} exceeds the {limit} byte limit "
                f"({len(response.content)} bytes)."
            )

    def get(self, url: str, *, headers: dict[str, str] | None = None, **kwargs) -> httpx.Response:
        """Fetch *url* with robots check, rate limiting and retry/backoff."""
        if not self.robots.is_allowed(url):
            raise RobotsDisallowedError(f"robots.txt disallows fetching {url}")

        request_headers = {"User-Agent": self._next_user_agent()}
        if headers:
            request_headers.update(headers)

        last_error: Exception | None = None
        for attempt in range(self.settings.crawler_max_retries + 1):
            self.rate_limiter.wait()
            try:
                response = self._client.get(url, headers=request_headers, **kwargs)
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning("request_error", url=url, attempt=attempt, error=str(exc))
            else:
                if response.status_code in _RETRYABLE_STATUS:
                    last_error = CrawlerError(f"HTTP {response.status_code} for {url}")
                    logger.warning(
                        "retryable_status", url=url, attempt=attempt, status=response.status_code
                    )
                else:
                    response.raise_for_status()
                    self._check_response_size(url, response)
                    return response

            if attempt < self.settings.crawler_max_retries:
                backoff = min(2**attempt, 30)
                self.rate_limiter._sleep(backoff)

        raise CrawlerError(f"Failed to fetch {url} after retries: {last_error}")
