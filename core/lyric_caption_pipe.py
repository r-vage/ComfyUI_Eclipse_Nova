# Pipe assembly, local controls and resolved lyric-caption results.
import copy
import json

from . import lyric_caption_configuration as controls
from . import lyric_captions
from .lyric_reference import resolve_timing
from .resolution_sizing import number, require_number

CLIP_NUMBERS = {
    "trim_start": number("Trim start (s)", 0, 0, 86400, 0.1),
    "duration": number("Duration (s)", 0, 0, 86400, 0.1),
}
OVERRIDE_NUMBERS = {**CLIP_NUMBERS, **{key: controls.NUMBERS[key] for key in ("width", "height", "fps")}}


def default_configuration():
    config = controls.default_configuration()
    config["parameters"].update(language="Auto", **{key: field["default"] for key, field in CLIP_NUMBERS.items()})
    return config


def editor_spec():
    spec = controls.editor_spec()
    spec["numbers"].update(copy.deepcopy(CLIP_NUMBERS))
    spec["pipe_only"] = True
    spec["tips"].update(
        trim_start="Start of the excerpt in the full recording. Audio and captions are trimmed together.",
        duration="Seconds to render. Zero uses the rest of the recording.",
    )
    return spec


def validate_configuration(raw):
    if not isinstance(raw, str) or len(raw) > 16384:
        raise ValueError("Caption configuration must be JSON text of at most 16 KiB.")
    try:
        config = json.loads(raw)
        parameters = config["parameters"]
        clip = {key: require_number(parameters.pop(key), field) for key, field in CLIP_NUMBERS.items()}
    except (KeyError, TypeError, RecursionError) as error:
        raise ValueError("Expected pipe caption settings including trim_start and duration.") from error
    config = controls.validate_configuration(json.dumps(config))
    config["parameters"].update(clip)
    return config


def fields():
    result = [
        ("audio", "Audio", "Complete original recording. This remains the output video's soundtrack."),
        ("vocals", "Audio", "Optional full-song vocal stem with the same time zero and duration (within 50 ms)."),
        ("lyrics", "String", "Original full-song lyrics or song JSON. Blank uses the timing reference's text or automatic transcription."),
        ("corrected_lyrics", "String", "Optional complete edited lyrics. Paste the original text and correct words; blank keeps the original."),
        ("timing", "String", "Original full-song timing JSON from Transcribe Audio or a previous render. Blank creates it internally."),
        ("corrected_timing", "String", "Optional manually edited full-song timing JSON matching the selected lyrics. Blank or {} means no manual override."),
        ("background", "Background", "IMAGE, VIDEO or exact frame timeline starting at the rendered clip's zero. Background audio is ignored."),
        ("seed", "Int", "Optional unsigned 64-bit seed. A supplied value overrides the local caption-placement seed."),
    ]
    for key, field in OVERRIDE_NUMBERS.items():
        kind = "Int" if field["step"] in (1, 2) else "Float"
        result.append((key, kind, controls.TIPS.get(key, f"Override local {field['label'].lower()}.")))
    result.extend((key, kind, tip) for key, kind, tip in (
        ("video", "Video", "Rendered caption video, including its trimmed original soundtrack."),
        ("srt", "String", "Rendered clip's subtitles, with clip-relative timestamps."),
        ("report", "String", "Timing selection, corrections, alignment coverage and rendering report."),
    ))
    return result


def assemble_pipe(pipe=None, **values):
    pipe = lyric_captions._single(pipe, "pipe")
    if pipe is not None and not isinstance(pipe, dict):
        raise ValueError("Expected a PIPE dictionary.")
    context = dict(pipe or {})
    for key, _kind, _tip in fields():
        value = values.get(key)
        if key != "background":
            value = lyric_captions._single(value, key)
        elif isinstance(value, (list, tuple)) and (not value or all(item is None for item in value)):
            value = None
        if value is not None:
            # Empty strings deliberately clear inherited correction fields.
            context[key] = value
    return context


def resolve_settings(configuration, pipe):
    config = validate_configuration(configuration)
    # Chained renderers keep their own appearance and alignment choices, even
    # when the incoming pipe contains the previous render's resolved settings.
    for key in OVERRIDE_NUMBERS:
        if pipe.get(key) is not None:
            config["parameters"][key] = pipe[key]
    seed = pipe.get("seed")
    if seed is not None:
        if type(seed) is not int or not 0 <= seed < 2**64:
            raise ValueError("Caption seed must be an unsigned 64-bit integer.")
        config["seed"] = {"source": "local", "policy": "fixed", "value": str(seed)}
    config = validate_configuration(json.dumps(config))
    parameters = dict(config["parameters"])
    clip = {key: parameters.pop(key) for key in CLIP_NUMBERS}
    parameters = controls.resolve_parameters({**config, "parameters": parameters})
    return {**parameters, **clip}, controls.resolve_seed(config)


def render_pipe(pipe, configuration):
    if not isinstance(pipe, dict):
        raise TypeError("Connect a PIPE from IO Lyric Captions.")
    audio = pipe.get("audio")
    if not isinstance(audio, dict):
        raise TypeError("The lyric PIPE requires audio. Connect the complete original recording to IO Lyric Captions.")
    parameters, seed = resolve_settings(configuration, pipe)
    lyrics, timing, resolution = resolve_timing(
        audio, **{key: pipe.get(key) for key in ("lyrics", "corrected_lyrics", "timing", "corrected_timing", "vocals")},
        **{key: parameters[key] for key in ("language", "device", "unmatched_passages", "word_timing")},
    )
    result = lyric_captions.render_captions(
        audio, lyrics, corrected_timing=json.dumps(timing, ensure_ascii=False), background=pipe.get("background"),
        **parameters, seed=seed,
    )
    report = json.loads(result[2])
    warnings = list(dict.fromkeys([*resolution.get("warnings", []), *report["warnings"]]))
    report.update(resolution, warnings=warnings)
    # The output carries the actual text/timing. A second render with another
    # background reuses them directly, without recognition or word alignment.
    output = {**pipe, **parameters, "seed": seed, "video": result[0], "srt": result[1],
              "report": json.dumps(report, ensure_ascii=False, indent=2), "timing": result[3], "lyrics": result[4]}
    return output
