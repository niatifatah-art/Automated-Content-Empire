from __future__ import annotations

from ace.production_templates import discover, effective_controls, resolve, search, select


def test_builtins_are_discoverable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    templates = discover(tmp_path / "workspace")
    ids = {item.template_id for item in templates}
    assert {
        "horror-story",
        "funny-facts",
        "educational-explainer",
        "tech-news",
        "dark-documentary",
    }.issubset(ids)


def test_latest_version_resolution(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    item = resolve("horror-story", tmp_path / "workspace")
    assert item.reference == "horror-story@1.0.0"
    assert resolve(item.reference, tmp_path / "workspace").reference == item.reference


def test_auto_selection_prefers_horror_for_story_terms(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    item = select("A strange red umbrella waits outside a haunted hotel", "short", tmp_path / "workspace")
    assert item.template_id == "horror-story"


def test_auto_selection_has_general_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    item = select("How does evaporation work?", "short", tmp_path / "workspace")
    assert item.template_id == "educational-explainer"


def test_locked_identity_rejects_conflicting_legacy_override(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    item = resolve("horror-story", tmp_path / "workspace")
    controls = effective_controls(item, look="fun", media="mixed", memes="on", quality="best")
    assert controls["genre"] == "suspense"
    assert controls["humor_policy"] == "none"
    assert controls["media_mode"] == "mixed"
    assert controls["quality_mode"] == "best"
    assert controls["ignored_locked_overrides"] == {}


def test_template_search(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    results = search("documentary investigation", tmp_path / "workspace")
    assert results
    assert results[0].template_id == "dark-documentary"
