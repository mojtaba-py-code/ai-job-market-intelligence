"""Command-line entry point.

Usage:
    jmi serve [--host H] [--port P] [--reload]
    jmi seed [--no-demo]
    jmi ingest <source> [--limit N] [--since YYYY-MM-DD]
    jmi report
    jmi secret-key
"""

from __future__ import annotations

import argparse
import json
import sys

from .config import generate_secret_key, get_settings


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "jmi.api.app:app",
        host=args.host or settings.api_host,
        port=args.port or settings.api_port,
        reload=args.reload,
    )
    return 0


def _cmd_seed(args: argparse.Namespace) -> int:
    from .seed import seed

    seed(with_demo_data=not args.no_demo)
    print("Seed complete.")
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    from .application.services import IngestService
    from .crawler import sources  # noqa: F401  register sources
    from .infrastructure.db.session import create_all, session_scope

    create_all()
    with session_scope() as session:
        record = IngestService(session).ingest(args.source, since=args.since, limit=args.limit)
        print(
            f"Ingested '{args.source}': fetched={record.fetched} "
            f"unique={record.unique_count} duplicates={record.duplicates}"
        )
    return 0


def _cmd_report(_args: argparse.Namespace) -> int:
    from .application.services import AnalyticsService
    from .infrastructure.db.session import session_scope

    with session_scope() as session:
        report = AnalyticsService(session).market_report()
    print(json.dumps(report.as_dict(), indent=2, default=str))
    return 0


def _cmd_secret_key(_args: argparse.Namespace) -> int:
    print(generate_secret_key())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jmi", description="Job Market Intelligence CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Run the API server")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--reload", action="store_true")
    serve.set_defaults(func=_cmd_serve)

    seed = sub.add_parser("seed", help="Create schema, admin user and demo data")
    seed.add_argument("--no-demo", action="store_true", help="Skip demo ingestion")
    seed.set_defaults(func=_cmd_seed)

    ingest = sub.add_parser("ingest", help="Crawl and store a source")
    ingest.add_argument("source")
    ingest.add_argument("--limit", type=int, default=None)
    ingest.add_argument("--since", default=None)
    ingest.set_defaults(func=_cmd_ingest)

    report = sub.add_parser("report", help="Print a market analytics report as JSON")
    report.set_defaults(func=_cmd_report)

    secret = sub.add_parser("secret-key", help="Generate a strong secret key")
    secret.set_defaults(func=_cmd_secret_key)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
