"""Packaging guards: an extra must pull its weight.

An optional-dependency extra that installs a package nothing in the codebase
uses is a trap — the reader pays the download and no behaviour changes.

The check deliberately looks at **imports**, parsed from the AST, rather than
searching the source text. A textual search is satisfied by a docstring that
merely mentions the package, which is precisely the failure being guarded
against: this repository once declared an ``nlp`` extra whose only trace was
prose describing a spaCy backend that did not exist.
"""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Extras aimed at contributors, not users. Their packages are invoked as
# executables (ruff, mypy, pre-commit) rather than imported.
TOOLING_EXTRAS = {"dev"}

# Packages that are genuinely required but never imported by name, because the
# library that needs them resolves them from a URL scheme at runtime. Each
# entry must name the scheme, and `test_url_scheme_drivers_are_really_used`
# checks that the scheme is actually configured — so this cannot quietly become
# a place to park dead dependencies.
URL_SCHEME_DRIVERS = {
    "psycopg": "postgresql+psycopg://",  # SQLAlchemy picks the DBAPI by name
    "redis": "redis://",  # Celery's broker/result transport
}

IMPORT_ROOTS = (PROJECT_ROOT / "src", PROJECT_ROOT / "migrations")
CONFIG_FILES = (PROJECT_ROOT / ".env.example", PROJECT_ROOT / "src" / "jmi" / "config.py")


def _distribution_name(requirement: str) -> str:
    """``psycopg[binary]>=3.1`` -> ``psycopg``."""
    return re.split(r"[<>=!~\[;\s]", requirement, maxsplit=1)[0].strip()


def _import_name(distribution: str) -> str:
    """``sentence-transformers`` -> ``sentence_transformers``."""
    return distribution.replace("-", "_")


def _optional_dependencies() -> dict[str, list[str]]:
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text("utf-8"))
    extras = pyproject["project"]["optional-dependencies"]
    return {name: reqs for name, reqs in extras.items() if name not in TOOLING_EXTRAS}


def _imported_top_level_modules() -> set[str]:
    """Every top-level module imported anywhere in the shipped source."""
    imported: set[str] = set()
    for root in IMPORT_ROOTS:
        for source in root.rglob("*.py"):
            tree = ast.parse(source.read_text("utf-8"), filename=str(source))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    imported.add(node.module.split(".")[0])
    return imported


def _extra_package_pairs() -> list[tuple[str, str]]:
    return [
        (extra, _distribution_name(req))
        for extra, reqs in _optional_dependencies().items()
        for req in reqs
    ]


@pytest.mark.parametrize(("extra", "package"), _extra_package_pairs(), ids=lambda v: str(v))
def test_declared_extra_is_actually_used(extra: str, package: str) -> None:
    """Every package in every user-facing extra is imported, or a named driver."""
    if package in URL_SCHEME_DRIVERS:
        pytest.skip(f"{package} is resolved from a URL scheme; see the driver test")
    assert _import_name(package) in _imported_top_level_modules(), (
        f"pyproject declares `{package}` under the `{extra}` extra, but nothing "
        f"under src/ or migrations/ imports it. Either use it, add it to "
        f"URL_SCHEME_DRIVERS with the scheme that pulls it in, or drop it — "
        f"installing it costs the reader bandwidth and buys nothing. A mention "
        f"in a docstring does not count."
    )


@pytest.mark.parametrize("package", sorted(URL_SCHEME_DRIVERS), ids=lambda v: str(v))
def test_url_scheme_drivers_are_really_used(package: str) -> None:
    """A driver excused from the import check must still be configured somewhere."""
    scheme = URL_SCHEME_DRIVERS[package]
    declared = {_distribution_name(req) for _, req in _extra_package_pairs() for req in [req]}
    assert package in declared, f"URL_SCHEME_DRIVERS lists `{package}`, which no extra installs"
    haystack = "\n".join(
        path.read_text("utf-8", errors="ignore") for path in CONFIG_FILES if path.is_file()
    )
    assert scheme in haystack, (
        f"`{package}` is excused from the import check because {scheme} is "
        f"supposed to select it, but that scheme appears in none of "
        f"{[p.name for p in CONFIG_FILES]}."
    )


def test_prose_only_names_extras_that_exist() -> None:
    """No docstring or guide may point the reader at an extra that was removed."""
    declared = set(_optional_dependencies()) | TOOLING_EXTRAS
    sources = [*(PROJECT_ROOT / "docs").rglob("*.md"), *(PROJECT_ROOT / "src").rglob("*.py")]
    offenders: dict[str, list[str]] = {}
    for path in sources:
        text = path.read_text("utf-8", errors="ignore")
        named = set(re.findall(r"jmi\[([a-z][a-z0-9_-]*)\]", text))
        named |= set(re.findall(r"`([a-z][a-z0-9_-]*)` extra", text))
        for name in sorted(named - declared):
            offenders.setdefault(name, []).append(str(path.relative_to(PROJECT_ROOT)))
    assert not offenders, f"prose names extras that pyproject does not define: {offenders}"
