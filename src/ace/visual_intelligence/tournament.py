from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Iterable

from ace.config import load as load_config
from ace.storage import metadata, resolve_generation
from ace.state import approve as record_approval, event as state_event
from ace.media_fingerprint import fingerprint_bundle, tokens as fingerprint_tokens
from ace.utils import ensure_dir, read_json, write_json
from ace.visual_intelligence.candidates import (
    copy_local_candidate,
    evidence_candidates,
    explainer_candidate,
    generated_concept_candidate,
    materialize,
    meme_candidate,
    stock_candidates,
    typography_candidate,
)
from ace.visual_intelligence.contracts import (
    CandidateOrigin,
    DecisionStatus,
    ShotIntent,
    VisualCandidate,
    VisualDecision,
    VisualFormat,
    VisualScore,
    VisualValidationReport,
)
from ace.visual_intelligence.judge import judge_candidate
from ace.visual_intelligence.scoring import score_candidate


ACE_RENDERABLE_FORMATS = {
    VisualFormat.ANIMATED_EXPLAINER.value,
    VisualFormat.COMPARISON_GRAPHIC.value,
    VisualFormat.DATA_CHART.value,
    VisualFormat.TIMELINE.value,
    VisualFormat.TERMINAL_DEMO.value,
    VisualFormat.APPLICATION_DEMO.value,
    VisualFormat.BROWSER_DEMO.value,
}


def _settings(workspace: str | Path | None) -> dict[str, Any]:
    config = load_config(workspace)
    return config.get("visual_intelligence", {})


def _thresholds(workspace: str | Path | None) -> dict[str, Any]:
    settings = _settings(workspace)
    return dict(settings.get("acceptance", {}))


def _candidate_paths(folder: Path, shot_id: str) -> tuple[Path, Path]:
    root = ensure_dir(folder / "visuals" / "candidates")
    return root / f"{shot_id}.json", root / f"{shot_id}-scores.json"


def _decision_path(folder: Path) -> Path:
    return folder / "visuals" / "decisions.json"


def load_intents(folder: Path) -> list[ShotIntent]:
    rows = read_json(folder / "visuals" / "shot-intents.json", []) or []
    return [ShotIntent.from_dict(row) for row in rows]



def _save_intent(folder: Path, intent: ShotIntent) -> None:
    rows = load_intents(folder)
    replaced = False
    for index, item in enumerate(rows):
        if item.shot_id == intent.shot_id:
            rows[index] = intent
            replaced = True
            break
    if not replaced:
        rows.append(intent)
    write_json(folder / "visuals" / "shot-intents.json", [item.to_dict() for item in rows])


def load_decisions(folder: Path) -> list[VisualDecision]:
    rows = read_json(_decision_path(folder), []) or []
    return [VisualDecision.from_dict(row) for row in rows]


def load_candidates(folder: Path, shot_id: str) -> tuple[list[VisualCandidate], list[VisualScore]]:
    candidates_path, scores_path = _candidate_paths(folder, shot_id)
    candidates = [VisualCandidate.from_dict(row) for row in (read_json(candidates_path, []) or [])]
    scores = [VisualScore.from_dict(row) for row in (read_json(scores_path, []) or [])]
    return candidates, scores


def _save_candidates(folder: Path, shot_id: str, candidates: list[VisualCandidate], scores: list[VisualScore]) -> None:
    candidates_path, scores_path = _candidate_paths(folder, shot_id)
    write_json(candidates_path, [item.to_dict() for item in candidates])
    write_json(scores_path, [item.to_dict() for item in scores])


def _save_decision(folder: Path, decision: VisualDecision) -> None:
    rows = load_decisions(folder)
    replaced = False
    for index, item in enumerate(rows):
        if item.shot_id == decision.shot_id:
            decision.replacement_history = [*item.replacement_history, *decision.replacement_history]
            rows[index] = decision
            replaced = True
            break
    if not replaced:
        rows.append(decision)
    write_json(_decision_path(folder), [item.to_dict() for item in rows])


def generate_candidates(
    folder: Path,
    intent: ShotIntent,
    *,
    duration: float,
    workspace: str | Path | None = None,
    resource_finder: Callable[..., Any] | None = None,
    animate_explainers: bool = True,
    generate_cloud_images: bool | None = None,
) -> list[VisualCandidate]:
    settings = _settings(workspace)
    candidates: list[VisualCandidate] = []
    candidates.extend(evidence_candidates(folder, intent))

    # Generate more than one ACE-native candidate so the tournament compares
    # genuinely different visual languages instead of rubber-stamping one template.
    requested_ace_formats = [item for item in intent.preferred_formats if item in ACE_RENDERABLE_FORMATS]
    ace_candidate_limit = max(1, int(settings.get("ace_candidates_per_shot", 2)))
    for visual_format in requested_ace_formats[:ace_candidate_limit]:
        candidates.append(
            explainer_candidate(
                folder,
                intent,
                duration,
                animate=animate_explainers,
                visual_format=visual_format,
            )
        )

    generated_settings = load_config(workspace).get("generated_images", {})
    should_generate_image = (
        VisualFormat.GENERATED_CONCEPT_IMAGE.value in intent.preferred_formats
        and bool(generated_settings.get("enabled", True))
        and (bool(generated_settings.get("automatic_for_missing_concepts", True)) if generate_cloud_images is None else generate_cloud_images)
        and not intent.evidence_required
    )
    if should_generate_image:
        try:
            candidates.append(generated_concept_candidate(folder, intent, workspace))
        except Exception as exc:
            intent.metadata.setdefault("candidate_generation_warnings", []).append(f"Cloud concept image unavailable: {exc}")

    generation_meta = metadata(folder)
    meme_mode = str(generation_meta.get("meme_mode") or "auto")
    if VisualFormat.MEME.value in intent.preferred_formats or meme_mode == "on":
        item = meme_candidate(folder, intent, mode=meme_mode)
        if item is not None:
            candidates.append(item)

    if any(item in intent.preferred_formats for item in (VisualFormat.KINETIC_TYPOGRAPHY.value, VisualFormat.MINIMAL_SCREEN.value)):
        candidates.append(typography_candidate(folder, intent, label="HOOK" if intent.purpose == "hook" else "KEY IDEA"))

    finder = resource_finder
    if finder is None:
        from ace.resources import find as finder
    candidates.extend(
        stock_candidates(
            intent,
            workspace,
            finder=finder,
            limit_per_query=int(settings.get("stock_candidates_per_query", 4)),
        )
    )

    # Always retain one intentional ACE-owned fallback. This is not a black or
    # placeholder screen; it uses the exact narration and can be published.
    if not any(item.format == VisualFormat.KINETIC_TYPOGRAPHY.value for item in candidates):
        candidates.append(typography_candidate(folder, intent))

    # Remove duplicates while retaining candidate order.
    seen: set[str] = set()
    output: list[VisualCandidate] = []
    for candidate in candidates:
        key = str(candidate.path or candidate.download_url or candidate.source_url or candidate.candidate_id)
        if key in seen:
            continue
        seen.add(key)
        output.append(candidate)
    maximum = int(settings.get("maximum_candidates_per_shot", 12))
    return output[:maximum]



def _creative_selection_rank(candidate: VisualCandidate, score: VisualScore, intent: ShotIntent, media_mode: str) -> float:
    """Apply a small creative preference without overriding semantic quality."""
    rank = score.overall
    live = candidate.format in {VisualFormat.ACCOUNT_ASSET.value, VisualFormat.STOCK_VIDEO.value}
    explanatory = candidate.format in {
        VisualFormat.ANIMATED_EXPLAINER.value,
        VisualFormat.BROWSER_DEMO.value,
        VisualFormat.APPLICATION_DEMO.value,
        VisualFormat.TERMINAL_DEMO.value,
        VisualFormat.COMPARISON_GRAPHIC.value,
        VisualFormat.DATA_CHART.value,
        VisualFormat.TIMELINE.value,
    }
    evidence = candidate.format in {
        VisualFormat.OFFICIAL_EVIDENCE.value,
        VisualFormat.ARTICLE_CARD.value,
        VisualFormat.SOCIAL_POST_CARD.value,
    }
    if intent.evidence_required:
        if evidence:
            rank += 12
        elif live:
            rank -= 10
        return rank

    literal_beat = intent.literalness in {"literal", "mixed"} and intent.purpose in {
        "hook", "support", "establish_context", "demonstrate", "reaction"
    }
    mechanism = intent.literalness == "abstract_mechanism" or intent.purpose == "explain_mechanism"
    if media_mode == "broll" and literal_beat and live:
        rank += 8 if candidate.format == VisualFormat.ACCOUNT_ASSET.value else 6
    elif media_mode == "auto" and literal_beat and live:
        rank += 3
    if mechanism and explanatory:
        rank += 5
    if mechanism and live:
        rank -= 5
    if candidate.format == VisualFormat.MEME.value:
        rank += 4 if intent.humor_allowed and intent.purpose not in {"show_evidence", "show_data"} else -20
    return rank


def run_tournament(
    folder: Path,
    intent: ShotIntent,
    *,
    duration: float,
    workspace: str | Path | None = None,
    used_fingerprints: set[str] | None = None,
    resource_finder: Callable[..., Any] | None = None,
    cloud_judge: bool | None = None,
    animate_explainers: bool = True,
    generate_cloud_images: bool | None = None,
) -> tuple[VisualCandidate, VisualScore, VisualDecision, list[VisualCandidate], list[VisualScore]]:
    used_fingerprints = used_fingerprints if used_fingerprints is not None else set()
    settings = _settings(workspace)
    thresholds = _thresholds(workspace)
    candidates = generate_candidates(
        folder,
        intent,
        duration=duration,
        workspace=workspace,
        resource_finder=resource_finder,
        animate_explainers=animate_explainers,
        generate_cloud_images=generate_cloud_images,
    )
    _save_intent(folder, intent)
    deterministic_scores = [score_candidate(intent, candidate, used_fingerprints=used_fingerprints, thresholds=thresholds) for candidate in candidates]
    media_mode = str(metadata(folder).get("media_mode") or "auto")
    ranked = sorted(
        zip(candidates, deterministic_scores),
        key=lambda item: _creative_selection_rank(item[0], item[1], intent, media_mode),
        reverse=True,
    )
    judged: list[tuple[VisualCandidate, VisualScore]] = []
    quality_mode = str(metadata(folder).get("quality_mode") or "balanced")
    configured_judge_limit = int(settings.get("cloud_judge_candidate_limit", 3))
    per_quality = settings.get("cloud_judge_candidates_by_quality", {"quick": 0, "balanced": 1, "best": 2})
    judge_limit = min(configured_judge_limit, int(per_quality.get(quality_mode, 1)))

    for rank, (candidate, base_score) in enumerate(ranked):
        current = candidate
        try:
            if rank < judge_limit or base_score.decision in {DecisionStatus.ACCEPTED.value, DecisionStatus.NEEDS_APPROVAL.value}:
                current = materialize(current, folder)
                current = copy_local_candidate(current, folder)
        except Exception as exc:
            base_score.decision = DecisionStatus.REJECTED.value
            base_score.reasoning.append(f"Candidate could not be downloaded or copied: {exc}")
        score = base_score
        if rank < judge_limit and current.is_local:
            score = judge_candidate(intent, current, score, workspace, enabled=cloud_judge)
        judged.append((current, score))

    judged.sort(
        key=lambda item: (
            item[1].decision == DecisionStatus.ACCEPTED.value,
            _creative_selection_rank(item[0], item[1], intent, media_mode),
        ),
        reverse=True,
    )
    accepted = [item for item in judged if item[1].decision == DecisionStatus.ACCEPTED.value]
    needs_approval = [item for item in judged if item[1].decision == DecisionStatus.NEEDS_APPROVAL.value]
    status = DecisionStatus.ACCEPTED.value
    if accepted:
        selected, selected_score = accepted[0]
    elif needs_approval:
        selected, selected_score = needs_approval[0]
        status = DecisionStatus.NEEDS_APPROVAL.value
    else:
        # Prefer a deterministic ACE-owned explainer or typography fallback.
        safe = [
            item
            for item in judged
            if item[0].origin == CandidateOrigin.ACE_GENERATED.value
            and item[0].format in {
                VisualFormat.ANIMATED_EXPLAINER.value,
                VisualFormat.KINETIC_TYPOGRAPHY.value,
                VisualFormat.TERMINAL_DEMO.value,
                VisualFormat.APPLICATION_DEMO.value,
                VisualFormat.BROWSER_DEMO.value,
                VisualFormat.COMPARISON_GRAPHIC.value,
                VisualFormat.DATA_CHART.value,
                VisualFormat.TIMELINE.value,
            }
        ]
        if not safe:
            fallback_format = next((item for item in intent.preferred_formats if item in ACE_RENDERABLE_FORMATS), VisualFormat.ANIMATED_EXPLAINER.value)
            fallback = explainer_candidate(folder, intent, duration, animate=animate_explainers, visual_format=fallback_format)
            fallback_score = score_candidate(intent, fallback, used_fingerprints=used_fingerprints, thresholds={**thresholds, "minimum_relevance": 0, "minimum_clarity": 0, "minimum_vertical_fit": 0, "minimum_truthfulness": 0})
            judged.append((fallback, fallback_score))
            safe = [(fallback, fallback_score)]
        selected, selected_score = max(safe, key=lambda item: item[1].overall)
        status = DecisionStatus.FALLBACK.value
        selected_score.decision = DecisionStatus.FALLBACK.value
        selected_score.reasoning.append("No external candidate passed the strict threshold; ACE selected an original safe visual.")

    if selected.path and Path(selected.path).exists():
        selected.metadata["fingerprint_bundle"] = fingerprint_bundle(selected.path, include_perceptual=True)
        selected.metadata["fingerprint"] = selected.metadata["fingerprint_bundle"].get("sha256")
    fingerprint = str(selected.metadata.get("fingerprint") or selected.path or selected.source_url or selected.candidate_id)
    if fingerprint:
        used_fingerprints.add(f"id:{fingerprint}")
    used_fingerprints.update(fingerprint_tokens(selected.metadata.get("fingerprint_bundle")))

    candidates_by_id = {item.candidate_id: item for item, _ in judged}
    scores_by_id = {item.candidate_id: score for item, score in judged}
    all_candidates = list(candidates_by_id.values())
    all_scores = list(scores_by_id.values())
    _save_candidates(folder, intent.shot_id, all_candidates, all_scores)
    rejected_ids = [score.candidate_id for score in all_scores if score.candidate_id != selected.candidate_id]
    reason = (
        f"Selected {selected.format} from {selected.provider} with {selected_score.overall:.1f}/100. "
        + " ".join(selected_score.reasoning[-3:])
    ).strip()
    decision = VisualDecision(
        shot_id=intent.shot_id,
        selected_candidate_id=selected.candidate_id,
        status=status,
        score=selected_score.overall,
        reason=reason,
        candidate_count=len(all_candidates),
        rejected_candidate_ids=rejected_ids,
        approval_required=status == DecisionStatus.NEEDS_APPROVAL.value or selected.approval_required,
        selected_path=selected.path,
        selected_format=selected.format,
        selected_origin=selected.origin,
        selected_provider=selected.provider,
        metadata={
            "semantic_relevance": selected_score.semantic_relevance,
            "clarity": selected_score.clarity,
            "truthfulness": selected_score.truthfulness,
            "judge": selected_score.judge,
            "fingerprint": fingerprint,
            "fingerprint_bundle": selected.metadata.get("fingerprint_bundle"),
        },
    )
    _save_decision(folder, decision)
    return selected, selected_score, decision, all_candidates, all_scores


def validate(folder: Path, workspace: str | Path | None = None) -> VisualValidationReport:
    decisions = load_decisions(folder)
    scores: dict[str, VisualScore] = {}
    for intent in load_intents(folder):
        _, shot_scores = load_candidates(folder, intent.shot_id)
        for score in shot_scores:
            scores[score.candidate_id] = score
    problems: list[str] = []
    warnings: list[str] = []
    per_shot: list[dict[str, Any]] = []
    relevance_values: list[float] = []
    overall_values: list[float] = []
    accepted = warning_count = rejected = missing = unexplained = 0
    generic = 0
    fingerprints: dict[str, int] = {}
    for decision in decisions:
        score = scores.get(decision.selected_candidate_id)
        if not decision.selected_path or not Path(decision.selected_path).exists():
            missing += 1
        if not decision.reason.strip():
            unexplained += 1
        if decision.selected_format in {VisualFormat.STOCK_VIDEO.value, VisualFormat.STOCK_IMAGE.value} and score and score.semantic_relevance < 85:
            generic += 1
        if score:
            relevance_values.append(score.semantic_relevance)
            overall_values.append(score.overall)
        if decision.status == DecisionStatus.ACCEPTED.value:
            accepted += 1
        elif decision.status in {DecisionStatus.NEEDS_APPROVAL.value, DecisionStatus.FALLBACK.value}:
            warning_count += 1
        else:
            rejected += 1
        fingerprint = str(decision.metadata.get("fingerprint") or decision.selected_path or decision.selected_candidate_id)
        fingerprints[fingerprint] = fingerprints.get(fingerprint, 0) + 1
        per_shot.append({"decision": decision.to_dict(), "score": score.to_dict() if score else None})
    duplicate_count = sum(count - 1 for count in fingerprints.values() if count > 1)
    average_relevance = sum(relevance_values) / max(1, len(relevance_values))
    average_overall = sum(overall_values) / max(1, len(overall_values))
    filler_ratio = generic / max(1, len(decisions))
    thresholds = _thresholds(workspace)
    minimum_average = float(thresholds.get("minimum_average_relevance", 78))
    maximum_filler = float(thresholds.get("maximum_generic_filler_ratio", 0.10))
    if missing:
        problems.append(f"{missing} selected visual(s) are missing.")
    if unexplained:
        problems.append(f"{unexplained} visual decision(s) have no explanation.")
    if duplicate_count:
        problems.append(f"{duplicate_count} exact visual duplicate(s) were selected.")
    if average_relevance < minimum_average and decisions:
        problems.append(f"Average visual relevance {average_relevance:.1f} is below {minimum_average:.1f}.")
    if filler_ratio > maximum_filler:
        problems.append(f"Generic filler ratio {filler_ratio:.1%} exceeds {maximum_filler:.1%}.")
    if warning_count:
        warnings.append(f"{warning_count} shot(s) use a fallback or require approval.")
    status = "not_run" if not decisions else "failed" if problems else "warning" if warnings else "passed"
    report = VisualValidationReport(
        status=status,
        shot_count=len(decisions),
        accepted_count=accepted,
        warning_count=warning_count,
        rejected_count=rejected,
        missing_count=missing,
        average_relevance=round(average_relevance, 2),
        average_overall=round(average_overall, 2),
        generic_filler_ratio=round(filler_ratio, 4),
        unexplained_decisions=unexplained,
        duplicate_count=duplicate_count,
        problems=problems,
        warnings=warnings,
        per_shot=per_shot,
    )
    write_json(folder / "quality" / "visual-intelligence-report.json", report.to_dict())
    return report


def explain(folder: Path, shot_id: str | None = None) -> dict[str, Any]:
    intents = {item.shot_id: item for item in load_intents(folder)}
    decisions = {item.shot_id: item for item in load_decisions(folder)}
    shot_ids = [shot_id] if shot_id else sorted(set(intents) | set(decisions))
    rows: list[dict[str, Any]] = []
    for current in shot_ids:
        intent = intents.get(current)
        decision = decisions.get(current)
        candidates, scores = load_candidates(folder, current)
        rows.append(
            {
                "shot_id": current,
                "intent": intent.to_dict() if intent else None,
                "decision": decision.to_dict() if decision else None,
                "candidates": [item.to_dict() for item in candidates],
                "scores": [item.to_dict() for item in sorted(scores, key=lambda score: score.overall, reverse=True)],
            }
        )
    return {"generation": str(folder), "shots": rows}


def replace(folder: Path, shot_id: str, candidate_id: str, *, approved: bool = False) -> VisualDecision:
    candidates, scores = load_candidates(folder, shot_id)
    candidate = next((item for item in candidates if item.candidate_id == candidate_id), None)
    score = next((item for item in scores if item.candidate_id == candidate_id), None)
    if not candidate or not score:
        raise KeyError(f"Candidate not found for {shot_id}: {candidate_id}")
    if candidate.approval_required and not approved:
        raise PermissionError("This candidate requires explicit approval. Re-run with --approve.")
    if not candidate.path or not Path(candidate.path).exists():
        candidate = materialize(candidate, folder)
    previous = next((item for item in load_decisions(folder) if item.shot_id == shot_id), None)
    history = []
    if previous:
        history.append(
            {
                "selected_candidate_id": previous.selected_candidate_id,
                "selected_path": previous.selected_path,
                "reason": previous.reason,
                "replaced_by": candidate_id,
            }
        )
    decision = VisualDecision(
        shot_id=shot_id,
        selected_candidate_id=candidate.candidate_id,
        status=DecisionStatus.ACCEPTED.value,
        score=score.overall,
        reason=f"Manually selected {candidate.title}. Original automated score: {score.overall:.1f}/100.",
        candidate_count=len(candidates),
        rejected_candidate_ids=[item.candidate_id for item in candidates if item.candidate_id != candidate.candidate_id],
        approval_required=False,
        selected_path=candidate.path,
        selected_format=candidate.format,
        selected_origin=candidate.origin,
        selected_provider=candidate.provider,
        replacement_history=history,
        metadata={"manual": True, "approved": approved},
    )
    _save_decision(folder, decision)
    state_event(
        folder,
        "visual_replacement",
        stage="visual_intelligence",
        status="passed",
        message=decision.reason,
        metadata={"shot_id": shot_id, "candidate_id": candidate_id, "approved": approved},
    )
    if approved:
        record_approval(folder, "visual_intelligence", subject_id=shot_id, metadata={"candidate_id": candidate_id, "operation": "replace"})
    return decision


def regenerate_shot(
    folder: Path,
    shot_id: str,
    *,
    workspace: str | Path | None = None,
    resource_finder: Callable[..., Any] | None = None,
    cloud_judge: bool | None = None,
    animate_explainers: bool = True,
) -> tuple[VisualDecision, dict[str, Any]]:
    intents = {item.shot_id: item for item in load_intents(folder)}
    intent = intents.get(shot_id)
    if not intent:
        raise KeyError(f"Shot intent not found: {shot_id}")
    shot_rows = read_json(folder / "visuals" / "shot-plan.json", []) or []
    shot_row = next((row for row in shot_rows if str((row.get("metadata") or {}).get("shot_id") or f"shot-{int(row.get('index', 0)):03d}") == shot_id), None)
    if not shot_row:
        raise KeyError(f"Shot not found: {shot_id}")
    previous = next((item for item in load_decisions(folder) if item.shot_id == shot_id), None)
    selected, score, decision, candidates, scores = run_tournament(
        folder,
        intent,
        duration=float(shot_row.get("duration") or 3.0),
        workspace=workspace,
        used_fingerprints=set(),
        resource_finder=resource_finder,
        cloud_judge=cloud_judge,
        animate_explainers=animate_explainers,
    )
    if previous:
        decision.replacement_history.append(
            {
                "selected_candidate_id": previous.selected_candidate_id,
                "selected_path": previous.selected_path,
                "reason": previous.reason,
                "replaced_by": selected.candidate_id,
                "operation": "regenerate",
            }
        )
        _save_decision(folder, decision)
    shot_row["resource_path"] = selected.path
    shot_row["resource_id"] = selected.candidate_id
    shot_row["source_url"] = selected.source_url
    shot_row["visual_type"] = selected.format
    shot_row["reason"] = decision.reason
    shot_row["approval_required"] = decision.approval_required
    metadata = dict(shot_row.get("metadata") or {})
    metadata.update(
        {
            "visual_candidate": selected.to_dict(),
            "visual_score": score.to_dict(),
            "visual_decision": decision.to_dict(),
            "candidate_count": len(candidates),
            "candidate_scores": {item.candidate_id: item.overall for item in scores},
        }
    )
    shot_row["metadata"] = metadata
    write_json(folder / "visuals" / "shot-plan.json", shot_rows)
    from ace.captions import adapt_to_visuals
    adapt_to_visuals(folder, workspace)
    validate(folder, workspace)
    state_event(
        folder,
        "visual_regeneration",
        stage="visual_intelligence",
        status=decision.status,
        message=decision.reason,
        metadata={"shot_id": shot_id, "candidate_id": selected.candidate_id},
    )
    return decision, shot_row


def approve_decision(folder: Path, shot_id: str) -> VisualDecision:
    decisions = load_decisions(folder)
    selected = next((item for item in decisions if item.shot_id == shot_id), None)
    if not selected:
        raise KeyError(f"Visual decision not found: {shot_id}")
    selected.approval_required = False
    selected.status = DecisionStatus.ACCEPTED.value
    selected.metadata["approved"] = True
    selected.reason = selected.reason + " Human approval recorded."
    _save_decision(folder, selected)
    shot_rows = read_json(folder / "visuals" / "shot-plan.json", []) or []
    for row in shot_rows:
        current = str((row.get("metadata") or {}).get("shot_id") or f"shot-{int(row.get('index', 0)):03d}")
        if current == shot_id:
            row["approval_required"] = False
            row["reason"] = selected.reason
    write_json(folder / "visuals" / "shot-plan.json", shot_rows)
    record_approval(
        folder,
        "visual_intelligence",
        subject_id=shot_id,
        metadata={"candidate_id": selected.selected_candidate_id, "operation": "approve"},
    )
    return selected
