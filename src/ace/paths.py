from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ace.utils import ensure_dir


@dataclass(frozen=True)
class ACEPaths:
    config_root: Path
    data_root: Path
    cache_root: Path

    @property
    def config_file(self) -> Path:
        return self.config_root / "config.json"

    @property
    def secrets_file(self) -> Path:
        return self.config_root / "secrets.env"

    @property
    def accounts_dir(self) -> Path:
        return self.config_root / "accounts"

    @property
    def active_account_file(self) -> Path:
        return self.config_root / "active-account"

    @property
    def content_dir(self) -> Path:
        return self.data_root / "content"

    @property
    def account_assets_dir(self) -> Path:
        return self.data_root / "accounts"

    @property
    def cache_db(self) -> Path:
        return self.cache_root / "cache.sqlite3"

    @property
    def state_file(self) -> Path:
        return self.cache_root / "provider-state.json"

    def ensure(self) -> "ACEPaths":
        for path in (self.config_root, self.data_root, self.cache_root, self.accounts_dir, self.content_dir, self.account_assets_dir):
            ensure_dir(path)
        return self


def resolve_paths(workspace: str | Path | None = None) -> ACEPaths:
    root = workspace or os.environ.get("ACE_HOME")
    if root:
        base = Path(root).expanduser().resolve()
        return ACEPaths(base / "config", base / "data", base / "cache").ensure()
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    cache_home = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return ACEPaths(config_home / "ace", data_home / "ace", cache_home / "ace").ensure()
