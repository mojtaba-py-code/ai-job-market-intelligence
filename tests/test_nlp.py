"""Tests for the NLP pipeline: cleaning, skills, dedup, resume."""

from __future__ import annotations

from jmi.domain.entities import JobPosting, Location
from jmi.domain.enums import SkillKind
from jmi.nlp import (
    DuplicateDetector,
    clean_text,
    get_default_extractor,
    jaccard_similarity,
    parse_resume,
)
from jmi.nlp.skills import SkillExtractor


def test_clean_text_strips_html_and_whitespace():
    dirty = "<p>Hello&nbsp;&amp;   welcome</p>\n\n\n<b>World</b>"
    assert clean_text(dirty) == "Hello & welcome World"


def test_clean_text_keep_newlines_collapses_blank_runs():
    text = "Line one\n\n\n\nLine two"
    assert clean_text(text, keep_newlines=True) == "Line one\n\nLine two"


def test_skill_extractor_finds_technologies():
    extractor = get_default_extractor()
    text = "We use Python, FastAPI and PostgreSQL, deploy on AWS with Docker."
    names = {s.name for s in extractor.extract(text)}
    assert {"Python", "FastAPI", "PostgreSQL", "AWS", "Docker"} <= names


def test_skill_extractor_handles_symbol_tokens():
    extractor = get_default_extractor()
    names = {s.name for s in extractor.extract("Strong C++, C# and .NET background")}
    assert {"C++", "C#", ".NET"} <= names


def test_skill_extractor_word_boundaries():
    extractor = get_default_extractor()
    # 'Gopher' must not match 'Go'; 'javascripting' must not match 'js'.
    names = {s.name for s in extractor.extract("A gopher wrote some prose.")}
    assert "Go" not in names


def test_skill_extractor_prefers_longer_alias():
    extractor = get_default_extractor()
    names = {s.name for s in extractor.extract("Experience with SQL Server required")}
    assert "SQL Server" in names


def test_skill_extractor_deduplicates():
    extractor = get_default_extractor()
    skills = extractor.extract("python python PYTHON")
    assert [s.name for s in skills] == ["Python"]


def test_extract_by_kind_groups_correctly():
    extractor = get_default_extractor()
    grouped = extractor.extract_by_kind("Python and PostgreSQL and AWS")
    assert grouped[SkillKind.language] == ["Python"]
    assert grouped[SkillKind.database] == ["PostgreSQL"]
    assert grouped[SkillKind.cloud] == ["AWS"]


def _posting(title: str, company: str, desc: str, city: str = "NYC") -> JobPosting:
    return JobPosting(
        source="t",
        external_id=title,
        title=title,
        company=company,
        description=desc,
        location=Location(city=city, country="US"),
    )


def test_jaccard_similarity_bounds():
    assert jaccard_similarity("a b c", "a b c") == 1.0
    assert jaccard_similarity("a b c", "x y z") == 0.0
    assert 0.0 < jaccard_similarity("a b c d", "a b x y") < 1.0


def test_duplicate_detector_exact_hash():
    detector = DuplicateDetector()
    p1 = _posting("Engineer", "Acme", "Build things with python")
    p2 = _posting("Engineer", "Acme", "Build things with python")
    assert detector.is_duplicate(p1) is False
    detector.add(p1)
    assert detector.is_duplicate(p2) is True


def test_duplicate_detector_near_duplicate_same_company():
    detector = DuplicateDetector(similarity_threshold=0.6)
    p1 = _posting("Backend Engineer", "Acme", "Build scalable APIs with python and fastapi")
    p2 = _posting("Backend Engineer", "Acme", "Build scalable APIs with python and fastapi today")
    detector.add(p1)
    assert detector.is_duplicate(p2) is True


def test_duplicate_detector_different_company_not_duplicate():
    detector = DuplicateDetector(similarity_threshold=0.6)
    p1 = _posting("Backend Engineer", "Acme", "Build scalable APIs with python")
    p2 = _posting("Backend Engineer", "Globex", "Build scalable APIs with python")
    detector.add(p1)
    assert detector.is_duplicate(p2) is False


def test_filter_unique_keeps_first():
    detector = DuplicateDetector()
    postings = [
        _posting("A", "Acme", "same text here"),
        _posting("A", "Acme", "same text here"),
        _posting("B", "Globex", "different"),
    ]
    unique = detector.filter_unique(postings)
    assert len(unique) == 2


def test_parse_resume_extracts_skills_and_experience():
    resume = """
    Jane Doe — jane@example.com
    Senior Engineer with 7 years of experience.
    Skills: Python, FastAPI, PostgreSQL, Docker, AWS.
    """
    profile = parse_resume(resume)
    assert profile.email == "jane@example.com"
    assert profile.years_experience == 7
    assert {"Python", "FastAPI", "PostgreSQL"} <= profile.skill_set


def test_custom_taxonomy_extractor():
    from jmi.nlp.taxonomy import Taxonomy

    extractor = SkillExtractor(Taxonomy())
    assert any(s.kind is SkillKind.framework for s in extractor.extract("django app"))
