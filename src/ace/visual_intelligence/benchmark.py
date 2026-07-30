from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from importlib.resources import files
from typing import Any

import yaml

from ace.visual_intelligence.intent import deterministic_intent


@dataclass(slots=True)
class BenchmarkCase:
    id: str
    topic: str
    narration: str
    purpose: str
    mood: str
    expected_formats: list[str]
    expected_subject_terms: list[str]
    required_elements: list[str]
    forbidden_elements: list[str]
    forbidden_primary_formats: list[str]


@dataclass(slots=True)
class BenchmarkResult:
    id: str
    passed: bool
    score: float
    problems: list[str]
    intent: dict[str, Any]


def fixture_root() -> Path:
    # Source checkout and wheel installations both include package data only for
    # ace.data, so the CLI can also accept an explicit fixture directory. The
    # repository benchmark lives at project_root/benchmarks.
    return Path(__file__).resolve().parents[3] / "benchmarks" / "visual_intelligence"


def load_cases(root: str | Path | None = None) -> list[BenchmarkCase]:
    output: list[BenchmarkCase] = []
    documents: list[str] = []
    if root:
        directory = Path(root)
        documents.extend(path.read_text(encoding="utf-8") for path in sorted(directory.glob("*.yaml")))
    else:
        directory = fixture_root()
        if directory.exists():
            documents.extend(path.read_text(encoding="utf-8") for path in sorted(directory.glob("*.yaml")))
        if not documents:
            documents.append(files("ace.data").joinpath("visual_benchmarks.yaml").read_text(encoding="utf-8"))
    for document in documents:
        data = yaml.safe_load(document) or {}
        rows = data.get("cases", []) if isinstance(data, dict) else []
        for row in rows:
            output.append(
                BenchmarkCase(
                    id=str(row["id"]),
                    topic=str(row.get("topic") or ""),
                    narration=str(row["narration"]),
                    purpose=str(row.get("purpose") or "support"),
                    mood=str(row.get("mood") or "technical_dynamic"),
                    expected_formats=[str(item) for item in row.get("expected_formats", [])],
                    expected_subject_terms=[str(item) for item in row.get("expected_subject_terms", [])],
                    required_elements=[str(item) for item in row.get("required_elements", [])],
                    forbidden_elements=[str(item) for item in row.get("forbidden_elements", [])],
                    forbidden_primary_formats=[str(item) for item in row.get("forbidden_primary_formats", [])],
                )
            )
    return output


def evaluate(case: BenchmarkCase) -> BenchmarkResult:
    intent = deterministic_intent(
        case.narration,
        shot_id=case.id,
        purpose=case.purpose,
        mood=case.mood,
        topic=case.topic,
        caption_strategy="short_phrase",
    )
    problems: list[str] = []
    points = 0.0
    total = 5.0
    top_formats = intent.preferred_formats[:3]
    if not case.expected_formats or any(item in top_formats for item in case.expected_formats):
        points += 1
    else:
        problems.append(f"Expected one of {case.expected_formats} in top formats, got {top_formats}.")
    primary = intent.preferred_formats[0] if intent.preferred_formats else ""
    if primary not in case.forbidden_primary_formats:
        points += 1
    else:
        problems.append(f"Forbidden primary format selected: {primary}.")
    subject = intent.subject.lower()
    if not case.expected_subject_terms or any(term.lower() in subject for term in case.expected_subject_terms):
        points += 1
    else:
        problems.append(f"Subject {intent.subject!r} lacks expected terms {case.expected_subject_terms}.")
    missing_required = [item for item in case.required_elements if item not in intent.required_elements]
    if not missing_required:
        points += 1
    else:
        problems.append("Missing required elements: " + ", ".join(missing_required) + ".")
    missing_forbidden = [item for item in case.forbidden_elements if item not in intent.forbidden_elements]
    if not missing_forbidden:
        points += 1
    else:
        problems.append("Planner did not reject: " + ", ".join(missing_forbidden) + ".")
    score = round(points / total * 100, 2)
    return BenchmarkResult(case.id, score >= 80 and not problems, score, problems, intent.to_dict())


def run(root: str | Path | None = None) -> dict[str, Any]:
    cases = load_cases(root)
    results = [evaluate(case) for case in cases]
    score = sum(item.score for item in results) / max(1, len(results))
    return {
        "status": "passed" if results and all(item.passed for item in results) else "failed" if results else "not_run",
        "case_count": len(results),
        "passed_count": sum(item.passed for item in results),
        "average_score": round(score, 2),
        "results": [
            {"id": item.id, "passed": item.passed, "score": item.score, "problems": item.problems, "intent": item.intent}
            for item in results
        ],
    }
