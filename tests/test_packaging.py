"""Packaging guards: an extra must pull its weight.

An optional-dependency extra that installs a package nothing in the codebase
references is a trap — the user pays the download (spaCy and FAISS run to
hundreds of megabytes) and no behaviour changes. This module walks
``[project.optional-dependencies]`` in ``pyproject.toml`` and fails when a
declared package is never referenced by the code, the migrations, or the
sample environment file.

Documentation is deliberately *not* searched: a package that only ever appears
in prose is exactly the failure this guard exists to catch.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Extras aimed at contributors rather than users; their packages are invoked as
# tools (ruff, mypy, pre-commit) rather than imported, so the guard skips them.
TOOLING_EXTRAS = {"dev"}

# A package can be referenced without an ``import``: SQLAlchemy and Alembic
# select their drivers by name inside a connection URL.
SEARCH_PATHS = (
    PROJECT_ROOT / "src",
    PROJECT_ROOT / "migrations",
    PROJECT_ROOT / ".env.example",
)


def _distribution_name(requirement: str) -> str:
    """``psycopg[binary]>=3.1`` -> ``psycopg``."""
    return re.split(r"[<>=!~\[;\s]", requirement, maxsplit=1)[0].strip()


def _optional_dependencies() -> dict[str, list[str]]:
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text("utf-8"))
    extras = pyproject["project"]["optional-dependencies"]
    return {name: reqs for name, reqs in extras.items() if name not in TOOLING_EXTRAS}


def _searchable_text() -> str:
    chunks: list[str] = []
    for path in SEARCH_PATHS:
        if path.is_file():
            chunks.append(path.read_text("utf-8", errors="ignore"))
        elif path.is_dir():
            for source in path.rglob("*.py"):
                chunks.append(source.read_text("utf-8", errors="ignore"))
    return "\n".join(chunks)


def _cases() -> list[tuple[str, str]]:
    return [
        (extra, _distribution_name(req))
        for extra, reqs in _optional_dependencies().items()
        for req in reqs
    ]


@pytest.mark.parametrize(("extra", "package"), _cases(), ids=lambda v: str(v))
def test_declared_extra_is_actually_used(extra: str, package: str) -> None:
    """Every package in every user-facing extra is referenced by the code."""
    haystack = _searchable_text()
    # ``sentence-transformers`` is imported as ``sentence_transformers``.
    candidates = {package, package.replace("-", "_")}
    assert any(name in haystack for name in candidates), (
        f"pyproject declares `{package}` under the `{extra}` extra, but no file "
        f"under src/, migrations/ or .env.example references it. Either use it "
        f"or drop it — installing it costs the user bandwidth and buys nothing."
    )


def test_extras_are_documented_honestly() -> None:
    """The deployment guide must not promise an extra that no longer exists."""
    declared = set(_optional_dependencies()) | TOOLING_EXTRAS
    guide = (PROJECT_ROOT / "docs" / "deployment.md").read_text("utf-8")
    promised = set(re.findall(r"`([a-z][a-z0-9_-]*)` extra", guide))
    assert promised <= declared, (
        f"docs/deployment.md points the reader at extras that pyproject does "
        f"not define: {sorted(promised - declared)}"
    )
