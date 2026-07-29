from __future__ import annotations

from pathlib import Path

import pytest

from ace.accounts import create as create_account
from ace.config import initialize
from ace.storage import create_generation, update_metadata
from ace.utils import write_json


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    initialize(tmp_path, force=True)
    create_account("Test Creator", description="Technology explained clearly", workspace=tmp_path)
    return tmp_path


@pytest.fixture
def generation(workspace: Path) -> Path:
    folder = create_generation("youtube", "short", "Why passkeys matter", account_slug="test-creator", workspace=workspace)
    script = (
        "Passwords can be stolen by fake login pages. Passkeys keep the secret on your device. "
        "Your phone confirms you with Face ID or a fingerprint. The website gets proof instead of your reusable password. "
        "That makes ordinary phishing much harder. Try passkeys on an account that supports them."
    )
    (folder / "selected.md").write_text(script + "\n", encoding="utf-8")
    update_metadata(folder, final_provider="fixture", final_model="fixture", selected_candidate=1)
    write_json(folder / "evaluation.json", {"selected": 1})
    return folder
