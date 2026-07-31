# Architecture

The platform follows **Clean Architecture**: dependencies point inwards, and the
domain core has no knowledge of the web framework, the database, or any external
service. This keeps business rules independently testable and lets
infrastructure choices (SQLite ↔ PostgreSQL, TF-IDF ↔ transformers, APScheduler
↔ Celery) change without touching the core.

## Layers

```mermaid
flowchart TD
    subgraph API["api — transport (FastAPI)"]
        R[routers] --> DP[deps / middleware / schemas]
    end
    subgraph APP["application — use cases"]
        S[services] --> M[mappers]
    end
    subgraph DOM["domain — enterprise rules"]
        E[entities / value objects] --> EN[enums]
    end
    subgraph INFRA["infrastructure & adapters"]
        DB[(SQLAlchemy models + repositories)]
        SEC[security: bcrypt + JWT]
        EXP[export: csv/json/xlsx]
        NOTIF[notifications]
        SCHED[scheduler: APScheduler/Celery]
        CR[crawler: http/robots/sources/pipeline]
        NLP[nlp: taxonomy/skills/dedup/resume]
        SR[search: embeddings + index]
        AN[analytics: pandas]
    end

    API --> APP
    APP --> DOM
    APP --> INFRA
    CR --> DOM
    NLP --> DOM
    INFRA --> DOM
```

**Dependency rule:** `domain` imports nothing from the outer layers.
`application` depends on `domain` and orchestrates `infrastructure` through
narrow repository/service interfaces. `api` is a thin adapter that validates
input, calls a service, and serialises the result.

## Ingestion data flow

```mermaid
flowchart LR
    SRC[Source.fetch] --> CLEAN[clean_text]
    CLEAN --> SKILL[SkillExtractor]
    SKILL --> DEDUP[DuplicateDetector]
    DEDUP --> UPSERT[JobRepository.upsert_from_posting]
    UPSERT --> DBP[(PostgreSQL / SQLite)]
    UPSERT --> CREC[CrawlJob record]
```

A `Source` yields raw-but-structured `JobPosting` domain objects. The
`CrawlPipeline` cleans the text, extracts canonical skills, drops exact and
near-duplicates, and the `IngestService` upserts them (deduplicating on a
content hash) while recording a `CrawlJob` for observability.

## Request sequence — semantic search

```mermaid
sequenceDiagram
    participant C as Client
    participant A as FastAPI router
    participant S as SearchService
    participant I as SemanticSearchIndex
    participant DB as Repository

    C->>A: POST /api/v1/search/semantic {query}
    A->>S: search(query, top_k)
    S->>DB: all_for_index()
    DB-->>S: jobs
    S->>I: build(documents) [first call]
    S->>I: query(query, top_k)
    I-->>S: ranked doc ids + scores
    S-->>A: enriched job records
    A-->>C: 200 JSON (with scores)
```

## Request sequence — authenticated crawl

```mermaid
sequenceDiagram
    participant C as Client
    participant MW as Rate-limit + Security middleware
    participant A as Crawler router
    participant G as require_role(admin, analyst)
    participant Ing as IngestService
    participant P as CrawlPipeline

    C->>MW: POST /api/v1/crawler/ingest (Bearer token)
    MW->>A: forward (within rate limit)
    A->>G: resolve current user + check role
    G-->>A: authorized user
    A->>Ing: ingest(source)
    Ing->>P: run(source)
    P-->>Ing: unique postings
    Ing-->>A: CrawlJob (completed)
    A-->>C: 202 Accepted
```

## Cross-cutting concerns

- **Configuration** — `config.py` (pydantic-settings). Secrets from env only;
  production refuses placeholder secrets.
- **Logging** — `logging.py` (structlog), with a processor that redacts
  sensitive keys (`password`, `token`, `secret_key`, …) before any sink.
- **Errors** — a single `JMIError` hierarchy is mapped to HTTP responses by
  `api/errors.py`; unexpected exceptions never leak internals.
- **Extensibility** — new job portals are added by subclassing `BaseSource` and
  registering with `@registry.register`; the taxonomy is data-driven and can be
  extended from an external JSON file.
