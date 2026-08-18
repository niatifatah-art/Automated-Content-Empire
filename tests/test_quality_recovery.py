from __future__ import annotations

import json

from ace.quality import heuristic, run


def test_short_generic_template_does_not_score_as_perfect():
    text = (
        "In this video, we're going to talk about Linux. "
        "Linux is an operating system that many people use. "
        "It can be useful for programming and everyday tasks. "
        "Let's dive in and explore why people like it. "
        "There are many distributions, many desktop choices, and lots of software. "
        "It is important to note that the best choice depends on your needs. "
        "Try a few options and see what works for you."
    )

    report = heuristic(text, content_type="short")

    assert report.score < 85
    assert report.status == "warning"
    assert report.checks["generic_opening"] is True
    assert report.checks["generic_filler_count"] >= 1


def test_specific_natural_short_can_pass_deterministic_gate():
    text = (
        "Your browser does not jump straight from google.com to a website. "
        "First it asks DNS for the server address, then it opens a connection, negotiates HTTPS, and finally requests the page. "
        "That is why a broken DNS server can make the internet look completely dead even while your Wi-Fi is connected. "
        "Change DNS and the same connection can suddenly work again. "
        "The weird part is that all of this happens before the page you wanted has even started loading."
    )

    report = heuristic(text, content_type="short")

    assert report.score >= 85
    assert report.checks["generic_opening"] is False
    assert report.checks["generic_filler_count"] == 0


def test_run_uses_generation_content_type(tmp_path):
    (tmp_path / "quality").mkdir()
    (tmp_path / "selected.md").write_text(
        "In this video, we're going to explain DNS. "
        "DNS turns names into addresses so computers can find servers. "
        "Let's dive in and look at the basics. "
        "Your device asks a resolver, the resolver finds the answer, and the browser can continue. "
        "That lookup is one of the first steps before a site loads. "
        "If DNS fails, a working network can still appear broken to the user.",
        encoding="utf-8",
    )
    (tmp_path / "metadata.json").write_text(
        json.dumps({"content_type": "short", "platform": "youtube", "topic": "DNS"}),
        encoding="utf-8",
    )

    report = run(tmp_path, use_ai=False)

    assert report.checks["content_type"] == "short"
    assert report.checks["generic_opening"] is True
    assert report.score < 85
