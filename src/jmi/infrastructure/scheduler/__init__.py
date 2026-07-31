"""Background scheduling.

Uses APScheduler for in-process cron-style scheduling. When the ``jmi[tasks]``
extra (Celery + Redis) is installed, the same job functions can be dispatched to
distributed workers instead — see ``docs/deployment.md``.
"""

from .scheduler import CrawlScheduler, build_scheduler

__all__ = ["CrawlScheduler", "build_scheduler"]
