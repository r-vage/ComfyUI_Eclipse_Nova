# Install each bundled theme once. Runtime themes belong to the user.

import shutil
from pathlib import Path

from .json_store import JsonStoreError, update_json_object
from .logger import log

_MARKER = ".theme-defaults.json"
_LOG_PREFIX = "Themes"


def _copy_missing_example(source: Path, target: Path, root: Path) -> bool:
    # Do not follow user-directory symlinks or replace an existing destination.
    parent = root
    for part in target.relative_to(root).parent.parts:
        parent /= part
        if parent.is_symlink():
            raise OSError(f"Theme directory is a symlink: {parent}")
        parent.mkdir(exist_ok=True)
    try:
        output = target.open("xb")
    except FileExistsError:
        return False
    try:
        with output, source.open("rb") as bundled:
            shutil.copyfileobj(bundled, output)
    except OSError:
        target.unlink(missing_ok=True)
        raise
    return True


def _completed_files(state: dict) -> set[str]:
    if state and (
        type(state.get("version")) is not int
        or state["version"] != 1
        or not isinstance(state.get("files"), list)
        or not all(isinstance(value, str) for value in state["files"])
    ):
        raise JsonStoreError("Invalid theme extraction record; preserving user files")
    return set(state.get("files", []))


def extract_theme_defaults(repo_root: str | Path) -> int:
    # A separate record works on existing installations with an older migration
    # marker or a prepopulated manifest. Hash changes never reset this record.
    root = Path(repo_root)
    defaults = root / ".defaults" / "themes"
    if defaults.parent.is_symlink() or defaults.is_symlink() or not defaults.is_dir():
        return 0
    examples = sorted(path for path in defaults.rglob("*.example") if path.is_file() and not path.is_symlink())
    if not examples:
        return 0
    marker = root / _MARKER
    if marker.is_symlink():
        log.warning(_LOG_PREFIX, "Theme extraction record is a symlink; preserving user files")
        return 0

    copied = 0

    def install(state: dict) -> None:
        nonlocal copied
        completed = _completed_files(state)
        for example in examples:
            relative = example.relative_to(defaults).with_suffix("")
            key = (Path("themes") / relative).as_posix()
            if key in completed:
                continue
            try:
                copied += _copy_missing_example(example, root / key, root)
            except OSError as error:
                log.warning(_LOG_PREFIX, f"Could not extract '{key}': {error}")
                continue
            # Existing files, including invalid JSON, are adopted untouched.
            completed.add(key)
        state.update(version=1, files=sorted(completed))

    try:
        update_json_object(marker, install, default={})
    except (JsonStoreError, OSError) as error:
        log.warning(_LOG_PREFIX, f"Could not record theme extraction: {error}")
    if copied:
        log.msg(_LOG_PREFIX, f"Extracted {copied} theme default file(s)")
    return copied
