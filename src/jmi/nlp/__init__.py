"""NLP pipeline: text cleaning, skill/technology extraction, dedup, resumes."""

from .cleaner import clean_text, normalize_whitespace
from .dedup import DuplicateDetector, jaccard_similarity
from .resume import ResumeProfile, parse_resume
from .skills import SkillExtractor, get_default_extractor

__all__ = [
    "DuplicateDetector",
    "ResumeProfile",
    "SkillExtractor",
    "clean_text",
    "get_default_extractor",
    "jaccard_similarity",
    "normalize_whitespace",
    "parse_resume",
]
