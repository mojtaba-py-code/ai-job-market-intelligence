# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| 1.1.x | ✅ |
| 1.0.x | ⚠️ Security fixes only |
| < 1.0 | ❌ |

Security fixes are applied to `main` and released from there.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Report it privately through GitHub's
[Report a vulnerability](https://github.com/mojtaba-py-code/ai-job-market-intelligence/security/advisories/new)
form, or by email to **mojtaba.python@gmail.com**.

Include what you can:

- the affected version, tag or commit,
- what the issue is and what an attacker gains from it,
- steps or a minimal proof of concept that reproduces it.

| Stage | Target |
| --- | --- |
| Acknowledgement | within 72 hours |
| Initial assessment | within 7 days |
| Fix and published advisory | once a patch is ready |

Reporters are credited in the advisory unless they prefer otherwise.

## Scope

In scope: the code in this repository — the REST API, the JWT/RBAC layer, the
ingestion adapters that fetch third-party content, the NLP pipeline, and
anything that handles a request, an uploaded resume, or a secret.

Out of scope:

- Vulnerabilities in third-party dependencies or in the NLP models themselves —
  report those upstream; if this project's *use* of them is what makes them
  exploitable, that **is** in scope.
- Findings that require an attacker to already control the host or the process.

---

## Threat model

The platform ingests data from **untrusted third-party job boards** and serves it
to authenticated analysts over a public HTTP API. That shapes the whole design:
scraped text is treated as hostile input all the way through to export, and no
request-supplied value is trusted for identity or authorisation.

### Assets

| Asset | Protection |
| --- | --- |
| User credentials | bcrypt hashes with per-password salt; never logged |
| Signing key | `SecretStr`, environment-only, validated at boot |
| SMTP / Telegram credentials | `SecretStr`, redacted from structured logs |
| Job corpus & analytics | read APIs are public by design; write and export paths require auth |

### Controls

| Threat | Control | Enforced in |
| --- | --- | --- |
| Credential stuffing / brute force | Dedicated auth rate-limit budget, far tighter than the global one | [`api/middleware.py`](src/jmi/api/middleware.py) |
| Rate-limit evasion via forged `X-Forwarded-For` | Header honoured only when `JMI_TRUSTED_PROXY_HOPS > 0`, and read from the trusted hop | [`api/middleware.py`](src/jmi/api/middleware.py) |
| Limiter memory exhaustion | LRU-bounded client table | [`api/middleware.py`](src/jmi/api/middleware.py) |
| User enumeration | Uniform error text; a real bcrypt decoy hash equalises timing for unknown accounts | [`services/auth_service.py`](src/jmi/application/services/auth_service.py) |
| JWT forgery (`alg: none`, key confusion) | Symmetric algorithm allowlist, verified against the configured algorithm only | [`config.py`](src/jmi/config.py), [`security/tokens.py`](src/jmi/infrastructure/security/tokens.py) |
| Cross-deployment token replay | Issuer + audience binding, `typ` marker, required-claim set, unique `jti` | [`security/tokens.py`](src/jmi/infrastructure/security/tokens.py) |
| Privilege escalation at registration | `role` is not part of the public registration schema | [`api/schemas.py`](src/jmi/api/schemas.py) |
| Spreadsheet formula injection (CSV/Excel) | Untrusted cell values escaped on export | [`export/exporters.py`](src/jmi/infrastructure/export/exporters.py) |
| Stored XSS via scraped job text | Output escaping in the dashboard, plus a nonce-based CSP with no `unsafe-inline` | [`api/static/dashboard.html`](src/jmi/api/static/dashboard.html), [`api/middleware.py`](src/jmi/api/middleware.py) |
| Cross-origin theft of authenticated responses | Wildcard CORS with credentials is rejected at startup | [`config.py`](src/jmi/config.py) |
| SQL injection | All access through SQLAlchemy expressions; LIKE metacharacters escaped | [`db/repositories.py`](src/jmi/infrastructure/db/repositories.py) |
| Catastrophic backtracking (ReDoS) in text cleaning | Linear-time patterns, with tests asserting growth rather than wall clock | [`nlp/cleaner.py`](src/jmi/nlp/cleaner.py), [`nlp/resume.py`](src/jmi/nlp/resume.py) |
| Secret leakage via logs or tracebacks | `SecretStr` everywhere + structlog key redaction | [`config.py`](src/jmi/config.py), [`logging.py`](src/jmi/logging.py) |
| Insecure production boot | Placeholder credentials, weak secret, debug mode and unsafe CORS are all fatal | [`config.py`](src/jmi/config.py) |
| Crawler memory exhaustion | Response size cap; robots.txt gate fails closed on network error | [`crawler/http_client.py`](src/jmi/crawler/http_client.py) |
| API surface disclosure | OpenAPI docs off by default in production | [`api/app.py`](src/jmi/api/app.py) |
| Exposed backing services | PostgreSQL and Redis are not published to the host; Redis requires a password | [`docker-compose.yml`](docker-compose.yml) |

Each control has a matching regression test in
[`tests/test_security_hardening.py`](tests/test_security_hardening.py), written
as "an attacker does X, and X fails".

### Not defended against

- **Multi-instance rate limiting.** The limiter is in-process; each instance
  keeps its own counters. Put a shared limiter (Redis, or the ingress) in front
  of a horizontally scaled deployment.
- **Token revocation.** Access tokens are stateless and valid until they expire;
  keep `JMI_ACCESS_TOKEN_TTL_MINUTES` short. The `jti` claim is emitted so a
  denylist can be added without changing the token format.
- **TLS termination**, which belongs to the reverse proxy or platform. HSTS is
  emitted in production on the assumption that TLS is already in place.
- **Availability under volumetric DDoS**, which needs network-layer defences.

---

## Notes for operators

- `JMI_SECRET_KEY` must be a real random value in any deployment — generate one
  with `python -m jmi secret-key`. The value in `.env.example` and the one used
  in CI are placeholders and must never reach a running deployment. Use a
  different key per environment: sharing one lets a token minted for staging
  authenticate against production.
- Uploaded resumes are user-supplied input. Treat the parsed text as untrusted
  and keep the storage location outside any web-served directory.
- Ingestion fetches remote URLs. Run it with egress restricted to the sources
  you intend, and only ingest sources you are permitted to.

### Deployment checklist

Before exposing an instance publicly:

- [ ] `JMI_SECRET_KEY` set from `python -m jmi secret-key` (32+ chars, unique per environment)
- [ ] `JMI_ENV=production` and `JMI_DEBUG=false` — this activates the boot-time guards
- [ ] `JMI_ADMIN_EMAIL` and `JMI_ADMIN_PASSWORD` changed from their defaults, then the password rotated after first login
- [ ] `JMI_CORS_ORIGINS` set to explicit origins, not `*`, whenever credentials are allowed
- [ ] `JMI_TRUSTED_PROXY_HOPS` matches the actual number of proxies in front of the app
- [ ] TLS terminated upstream, HTTP redirected to HTTPS
- [ ] `JMI_DOCS_ENABLED` left off unless public API docs are intentional
- [ ] PostgreSQL rather than SQLite, with migrations applied via Alembic
- [ ] Backing services unreachable from outside the deployment network
- [ ] Log sink scanned to confirm no credentials appear

Setting `JMI_TRUSTED_PROXY_HOPS` higher than the real proxy count lets clients
forge their rate-limit identity — it must match the deployment exactly.
