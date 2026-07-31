"""Source registry — a small plugin system for job portals."""

from __future__ import annotations

from .base import BaseSource


class SourceRegistry:
    """Registry mapping source names to :class:`BaseSource` subclasses."""

    def __init__(self) -> None:
        self._sources: dict[str, type[BaseSource]] = {}

    def register(self, source_cls: type[BaseSource]) -> type[BaseSource]:
        """Register a source class. Usable as a decorator."""
        name = source_cls.metadata.name
        if name in self._sources:
            raise ValueError(f"Source '{name}' is already registered.")
        self._sources[name] = source_cls
        return source_cls

    def create(self, name: str, **kwargs) -> BaseSource:
        try:
            source_cls = self._sources[name]
        except KeyError as exc:
            raise KeyError(f"Unknown source '{name}'. Available: {self.names()}") from exc
        return source_cls(**kwargs)

    def names(self) -> list[str]:
        return sorted(self._sources)

    def all_metadata(self) -> list:
        return [cls.metadata for cls in self._sources.values()]


registry = SourceRegistry()
