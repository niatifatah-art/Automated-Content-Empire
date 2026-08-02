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
