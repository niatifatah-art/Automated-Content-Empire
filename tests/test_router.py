from ace.providers.router import ProviderRouter


def test_two_gemini_credentials_maximum(workspace, monkeypatch):
    secrets = workspace / "config" / "secrets.env"
    secrets.write_text(
        "GEMINI_API_KEY_PRIMARY=one\n"
        "GEMINI_API_KEY_BACKUP=two\n"
        "GEMINI_API_KEY=three\n",
        encoding="utf-8",
    )
    router = ProviderRouter(workspace)
    credentials = router.credentials_for("gemini")
    assert [item.name for item in credentials] == ["primary", "backup"]
    assert [item.value for item in credentials] == ["one", "two"]


def test_legacy_key_becomes_primary(workspace):
    secrets = workspace / "config" / "secrets.env"
    secrets.write_text("GEMINI_API_KEY=legacy\n", encoding="utf-8")
    router = ProviderRouter(workspace)
    credentials = router.credentials_for("gemini")
    assert len(credentials) == 1
    assert credentials[0].name == "primary"

from ace.providers.base import GenerationResult, ProviderFailure


class _ModelFallbackGemini:
    name = "gemini"
    cloud = True

    def __init__(self):
        self.calls = []

    def generate(self, request, credential=None):
        self.calls.append((request.model, credential))
        if request.model == "gemini-3.6-flash":
            raise ProviderFailure("quota exhausted", category="rate_limit", retryable=True, retry_after=60)
        return GenerationResult("cloud fallback passed", "gemini", request.model)


def test_rate_limit_is_model_scoped_and_falls_back_to_another_cloud_model(workspace):
    secrets = workspace / "config" / "secrets.env"
    secrets.write_text("GEMINI_API_KEY_PRIMARY=one\n", encoding="utf-8")
    router = ProviderRouter(workspace)
    fake = _ModelFallbackGemini()
    router.providers["gemini"] = fake

    result = router.generate("script", "test")

    assert result.model == "gemini-3.5-flash"
    assert fake.calls[:2] == [("gemini-3.6-flash", "one"), ("gemini-3.5-flash", "one")]
    status = router.credential_status()[0]
    assert status["available"] is True
    assert status["model_cooldowns_seconds"]["gemini-3.6-flash"] > 0


class _BackupGemini:
    name = "gemini"
    cloud = True

    def __init__(self):
        self.calls = []

    def generate(self, request, credential=None):
        self.calls.append((request.model, credential))
        if credential == "one":
            raise ProviderFailure("primary quota", category="rate_limit", retryable=True, retry_after=60)
        return GenerationResult("backup passed", "gemini", request.model)


def test_backup_credential_is_tried_before_lower_model(workspace):
    secrets = workspace / "config" / "secrets.env"
    secrets.write_text("GEMINI_API_KEY_PRIMARY=one\nGEMINI_API_KEY_BACKUP=two\n", encoding="utf-8")
    router = ProviderRouter(workspace)
    fake = _BackupGemini()
    router.providers["gemini"] = fake

    result = router.generate("script", "test")

    assert result.model == "gemini-3.6-flash"
    assert result.credential_name == "backup"
    assert fake.calls[:2] == [("gemini-3.6-flash", "one"), ("gemini-3.6-flash", "two")]
