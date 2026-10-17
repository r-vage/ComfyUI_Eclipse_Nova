# Migration module for ComfyUI_Eclipse.
#
# Handles:
# - Extracting .example files with smart update support (hash-based)
# - Renaming legacy Eclipse-owned config in place
# - Cleaning extracted companion configuration after ownership transfer

import hashlib
import json
import os
import platform
import shutil
from typing import Dict

from .json_store import JsonStoreError, read_json_object, update_json_object
from .logger import log
from .theme_defaults import extract_theme_defaults

_LOG_PREFIX = "Migration"
_MIGRATED_MARKER = ".migrated"
_MANIFEST_FILE = ".manifest.json"
_COMPANION_MARKER_VERSION = 2
_SMART_MODEL_LOADER_KEYS = {
    "civitai_api_key",
    "allow_legacy_model_formats",
}
_SMART_LM_LOADER_KEYS = {
    "llm_models_path",
    "llm_models_absolute_path",
    "few_shot_training_file",
}
_SHARED_COMPANION_KEYS = {
    "hf_token",
    "retry_download_attempts",
}
_REMOVED_ECLIPSE_KEYS = {
    "gemini_api_key", "danbooru_user_id", "danbooru_login", "danbooru_api_key",
    "danbooru_credentials",
}


# ============================================================================
# File hashing
# ============================================================================


def _file_hash(path: str) -> str:
    # Compute SHA-256 hash of a file's contents.
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ============================================================================
# Manifest (hash tracking for smart updates)
# ============================================================================


def _load_manifest(defaults_dir: str) -> Dict[str, str]:
    # Load the manifest that tracks which .example hash was last extracted.
    # Returns dict mapping relative path (without .example) → hash string.
    manifest_path = os.path.join(defaults_dir, _MANIFEST_FILE)
    if not os.path.isfile(manifest_path):
        return {}
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_manifest(defaults_dir: str, manifest: Dict[str, str]) -> None:
    # Save the manifest file. Entries are sorted for stable diffs.
    manifest_path = os.path.join(defaults_dir, _MANIFEST_FILE)
    try:
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)
    except OSError as e:
        log.warning(_LOG_PREFIX, f"Could not save manifest: {e}")


# ============================================================================
# .example file extraction (with smart update support)
# ============================================================================


def extract_all_example_files(repo_root: str) -> int:
    # Extract .example files from root .defaults/ folder to their repo locations.
    # The .defaults/ folder mirrors the repo structure:
    #   .defaults/config.json.example        → config.json
    #   .defaults/patterns/*.json.example     → patterns/*.json
    #   .defaults/prompts/**/*.txt.example    → prompts/**/*.txt
    #   .defaults/styles/*.csv.example        → styles/*.csv
    #   .defaults/wildcards/*.txt.example     → wildcards/*.txt
    #
    # Smart update behavior:
    #   - New files (target doesn't exist) → extract and record hash
    #   - Updated .example (hash changed) + unmodified target → auto-update
    #   - Updated .example + user-modified target → skip (preserve edits)
    #   - Unchanged .example → skip
    #
    # Args:
    #     repo_root: Path to the ComfyUI_Eclipse repo root
    #
    # Returns:
    #     Total number of files extracted or updated
    defaults_path = os.path.join(repo_root, ".defaults")
    if not os.path.isdir(defaults_path):
        return 0

    _hide_on_windows(defaults_path)
    theme_count = extract_theme_defaults(repo_root)
    extracted, updated = _extract_defaults_dir(defaults_path, repo_root)
    if extracted > 0:
        log.msg(_LOG_PREFIX, f"Extracted {extracted} new default file(s)")
    if updated > 0:
        log.msg(_LOG_PREFIX, f"Updated {updated} default file(s) (unmodified by user)")
    return theme_count + extracted + updated


def _hide_on_windows(path: str) -> None:
    # Set the Windows hidden attribute on a file/folder.
    # No-op on Linux/macOS (dot-prefix already hides it).
    if platform.system() != "Windows":
        return
    try:
        import ctypes

        windll = getattr(ctypes, "windll", None)
        if windll is None:
            return
        FILE_ATTRIBUTE_HIDDEN = 0x02
        attrs = windll.kernel32.GetFileAttributesW(path)
        if attrs != -1 and not (attrs & FILE_ATTRIBUTE_HIDDEN):
            windll.kernel32.SetFileAttributesW(path, attrs | FILE_ATTRIBUTE_HIDDEN)
    except Exception:
        pass


def _extract_defaults_dir(defaults_dir: str, output_dir: str) -> tuple:
    # Extract and smart-update .example files from a .defaults/ directory.
    # Walks recursively, preserving subdirectory structure.
    # Strips the .example suffix to create the usable file.
    #
    # Smart update logic per file:
    #   1. Target doesn't exist → extract, record hash in manifest
    #   2. Target exists, no manifest entry → record current .example hash
    #      (assume user has the file, don't overwrite — backward compat for
    #      users who installed before the manifest existed)
    #   3. Target exists, manifest entry matches current .example hash →
    #      no update needed (skip)
    #   4. Target exists, manifest entry differs from current .example hash →
    #      .example was updated (developer pushed changes):
    #      a. Target hash matches OLD manifest hash → user didn't modify →
    #         safe to auto-update
    #      b. Target hash differs from OLD manifest hash → user modified →
    #         skip (preserve their edits)
    #
    # Args:
    #     defaults_dir: The .defaults/ directory containing .example files
    #     output_dir: The parent folder where extracted files are written
    #
    # Returns:
    #     Tuple of (extracted_count, updated_count)
    manifest = _load_manifest(defaults_dir)
    extracted = 0
    updated = 0
    manifest_changed = False
    valid_manifest_keys = set()

    marker = os.path.join(output_dir, _MIGRATED_MARKER)
    migrated = os.path.exists(marker)

    for root, _dirs, files in os.walk(defaults_dir):
        for f in sorted(files):
            if not f.endswith(".example"):
                continue

            example_path = os.path.join(root, f)
            # Compute relative path from .defaults/ dir, strip .example suffix
            rel_path = os.path.relpath(example_path, defaults_dir)
            target_name = rel_path[:-8]  # Strip ".example"
            target_path = os.path.join(output_dir, target_name)
            # Use forward slashes for consistent manifest keys across platforms
            manifest_key = target_name.replace(os.sep, "/")
            valid_manifest_keys.add(manifest_key)

            example_hash = _file_hash(example_path)

            if manifest_key.startswith("themes/"):
                # Themes are installed once by extract_theme_defaults. The
                # manifest records shipped hashes, not permission to update.
                if manifest.get(manifest_key) != example_hash:
                    manifest[manifest_key] = example_hash
                    manifest_changed = True
                continue

            if not os.path.exists(target_path):
                # Case 1: New file — extract it
                # If migrated is True and the file is already in the manifest,
                # it means the user deleted it intentionally. Preserve their deletion.
                if migrated and manifest_key in manifest:
                    continue

                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                shutil.copy2(example_path, target_path)
                manifest[manifest_key] = example_hash
                manifest_changed = True
                extracted += 1

            elif manifest_key not in manifest:
                # Case 2: File exists but no manifest entry (pre-manifest install).
                # Record current .example hash so future updates can be tracked.
                # Don't overwrite — the user may have customized the file.
                manifest[manifest_key] = example_hash
                manifest_changed = True

            elif manifest[manifest_key] == example_hash:
                # Case 3: .example unchanged since last extraction — nothing to do
                pass

            else:
                # Case 4: .example was updated (developer pushed changes)
                old_example_hash = manifest[manifest_key]
                target_hash = _file_hash(target_path)

                if target_hash == old_example_hash:
                    # Preserve removed feature-owned config values during pack
                    # extraction. The field-level merge below adds any new
                    # Eclipse defaults without deleting existing keys.
                    if manifest_key != "config.json":
                        shutil.copy2(example_path, target_path)
                        updated += 1
                    manifest[manifest_key] = example_hash
                    manifest_changed = True
                    if manifest_key == "config.json":
                        log.debug(
                            _LOG_PREFIX,
                            "Preserved existing config values while updating defaults",
                        )
                    else:
                        log.debug(_LOG_PREFIX, f"Auto-updated: {target_name}")
                else:
                    # Case 4b: User modified the file — preserve their edits
                    manifest[manifest_key] = example_hash
                    manifest_changed = True
                    log.debug(_LOG_PREFIX, f"Skipped (user-modified): {target_name}")

    stale_manifest_keys = set(manifest) - valid_manifest_keys
    if stale_manifest_keys:
        for stale_key in stale_manifest_keys:
            del manifest[stale_key]
        manifest_changed = True

    if manifest_changed:
        _save_manifest(defaults_dir, manifest)

    return extracted, updated


# ============================================================================
# Wildcard prompt integration
# ============================================================================


def _create_windows_junction(source_dir: str, link_dir: str) -> None:
    # CPython's native helper creates the same privilege-free NTFS junction as
    # `mklink /J` without launching cmd.exe or interpolating paths into a shell.
    try:
        import _winapi  # type: ignore
    except ImportError as error:
        raise OSError("Native Windows junction support is unavailable") from error
    _winapi.CreateJunction(source_dir, link_dir)


def create_wildcards_junction(repo_root: str, comfyui_root: str) -> bool:
    # Own only Nova's link; the original pack may still use smart_prompt.
    source_dir = os.path.join(repo_root, "prompts")
    link_dir = os.path.join(comfyui_root, "models", "wildcards", "smart_prompt_nova")

    if not os.path.isdir(source_dir):
        log.warning(_LOG_PREFIX, f"Wildcard prompt source not found: {source_dir}")
        return False

    is_junction = _is_junction(link_dir)
    is_symlink = os.path.islink(link_dir)
    if is_symlink or is_junction:
        if _paths_reference_same_directory(link_dir, source_dir):
            return True
        try:
            if is_junction:
                os.rmdir(link_dir)
            else:
                os.unlink(link_dir)
        except OSError as error:
            log.warning(
                _LOG_PREFIX,
                f"Could not replace outdated wildcard prompt link: {type(error).__name__}",
            )
            return False
        log.msg(_LOG_PREFIX, "Removed outdated wildcards/smart_prompt_nova link")
    elif os.path.lexists(link_dir):
        log.warning(
            _LOG_PREFIX,
            "Cannot create wildcards/smart_prompt_nova link because that path already exists",
        )
        return False

    try:
        os.makedirs(os.path.dirname(link_dir), exist_ok=True)
        if platform.system() == "Windows":
            _create_windows_junction(source_dir, link_dir)
            link_kind = "junction"
        else:
            os.symlink(source_dir, link_dir, target_is_directory=True)
            link_kind = "symlink"
    except (AttributeError, OSError) as error:
        log.warning(
            _LOG_PREFIX,
            f"Could not create wildcard prompt link: {type(error).__name__}",
        )
        return False

    log.msg(
        _LOG_PREFIX,
        f"Created {link_kind}: wildcards/smart_prompt_nova → Eclipse Nova prompts",
    )
    return True


def _paths_reference_same_directory(path: str, target: str) -> bool:
    # samefile follows Linux symlinks and Windows junctions, comparing the
    # resulting filesystem objects rather than their textual path spelling.
    try:
        return os.path.samefile(path, target)
    except OSError:
        return False


def _is_junction(path: str) -> bool:
    # os.path.isjunction is available on current Python versions; retain a
    # conservative Windows fallback for older supported environments.
    isjunction = getattr(os.path, "isjunction", None)
    if callable(isjunction):
        return bool(isjunction(path))
    if platform.system() != "Windows":
        return False
    try:
        import ctypes

        windll = getattr(ctypes, "windll", None)
        if windll is None:
            return False
        file_attribute_reparse_point = 0x0400
        attrs = windll.kernel32.GetFileAttributesW(path)
        return attrs != -1 and bool(attrs & file_attribute_reparse_point)
    except (AttributeError, OSError):
        return False


# ============================================================================
# Config field-level merge (add missing keys without overwriting)
# ============================================================================


def _merge_config_fields(repo_root: str) -> None:
    # Ensure config.json has all keys defined in .defaults/config.json.example.
    # Adds missing keys with their default values. Never overwrites existing keys.
    # This handles new Eclipse fields when .example extraction preserves a
    # user-modified configuration file.
    config_path = os.path.join(repo_root, "config.json")
    example_path = os.path.join(repo_root, ".defaults", "config.json.example")
    if not os.path.isfile(config_path) or not os.path.isfile(example_path):
        return
    try:
        with open(example_path, "r", encoding="utf-8") as default_file:
            default_config = json.load(default_file)
        if not isinstance(default_config, dict):
            raise ValueError("default config root must be an object")
    except (json.JSONDecodeError, OSError, ValueError) as e:
        log.warning(_LOG_PREFIX, f"Could not read config for field merge: {e}")
        return

    added = []
    try:
        def merge_defaults(user_config: dict) -> None:
            for key, value in default_config.items():
                if key not in user_config:
                    user_config[key] = value
                    if key != "_comments":
                        added.append(key)

            default_comments = default_config.get("_comments")
            user_comments = user_config.get("_comments")
            if isinstance(default_comments, dict) and isinstance(user_comments, dict):
                for comment_key, comment_value in default_comments.items():
                    if comment_key not in user_comments:
                        user_comments[comment_key] = comment_value

        update_json_object(config_path, merge_defaults, private=True)
        if added:
            log.msg(
                _LOG_PREFIX,
                f"Added {len(added)} new config field(s): {', '.join(added)}",
            )
    except (JsonStoreError, OSError) as e:
        log.warning(_LOG_PREFIX, f"Could not write merged config: {e}")


# ============================================================================
# Extracted companion configuration cleanup
# ============================================================================


def _confirmed_companion_keys(marker_paths: tuple[str, ...]) -> set[str]:
    # Return only key names confirmed by a current, value-free companion marker.
    for marker_path in marker_paths:
        if not os.path.isfile(marker_path) or os.path.islink(marker_path):
            continue
        try:
            with open(marker_path, "r", encoding="utf-8") as marker_file:
                marker = json.load(marker_file)
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(marker, dict):
            continue
        examined = marker.get("examined_eclipse_config_keys")
        version = marker.get("version")
        if (
            isinstance(version, int)
            and not isinstance(version, bool)
            and version >= _COMPANION_MARKER_VERSION
            and marker.get("completed") is True
            and isinstance(examined, list)
            and all(isinstance(key, str) for key in examined)
        ):
            return set(examined)
    return set()


def cleanup_extracted_companion_config(repo_root: str) -> set[str]:
    # Remove extracted fields only after their owning companion confirms that it
    # examined the Eclipse source config. Shared fields require both companions.
    custom_nodes = os.path.dirname(repo_root)
    loader_keys = _confirmed_companion_keys(
        tuple(
            os.path.join(custom_nodes, name, ".eclipse_loader_data_migrated")
            for name in ("ComfyUI_SmartModelLoader", "comfyui_smartmodelloader")
        )
    )
    smart_lm_keys = _confirmed_companion_keys(
        tuple(
            os.path.join(custom_nodes, name, ".smartllm-migration.json")
            for name in ("ComfyUI_SmartLLM", "comfyui_smartllm")
        )
    )

    removable = set(_REMOVED_ECLIPSE_KEYS)
    removable.update((_SMART_MODEL_LOADER_KEYS & loader_keys) | (
        _SMART_LM_LOADER_KEYS & smart_lm_keys
    ))
    removable.update(_SHARED_COMPANION_KEYS & loader_keys & smart_lm_keys)
    if not removable:
        return set()

    config_path = os.path.join(repo_root, "config.json")
    if not os.path.isfile(config_path) or os.path.islink(config_path):
        return set()

    try:
        current_config = read_json_object(config_path)
    except (JsonStoreError, OSError) as error:
        log.warning(
            _LOG_PREFIX,
            f"Could not inspect extracted companion configuration: {type(error).__name__}",
        )
        return set()
    current_comments = current_config.get("_comments")
    has_removable_comment = isinstance(current_comments, dict) and bool(
        removable & current_comments.keys()
    )
    if not removable.intersection(current_config) and not has_removable_comment:
        return set()

    removed: set[str] = set()

    def remove_confirmed(config: dict) -> None:
        comments = config.get("_comments")
        for key in removable:
            if key in config:
                del config[key]
                removed.add(key)
            if isinstance(comments, dict):
                comments.pop(key, None)

    try:
        update_json_object(config_path, remove_confirmed, private=True)
    except (JsonStoreError, OSError) as error:
        log.warning(
            _LOG_PREFIX,
            f"Could not clean extracted companion configuration: {type(error).__name__}",
        )
        return set()

    if removed:
        log.msg(
            _LOG_PREFIX,
            f"Removed {len(removed)} confirmed companion configuration field(s)",
        )
    return removed


# ============================================================================
# Main entry point
# ============================================================================


def run_migrations(
    repo_root: str | None = None, comfyui_root: str | None = None
) -> None:
    # Run all migrations in the correct order.
    # Called once from __init__.py on startup.
    #
    # Args:
    #     repo_root: Path to ComfyUI_Eclipse repo root (auto-detected if None)
    #     comfyui_root: Path to ComfyUI root (auto-detected if None)
    if repo_root is None:
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if comfyui_root is None:
        comfyui_root = os.path.abspath(os.path.join(repo_root, "..", ".."))

    # 1. Rename eclipse_config.json → config.json (v2.x migration)
    _migrate_config_rename(repo_root)

    # 2. Extract .example files using their folder and file names unchanged.
    extract_all_example_files(repo_root)

    # 3. Merge new config fields into existing config.json (preserves user values)
    _merge_config_fields(repo_root)

    # 4. Remove extracted config only after companion migration confirmation
    cleanup_extracted_companion_config(repo_root)

    # 5. Expose Eclipse prompts to wildcard processors.
    create_wildcards_junction(repo_root, comfyui_root)


# ============================================================================
# Config file rename migration (eclipse_config.json → config.json)
# ============================================================================


def _migrate_config_rename(repo_root: str) -> None:
    # Rename eclipse_config.json → config.json if old name still exists.
    # Also handles the .example file.
    old_config = os.path.join(repo_root, "eclipse_config.json")
    new_config = os.path.join(repo_root, "config.json")
    old_example = os.path.join(repo_root, "eclipse_config.json.example")

    if os.path.exists(old_config) and not os.path.exists(new_config):
        os.rename(old_config, new_config)
        log.msg(_LOG_PREFIX, "Renamed eclipse_config.json → config.json")

    # Clean up old .example file (now lives in .defaults/)
    if os.path.exists(old_example):
        try:
            os.remove(old_example)
        except OSError:
            pass

    # Clean up old file if both exist (new takes priority)
    if os.path.exists(old_config) and os.path.exists(new_config):
        try:
            os.remove(old_config)
            log.msg(
                _LOG_PREFIX,
                "Removed leftover eclipse_config.json (config.json already exists)",
            )
        except OSError:
            pass
