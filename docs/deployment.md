# Deployment Guide

## 1. Environment

Copy `.env.example` to `.env` and set at minimum:

```bash
JMI_ENV=production
JMI_DEBUG=false
JMI_SECRET_KEY=<output of: python -m jmi secret-key>
JMI_DATABASE_URL=postgresql+psycopg://jmi:PASSWORD@db:5432/jmi
JMI_CORS_ORIGINS=https://your-frontend.example.com
```

> The application **refuses to start in production** if `JMI_SECRET_KEY` is unset
> or left at the placeholder value.

## 2. Docker Compose (recommended)

The bundled stack runs the API, PostgreSQL and Redis:

```bash
export JMI_SECRET_KEY=$(python -m jmi secret-key)
export POSTGRES_PASSWORD=$(python -c "import secrets;print(secrets.token_urlsafe(24))")
docker compose up --build -d
docker compose logs -f api
```

The `api` service runs `jmi seed` (schema + admin + demo data) and then serves
on port 8000. Remove the demo ingest from the compose `command` for a clean
production database, or run `python -m jmi seed --no-demo`.

## 3. Database migrations (PostgreSQL)

For SQLite the schema is auto-created. For PostgreSQL use Alembic:

```bash
pip install -e ".[postgres]"

# Generate the initial migration from the models
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

`migrations/env.py` reads the database URL from application settings, so the
same `JMI_DATABASE_URL` drives both the app and migrations.

## 4. Background workers

**In-process (default)** — APScheduler, wired via
`jmi.infrastructure.scheduler.CrawlScheduler`; suitable for a single instance.

**Distributed (optional)** — Celery + Redis:

```bash
pip install -e ".[tasks]"
celery -A jmi.infrastructure.scheduler.celery_app.celery_app worker --loglevel=info
```

Dispatch a crawl:

```python
from jmi.infrastructure.scheduler.celery_app import ingest_source
ingest_source.delay("sample")
```

## 5. Reverse proxy & TLS

Run behind a reverse proxy (nginx / Traefik / a cloud LB) terminating TLS.
The app already sets security headers and, in production, HSTS. Ensure the proxy
forwards `X-Forwarded-For` so rate limiting keys on the real client IP.

Example (nginx):

```nginx
location / {
    proxy_pass http://api:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

## 6. Scaling notes

- The API is stateless — scale horizontally behind the load balancer.
- For multi-instance deployments, back the rate limiter with Redis (a drop-in
  replacement for the in-memory limiter) so limits are shared.
- The semantic index is in-memory per process; for large corpora enable the
  `semantic` extra (FAISS) and/or externalise the index to a vector store.

## 7. Observability

- **Health**: `GET /health` (liveness), `GET /api/v1/ready` (readiness — checks
  the DB). The Docker image ships a `HEALTHCHECK`.
- **Logs**: structured JSON in production (`structlog`), with sensitive-key
  redaction — ship to your log aggregator.
- **Metrics**: install the `metrics` extra (`prometheus-client`) to expose
  application metrics for Prometheus/Grafana.
