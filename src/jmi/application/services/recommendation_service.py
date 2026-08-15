"""Resume matching & recommendation use-case.

Given a resume, the service:

* parses skills and experience (NLP layer),
* scores every job by a blend of **skill overlap** and **semantic similarity**,
* returns the best matches with a per-job *match score* and *missing skills*,
* aggregates a **learning roadmap** (most in-demand missing skills),
* predicts a **salary band** from comparable matched roles, and
* suggests **career directions** from the categories of the top matches.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from statistics import median

from sqlalchemy.orm import Session

from ...nlp.resume import parse_resume
from .search_service import SearchService

# Blend weights: how much skill overlap vs. semantic similarity contribute.
_SKILL_WEIGHT = 0.7
_SEMANTIC_WEIGHT = 0.3


@dataclass(slots=True)
class JobMatch:
    job_id: int
    title: str
    company: str | None
    score: float
    matched_skills: list[str]
    missing_skills: list[str]


@dataclass(slots=True)
class RecommendationResult:
    resume_skills: list[str]
    years_experience: int | None
    matches: list[JobMatch] = field(default_factory=list)
    learning_roadmap: list[dict] = field(default_factory=list)
    salary_prediction: dict | None = None
    career_suggestions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "resume_skills": self.resume_skills,
            "years_experience": self.years_experience,
            "matches": [
                {
                    "job_id": m.job_id,
                    "title": m.title,
                    "company": m.company,
                    "score": m.score,
                    "matched_skills": m.matched_skills,
                    "missing_skills": m.missing_skills,
                }
                for m in self.matches
            ],
            "learning_roadmap": self.learning_roadmap,
            "salary_prediction": self.salary_prediction,
            "career_suggestions": self.career_suggestions,
        }


class RecommendationService:
    def __init__(self, session: Session) -> None:
        self.session = session
        # No explicit index: sharing the process-wide cached one keeps a resume
        # match from rebuilding the corpus embedding on every call.
        self._search = SearchService(session)

    def recommend(self, resume_text: str, *, top_k: int = 10) -> RecommendationResult:
        profile = parse_resume(resume_text)
        resume_skills = set(profile.skills)

        from ...infrastructure.db.repositories import JobRepository

        jobs = JobRepository(self.session).all_for_index()
        if not jobs:
            return RecommendationResult(
                resume_skills=sorted(resume_skills),
                years_experience=profile.years_experience,
            )

        # Semantic similarity between the resume and each job.
        semantic_scores = {
            hit["id"]: hit["score"]
            for hit in self._search.search(" ".join(profile.skills) or resume_text, top_k=len(jobs))
        }

        matches: list[JobMatch] = []
        missing_counter: Counter[str] = Counter()
        for job in jobs:
            required = {s.name for s in job.skills}
            if not required:
                continue
            matched = required & resume_skills
            missing = required - resume_skills
            skill_score = len(matched) / len(required)
            semantic = semantic_scores.get(job.id, 0.0)
            score = _SKILL_WEIGHT * skill_score + _SEMANTIC_WEIGHT * semantic
            for skill in missing:
                missing_counter[skill] += 1
            matches.append(
                JobMatch(
                    job_id=job.id,
                    title=job.title,
                    company=job.company.name if job.company else None,
                    score=round(score, 4),
                    matched_skills=sorted(matched),
                    missing_skills=sorted(missing),
                )
            )

        matches.sort(key=lambda m: m.score, reverse=True)
        top_matches = matches[:top_k]

        return RecommendationResult(
            resume_skills=sorted(resume_skills),
            years_experience=profile.years_experience,
            matches=top_matches,
            learning_roadmap=self._roadmap(missing_counter),
            salary_prediction=self._predict_salary(jobs, top_matches),
            career_suggestions=self._career_suggestions(jobs, top_matches),
        )

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _roadmap(missing_counter: Counter[str]) -> list[dict]:
        return [
            {"skill": skill, "demand": count} for skill, count in missing_counter.most_common(10)
        ]

    def _predict_salary(self, jobs, top_matches: list[JobMatch]) -> dict | None:
        match_ids = {m.job_id for m in top_matches}
        by_currency: dict[str, list[float]] = {}
        for job in jobs:
            if job.id not in match_ids or not job.currency:
                continue
            mids = [v for v in (job.salary_min, job.salary_max) if v is not None]
            if mids:
                by_currency.setdefault(job.currency, []).append(sum(mids) / len(mids))
        if not by_currency:
            return None
        currency, values = max(by_currency.items(), key=lambda kv: len(kv[1]))
        return {
            "currency": currency,
            "expected_min": round(min(values), 2),
            "expected_median": round(median(values), 2),
            "expected_max": round(max(values), 2),
            "based_on": len(values),
        }

    @staticmethod
    def _career_suggestions(jobs, top_matches: list[JobMatch]) -> list[str]:
        match_ids = {m.job_id for m in top_matches}
        categories = Counter(job.category for job in jobs if job.id in match_ids and job.category)
        return [category for category, _ in categories.most_common(5)]
