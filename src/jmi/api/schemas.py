"""Pydantic request/response schemas (the API contract)."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field

from ..domain.enums import ExportFormat, UserRole


# -- Auth -------------------------------------------------------------------
class RegisterRequest(BaseModel):
    # NOTE: role is intentionally NOT accepted here. Public self-registration
    # always yields a 'viewer'; privileged roles are granted only via the seed
    # bootstrap or an admin-only endpoint, preventing privilege escalation.
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    role: UserRole
    is_active: bool


# -- Jobs -------------------------------------------------------------------
class SkillOut(BaseModel):
    name: str
    kind: str


class JobSummary(BaseModel):
    id: int
    title: str
    company: str | None = None
    country: str | None = None
    city: str | None = None
    remote_status: str
    seniority: str
    category: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    currency: str | None = None
    posted_at: str | None = None
    skills: list[SkillOut] = []


class JobDetail(JobSummary):
    source: str
    external_id: str
    url: str | None = None
    description: str = ""
    company_industry: str | None = None
    company_size: str | None = None
    employment_type: str


class PaginatedJobs(BaseModel):
    items: list[JobSummary]
    total: int
    limit: int
    offset: int


# -- Search -----------------------------------------------------------------
class SemanticSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=10, ge=1, le=50)


class SearchHitOut(JobSummary):
    score: float


# -- Recommendations --------------------------------------------------------
class RecommendRequest(BaseModel):
    resume_text: str = Field(min_length=20, max_length=50_000)
    top_k: int = Field(default=10, ge=1, le=50)


# -- Crawler ----------------------------------------------------------------
class IngestRequest(BaseModel):
    source: str = Field(min_length=1, max_length=64)
    since: str | None = None
    limit: int | None = Field(default=None, ge=1, le=10_000)


class CrawlJobOut(BaseModel):
    id: int
    source: str
    status: str
    fetched: int
    unique_count: int
    duplicates: int
    error: str | None = None


class SourceOut(BaseModel):
    name: str
    display_name: str
    base_url: str
    requires_javascript: bool


# -- Export -----------------------------------------------------------------
class ExportQuery(BaseModel):
    format: ExportFormat = ExportFormat.csv


# -- Errors -----------------------------------------------------------------
class ErrorResponse(BaseModel):
    error: str
    detail: str
