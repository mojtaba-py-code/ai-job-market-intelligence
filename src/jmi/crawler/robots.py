"""robots.txt compliance gate.

Every outbound crawl request is checked against the target host's robots.txt.
Results are cached per host for the process lifetime. Fetch failures fail
**open** for the standard ``*`` agent only when the file is genuinely absent
(HTTP 404); network errors fail **closed** to stay on the safe side.
"""

from __future__ import annotations

from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from ..logging import get_logger

logger = get_logger(__name__)


class RobotsGate:
    """Caches robots.txt parsers per host and answers allow/deny queries."""

    def __init__(self, user_agent: str, *, enabled: bool = True) -> None:
        self.user_agent = user_agent
        self.enabled = enabled
        self._cache: dict[str, RobotFileParser | None] = {}

    def _robots_url(self, url: str) -> tuple[str, str]:
        parts = urlsplit(url)
        host = f"{parts.scheme}://{parts.netloc}"
        return host, f"{host}/robots.txt"

    def _load(self, host: str, robots_url: str) -> RobotFileParser | None:
        try:
            response = httpx.get(
                robots_url,
                timeout=10.0,
                headers={"User-Agent": self.user_agent},
                follow_redirects=True,
            )
        except httpx.HTTPError as exc:  # network problem -> fail closed
            logger.warning("robots_fetch_failed", host=host, error=str(exc))
            return None

        if response.status_code == 404:
            # No robots.txt means everything is allowed.
            parser = RobotFileParser()
            parser.parse([])
            return parser
        if response.status_code >= 400:
            logger.warning("robots_unavailable", host=host, status=response.status_code)
            return None

        parser = RobotFileParser()
        parser.parse(response.text.splitlines())
        return parser

    def is_allowed(self, url: str) -> bool:
        """Return whether *url* may be fetched under the configured user agent."""
        if not self.enabled:
            return True

        host, robots_url = self._robots_url(url)
        if host not in self._cache:
            self._cache[host] = self._load(host, robots_url)

        parser = self._cache[host]
        if parser is None:
            # Could not obtain robots.txt due to an error -> be conservative.
            return False
        return parser.can_fetch(self.user_agent, url)
