# Developer Guide

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
python -m jmi seed
```

## Everyday commands

```bash
make lint      # ruff check
make format    # ruff --fix + ruff format
make type      # mypy
make test      # pytest
make cov       # pytest with coverage
make run       # uvicorn with reload
```

## Adding a new job source

1. Create `src/jmi/crawler/sources/<name>_source.py`.
2. Subclass `BaseSource`, declare `metadata`, implement `fetch()`:

```python
from collections.abc import Iterator
from datetime import datetime, timezone

from ...domain.entities import JobPosting, Location, SalaryRange
from ...domain.enums import RemoteStatus
from ..base import BaseSource, SourceMetadata
from ..registry import registry


@registry.register
class AcmeBoardSource(BaseSource):
    metadata = SourceMetadata(
        name="acme",
        display_name="Acme Job Board",
        base_url="https://boards.acme.example",
        supports_incremental=True,
    )

    def fetch(self, *, since=None, limit=None) -> Iterator[JobPosting]:
        # self.http is a polite HttpClient: retry + rate-limit + robots gate.
        resp = self.http.get(f"{self.metadata.base_url}/api/jobs")
        for record in resp.json()["results"]:
            yield JobPosting(
                source=self.name,
                external_id=str(record["id"]),
                title=record["title"],
                company=record["company"],
                description=record.get("description", ""),
                remote_status=RemoteStatus.remote if record["remote"] else RemoteStatus.on_site,
                location=Location(country=record.get("country"), city=record.get("city")),
                salary=SalaryRange(min_amount=record.get("min"), max_amount=record.get("max")),
                scraped_at=datetime.now(timezone.utc),
            )
```

3. Export it from `src/jmi/crawler/sources/__init__.py` so it registers on import.
4. It is now available via `POST /api/v1/crawler/ingest {"source": "acme"}` and
   `python -m jmi ingest acme`. Skill extraction, dedup and persistence are
   handled by the pipeline — you only map fields.

**Etiquette:** always fetch through `self.http` (never a bare `httpx` call) so
robots.txt, rate limiting and retries apply. Only scrape publicly accessible
pages and respect each site's Terms of Service.

## Extending the skill taxonomy

The taxonomy lives in `src/jmi/nlp/taxonomy.py`. Add entries inline, or provide
an external override JSON and load it:

```json
{ "Svelte": { "kind": "framework", "aliases": ["svelte", "sveltekit"] } }
```

```python
from jmi.nlp.taxonomy import load_taxonomy
from jmi.nlp.skills import SkillExtractor

extractor = SkillExtractor(load_taxonomy("my_taxonomy.json"))
```

`kind` is one of: `language`, `framework`, `database`, `cloud`, `tool`,
`concept`, `soft` — these drive the analytics rollups.

## Testing conventions

- Tests are hermetic: in-memory SQLite (`conftest.py`), mocked HTTP transports.
- Prefer testing services/repositories over mocking internals.
- API tests use `TestClient` with a `get_db` dependency override.
- Keep new code covered; run `make cov` and check `--cov-report=term-missing`.

## Security checklist

When touching auth, crawling or I/O, verify:

- [ ] New secrets are typed `SecretStr` on `Settings`, never plain `str` — a
      plain string leaks through `repr()`, tracebacks and `model_dump()`.
- [ ] No secret has a production-usable default; unsafe production values are
      rejected in `Settings._enforce_production_hardening`.
- [ ] New endpoints declare the right `require_role(...)` guard.
- [ ] User input is a Pydantic schema (validated, length-bounded).
- [ ] DB access goes through the ORM/repository (no string-built SQL), and any
      new `LIKE` pattern escapes user input with `_escape_like`.
- [ ] Outbound scraping uses `self.http` (robots + rate limit + retry + size cap).
- [ ] Nothing sensitive is logged (the redaction processor covers common keys —
      extend `_SENSITIVE_KEYS` if you add new ones).
- [ ] Errors raise a `JMIError` subclass so responses stay consistent and safe.
- [ ] Anything identifying a caller comes from `client_ip(...)`, never straight
      from a request header.
- [ ] Untrusted text reaching a new export format is escaped like
      `escape_formula` does for CSV/Excel.
- [ ] New dashboard markup uses no inline `style=""` attributes — a CSP nonce
      cannot authorise them, so the browser silently drops them. Set dynamic
      styles through the CSSOM (`el.style.width = ...`).
- [ ] A regression test lands in `tests/test_security_hardening.py`, phrased as
      an attack that must fail.

The full threat model, including what is deliberately out of scope, lives in
[SECURITY.md](../SECURITY.md).
