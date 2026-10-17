# User-editable node designs. This module reads only this pack's theme folders.
import json
import re
from pathlib import Path
from typing import Any

THEMES_DIR = Path(__file__).resolve().parents[1] / "themes"
MAX_THEME_BYTES = 128 * 1024
MAX_THEME_FILES = 256
MAX_LABEL_LENGTH = 80
MIN_LABEL_CHARACTER = 32
_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
_HEX = r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]|[0-9a-fA-F]{3}(?:[0-9a-fA-F]{2})?)?"
_COLOR = re.compile(rf"(?:{_HEX}|transparent)\Z")
_OPAQUE = re.compile(r"#[0-9a-fA-F]{6}\Z")
_LENGTH = r"(?:0|[0-9]{1,3}(?:\.[0-9]{1,2})?px)"
_SHADOW = re.compile(
    rf"(?:none|{_LENGTH} {_LENGTH} {_LENGTH} {_HEX}(?:, {_LENGTH} {_LENGTH} {_LENGTH} {_HEX}){{0,3}})\Z",
)
_SHADOW_KEYS = {"selected-shadow", "hover-shadow", "menu-shadow", "dialog-shadow"}
_COLOR_KEYS = {
    "text", "muted", "label", "error", "success", "warning", "danger", "accent",
    "control-border", "control-bg", "control-hover", "control-selected",
    "control-strong", "control-primary", "input-bg", "input-border",
    "select-border", "select-bg", "select-hover-border", "select-text",
    "muted-accent", "ratio-bg", "bar-bg", "bar-border", "bar-text", "pill-border",
    "selected-border", "selected-text", "selected-bg", "bar-hover", "bar-focus",
    "divider", "row-bg", "menu-bg", "menu-border", "option-bg", "dialog-border",
    "backdrop",
}
_CATEGORIES = {"loader", "text", "image", "pipe", "router", "video", "folder", "bridge"}


def valid_design_id(value: Any) -> bool:
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def _validate_node_colors(node: Any) -> None:
    if not isinstance(node, dict) or set(node) != {"background", "title", "routing_background", "category_titles"}:
        raise ValueError("Invalid node color fields")
    titles = node["category_titles"]
    if not isinstance(titles, dict) or set(titles) - _CATEGORIES:
        raise ValueError("Unknown node title category")
    if any(not isinstance(v, str) or not _OPAQUE.fullmatch(v)
           for v in [node["background"], node["title"], node["routing_background"], *titles.values()]):
        raise ValueError("Node colors must be opaque six-digit hex colors")


def _validate_tokens(tokens: Any) -> None:
    if not isinstance(tokens, dict) or set(tokens) != _COLOR_KEYS | _SHADOW_KEYS | {"pill-radius", "color-scheme"}:
        raise ValueError("Missing or unsupported tokens; copy a complete bundled theme")
    for key, value in tokens.items():
        if not isinstance(value, str):
            raise TypeError(f"Token {key} must be a string")
        if key in _COLOR_KEYS:
            valid = _COLOR.fullmatch(value)
        elif key in _SHADOW_KEYS:
            valid = _SHADOW.fullmatch(value)
        elif key == "pill-radius":
            valid = re.fullmatch(_LENGTH, value)
        else:
            valid = value in {"dark", "light"}
        if not valid:
            raise ValueError(f"Invalid value for token {key}")


def _validate_theme(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or set(data) != {"version", "label", "node", "tokens"}:
        raise ValueError("Expected version, label, node and tokens fields")
    if type(data["version"]) is not int or data["version"] != 1:
        raise ValueError("Unsupported theme format (expected version 1)")
    label = data["label"]
    if (not isinstance(label, str) or not label.strip() or len(label) > MAX_LABEL_LENGTH
            or any(ord(c) < MIN_LABEL_CHARACTER for c in label)):
        raise ValueError("Label must be a nonempty string of at most 80 characters")
    _validate_node_colors(data["node"])
    _validate_tokens(data["tokens"])
    return data


def _theme_files(directory: Path) -> list[Path]:
    if directory.is_symlink():
        raise ValueError("Theme folders must not be symlinks")
    if not directory.exists():
        return []
    files = sorted(directory.glob("*.json"))
    if len(files) > MAX_THEME_FILES:
        raise ValueError(f"Too many themes (maximum {MAX_THEME_FILES})")
    return files


def _read_theme(path: Path) -> dict[str, Any]:
    if not valid_design_id(path.stem):
        raise ValueError("Use a lowercase filename with letters, digits, hyphens or underscores")
    if path.is_symlink() or not path.is_file():
        raise ValueError("Theme must be a regular file")
    with path.open("rb") as handle:
        raw = handle.read(MAX_THEME_BYTES + 1)
    if len(raw) > MAX_THEME_BYTES:
        raise ValueError("Theme exceeds the size limit")
    return _validate_theme(json.loads(raw))


def load_node_designs() -> dict[str, Any]:
    # Read only on startup/settings requests. No file watcher or per-node lookup.
    themes: dict[str, Any] = {}
    errors: list[str] = []
    for directory in (THEMES_DIR, THEMES_DIR / "custom"):
        try:
            files = _theme_files(directory)
        except OSError:
            errors.append(f"{directory.name}: could not list theme files")
            continue
        except ValueError as error:
            errors.append(f"{directory.name}: {error}")
            continue
        for path in files:
            name = path.relative_to(THEMES_DIR).as_posix()
            try:
                themes[path.stem] = _read_theme(path)
            except (OSError, UnicodeError, json.JSONDecodeError):
                errors.append(f"{name}: could not read a JSON theme")
            except (TypeError, ValueError) as error:
                errors.append(f"{name}: {error}")
    return {"themes": themes, "errors": errors}


def available_node_design(value: Any) -> bool:
    return valid_design_id(value) and value in load_node_designs()["themes"]
