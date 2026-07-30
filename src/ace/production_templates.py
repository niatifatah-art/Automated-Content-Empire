from __future__ import annotations

from dataclasses import dataclass
from importlib import resources as importlib_resources
from pathlib import Path
from typing import Any, Iterable

import yaml

from ace.paths import resolve_paths


class TemplateError(ValueError):
    """Raised when a production template is missing, invalid, or incompatible."""


@dataclass(frozen=True, slots=True)
class ProductionTemplate:
    template_id: str
    version: str
    source: str
    manifest: dict[str, Any]

    @property
    def reference(self) -> str:
        return f"{self.template_id}@{self.version}"

    @property
    def name(self) -> str:
        identity = self.manifest.get("identity") or {}
        return str(identity.get("name") or self.template_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.template_id,
            "version": self.version,
            "reference": self.reference,
            "name": self.name,
            "source": self.source,
            "manifest": self.manifest,
        }


_REQUIRED_TOP_LEVEL = {
    "schema_version",
    "id",
    "version",
    "identity",
    "description",
    "best_use_cases",
    "audience",
    "selection",
    "controls",
    "workflow",
    "creative",
    "resources",
    "capabilities",
    "quality",
    "preview",
}


def _version_key(value: str) -> tuple[int, int, int, str]:
    core, _, suffix = str(value).partition("-")
    pieces = core.split(".")
    if len(pieces) != 3 or not all(piece.isdigit() for piece in pieces):
        raise TemplateError(f"Invalid semantic version: {value!r}")
    return int(pieces[0]), int(pieces[1]), int(pieces[2]), suffix


def _normalize_id(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("_", "-").replace(" ", "-")
    if not normalized or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in normalized):
        raise TemplateError(f"Invalid template id: {value!r}")
    return normalized


def validate_manifest(value: dict[str, Any], *, source: str = "<memory>") -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TemplateError(f"Template {source} must contain a YAML object.")
    missing = sorted(_REQUIRED_TOP_LEVEL - set(value))
    if missing:
        raise TemplateError(f"Template {source} is missing: {', '.join(missing)}")

    manifest = dict(value)
    manifest["id"] = _normalize_id(str(manifest["id"]))
    manifest["version"] = str(manifest["version"]).strip()
    _version_key(manifest["version"])

    if int(manifest.get("schema_version") or 0) != 1:
        raise TemplateError(f"Template {source} uses unsupported schema_version={manifest.get('schema_version')!r}.")

    identity = manifest.get("identity")
    if not isinstance(identity, dict) or not str(identity.get("name") or "").strip():
        raise TemplateError(f"Template {source} needs identity.name.")

    controls = manifest.get("controls")
    if not isinstance(controls, dict):
        raise TemplateError(f"Template {source} needs a controls object.")
    for section in ("locked", "overridable", "adaptive"):
        if not isinstance(controls.get(section), dict):
            raise TemplateError(f"Template {source} needs controls.{section}.")

    capabilities = manifest.get("capabilities")
    if not isinstance(capabilities, dict):
        raise TemplateError(f"Template {source} needs a capabilities object.")
    for section in ("required", "optional"):
        values = capabilities.get(section)
        if not isinstance(values, list) or not all(isinstance(item, str) and item.strip() for item in values):
            raise TemplateError(f"Template {source} needs capabilities.{section} as a string list.")

    workflow = manifest.get("workflow")
    if not isinstance(workflow, dict) or not isinstance(workflow.get("stages"), list) or not workflow["stages"]:
        raise TemplateError(f"Template {source} needs workflow.stages.")

    selection = manifest.get("selection")
    if not isinstance(selection, dict):
        raise TemplateError(f"Template {source} needs a selection object.")
    for key in ("keywords", "content_types"):
        if not isinstance(selection.get(key), list):
            raise TemplateError(f"Template {source} needs selection.{key} as a list.")

    return manifest


def _load_yaml(text: str, *, source: str) -> ProductionTemplate:
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise TemplateError(f"Invalid YAML in {source}: {exc}") from exc
    manifest = validate_manifest(raw, source=source)
    return ProductionTemplate(manifest["id"], manifest["version"], source, manifest)


def _walk_traversable(root: Any) -> Iterable[Any]:
    for item in root.iterdir():
        if item.is_dir():
            yield from _walk_traversable(item)
        elif item.name in {"template.yaml", "template.yml"}:
            yield item


def _builtin_templates() -> list[ProductionTemplate]:
    root = importlib_resources.files("ace.data").joinpath("templates")
    output: list[ProductionTemplate] = []
    if not root.is_dir():
        return output
    for item in _walk_traversable(root):
        source = f"builtin:{item}"
        output.append(_load_yaml(item.read_text(encoding="utf-8"), source=source))
    return output


def _filesystem_templates(root: Path, *, label: str) -> list[ProductionTemplate]:
    output: list[ProductionTemplate] = []
    if not root.exists():
        return output
    for path in sorted(root.rglob("template.y*ml")):
        if not path.is_file():
            continue
        output.append(_load_yaml(path.read_text(encoding="utf-8"), source=f"{label}:{path}"))
    return output


def discover(workspace: str | Path | None = None, *, include_project: bool = True) -> list[ProductionTemplate]:
    """Discover immutable built-in, user, and project templates.

    Precedence is project > user > built-in for an identical id/version. Released
    versions are never overwritten on disk; this precedence only controls which
    copy ACE resolves when the same reference is intentionally shadowed.
    """

    paths = resolve_paths(workspace)
    candidates = [*_builtin_templates(), *_filesystem_templates(paths.config_root / "templates", label="user")]
    if include_project:
        candidates.extend(_filesystem_templates(Path.cwd() / "templates", label="project"))

    precedence = {"builtin": 0, "user": 1, "project": 2}
    selected: dict[tuple[str, str], ProductionTemplate] = {}
    for item in candidates:
        key = (item.template_id, item.version)
        current = selected.get(key)
        current_kind = current.source.split(":", 1)[0] if current else ""
        item_kind = item.source.split(":", 1)[0]
        if current is None or precedence.get(item_kind, 0) >= precedence.get(current_kind, 0):
            selected[key] = item
    return sorted(selected.values(), key=lambda item: (item.template_id, _version_key(item.version)))


def registry(workspace: str | Path | None = None) -> dict[str, list[ProductionTemplate]]:
    output: dict[str, list[ProductionTemplate]] = {}
    for item in discover(workspace):
        output.setdefault(item.template_id, []).append(item)
    for values in output.values():
        values.sort(key=lambda item: _version_key(item.version), reverse=True)
    return output


def resolve(reference: str, workspace: str | Path | None = None) -> ProductionTemplate:
    template_id, separator, requested_version = str(reference or "").strip().partition("@")
    template_id = _normalize_id(template_id)
    versions = registry(workspace).get(template_id, [])
    if not versions:
        raise TemplateError(f"Unknown production template: {template_id}")
    if not separator:
        return versions[0]
    for item in versions:
        if item.version == requested_version:
            return item
    available = ", ".join(item.version for item in versions)
    raise TemplateError(f"Template {template_id!r} has no version {requested_version!r}. Available: {available}")


def select(topic: str, content_type: str = "short", workspace: str | Path | None = None) -> ProductionTemplate:
    """Select the best installed production identity without making it mandatory."""

    words = {word.strip(".,!?()[]{}\"'").lower() for word in str(topic).split() if word.strip()}
    best: tuple[float, ProductionTemplate] | None = None
    for versions in registry(workspace).values():
        item = versions[0]
        selection = item.manifest.get("selection") or {}
        keywords = {str(value).lower() for value in selection.get("keywords", [])}
        content_types = {str(value).lower() for value in selection.get("content_types", [])}
        score = float(len(words & keywords) * 3)
        if str(content_type).lower() in content_types:
            score += 2
        if selection.get("default"):
            score += 0.25
        candidate = (score, item)
        if best is None or candidate[0] > best[0] or (candidate[0] == best[0] and item.template_id < best[1].template_id):
            best = candidate
    if best is None:
        raise TemplateError("No production templates are installed.")
    return best[1]


def effective_controls(
    template: ProductionTemplate,
    *,
    look: str | None = None,
    media: str | None = None,
    memes: str | None = None,
    quality: str | None = None,
) -> dict[str, Any]:
    """Merge legacy flags into template controls without violating locked identity."""

    controls = template.manifest["controls"]
    effective: dict[str, Any] = {
        **dict(controls.get("adaptive") or {}),
        **dict(controls.get("overridable") or {}),
        **dict(controls.get("locked") or {}),
    }
    requested = {
        "creative_style": look,
        "media_mode": media,
        "meme_mode": memes,
        "quality_mode": quality,
    }
    overridable = controls.get("overridable") or {}
    locked = controls.get("locked") or {}
    ignored: dict[str, Any] = {}
    for key, value in requested.items():
        if value is None:
            continue
        if key in locked:
            ignored[key] = value
            continue
        if key in overridable or key in controls.get("adaptive", {}):
            effective[key] = value
        else:
            # Legacy compatibility: unknown controls remain accepted but are
            # explicitly recorded instead of silently changing template identity.
            effective[key] = value
    effective["ignored_locked_overrides"] = ignored
    return effective


def search(query: str, workspace: str | Path | None = None) -> list[ProductionTemplate]:
    terms = {item.lower() for item in str(query).split() if item.strip()}
    results: list[tuple[int, ProductionTemplate]] = []
    for versions in registry(workspace).values():
        item = versions[0]
        manifest = item.manifest
        haystack = " ".join(
            [
                item.template_id,
                item.name,
                str(manifest.get("description") or ""),
                *[str(value) for value in manifest.get("best_use_cases", [])],
                *[str(value) for value in (manifest.get("selection") or {}).get("keywords", [])],
            ]
        ).lower()
        score = sum(term in haystack for term in terms)
        if not terms or score:
            results.append((score, item))
    return [item for _, item in sorted(results, key=lambda row: (-row[0], row[1].template_id))]
