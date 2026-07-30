from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable

from ace.visual_intelligence.contracts import ShotIntent, VisualFormat, VisualPurpose


_TOKEN_RE = re.compile(r"[A-Za-z0-9_+.#-]{2,}")


def _contains(text: str, *terms: str) -> bool:
    value = text.lower()
    return any(term.lower() in value for term in terms)


def _subject_slug(value: str) -> str:
    words = [token.lower().strip(".-") for token in _TOKEN_RE.findall(value)]
    stop = {
        "the", "and", "that", "this", "with", "from", "your", "you", "into", "when", "then",
        "will", "have", "has", "for", "are", "was", "were", "can", "could", "would", "about",
        "other", "people", "some", "just", "more", "most", "than", "they", "their", "there",
    }
    unique: list[str] = []
    for word in words:
        if word in stop or len(word) < 3 or word in unique:
            continue
        unique.append(word)
    return "_".join(unique[:6]) or "general_topic"


def _queries(subject: str, narration: str, formats: list[str], required: list[str]) -> dict[str, list[str]]:
    base = " ".join(subject.replace("_", " ").split())
    core = " ".join(required[:4])
    output: dict[str, list[str]] = {}
    for visual_format in formats:
        if visual_format == VisualFormat.STOCK_VIDEO.value:
            output[visual_format] = [f"{base} real person device", f"{base} close up vertical"]
        elif visual_format == VisualFormat.STOCK_IMAGE.value:
            output[visual_format] = [f"{base} photo", f"{base} illustration"]
        elif visual_format == VisualFormat.OFFICIAL_EVIDENCE.value:
            output[visual_format] = [f"{base} official announcement", f"{base} newsroom documentation"]
        elif visual_format in {VisualFormat.BROWSER_DEMO.value, VisualFormat.APPLICATION_DEMO.value}:
            output[visual_format] = [f"{base} user interface demonstration", f"{base} settings screen"]
        elif visual_format == VisualFormat.TERMINAL_DEMO.value:
            output[visual_format] = [f"{base} terminal command demonstration"]
        elif visual_format == VisualFormat.ANIMATED_EXPLAINER.value:
            output[visual_format] = [f"{base} {core} animated explainer".strip()]
        elif visual_format == VisualFormat.MEME.value:
            output[visual_format] = [f"{base} relatable tech reaction"]
        else:
            output[visual_format] = [base]
    return output


def deterministic_intent(
    narration: str,
    *,
    shot_id: str,
    purpose: str = VisualPurpose.SUPPORT.value,
    mood: str = "technical_dynamic",
    topic: str = "",
    caption_strategy: str = "short_phrase",
) -> ShotIntent:
    """Create a safe, deterministic visual plan before any cloud refinement.

    The rules intentionally prefer demonstrations and purpose-built explainers
    for mechanisms. Stock becomes primary only when the narration describes a
    literal real-world scene that stock media can represent honestly.
    """

    text = narration.strip() or topic.strip()
    lower = narration.lower()
    preferred: list[str] = []
    required: list[str] = []
    forbidden: list[str] = []
    evidence_required = False
    humor_allowed = mood in {"playful_tech", "gaming_hype", "challenge"}
    literalness = "mixed"
    rationale: list[str] = []
    subject = _subject_slug(narration or topic)
    importance = 0.62

    # Official announcements, company deals and release claims.
    if _contains(lower, "announced", "announcement", "partnership", "deal", "acquisition", "officially", "press release", "released", "confirmed", "incident report", "official report"):
        purpose = VisualPurpose.SHOW_EVIDENCE.value
        evidence_required = True
        importance = 0.9
        preferred.extend([
            VisualFormat.OFFICIAL_EVIDENCE.value,
            VisualFormat.ARTICLE_CARD.value,
            VisualFormat.TIMELINE.value,
            VisualFormat.ANIMATED_EXPLAINER.value,
        ])
        required.extend(["source_name", "headline", "date"])
        forbidden.extend(["unverified_social_post", "generic_business_handshake"])
        literalness = "evidence"
        rationale.append("A factual announcement should lead with primary-source evidence, not generic company footage.")

    # Code, command and application workflows.
    if _contains(lower, "sudo ", "apt ", "pip ", "npm ", "git ", "command", "terminal", "shell", "bash", "powershell"):
        purpose = VisualPurpose.DEMONSTRATE.value
        preferred = [VisualFormat.TERMINAL_DEMO.value, VisualFormat.KINETIC_TYPOGRAPHY.value, *preferred]
        required.extend(["terminal", "exact_command", "visible_result"])
        forbidden.extend(["random_typing", "generic_code_rain"])
        literalness = "demonstration"
        importance = max(importance, 0.82)
        rationale.append("Commands should be demonstrated exactly in a readable terminal view.")
    elif _contains(lower, "click", "open settings", "menu", "toggle", "browser", "website", "application", "install"):
        purpose = VisualPurpose.DEMONSTRATE.value
        preferred = [VisualFormat.APPLICATION_DEMO.value, VisualFormat.BROWSER_DEMO.value, *preferred]
        required.extend(["relevant_interface", "visible_action"])
        forbidden.extend(["unrelated_dashboard", "generic_laptop"])
        literalness = "demonstration"
        rationale.append("Interface instructions are clearest as a controlled UI demonstration.")

    # Network and security mechanisms.
    if _contains(lower, "public wi-fi", "public wifi", "shared network", "access point", "router"):
        subject = "public_wifi_shared_network"
        preferred = [VisualFormat.ANIMATED_EXPLAINER.value, VisualFormat.APPLICATION_DEMO.value, VisualFormat.STOCK_VIDEO.value, *preferred]
        required.extend(["wireless_router", "multiple_devices", "shared_network"])
        forbidden.extend(["fire", "financial_chart", "generic_office_interview", "generic_hacker", "abstract_ai_network"])
        rationale.append("A shared network needs a literal network topology or real connection scene.")
    if _contains(lower, "lacks encryption", "without encryption", "unencrypted", "exposed traffic", "plain text"):
        subject = "unencrypted_network_traffic"
        purpose = VisualPurpose.EXPLAIN_MECHANISM.value
        preferred = [VisualFormat.ANIMATED_EXPLAINER.value, VisualFormat.BROWSER_DEMO.value, VisualFormat.GENERATED_CONCEPT_IMAGE.value]
        required = ["shared_access_point", "multiple_devices", "data_packets", "missing_encryption_lock"]
        forbidden = ["fire", "financial_chart", "office_worker", "generic_hacker", "abstract_ai_network"]
        literalness = "abstract_mechanism"
        importance = 0.94
        rationale.append("Unencrypted traffic is abstract; a packet-flow explainer communicates the mechanism directly.")
    elif _contains(lower, "encryption", "encrypted", "https", "tls", "secure connection"):
        subject = "encrypted_connection"
        purpose = VisualPurpose.EXPLAIN_MECHANISM.value
        preferred = [VisualFormat.ANIMATED_EXPLAINER.value, VisualFormat.BROWSER_DEMO.value, VisualFormat.APPLICATION_DEMO.value]
        required.extend(["data_packets", "encryption_lock", "protected_connection"])
        forbidden.extend(["financial_chart", "generic_hacker", "abstract_ai_network"])
        literalness = "abstract_mechanism"
        importance = max(importance, 0.88)
        rationale.append("Encryption should show packets becoming protected or a real HTTPS state.")
    if _contains(lower, "rogue hotspot", "fake hotspot", "fake wi-fi", "evil twin", "lookalike network"):
        subject = "rogue_wifi_hotspot"
        purpose = VisualPurpose.EXPLAIN_MECHANISM.value
        preferred = [VisualFormat.ANIMATED_EXPLAINER.value, VisualFormat.APPLICATION_DEMO.value]
        required = ["two_similar_wifi_names", "trusted_network", "fake_network", "attacker_control"]
        forbidden = ["generic_hacker", "random_router", "financial_chart"]
        literalness = "abstract_mechanism"
        importance = 0.93
        rationale.append("A rogue hotspot requires a side-by-side trusted versus fake network visual.")
    if _contains(lower, "vpn", "virtual private network", "tunnel"):
        subject = "vpn_encrypted_tunnel"
        purpose = VisualPurpose.EXPLAIN_MECHANISM.value
        preferred = [VisualFormat.ANIMATED_EXPLAINER.value, VisualFormat.APPLICATION_DEMO.value]
        required.extend(["device", "encrypted_tunnel", "vpn_server", "destination"])
        forbidden.extend(["generic_hacker", "financial_chart"])
        literalness = "abstract_mechanism"
        rationale.append("A VPN is best explained as an encrypted tunnel between device and server.")
    if _contains(lower, "mobile hotspot", "phone hotspot", "cellular hotspot", "personal hotspot"):
        subject = "phone_personal_hotspot"
        purpose = VisualPurpose.DEMONSTRATE.value
        preferred = [VisualFormat.APPLICATION_DEMO.value, VisualFormat.ACCOUNT_ASSET.value, VisualFormat.STOCK_VIDEO.value]
        required = ["smartphone", "hotspot_settings", "connected_device"]
        forbidden = ["generic_wifi_router", "financial_chart"]
        literalness = "literal"
        rationale.append("A phone hotspot should be shown literally on a smartphone settings screen.")

    # Authentication and passkeys.
    if _contains(lower, "passkey", "face id", "fingerprint", "biometric", "authentication"):
        subject = "passkey_biometric_authentication"
        purpose = VisualPurpose.EXPLAIN_MECHANISM.value
        preferred = [VisualFormat.ANIMATED_EXPLAINER.value, VisualFormat.APPLICATION_DEMO.value, VisualFormat.STOCK_VIDEO.value]
        required.extend(["device", "biometric_confirmation", "public_private_key_flow"])
        forbidden.extend(["generic_password_typing", "financial_chart", "generic_hacker"])
        literalness = "mixed"
        rationale.append("Passkeys need a device-authentication flow, not generic password imagery.")

    # Programming logic and code behavior.
    if _contains(lower, "function", "loop", "iterate", "iteration", "mutates", "mutation", "list", "dictionary", "exception", "traceback", "bug happens"):
        subject = _subject_slug(narration)
        purpose = VisualPurpose.EXPLAIN_MECHANISM.value
        preferred = [VisualFormat.ANIMATED_EXPLAINER.value, VisualFormat.KINETIC_TYPOGRAPHY.value, VisualFormat.TERMINAL_DEMO.value, *preferred]
        required.extend(["code_state", "before_after", "execution_flow"])
        forbidden.extend(["generic_code_rain", "random_typing", "unrelated_dashboard"])
        literalness = "abstract_mechanism"
        rationale.append("Programming behavior should show state changes or execution flow, not generic coding footage.")

    # APIs, cloud/local routing and architecture.
    if _contains(lower, "api request", "api call", "endpoint", "provider route", "fallback", "cloud model", "local model", "architecture", "workflow", "pipeline"):
        subject = "software_system_flow"
        purpose = VisualPurpose.EXPLAIN_MECHANISM.value
        preferred = [VisualFormat.ANIMATED_EXPLAINER.value, VisualFormat.COMPARISON_GRAPHIC.value]
        required.extend(["request", "processing_nodes", "response", "directional_flow"])
        forbidden.extend(["generic_code_rain", "random_server_room"])
        literalness = "abstract_mechanism"
        rationale.append("Software architecture should be explained with a structured flow diagram.")

    # Comparisons, data and timelines.
    comparison_terms = ("versus", " vs ", "compared", "comparison", "faster than", "slower than", "better than", "cheaper than")
    if _contains(lower, *comparison_terms):
        purpose = VisualPurpose.COMPARE.value
        preferred = [VisualFormat.COMPARISON_GRAPHIC.value, VisualFormat.DATA_CHART.value, *preferred]
        required.extend(["option_a", "option_b", "comparison_criteria"])
        forbidden.extend(["unlabeled_chart"])
        literalness = "data"
        rationale.append("A comparison needs labeled side-by-side criteria rather than generic footage.")
    if re.search(r"\b\d+(?:\.\d+)?\s*(?:%|fps|gb|tb|ms|x|million|billion)\b", lower):
        purpose = VisualPurpose.SHOW_DATA.value
        preferred = [VisualFormat.DATA_CHART.value, VisualFormat.KINETIC_TYPOGRAPHY.value, *preferred]
        required.extend(["exact_value", "unit", "context"])
        forbidden.extend(["invented_scale", "unlabeled_chart"])
        evidence_required = True
        importance = max(importance, 0.86)
        rationale.append("A precise value should be shown exactly and tied to its source.")
    if _contains(lower, "timeline", "first", "then", "after that", "finally", "over the next", "history"):
        preferred = [VisualFormat.TIMELINE.value, *preferred]
        required.extend(["ordered_steps"])

    # Challenge and humor formats.
    challenge_signal = (
        mood == "challenge"
        or _contains(lower, "for seven days", "for 7 days", "i tried", "day one", "day 1", "day three", "day 3")
        or ("challenge" in lower and _contains(lower, "week", "day", "attempt", "creator"))
    )
    if challenge_signal:
        purpose = VisualPurpose.CHALLENGE_PROGRESS.value
        subject = "creator_challenge_" + _subject_slug(narration)
        preferred = [VisualFormat.ACCOUNT_ASSET.value, VisualFormat.TIMELINE.value, VisualFormat.KINETIC_TYPOGRAPHY.value]
        required.extend(["progress", "day_or_step", "result"])
        humor_allowed = True
        literalness = "creator"
        rationale.append("Challenge content benefits from creator footage and visible progress.")
    if humor_allowed and _contains(lower, "somehow", "of course", "because linux", "developer", "bug", "crash", "weird", "ridiculous"):
        if purpose not in {VisualPurpose.SHOW_EVIDENCE.value, VisualPurpose.SHOW_DATA.value}:
            preferred.append(VisualFormat.MEME.value)
            rationale.append("A light meme candidate is allowed, but it must not replace factual explanation.")

    # Literal physical scenes are where stock performs well.
    literal_terms = (
        "person using", "walking", "cafe", "coffee shop", "airport", "gaming setup", "graphics card",
        "data center", "smartphone in hand", "laptop", "server rack", "office building",
    )
    if _contains(lower, *literal_terms) and purpose not in {VisualPurpose.EXPLAIN_MECHANISM.value, VisualPurpose.SHOW_EVIDENCE.value}:
        preferred = [VisualFormat.ACCOUNT_ASSET.value, VisualFormat.STOCK_VIDEO.value, VisualFormat.STOCK_IMAGE.value, *preferred]
        literalness = "literal"
        rationale.append("This narration describes a real physical scene that strong literal footage can show.")

    # Hook/CTA presentation.
    if purpose == VisualPurpose.HOOK.value:
        importance = max(importance, 0.9)
        preferred = [VisualFormat.KINETIC_TYPOGRAPHY.value, *preferred]
    if purpose == VisualPurpose.CALL_TO_ACTION.value:
        preferred = [VisualFormat.KINETIC_TYPOGRAPHY.value, VisualFormat.MINIMAL_SCREEN.value, *preferred]

    # Final fallback order: original communication first, stock only after it.
    if not preferred:
        if literalness == "literal":
            preferred = [VisualFormat.ACCOUNT_ASSET.value, VisualFormat.STOCK_VIDEO.value, VisualFormat.STOCK_IMAGE.value]
        else:
            preferred = [VisualFormat.ANIMATED_EXPLAINER.value, VisualFormat.KINETIC_TYPOGRAPHY.value, VisualFormat.STOCK_VIDEO.value]
    if VisualFormat.MINIMAL_SCREEN.value not in preferred:
        preferred.append(VisualFormat.MINIMAL_SCREEN.value)

    # Deduplicate while retaining order.
    preferred = list(dict.fromkeys(preferred))
    required = list(dict.fromkeys(required))
    forbidden = list(dict.fromkeys(forbidden))
    subject = subject or _subject_slug(text)

    return ShotIntent(
        shot_id=shot_id,
        narration=narration,
        purpose=purpose,
        subject=subject,
        mood=mood,
        importance=importance,
        preferred_formats=preferred,
        required_elements=required,
        forbidden_elements=forbidden,
        search_queries=_queries(subject, narration, preferred, required),
        caption_strategy=caption_strategy,
        evidence_required=evidence_required,
        humor_allowed=humor_allowed,
        literalness=literalness,
        rationale=" ".join(rationale) or "The deterministic planner selected formats according to the narration purpose.",
        metadata={"planner": "deterministic", "topic": topic},
    )


def _extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.I)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        value = json.loads(stripped)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            value = json.loads(stripped[start : end + 1])
            return value if isinstance(value, dict) else {}
        raise


def _merge_cloud(base: ShotIntent, row: dict[str, Any]) -> ShotIntent:
    allowed_formats = {item.value for item in VisualFormat}
    formats = [str(item) for item in row.get("preferred_formats", []) if str(item) in allowed_formats]
    if not formats:
        formats = base.preferred_formats
    purpose = str(row.get("purpose") or base.purpose)
    if purpose not in {item.value for item in VisualPurpose}:
        purpose = base.purpose
    return ShotIntent(
        shot_id=base.shot_id,
        narration=base.narration,
        purpose=purpose,
        subject=str(row.get("subject") or base.subject),
        mood=str(row.get("mood") or base.mood),
        importance=float(row.get("importance", base.importance)),
        preferred_formats=formats,
        required_elements=list(row.get("required_elements") or base.required_elements),
        forbidden_elements=list(row.get("forbidden_elements") or base.forbidden_elements),
        search_queries=dict(row.get("search_queries") or base.search_queries),
        caption_strategy=str(row.get("caption_strategy") or base.caption_strategy),
        evidence_required=bool(row.get("evidence_required", base.evidence_required)),
        humor_allowed=bool(row.get("humor_allowed", base.humor_allowed)),
        literalness=str(row.get("literalness") or base.literalness),
        rationale=str(row.get("rationale") or base.rationale),
        metadata={**base.metadata, "planner": "cloud_refined", "cloud_raw": row},
    )


@dataclass(slots=True)
class IntentPlanner:
    workspace: str | None = None
    allow_cloud: bool = True
    router_factory: Callable[..., Any] | None = None

    def plan(
        self,
        narration: str,
        *,
        shot_id: str,
        purpose: str,
        mood: str,
        topic: str,
        caption_strategy: str,
    ) -> ShotIntent:
        baseline = deterministic_intent(
            narration,
            shot_id=shot_id,
            purpose=purpose,
            mood=mood,
            topic=topic,
            caption_strategy=caption_strategy,
        )
        if not self.allow_cloud:
            return baseline
        try:
            if self.router_factory is None:
                from ace.providers.router import ProviderRouter

                router = ProviderRouter(self.workspace, allow_degraded=False)
            else:
                router = self.router_factory(self.workspace)
            prompt = (
                "You are ACE's Visual Intent Planner. Refine the deterministic plan below. "
                "Choose the clearest truthful visual language for the exact narration. Stock footage is not the default. "
                "Never choose visual metaphors based only on one word. Do not suggest generic hackers, office workers, "
                "financial charts, abstract AI networks, or fire unless they are literally relevant. Return one JSON object only.\n\n"
                f"TOPIC: {topic}\nNARRATION: {narration}\n"
                f"DETERMINISTIC_PLAN:\n{json.dumps(baseline.to_dict(), ensure_ascii=False, indent=2)}\n\n"
                "Required keys: purpose, subject, mood, importance, preferred_formats, required_elements, "
                "forbidden_elements, search_queries, caption_strategy, evidence_required, humor_allowed, "
                "literalness, rationale. Use only supported preferred_formats from the deterministic plan schema."
            )
            result = router.generate(
                "visual_planning",
                prompt,
                temperature=0.2,
                max_output_tokens=1800,
                json_mode=True,
                metadata={"shot_id": shot_id, "subject": baseline.subject, "stage": "visual_intent"},
            )
            row = _extract_json(result.text)
            refined = _merge_cloud(baseline, row)
            refined.metadata.update(
                {
                    "provider": result.provider,
                    "model": result.model,
                    "credential_name": result.credential_name,
                    "degraded": result.degraded,
                }
            )
            return refined
        except Exception as exc:  # Cloud refinement is optional; deterministic behavior remains valid.
            baseline.metadata["cloud_error"] = str(exc)
            return baseline
