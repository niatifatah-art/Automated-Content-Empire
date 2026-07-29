from ace.providers.base import GenerationRequest
from ace.providers.gemini import GeminiProvider


def test_new_gemini_models_do_not_send_deprecated_temperature():
    req = GenerationRequest("script", "x", "gemini-3.6-flash", temperature=0.9, max_output_tokens=512)
    config = GeminiProvider._generation_config(req)
    assert "temperature" not in config
    assert config["maxOutputTokens"] == 512


def test_retry_delay_is_parsed_from_error_body():
    body = '{"error":{"details":[{"retryDelay":"57.25s"}]}}'
    assert GeminiProvider._retry_after_from_body(body) == 57.25
