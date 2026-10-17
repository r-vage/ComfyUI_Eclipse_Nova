# File-backed Smart Prompt configuration, catalog and execution.

import hashlib
import json
import os
import random
import re
import secrets
import stat
import tempfile
import threading
from pathlib import Path, PurePosixPath

PROMPT_ROOT = Path(__file__).resolve().parents[1] / "prompts"
WIDGET_TYPE = "ECLIPSE_NOVA_SMART_PROMPT"
MAX_FILE_BYTES = 1024 * 1024
MAX_CONFIG_BYTES = 2 * 1024 * 1024
MAX_SEED = 2**64 - 1
_FILE_LOCK = threading.RLock()


class PromptFileConflict(ValueError):
    pass


def default_configuration():
    return {"version": 1, "folders": [], "seed": {"source": "local", "value": "0", "policy": "fixed"}}


def _relative_path(value, *, file=False):
    if not isinstance(value, str) or not value or len(value) > 2048 or "\\" in value or "\0" in value:
        raise ValueError("Use a relative path inside the prompts folder.")
    parts = value.split("/")
    if any(not part or part.startswith(".") or ":" in part for part in parts) or parts[0] == "tag_lists":
        raise ValueError("This path is not part of the Smart Prompt library.")
    if file and (len(parts) < 2 or PurePosixPath(value).suffix.lower() != ".txt"):
        raise ValueError("Select a .txt file inside a prompt folder.")
    return value


def _file_path(value):
    relative = _relative_path(value, file=True)
    root = PROMPT_ROOT.resolve()
    path = root / relative
    for ancestor in (path, *path.parents):
        if ancestor == root:
            break
        if ancestor.is_symlink():
            raise ValueError("Prompt editing does not follow symbolic links.")
    if not path.resolve().is_relative_to(root):
        raise ValueError("The prompt file must be inside the prompts folder.")
    if not path.is_file():
        raise FileNotFoundError(f"Prompt file is missing: {relative}")
    return path


def catalog():
    folders = []
    if not PROMPT_ROOT.is_dir():
        return {"folders": folders}
    for directory, dirs, filenames in os.walk(PROMPT_ROOT, followlinks=False):
        base = Path(directory)
        dirs[:] = sorted(name for name in dirs if not name.startswith(".")
                         and not (base / name).is_symlink()
                         and not (base == PROMPT_ROOT and name == "tag_lists"))
        if base == PROMPT_ROOT:
            continue
        files = []
        for name in sorted(filenames, key=lambda value: (value.casefold(), value)):
            path = base / name
            if name.startswith(".") or path.suffix.lower() != ".txt" or path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(PROMPT_ROOT).as_posix()
            _relative_path(relative, file=True)
            files.append({"id": relative, "name": path.stem})
        if files:
            relative = base.relative_to(PROMPT_ROOT).as_posix()
            folders.append({"id": relative, "name": relative, "files": files})
    return {"folders": folders}


def read_file(relative):
    path = _file_path(relative)
    with path.open("rb") as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"Prompt file exceeds 1 MiB: {relative}")
    try:
        content = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError(f"Prompt file must contain UTF-8 text: {relative}") from error
    return {"id": relative, "content": content, "revision": hashlib.sha256(data).hexdigest(),
            "options": [line.strip() for line in content.splitlines() if line.strip()]}


def save_file(relative, content, revision):
    if not isinstance(content, str) or "\0" in content or len(content.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError("Prompt text must be at most 1 MiB and cannot contain NUL characters.")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{64}", revision):
        raise ValueError("Read the prompt file before saving it.")
    with _FILE_LOCK:
        path = _file_path(relative)
        if read_file(relative)["revision"] != revision:
            raise PromptFileConflict("This file changed since you opened it. Keep your draft or reload the file before saving.")
        mode = stat.S_IMODE(path.stat().st_mode)
        fd, temporary = tempfile.mkstemp(prefix=".smart-prompt-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                os.chmod(temporary, mode)
                stream.write(content.encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())
            if read_file(relative)["revision"] != revision:
                raise PromptFileConflict("This file changed while saving. Your draft has been retained.")
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return read_file(relative)


def validate_configuration(raw):
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_CONFIG_BYTES:
        raise ValueError("Smart Prompt configuration must be a JSON string of at most 2 MiB.")
    try:
        config = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid Smart Prompt configuration JSON.") from error
    if not isinstance(config, dict) or set(config) != {"version", "folders", "seed"} or type(config["version"]) is not int or config["version"] != 1:
        raise ValueError("Expected version 1 Smart Prompt configuration.")
    seed = config["seed"]
    if not isinstance(seed, dict) or set(seed) != {"source", "value", "policy"}:
        raise ValueError("Seed requires a source, decimal value and queue policy.")
    if seed["source"] not in ("local", "input") or seed["policy"] not in ("fixed", "random", "increment", "decrement"):
        raise ValueError("Unknown seed source or queue policy.")
    if not isinstance(seed["value"], str) or not re.fullmatch(r"0|[1-9][0-9]{0,19}", seed["value"]) or int(seed["value"]) > MAX_SEED:
        raise ValueError("Seed must be an unsigned 64-bit decimal value.")
    if not isinstance(config["folders"], list) or len(config["folders"]) > 512:
        raise ValueError("Smart Prompt supports up to 512 active folders.")
    seen = set()
    for folder in config["folders"]:
        if not isinstance(folder, dict) or set(folder) != {"id", "files"}:
            raise ValueError("A folder requires its relative path and selected files.")
        identity = _relative_path(folder["id"])
        if identity in seen or not isinstance(folder["files"], list) or len(folder["files"]) > 4096:
            raise ValueError("Folders must be unique and contain at most 4096 selected files.")
        seen.add(identity)
        selected = set()
        for entry in folder["files"]:
            if not isinstance(entry, dict) or set(entry) not in ({"id", "mode"}, {"id", "mode", "value"}):
                raise ValueError("Invalid prompt file selection.")
            path = _relative_path(entry["id"], file=True)
            if str(PurePosixPath(path).parent) != identity or path in selected:
                raise ValueError("Prompt files must be unique and belong to their selected folder.")
            selected.add(path)
            if entry["mode"] == "value":
                if not isinstance(entry.get("value"), str) or not entry["value"].strip() or len(entry["value"]) > MAX_FILE_BYTES:
                    raise ValueError("Choose a nonempty prompt line.")
            elif entry["mode"] != "random" or "value" in entry:
                raise ValueError("A file selection must be Random or an exact line.")
    return config


def selected_files(config):
    result = []
    for folder in config["folders"]:
        for entry in folder["files"]:
            data = read_file(entry["id"])
            if not data["options"]:
                raise ValueError(f"Prompt file has no options: {entry['id']}")
            if entry["mode"] == "value" and entry["value"] not in data["options"]:
                raise ValueError(f"Saved choice is unavailable in {entry['id']}. Select a current option or None.")
            result.append((entry, data))
    return result


def fingerprint(raw):
    config = validate_configuration(raw)
    if config["seed"]["source"] == "local" and config["seed"]["policy"] == "random":
        return float("nan")
    return tuple((entry["id"], data["revision"]) for entry, data in selected_files(config))


def generate(raw, seed_input=None):
    config = validate_configuration(raw)
    if config["seed"]["source"] == "input":
        if type(seed_input) is not int or not 0 <= seed_input <= MAX_SEED:
            raise ValueError("Connect a valid unsigned 64-bit seed_input or enable Local seed.")
        seed = seed_input
    else:
        seed = secrets.randbits(64) if config["seed"]["policy"] == "random" else int(config["seed"]["value"])
    phrases = []
    for entry, data in selected_files(config):
        # Stable per-file randomness: reordering does not reroll other selections.
        choice = random.Random(f"{seed}\0{entry['id']}").choice(data["options"]) if entry["mode"] == "random" else entry["value"]
        cleaned = re.sub(r"\s+", " ", choice).strip().rstrip(",. ")
        if cleaned:
            phrases.append(cleaned)
    return ", ".join(phrases), seed
