# Immutable saved versions behind one atomically published run manifest.
import copy
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .json_store import (
    _fsync_directory,
    locked_path,
    read_json_object,
    write_json_object,
)
from .video_resume import _copy_media
from .video_run import _contained_file, load_video_run, manifest_path, run_revision

CURRENT_VERSION = "Current run"
_BACKUPS = ".backups"
_VERSIONS = ".versions"
_BACKUP_ID = re.compile(r"\d{8}_\d{6}_[a-f0-9]{12}")


def _managed_folder(root, name):
    path = root / name
    if path.is_symlink():
        raise ValueError(f"Saved run {name} must be a real folder, not a symlink.")
    path.mkdir(exist_ok=True)
    return path


def selected_run_path(saved_run, backup=CURRENT_VERSION):
    import folder_paths

    if not isinstance(saved_run, str) or not saved_run or len(saved_run) > 4096:
        raise ValueError("Select a saved run first.")
    output = Path(folder_paths.get_output_directory()).resolve()
    path = (output / saved_run).resolve()
    if not path.is_relative_to(output) or path.name != "run.json" or not path.is_file():
        raise ValueError("Select a run.json inside ComfyUI output.")
    if backup is None or backup == CURRENT_VERSION:
        return path
    if not isinstance(backup, str) or not _BACKUP_ID.fullmatch(backup):
        raise ValueError("Select a backup from this run's backup list.")
    root = path.parent
    folder = root / _BACKUPS / backup
    if (root / _BACKUPS).is_symlink() or folder.is_symlink():
        raise ValueError("Backup folders may not be symlinks.")
    manifest = _contained_file(root, f"{_BACKUPS}/{backup}/run.json")
    info = read_json_object(_contained_file(root, f"{_BACKUPS}/{backup}/backup.json"))
    if info.get("format") != "eclipse_run_backup" or info.get("version") != 1:
        raise ValueError("Unsupported saved run backup.")
    return manifest


def backup_catalog(saved_run):
    path = selected_run_path(saved_run)
    root = path.parent
    backups = []
    directory = root / _BACKUPS
    if directory.is_dir() and not directory.is_symlink():
        for folder in sorted(directory.iterdir(), reverse=True):
            if not _BACKUP_ID.fullmatch(folder.name):
                continue
            try:
                saved = selected_run_path(saved_run, folder.name)
                info = read_json_object(folder / "backup.json")
                manifest = read_json_object(saved)
                backups.append({"id": folder.name, "parts": len(manifest["chunks"]),
                                "frames": manifest["frame_count"], **info})
            except (OSError, ValueError, KeyError, TypeError):
                continue
    backups.sort(key=lambda item: (item.get("created_at", ""), item["id"]), reverse=True)
    return {"run": str(root), "revision": run_revision(path), "backups": backups}


def copy_saved_run(source, target):
    # Copy only referenced assets, never recursively include history or drafts.
    # Hard links share immutable media; all metadata is written to new files.
    source = manifest_path(str(source))
    source_root = source.parent
    target = Path(target)
    target.mkdir(parents=True, exist_ok=False)
    manifest = read_json_object(source)
    result = copy.deepcopy(manifest)
    copied = {}

    def media(value, destination):
        original = _contained_file(source_root, value)
        if original not in copied:
            _copy_media(original, target / destination)
            copied[original] = destination
        return copied[original]

    try:
        for index, entry in enumerate(result["chunks"]):
            suffix = Path(entry["file"]).suffix
            destination = (f"part_{index:05d}/frames.npy" if result["kind"] == "frames"
                           else f"part_{index:05d}{suffix}")
            entry["file"] = media(entry["file"], destination)
        if result.get("audio"):
            result["audio"]["file"] = media(result["audio"]["file"], "soundtrack.npy")
        if result.get("checkpoint"):
            from .video_part_prompts import source_key

            checkpoint = read_json_object(_contained_file(source_root, result["checkpoint"]))
            checkpoint["prompt_source_id"] = source_key(checkpoint)
            checkpoint["images"] = [media(name, f"reference_{index:05d}.npy")
                                    for index, name in enumerate(checkpoint["images"])]
            for name in ("audio", "conditioning_audio", "caption_audio"):
                if checkpoint.get(name):
                    checkpoint[name]["file"] = media(checkpoint[name]["file"], f"input_{name}.npy")
            write_json_object(target / "checkpoint.json", checkpoint)
            result["checkpoint"] = "checkpoint.json"
        for key in ("workflow", "prompt"):
            name = manifest.get(key, f"{key}.json")
            if key in manifest or not manifest.get("history") and (source_root / name).is_file():
                value = read_json_object(_contained_file(source_root, name))
                write_json_object(target / f"{key}.json", value)
                result[key] = f"{key}.json"
            else:
                result.pop(key, None)
        result.pop("history", None)
        write_json_object(target / "run.json", result)
    except BaseException:
        shutil.rmtree(target)
        raise
    return target


def _validate_saved(path):
    source = load_video_run(str(path))[0]
    if read_json_object(Path(path) / "run.json").get("checkpoint"):
        from .video_checkpoint import load_checkpoint
        from .video_resume import plan_ranges

        data = load_checkpoint(str(path))
        counts = ([chunk.count for chunk in source.chunks] if hasattr(source, "chunks")
                  else [entry["count"] for entry in source._eclipse_run_entries])
        if counts != [count for _, count in plan_ranges(data.plan)[2]][:len(counts)]:
            raise ValueError("Saved backup media does not match its planned part boundaries.")


def _sync_saved_files(root):
    # Flush media and directory entries before the manifest can expose them.
    for directory, _, files in os.walk(root, topdown=False, followlinks=False):
        for name in files:
            path = Path(directory) / name
            if path.is_symlink():
                raise ValueError("Saved history files may not be symlinks.")
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
        _fsync_directory(Path(directory))
    _fsync_directory(root.parent)


def _publish_manifest(root, staged, action, backup):
    manifest = read_json_object(staged / "run.json")
    prefix = staged.relative_to(root).as_posix()

    def relative(name):
        _contained_file(staged, name)
        return f"{prefix}/{name}"

    for entry in manifest["chunks"]:
        entry["file"] = relative(entry["file"])
    if manifest.get("audio"):
        manifest["audio"]["file"] = relative(manifest["audio"]["file"])
    if manifest.get("checkpoint"):
        value = read_json_object(_contained_file(staged, manifest["checkpoint"]))
        value["images"] = [relative(name) for name in value["images"]]
        for name in ("audio", "conditioning_audio", "caption_audio"):
            if value.get(name):
                value[name]["file"] = relative(value[name]["file"])
        # This file belongs to the root manifest; the staged checkpoint continues
        # to use local paths so both remain independently valid and immutable.
        write_json_object(staged / "active_checkpoint.json", value)
        manifest["checkpoint"] = f"{prefix}/active_checkpoint.json"
    for name in ("workflow", "prompt"):
        if manifest.get(name):
            manifest[name] = relative(manifest[name])
    manifest["history"] = {"id": uuid4().hex, "backup": backup, **action}
    # The manifest is the only commit point. Every file it references already
    # exists; readers of the previous manifest can still use its immutable files.
    write_json_object(root / "run.json", manifest)
    return manifest


def commit_update(run_path, staged, expected_revision, *, part=None, restored_from=None):
    root = manifest_path(str(run_path)).parent.resolve()
    staged = Path(staged).resolve()
    if staged.parent != root / _VERSIONS or (root / _VERSIONS).is_symlink():
        raise ValueError("The replacement must be staged inside the selected run.")
    _validate_saved(staged)
    _sync_saved_files(staged)
    action = {"operation": "restore" if restored_from else "replace", "part": part,
              "restored_from": restored_from, "created_at": datetime.now(timezone.utc).isoformat()}
    with locked_path(root / ".history-transaction"):
        if run_revision(root) != expected_revision:
            raise ValueError("The selected run changed while this operation was pending. Its current version is unchanged; reload it before retrying.")
        backup_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_") + uuid4().hex[:12]
        backups = _managed_folder(root, _BACKUPS)
        temporary = backups / f".pending-{backup_id}"
        try:
            copy_saved_run(root, temporary)
            write_json_object(temporary / "backup.json", {
                "format": "eclipse_run_backup", "version": 1,
                "revision": expected_revision, **action})
            _sync_saved_files(temporary)
            os.replace(temporary, backups / backup_id)
            _fsync_directory(backups)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
        manifest = _publish_manifest(root, staged, action, backup_id)
    return manifest, backup_id


def update_directory(run_path):
    root = manifest_path(str(run_path)).parent.resolve()
    if any(name in (_BACKUPS, _VERSIONS) for name in root.parts):
        raise ValueError("Backups are read-only. Restore the selected backup before updating this run.")
    return _managed_folder(root, _VERSIONS)


def restore_backup(saved_run, backup, expected_revision):
    if backup is None or backup == CURRENT_VERSION:
        raise ValueError("Select a backup to restore first.")
    if not isinstance(expected_revision, str) or len(expected_revision) != 64:
        raise ValueError("Refresh the backup list before restoring.")
    active = selected_run_path(saved_run)
    source = selected_run_path(saved_run, backup)
    _validate_saved(source.parent)
    versions = update_directory(active)
    staged = Path(tempfile.mkdtemp(prefix="restore_", dir=versions))
    staged.rmdir()
    try:
        copy_saved_run(source, staged)
        _, saved_backup = commit_update(active, staged, expected_revision, restored_from=backup)
    except BaseException:
        if staged.exists():
            shutil.rmtree(staged)
        raise
    return {"run": str(active.parent), "restored": backup, "backup": saved_backup,
            "revision": run_revision(active)}
