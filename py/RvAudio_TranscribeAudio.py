# Standalone audio transcription, also usable as a lyric-caption source.
import json

import nodes
from comfy_api.latest import io

from ..core import CATEGORY
from ..core.audio_transcription import TRANSCRIPTION_REVISION
from ..core.audio_transcription import cached_transcription as transcribe_audio
from ..core.lyric_alignment import LANGUAGES, model_identity
from ..core.lyric_qwen import CHOICES as WORD_TIMING_CHOICES
from ..core.lyric_qwen import REVISION as QWEN_REVISION
from ..core.lyric_qwen import TIP as WORD_TIMING_TIP
from ..core.lyric_timing import shifted_lines, srt_text
from ..core.node_debug import debug_node
from ..core.operation_panel import FingerprintedOperationPanel

_LOG_PREFIX = "TranscribeAudio"


class RvAudio_TranscribeAudio(FingerprintedOperationPanel, io.ComfyNode):
    PANEL_KIND = "transcribe"

    @classmethod
    def operation_schema(cls):
        return io.Schema(
            node_id="Transcribe Audio [Eclipse Nova]",
            display_name="Transcribe Audio",
            category=CATEGORY.MAIN.value + CATEGORY.AUDIO.value,
            is_output_node=True,
            description="Recognize speech or sung words with the local Whisper large-v3 model. Outputs text and full-audio timing for review, subtitles or lyric captions. No supplied lyrics are required.",
            inputs=[
                io.Audio.Input("audio", tooltip="Complete recording. Output timestamps start at this audio's time zero."),
                io.Combo.Input("language", options=["Auto", *LANGUAGES], default="Auto"),
                io.Combo.Input("device", options=["auto", "cpu", "cuda"], default="auto"),
                io.Combo.Input("word_timing", options=list(WORD_TIMING_CHOICES), default="whisper", tooltip=WORD_TIMING_TIP),
                io.Boolean.Input("stop", default=False,
                                 tooltip="Stop normal queues after a changed transcript. Queue again unchanged to continue. Play already ends at this node."),
                io.Audio.Input("vocals", optional=True,
                               tooltip="Optional isolated vocals with the same time zero and duration as audio (within 50 ms)."),
            ],
            outputs=[io.String.Output("transcript"), io.String.Output("timing_json"),
                     io.String.Output("srt"), io.String.Output("report")],
        )

    @classmethod
    def fingerprint_operation(cls, **kwargs):
        return model_identity(), TRANSCRIPTION_REVISION, QWEN_REVISION

    @classmethod
    @debug_node(_LOG_PREFIX, values=("language", "device"))
    def execute_operation(cls, audio, language="Auto", device="auto", vocals=None, stop=False, word_timing="whisper"):
        text, data, report = transcribe_audio(audio, language, device, vocals, word_timing)
        result = io.NodeOutput(text, json.dumps(data, ensure_ascii=False, indent=2),
                               srt_text(shifted_lines(data, data["duration"])),
                               json.dumps(report, ensure_ascii=False, indent=2))
        if stop:
            nodes.interrupt_processing()
        return result
