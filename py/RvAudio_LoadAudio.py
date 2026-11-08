# File/incoming audio excerpts with a shared-design panel and explicit trim inputs.

import json

from comfy_api.latest import io

from ..core import CATEGORY
from ..core.audio_loader_configuration import (
    WIDGET,
    default_configuration,
    resolved_trim,
    validate_configuration,
)
from ..core.audio_loading import (
    MISSING_AUDIO,
    audio_fingerprint,
    load_audio_excerpt,
    validate_audio_source,
)


class RvAudio_LoadAudio(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Load Audio [Eclipse Nova]", display_name="Load Audio",
            category=CATEGORY.MAIN.value + CATEGORY.AUDIO.value,
            description="Audition and trim a file or incoming AUDIO at its native sample rate. Connected start_time and duration override the panel; zero duration loads to the end.",
            inputs=[
                io.Audio.Input("audio_in", optional=True, lazy=True,
                               tooltip="Auto prefers this source. Selected file ignores it without executing its upstream branch."),
                io.Float.Input("start_time", optional=True, force_input=True, min=0.0, max=86400.0,
                               tooltip="Override the local start in seconds. Share this with captions to keep their timing aligned."),
                io.Float.Input("duration", optional=True, force_input=True, min=0.0, max=86400.0,
                               tooltip="Override the local duration in seconds. Zero means the remainder of the source."),
                io.String.Input("configuration", socketless=True, default=json.dumps(default_configuration()),
                                extra_dict={"widgetType": WIDGET, "editorSpec": {}}),
                io.Boolean.Input("enabled", optional=True, force_input=True, default=True,
                                 tooltip="False skips this loader and its preview without reading the file or incoming audio. Connect Video Run Storage's prepare output to load sources only for a new run."),
            ],
            outputs=[io.Audio.Output("audio"), io.Float.Output("duration")],
            is_output_node=True,
        )

    @classmethod
    def check_lazy_status(cls, configuration, audio_in=MISSING_AUDIO, enabled=True, **_inputs):
        config = validate_configuration(configuration)
        return ["audio_in"] if enabled and config["source"] != "Selected file" and audio_in is None else []

    @classmethod
    def validate_inputs(cls, configuration, audio_in=MISSING_AUDIO, start_time=None, duration=None, enabled=True):
        try:
            config = validate_configuration(configuration)
            resolved_trim(config, start_time, duration)
            # A connected enable control is unresolved during validation. Defer
            # availability until execution; preserve ordinary standalone checks.
            return (validate_audio_source(config["audio"], audio_in, config["source"])
                    if enabled is True else True)
        except (TypeError, ValueError, OSError) as error:
            return str(error)

    @classmethod
    def fingerprint_inputs(cls, configuration, enabled=True, **_inputs):
        if enabled is False:
            return False
        return audio_fingerprint(validate_configuration(configuration)["audio"])

    @classmethod
    def execute(cls, configuration, audio_in=None, start_time=None, duration=None, enabled=True):
        if not enabled:
            from comfy_execution.graph_utils import ExecutionBlocker

            return io.NodeOutput(ExecutionBlocker(None), ExecutionBlocker(None))
        config = validate_configuration(configuration)
        start_time, duration = resolved_trim(config, start_time, duration)
        audio, loaded_duration, ui = load_audio_excerpt(
            config["audio"], start_time, duration, audio_in, config["stop"], config["source"],
        )
        return io.NodeOutput(audio, loaded_duration, ui=ui)
