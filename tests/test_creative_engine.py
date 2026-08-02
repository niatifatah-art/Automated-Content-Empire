from pathlib import Path

from ace.cli import create_parser
from ace.creative import build_broll_queries, choose_meme_beat, edit_directive
from ace.providers.gemini import GeminiProvider
from ace.visual_intelligence.contracts import ShotIntent
from ace.visual_intelligence.tournament import generate_candidates


def test_broll_director_builds_distinct_shot_queries():
    intent = ShotIntent(
        shot_id="shot-001",
        narration="You type a URL into the browser and press Enter.",
        purpose="support",
        subject="browser_url_entry",
        mood="playful_tech",
        preferred_formats=["stock_video", "browser_demo"],
        required_elements=["browser", "address_bar", "hands"],
        forbidden_elements=["generic_hacker"],
        literalness="literal",
    )
    plans = build_broll_queries(intent)
    assert len(plans) >= 5
    assert len({item.query for item in plans}) == len(plans)
    assert any("over shoulder" in item.query for item in plans)
    assert any("close up" in item.query for item in plans)


def test_meme_director_rejects_forced_joke_and_accepts_natural_beat():
    serious = ShotIntent(
        shot_id="shot-001",
        narration="The company published an incident report.",
        purpose="show_evidence",
        subject="security_incident",
        mood="serious_technical",
        evidence_required=True,
        humor_allowed=False,
    )
    assert choose_meme_beat(serious).allowed is False

    playful = ShotIntent(
        shot_id="shot-002",
        narration="Of course the Linux fix created another bug.",
        purpose="support",
        subject="linux_bug",
        mood="playful_tech",
        preferred_formats=["meme", "terminal_demo"],
        humor_allowed=True,
    )
    beat = choose_meme_beat(playful)
    assert beat.allowed is True
    assert beat.punchline


def test_tournament_candidate_generation_connects_original_memes(generation: Path, workspace: Path):
    intent = ShotIntent(
        shot_id="shot-001",
        narration="Of course the developer fixed one bug and created another.",
        purpose="support",
        subject="developer_bug",
        mood="playful_tech",
        preferred_formats=["meme", "kinetic_typography"],
        required_elements=[],
        humor_allowed=True,
    )
    candidates = generate_candidates(
        generation,
        intent,
        duration=2.0,
        workspace=workspace,
        resource_finder=lambda *args, **kwargs: [],
        animate_explainers=False,
        generate_cloud_images=False,
    )
    assert any(item.format == "meme" and item.provider == "ace_meme" for item in candidates)


def test_hook_edit_directive_uses_real_emphasis():
    intent = ShotIntent(
        shot_id="shot-001",
        narration="This is what happens after you press Enter.",
        purpose="hook",
        subject="browser_request",
        mood="technical_dynamic",
        preferred_formats=["stock_video"],
    )
    directive = edit_directive(intent, 1)
    assert directive.motion == "punch_in"
    assert directive.transition == "cut"
    assert directive.emphasis == "strong"


def test_simple_make_command_defaults():
    args = create_parser().parse_args(["make", "Why", "DNS", "matters"])
    assert args.command == "make"
    assert args.platform == "youtube"
    assert args.content_type == "short"
    assert args.style == "adaptive"
    assert args.media == "mixed"
    assert args.memes == "auto"


def test_daily_quota_is_distinguished_from_short_rate_limit():
    body = '{"error":{"details":[{"violations":[{"quotaId":"GenerateRequestsPerDayPerProjectPerModel-FreeTier","quotaMetric":"generativelanguage.googleapis.com/generate_content_free_tier_requests"}]}]}}'
    assert GeminiProvider._quota_scope_from_body(body) == "daily"
    assert GeminiProvider._seconds_until_pacific_midnight() >= 60


def test_creative_quality_flags_slideshow(generation: Path, workspace: Path):
    from ace.creative_quality import inspect
    from ace.utils import write_json

    shots = []
    for index in range(1, 6):
        shots.append(
            {
                "index": index,
                "start": (index - 1) * 3.0,
                "end": index * 3.0,
                "duration": 3.0,
                "narration": "A static explanation.",
                "purpose": "support",
                "visual_type": "kinetic_typography",
                "search_query": "test",
                "transition": "cut",
                "mood": "playful_tech",
                "metadata": {"creative": {"motion": "steady"}},
            }
        )
    write_json(generation / "visuals" / "shot-plan.json", shots)
    report = inspect(generation, workspace)
    assert report["status"] == "warning"
    assert report["static_card_ratio"] == 1.0
    assert report["score"] < 80


def test_simple_command_aliases_and_friendly_controls():
    parser = create_parser()
    make = parser.parse_args(["make", "DNS", "explained", "--look", "fun", "--footage", "mixed", "--humor", "auto", "--mode", "best"])
    assert make.style == "fun"
    assert make.media == "mixed"
    assert make.memes == "auto"
    assert make.quality == "best"
    redo = parser.parse_args(["redo", "4"])
    assert redo.command == "redo"
    assert redo.shot_pos == 4
    assert parser.parse_args(["open"]).command == "open"
    assert parser.parse_args(["checkup", "--offline"]).command == "checkup"


def test_secondary_selector_rejects_text_cards_and_chooses_live_cutaway(tmp_path: Path):
    from ace.visuals import Shot, _select_secondary_visual
    from ace.visual_intelligence.contracts import VisualCandidate, VisualScore

    selected_path = tmp_path / "explainer.png"
    text_path = tmp_path / "card.png"
    live_path = tmp_path / "broll.mp4"
    for item in (selected_path, text_path, live_path):
        item.write_bytes(b"test")

    selected = VisualCandidate("selected", "shot-001", "animated_explainer", "ace_explainer", "DNS explainer", path=str(selected_path))
    text_card = VisualCandidate("text", "shot-001", "kinetic_typography", "ace_typography", "Text card", path=str(text_path))
    live = VisualCandidate("live", "shot-001", "stock_video", "pexels", "Hands typing URL", path=str(live_path))
    selected_score = VisualScore("selected", "shot-001", 95, 92, 90, 95, 90, 100, 90, 100, 0, 94, "accepted")
    text_score = VisualScore("text", "shot-001", 91, 90, 80, 95, 85, 100, 88, 100, 0, 90, "accepted")
    live_score = VisualScore("live", "shot-001", 88, 86, 82, 90, 86, 100, 87, 90, 0, 88, "accepted")
    shot = Shot(1, 0.0, 3.4, 3.4, "Type a URL into the browser.", "support", "animated_explainer", "typing url")
    intent = ShotIntent(
        shot_id="shot-001",
        narration=shot.narration,
        purpose="support",
        subject="browser_url_entry",
        preferred_formats=["browser_demo", "stock_video", "animated_explainer"],
        literalness="mixed",
    )
    candidate, score, usage = _select_secondary_visual(
        selected=selected,
        selected_score=selected_score,
        candidates=[selected, text_card, live],
        scores=[selected_score, text_score, live_score],
        shot=shot,
        intent=intent,
    )
    assert candidate is live
    assert score is live_score
    assert usage["mode"] == "cutaway"


def test_humor_on_considers_but_does_not_force_a_meme():
    intent = ShotIntent(
        shot_id="shot-calm",
        narration="The browser sends the request to the server.",
        purpose="support",
        subject="browser_server_request",
        mood="playful_tech",
        humor_allowed=True,
    )
    assert choose_meme_beat(intent, mode="on").allowed is False


def test_creative_quality_counts_live_cutaway_without_marking_static_primary(generation: Path, workspace: Path):
    from ace.creative_quality import inspect
    from ace.utils import write_json

    shots = []
    for index in range(1, 5):
        shots.append(
            {
                "index": index,
                "start": (index - 1) * 2.5,
                "end": index * 2.5,
                "duration": 2.5,
                "narration": "A technical explanation.",
                "purpose": "support",
                "visual_type": "animated_explainer",
                "search_query": "test",
                "transition": "cut" if index % 2 else "quick_fade",
                "mood": "technical_dynamic",
                "metadata": {
                    "creative": {"motion": "steady" if index % 2 else "slow_push"},
                    "secondary_visual": {"format": "stock_video"},
                    "secondary_usage": {"mode": "cutaway", "start": 0.7, "duration": 1.0},
                },
            }
        )
    write_json(generation / "visuals" / "shot-plan.json", shots)
    report = inspect(generation, workspace)
    assert report["cutaway_count"] == 4
    assert report["live_broll_ratio"] == 1.0
    assert report["static_card_ratio"] == 0.0


def test_typography_candidate_uses_concise_cta_text(generation: Path):
    from ace.visual_intelligence.candidates import typography_candidate

    intent = ShotIntent(
        shot_id="shot-cta",
        narration="All of that can happen before your finger leaves the Enter key.",
        purpose="call_to_action",
        subject="all_happen_before_finger_leaves_enter",
        preferred_formats=["kinetic_typography"],
    )
    candidate = typography_candidate(generation, intent)
    assert candidate.path
    assert len(candidate.title.split()) <= 9
