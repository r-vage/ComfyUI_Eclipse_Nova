# Themed recorder panel using the existing capture/session engine and routes.
import json

import comfy.model_management
from comfy_api.latest import io

from ..core import CATEGORY
from ..core.media_tool_configuration import (
    WIDGET_TYPE,
    default_configuration,
    editor_spec,
    validate_configuration,
)
from ..core.system_audio import system_audio_recorder


class RvAudio_SystemAudioRecorder(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="System Audio Recorder [Eclipse Nova]", display_name="System Audio Recorder",
            category=CATEGORY.MAIN.value + CATEGORY.AUDIO.value,
            description="Record system output at 48 kHz stereo. Start captures and queues; Stop publishes audio and releases downstream execution. Update Output reuses the retained capture.",
            not_idempotent=True,
            inputs=[io.String.Input("configuration", socketless=True, default=json.dumps(default_configuration("recorder")),
                                    extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": editor_spec("recorder")})],
            outputs=[io.Audio.Output("audio"), io.String.Output("wav_path"), io.String.Output("mp3_path"),
                     io.Float.Output("duration")],
            hidden=[io.Hidden.unique_id],
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            validate_configuration(configuration, "recorder")
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def execute(cls, configuration):
        config = validate_configuration(configuration, "recorder")
        params = config["parameters"]
        if not config["recording_token"]:
            raise ValueError("No active recording session. Press Start on the System Audio Recorder node.")
        recording = system_audio_recorder.wait_and_consume(
            node_id=str(cls.hidden.unique_id), token=config["recording_token"],
            filename_prefix=params["filename_prefix"], output_format=params["format"], bitrate=params["mp3_bitrate"],
            strip_start_silence=params["strip_start_silence"], silence_threshold_db=params["silence_threshold_db"],
            interrupt_check=comfy.model_management.throw_exception_if_processing_interrupted,
        )
        audio = {"waveform": recording.waveform.unsqueeze(0), "sample_rate": recording.sample_rate}
        return io.NodeOutput(audio, recording.wav_path, recording.mp3_path, recording.duration)
