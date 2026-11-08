# Resolved render inputs, saved before sampling. Model objects are never serialized.
import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np
import torch

from .frame_timeline import FrameTimeline
from .image_helpers import flatten_images, unwrap_value
from .json_store import read_json_object, write_json_object
from .minimax_h3_clips import REFERENCE_MODES, H3Clip, H3ClipPlan
from .minimax_h3_segment_plan import audio_shape
from .video_resume import plan_ranges, prepare_resume
from .video_run import (
    _contained_file,
    _save_array,
    create_run_directory,
    manifest_path,
)

CHECKPOINT = "checkpoint.json"


@dataclass(frozen=True)
class RenderInputs:
    plan: object
    width: int
    height: int
    images: object = None
    audio: object = None
    conditioning_audio: object = None
    prompts: object = ""
    first_part_prompt: str = ""
    reference_mode: str = "first_and_last"
    visual_condition_strength: float = 0.999
    caption_audio: object = None
    caption_start: float = 0.0

    @property
    def fps(self):
        return plan_ranges(self.plan)[1]


def render_inputs(plan, width, height, **kwargs):
    plan = unwrap_value(plan)
    kind, _, _ = plan_ranges(plan)
    if any(type(v) is not int or v < 16 for v in (width, height)):
        raise ValueError("Render width and height must be integers of at least 16 pixels.")
    data = RenderInputs(plan, width, height, **kwargs)
    if data.reference_mode not in REFERENCE_MODES:
        raise ValueError("Unknown reference-image mode in the run inputs.")
    if not math.isfinite(data.visual_condition_strength) or not 0 <= data.visual_condition_strength <= 1:
        raise ValueError("Visual condition strength must be between zero and one.")
    if not isinstance(data.first_part_prompt, str) or not (
        isinstance(data.prompts, str) or isinstance(data.prompts, (list, tuple))
        and all(isinstance(item, str) for item in data.prompts)
    ):
        raise ValueError("Run prompts must be text or a list of text.")
    if kind == "clips":
        data = replace(data, audio=plan.audio)
    else:
        for name, rate_key, count_key in (("audio", "sample_rate", "sample_count"),
                                         ("conditioning_audio", "conditioning_sample_rate", "conditioning_sample_count")):
            value = getattr(data, name)
            if value is None and name == "conditioning_audio":
                value = data.audio
                data = replace(data, conditioning_audio=value)
            waveform, rate = audio_shape(value)
            if rate != plan[rate_key] or waveform.shape[-1] != plan[count_key]:
                raise ValueError(f"Saved {name} does not match the lip-sync plan.")
        if len(flatten_images(data.images)) != plan["image_count"]:
            raise ValueError("Reference-image count does not match the lip-sync plan.")
    if data.caption_audio is None:
        data = replace(data, caption_audio=data.audio, caption_start=0.0)
    if not math.isfinite(data.caption_start) or data.caption_start < 0:
        raise ValueError("Caption excerpt start must be finite and nonnegative.")
    if data.caption_audio is not None:
        waveform, rate = audio_shape(data.caption_audio)
        if data.caption_start >= waveform.shape[-1] / rate:
            raise ValueError("Caption excerpt start is outside the full recording.")
    return data


def caption_context(data):
    return {"audio": data.caption_audio, "trim_start": data.caption_start}


def load_caption_context(run_path, audio=None):
    root = manifest_path(run_path).parent
    manifest = read_json_object(root / "run.json")
    if manifest.get("checkpoint") != CHECKPOINT:
        return {"audio": audio, "trim_start": 0.0}
    value = read_json_object(_contained_file(root, CHECKPOINT))
    item = value.get("caption_audio")
    if item is None:
        return {"audio": audio, "trim_start": 0.0}
    return {"audio": _load_audio(root, item), "trim_start": value.get("caption_start", 0.0)}


def _load_audio(root, item):
    array = np.load(_contained_file(root, item["file"]), allow_pickle=False)
    if array.dtype != np.float32 or array.ndim != 3 or array.shape[0] != 1 or min(array.shape) < 1:
        raise ValueError("Invalid checkpoint audio array.")
    rate = item["sample_rate"]
    if type(rate) is not int or rate <= 0:
        raise ValueError("Invalid checkpoint audio sample rate.")
    return {"waveform": torch.from_numpy(array), "sample_rate": rate}


def save_checkpoint(root, data, parent=None):
    root = Path(root)
    kind, fps, ranges = plan_ranges(data.plan)
    plan = ({"clips": [asdict(clip) for clip in data.plan.clips], "total_frames": data.plan.total_frames,
             "audio_source": data.plan.audio_source, "report": data.plan.report}
            if kind == "clips" else data.plan)
    value = {"format": "eclipse_render_checkpoint", "version": 1, "kind": kind,
             "plan": plan, "fps": fps, "width": data.width, "height": data.height,
             "total_parts": len(ranges), "total_frames": sum(count for _, count in ranges),
             "prompts": data.prompts, "first_part_prompt": data.first_part_prompt,
             "reference_mode": data.reference_mode, "visual_condition_strength": data.visual_condition_strength,
             "images": [], "audio": None, "conditioning_audio": None, "parent_run": parent,
             "caption_audio": None, "caption_start": data.caption_start}
    for index, pixels in enumerate(flatten_images(data.images)):
        file = f"reference_{index:05d}.npy"
        _save_array(root / file, pixels.detach().to(device="cpu", dtype=torch.float32).numpy())
        value["images"].append(file)
    for name in ("audio", "conditioning_audio", "caption_audio"):
        audio = getattr(data, name)
        if audio is not None:
            if name == "caption_audio" and audio is data.audio:
                value[name] = value["audio"]
                continue
            waveform, rate = audio_shape(audio)
            file = f"input_{name}.npy"
            _save_array(root / file, waveform.detach().to(device="cpu", dtype=torch.float32).numpy())
            value[name] = {"file": file, "sample_rate": rate}
    # Validate JSON before exposing this immutable checkpoint to an append node.
    json.dumps(value, allow_nan=False)
    write_json_object(root / CHECKPOINT, value)


def load_checkpoint(run_path):
    manifest = manifest_path(run_path)
    root = manifest.parent
    recorded = read_json_object(manifest)
    if recorded.get("checkpoint") != CHECKPOINT:
        raise ValueError("This run has no resolved render checkpoint. It can still be loaded/exported; start a new run with Video Loop Start to enable resume.")
    value = read_json_object(_contained_file(root, CHECKPOINT))
    if value.get("format") != "eclipse_render_checkpoint" or value.get("version") != 1:
        raise ValueError("Unsupported render checkpoint.")
    audios = {}
    for name in ("audio", "conditioning_audio", "caption_audio"):
        item = value.get(name)
        if item is None:
            audios[name] = None
            continue
        audios[name] = _load_audio(root, item)
    images = []
    for file in value["images"]:
        array = np.load(_contained_file(root, file), allow_pickle=False)
        if array.dtype != np.float32 or array.ndim != 4 or array.shape[0] != 1 or array.shape[-1] not in (1, 3, 4):
            raise ValueError("Invalid checkpoint reference image.")
        images.append(torch.from_numpy(array))
    plan = value["plan"]
    if value["kind"] == "clips":
        plan = H3ClipPlan(tuple(H3Clip(**item) for item in plan["clips"]), plan["total_frames"],
                          plan["audio_source"], audios["audio"], plan["report"])
    elif value["kind"] != "frames":
        raise ValueError("Unsupported checkpoint render kind.")
    data = render_inputs(plan, value["width"], value["height"], images=images or None, **audios,
                         caption_start=value.get("caption_start", 0.0),
                         **{name: value[name] for name in ("prompts", "first_part_prompt", "reference_mode", "visual_condition_strength")})
    kind, fps, ranges = plan_ranges(data.plan)
    if (kind != recorded["kind"] or fps != recorded["fps"] or data.width != recorded["width"]
            or data.height != recorded["height"] or len(ranges) != value["total_parts"]
            or sum(n for _, n in ranges) != value["total_frames"]):
        raise ValueError("Render checkpoint and saved media metadata disagree.")
    return data


def prepare_video_loop(storage, restart_part, previous=None, run_path=None, **inputs):
    if storage.run_mode == "Resume saved run":
        if not run_path or previous is None:
            raise ValueError("Resume requires source and run_path from Load Video Run.")
        data = load_checkpoint(run_path)
        previous, start, remaining, report = prepare_resume(data.plan, True, restart_part, previous,
            storage, data.width, data.height, allow_complete=True)
    elif storage.run_mode == "New run":
        data = render_inputs(**inputs)
        previous, start = None, 0
        remaining = len(plan_ranges(data.plan)[2])
        report = f"New run: {remaining} parts."
    else:
        raise ValueError("Video Loop Start is for New run or Resume saved run; route Load saved run directly to output.")
    if storage.mode == "persistent" and remaining:
        root = (getattr(previous, "run_directory", None) or getattr(previous, "_eclipse_run_directory", None)
                or create_run_directory(storage))
        save_checkpoint(root, data, run_path if storage.run_mode == "Resume saved run" else None)
        manifest = Path(root) / "run.json"
        if manifest.is_file():
            value = read_json_object(manifest)
            value.update(checkpoint=CHECKPOINT, total_parts=start + remaining,
                         total_frames=sum(n for _, n in plan_ranges(data.plan)[2]), status="partial")
            write_json_object(manifest, value)
        storage = replace(storage, run_directory=str(root))
    return data, previous, start, start + remaining, storage, report


def verify_part(data, values, completed, storage):
    if len(values) != 1:
        raise ValueError("Video Loop End requires one accumulated video/timeline.")
    source = values[0]
    expected = sum(count for _, count in plan_ranges(data.plan)[2][:completed])
    count = len(source) if isinstance(source, FrameTimeline) else source.get_frame_count()
    if count != expected:
        raise ValueError(f"Completed part has {count} accumulated frames; the saved plan requires {expected}.")
    root = getattr(source, "run_directory", None) or getattr(source, "_eclipse_run_directory", None)
    if storage.mode == "persistent":
        manifest = read_json_object(Path(root) / "run.json") if root else {}
        if manifest.get("frame_count") != expected or len(manifest.get("chunks", ())) != completed:
            raise ValueError("The completed part was not committed to its saved run.")
        return str(Path(root) / "run.json")
    return ""
