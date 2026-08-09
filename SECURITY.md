# Security Policy

## Supported versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

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

## What to expect

- Acknowledgement within **72 hours**.
- An initial assessment within **7 days**.
- A fix and a published advisory once a patch is ready.
- Credit in the advisory, if you want it.

## Scope

In scope: the code in this repository — the REST API, the JWT/RBAC layer, the
ingestion adapters that fetch third-party content, the NLP pipeline, and
anything that handles a request, an uploaded resume, or a secret.

Out of scope:

- Vulnerabilities in third-party dependencies or in the NLP models themselves —
  report those upstream; if this project's use of them is what makes them
  exploitable, that *is* in scope.
- Findings that require an attacker to already control the host or the process.

## Notes for operators

- `JMI_SECRET_KEY` must be a real random value in any deployment — generate one
  with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. The value
  in `.env.example` and the one used in CI are placeholders and must never reach
  a running deployment.
- Uploaded resumes are user-supplied input. Treat the parsed text as untrusted
  and keep the storage location outside any web-served directory.
- Ingestion fetches remote URLs. Run it with egress restricted to the sources
  you intend, and only ingest sources you are permitted to.
