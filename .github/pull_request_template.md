## What and why

<!-- What does this change, and what problem does it solve? Link any related issue. -->

## How it was verified

<!-- Commands run, cases covered, anything checked manually. -->

## Checklist

- [ ] Tests added or updated (a bug fix has a test that fails without it)
- [ ] `make check` passes locally (lint, types, tests, audit)
- [ ] Docstrings and docs updated where behaviour changed
- [ ] No secrets, credentials, or personal data in the diff

## Security impact

<!-- Delete this section if the change cannot affect security. -->

- [ ] Touches auth, tokens, rate limiting, config, or data export
- [ ] Regression test added to `tests/test_security_hardening.py`
- [ ] Threat model in `SECURITY.md` still accurate
