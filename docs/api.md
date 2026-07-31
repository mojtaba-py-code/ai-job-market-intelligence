# API Reference

Base path: `/api/v1`. Interactive docs: `/docs` (Swagger) and `/redoc`.
Auth: JWT bearer tokens (`Authorization: Bearer <token>`).

## Authentication

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| POST | `/api/v1/auth/register` | — | Register a user (always `viewer`) |
| POST | `/api/v1/auth/login` | — | Login with JSON body → access token |
| POST | `/api/v1/auth/token` | — | OAuth2 password flow (Swagger "Authorize") |
| GET  | `/api/v1/auth/me` | bearer | Current user profile |

```bash
curl -X POST localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"..."}'
# → {"access_token":"eyJ...","token_type":"bearer"}
```

## Jobs

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/api/v1/jobs` | — | Paginated / filtered / sorted listing |
| GET | `/api/v1/jobs/{id}` | — | Full job detail |
| GET | `/api/v1/jobs/export` | bearer | Export filtered set (`format=csv\|json\|excel`) |

**Query parameters** for `GET /api/v1/jobs`:

| Param | Type | Notes |
| --- | --- | --- |
| `q` | string | free-text in title/description |
| `company`, `country`, `city`, `category`, `skill` | string | exact filters |
| `remote_status` | enum | `remote\|hybrid\|on_site\|unknown` |
| `min_salary` | number | matches jobs whose `salary_max ≥ value` |
| `sort` | string | `posted_at`, `salary_max`, `created_at`, `title` (prefix `-` for desc) |
| `limit` | int | 1–100 (default 20) |
| `offset` | int | ≥ 0 |

Response:

```json
{ "items": [ { "id": 1, "title": "...", "skills": [...] } ],
  "total": 42, "limit": 20, "offset": 0 }
```

## Semantic search

| Method | Path | Auth |
| --- | --- | --- |
| POST | `/api/v1/search/semantic` | — |

```json
// request
{ "query": "remote python jobs with fastapi and postgresql", "top_k": 5 }
// response: job summaries, each with a "score"
```

## Analytics

| Method | Path | Auth |
| --- | --- | --- |
| GET | `/api/v1/analytics/report?top_n=15` | — |

Returns `total_jobs`, `remote_percentage`, `top_skills`, `top_languages`,
`top_frameworks`, `top_databases`, `top_cloud`, `salary_by_currency`,
`top_companies`, `top_countries`, `top_cities`, `monthly_trend`.

## Recommendations

| Method | Path | Auth |
| --- | --- | --- |
| POST | `/api/v1/recommendations/match` | bearer |

```json
// request
{ "resume_text": "Backend engineer, 5 years Python, FastAPI, PostgreSQL...", "top_k": 10 }
// response
{ "resume_skills": ["Python", "FastAPI", ...],
  "years_experience": 5,
  "matches": [ { "job_id": 1, "score": 0.82, "matched_skills": [...], "missing_skills": [...] } ],
  "learning_roadmap": [ { "skill": "Kubernetes", "demand": 3 } ],
  "salary_prediction": { "currency": "USD", "expected_min": 140000, "expected_median": 160000, "expected_max": 180000, "based_on": 3 },
  "career_suggestions": ["Backend Engineering", "Data Engineering"] }
```

## Crawler (admin / analyst)

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| POST | `/api/v1/crawler/ingest` | admin/analyst | Crawl a source and persist |
| GET | `/api/v1/crawler/jobs` | admin/analyst | Recent crawl runs |
| GET | `/api/v1/sources` | — | Registered sources |

## System

| Method | Path | Description |
| --- | --- | --- |
| GET | `/health` | Liveness (never rate-limited) |
| GET | `/api/v1/ready` | Readiness (checks the database) |
| GET | `/` | HTML analytics dashboard |

## Errors

All errors share a consistent shape and never leak internals:

```json
{ "error": "not_found", "detail": "Job 999 not found." }
```

| Status | `error` code |
| --- | --- |
| 401 | `authentication_error` |
| 403 | `authorization_error` |
| 404 | `not_found` |
| 409 | `conflict` |
| 422 | `validation_error` (Pydantic) |
| 429 | `rate_limited` |
| 500 | `internal_error` |

## Rate limiting

Fixed-window per client IP (`JMI_RATE_LIMIT_REQUESTS` per
`JMI_RATE_LIMIT_WINDOW_SECONDS`). Responses include `X-RateLimit-Limit` and
`X-RateLimit-Remaining`; 429s include `Retry-After`. `/health` and docs are exempt.
