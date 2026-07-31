"""Concrete job source integrations.

Importing this package registers the bundled sources with the global registry.
Add new portals by creating a module here that subclasses
:class:`~jmi.crawler.base.BaseSource` and decorating it with ``@registry.register``.
"""

from .html_demo_source import HtmlDemoSource
from .sample_source import SampleJsonSource

__all__ = ["HtmlDemoSource", "SampleJsonSource"]
