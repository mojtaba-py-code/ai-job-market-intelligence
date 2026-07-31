"""Curated technology & skill taxonomy.

The taxonomy is the backbone of skill extraction and analytics. Each canonical
skill maps to a :class:`~jmi.domain.enums.SkillKind` and a set of case-insensitive
aliases. The default taxonomy below can be extended at runtime via an external
JSON file (see :func:`load_taxonomy`).

Keeping this rule-based table means extraction is deterministic, explainable and
runs without downloading multi-gigabyte models — while the optional spaCy backend
(``jmi.nlp.skills``) can enrich it when installed.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..domain.enums import SkillKind

# Canonical name -> (kind, aliases). Aliases are matched case-insensitively with
# word boundaries so "R" or "Go" do not match inside other words.
_DEFAULT_TAXONOMY: dict[str, tuple[SkillKind, tuple[str, ...]]] = {
    # -- Programming languages ---------------------------------------------
    "Python": (SkillKind.language, ("python", "py3", "python3")),
    "JavaScript": (SkillKind.language, ("javascript", "js", "ecmascript")),
    "TypeScript": (SkillKind.language, ("typescript", "ts")),
    "Java": (SkillKind.language, ("java",)),
    "C#": (SkillKind.language, ("c#", "csharp", "c sharp")),
    "C++": (SkillKind.language, ("c++", "cpp")),
    "C": (SkillKind.language, ("c language", "ansi c")),
    "Go": (SkillKind.language, ("golang", "go lang")),
    "Rust": (SkillKind.language, ("rust",)),
    "Ruby": (SkillKind.language, ("ruby",)),
    "PHP": (SkillKind.language, ("php",)),
    "Swift": (SkillKind.language, ("swift",)),
    "Kotlin": (SkillKind.language, ("kotlin",)),
    "Scala": (SkillKind.language, ("scala",)),
    "R": (SkillKind.language, ("rlang", "r language")),
    "SQL": (SkillKind.language, ("sql",)),
    "Bash": (SkillKind.language, ("bash", "shell scripting")),
    # -- Frameworks / libraries --------------------------------------------
    "FastAPI": (SkillKind.framework, ("fastapi",)),
    "Django": (SkillKind.framework, ("django",)),
    "Flask": (SkillKind.framework, ("flask",)),
    "React": (SkillKind.framework, ("react", "react.js", "reactjs")),
    "Vue.js": (SkillKind.framework, ("vue", "vue.js", "vuejs")),
    "Angular": (SkillKind.framework, ("angular", "angularjs")),
    "Node.js": (SkillKind.framework, ("node", "node.js", "nodejs")),
    "Express": (SkillKind.framework, ("express", "express.js")),
    "Spring": (SkillKind.framework, ("spring", "spring boot")),
    ".NET": (SkillKind.framework, (".net", "dotnet", "asp.net")),
    "TensorFlow": (SkillKind.framework, ("tensorflow", "tf")),
    "PyTorch": (SkillKind.framework, ("pytorch", "torch")),
    "scikit-learn": (SkillKind.framework, ("scikit-learn", "sklearn", "scikit learn")),
    "Pandas": (SkillKind.framework, ("pandas",)),
    "NumPy": (SkillKind.framework, ("numpy",)),
    "Next.js": (SkillKind.framework, ("next.js", "nextjs")),
    # -- Databases ----------------------------------------------------------
    "PostgreSQL": (SkillKind.database, ("postgresql", "postgres", "psql")),
    "MySQL": (SkillKind.database, ("mysql",)),
    "SQLite": (SkillKind.database, ("sqlite",)),
    "MongoDB": (SkillKind.database, ("mongodb", "mongo")),
    "Redis": (SkillKind.database, ("redis",)),
    "Elasticsearch": (SkillKind.database, ("elasticsearch", "elastic search")),
    "Cassandra": (SkillKind.database, ("cassandra",)),
    "Oracle": (SkillKind.database, ("oracle db", "oracle database")),
    "SQL Server": (SkillKind.database, ("sql server", "mssql")),
    "DynamoDB": (SkillKind.database, ("dynamodb",)),
    "Snowflake": (SkillKind.database, ("snowflake",)),
    # -- Cloud providers ----------------------------------------------------
    "AWS": (SkillKind.cloud, ("aws", "amazon web services")),
    "Azure": (SkillKind.cloud, ("azure", "microsoft azure")),
    "GCP": (SkillKind.cloud, ("gcp", "google cloud", "google cloud platform")),
    "DigitalOcean": (SkillKind.cloud, ("digitalocean", "digital ocean")),
    "Heroku": (SkillKind.cloud, ("heroku",)),
    # -- Tools / DevOps -----------------------------------------------------
    "Docker": (SkillKind.tool, ("docker",)),
    "Kubernetes": (SkillKind.tool, ("kubernetes", "k8s")),
    "Terraform": (SkillKind.tool, ("terraform",)),
    "Git": (SkillKind.tool, ("git", "github", "gitlab")),
    "CI/CD": (SkillKind.tool, ("ci/cd", "cicd", "continuous integration")),
    "Kafka": (SkillKind.tool, ("kafka", "apache kafka")),
    "RabbitMQ": (SkillKind.tool, ("rabbitmq",)),
    "Celery": (SkillKind.tool, ("celery",)),
    "Airflow": (SkillKind.tool, ("airflow", "apache airflow")),
    "Spark": (SkillKind.tool, ("spark", "apache spark", "pyspark")),
    "Jenkins": (SkillKind.tool, ("jenkins",)),
    "GraphQL": (SkillKind.tool, ("graphql",)),
    "REST API": (SkillKind.tool, ("rest", "rest api", "restful")),
    "gRPC": (SkillKind.tool, ("grpc",)),
    # -- Concepts -----------------------------------------------------------
    "Machine Learning": (SkillKind.concept, ("machine learning", "ml")),
    "Deep Learning": (SkillKind.concept, ("deep learning",)),
    "NLP": (SkillKind.concept, ("nlp", "natural language processing")),
    "Data Engineering": (SkillKind.concept, ("data engineering", "etl", "elt")),
    "Microservices": (SkillKind.concept, ("microservices", "microservice")),
    "Agile": (SkillKind.concept, ("agile", "scrum", "kanban")),
    "TDD": (SkillKind.concept, ("tdd", "test driven development")),
    # -- Soft skills --------------------------------------------------------
    "Communication": (SkillKind.soft, ("communication skills",)),
    "Leadership": (SkillKind.soft, ("leadership",)),
    "Problem Solving": (SkillKind.soft, ("problem solving", "problem-solving")),
    "Teamwork": (SkillKind.soft, ("teamwork", "team player")),
}


class Taxonomy:
    """An immutable-ish lookup of canonical skills and their aliases."""

    def __init__(self, table: dict[str, tuple[SkillKind, tuple[str, ...]]] | None = None) -> None:
        self._table = dict(table or _DEFAULT_TAXONOMY)

    def __len__(self) -> int:
        return len(self._table)

    def items(self):
        return self._table.items()

    def kind_of(self, canonical: str) -> SkillKind:
        entry = self._table.get(canonical)
        return entry[0] if entry else SkillKind.concept

    def alias_map(self) -> dict[str, str]:
        """Return alias (lower) -> canonical name for every alias and name."""
        mapping: dict[str, str] = {}
        for canonical, (_, aliases) in self._table.items():
            mapping[canonical.lower()] = canonical
            for alias in aliases:
                mapping[alias.lower()] = canonical
        return mapping

    def merge(self, extra: dict[str, tuple[SkillKind, tuple[str, ...]]]) -> None:
        self._table.update(extra)


def load_taxonomy(path: str | Path | None = None) -> Taxonomy:
    """Load the default taxonomy, optionally merged with a JSON override file.

    The JSON format is ``{"Canonical Name": {"kind": "framework",
    "aliases": ["alias1", "alias2"]}}``.
    """
    taxonomy = Taxonomy()
    if path is None:
        return taxonomy

    file_path = Path(path)
    if not file_path.exists():
        return taxonomy

    raw = json.loads(file_path.read_text(encoding="utf-8"))
    extra: dict[str, tuple[SkillKind, tuple[str, ...]]] = {}
    for name, spec in raw.items():
        kind = SkillKind(spec.get("kind", "concept"))
        aliases = tuple(spec.get("aliases", []))
        extra[name] = (kind, aliases)
    taxonomy.merge(extra)
    return taxonomy
