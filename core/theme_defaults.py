# Install each bundled theme once. Runtime themes belong to the user.

from pathlib import Path

from .default_files import extract_defaults_once


def extract_theme_defaults(repo_root: str | Path) -> int:
    return extract_defaults_once(
        repo_root, "themes", ".theme-defaults.json", label="theme", log_prefix="Themes",
    )
