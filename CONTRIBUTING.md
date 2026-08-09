# Contributing

Thanks for taking a look. This is how the project is developed locally and what
CI expects before a change lands.

## Setup

```bash
make dev                          # python -m pip install -e ".[dev]"
cp .env.example .env              # then set JMI_SECRET_KEY
```

Generate a signing key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Seed a working database and start the API:

```bash
make seed
make run
```

## Before you push

Everything below runs in CI, so run it locally first:

```bash
make lint     # ruff check src tests
make type     # mypy
make cov      # pytest --cov=jmi --cov-report=term-missing
```

`make format` fixes lint and formatting in place. CI additionally enforces
`ruff format --check src tests` and builds the Docker image, so run
`make format` before pushing and keep the `Dockerfile` working.

CI runs on Python 3.11 and 3.12.

## Conventions

- **Architecture** — keep the layer boundaries. Routers call services, services
  depend on abstractions, only adapters touch an external source. A new job
  source is a new adapter, not a change to the ingestion core. See
  [`docs/architecture.md`](docs/architecture.md).
- **Types** — everything in `src/jmi` is typed; mypy must stay clean.
- **Migrations** — schema changes ship with an Alembic revision in
  `migrations/`; never edit an applied revision.
- **Tests** — add tests with the change; external HTTP and model downloads are
  mocked, never real.
- **Commits** — short imperative subject, a body explaining the *why*.

## Docs

[`docs/`](docs) holds the API reference, architecture notes, the ER diagram, the
developer guide and the deployment guide. Update the relevant one in the same PR
as the change.

## Reporting a security problem

Do not open a public issue — see [SECURITY.md](SECURITY.md).
