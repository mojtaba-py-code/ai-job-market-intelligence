"""Per-account login throttling.

The rate limiter in the API layer meters by client address. That stops one host
from grinding through a password list, but not a distributed attempt: guesses
spread across many addresses each stay under the per-address budget while the
*account* still receives thousands of them.

This throttle closes that gap by counting recent failures per account. It is
deliberately keyed on the **submitted** identifier rather than a resolved user
row, so an unknown address is throttled exactly like a real one and the endpoint
does not become a account-existence oracle.

**Known trade-off.** Any per-account lockout lets someone deliberately lock a
user out by failing logins on their behalf. The defaults are chosen to make that
a nuisance rather than an outage — a 15-minute window that lapses on its own,
with no administrator action needed — and the counter is cleared the moment a
correct password arrives, so the real owner is never locked out of a session
they can actually authenticate. Sites needing stronger guarantees should pair
this with a second factor rather than a longer lockout.

State is per process and in memory: it is a speed bump that resets on restart,
not an audit trail. A shared store belongs behind the same interface for a
multi-instance deployment.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque

from ...config import Settings, get_settings


class LoginThrottle:
    """Counts recent failed logins per account, with an LRU memory bound."""

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        self._max_failures = settings.login_max_failures
        self._window = settings.login_failure_window_seconds
        self._max_accounts = settings.login_max_tracked_accounts
        self._failures: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def _key(identifier: str) -> str:
        return identifier.strip().lower()

    def _recent(self, key: str, now: float) -> deque[float]:
        failures = self._failures.get(key)
        if failures is None:
            failures = deque()
            self._failures[key] = failures
        self._failures.move_to_end(key)
        cutoff = now - self._window
        while failures and failures[0] < cutoff:
            failures.popleft()
        return failures

    def is_locked(self, identifier: str, *, now: float | None = None) -> bool:
        """Whether *identifier* has exhausted its recent-failure budget."""
        now = time.monotonic() if now is None else now
        with self._lock:
            return len(self._recent(self._key(identifier), now)) >= self._max_failures

    def retry_after(self, identifier: str, *, now: float | None = None) -> int:
        """Seconds until the oldest recorded failure ages out of the window."""
        now = time.monotonic() if now is None else now
        with self._lock:
            failures = self._recent(self._key(identifier), now)
            if not failures:
                return 0
            return max(1, int(failures[0] + self._window - now) + 1)

    def record_failure(self, identifier: str, *, now: float | None = None) -> None:
        """Note a failed attempt against *identifier*."""
        now = time.monotonic() if now is None else now
        with self._lock:
            self._recent(self._key(identifier), now).append(now)
            while len(self._failures) > self._max_accounts:
                self._failures.popitem(last=False)

    def record_success(self, identifier: str) -> None:
        """Clear the history for *identifier* after a correct password."""
        with self._lock:
            self._failures.pop(self._key(identifier), None)

    def reset(self) -> None:
        """Forget every recorded failure (used by tests)."""
        with self._lock:
            self._failures.clear()


#: Shared across requests, since per-request state would count nothing.
_throttle: LoginThrottle | None = None
_throttle_lock = threading.Lock()


def get_login_throttle() -> LoginThrottle:
    """Return the process-wide login throttle, creating it on first use."""
    global _throttle

    with _throttle_lock:
        if _throttle is None:
            _throttle = LoginThrottle()
        return _throttle


def reset_login_throttle() -> None:
    """Drop the shared throttle so the next call rebuilds it from settings."""
    global _throttle

    with _throttle_lock:
        _throttle = None
