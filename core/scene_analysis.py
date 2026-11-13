"""Measured scene boundaries, disk samples and validated performance descriptions."""
import json
import math
import re
import tempfile
from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise
from pathlib import Path

import cv2
import numpy as np

from .json_store import write_json_object
from .logger import log
from .minimax_h3_segment_plan import H3_FPS
from .scene_gradual import appearance_histogram, gradual_boundaries
from .scene_motion_text import (
    motion_only_text,
    performance_motion_text,
    performance_prompt_issue,
)
from .video_stream import video_frame_source
from .video_timing import _rgb_array, check_media_interrupt, media_progress

PLAN_TYPE = "ECLIPSE_SCENE_PLAN"
JOBS_TYPE = "ECLIPSE_SCENE_JOBS"
STATE_TYPE = "ECLIPSE_SCENE_DESCRIPTIONS"
FRAME_SOURCE_TYPE = "SMARTLLM_FRAME_SOURCE"
ANALYSIS_TYPE = "ECLIPSE_SCENE_ANALYSIS"
_LOG_PREFIX = "SceneAnalysis"
APPEARANCE_MODES = ("exclude source appearance", "include source appearance")
H3_PERFORMANCE_PROMPT = (
    "The subject performs naturally to the supplied audio, with synchronized lip movements. "
    "Preserve the identity and appearance of the selected reference image."
)


@dataclass(frozen=True)
class ScenePlan:
    source: object
    metadata: dict
    scenes: tuple

    def __deepcopy__(self, memo):
        return self


def detect_scenes(video, longest_side=128, threshold=2.5, window_width=4,
                  min_content=15.0, min_scene_frames=1, *, detect_gradual=False,
                  gradual_threshold=2.3, gradual_min_change=0.2):
    try:
        from scenedetect import FrameTimecode
        from scenedetect.detectors import AdaptiveDetector
    except ImportError as error:
        raise RuntimeError("Scene Detector needs scenedetect>=0.7.2 in the ComfyUI environment") from error
    if longest_side < 16 or threshold <= 0 or window_width < 1 or min_content < 0 or min_scene_frames < 1:
        raise ValueError("Invalid scene detector settings")
    if (not isinstance(detect_gradual, bool) or not math.isfinite(gradual_threshold) or gradual_threshold <= 0
            or not math.isfinite(gradual_min_change) or not 0 < gradual_min_change <= 1):
        raise ValueError("Invalid gradual scene detector settings")
    source = video_frame_source(video)
    count = len(source.timing)
    detector = AdaptiveDetector(adaptive_threshold=threshold, min_content_val=min_content,
                                window_width=window_width, min_scene_len=min_scene_frames)
    scale = min(1, longest_side / max(source.width, source.height))
    size = (max(1, round(source.width * scale)), max(1, round(source.height * scale)))
    rate = Fraction(count, 1) / source.timing.duration
    cuts = []
    appearances = []
    progress = media_progress(count, stage="Detecting scenes")
    iterator = iter(source.frames())
    decoded = 0
    try:
        for index, frame in enumerate(iterator):
            check_media_interrupt()
            pixels = _rgb_array(frame)
            pixels = cv2.resize(pixels, size, interpolation=cv2.INTER_AREA)
            if detect_gradual:
                appearances.append(appearance_histogram(pixels))
            # PySceneDetect expects BGR. Scan every frame; LM sampling is separate.
            stamp = FrameTimecode(index, fps=rate)
            cuts.extend(c.frame_num for c in detector.process_frame(stamp, pixels[..., ::-1]))
            decoded += 1
            if progress:
                progress.update_absolute(decoded)
        if decoded:
            cuts.extend(c.frame_num for c in detector.post_process(stamp))
    finally:
        close = getattr(iterator, "close", None)
        if close:
            close()
    source.timing.validate_count(decoded)
    gradual_cuts = gradual_boundaries(appearances, cuts, window_width, min_scene_frames,
                                     gradual_threshold, gradual_min_change) if detect_gradual else []
    cuts.extend(gradual_cuts)
    boundaries = [0, *sorted({value for value in cuts if 0 < value < count}), count]
    times = (*source.timing.timestamps, source.timing.duration)
    scenes = tuple({"scene_id": index, "start_frame": start, "end_frame_exclusive": end,
                    "start_seconds": float(times[start]), "end_seconds": float(times[end]),
                    "start_time": str(times[start]), "end_time": str(times[end])}
                   for index, (start, end) in enumerate(pairwise(boundaries)))
    stream = video.get_stream_source() if callable(getattr(video, "get_stream_source", None)) else None
    metadata = {"frame_count": count, "width": source.width, "height": source.height,
                "duration_seconds": float(source.timing.duration), "source": str(stream) if isinstance(stream, (str, Path)) else "native VIDEO",
                "detector": {"method": "AdaptiveDetector", "longest_side": longest_side, "threshold": threshold,
                             "window_width": window_width, "min_content": min_content, "min_scene_frames": min_scene_frames},
                "timing": "presentation timestamps relative to the supplied VIDEO trim; end exclusive"}
    if detect_gradual:
        metadata["detector"].update(method="AdaptiveDetector + temporal appearance",
                                    gradual_threshold=gradual_threshold, gradual_min_change=gradual_min_change,
                                    gradual_cut_frames=gradual_cuts)
    return ScenePlan(source, metadata, scenes)


def limit_scene_cuts(plan, max_cuts_per_second=0.0):
    """Merge scenes around excess cuts without rescanning or shifting boundaries."""
    if not isinstance(plan, ScenePlan):
        raise TypeError("Expected Scene Detector plan")
    if (type(max_cuts_per_second) not in (int, float) or not math.isfinite(max_cuts_per_second)
            or max_cuts_per_second < 0):
        raise ValueError("Maximum cuts per second must be finite and nonnegative; zero is unlimited")
    if max_cuts_per_second == 0:
        return plan
    spacing = 1 / Fraction(str(max_cuts_per_second))
    times = plan.source.timing.timestamps
    retained = [0]
    excluded = []
    previous_time = times[plan.scenes[0]["start_frame"]]
    for index, scene in enumerate(plan.scenes[1:], start=1):
        timestamp = times[scene["start_frame"]]
        if timestamp - previous_time >= spacing:
            retained.append(index)
            previous_time = timestamp
        else:
            excluded.append(scene["start_frame"])
    retained.append(len(plan.scenes))
    scenes = []
    for index, (start, stop) in enumerate(pairwise(retained)):
        first, last = plan.scenes[start], plan.scenes[stop - 1]
        merged = {**first, "scene_id": index, "end_frame_exclusive": last["end_frame_exclusive"],
                  "end_seconds": last["end_seconds"]}
        if "end_time" in last:
            merged["end_time"] = last["end_time"]
        scenes.append(merged)
    metadata = {**plan.metadata, "cut_limit": {
        "max_cuts_per_second": max_cuts_per_second, "minimum_spacing_seconds": float(spacing),
        "input_cut_count": len(plan.scenes) - 1, "retained_cut_count": len(scenes) - 1,
        "excluded_cut_frames": sorted(set(excluded).union(plan.metadata.get("cut_limit", {}).get("excluded_cut_frames", []))),
    }}
    return ScenePlan(plan.source, metadata, tuple(scenes))


def sample_indices(start, end, mode, budget, every_nth):
    if end <= start or budget < 2 or every_nth < 1:
        raise ValueError("Invalid scene sampling range or settings")
    if mode == "uniform":
        values = np.linspace(start, end - 1, min(budget, end - start)).round().astype(int).tolist()
    elif mode == "every_nth":
        values = list(range(start, end, every_nth))
    else:
        raise ValueError("Sampling must be uniform or every_nth")
    return tuple(sorted({start, *values, end - 1}))


def frame_windows(indices, maximum, overlap):
    if maximum < 2 or not 0 <= overlap < maximum:
        raise ValueError("Window size must exceed overlap and contain at least two frames")
    start = 0
    while start < len(indices):
        window = indices[start:start + maximum]
        yield window
        if start + maximum >= len(indices):
            break
        start += maximum - overlap


@dataclass(frozen=True)
class SceneJobs:
    plan: ScenePlan
    jobs: tuple
    cache: object
    sampling: dict
    memory_frames: dict | None = None

    def __deepcopy__(self, memo):
        return self


@dataclass(frozen=True)
class DiskFrameSource:
    owner: SceneJobs
    indices: tuple
    version: int = 1

    def __len__(self):
        return len(self.indices)

    def iter_frames(self):
        for index in self.indices:
            check_media_interrupt()
            if self.owner.memory_frames is not None:
                yield self.owner.memory_frames[index]
            else:
                # uint8 on disk; only one source frame is resident during iteration.
                yield np.load(Path(self.owner.cache.name) / f"{index:09d}.npy", allow_pickle=False)

    def __deepcopy__(self, memo):
        return self


def prepare_scene_jobs(plan, sampling="uniform", samples_per_scene=8, every_nth=2,
                       max_frames=8, overlap=2, cache_root=None, storage=None):
    if not isinstance(plan, ScenePlan):
        raise TypeError("Expected Scene Detector plan")
    jobs = []
    wanted = set()
    times = plan.source.timing.timestamps
    for scene in plan.scenes:
        indices = sample_indices(scene["start_frame"], scene["end_frame_exclusive"], sampling,
                                 samples_per_scene, every_nth)
        for window_id, window in enumerate(frame_windows(indices, max_frames, overlap)):
            jobs.append({"scene_id": scene["scene_id"], "window_id": window_id,
                         "frame_indices": list(window), "frame_seconds": [float(times[index]) for index in window]})
            wanted.update(window)
    cache = tempfile.TemporaryDirectory(prefix="eclipse-scenes-", dir=cache_root)
    # Response JSON still has a diagnostic location in RAM mode. Only selected
    # images are kept resident; detection and source decoding remain streaming.
    memory_frames = {} if storage is not None and storage.mode == "memory" else None
    iterator = iter(plan.source.frames())
    try:
        saved = set()
        progress = media_progress(len(times), stage="Caching selected scene frames")
        for index, frame in enumerate(iterator):
            check_media_interrupt()
            if index in wanted:
                pixels = _rgb_array(frame)
                if memory_frames is None:
                    np.save(Path(cache.name) / f"{index:09d}.npy", pixels, allow_pickle=False)
                else:
                    memory_frames[index] = pixels.copy()
                saved.add(index)
            if progress:
                progress.update_absolute(index + 1)
        if saved != wanted:
            raise ValueError("Source changed or omitted selected frames; detect scenes again")
    except BaseException:
        cache.cleanup()
        raise
    finally:
        close = getattr(iterator, "close", None)
        if close:
            close()
    return SceneJobs(plan, tuple(jobs), cache, {"mode": sampling, "samples_per_scene": samples_per_scene,
                                              "every_nth": every_nth, "max_frames": max_frames, "overlap": overlap}, memory_frames)


def get_scene_job(jobs, index):
    if not isinstance(jobs, SceneJobs) or not 0 <= index < len(jobs.jobs):
        raise ValueError(f"Invalid scene window index {index}")
    job = jobs.jobs[index]
    context = {**job, "scene": jobs.plan.scenes[job["scene_id"]],
               "instructions": (
                   "Observe these images as one scene window in the listed order. "
                   "The first frame may already be mid-gesture: describe its existing pose separately "
                   "from movement visible within this window. Do not invent an approach, preparation "
                   "or return to rest. Compare visible body, hand/finger and facial motion; "
                   "summarize distinct changes, not one event per sample. State uncertainty "
                   "if the samples do not establish the motion or a boundary pose is not visible. "
                   "Follow the selected task's response format; this context does not require JSON. "
                   "When the task requests scene_id/window_id, copy them from this context. "
                   "Follow the selected analysis task's appearance "
                   "policy: motion analysis omits appearance entirely; full T2V description includes it. "
                   "Describe only visible evidence; do not create cuts. "
                   "Times are relative to the trimmed source VIDEO.")}
    excluded = [frame for frame in jobs.plan.metadata.get("cut_limit", {}).get("excluded_cut_frames", [])
                if job["frame_indices"][0] < frame <= job["frame_indices"][-1]]
    if excluded:
        context["excluded_source_cuts"] = [
            {"frame": frame, "seconds": float(jobs.plan.source.timing.timestamps[frame])} for frame in excluded]
        context["instructions"] += (
            " This window crosses source edits excluded by the cut limit. A sudden pose change across "
            "an excluded_source_cuts boundary is an edit, not evidence of physical movement. "
            "Do not invent a connecting action between those samples; record that uncertainty.")
    return DiskFrameSource(jobs, tuple(job["frame_indices"])), json.dumps(context, ensure_ascii=False)


_TEXT_FIELDS = ("framing", "camera_motion", "start_pose", "end_pose")
_LIST_FIELDS = ("actions", "gaze_expression", "uncertainties")


def _input_evidence(value):
    if "input_evidence" not in value:
        return None
    evidence = value["input_evidence"]
    positions = evidence.get("positions") if isinstance(evidence, dict) else None
    omitted = evidence.get("omitted_black_positions", []) if isinstance(evidence, dict) else None
    if (not isinstance(positions, list) or not isinstance(omitted, list)
            or any(type(position) is not int or position < 0 for position in positions + omitted)
            or positions != sorted(set(positions)) or omitted != sorted(set(omitted))
            or set(positions).intersection(omitted) or evidence.get("image_count") != len(positions)
            or (not positions and not (omitted and evidence.get("skipped_reason") == "all_black"))
            or (positions and evidence.get("skipped_reason") == "all_black")):
        raise ValueError("Invalid measured input evidence")
    return evidence


def _caption_observation(value):
    # Public scene_caption v1 envelope: JSON produced by the caller, while the
    # model writes ordinary task text. Never fabricate a structured pose audit.
    if type(value.get("version")) is not int or value["version"] != 1:
        raise ValueError("Expected scene_caption version 1")
    if value.get("description_mode") != "full":
        raise ValueError("Scene captions retain task text; description_mode must be full")
    for key in ("performance_prompt", "source_task", "source_response"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise ValueError(f"Scene caption {key} must contain text")
    result = {key: value[key] for key in ("format", "version", "scene_id", "window_id", "description_mode",
                                        "performance_prompt", "source_task", "source_response")}
    evidence = _input_evidence(value)
    if evidence is not None:
        result["input_evidence"] = evidence
    return result


def validate_observation(raw, scene_id, window_id):
    if not isinstance(raw, str) or len(raw) > 65536:
        raise ValueError("Expected JSON text smaller than 64 KiB")
    raw = raw.strip()
    if raw.startswith("```") and raw.endswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)[:-3].strip()
    try:
        value = json.loads(raw)
    except ValueError as error:
        raise ValueError("Expected scene JSON. For ordinary image/H3 tasks, enable Scene JSON in Smart LM Loader. "
                         "For structured scene tasks, check Max tokens or retry this window") from error
    if not isinstance(value, dict):
        raise TypeError("Expected one scene observation object")
    for key, expected in (("scene_id", scene_id), ("window_id", window_id)):
        if type(value.get(key)) is not int or value[key] != expected:
            raise ValueError(f"Response {key} must be {expected}")
    if value.get("format") == "scene_caption":
        return _caption_observation(value)
    mode = value.get("description_mode")
    if mode is not None and mode not in ("motion", "full"):
        raise ValueError("Unknown scene description_mode; expected motion or full")
    # Task-marked results generate from performance_prompt. Their separate
    # appearance audit is optional; only legacy export cleanup depends on it.
    text_fields = _TEXT_FIELDS if mode is not None else (*_TEXT_FIELDS, "appearance")
    for key in text_fields:
        if not isinstance(value.get(key), str):
            raise TypeError(f"Observation {key} must be text")
        if not value[key].strip():
            raise ValueError(f"Observation {key} is blank; describe visible evidence or state uncertainty")
    for key in _LIST_FIELDS:
        # A scalar phrase is one observation, not a reason to discard a window.
        # Keep its wording intact; commas need not separate distinct actions.
        if isinstance(value.get(key), str):
            value[key] = [value[key]] if value[key].strip() else []
        if not isinstance(value.get(key), list) or not all(isinstance(item, str) for item in value[key]):
            raise ValueError(f"Observation {key} must be a list of text")
    if not any(value[key].strip() for key in ("framing", "start_pose", "end_pose")):
        raise ValueError("Observation contains no usable framing or pose evidence")
    if not isinstance(value.get("performance_prompt"), str) or not value["performance_prompt"].strip():
        raise ValueError(performance_prompt_issue(value.get("performance_prompt")))
    warnings = value.get("review_warnings", [])
    if not isinstance(warnings, list) or any(not isinstance(item, str) for item in warnings):
        raise TypeError("Observation review_warnings must be a list of text")
    warnings = list(warnings)
    # Older cached results used contract_error for content complaints. Validate
    # the actual data above and retain usable text for review instead of losing it.
    if isinstance(value.get("contract_error"), str) and value["contract_error"].strip():
        warnings.append(value["contract_error"])
    issue = performance_prompt_issue(value["performance_prompt"])
    if issue:
        warnings.append(issue)
    result = {key: value[key] for key in ("scene_id", "window_id", *text_fields, *_LIST_FIELDS, "performance_prompt")}
    if mode is not None and "appearance" in value:
        result["appearance"] = value["appearance"]
        if mode == "motion":
            warnings.append("Motion analysis returned source appearance metadata; review the text before use.")
        elif not isinstance(value["appearance"], str) or not value["appearance"].strip():
            warnings.append("Appearance audit is blank or not text; retained for review. Generation uses performance_prompt.")
    if warnings:
        result["review_warnings"] = _unique(warnings)
    if mode is not None:
        result["description_mode"] = mode
    evidence = _input_evidence(value)
    if evidence is not None:
        result["input_evidence"] = evidence
    return result


def collect_scene_description(jobs, index, texts, state=()):
    get_scene_job(jobs, index)
    if len(state) != index:
        raise ValueError(f"Scene collector expected window {len(state)}, received {index}; wire the collector through the loop")
    texts = [texts] if isinstance(texts, str) else texts
    job = jobs.jobs[index]
    if not texts or len(texts) > len(job["frame_indices"]):
        raise ValueError(f"Scene {job['scene_id']} window {job['window_id']}: unexpected response count")
    path = Path(jobs.cache.name) / f"response-{index:05d}.json"
    # Preserve malformed responses for inspection; never log model text.
    write_json_object(path, {"job": job, "responses": list(texts)})
    try:
        observations = [validate_observation(text, job["scene_id"], job["window_id"]) for text in texts]
        for observation in observations:
            if observation.get("review_warnings"):
                log.warning(_LOG_PREFIX, f"Scene {job['scene_id']} window {job['window_id']}: "
                            "description kept for manual review; see the saved analysis and report.")
            evidence = observation.get("input_evidence")
            if evidence:
                for key, prefix in (("positions", "frame"), ("omitted_black_positions", "omitted_frame")):
                    positions = evidence.get(key, [])
                    if positions and max(positions) >= len(job["frame_indices"]):
                        raise ValueError("Observed or omitted frame position is outside this window")
                    evidence[prefix + "_indices"] = [job["frame_indices"][position] for position in positions]
                    evidence[prefix + "_seconds"] = [job["frame_seconds"][position] for position in positions]
    except (TypeError, ValueError) as error:
        raise ValueError(f"Scene {job['scene_id']} window {job['window_id']}: {error}. Response saved at {path}") from error
    return (*state, {**job, "observations": observations})


def _unique(items):
    return list(dict.fromkeys(value.strip() for value in items if value.strip()))


def performance_instruction(observations):
    """Join the paragraphs written in the analysis calls, never rebuild audit fields."""
    appearances = [item.get("appearance", "") for item in observations]
    paragraphs = []
    for item in observations:
        if not isinstance(item.get("performance_prompt"), str) or not item["performance_prompt"].strip():
            raise ValueError(performance_prompt_issue(item.get("performance_prompt")))
        # Explicit task policies produce the intended paragraph in the analysis
        # call. Retain bounded cleanup only for older, unmarked observations.
        text = item["performance_prompt"]
        if item.get("description_mode") is None:
            text = performance_motion_text(text, appearances)
        paragraph = _h3_paragraph([text])
        if not paragraph:
            raise ValueError("performance_prompt contains no transferable direction; rerun Scene Motion Analysis")
        # Shared samples can produce identical neighboring summaries. A later
        # recurrence after another window remains in its observed order.
        if not paragraphs or paragraph.casefold() != paragraphs[-1].casefold():
            paragraphs.append(paragraph)
    return " ".join(paragraphs)


def build_scene_analysis(jobs, state):
    if len(state) != len(jobs.jobs):
        raise ValueError(f"Analysis incomplete: {len(state)} of {len(jobs.jobs)} windows; no scene was dropped")
    scenes = []
    for scene in jobs.plan.scenes:
        windows = [item for item in state if item["scene_id"] == scene["scene_id"]]
        expected = [item for item in jobs.jobs if item["scene_id"] == scene["scene_id"]]
        if len(windows) != len(expected) or any({key: item[key] for key in template} != template for item, template in zip(windows, expected)):
            raise ValueError(f"Scene {scene['scene_id']} has missing or reordered windows")
        observations = [observation for window in windows for observation in window["observations"]]
        scenes.append({**scene, "windows": windows, "instruction": performance_instruction(observations),
                       "uncertainties": _unique(value for item in observations for value in item.get("uncertainties", []))})
    bundle = {"format": "eclipse_scene_analysis", "version": 2, "source": jobs.plan.metadata,
              "sampling": jobs.sampling, "scenes": scenes}
    validate_scene_analysis(bundle)
    return bundle


def validate_scene_analysis(bundle):
    if not isinstance(bundle, dict) or bundle.get("format") != "eclipse_scene_analysis" or bundle.get("version") != 2:
        raise ValueError("Expected Eclipse scene analysis version 2 with performance_prompt; rerun the reference analysis")
    scenes = bundle.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("Scene analysis must contain at least one scene")
    source = bundle.get("source", {})
    previous_frame, previous_time = 0, 0.0
    for index, scene in enumerate(scenes):
        if not isinstance(scene, dict) or type(scene.get("scene_id")) is not int or scene["scene_id"] != index:
            raise ValueError("Scene IDs must be consecutive from zero")
        start, end = scene.get("start_frame"), scene.get("end_frame_exclusive")
        begin, finish = scene.get("start_seconds"), scene.get("end_seconds")
        if type(start) is not int or type(end) is not int or start != previous_frame or end <= start:
            raise ValueError(f"Scene {index} frame ranges must be contiguous and nonempty")
        if any(type(value) not in (float, int) or not math.isfinite(value) for value in (begin, finish)):
            raise ValueError(f"Scene {index} has invalid measured timestamps")
        if not math.isclose(begin, previous_time, abs_tol=1e-8) or finish <= begin:
            raise ValueError(f"Scene {index} timestamps must be contiguous and increasing")
        if not isinstance(scene.get("instruction"), str) or not scene["instruction"].strip():
            raise ValueError(f"Scene {index} is missing its performance instruction")
        windows = scene.get("windows")
        if not isinstance(windows, list) or not windows:
            raise ValueError(f"Scene {index} is missing analysis windows; rerun the reference analysis")
        for window_id, window in enumerate(windows):
            if (not isinstance(window, dict) or window.get("scene_id") != index
                    or window.get("window_id") != window_id):
                raise ValueError(f"Scene {index} has missing or reordered windows")
            observations = window.get("observations")
            if not isinstance(observations, list) or not observations:
                raise ValueError(f"Scene {index} window {window_id} is missing observations")
            for observation in observations:
                validate_observation(json.dumps(observation), index, window_id)
        previous_frame, previous_time = end, finish
    if previous_frame != source.get("frame_count") or not math.isclose(previous_time, source.get("duration_seconds", -1), abs_tol=1e-8):
        raise ValueError("Scene ranges do not cover the complete measured source")
    return bundle


def _h3_paragraph(parts):
    sentences = []
    for part in parts:
        part = " ".join(part.split())
        if part:
            sentences.append(part if part.endswith((".", "!", "?")) else part + ".")
    return " ".join(sentences)


def _h3_shot_direction(scene, appearance_mode=APPEARANCE_MODES[0]):
    observations = [item for window in scene["windows"] for item in window["observations"]]
    modes = {item.get("description_mode") for item in observations}
    if len(modes) != 1:
        raise ValueError(f"Scene {scene['scene_id']} mixes description tasks; rerun its windows with one task")
    mode = next(iter(modes))
    if mode is not None:
        required_mode = APPEARANCE_MODES[0] if mode == "motion" else APPEARANCE_MODES[1]
        if appearance_mode != required_mode:
            task = "Scene Motion Analysis" if appearance_mode == APPEARANCE_MODES[0] else "Scene Description (T2V)"
            raise ValueError(f"This analysis uses {mode} descriptions. Select '{required_mode}' to export it, "
                             f"or rerun {task} for the requested appearance policy.")
        return _h3_paragraph([scene["instruction"]])
    # instruction is the joined performance paragraphs, or the user's explicit
    # edit. Audit fields never become a fallback generation prompt.
    direction = motion_only_text(scene["instruction"], [item["appearance"] for item in observations])
    if not direction.strip():
        raise ValueError(f"Scene {scene['scene_id']} has no transferable performance instruction")
    appearance = []
    if appearance_mode == APPEARANCE_MODES[1]:
        appearance = _unique(item["appearance"] for item in observations
                             if item["appearance"].strip().rstrip(".").casefold()
                             not in {"not visible", "not observed", "uncertain", "unknown", "none", "n/a"})
    return _h3_paragraph([*appearance, direction])


def h3_scene_part_inputs(bundle, performance_prompt=H3_PERFORMANCE_PROMPT, appearance_mode=APPEARANCE_MODES[0]):
    validate_scene_analysis(bundle)
    if appearance_mode not in APPEARANCE_MODES:
        raise ValueError("Choose whether to exclude or include source appearance")
    scenes = bundle["scenes"]
    cuts = [scene["start_seconds"] for scene in scenes[1:]]
    frames = [round(value * H3_FPS) for value in cuts]
    # Match the audio planner's ceiling for the final partial output frame.
    total = math.ceil(bundle["source"]["duration_seconds"] * H3_FPS)
    if any(not 0 < value < total for value in frames) or len(set(frames)) != len(frames):
        raise ValueError("Detected cuts collide on H3's 24 FPS timeline; review scene sensitivity before planning")
    instructions = [_h3_shot_direction(scene, appearance_mode) for scene in scenes[1:]]
    return (", ".join(format(value, ".9f") for value in cuts), instructions,
            _h3_paragraph([performance_prompt]), _h3_shot_direction(scenes[0], appearance_mode))


def scene_analysis_review_report(bundle):
    warnings = []
    for scene in bundle["scenes"]:
        for window in scene["windows"]:
            for observation in window["observations"]:
                checked = validate_observation(json.dumps(observation), scene["scene_id"], window["window_id"])
                warnings.extend(f"Scene {scene['scene_id']} window {window['window_id']}: {warning}"
                                for warning in checked.get("review_warnings", []))
    warnings = _unique(warnings)
    if not warnings:
        return ""
    return (f"\nReview needed ({len(warnings)} warnings). Prompts are kept for copying and editing "
            "in the manual inputs.\n" + "\n".join(warnings))


def save_scene_analysis(bundle, path):
    validate_scene_analysis(bundle)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_object(path, bundle)
    return str(path)


def load_scene_analysis(path):
    # Export files are immutable snapshots, not mutable configuration stores.
    # Read-only media folders must not need a sibling lock directory to import.
    return validate_scene_analysis(json.loads(Path(path).read_text(encoding="utf-8")))
