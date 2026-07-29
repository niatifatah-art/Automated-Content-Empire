from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ace.config import load as load_config
from ace.paths import resolve_paths
from ace.providers.base import GenerationRequest, GenerationResult, ProviderFailure, TextProvider
from ace.providers.gemini import GeminiProvider
from ace.providers.ollama import OllamaProvider
from ace.providers.openai_compat import OpenAICompatibleProvider
from ace.secrets import load as load_secrets
from ace.utils import read_json, utc_now_iso, write_json


@dataclass
class Credential:
    name: str
    value: str
    provider: str


class ProviderRouter:
    """Cloud-first provider router with model-aware quota failover.

    A Gemini quota is commonly scoped to a project *and model*.  ACE therefore
    cools down the failing credential/model pair rather than disabling the whole
    credential.  This lets a 3.6 Flash quota failure immediately fall through to
    3.5 Flash or Flash-Lite, and it still lets a separately-authorized backup
    credential try the preferred model first.
    """

    def __init__(
        self,
        workspace: str | Path | None = None,
        *,
        allow_degraded: bool | None = None,
        default_provider: str | None = None,
        default_model: str | None = None,
        default_no_fallback: bool = False,
        free_only: bool = False,
    ):
        self.workspace = workspace
        self.default_provider = default_provider
        self.default_model = default_model
        self.default_no_fallback = default_no_fallback
        self.free_only = free_only
        self.config = load_config(workspace)
        self.secrets = load_secrets(workspace)
        execution = self.config.get("execution", {})
        self.allow_degraded = bool(execution.get("allow_degraded_local", False) if allow_degraded is None else allow_degraded)
        self.state_path = resolve_paths(workspace).state_file
        self.state: dict[str, Any] = read_json(self.state_path, {}) or {}
        self.providers = self._providers()

    def _providers(self) -> dict[str, TextProvider]:
        result: dict[str, TextProvider] = {}
        for name, cfg in self.config.get("providers", {}).items():
            if not cfg.get("enabled", False):
                continue
            kind = cfg.get("type")
            if kind == "gemini":
                result[name] = GeminiProvider(str(cfg.get("base_url")))
            elif kind == "ollama":
                result[name] = OllamaProvider(str(cfg.get("base_url")))
            elif kind == "openai_compatible":
                headers = {"HTTP-Referer": "https://github.com/niatifatah-art/Automated-Content-Empire", "X-Title": "ACE"} if name == "openrouter" else {}
                result[name] = OpenAICompatibleProvider(name, str(cfg.get("base_url")), extra_headers=headers)
        return result

    def credentials_for(self, provider: str) -> list[Credential]:
        if provider == "gemini":
            settings = self.config.get("credentials", {}).get("gemini", {})
            variables = list(settings.get("environment_variables", []))
            maximum = int(settings.get("maximum_credentials", 2))
            result: list[Credential] = []
            seen: set[str] = set()
            for variable in variables:
                value = self.secrets.get(variable)
                if not value or value in seen:
                    continue
                seen.add(value)
                display = "primary" if variable.endswith("PRIMARY") or variable == "GEMINI_API_KEY" else "backup" if variable.endswith("BACKUP") else variable.lower()
                result.append(Credential(display, value, provider))
                if len(result) >= maximum:
                    break
            return result
        cfg = self.config.get("providers", {}).get(provider, {})
        env = cfg.get("api_key_env")
        if env and self.secrets.get(str(env)):
            return [Credential("default", self.secrets[str(env)], provider)]
        return [Credential("none", "", provider)] if provider == "ollama" else []

    @staticmethod
    def _credential_key(provider: str, credential: str) -> str:
        return f"credential:{provider}:{credential}"

    @staticmethod
    def _route_key(provider: str, credential: str, model: str) -> str:
        return f"route:{provider}:{credential}:{model}"

    def _legacy_state(self, provider: str, credential: str) -> dict[str, Any]:
        return dict(self.state.get(f"{provider}:{credential}", {}))

    def _available(self, provider: str, credential: Credential, model: str) -> bool:
        credential_state = dict(self.state.get(self._credential_key(provider, credential.name), {}))
        legacy = self._legacy_state(provider, credential.name)
        # ACE 2.0 stored rate-limit cooldowns at credential scope.  Do not let
        # that old state block another Gemini model after upgrading.
        disabled = bool(credential_state.get("disabled", False))
        if legacy.get("last_category") in {"authentication", "permission"}:
            disabled = disabled or bool(legacy.get("disabled", False))
        if disabled:
            return False
        route_state = dict(self.state.get(self._route_key(provider, credential.name, model), {}))
        return float(route_state.get("cooldown_until", 0) or 0) <= time.time()

    def _mark_failure(self, provider: str, credential: Credential, model: str, failure: ProviderFailure) -> None:
        now = utc_now_iso()
        if failure.category in {"authentication", "permission"}:
            key = self._credential_key(provider, credential.name)
            current = dict(self.state.get(key, {}))
            current.update(
                {
                    "last_failure": now,
                    "last_category": failure.category,
                    "failure_count": int(current.get("failure_count", 0)) + 1,
                    "disabled": True,
                }
            )
            self.state[key] = current
        else:
            key = self._route_key(provider, credential.name, model)
            current = dict(self.state.get(key, {}))
            current.update(
                {
                    "last_failure": now,
                    "last_category": failure.category,
                    "failure_count": int(current.get("failure_count", 0)) + 1,
                }
            )
            if failure.category in {"rate_limit", "outage", "network"}:
                fallback = float(self.config.get("credentials", {}).get("gemini", {}).get("cooldown_seconds", 60))
                cooldown = failure.retry_after if failure.retry_after is not None else fallback
                current["cooldown_until"] = time.time() + max(1.0, float(cooldown))
            self.state[key] = current
        write_json(self.state_path, self.state)

    def _mark_success(self, provider: str, credential: Credential, model: str) -> None:
        credential_key = self._credential_key(provider, credential.name)
        credential_state = dict(self.state.get(credential_key, {}))
        credential_state.update({"last_success": utc_now_iso(), "failure_count": 0, "disabled": False})
        self.state[credential_key] = credential_state

        route_key = self._route_key(provider, credential.name, model)
        route_state = dict(self.state.get(route_key, {}))
        route_state.update({"last_success": utc_now_iso(), "failure_count": 0, "cooldown_until": 0})
        self.state[route_key] = route_state
        write_json(self.state_path, self.state)

    def _routes(self, task: str, provider: str | None, model: str | None) -> list[dict[str, Any]]:
        routes = list(self.config.get("routes", {}).get(task, self.config.get("routes", {}).get("script", [])))
        if provider:
            return [{"provider": provider, "model": model or "auto", "critical": True}]
        if model:
            routes = [{**route, "model": model} for route in routes]
        unique: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for route in routes:
            key = (str(route.get("provider")), str(route.get("model")))
            if key in seen:
                continue
            seen.add(key)
            unique.append(route)
        return unique

    def generate(
        self,
        task: str,
        prompt: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.4,
        max_output_tokens: int = 4096,
        json_mode: bool = False,
        system: str | None = None,
        no_fallback: bool = False,
    ) -> GenerationResult:
        provider = provider or self.default_provider
        model = model or self.default_model
        no_fallback = no_fallback or self.default_no_fallback
        routes = self._routes(task, provider, model)
        failures: list[str] = []

        for route in routes:
            provider_name = str(route.get("provider"))
            selected_model = str(route.get("model"))
            degraded = bool(route.get("degraded")) or not bool(self.config.get("providers", {}).get(provider_name, {}).get("cloud", False))
            if degraded and not self.allow_degraded:
                failures.append(f"{provider_name}/{selected_model}: skipped degraded local route")
                continue
            provider_config = self.config.get("providers", {}).get(provider_name, {})
            if self.free_only and provider_config.get("cost_tier") in {"paid", "mixed"}:
                failures.append(f"{provider_name}/{selected_model}: skipped paid route in free-only mode")
                continue
            instance = self.providers.get(provider_name)
            if not instance:
                failures.append(f"{provider_name}/{selected_model}: provider disabled or unavailable")
                continue
            credentials = self.credentials_for(provider_name)
            if not credentials:
                failures.append(f"{provider_name}/{selected_model}: no credential")
                continue

            for credential in credentials:
                if not self._available(provider_name, credential, selected_model):
                    failures.append(f"{provider_name}/{selected_model}/{credential.name}: cooldown or disabled")
                    continue
                request = GenerationRequest(task, prompt, selected_model, temperature, max_output_tokens, json_mode, system)
                try:
                    result = instance.generate(request, credential.value or None)
                    self._mark_success(provider_name, credential, selected_model)
                    return GenerationResult(
                        text=result.text,
                        provider=result.provider,
                        model=result.model,
                        credential_name=credential.name,
                        usage=result.usage,
                        degraded=result.degraded or degraded,
                    )
                except ProviderFailure as exc:
                    self._mark_failure(provider_name, credential, selected_model, exc)
                    failures.append(f"{provider_name}/{selected_model}/{credential.name}: {exc.category}: {exc}")
                    if no_fallback:
                        raise

            if no_fallback:
                break

        message = "No acceptable model route succeeded.\n" + "\n".join(f"- {item}" for item in failures)
        if not self.allow_degraded:
            message += "\nLocal fallback is intentionally disabled for quality-sensitive work. ACE tried every configured cloud model and credential first. Re-run with --allow-degraded only if you accept reduced quality."
        raise ProviderFailure(message, category="routing")

    def credential_status(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        now = time.time()
        configured_routes: dict[str, set[str]] = {}
        for route_list in self.config.get("routes", {}).values():
            for route in route_list:
                configured_routes.setdefault(str(route.get("provider")), set()).add(str(route.get("model")))

        for provider in self.providers:
            for credential in self.credentials_for(provider):
                credential_state = dict(self.state.get(self._credential_key(provider, credential.name), {}))
                legacy = self._legacy_state(provider, credential.name)
                model_cooldowns: dict[str, int] = {}
                latest_failure: tuple[str | None, str | None] = (credential_state.get("last_failure"), credential_state.get("last_category"))
                for model in configured_routes.get(provider, set()):
                    route_state = dict(self.state.get(self._route_key(provider, credential.name, model), {}))
                    until = float(route_state.get("cooldown_until", 0) or 0)
                    if until > now:
                        model_cooldowns[model] = max(1, round(until - now))
                    route_failure = route_state.get("last_failure")
                    if route_failure and (not latest_failure[0] or str(route_failure) > str(latest_failure[0])):
                        latest_failure = (str(route_failure), route_state.get("last_category"))
                if not latest_failure[0] and legacy.get("last_failure"):
                    latest_failure = (legacy.get("last_failure"), legacy.get("last_category"))
                disabled = bool(credential_state.get("disabled", False)) or (
                    legacy.get("last_category") in {"authentication", "permission"} and bool(legacy.get("disabled", False))
                )
                rows.append(
                    {
                        "provider": provider,
                        "credential": credential.name,
                        "configured": bool(credential.value) or provider == "ollama",
                        "available": not disabled,
                        "model_cooldowns_seconds": model_cooldowns,
                        "last_success": credential_state.get("last_success") or legacy.get("last_success"),
                        "last_failure": latest_failure[0],
                        "last_category": latest_failure[1],
                    }
                )
        return rows
