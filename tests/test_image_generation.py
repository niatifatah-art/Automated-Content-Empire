import base64

from ace import image_generation


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def test_gemini_image_uses_interactions_api(monkeypatch, tmp_path):
    captured = {}
    image_bytes = b"fake-png"

    monkeypatch.setattr(image_generation, "_gemini_keys", lambda workspace=None: [("primary", "secret")])

    def fake_request(method, url, **kwargs):
        captured.update({"method": method, "url": url, **kwargs})
        return FakeResponse({"steps": [{"type": "model_output", "content": [{"type": "image", "mime_type": "image/png", "data": base64.b64encode(image_bytes).decode()}]}]})

    monkeypatch.setattr(image_generation, "request", fake_request)
    output = tmp_path / "image.png"
    result = image_generation._generate_gemini("original illustration", output, None, "gemini-3.1-flash-image", "9:16")

    assert output.read_bytes() == image_bytes
    assert captured["url"].endswith("/v1beta/interactions")
    assert captured["json_body"]["response_format"]["aspect_ratio"] == "9:16"
    assert result.provider == "gemini_image:primary"
