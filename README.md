# AI-Powered Job Market Intelligence Platform

[![CI](https://github.com/mojtaba-py-code/ai-job-market-intelligence/actions/workflows/ci.yml/badge.svg)](https://github.com/mojtaba-py-code/ai-job-market-intelligence/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-async-009688.svg)](https://fastapi.tiangolo.com)
[![Code style: ruff](https://img.shields.io/badge/lint-ruff-black.svg)](https://github.com/astral-sh/ruff)
[![Types: mypy](https://img.shields.io/badge/types-mypy-blue.svg)](https://mypy-lang.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A production-grade platform that ingests publicly available job postings from
multiple sources, normalises and de-duplicates them, extracts skills and
technologies with an NLP pipeline, powers **semantic search** and **resume
matching**, and serves **market analytics** through a secured FastAPI backend
and a live dashboard.

Built with Clean Architecture, the repository pattern, strict typing and a
security-first mindset (JWT auth, role-based authorization, rate limiting,
secret hygiene, robots.txt-respecting crawling).

---

## Live demo

**One-click deploy** — no Postgres, Redis or ML wheels needed: search falls back
to the built-in pure-Python TF-IDF backend, the database is SQLite, and `jmi
seed` loads bundled offline demo postings so the dashboard, search and analytics
all have data on first load.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/mojtaba-py-code/ai-job-market-intelligence)

Once it is up, explore:

- **`/`** — a self-contained analytics dashboard: total jobs, remote %, most
  in-demand skills, languages/frameworks/databases/clouds, salary by currency,
  and top hiring companies/countries.
- **`/docs`** — interactive OpenAPI (Swagger UI); `/redoc` for ReDoc.
- **`POST /api/v1/search/semantic`** — natural-language search, e.g.
  `{"query": "remote python backend engineer", "limit": 5}`.
- **`GET /api/v1/analytics/report`** — the JSON behind the dashboard.

`JMI_SECRET_KEY` and the admin password are generated automatically by the
[`render.yaml`](render.yaml) blueprint; the read-only endpoints above need no
login. The free instance sleeps when idle, so the first request may take ~30s.

---

## Highlights

| Area | What it does |
| --- | --- |
| **Ingestion** | Pluggable job sources, polite HTTP client (retry, backoff, rate limiting, User-Agent rotation, robots.txt gate), incremental crawling |
| **NLP** | Rule-based skill/technology extraction over a curated taxonomy, text cleaning/normalisation, exact + near-duplicate detection, resume parsing |
| **Semantic search** | Natural-language queries (e.g. *"remote python jobs with fastapi and postgresql"*) via TF-IDF by default, sentence-transformers + FAISS when installed |
| **Recommendations** | Resume → match scores, missing skills, learning roadmap, salary prediction, career suggestions |
| **Analytics** | Top skills / languages / frameworks / databases / clouds, salary distribution, remote %, company / country / city rankings, monthly trends |
| **API** | FastAPI with auth, RBAC, pagination, filtering, sorting, versioning (`/api/v1`), OpenAPI docs, export (CSV/JSON/Excel) |
| **Dashboard** | Self-contained, theme-aware analytics dashboard served at `/` |
| **Ops** | Docker + Compose, GitHub Actions CI, APScheduler (and optional Celery/Redis) scheduling, structured logging with secret redaction |

## Design philosophy: graceful degradation

Heavy ML / infrastructure dependencies are **optional extras**. The platform
runs fully with a lightweight, deterministic default and *automatically upgrades*
its behaviour when an extra is installed:

| Extra | Default (no extra) | With extra |
| --- | --- | --- |
| `semantic` | TF-IDF cosine search | sentence-transformers dense embeddings + FAISS |
| `nlp` | rule-based taxonomy extraction | + spaCy NER enrichment |
| `postgres` | SQLite | PostgreSQL + Alembic migrations |
| `tasks` | APScheduler (in-process) | Celery + Redis distributed workers |
| `browser` | HTTP/HTML/JSON scraping | + Playwright JS rendering |

This keeps the default install small and the test-suite fast and hermetic.

---

## Quick start

```bash
# 1. Create a virtualenv and install (dev extras include the test tooling)
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# 2. Configure
cp .env.example .env
python -m jmi secret-key         # paste the output into JMI_SECRET_KEY

# 3. Create schema, an admin user and demo data
python -m jmi seed

# 4. Run the API + dashboard
python -m jmi serve --reload
```

Then open:

- Dashboard → <http://127.0.0.1:8000/>
- Swagger UI → <http://127.0.0.1:8000/docs>
- ReDoc → <http://127.0.0.1:8000/redoc>

### CLI

```bash
python -m jmi seed [--no-demo]      # schema + admin + demo data
python -m jmi ingest sample         # crawl a source into the DB
python -m jmi report                # print a market analytics report (JSON)
python -m jmi serve --reload        # run the API server
python -m jmi secret-key            # generate a strong secret
```

### Docker

```bash
export JMI_SECRET_KEY=$(python -m jmi secret-key)
docker compose up --build -d
# API on http://localhost:8000  (PostgreSQL + Redis included)
```

---

## Example API calls

```bash
# Login (the seeded admin) and capture a token
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"change-me-strong-password"}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# Filtered, paginated listing
curl "localhost:8000/api/v1/jobs?skill=Python&remote_status=remote&limit=5"

# Natural-language semantic search
curl -X POST localhost:8000/api/v1/search/semantic \
  -H 'Content-Type: application/json' \
  -d '{"query":"remote python jobs with fastapi and postgresql","top_k":5}'

# Market analytics
curl localhost:8000/api/v1/analytics/report

# Resume matching (authenticated)
curl -X POST localhost:8000/api/v1/recommendations/match \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"resume_text":"Backend engineer, 5 years Python, FastAPI, PostgreSQL, Docker, AWS."}'

# Export (authenticated)
curl -OJ -H "Authorization: Bearer $TOKEN" \
  "localhost:8000/api/v1/jobs/export?format=excel&skill=Python"
```

---

## Project layout (Clean Architecture)

```
src/jmi/
├── domain/            # framework-free entities, value objects, enums
├── application/       # use-case services + ORM→DTO mappers
├── infrastructure/    # DB (models, repositories, session), security,
│                      # export, notifications, scheduler
├── crawler/           # HTTP client, robots gate, pluggable sources, pipeline
├── nlp/               # taxonomy, cleaning, skill extraction, dedup, resumes
├── search/            # embeddings (TF-IDF / sentence-transformers) + index
├── analytics/         # pandas aggregations
├── api/               # FastAPI app, routers, deps, middleware, schemas
├── config.py          # pydantic-settings, secret enforcement
├── logging.py         # structlog with sensitive-key redaction
└── __main__.py        # CLI
```

Dependencies point **inwards**: `domain` knows nothing about the database or the
web framework; `application` orchestrates domain + infrastructure; `api` is a
thin transport layer. See [docs/architecture.md](docs/architecture.md).

---

## Security

- **Secrets**: loaded from env only; the app refuses to boot in production with a
  placeholder `JMI_SECRET_KEY`. `.env` is git-ignored; logs redact sensitive keys.
- **Auth**: JWT (PyJWT) access tokens; passwords hashed with bcrypt (per-password salt).
- **Authorization**: role-based (`admin` / `analyst` / `viewer`); public
  registration can only create a `viewer` — no privilege escalation.
- **Transport hardening**: security headers middleware, configurable CORS, HSTS in
  production, in-memory rate limiting (Redis-ready for multi-instance).
- **Injection safety**: all DB access goes through the SQLAlchemy ORM
  (parameterised); all input validated by Pydantic.
- **Scraping ethics**: robots.txt is honoured, requests are rate-limited and
  identify the bot; failures fail safe.

See [docs/developer-guide.md](docs/developer-guide.md#security-checklist).

---

## Testing & quality

```bash
ruff check src tests        # lint
ruff format --check src tests
mypy                        # static types
pytest --cov=jmi            # tests + coverage
```

The suite runs against an in-memory SQLite database and mocked HTTP transports —
no network, no external services. Current status: **83 tests, ~88% coverage**,
`ruff` clean, `mypy` clean.

---

## Documentation

- [Architecture](docs/architecture.md) — layers, data flow, sequence diagrams
- [ER diagram](docs/er-diagram.md) — database schema
- [Deployment guide](docs/deployment.md) — Docker, Postgres, Alembic, workers
- [Developer guide](docs/developer-guide.md) — adding sources, extending the taxonomy
- [API reference](docs/api.md) — endpoints, auth, examples

## License

MIT.
