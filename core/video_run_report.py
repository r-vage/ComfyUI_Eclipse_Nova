# Model choices recorded for reference when reopening a video run.
import json

from .video_run import _contained_file
from .video_timeline import FRAME_PLAN_MODELS, MODELS, scene_image_report

_LOADER = "Smart Model Loader [SML2]"
_ROLE = "EclipseNova.videoRunLoader"


def checkpoint_family(checkpoint):
    if checkpoint.get("kind") == "clips":
        return MODELS[0]
    plan = checkpoint.get("plan")
    return FRAME_PLAN_MODELS.get(plan.get("kind"), "") if isinstance(plan, dict) else ""


def _label(value):
    return " ".join(value.splitlines()).strip()[:1024] if isinstance(value, str) else ""


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _preset_input(prompt, settings_link, family):
    # Earlier unified workflows supplied the template through a family selector.
    def source(link):
        if isinstance(link, list) and len(link) == 2 and link[1] == 0:
            return _mapping(prompt.get(str(link[0])))
        return {}

    settings = source(settings_link)
    if settings.get("class_type") != "Smart Model Loader Settings [SML2]":
        return ""
    template = _mapping(settings.get("inputs")).get("template")
    node = source(template)
    if node.get("class_type") == "Video Timeline Select [Eclipse Nova]" and family in MODELS:
        branch = ("native", "segmented", "wan")[MODELS.index(family)]
        template = _mapping(node.get("inputs")).get(branch)
        node = source(template)
    if node.get("class_type") == "PrimitiveString":
        template = _mapping(node.get("inputs")).get("value")
    return "" if template == "(inherit)" else _label(template)


def workflow_loader(workflow, prompt, family):
    nodes = _mapping(workflow).get("nodes")
    prompt = _mapping(prompt)
    panels = {str(n["id"]): n for n in nodes if isinstance(n, dict) and "id" in n
              and n.get("type") == _LOADER and n.get("mode", 0) == 0} if isinstance(nodes, list) else {}
    submitted = {str(k): n for k, n in prompt.items() if isinstance(n, dict) and n.get("class_type") == _LOADER}
    marked = [key for key, panel in panels.items() if _mapping(panel.get("properties")).get(_ROLE)]
    eligible = list(submitted) if prompt else list(panels)
    # The preceding workflow named the shared loader but did not mark its role.
    if not marked:
        marked = [key for key, panel in panels.items() if panel.get("title") == "Shared video model loader"]
    choices = [key for key in eligible if key in marked] if marked else eligible
    if len(choices) != 1:
        return {}
    key = choices[0]
    panel = panels.get(key, {})
    inputs = _mapping(submitted.get(key, {}).get("inputs"))
    if "pipe_opt" in inputs:
        preset = _preset_input(prompt, inputs["pipe_opt"], family)
        return {"preset": preset} if preset else {}
    sockets = panel.get("inputs")
    if key not in submitted and isinstance(sockets, list) and any(
            _mapping(s).get("name") == "pipe_opt" and s.get("link") is not None for s in sockets):
        return {}
    editor = _mapping(_mapping(panel.get("properties")).get("smartModelLoaderV2"))
    preset = _label(editor.get("presetName"))
    configuration = inputs.get("configuration") or _mapping(panel.get("widgets_values_named")).get("configuration")
    widgets = panel.get("widgets_values")
    if configuration is None and isinstance(widgets, list) and widgets:
        configuration = widgets[0]
    try:
        model = _label(json.loads(configuration)["model"]["resource"]["name"])
    except (KeyError, TypeError, ValueError, RecursionError):
        model = ""
    return {k: v for k, v in (("preset", preset), ("model", model)) if v}


def _document(root, manifest, key):
    if not manifest.get(key):
        return {}
    path = _contained_file(root, manifest[key])
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("Saved report metadata exceeds 32 MiB.")
    with path.open(encoding="utf-8") as stream:
        data = json.load(stream)
    return data if isinstance(data, dict) else {}


def saved_loader(root, manifest, checkpoint):
    recorded = checkpoint.get("video_loader")
    if isinstance(recorded, dict):
        return {k: value for k in ("preset", "model") if (value := _label(recorded.get(k)))}
    # Optional archives in older runs can be absent. Media remains usable.
    def archive(key):
        try:
            return _document(root, manifest, key)
        except (OSError, ValueError, TypeError, RecursionError):
            return {}

    return workflow_loader(archive("workflow"), archive("prompt"), checkpoint_family(checkpoint))


def settings_text(root, manifest, checkpoint):
    loader = saved_loader(root, manifest, checkpoint)
    lines = [f"Video task · {checkpoint_family(checkpoint) or 'Not recorded'}",
             f"Loader preset · {loader.get('preset') or 'Not recorded'}",
             f"Model file · {loader.get('model') or 'Not recorded'}"]
    metadata = _mapping(_mapping(checkpoint.get("plan")).get("source_metadata"))
    if images := scene_image_report(metadata):
        lines.append(images)
    return "\n".join(lines)


def preview_run_report(path):
    from .json_store import read_json_object

    manifest = read_json_object(path)
    if manifest.get("format") != "eclipse_video_run" or manifest.get("version") != 1:
        raise ValueError("Unsupported saved video run format.")
    checkpoint = _document(path.parent, manifest, "checkpoint")
    settings = settings_text(path.parent, manifest, checkpoint)
    parts = len(manifest["chunks"])
    frames = manifest["frame_count"]
    frame_progress = f"{frames} / {manifest['total_frames']}" if manifest.get("total_frames") else str(frames)
    part_progress = f"{parts} / {manifest['total_parts']}" if manifest.get("total_parts") else str(parts)
    return (f"{settings}\n\n{manifest['width']}×{manifest['height']} at {manifest['fps']:g} FPS\n"
            f"Saved frames · {frame_progress}\nSaved parts · {part_progress}")
