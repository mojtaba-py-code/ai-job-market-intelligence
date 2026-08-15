# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] — 2026-08-15

A second hardening pass, focused on what a request can *cost* and what it can
*reveal* — the areas the first pass did not cover.

### Security

- **Fixed an unauthenticated CPU amplification in semantic search.** Every call
  to the public `/api/v1/search/semantic` rebuilt the index from scratch: it
  fitted the embedder over the whole corpus, embedded every document, and loaded
  all jobs from the database *twice*. One small HTTP request therefore cost
  O(corpus) CPU and allocations, so the endpoint got more expensive as the
  platform got more useful, and the rate limit was no defence. The index is now
  built once per corpus state and shared process-wide, invalidated by a cheap
  fingerprint and explicitly after ingestion. Measured at 1,200 postings: **199 ms
  → 25 ms per request**, with the gap widening linearly as the corpus grows.
- **Capped request body size** (`JMI_MAX_REQUEST_BODY_BYTES`, 1 MiB default).
  Pydantic's field limits only apply once the whole body is buffered, so a
  multi-gigabyte POST to a 50 KB field was still multi-gigabytes of memory spent
  before anything rejected it. Enforced as raw ASGI so a chunked body with no
  declared `Content-Length` is cut off as it arrives rather than trusted.
- **Added a per-account login lockout.** The existing limiter meters by client
  address, which a distributed attempt sidesteps entirely — guesses spread over
  many addresses each stay under budget while the account absorbs thousands. It
  keys on the submitted identifier, so unknown accounts throttle identically and
  the lockout does not become an existence oracle. A correct password clears the
  counter, so nobody can hold a real user out by failing logins on their behalf.
- **Stopped disclosing the build.** `/health` withheld nothing, so an
  unauthenticated caller could read the exact version and match it against
  published advisories. It now reports only status in production, and the
  `Server` banner no longer names the underlying software.
- **Added `Cache-Control: no-store, private`** to every `/api/` response, so job
  data and exports do not linger in shared caches or browser history.
- **Hardened the containers**: read-only root filesystem with writable paths on
  tmpfs, every Linux capability dropped, and `no-new-privileges` on all three
  services. CI now starts the stack and serves requests through it, because this
  is exactly the kind of change that passes review and fails at runtime.

### Fixed

- `create_app(settings)` was silently ignored downstream: routes read the cached
  process-wide settings instead, so a route deciding what to disclose based on
  the environment read the wrong environment. Settings are now published on
  `app.state` and resolved through a dependency.
- The body-limit middleware built its rejection response with a `None` ASGI
  scope, which raised instead of returning 413. Caught by its own test.

### Added

- `tests/test_security_resources.py` — 20 tests covering the above.
- `.well-known/security.txt` (RFC 9116) for machine-readable disclosure contact.
- A personal-data section in `SECURITY.md`, recording that resume text is never
  persisted or logged, and that the unused `resumes` table must not be wired up
  without encryption at rest, a retention period and a deletion path.

## [1.1.0] — 2026-08-15

A security-hardening release. Every change below has a matching regression test
in `tests/test_security_hardening.py`; the threat model is documented in
[SECURITY.md](SECURITY.md).

### Security

- **Rate limiting can no longer be bypassed by forging `X-Forwarded-For`.** The
  header was previously trusted unconditionally, so a single host could mint an
  unlimited number of identities and get a fresh request budget for each. It is
  now honoured only when `JMI_TRUSTED_PROXY_HOPS` is set, and read from the hop
  the trusted proxy actually wrote.
- **Bounded the rate limiter's memory.** The client table grew without limit, so
  a flood of distinct source addresses could exhaust memory — the limiter itself
  becoming the denial of service. Entries are now held in an LRU.
- **Added a dedicated brute-force budget for credential endpoints.** Login,
  token and registration requests are metered separately and far more tightly
  than the general limit.
- **Fixed the user-enumeration timing defence, which did not work.** The decoy
  used for unknown accounts was not a valid bcrypt hash, so `checkpw` rejected it
  immediately without hashing — making "no such user" measurably *faster* than a
  real password check. It is now a genuine hash computed once per process.
- **Secrets are `SecretStr` throughout.** `repr()`, `str()` and `model_dump()`
  previously exposed the signing key, SMTP password, Telegram token and admin
  password in tracebacks and log lines.
- **Rejected wildcard CORS combined with credentials.** Starlette echoes the
  caller's `Origin` when credentials are allowed, so `*` stopped being an
  anonymous-only policy and let any site read authenticated responses. The
  combination is now fatal at startup; the Render demo was configured this way.
- **Escaped spreadsheet formula injection in CSV and Excel exports.** Scraped job
  text flows straight into files analysts open locally, where a title beginning
  `=`, `+`, `-` or `@` is executed by Excel, LibreOffice and Google Sheets.
- **Hardened JWTs**: symmetric algorithm allowlist (rejecting `alg: none` and
  key-confusion attacks), issuer and audience binding, a `typ` marker so other
  token kinds cannot be replayed as access tokens, a required-claim set, and a
  unique `jti`. Caller-supplied extra claims can no longer override `role` or
  `sub`.
- **Added a nonce-based Content-Security-Policy** with no `unsafe-inline`, plus
  `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy` and
  `X-Permitted-Cross-Domain-Policies`.
- **Disabled OpenAPI docs in production by default** (`JMI_DOCS_ENABLED` opts
  back in).
- **Refused unsafe production boots.** Every placeholder credential is now fatal
  — signing key, bootstrap admin e-mail and password — not just the signing key,
  because `jmi seed` creates that admin with the `admin` role and its default
  password is published in this repository. Short signing keys and
  `JMI_DEBUG=true` are refused too, and all problems are reported together
  rather than one restart at a time.
- **Capped crawler response size**, so a hostile or broken source cannot stream
  an unbounded body into memory.
- **Made text cleaning and e-mail extraction linear**, removing patterns whose
  backtracking was quadratic on adversarial input (ReDoS).
- **Stopped publishing PostgreSQL and Redis to the Docker host**, and required a
  Redis password — an unauthenticated Redis on a public interface is a full host
  compromise.
- **Pinned GitHub Actions to commit SHAs** and scoped the workflow token to read.
- Raised dependency floors off releases with published CVEs.
- Disabled accounts are no longer disclosed to callers who do not hold the
  password; the active check moved after password verification.
- Escaped `LIKE` metacharacters in free-text search, keeping user queries literal
  and preventing a `%` query from forcing a full scan of every description.
- A malformed `sub` claim now returns 401 rather than a 500.

### Added

- `SECURITY.md`, now carrying a full threat model — assets, a table mapping each
  threat to its control and the file enforcing it, what is deliberately not
  defended against, and a pre-launch checklist.
- `tests/test_security_hardening.py` — 60+ regression tests written as attacks
  that must fail.
- Security CI: Bandit and `pip-audit` on every push, plus a weekly workflow
  adding Gitleaks over full history and Trivy container scanning. CodeQL is left
  to GitHub's default code scanning setup, which cannot coexist with an advanced
  workflow configuration.
- Dependabot coverage extended to Docker base images.
- `.pre-commit-config.yaml` including private-key and secret detection.
- `CHANGELOG.md`, `CODE_OF_CONDUCT.md`, issue and pull request templates.
- `make audit`, `make check` and `make hooks` targets.

### Changed

- CORS now allows only the methods and headers the API actually uses, rather
  than `*`.
- Dashboard bar widths are applied through the CSSOM instead of inline `style`
  attributes, which a CSP nonce cannot authorise.
- Short passwords at registration return 422 rather than 409.

### Fixed

- `package-data` referenced a `../../data/taxonomy/*.json` path that does not
  exist, and omitted the dashboard and demo fixtures actually needed at runtime,
  so built wheels shipped without the dashboard and silently served a stub page.
- Corrected a wrong expectation in the tag-stripping test.

## [1.0.0] — 2026-07-31

Initial release.

### Added

- Clean Architecture layout: domain, application, infrastructure and API layers.
- Pluggable multi-source ingestion with a polite HTTP client — retry with
  exponential backoff, per-host rate limiting, User-Agent rotation and a
  robots.txt gate.
- Rule-based NLP pipeline: skill and technology extraction over a curated
  taxonomy, text normalisation, exact and near-duplicate detection.
- Semantic search over TF-IDF by default, upgrading to sentence-transformers and
  FAISS when the `semantic` extra is installed.
- Resume matching with skill-gap analysis and a learning roadmap.
- Market analytics: top skills, languages, frameworks, databases and clouds,
  salary distribution, remote share, company and geography rankings.
- FastAPI backend with JWT auth, role-based authorization, pagination, filtering,
  sorting and CSV/JSON/Excel export.
- Self-contained analytics dashboard.
- SQLAlchemy 2.0 models with the repository pattern; SQLite by default,
  PostgreSQL with Alembic migrations via the `postgres` extra.
- Docker, Docker Compose and GitHub Actions CI.

[1.2.0]: https://github.com/mojtaba-py-code/ai-job-market-intelligence/releases/tag/v1.2.0
[1.1.0]: https://github.com/mojtaba-py-code/ai-job-market-intelligence/releases/tag/v1.1.0
[1.0.0]: https://github.com/mojtaba-py-code/ai-job-market-intelligence/releases/tag/v1.0.0
