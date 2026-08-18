import yaml

from ace.accounts import account_path, load, migrate_all


def test_legacy_account_gets_editing_defaults_and_is_persisted(workspace):
    path = account_path("test-creator", workspace)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw.pop("editing", None)
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    loaded = load("test-creator", workspace)
    assert loaded["editing"]["style"] == "adaptive"

    migrated = migrate_all(workspace)
    assert migrated == ["test-creator"]
    persisted = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert persisted["editing"]["captions"]["mode"] == "director"


def test_legacy_voice_provider_is_preserved_while_profile_binding_is_added(workspace):
    path = account_path("test-creator", workspace)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw["voice"] = {
        "configured": True,
        "provider": "kokoro",
        "voice_id": "af_sarah",
        "pace": "natural",
        "energy": "conversational",
    }
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    loaded = load("test-creator", workspace)
    assert loaded["voice"]["provider"] == "kokoro"
    assert loaded["voice"]["voice_id"] == "af_sarah"
    assert loaded["voice"]["profile_id"] is None
    assert loaded["voice"]["policy"] == "consistency_first"
    assert loaded["voice"]["default_style"] == "creator"
