from ace.accounts import asset_dir
from ace.resources import search_library


def test_account_asset_sidecar_tags_are_searchable(workspace):
    root = asset_dir(workspace=workspace)
    asset = root / "clip.mp4"
    asset.write_bytes(b"not-a-real-video")
    asset.with_suffix(".mp4.tags").write_text("biometric, security, phone\n", encoding="utf-8")

    rows = search_library("phone authentication", "video", workspace)
    assert len(rows) == 1
    assert "phone" in rows[0].tags
    assert rows[0].license == "user_owned"
