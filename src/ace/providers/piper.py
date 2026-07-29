from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ace.errors import ProviderRequestError, ProviderUnavailable


def generate(
    text: str,
    output: str | Path,
    *,
    model: str,
    workspace: str | Path,
) -> Path:
    executable = shutil.which("piper")
    if not executable:
        raise ProviderUnavailable("The 'piper' executable is not installed.")

    model_path = Path(model).expanduser()
    if not model_path.is_absolute():
        model_path = Path(workspace) / "models" / "piper" / model_path
    if not model_path.exists():
        raise ProviderUnavailable(f"Piper model not found: {model_path}")

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [executable, "--model", str(model_path), "--output_file", str(output_path)],
        input=text,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ProviderRequestError(
            f"Piper failed: {result.stderr.strip() or 'unknown error'}"
        )
    if not output_path.exists():
        raise ProviderRequestError("Piper completed without creating an audio file.")
    return output_path
