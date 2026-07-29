from ace.config import load, set_value


def test_defaults_and_nested_setting(workspace):
    config = load(workspace)
    assert config["execution"]["cloud_first"] is True
    assert config["credentials"]["gemini"]["maximum_credentials"] == 2
    set_value("captions.maximum_lines", "2", workspace)
    assert load(workspace)["captions"]["maximum_lines"] == 2

from ace.config import initialize
from ace.utils import read_json, write_json


def test_upgrade_enriches_legacy_cloud_routes_before_local(workspace):
    config_path = workspace / "config" / "config.json"
    config = read_json(config_path, {})
    config["version"] = "2.0.0"
    config["routes"]["script"] = [
        {"provider": "gemini", "model": "gemini-3.6-flash", "critical": True},
        {"provider": "ollama", "model": "qwen2.5:latest", "degraded": True},
    ]
    write_json(config_path, config)

    initialize(workspace, upgrade=True)
    upgraded = read_json(config_path, {})
    route_pairs = [(item["provider"], item["model"]) for item in upgraded["routes"]["script"]]

    assert route_pairs[:3] == [
        ("gemini", "gemini-3.6-flash"),
        ("gemini", "gemini-3.5-flash"),
        ("gemini", "gemini-3.5-flash-lite"),
    ]
    assert ("ollama", "qwen2.5:latest") in route_pairs
