# Contributing

Thanks for taking a look. This is how the project is developed locally, what CI
expects before a change lands, and where the non-obvious parts live.

## Setup

```bash
make dev                          # python -m pip install -e ".[dev]"
make hooks                        # pre-commit install
cp .env.example .env              # then set JMI_SECRET_KEY
```

Generate a signing key:

```bash
python -m jmi secret-key
```

Seed a working database and start the API:

```bash
make seed
make run
```

The test suite is hermetic — in-memory SQLite, mocked HTTP transports, no
network — so `make test` works offline and without any `.env` present.

## Before you push

Everything below runs in CI, so run it locally first:

```bash
make lint     # ruff check src tests
make type     # mypy
make cov      # pytest --cov=jmi --cov-report=term-missing
make audit    # bandit + pip-audit
```

`make check` runs all of them. `make format` fixes lint and formatting in place;
CI additionally enforces `ruff format --check src tests` and builds the Docker
image, so run `make format` before pushing and keep the `Dockerfile` working.

CI runs on Python 3.11 and 3.12.

## Conventions

- **Architecture** — keep the layer boundaries. Routers call services, services
  depend on abstractions, only adapters touch an external source. A new job
  source is a new adapter, not a change to the ingestion core. See
  [`docs/architecture.md`](docs/architecture.md).
- **Types** — everything in `src/jmi` is typed; mypy must stay clean.
- **Migrations** — schema changes ship with an Alembic revision in
  `migrations/`; never edit an applied revision.
- **Tests** — add tests with the change; a bug fix needs a test that fails
  without it. External HTTP and model downloads are mocked, never real. Coverage
  should not regress.
- **Docstrings** — explain *why*, not a restatement of the signature.
- **Commits** — short imperative subject, a body explaining the *why*.

## Common tasks

### Adding a job source

1. Subclass `BaseSource` in `src/jmi/crawler/sources/`.
2. Declare `metadata` and implement `fetch()`, yielding `JobPosting` objects.
3. Register it with the `@registry.register` decorator and export it from
   `sources/__init__.py` so it registers on import.
4. Add a test using a recorded fixture — never a live HTTP call.

Always fetch through `self.http` rather than a bare `httpx` call, so robots.txt,
request delays, retries and the response size cap all apply. Only scrape
publicly accessible pages, and respect each site's Terms of Service. Full
walkthrough in [`docs/developer-guide.md`](docs/developer-guide.md).

### Extending the skill taxonomy

Skills live in `src/jmi/nlp/taxonomy.py`, grouped by `SkillKind`. Add the
canonical name plus its aliases, then add an extraction test — aliases are where
regressions hide (`"go"` as a language versus `"go"` as an English word).

## Security-sensitive changes

Some areas need extra care, because a mistake there is silent rather than loud:

- `api/middleware.py` — rate limiting, client identification, security headers
- `infrastructure/security/` — password hashing and token handling
- `config.py` — secret handling and the production boot guards
- `infrastructure/export/` — untrusted data leaving the system

If you touch these, work through the checklist in
[`docs/developer-guide.md`](docs/developer-guide.md#security-checklist) and add a
test to `tests/test_security_hardening.py` phrased as an attack that must fail.

## Docs

[`docs/`](docs) holds the API reference, architecture notes, the ER diagram, the
developer guide and the deployment guide. Update the relevant one in the same PR
as the change.

## Reporting a security problem

Do not open a public issue — see [SECURITY.md](SECURITY.md).

## Code of conduct

Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).
