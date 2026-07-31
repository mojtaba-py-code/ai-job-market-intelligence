"""Enumerations shared across the domain."""

from __future__ import annotations

from enum import Enum


class EmploymentType(str, Enum):
    full_time = "full_time"
    part_time = "part_time"
    contract = "contract"
    temporary = "temporary"
    internship = "internship"
    freelance = "freelance"
    unknown = "unknown"


class RemoteStatus(str, Enum):
    remote = "remote"
    hybrid = "hybrid"
    on_site = "on_site"
    unknown = "unknown"


class SeniorityLevel(str, Enum):
    intern = "intern"
    junior = "junior"
    mid = "mid"
    senior = "senior"
    lead = "lead"
    principal = "principal"
    manager = "manager"
    unknown = "unknown"


class SkillKind(str, Enum):
    """Category of an extracted skill token, used for analytics rollups."""

    language = "language"
    framework = "framework"
    database = "database"
    cloud = "cloud"
    tool = "tool"
    concept = "concept"
    soft = "soft"


class UserRole(str, Enum):
    admin = "admin"
    analyst = "analyst"
    viewer = "viewer"


class CrawlJobStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class ExportFormat(str, Enum):
    csv = "csv"
    json = "json"
    excel = "excel"
