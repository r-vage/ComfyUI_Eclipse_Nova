from types import ModuleType
from typing import Any, Optional

import comfy  # type: ignore

from . import config_store as _config_store

# Import log from logger (centralized location)
from .logger import log

get_config_snapshot = _config_store.get_config_snapshot
get_config_value = _config_store.get_config_value
invalidate_config_cache = _config_store.invalidate_config_cache
update_config_value = _config_store.update_config_value
update_config_values = _config_store.update_config_values


def _ensure_config_exists() -> bool:
    # Backward-compatible private alias for callers predating config_store.
    return _config_store.ensure_config_exists()


class AnyType(str):
    # A special class that is always equal in not-equal comparisons. Credit to pythongosssss

    def __eq__(self, _) -> bool:
        return True

    def __ne__(self, __value: object) -> bool:
        return False


def get_workflow_node(extra_pnginfo: Optional[dict], node_id: str, default=None):
    # Find a node in the workflow JSON by its colon-path unique_id (e.g. "42:7").
    # Handles nodes inside ComfyUI subgraphs by traversing
    # workflow.definitions.subgraphs when the node type matches a subgraph UUID.
    # Mirrors rgthree's get_worflow_node() server-side helper.
    if not extra_pnginfo or "workflow" not in extra_pnginfo:
        return default
    workflow = extra_pnginfo["workflow"]
    parts = node_id.split(":")
    nodes_list = workflow.get("nodes", [])
    subgraph_defs = (workflow.get("definitions") or {}).get("subgraphs", [])
    found = None
    for part in parts:
        found = next((n for n in nodes_list if str(n.get("id", "")) == part), None)
        if found is None:
            return default
        # If there are more parts, dive into the subgraph definition
        node_type = found.get("type", "")
        sg_def = next(
            (sg for sg in subgraph_defs if str(sg.get("id", "")) == str(node_type)),
            None,
        )
        if sg_def is not None and "nodes" in sg_def:
            nodes_list = sg_def["nodes"]
    return found if found is not None else default


_VRAM_LOG_PREFIX = "VRAM"


def _defer_to_comfyui_memory_management(stage: str) -> None:
    # Keep routing nodes running when the optional aggressive purge cannot
    # complete safely. ComfyUI can still unload models during normal memory
    # pressure handling or when an out-of-memory error is reported.
    log.warning(
        _VRAM_LOG_PREFIX,
        f"Aggressive purge stopped {stage}; continuing workflow so ComfyUI "
        "can manage memory",
    )


def _accelerator_is_available(backend: Any) -> bool:
    # Avoid initializing unavailable accelerator backends just to purge them.
    is_available = getattr(backend, "is_available", None)
    if callable(is_available):
        return bool(is_available())

    device_count = getattr(backend, "device_count", None)
    if callable(device_count):
        return int(device_count()) > 0

    return True


def _synchronize_accelerators(torch_mod: Any, stage: str) -> bool:
    # Finish queued work before native model objects or allocator state change.
    try:
        cuda = getattr(torch_mod, "cuda", None)
        if cuda is not None and _accelerator_is_available(cuda):
            for device_index in range(cuda.device_count()):
                with cuda.device(device_index):
                    cuda.synchronize()
    except Exception as e:
        log.warning(
            _VRAM_LOG_PREFIX,
            f"Aborting purge: CUDA synchronization failed {stage}: {e}",
        )
        return False

    synchronized = True
    for backend_name in ("mps", "xpu", "npu", "mlu"):
        backend = getattr(torch_mod, backend_name, None)
        synchronize = getattr(backend, "synchronize", None)
        if backend is None or not callable(synchronize):
            continue

        try:
            if _accelerator_is_available(backend):
                synchronize()
        except Exception as e:
            synchronized = False
            log.warning(
                _VRAM_LOG_PREFIX,
                f"{backend_name.upper()} synchronization failed {stage}: {e}",
            )

    return synchronized


def _clear_accelerator_caches(torch_mod: Any) -> bool:
    # Clear every unused accelerator cache after model destruction is complete.
    cleared = True
    try:
        cuda = getattr(torch_mod, "cuda", None)
        if cuda is not None and _accelerator_is_available(cuda):
            for device_index in range(cuda.device_count()):
                with cuda.device(device_index):
                    cuda.empty_cache()
                    ipc_collect = getattr(cuda, "ipc_collect", None)
                    if callable(ipc_collect):
                        ipc_collect()
    except Exception as e:
        cleared = False
        log.warning(_VRAM_LOG_PREFIX, f"CUDA cache cleanup failed: {e}")

    for backend_name in ("mps", "xpu", "npu", "mlu"):
        backend = getattr(torch_mod, backend_name, None)
        empty_cache = getattr(backend, "empty_cache", None)
        if backend is None or not callable(empty_cache):
            continue

        try:
            if _accelerator_is_available(backend):
                empty_cache()
        except Exception as e:
            cleared = False
            log.warning(
                _VRAM_LOG_PREFIX,
                f"{backend_name.upper()} cache cleanup failed: {e}",
            )

    return cleared


def purge_vram() -> None:
    # Aggressive inline memory barrier used before another model-heavy stage.
    # Unloads every ComfyUI-managed model and clears all unused accelerator
    # caches. Synchronization must happen before garbage collection because
    # collection can invoke native CUDA extension finalizers.
    import gc

    torch_mod: Optional[ModuleType]
    model_management: Optional[ModuleType]
    try:
        import torch as torch_mod  # type: ignore
    except Exception:
        torch_mod = None

    try:
        import comfy.model_management as model_management  # type: ignore
    except Exception:
        model_management = None

    # Do not destroy native objects while asynchronous kernels or weight
    # transfers are still using them.
    if torch_mod is not None and not _synchronize_accelerators(
        torch_mod, "before model unloading"
    ):
        _defer_to_comfyui_memory_management("before model unloading")
        return

    if model_management is not None:
        unload_all_models = getattr(model_management, "unload_all_models", None)
        if callable(unload_all_models):
            try:
                unload_all_models()
            except Exception as e:
                log.warning(_VRAM_LOG_PREFIX, f"Model unloading failed: {e}")
                if torch_mod is not None:
                    _synchronize_accelerators(torch_mod, "after failed unloading")
                _defer_to_comfyui_memory_management("after model unloading failed")
                return

    # Model unloading may enqueue offload copies. Complete them before Python
    # invokes C-extension destructors during full garbage collection.
    if torch_mod is not None and not _synchronize_accelerators(
        torch_mod, "after model unloading"
    ):
        _defer_to_comfyui_memory_management("after model unloading")
        return

    try:
        gc.collect()
    except Exception as e:
        log.warning(_VRAM_LOG_PREFIX, f"Garbage collection failed: {e}")
        _defer_to_comfyui_memory_management("after garbage collection failed")
        return

    if torch_mod is not None and not _synchronize_accelerators(
        torch_mod, "after garbage collection"
    ):
        _defer_to_comfyui_memory_management("after garbage collection")
        return

    # Keep ComfyUI's canonical cleanup for its active backend, then explicitly
    # clear all devices for multi-GPU and non-Comfy accelerator allocations.
    cache_errors = []
    if model_management is not None:
        soft_empty_cache = getattr(model_management, "soft_empty_cache", None)
        if callable(soft_empty_cache):
            try:
                soft_empty_cache()
            except Exception as e:
                cache_errors.append("ComfyUI")
                log.warning(_VRAM_LOG_PREFIX, f"ComfyUI cache cleanup failed: {e}")

    if torch_mod is not None and not _clear_accelerator_caches(torch_mod):
        cache_errors.append("accelerator")

    if cache_errors:
        failed_caches = " and ".join(cache_errors)
        log.warning(
            _VRAM_LOG_PREFIX,
            f"Aggressive purge could not clear {failed_caches} caches; "
            "continuing workflow so ComfyUI can manage remaining memory",
        )


# Pre-instantiated AnyType for use across nodes
# Import as: from ..core.common import any_type
any_type = AnyType("*")


# Sampler and scheduler lists for ComfyUI (lazy-loaded to avoid import errors in standalone tests)
_SAMPLERS_COMFY = None
_SCHEDULERS_ANY = None


def get_samplers_comfy():
    """Get ComfyUI sampler list (lazy-loaded)."""
    global _SAMPLERS_COMFY
    if _SAMPLERS_COMFY is None:
        _SAMPLERS_COMFY = comfy.samplers.KSampler.SAMPLERS
    return _SAMPLERS_COMFY


def get_schedulers_any():
    """Get ComfyUI scheduler list (lazy-loaded)."""
    global _SCHEDULERS_ANY
    if _SCHEDULERS_ANY is None:
        _SCHEDULERS_ANY = comfy.samplers.KSampler.SCHEDULERS
    return _SCHEDULERS_ANY


# Backward compatibility - these will fail if accessed before ComfyUI is loaded
# Use get_samplers_comfy() and get_schedulers_any() instead for safe access
try:
    SAMPLERS_COMFY = comfy.samplers.KSampler.SAMPLERS
    SCHEDULERS_ANY = comfy.samplers.KSampler.SCHEDULERS
except AttributeError:
    # ComfyUI not fully loaded yet (standalone test mode)
    SAMPLERS_COMFY = []
    SCHEDULERS_ANY = []

# ============================================================================
# ComfyUI progress bar utilities
# ============================================================================


def make_comfy_progress(total: int):
    # Create a ComfyUI ProgressBar for a batch loop.
    #
    # Usage:
    #   pbar = make_comfy_progress(n_frames)
    #   for i in range(n_frames):
    #       ...
    #       pbar.update(1)
    import comfy.utils  # type: ignore  # lazy — safe at module load time

    return comfy.utils.ProgressBar(max(total, 1))
