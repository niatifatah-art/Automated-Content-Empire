from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


class _ValueEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class VisualPurpose(_ValueEnum):
    HOOK = "hook"
    ESTABLISH_CONTEXT = "establish_context"
    EXPLAIN_MECHANISM = "explain_mechanism"
    SHOW_EVIDENCE = "show_evidence"
    DEMONSTRATE = "demonstrate"
    COMPARE = "compare"
    SHOW_DATA = "show_data"
    REACTION = "reaction"
    CHALLENGE_PROGRESS = "challenge_progress"
    CALL_TO_ACTION = "call_to_action"
    SUPPORT = "support"


class VisualFormat(_ValueEnum):
    OFFICIAL_EVIDENCE = "official_evidence"
    BROWSER_DEMO = "browser_demo"
    TERMINAL_DEMO = "terminal_demo"
    APPLICATION_DEMO = "application_demo"
    ANIMATED_EXPLAINER = "animated_explainer"
    GENERATED_CONCEPT_IMAGE = "generated_concept_image"
    ARTICLE_CARD = "article_card"
    SOCIAL_POST_CARD = "social_post_card"
    DATA_CHART = "data_chart"
    COMPARISON_GRAPHIC = "comparison_graphic"
    TIMELINE = "timeline"
    MEME = "meme"
    ACCOUNT_ASSET = "account_asset"
    STOCK_VIDEO = "stock_video"
    STOCK_IMAGE = "stock_image"
    KINETIC_TYPOGRAPHY = "kinetic_typography"
    MINIMAL_SCREEN = "minimal_screen"


class CandidateOrigin(_ValueEnum):
    OFFICIAL_CAPTURE = "official_capture"
    ACCOUNT_OWNED = "account_owned"
    ACE_GENERATED = "ace_generated"
    AI_GENERATED = "ai_generated"
    LICENSED_STOCK = "licensed_stock"
    ATTRIBUTION_REQUIRED = "attribution_required"
    REFERENCE_ONLY = "reference_only"
    SIMULATED = "simulated"
    PLACEHOLDER = "placeholder"


class DecisionStatus(_ValueEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NEEDS_APPROVAL = "needs_approval"
    FALLBACK = "fallback"


def _enum_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [_enum_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _enum_value(item) for key, item in value.items()}
    return value


@dataclass(slots=True)
class ShotIntent:
    shot_id: str
    narration: str
    purpose: str = VisualPurpose.SUPPORT.value
    subject: str = "general_topic"
    mood: str = "technical_dynamic"
    importance: float = 0.5
    preferred_formats: list[str] = field(default_factory=lambda: [VisualFormat.STOCK_VIDEO.value])
    required_elements: list[str] = field(default_factory=list)
    forbidden_elements: list[str] = field(default_factory=list)
    search_queries: dict[str, list[str]] = field(default_factory=dict)
    caption_strategy: str = "short_phrase"
    evidence_required: bool = False
    humor_allowed: bool = False
    literalness: str = "mixed"
    rationale: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.importance = max(0.0, min(1.0, float(self.importance)))
        self.preferred_formats = _unique_strings(self.preferred_formats)
        self.required_elements = _unique_strings(self.required_elements)
        self.forbidden_elements = _unique_strings(self.forbidden_elements)
        self.search_queries = {
            str(key): _unique_strings(value if isinstance(value, list) else [str(value)])
            for key, value in (self.search_queries or {}).items()
        }

    def to_dict(self) -> dict[str, Any]:
        return _enum_value(asdict(self))

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "ShotIntent":
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{key: value for key, value in row.items() if key in allowed})


@dataclass(slots=True)
class VisualCandidate:
    candidate_id: str
    shot_id: str
    format: str
    provider: str
    title: str
    description: str = ""
    path: str | None = None
    source_url: str | None = None
    download_url: str | None = None
    origin: str = CandidateOrigin.ACE_GENERATED.value
    license_status: str = "account_owned"
    tags: list[str] = field(default_factory=list)
    semantic_elements: list[str] = field(default_factory=list)
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    generation_cost_usd: float = 0.0
    generation_time_seconds: float = 0.0
    approval_required: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.tags = _unique_strings(self.tags)
        self.semantic_elements = _unique_strings(self.semantic_elements)
        self.generation_cost_usd = max(0.0, float(self.generation_cost_usd or 0.0))
        self.generation_time_seconds = max(0.0, float(self.generation_time_seconds or 0.0))

    @property
    def is_local(self) -> bool:
        return bool(self.path and Path(self.path).expanduser().exists())

    @property
    def aspect_ratio(self) -> float | None:
        if self.width and self.height:
            return self.width / self.height
        return None

    def searchable_text(self) -> str:
        return " ".join([self.title, self.description, *self.tags, *self.semantic_elements]).strip()

    def to_dict(self) -> dict[str, Any]:
        return _enum_value(asdict(self))

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "VisualCandidate":
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{key: value for key, value in row.items() if key in allowed})


@dataclass(slots=True)
class VisualScore:
    candidate_id: str
    shot_id: str
    semantic_relevance: float
    clarity: float
    required_element_coverage: float
    vertical_fit: float
    style_match: float
    truthfulness: float
    visual_quality: float
    provenance_confidence: float
    duplicate_risk: float
    overall: float
    decision: str
    forbidden_violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)
    judge: str = "deterministic"
    schema_version: int = 1

    def __post_init__(self) -> None:
        for name in (
            "semantic_relevance",
            "clarity",
            "required_element_coverage",
            "vertical_fit",
            "style_match",
            "truthfulness",
            "visual_quality",
            "provenance_confidence",
            "duplicate_risk",
            "overall",
        ):
            setattr(self, name, max(0.0, min(100.0, float(getattr(self, name)))))

    def to_dict(self) -> dict[str, Any]:
        return _enum_value(asdict(self))

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "VisualScore":
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{key: value for key, value in row.items() if key in allowed})


@dataclass(slots=True)
class VisualDecision:
    shot_id: str
    selected_candidate_id: str
    status: str
    score: float
    reason: str
    candidate_count: int
    rejected_candidate_ids: list[str] = field(default_factory=list)
    approval_required: bool = False
    selected_path: str | None = None
    selected_format: str | None = None
    selected_origin: str | None = None
    selected_provider: str | None = None
    replacement_history: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return _enum_value(asdict(self))

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "VisualDecision":
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{key: value for key, value in row.items() if key in allowed})


@dataclass(slots=True)
class VisualValidationReport:
    status: str
    shot_count: int
    accepted_count: int
    warning_count: int
    rejected_count: int
    missing_count: int
    average_relevance: float
    average_overall: float
    generic_filler_ratio: float
    unexplained_decisions: int
    duplicate_count: int
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    per_shot: list[dict[str, Any]] = field(default_factory=list)
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return _enum_value(asdict(self))


def _unique_strings(values: Iterable[Any]) -> list[str]:
    output: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in output:
            output.append(normalized)
    return output
