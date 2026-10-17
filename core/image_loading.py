# Shared decoding, ordered frame catalogs and node-local iteration. No tensor cache.

import copy
import hashlib
import json
import math
import random
import threading
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import folder_paths
import torch
from PIL import Image, ImageOps

from .file_cache import FileListCache
from .image_helpers import image2mask, pil2tensor, unwrap_value
from .image_metadata import extract_image_metadata, selected_generation_metadata
from .resolution_sizing import require_number

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff", ".tif", ".mpo"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".gifv"}
_cursors = OrderedDict()
_cursor_lock = threading.RLock()


def source_image_path(config):
    source = config["source"]
    filename = config["files"][source].replace("\\", "/")
    if not filename or filename == "none":
        raise ValueError("Select an image in the file picker.")
    base = Path(folder_paths.get_output_directory() if source == "output" else folder_paths.get_input_directory()).resolve()
    path = (base / filename).resolve()
    if not path.is_relative_to(base) or not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
        raise ValueError(f"Image is missing or outside the {source} folder: {filename}")
    return path


def file_fingerprint(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _frame_tensors(frame):
    frame = ImageOps.exif_transpose(frame)
    if frame.mode == "I":
        frame = frame.point(lambda value: value / 255)
    image = pil2tensor(frame.convert("RGB"))
    if "A" in frame.getbands() or "transparency" in frame.info:
        mask = 1 - image2mask(frame.convert("RGBA").getchannel("A"))
    else:
        mask = torch.zeros((1, frame.height, frame.width), dtype=torch.float32)
    return image, mask


def image_pipe(path, image, mask, metadata=None, **identity):
    return {**(metadata or {}), "image": image, "mask": mask,
            "width": image.shape[2], "height": image.shape[1],
            "filepath": str(path), "filename": Path(path).name, "source_name": Path(path).stem, **identity}


def load_image(config):
    path = source_image_path(config)
    images, masks = [], []
    with Image.open(path) as source:
        metadata = selected_generation_metadata(extract_image_metadata(source), config["metadata_fields"]) if config["metadata"] else {}
        count = 1 if source.format == "MPO" else getattr(source, "n_frames", 1)
        for index in range(count):
            source.seek(index)
            image, mask = _frame_tensors(source)
            # Preserve the file loader's same-size animation batch contract.
            if images and image.shape[1:] != images[0].shape[1:]:
                continue
            images.append(image)
            masks.append(mask)
    image, mask = torch.cat(images), torch.cat(masks)
    return image, mask, image_pipe(path, image, mask, metadata)


def resolve_paths(text):
    lines = [line.strip().strip('"').strip("'") for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("Enter at least one image, video or folder path.")
    paths = []
    for line in lines:
        path = Path(line).expanduser()
        if not path.is_absolute():
            path = Path(folder_paths.get_input_directory()) / path
        path = path.resolve()
        if not path.exists():
            raise ValueError(f"Source path does not exist: {line}")
        paths.append(path)
    return paths


def _directory_files(path, config, refresh):
    key = FileListCache.get_cache_key(str(path), config["recursive"], config["sort"]["by"], config["sort"]["order"])
    if refresh:
        FileListCache.invalidate(str(path))
    cached = FileListCache.get_cached_list(key)
    if cached is not None:
        return [Path(name) for name in cached]
    iterator = path.rglob("*") if config["recursive"] else path.iterdir()
    files = [file for file in iterator if file.is_file() and file.suffix.lower() in IMAGE_EXTENSIONS]
    sort = config["sort"]["by"]
    def key_for(file):
        name = (str(file).casefold(), str(file))
        if sort == "name":
            return name
        stat = file.stat()
        return ({"date_modified": stat.st_mtime_ns, "date_created": stat.st_ctime_ns, "size": stat.st_size}[sort], *name)
    files.sort(key=key_for, reverse=config["sort"]["order"] == "descending")
    FileListCache.set_cached_list(key, [str(file) for file in files], {"folder_path": str(path), "count": len(files)})
    return files


def _interruption_check():
    from comfy.model_management import throw_exception_if_processing_interrupted
    throw_exception_if_processing_interrupted()


@lru_cache(maxsize=512)
def _frame_count(path, size, modified):
    if Path(path).suffix.lower() not in VIDEO_EXTENSIONS:
        try:
            with Image.open(path) as image:
                return 1 if image.format == "MPO" else getattr(image, "n_frames", 1)
        except OSError:
            return 1  # Preserve this entry's index; decoding reports the selected corrupt file.
    capture = cv2.VideoCapture(path)
    try:
        if not capture.isOpened():
            raise ValueError(f"Cannot open video: {path}")
        estimate = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        count = int(estimate) if math.isfinite(estimate) else 0
        if count > 0:
            return count
        # Unknown-length videos are counted without retaining decoded frames.
        count = 0
        while capture.grab():
            _interruption_check()
            count += 1
        if not count:
            raise ValueError(f"Video contains no readable frames: {path}")
        return count
    finally:
        capture.release()


@dataclass(frozen=True)
class Source:
    path: Path
    base: Path
    folder_index: int
    start: int
    count: int
    folder_start: int
    folder_count: int


def catalog(config, refresh=False):
    sources, total = [], 0
    roots = resolve_paths(config["paths"])
    for group, path in enumerate(roots):
        files = _directory_files(path, config, refresh) if path.is_dir() else [path]
        folder_start = total
        pending = []
        for file in files:
            if file.suffix.lower() not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
                raise ValueError(f"Unsupported image/video file: {file}")
            stat = file.stat()
            count = _frame_count(str(file), stat.st_size, stat.st_mtime_ns)
            pending.append((file, total, count))
            total += count
        for file, start, count in pending:
            sources.append(Source(file, path if path.is_dir() else path.parent, group, start, count, folder_start, total - folder_start))
    if not total:
        raise ValueError("No image files or video frames found in the supplied paths.")
    return sources, total, len(roots)


def _read_frames(source, start, end, metadata):
    if source.path.suffix.lower() in VIDEO_EXTENSIONS:
        capture = cv2.VideoCapture(str(source.path))
        try:
            if not capture.set(cv2.CAP_PROP_POS_FRAMES, start):
                for _ in range(start):
                    _interruption_check()
                    if not capture.grab():
                        raise ValueError(f"Cannot seek to frame {start} of {source.path}")
            for index in range(start, end + 1):
                _interruption_check()
                ok, frame = capture.read()
                if not ok:
                    raise ValueError(f"Cannot decode frame {index} of {source.path}")
                image = pil2tensor(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
                yield index, image, torch.zeros(image.shape[:3], dtype=torch.float32), {}
        finally:
            capture.release()
    else:
        with Image.open(source.path) as file:
            values = extract_image_metadata(file) if metadata else {}
            for index in range(start, end + 1):
                _interruption_check()
                file.seek(index)
                image, mask = _frame_tensors(file)
                yield index, image, mask, values


def _resize_custom(images, masks, settings, width, height):
    from .resize_configuration import NUMBERS, execute_configuration

    mode = settings["scale_to"]
    if mode == "custom":
        # Folder loading always uses connected dimensions for a custom target.
        settings = {**settings, "use_input_size": True}
        return execute_configuration(images, json.dumps(settings), masks, width=width, height=height)[:2]
    dimensions = {}
    for axis, value in (("width", width), ("height", height)):
        if mode != axis and mode not in ("longest", "shortest"):
            continue
        value = unwrap_value(value)
        if value is not None:
            require_number(value, NUMBERS[f"custom_{axis}"])
            dimensions[axis] = int(value)
    if not dimensions:
        return execute_configuration(images, json.dumps(settings), masks)[:2]
    resized_images, resized_masks = [], []
    for image, mask in zip(images, masks):
        sizes = [value or image.shape[2 if axis == "width" else 1] for axis, value in dimensions.items()]
        size = (min if mode == "shortest" else max)(sizes)
        result = execute_configuration([image], json.dumps({**settings, "size": size}), [mask])
        resized_images.extend(result[0]); resized_masks.extend(result[1])
    return resized_images, resized_masks


def _resize_selected(images, masks, resize, width=None, height=None):
    if resize is None:
        return images, masks
    from .resize_configuration import execute_configuration
    sizes = [(image.shape[2], image.shape[1]) for image in images]
    policy = resize["policy"]
    if policy == "strict":
        if len(set(sizes)) > 1:
            raise ValueError("Selected frames have different sizes. Choose a resize policy or disable Resize.")
        return images, masks
    if policy == "custom":
        return _resize_custom(images, masks, resize["settings"], width, height)
    from .resize_configuration import DEFAULTS, active_fields
    target = sizes[0] if policy == "first" else tuple((max if policy == "largest" else min)(axis) for axis in zip(*sizes))
    config = {**DEFAULTS, "scale_to": "custom", "custom_width": target[0], "custom_height": target[1],
              "fit": "stretch", "method": "bilinear", "divisible_by": 1}
    raw = json.dumps({"version": 1, **{key: config[key] for key in active_fields(config)}})
    return execute_configuration(images, raw, masks)[:2]


def _selection(config, total, key, seed):
    mode = config["mode"]
    signature = json.dumps({name: config[name] for name in ("paths", "recursive", "sort", "mode", "single", "range", "step", "revision")}, sort_keys=True)
    signature += f"/{total}"
    previous = _cursors.get(key)
    if not previous or previous["signature"] != signature:
        previous = None
    cursor = copy.deepcopy(previous) if previous else {"signature": signature}
    if mode == "single":
        policy = config["single"]["advance"]
        selected = config["single"]["index"]
        if policy != "fixed":
            if previous and seed is not None and previous.get("seed") == seed:
                selected = previous["selected"]
            elif policy == "random":
                selected = random.randrange(total)
            elif policy == "shuffle":
                deck = cursor.setdefault("deck", [])
                if not deck:
                    if previous and config["stop_at_end"]:
                        selected = total
                    else:
                        deck.extend(range(total)); random.shuffle(deck)
                        selected = deck.pop()
                else:
                    selected = deck.pop()
            elif previous:
                selected = previous["selected"] + (1 if policy == "next" else -1)
        if not config["stop_at_end"]:
            selected %= total
        cursor.update(selected=selected, seed=seed)
        return selected, selected, cursor
    start, end = (config["range"][name] for name in ("start", "end"))
    start = max(0, total + start if start < 0 else start)
    end = min(total - 1, total + end if end < 0 else end)
    if end < start:
        return total, total, cursor
    if mode == "step":
        batch = config["step"]["batch_index"]
        policy = config["step"]["advance"]
        size = end - start + 1
        batches = (total - start + size - 1) // size
        if policy == "random":
            batch = random.randrange(batches)
        elif previous and policy != "fixed":
            batch = previous["batch"] + (1 if policy == "next" else -1)
        if not config["stop_at_end"]:
            batch %= batches
        cursor["batch"] = batch
        if batch < 0:
            return -1, -1, cursor
        start, end = start + batch * size, end + batch * size
    return start, min(end, total - 1), cursor


def load_files(config, *, key, seed=None, width=None, height=None):
    sources, total, folders = catalog(config)
    with _cursor_lock:
        start, end, cursor = _selection(config, total, key, seed)
    info = {"total": total, "start": start, "end": end, "mode": config["mode"], "batch_index": cursor.get("batch"), "stopped": start < 0 or start >= total or end < start}
    if info["stopped"]:
        return None, info
    images, masks, identities = [], [], []
    for source in sources:
        if source.start > end or source.start + source.count <= start:
            continue
        for frame, image, mask, metadata in _read_frames(source, max(0, start - source.start), min(source.count - 1, end - source.start), config["metadata"]):
            images.append(image); masks.append(mask)
            identities.append((source, frame, metadata))
    images, masks = _resize_selected(images, masks, config["resize"], width, height)
    pipes, files = [], []
    for image, mask, (source, frame, metadata) in zip(images, masks, identities):
        files.append(str(source.path))
        pipes.append(image_pipe(source.path, image, mask, metadata, current_index=source.start + frame,
                                total_count=total, base_path=str(source.base), folder_index=source.folder_index,
                                folder_count=folders, local_index=source.start + frame - source.folder_start,
                                local_count=source.folder_count, source_frame=frame))
    with _cursor_lock:
        _cursors[key] = cursor
        _cursors.move_to_end(key)
        while len(_cursors) > 128:
            _cursors.popitem(last=False)
    return (images, masks, pipes, files), info
