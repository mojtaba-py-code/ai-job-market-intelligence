# Entity-Relationship Diagram

The schema is normalised around the natural entities of the domain. Companies
and skills are shared across jobs (foreign key / many-to-many); location and
salary are stored on the job row as a deliberate, read-optimised denormalisation
for the analytics workload.

```mermaid
erDiagram
    USERS ||--o{ RESUMES : owns
    COMPANIES ||--o{ JOBS : posts
    JOBS ||--o{ JOB_SKILLS : has
    SKILLS ||--o{ JOB_SKILLS : appears_in

    USERS {
        int id PK
        string email UK
        string hashed_password
        enum role
        bool is_active
        datetime created_at
    }

    COMPANIES {
        int id PK
        string name UK
        string industry
        string size
    }

    SKILLS {
        int id PK
        string name UK
        enum kind
    }

    JOBS {
        int id PK
        string source
        string external_id
        string content_hash UK
        string title
        string url
        text description
        int company_id FK
        enum employment_type
        enum remote_status
        enum seniority
        string category
        string country
        string city
        float salary_min
        float salary_max
        string currency
        string salary_period
        int experience_years_min
        date posted_at
        date expires_at
        datetime scraped_at
    }

    JOB_SKILLS {
        int job_id PK,FK
        int skill_id PK,FK
    }

    RESUMES {
        int id PK
        int user_id FK
        string filename
        text text
        int years_experience
        datetime created_at
    }

    CRAWL_JOBS {
        int id PK
        string source
        enum status
        datetime started_at
        datetime finished_at
        int fetched
        int unique_count
        int duplicates
        text error
    }
```

## Constraints & indexes

- `jobs (source, external_id)` — unique together (a source's stable id).
- `jobs.content_hash` — unique; the deduplication key (SHA-256 of normalised
  title + company + location + description prefix).
- Indexed for query performance: `jobs.remote_status`, `jobs.category`,
  `jobs.country`, `jobs.city`, `jobs.title`, `companies.name`, `skills.name`,
  `users.email`.
- Foreign keys use `ON DELETE CASCADE` where a child cannot exist without its
  parent (`job_skills`, `resumes`).

Migrations are managed with **Alembic** (`jmi[postgres]` extra); for the SQLite
quick-start the schema is created automatically on startup.
