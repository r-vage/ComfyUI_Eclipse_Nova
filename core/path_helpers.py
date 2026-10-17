import os
from pathlib import Path


def normalize_relative_folder_path(path: str) -> str:
    """Convert either slash style in a relative folder path to the host separator."""
    if os.path.isabs(path):
        return path
    return path.replace("\\", os.sep).replace("/", os.sep)


def sanitize_output_path(value: str) -> str:
    # Keep the host-native anchor (POSIX root, Windows drive or UNC share)
    # separate from filename components, whose colons and other reserved
    # characters must be sanitized. A drive root is `D:\\`, not `D:`.
    path = Path(value.replace("\\", "/"))
    parts = path.parts[1:] if path.anchor else path.parts
    sanitized = [path.anchor] if path.anchor else []
    invalid = '<>:"|?*' + "".join(chr(i) for i in range(32))
    for part in parts:
        for char in invalid:
            part = part.replace(char, "_")
        sanitized.append(part.strip(" .") or "unnamed")
    return str(Path(*sanitized)) if sanitized else "default"
