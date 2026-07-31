"""Domain-wide exception hierarchy.

Keeping a single, typed hierarchy lets the API layer translate errors into
consistent HTTP responses without leaking internal details.
"""

from __future__ import annotations


class JMIError(Exception):
    """Base class for all application errors."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.__class__.__name__)
        self.message = message or self.__class__.__name__


class ConfigurationError(JMIError):
    code = "configuration_error"


class ValidationError(JMIError):
    status_code = 422
    code = "validation_error"


class NotFoundError(JMIError):
    status_code = 404
    code = "not_found"


class ConflictError(JMIError):
    status_code = 409
    code = "conflict"


class AuthenticationError(JMIError):
    status_code = 401
    code = "authentication_error"


class AuthorizationError(JMIError):
    status_code = 403
    code = "authorization_error"


class RateLimitedError(JMIError):
    status_code = 429
    code = "rate_limited"


class CrawlerError(JMIError):
    code = "crawler_error"


class RobotsDisallowedError(CrawlerError):
    """Raised when robots.txt forbids fetching a URL."""

    code = "robots_disallowed"
