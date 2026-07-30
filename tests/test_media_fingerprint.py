from pathlib import Path

from PIL import Image

from ace.media_fingerprint import fingerprint_bundle, hamming_distance, perceptual_similarity


def test_image_fingerprint_detects_same_visual(tmp_path: Path):
    left = tmp_path / "left.png"
    right = tmp_path / "right.png"
    Image.new("RGB", (160, 240), (12, 44, 70)).save(left)
    Image.new("RGB", (160, 240), (12, 44, 70)).save(right)
    first = fingerprint_bundle(left)
    second = fingerprint_bundle(right)
    assert first["dhash"] == second["dhash"]
    assert perceptual_similarity(first, second) == 1.0
    assert hamming_distance(first["dhash"], second["dhash"]) == 0
