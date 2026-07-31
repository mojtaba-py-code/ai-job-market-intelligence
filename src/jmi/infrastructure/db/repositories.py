"""Repository pattern over the ORM.

Repositories are the only place that speaks SQLAlchemy. Services depend on these
narrow interfaces, which keeps business logic free of query details and makes it
trivial to unit-test with an in-memory SQLite database.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ...domain.entities import JobPosting
from ...domain.enums import SkillKind, UserRole
from .models import Company, CrawlJob, Job, Resume, Skill, User


@dataclass(slots=True)
class JobFilter:
    """Filter/sort/paginate options for job queries."""

    query: str | None = None
    company: str | None = None
    country: str | None = None
    city: str | None = None
    remote_status: str | None = None
    category: str | None = None
    skill: str | None = None
    min_salary: float | None = None
    sort: str = "-posted_at"
    limit: int = 20
    offset: int = 0


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_email(self, email: str) -> User | None:
        return self.session.scalar(select(User).where(User.email == email.lower()))

    def get(self, user_id: int) -> User | None:
        return self.session.get(User, user_id)

    def create(self, *, email: str, hashed_password: str, role: UserRole) -> User:
        user = User(email=email.lower(), hashed_password=hashed_password, role=role)
        self.session.add(user)
        self.session.flush()
        return user


class CompanyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create(
        self, name: str, *, industry: str | None = None, size: str | None = None
    ) -> Company:
        company = self.session.scalar(select(Company).where(Company.name == name))
        if company is None:
            company = Company(name=name, industry=industry, size=size)
            self.session.add(company)
            self.session.flush()
        else:
            # Backfill metadata if it was missing.
            if industry and not company.industry:
                company.industry = industry
            if size and not company.size:
                company.size = size
        return company


class SkillRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._cache: dict[str, Skill] = {}

    def get_or_create(self, name: str, kind: SkillKind) -> Skill:
        if name in self._cache:
            return self._cache[name]
        skill = self.session.scalar(select(Skill).where(Skill.name == name))
        if skill is None:
            skill = Skill(name=name, kind=kind)
            self.session.add(skill)
            self.session.flush()
        self._cache[name] = skill
        return skill


class JobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.companies = CompanyRepository(session)
        self.skills = SkillRepository(session)

    def get(self, job_id: int) -> Job | None:
        return self.session.get(Job, job_id)

    def get_by_hash(self, content_hash: str) -> Job | None:
        return self.session.scalar(select(Job).where(Job.content_hash == content_hash))

    def exists(self, source: str, external_id: str) -> bool:
        stmt = (
            select(func.count())
            .select_from(Job)
            .where(Job.source == source, Job.external_id == external_id)
        )
        return bool(self.session.scalar(stmt))

    def upsert_from_posting(self, posting: JobPosting) -> tuple[Job, bool]:
        """Insert or update a job from a domain posting.

        Returns ``(job, created)``. Deduplicates on ``content_hash``.
        """
        existing = self.get_by_hash(posting.content_hash)
        company = self.companies.get_or_create(
            posting.company,
            industry=posting.company_industry,
            size=posting.company_size,
        )
        skills = [self.skills.get_or_create(s.name, s.kind) for s in posting.skills]

        if existing is not None:
            existing.title = posting.title
            existing.description = posting.description
            existing.skills = skills
            return existing, False

        job = Job(
            source=posting.source,
            external_id=posting.external_id,
            content_hash=posting.content_hash,
            title=posting.title,
            url=posting.url,
            description=posting.description,
            company=company,
            employment_type=posting.employment_type,
            remote_status=posting.remote_status,
            seniority=posting.seniority,
            category=posting.category,
            country=posting.location.country,
            city=posting.location.city,
            salary_min=posting.salary.min_amount,
            salary_max=posting.salary.max_amount,
            currency=posting.salary.currency,
            salary_period=posting.salary.period,
            experience_years_min=posting.experience_years_min,
            education=posting.education,
            posted_at=posting.posted_at,
            expires_at=posting.expires_at,
            scraped_at=posting.scraped_at,
            skills=skills,
        )
        self.session.add(job)
        self.session.flush()
        return job, True

    # -- Queries ------------------------------------------------------------
    def _apply_filter(self, stmt, flt: JobFilter):
        if flt.query:
            like = f"%{flt.query.lower()}%"
            stmt = stmt.where(
                func.lower(Job.title).like(like) | func.lower(Job.description).like(like)
            )
        if flt.company:
            stmt = stmt.join(Job.company).where(func.lower(Company.name) == flt.company.lower())
        if flt.country:
            stmt = stmt.where(func.lower(Job.country) == flt.country.lower())
        if flt.city:
            stmt = stmt.where(func.lower(Job.city) == flt.city.lower())
        if flt.remote_status:
            stmt = stmt.where(Job.remote_status == flt.remote_status)
        if flt.category:
            stmt = stmt.where(func.lower(Job.category) == flt.category.lower())
        if flt.min_salary is not None:
            stmt = stmt.where(Job.salary_max >= flt.min_salary)
        if flt.skill:
            stmt = stmt.join(Job.skills).where(func.lower(Skill.name) == flt.skill.lower())
        return stmt

    def _apply_sort(self, stmt, sort: str):
        descending = sort.startswith("-")
        field = sort.lstrip("-")
        column = {
            "posted_at": Job.posted_at,
            "salary_max": Job.salary_max,
            "created_at": Job.created_at,
            "title": Job.title,
        }.get(field, Job.posted_at)
        return stmt.order_by(column.desc() if descending else column.asc())

    def search(self, flt: JobFilter) -> tuple[Sequence[Job], int]:
        base = select(Job).options(selectinload(Job.company), selectinload(Job.skills))
        base = self._apply_filter(base, flt)

        count_stmt = self._apply_filter(select(func.count(func.distinct(Job.id))), flt)
        total = int(self.session.scalar(count_stmt) or 0)

        base = self._apply_sort(base, flt.sort).limit(flt.limit).offset(flt.offset)
        rows = self.session.scalars(base).unique().all()
        return rows, total

    def all_for_index(self) -> Sequence[Job]:
        stmt = select(Job).options(selectinload(Job.skills), selectinload(Job.company))
        return self.session.scalars(stmt).unique().all()

    def count(self) -> int:
        return int(self.session.scalar(select(func.count()).select_from(Job)) or 0)


class ResumeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, *, user_id: int, text: str, filename: str | None, years: int | None) -> Resume:
        resume = Resume(user_id=user_id, text=text, filename=filename, years_experience=years)
        self.session.add(resume)
        self.session.flush()
        return resume


class CrawlJobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, source: str) -> CrawlJob:
        job = CrawlJob(source=source)
        self.session.add(job)
        self.session.flush()
        return job

    def recent(self, limit: int = 20) -> Sequence[CrawlJob]:
        stmt = select(CrawlJob).order_by(CrawlJob.created_at.desc()).limit(limit)
        return self.session.scalars(stmt).all()
