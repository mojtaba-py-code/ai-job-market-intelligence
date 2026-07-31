# syntax=docker/dockerfile:1

# ---- Builder ---------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Build tools for lxml / bcrypt wheels (removed from the final image).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

# Build a wheel and install it into an isolated prefix we can copy over.
# The skill taxonomy and sample data ship inside the package, so no top-level
# data directory needs to be copied here.
RUN pip install --upgrade pip build \
    && pip wheel --wheel-dir /wheels ".[postgres]"

# ---- Runtime ---------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    JMI_ENV=production

# Runtime libs only (no compilers).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libxml2 libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

# Create an unprivileged user to run the app.
RUN useradd --create-home --uid 10001 appuser
WORKDIR /app

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

# Writable runtime dir for the SQLite quick-start (Postgres is used in prod).
RUN mkdir -p /app/data/runtime && chown -R appuser:appuser /app/data

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx,os; httpx.get(f'http://127.0.0.1:{os.getenv(\"JMI_API_PORT\",\"8000\")}/health').raise_for_status()"

CMD ["uvicorn", "jmi.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
