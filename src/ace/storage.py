from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ace.paths import cache_home, content_dir, data_home, recent_path


def slugify(value: str, limit: int = 64) -> str:
    slug = re.sub(r"[^\w]+", "-", value.lower(), flags=re.UNICODE).replace("_", "-").strip("-")
    return slug[:limit].rstrip("-") or "content"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def generation_id(topic: str) -> str:
    return f"{_timestamp()}-{slugify(topic)}"


def create_generation_dir(
    profile_slug: str,
    platform: str,
    content_type: str,
    topic: str,
    workspace: str | Path | None = None,
) -> Path:
    folder = content_dir(workspace) / profile_slug / platform / content_type / generation_id(topic)
    for relative in (
        "candidates",
        "research/references",
        "resources/publishable",
        "resources/attribution-required",
        "resources/reference-only",
        "resources/generated",
        "resources/blocked",
        "licenses",
        "quality",
        "script",
        "revisions",
        "voice",
        "subtitles",
        "editing",
        "thumbnail",
        "exports",
        "temp",
    ):
        (folder / relative).mkdir(parents=True, exist_ok=True)
    recent_path(workspace).parent.mkdir(parents=True, exist_ok=True)
    recent_path(workspace).write_text(str(folder.resolve()) + "\n", encoding="utf-8")
    return folder


def last_generation(workspace: str | Path | None = None) -> Path:
    pointer = recent_path(workspace)
    if not pointer.exists():
        raise FileNotFoundError("No ACE generation has been created yet.")
    path = Path(pointer.read_text(encoding="utf-8").strip())
    if not path.exists():
        raise FileNotFoundError(f"The recorded generation no longer exists: {path}")
    return path


def resolve_generation(value: str | Path, workspace: str | Path | None = None) -> Path:
    if str(value).lower() == "last":
        return last_generation(workspace)
    path = Path(value).expanduser()
    if path.exists():
        return path.resolve()
    matches = list(content_dir(workspace).glob(f"*/*/*/{value}"))
    if len(matches) == 1:
        return matches[0].resolve()
    raise FileNotFoundError(f"Generation not found: {value}")


def write_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def save_generation(
    folder: Path,
    text: str,
    *,
    metadata: dict[str, Any],
    candidates: list[str] | None = None,
    selected_index: int = 0,
    evaluation: dict[str, Any] | None = None,
    profile_snapshot: dict[str, Any] | None = None,
    prompt: str | None = None,
) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    selected = folder / "selected.md"
    selected.write_text(text.rstrip() + "\n", encoding="utf-8")
    if prompt is not None:
        (folder / "prompt.txt").write_text(prompt.rstrip() + "\n", encoding="utf-8")
    if candidates:
        candidate_dir = folder / "candidates"
        candidate_dir.mkdir(exist_ok=True)
        for index, candidate in enumerate(candidates, 1):
            (candidate_dir / f"candidate-{index:02d}.md").write_text(candidate.rstrip() + "\n", encoding="utf-8")
    metadata = {**metadata, "selected_candidate": selected_index + 1, "generation_folder": str(folder)}
    write_json(folder / "metadata.json", metadata)
    if evaluation is not None:
        write_json(folder / "evaluation.json", evaluation)
    if profile_snapshot is not None:
        write_json(folder / "profile-snapshot.json", profile_snapshot)
        try:
            import yaml
            (folder / "profile-snapshot.yaml").write_text(
                yaml.safe_dump(profile_snapshot, sort_keys=False, allow_unicode=True, width=100),
                encoding="utf-8",
            )
        except Exception:
            pass
    return selected


def save_content(
    platform: str,
    content_type: str,
    topic: str,
    text: str,
    *,
    workspace: str | Path | None = None,
    output: str | Path | None = None,
    metadata: dict[str, Any] | None = None,
) -> Path:
    """Compatibility API.

    New ACE generations use a dedicated folder. An explicit output still writes
    exactly that file for scripts and integrations that depend on the old API.
    """
    if output is not None:
        path = Path(output).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text.rstrip() + "\n", encoding="utf-8")
        if metadata is not None:
            write_json(path.with_suffix(".json"), metadata)
        return path
    profile_slug = str((metadata or {}).get("profile_slug") or "no-profile")
    folder = create_generation_dir(profile_slug, platform, content_type, topic, workspace)
    return save_generation(folder, text, metadata=metadata or {})


def create_pack_dir(
    platform: str,
    topic: str,
    workspace: str | Path | None = None,
    profile_slug: str = "no-profile",
) -> Path:
    folder = content_dir(workspace) / profile_slug / platform / "pack" / generation_id(topic)
    folder.mkdir(parents=True, exist_ok=True)
    recent_path(workspace).parent.mkdir(parents=True, exist_ok=True)
    recent_path(workspace).write_text(str(folder.resolve()) + "\n", encoding="utf-8")
    return folder


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def directory_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return total
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def usage(workspace: str | Path | None = None) -> dict[str, int]:
    return {
        "data": directory_size(data_home(workspace)),
        "cache": directory_size(cache_home(workspace)),
        "content": directory_size(content_dir(workspace)),
    }


def cleanup(
    workspace: str | Path | None = None,
    *,
    retention_days: int = 7,
    preview: bool = False,
) -> list[Path]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    targets: list[Path] = []
    for folder in content_dir(workspace).glob("*/*/*/*"):
        if (folder / ".preserve").exists():
            continue
        cleanup_paths = [folder / "temp", folder / "candidates"]
        cleanup_paths.extend(path for path in folder.glob("extras/*/candidates") if path.is_dir())
        for path in cleanup_paths:
            if not path.exists():
                continue
            try:
                modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            except OSError:
                continue
            if modified < cutoff:
                targets.append(path)
    cache = cache_home(workspace)
    if cache.exists():
        for child in cache.iterdir():
            try:
                modified = datetime.fromtimestamp(child.stat().st_mtime, timezone.utc)
            except OSError:
                continue
            if modified < cutoff:
                targets.append(child)
    if not preview:
        for path in targets:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
    return targets


def preserve(generation: str | Path, workspace: str | Path | None = None) -> Path:
    folder = resolve_generation(generation, workspace)
    marker = folder / ".preserve"
    marker.write_text("Preserve this generation from automatic cleanup.\n", encoding="utf-8")
    return marker


def save(content_type: str, text: str) -> Path:
    return save_content("legacy", content_type, content_type, text)
