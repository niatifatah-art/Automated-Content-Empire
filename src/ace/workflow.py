from __future__ import annotations

from pathlib import Path

from ace.content import generate, generate_pack
from ace.engines.voice import generate_voice
from ace.project import load, resolve, save_metadata


def run(
    project_path: str | Path,
    *,
    review: bool = True,
    voice: bool = False,
    force: bool = False,
    provider: str | None = None,
    model: str | None = None,
    no_fallback: bool = False,
    workspace: str | Path | None = None,
) -> list[Path]:
    project = resolve(project_path, workspace)
    metadata = load(project, workspace)
    output_dir = project / "content"
    output_dir.mkdir(parents=True, exist_ok=True)

    created: list[Path] = []
    if metadata.get("pack"):
        has_content = any(output_dir.glob("*.md"))
        if force or not has_content:
            results = generate_pack(
                str(metadata["platform"]),
                topic=str(metadata["topic"]),
                review=review,
                provider=provider,
                model=model,
                no_fallback=no_fallback,
                workspace=workspace,
                output_dir=output_dir,
                profile_slug=metadata.get("profile_slug"),
                no_profile=not bool(metadata.get("profile_slug")),
            )
            created.extend(result.path for result in results)
    else:
        output = output_dir / "main.md"
        if force or not output.exists():
            result = generate(
                str(metadata["platform"]),
                str(metadata["content_type"]),
                topic=str(metadata["topic"]),
                review=review,
                provider=provider,
                model=model,
                no_fallback=no_fallback,
                workspace=workspace,
                output=output,
                profile_slug=metadata.get("profile_slug"),
                no_profile=not bool(metadata.get("profile_slug")),
            )
            created.append(result.path)

    if voice:
        source = output_dir / "main.md"
        if not source.exists():
            candidates = sorted(output_dir.glob("*.md"))
            source = candidates[0] if candidates else source
        if source.exists():
            voice_path = project / "voice" / "voice.wav"
            if force or not voice_path.exists():
                generate_voice(
                    source.read_text(encoding="utf-8"),
                    voice_path,
                    workspace=workspace,
                )
                created.append(voice_path)

    metadata["status"] = "generated"
    metadata["last_run_outputs"] = [str(path.relative_to(project)) for path in created]
    save_metadata(project, metadata)
    return created
