"""Resolve outgoing scene choices on the retained video clock."""
from itertools import pairwise

from .image_blending import validate_blend
from .minimax_h3_segment_plan import history_length

TRANSITIONS_TYPE = "ECLIPSE_VIDEO_TRANSITIONS"
SHOT_CHANGES = ("Cut", "Continue shot")


def transition_settings(after_scene, shot, previous_prompt, picture, seconds, previous=None, image_timeline=None):
    if type(after_scene) is not int or after_scene < 0 or shot not in SHOT_CHANGES:
        raise ValueError("Select a shot change and a nonnegative outgoing scene number.")
    if type(previous_prompt) is not int or not 0 <= previous_prompt <= 100:
        raise ValueError("Previous prompt influence must be an integer from 0 to 100.")
    validate_blend(picture, seconds)
    settings = previous or {}
    rules = {**settings.get("rules", {}), after_scene: (shot, previous_prompt, picture, seconds)}
    slots = settings.get("slots", ())
    if image_timeline is not None:
        slots = tuple((row["blend_mode"], row["blend_duration"]) for row in image_timeline.get("image_timeline_slots", ()))
    return {"rules": rules, "slots": slots}


def resolve_transitions(scenes, settings, *, h3, protect_source_edits):
    if not settings:
        return {}
    rules, slots = settings["rules"], settings["slots"]
    default = rules.get(0, ("Cut", 0, "cut", 0))
    result = {}
    for number, (left, right) in enumerate(pairwise(scenes), 1):
        shot, percent, picture, seconds = rules.get(number, default)
        if number not in rules and left.image is not None and left.image != right.image and left.image < len(slots):
            slot_mode, slot_seconds = slots[left.image]
            if slot_mode != "inherit":
                picture, seconds = slot_mode, slot_seconds
        if not h3 or protect_source_edits:
            shot, percent = "Cut", 0
        if shot == "Continue shot" or percent or (picture != "cut" and seconds > 0):
            result[right.start] = {"frame": right.start, "after_scene": number, "continue": shot == "Continue shot",
                                   "previous_prompt": percent, "picture": picture, "seconds": seconds}
    return result


def motion_regions(scenes, transitions, guidance, continuous_splits, paired_endpoints):
    """Budget a hidden guide only where it can coexist with the assigned pictures."""
    regions = {}
    for i, scene in enumerate(scenes):
        follows = transitions.get(scene.start, {}).get("continue", False)
        history = 0
        anchor_start = False
        if follows and i:
            previous = scenes[i - 1]
            anchor_start = (scene.image is not None and guidance == "First and last"
                            and (paired_endpoints or previous.image == scene.image))
            if scene.image is None or guidance == "Active reference" or anchor_start or (
                    guidance == "First frame" and previous.image == scene.image):
                history = history_length(previous.end - previous.start)
        if history or ((continuous_splits or follows) and guidance == "Active reference"):
            regions[str(scene.start)] = {"incoming": history, "technical": True}
            if anchor_start:
                regions[str(scene.start)]["anchor_start"] = True
    return regions


def transition_report(metadata):
    rows = metadata.get("scene_transitions", ())
    lines = [metadata["transition_note"]] if metadata.get("transition_note") else []
    for row in rows:
        items = []
        if row["continue"]:
            shot = "continue shot"
            if "motion_frames" in row:
                count = row["motion_frames"]
                if count is None:
                    shot += " (timed action in one render)"
                elif count:
                    shot += f" ({count} retained motion frame{'s' if count != 1 else ''})"
                else:
                    shot += " (starts from the assigned image)"
            items.append(shot)
        if percent := row["previous_prompt"]:
            items.append(f"{percent}% previous / {100 - percent}% new prompt")
        if row["picture"] != "cut" and row["seconds"]:
            items.append(f"{row['picture']} {row['seconds']:g}s")
        if items:
            lines.append(f"After scene {row['after_scene']} (frame {row['frame']}) · " + ", ".join(items))
    return "\n".join(lines)


def previous_influence(metadata, start):
    return next((row["previous_prompt"] for row in metadata.get("scene_transitions", ()) if row["frame"] == start), 0)


def picture_context(metadata):
    if metadata and any(row["picture"] != "cut" and row["seconds"] for row in metadata.get("scene_transitions", ())):
        return {"video_transitions": {key: metadata[key] for key in ("scene_transitions", "scene_boundaries")}}
    return {}
