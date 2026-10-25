# Manual still-image slots with per-image framing, transitions and metadata.
import json
import math

import torch
from PIL import Image, ImageOps

from .image_helpers import pil2tensor, prepare_image_output
from .image_loading import file_fingerprint, source_image_path
from .image_metadata import (
    GENERATION_GROUPS,
    extract_image_metadata,
    selected_generation_metadata,
)
from .image_timeline_video import fit_timeline_image, image_options, output_dimensions
from .video_timing import check_media_interrupt

WIDGET_TYPE = "ECLIPSE_NOVA_IMAGE_TIMELINE_LOAD"


def default_configuration():
    return {"version": 1, "width": 0, "height": 0, "images": []}


def validate_configuration(raw):
    if not isinstance(raw, str) or len(raw) > 262144:
        raise ValueError("Image slots must be JSON text smaller than 256 KiB.")
    try:
        config = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid image slot configuration.") from error
    if not isinstance(config, dict) or set(config) != set(default_configuration()) or type(config["version"]) is not int or config["version"] != 1:
        raise ValueError("Expected version 1 image slot configuration.")
    for key in ("width", "height"):
        value = config[key]
        if type(value) not in (int, float) or not math.isfinite(value) or int(value) != value or not 0 <= value <= 8192:
            raise ValueError("Canvas width/height must be integers from 0 to 8192.")
        config[key] = int(value)
    rows = config["images"]
    if not isinstance(rows, list) or len(rows) > 128:
        raise ValueError("Use at most 128 image slots.")
    identifiers = set()
    selected_metadata = 0
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"id", "file", "enabled", "fit", "crop_x", "crop_y", "blend_mode", "blend_duration", "use_metadata", "metadata_fields"}:
            raise ValueError("Invalid image slot fields.")
        if not isinstance(row["id"], str) or not 0 < len(row["id"]) <= 128 or row["id"] in identifiers:
            raise ValueError("Image slot IDs must be unique.")
        identifiers.add(row["id"])
        if type(row["enabled"]) is not bool or type(row["use_metadata"]) is not bool:
            raise ValueError("Image slot switches must be enabled or disabled.")
        file = row["file"]
        if file is not None and (
                not isinstance(file, dict) or set(file) != {"source", "filename"} or file["source"] not in ("input", "output")
                    or not isinstance(file["filename"], str) or not 0 < len(file["filename"]) <= 4096
                    or "\\" in file["filename"] or "\x00" in file["filename"]
                    or any(part in ("", ".", "..") for part in file["filename"].split("/"))):
            raise ValueError("Choose an image in the input or output folder.")
        fields = row["metadata_fields"]
        if not isinstance(fields, dict) or set(fields) != set(GENERATION_GROUPS) or any(type(v) is not bool for v in fields.values()):
            raise ValueError("Invalid metadata field selection.")
        if row["use_metadata"]:
            if not row["enabled"] or file is None:
                raise ValueError("Enable and choose the metadata source image.")
            selected_metadata += 1
        image_options([row], 1)
    if selected_metadata > 1:
        raise ValueError("Choose one image as the downstream metadata source.")
    return config


def image_path(file):
    return source_image_path({"source": file["source"], "files": {file["source"]: file["filename"]}})


def fingerprint(configuration):
    config = validate_configuration(configuration)
    return tuple((row["id"], file_fingerprint(image_path(row["file"])))
                 for row in config["images"] if row["enabled"] and row["file"] is not None)


def load_images(configuration, width=None, height=None):
    config = validate_configuration(configuration)
    rows = [row for row in config["images"] if row["enabled"] and row["file"] is not None]
    if not rows:
        raise ValueError("Add and enable at least one image slot.")
    images, settings, source_info = [], [], []
    metadata = {}
    metadata_source = None
    for row in rows:
        check_media_interrupt()
        path = image_path(row["file"])
        with Image.open(path) as original:
            # A slot is a still image, including when the source is animated.
            if row["use_metadata"]:
                metadata = selected_generation_metadata(extract_image_metadata(original), row["metadata_fields"])
                metadata_source = dict(row["file"])
            picture = ImageOps.exif_transpose(original)
            mode = "RGBA" if "A" in picture.getbands() or "transparency" in picture.info else "RGB"
            images.append(pil2tensor(picture.convert(mode)))
        settings.append({key: row[key] for key in ("id", "fit", "crop_x", "crop_y", "blend_mode", "blend_duration")})
        source_info.append(dict(row["file"]))
    width, height = output_dimensions(width if width is not None else config["width"],
                                      height if height is not None else config["height"],
                                      images[0].shape[2], images[0].shape[1])
    # The PIPE retains originals for later framing. The IMAGE socket supplies
    # one uniform batch so downstream planners see every slot in one execution.
    channels = max(image.shape[-1] for image in images)
    batch = torch.empty((len(images), height, width, channels), dtype=torch.float32)
    for index, (image, option) in enumerate(zip(images, settings)):
        picture = Image.fromarray(fit_timeline_image(image, width, height, option, preserve_alpha=True))
        fitted = pil2tensor(picture)[0]
        batch[index, ..., :3] = fitted[..., :3]
        if channels == 4:
            batch[index, ..., 3] = fitted[..., 3] if fitted.shape[-1] == 4 else 1.0
    report = f"{len(images)} images; canvas {width} × {height}. Per-slot blends lead into the next enabled image; the last blend is unused."
    report += "\nImages output: one resized/cropped batch without blending. PIPE retains the original images and slot settings."
    if metadata_source:
        report += f"\nMetadata: {metadata_source['filename']}; fields: {', '.join(metadata) or 'none available/selected'}."
    output = {**metadata, "images": images, "image_timeline_slots": settings,
              "image_timeline_sources": source_info, "width": width, "height": height,
              "image_timeline_metadata_source": metadata_source}
    return output, prepare_image_output(batch, was_batch=True), report
