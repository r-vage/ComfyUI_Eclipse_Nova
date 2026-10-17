# Image Selector execution and session state used by the node and endpoints.

import hashlib
import inspect
import json
import os
import time
import uuid

import comfy.utils
import folder_paths
import nodes
import torch
from comfy_api.latest import io
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from .image_helpers import cat_and_fit_images, flatten_images, tensor2pil
from .logger import log

_LOG_PREFIX = "Image Selector"

_temp_dir = folder_paths.get_temp_directory()

# ============================================================================
# Module-level shared state (lives for the lifetime of the ComfyUI process)
# ============================================================================

# unique_id → list[Tensor[1,H,W,C]]  — stored image list for each waiting node
_stored_images: dict = {}

# unique_id → list[int] | None
#   None  = no selection confirmed yet (node is waiting)
#   list  = confirmed indices, ready to consume on next run
_selections: dict = {}

# unique_id → str (stored signature of the images when selection was active)
_stored_signatures: dict = {}

# unique_id -> list[dict] (cached preview metadata)
_stored_ui_images: dict = {}

# Identifies one full grid within this backend lifetime; never serialized tensors.
_generations: dict[str, str] = {}


def get_selector_state(uid: str, generation: str) -> dict | None:
    if not generation or _generations.get(uid) != generation:
        return None
    images = _stored_ui_images.get(uid)
    if images is None or uid not in _stored_signatures:
        return None
    if not all(os.path.isfile(os.path.join(_temp_dir, image["subfolder"], image["filename"]))
               for image in images):
        return None
    return {
        "node_id": uid,
        "generation": generation,
        "images": images,
        "total_count": len(images),
        "confirmed_indices": get_selection(uid),
    }

# unique_ids whose current selection was produced by auto-select mode. This
# closes the small frontend-reset race when automatic mode is turned off and a
# new prompt is queued before the reset request reaches the server.
_auto_selected_uids: set[str] = set()


def store_images(uid: str, images: list) -> None:
    _stored_images[uid] = images


def get_stored_images(uid) -> list | None:
    return _stored_images.get(str(uid))


def store_selection(uid, indices: list) -> None:
    _selections[str(uid)] = indices


def get_selection(uid) -> list | None:
    return _selections.get(str(uid))


def reset_selection(uid) -> None:
    uid_str = str(uid)
    _selections.pop(uid_str, None)
    _auto_selected_uids.discard(uid_str)


def clear_state(uid) -> None:
    uid_str = str(uid)
    _stored_images.pop(uid_str, None)
    _selections.pop(uid_str, None)
    _stored_signatures.pop(uid_str, None)
    _stored_ui_images.pop(uid_str, None)
    _generations.pop(uid_str, None)
    _auto_selected_uids.discard(uid_str)
    subfolder = f"_cache_selector/{uid_str}"
    full_folder = os.path.join(_temp_dir, subfolder)
    if os.path.exists(full_folder):
        try:
            import shutil

            shutil.rmtree(full_folder)
        except OSError as error:
            log.warning(_LOG_PREFIX, f"Failed to remove selector previews: {error}")


# ============================================================================
# Helpers
# ============================================================================


def _compute_signature(image_list: list) -> str:
    # Confirmation belongs to the complete image contents, including frames
    # outside the old three-frame sample and changes that preserve sum/mean.
    digest = hashlib.sha256(str(len(image_list)).encode())
    for image in image_list:
        digest.update(f";{image.dtype}:{tuple(image.shape)};".encode())
        pixels = image.detach().cpu().contiguous().view(torch.uint8).numpy()
        digest.update(memoryview(pixels))
    return digest.hexdigest()


def _save_previews(image_list: list, prompt, extra_pnginfo, uid: str, *, output=False) -> list:
    # Save each [1,H,W,C] tensor to temp dir. Returns list of {filename, subfolder, type}.
    import shutil

    metadata = PngInfo()
    if prompt is not None:
        metadata.add_text("prompt", json.dumps(prompt))
    if extra_pnginfo is not None:
        for k in extra_pnginfo:
            metadata.add_text(k, json.dumps(extra_pnginfo[k]))

    # Selected-output previews must never replace the full interactive grid.
    subfolder = f"_cache_selector/{uid}/{'output' if output else 'grid'}"
    full_folder = os.path.join(_temp_dir, subfolder)

    # Remove old cache directory to avoid bloating
    if os.path.exists(full_folder):
        try:
            shutil.rmtree(full_folder)
        except OSError as e:
            log.warning(
                _LOG_PREFIX,
                f"[{uid}] Failed to clean up old cache directory {full_folder}: {e}",
            )

    os.makedirs(full_folder, exist_ok=True)

    results = []
    pbar = comfy.utils.ProgressBar(len(image_list))
    for idx, img_t in enumerate(image_list):
        pil = tensor2pil(img_t)

        # Scale down preview to max 1024px to save browser memory/VRAM and disk space
        max_size = 1024
        if pil.width > max_size or pil.height > max_size:
            if pil.width > pil.height:
                new_w = max_size
                new_h = int(pil.height * (max_size / pil.width))
            else:
                new_h = max_size
                new_w = int(pil.width * (max_size / pil.height))

            if hasattr(Image, "Resampling"):
                method = Image.Resampling.LANCZOS
            else:
                method = Image.LANCZOS
            pil = pil.resize((new_w, new_h), method)

        ts = int(time.time() * 1000) % 100000000
        fname = f"preview_{idx:05}_{ts}.png"
        pil.save(os.path.join(full_folder, fname), pnginfo=metadata, compress_level=1)
        results.append({"filename": fname, "subfolder": subfolder, "type": "temp"})
        pbar.update(1)

    return results



def selector_fingerprint(*, trigger=0, auto_confirm=False):
    # Inspect stack to find the ComfyUI node_id, dynprompt, and outputs_cache
    node_id = None
    dynprompt = None
    outputs_cache = None

    curr = inspect.currentframe()
    while curr:
        locs = curr.f_locals
        if "node_id" in locs and isinstance(locs["node_id"], (str, int)):
            node_id = str(locs["node_id"])
        if "self" in locs:
            obj = locs["self"]
            if type(obj).__name__ == "IsChangedCache":
                dynprompt = getattr(obj, "dynprompt", None)
                outputs_cache = getattr(obj, "outputs_cache", None)
        if node_id is not None and dynprompt is not None and outputs_cache is not None:
            break
        curr = curr.f_back

    selection = get_selection(node_id) if node_id is not None else None
    if selection is None or len(selection) == 0:
        # Force re-execution on every queue run if no selection confirmed yet
        return str(uuid.uuid4())

    # Dynamically lookup the upstream images to check if their content actually changed
    image_sig = ""
    if node_id is not None and dynprompt is not None and outputs_cache is not None:
        try:
            node = dynprompt.get_node(node_id)
            images_input = node.get("inputs", {}).get("images")
            # Connection format is: [upstream_node_id, output_index]
            if isinstance(images_input, (list, tuple)) and len(images_input) == 2:
                upstream_node_id = str(images_input[0])
                output_index = int(images_input[1])
                cached_entry = outputs_cache.get_local(upstream_node_id)
                if cached_entry is not None and hasattr(cached_entry, "outputs"):
                    upstream_outputs = cached_entry.outputs
                    if isinstance(upstream_outputs, (list, tuple)) and len(upstream_outputs) > output_index:
                        images_tensor = upstream_outputs[output_index]
                        if images_tensor is not None:
                            normalized = flatten_images(images_tensor)
                            image_sig = _compute_signature(normalized)
        except (AttributeError, IndexError, TypeError, ValueError, RuntimeError) as e:
            # Fall back gracefully to avoid breaking the execution flow
            log.warning(_LOG_PREFIX, f"[{node_id}] Failed to compute upstream image signature in fingerprint_inputs: {e}")

    # Generate fingerprint which changes if trigger, selection, or upstream image content changes
    return hashlib.md5(
        f"{trigger}_{auto_confirm}_{selection}_{image_sig}".encode()
    ).hexdigest()

def select_images(images, *, unique_id, prompt=None, extra_pnginfo=None, auto_confirm=False):
    if isinstance(images, list) and len(images) == 1:
        images = images[0]

    uid = str(unique_id)

    image_list = flatten_images(images)
    current_sig = _compute_signature(image_list)

    selection = get_selection(uid)

    # Check if input images changed since we stored them (even if selection is None/not confirmed yet)
    stored_sig = _stored_signatures.get(uid)
    if stored_sig is not None and stored_sig != current_sig:
        log.msg(
            _LOG_PREFIX,
            f"[{uid}] Input images changed (signature mismatch: stored={stored_sig} current={current_sig}) — auto-discarding selection and state",
        )
        clear_state(uid)
        selection = None

    # Disabling Auto confirm is a discard-like action. The
    # frontend resets immediately, and this server-side marker guarantees
    # that a prompt queued during that request cannot reuse the old
    # automatic selection.
    if not auto_confirm and uid in _auto_selected_uids:
        reset_selection(uid)
        selection = None

    # Determine if we already ran the first run on these images (stored sig matches and stored images exist)
    already_interrupted = (
        stored_sig is not None
        and stored_sig == current_sig
        and get_stored_images(uid) is not None
    )

    generation = _generations.setdefault(uid, uuid.uuid4().hex)

    if auto_confirm:
        valid = list(range(len(image_list)))
        batch = cat_and_fit_images(image_list, log_prefix=_LOG_PREFIX)
        cached_ui_images = (
            _stored_ui_images.get(uid) if stored_sig == current_sig else None
        )
        if cached_ui_images is None:
            cached_ui_images = _save_previews(
                image_list, prompt, extra_pnginfo, uid
            )
            _stored_ui_images[uid] = cached_ui_images

        store_selection(uid, valid)
        _auto_selected_uids.add(uid)
        _stored_signatures[uid] = current_sig
        _stored_images.pop(uid, None)

        log.msg(
            _LOG_PREFIX,
            f"[{uid}] Auto-selected all {len(valid)} image(s) without interrupting",
        )
        return io.NodeOutput(
            batch,
            valid,
            ui={
                "images": cached_ui_images,
                "eclipseSelector": [True],
                "autoSelectAndConfirm": [True],
                "selectedIndices": [valid],
                "totalCount": [len(image_list)],
                "selectorGeneration": [generation],
            },
        )

    if selection is not None:
        # User confirmed a selection
        valid = [i for i in selection if 0 <= i < len(image_list)]
        if valid:
            selected_list = [image_list[i] for i in valid]
            batch = cat_and_fit_images(selected_list, log_prefix=_LOG_PREFIX)

            if uid not in _stored_ui_images:
                _stored_ui_images[uid] = _save_previews(image_list, prompt, extra_pnginfo, uid)
            _stored_signatures[uid] = current_sig
            ui_images = _save_previews(selected_list, prompt, extra_pnginfo, uid, output=True)
            _stored_images.pop(uid, None)  # Free stored images tensor cache

            count = len(selected_list)
            log.msg(
                _LOG_PREFIX,
                f"[{uid}] Outputting {count} selected image(s) (selection confirmed)",
            )
            return io.NodeOutput(
                batch,
                valid,
                ui={
                    "images": ui_images,
                    "eclipseSelector": [False],
                    "selectionCount": [count],
                    "selectorImages": _stored_ui_images[uid],
                    "selectedIndices": [valid],
                    "totalCount": [len(image_list)],
                    "selectorGeneration": [generation],
                },
            )
        else:
            log.msg(
                _LOG_PREFIX,
                f"[{uid}] Confirmed selection is empty — interrupting workflow",
            )

    # No selection confirmed (first run or empty selection confirmed)
    valid = list(range(len(image_list)))
    selected_list = image_list
    batch = cat_and_fit_images(selected_list, log_prefix=_LOG_PREFIX)

    # Cache inputs & signature
    store_images(uid, image_list)
    _stored_signatures[uid] = current_sig

    if already_interrupted and uid in _stored_ui_images:
        ui_images = _stored_ui_images[uid]
    else:
        ui_images = _save_previews(image_list, prompt, extra_pnginfo, uid)
        _stored_ui_images[uid] = ui_images

    log.msg(
        _LOG_PREFIX,
        f"[{uid}] No selection confirmed — interrupting workflow to await selection",
    )
    nodes.interrupt_processing()

    return io.NodeOutput(
        batch,
        valid,
        ui={
            "images": ui_images,
            "eclipseSelector": [True],
            "totalCount": [len(image_list)],
            "selectorGeneration": [generation],
        },
    )
