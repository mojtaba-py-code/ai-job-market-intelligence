"""Tests for the crawler: sources, pipeline, rate limiter, retry, robots."""

from __future__ import annotations

import httpx
import pytest

from jmi.config import Settings
from jmi.crawler.http_client import HttpClient, RateLimiter
from jmi.crawler.pipeline import CrawlPipeline
from jmi.crawler.registry import SourceRegistry
from jmi.crawler.robots import RobotsGate
from jmi.crawler.sources import HtmlDemoSource, SampleJsonSource
from jmi.exceptions import CrawlerError, RobotsDisallowedError


def test_sample_source_fetches_postings():
    postings = list(SampleJsonSource().fetch())
    assert len(postings) >= 5
    first = postings[0]
    assert first.title
    assert first.company
    assert first.salary.currency


def test_sample_source_incremental_since_filter():
    postings = list(SampleJsonSource().fetch(since="2026-07-25"))
    assert all(p.posted_at is None or p.posted_at.isoformat() >= "2026-07-25" for p in postings)
    assert len(postings) < 8


def test_sample_source_limit():
    assert len(list(SampleJsonSource().fetch(limit=2))) == 2


def test_html_source_parses_cards():
    postings = list(HtmlDemoSource().fetch())
    assert len(postings) == 2
    titles = {p.title for p in postings}
    assert "Backend Engineer (Django)" in titles
    assert postings[0].salary.currency == "USD"
    assert postings[0].location.city == "Denver"


def test_pipeline_enriches_and_dedups():
    pipeline = CrawlPipeline()
    result = pipeline.run(SampleJsonSource())
    assert result.fetched == result.unique + result.duplicates
    assert result.unique > 0
    # Enrichment: skills extracted from description.
    a_job = result.postings[0]
    assert a_job.skills, "expected skills to be extracted"


def test_rate_limiter_waits_between_calls():
    slept: list[float] = []
    times = iter([0.0, 0.0, 0.05, 0.05])

    limiter = RateLimiter(0.1, clock=lambda: next(times), sleep=slept.append)
    limiter.wait()  # first call, no wait
    limiter.wait()  # second call, should request a sleep
    assert slept and slept[0] > 0


def test_registry_register_and_create():
    reg = SourceRegistry()
    reg.register(SampleJsonSource)
    assert "sample" in reg.names()
    assert isinstance(reg.create("sample"), SampleJsonSource)
    with pytest.raises(ValueError):
        reg.register(SampleJsonSource)  # duplicate


def test_registry_unknown_source():
    with pytest.raises(KeyError):
        SourceRegistry().create("does-not-exist")


def _client_with_transport(handler, *, respect_robots=False, max_retries=2) -> HttpClient:
    settings = Settings(
        crawler_request_delay_seconds=0.0,
        crawler_max_retries=max_retries,
        crawler_respect_robots=respect_robots,
    )
    transport = httpx.MockTransport(handler)
    inner = httpx.Client(transport=transport)
    gate = RobotsGate(settings.crawler_user_agent, enabled=respect_robots)
    return HttpClient(settings, robots_gate=gate, client=inner)


def test_http_client_retries_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(503)
        return httpx.Response(200, text="ok")

    client = _client_with_transport(handler)
    # patch the backoff sleep to be instant
    client.rate_limiter._sleep = lambda _s: None
    resp = client.get("https://example.com/data")
    assert resp.status_code == 200
    assert calls["n"] == 2


def test_http_client_gives_up_after_retries():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = _client_with_transport(handler, max_retries=1)
    client.rate_limiter._sleep = lambda _s: None
    with pytest.raises(CrawlerError):
        client.get("https://example.com/data")


def test_http_client_user_agent_rotation():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["user-agent"])
        return httpx.Response(200, text="ok")

    client = _client_with_transport(handler)
    client.get("https://example.com/a")
    client.get("https://example.com/b")
    assert len(set(seen)) >= 2  # UA rotated


def test_robots_gate_blocks_disallowed(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private")
        return httpx.Response(200, text="ok")

    settings = Settings(crawler_request_delay_seconds=0.0, crawler_respect_robots=True)
    transport = httpx.MockTransport(handler)

    gate = RobotsGate(settings.crawler_user_agent, enabled=True)
    # Point robots fetch at the mock transport.
    monkeypatch.setattr(
        "jmi.crawler.robots.httpx.get",
        lambda url, **kw: httpx.Client(transport=transport).get(url),
    )
    assert gate.is_allowed("https://example.com/private/x") is False
    assert gate.is_allowed("https://example.com/public/x") is True


def test_http_client_raises_on_disallowed_url(monkeypatch):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    client = _client_with_transport(handler, respect_robots=True)
    monkeypatch.setattr(client.robots, "is_allowed", lambda _url: False)
    with pytest.raises(RobotsDisallowedError):
        client.get("https://example.com/blocked")
