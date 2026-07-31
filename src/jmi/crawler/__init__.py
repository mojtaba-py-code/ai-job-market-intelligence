"""Web scraping framework: polite HTTP client, robots gate, pluggable sources."""

from .base import BaseSource, SourceMetadata
from .http_client import HttpClient, RateLimiter
from .pipeline import CrawlPipeline, CrawlResult
from .registry import SourceRegistry, registry
from .robots import RobotsGate

__all__ = [
    "BaseSource",
    "CrawlPipeline",
    "CrawlResult",
    "HttpClient",
    "RateLimiter",
    "RobotsGate",
    "SourceMetadata",
    "SourceRegistry",
    "registry",
]
