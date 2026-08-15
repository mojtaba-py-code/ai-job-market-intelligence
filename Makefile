.PHONY: help install dev hooks lint format type test cov audit check run seed ingest report docker-up docker-down clean

PY ?= python

help:
	@echo "Targets:"
	@echo "  install   Install the package (runtime deps)"
	@echo "  dev       Install with dev + optional extras"
	@echo "  hooks     Install the pre-commit hooks"
	@echo "  lint      Run ruff"
	@echo "  format    Auto-format / auto-fix with ruff"
	@echo "  type      Run mypy"
	@echo "  test      Run pytest"
	@echo "  cov       Run pytest with coverage"
	@echo "  audit     Security scan (bandit + pip-audit)"
	@echo "  check     lint + type + test + audit (what CI runs)"
	@echo "  run       Start the API server (reload)"
	@echo "  seed      Create schema, admin user and demo data"
	@echo "  report    Print a market analytics report"
	@echo "  docker-up Build and start the full stack"

install:
	$(PY) -m pip install -e .

dev:
	$(PY) -m pip install -e ".[dev]"

lint:
	$(PY) -m ruff check src tests

format:
	$(PY) -m ruff check --fix src tests
	$(PY) -m ruff format src tests

type:
	$(PY) -m mypy

test:
	$(PY) -m pytest -q

cov:
	$(PY) -m pytest --cov=jmi --cov-report=term-missing

audit:
	$(PY) -m bandit -c pyproject.toml -r src -ll
	$(PY) -m pip_audit --skip-editable --progress-spinner off

check: lint type test audit

hooks:
	$(PY) -m pre_commit install

run:
	$(PY) -m jmi serve --reload

seed:
	$(PY) -m jmi seed

ingest:
	$(PY) -m jmi ingest sample

report:
	$(PY) -m jmi report

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
