# Read prompt lines and advance independently per workflow/node at execution time.

import random
import threading
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path

from .logger import log

_cursors = OrderedDict()
_cursor_lock = threading.RLock()


def file_signature(text):
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if len(line) >= 2 and line[0] in "\"'" and line[-1] == line[0]:
            line = line[1:-1]
        if not line:
            continue
        path = Path(line).expanduser().resolve()
        try:
            stat = path.stat() if path.is_file() else None
        except OSError:
            stat = None
        entries.append((str(path), stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size) if stat else (str(path), None, None, None))
    return tuple(entries)


@lru_cache(maxsize=32)
def _read_lines(signature, revision):
    lines = []
    missing = []
    for filename, modified, _, _size in signature:
        if modified is None:
            missing.append(filename)
            continue
        try:
            # A BOM belongs to the file header, not the first prompt.
            with open(filename, encoding="utf-8-sig") as handle:
                lines.extend(line.strip() for line in handle if line.strip())
        except (OSError, UnicodeError) as error:
            missing.append(filename)
            log.warning("Read Prompt Files", f"Cannot read {filename}: {error}")
    return tuple(lines), tuple(missing)


def read_prompt(options, *, key, seed=None):
    signature = file_signature(options["file_paths"])
    prompts, missing = _read_lines(signature, options["revision"])
    total = len(prompts)
    info = {"total": total, "index": None, "stopped": False, "missing": list(missing)}
    if not total:
        # STRING outputs must stay scalar even for empty or missing files.
        return "", info
    policy = options["advance"]
    identity = (signature, options["revision"], options["index"], policy)
    with _cursor_lock:
        previous = _cursors.get(key)
        if not previous or previous["identity"] != identity:
            previous = None
        cursor = {"identity": identity, "remaining": []} if previous is None else {
            **previous, "remaining": previous["remaining"].copy(),
        }
        selected = min(options["index"], total - 1)
        frozen = previous is not None and seed is not None and previous.get("seed") == seed
        if policy != "fixed" and frozen:
            selected = previous["index"]
        elif policy == "random":
            selected = random.SystemRandom().randrange(total)
        elif policy == "shuffle":
            if not cursor["remaining"]:
                if previous and options["stop_at_end"]:
                    selected = total
                else:
                    cursor["remaining"] = list(range(total))
                    random.SystemRandom().shuffle(cursor["remaining"])
                    selected = cursor["remaining"].pop()
            else:
                selected = cursor["remaining"].pop()
        elif previous and policy in ("next", "previous"):
            selected = previous["index"] + (1 if policy == "next" else -1)
        if not options["stop_at_end"]:
            selected %= total
        info.update(index=selected, stopped=not 0 <= selected < total)
        if info["stopped"]:
            # Retain the last successful index/deck; disabling Stop resumes it.
            return None, info
        cursor.update(index=selected, seed=seed)
        _cursors[key] = cursor
        _cursors.move_to_end(key)
        while len(_cursors) > 128:
            _cursors.popitem(last=False)
    prompt = prompts[selected]
    if options["log_prompt"]:
        log.msg("Read Prompt Files", f"Line {selected} of {total}: {prompt}")
    return prompt, info
