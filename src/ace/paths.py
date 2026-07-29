from __future__ import annotations

import os
from importlib import resources
from pathlib import Path


WORKSPACE_ENV = "ACE_HOME"
CONFIG_ENV = "ACE_CONFIG_HOME"
DATA_ENV = "ACE_DATA_HOME"
CACHE_ENV = "ACE_CACHE_HOME"


def _expanded(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def portable_root(explicit: str | Path | None = None) -> Path | None:
    if explicit is not None:
        return _expanded(explicit)
    configured = os.environ.get(WORKSPACE_ENV)
    return _expanded(configured) if configured else None


def config_home(explicit: str | Path | None = None) -> Path:
    portable = portable_root(explicit)
    if portable is not None:
        return portable / "config"
    configured = os.environ.get(CONFIG_ENV)
    if configured:
        return _expanded(configured)
    xdg = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return (xdg / "ace").expanduser().resolve()


def data_home(explicit: str | Path | None = None) -> Path:
    portable = portable_root(explicit)
    if portable is not None:
        return portable / "data"
    configured = os.environ.get(DATA_ENV)
    if configured:
        return _expanded(configured)
    xdg = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return (xdg / "ace").expanduser().resolve()


def cache_home(explicit: str | Path | None = None) -> Path:
    portable = portable_root(explicit)
    if portable is not None:
        return portable / "cache"
    configured = os.environ.get(CACHE_ENV)
    if configured:
        return _expanded(configured)
    xdg = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return (xdg / "ace").expanduser().resolve()


def workspace_root(explicit: str | Path | None = None) -> Path:
    """Compatibility root used for user-facing workspace messages.

    With ACE_HOME/--home this is a portable workspace. Otherwise it is the
    persistent ACE data directory; configuration remains under XDG config.
    """

    portable = portable_root(explicit)
    return portable if portable is not None else data_home()


def config_path(workspace: str | Path | None = None) -> Path:
    return config_home(workspace) / "config.json"


def model_catalog_path(workspace: str | Path | None = None) -> Path:
    return config_home(workspace) / "model_catalog.json"


def catalog_path(workspace: str | Path | None = None) -> Path:
    return config_home(workspace) / "content_catalog.json"


def secrets_path(workspace: str | Path | None = None) -> Path:
    return config_home(workspace) / "secrets.env"


def accounts_dir(workspace: str | Path | None = None) -> Path:
    """Permanent account identities (one brand across all enabled platforms)."""
    return config_home(workspace) / "accounts"


def profiles_dir(workspace: str | Path | None = None) -> Path:
    """Compatibility alias for the v0.x profile directory.

    New writes use :func:`accounts_dir`; loaders still inspect this legacy path
    so an upgrade never loses an existing account.
    """
    return config_home(workspace) / "profiles"


def account_data_dir(account_slug: str, workspace: str | Path | None = None) -> Path:
    return data_home(workspace) / "accounts" / account_slug


def prompts_dir(workspace: str | Path | None = None) -> Path:
    return config_home(workspace) / "prompts"


def data_dir(workspace: str | Path | None = None) -> Path:
    return data_home(workspace)


def content_dir(workspace: str | Path | None = None) -> Path:
    return data_home(workspace) / "content"


def projects_dir(workspace: str | Path | None = None) -> Path:
    return data_home(workspace) / "projects"


def assets_dir(workspace: str | Path | None = None) -> Path:
    return data_home(workspace) / "assets"


def logs_dir(workspace: str | Path | None = None) -> Path:
    return data_home(workspace) / "logs"


def models_dir(workspace: str | Path | None = None) -> Path:
    return data_home(workspace) / "models"


def recent_path(workspace: str | Path | None = None) -> Path:
    return data_home(workspace) / "last_generation.txt"


def resource_text(relative_path: str) -> str:
    resource = resources.files("ace.resources").joinpath(relative_path)
    return resource.read_text(encoding="utf-8")
