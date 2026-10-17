"""Prime Linux CFFI callback compatibility before custom-node imports."""

from __future__ import annotations

import logging
import sys
from typing import Any

_LOG_PREFIX = "[Eclipse Nova] [prestartup]"
_LOGGER = logging.getLogger(__name__)
_cffi_runtime_guard: tuple[Any, Any] | None = None


def prime_linux_cffi_callbacks() -> bool:
    """Bind CFFI callbacks before ComfyUI globally loads ANGLE's libffi."""
    global _cffi_runtime_guard
    if sys.platform != "linux":
        return False
    try:
        import cffi

        ffi = cffi.FFI()
        callback = ffi.callback("int(int)", lambda value: value)
        if callback(1) != 1:
            raise RuntimeError("CFFI callback self-test returned an invalid value")
    except ImportError:
        return False
    except Exception as error:  # noqa: BLE001 - prestartup must remain non-fatal
        _LOGGER.warning(
            "%s: could not initialize Linux CFFI callback compatibility: %s",
            _LOG_PREFIX,
            error,
        )
        return False
    _cffi_runtime_guard = (ffi, callback)
    return True


prime_linux_cffi_callbacks()
