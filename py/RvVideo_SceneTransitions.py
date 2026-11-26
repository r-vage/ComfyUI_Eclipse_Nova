from comfy_api.latest import io

from ..core import CATEGORY
from ..core.image_blending import BLEND_MODES
from ..core.video_scene_transitions import (
    SHOT_CHANGES,
    TRANSITIONS_TYPE,
    transition_settings,
)
from ..core.video_transitions import render_scene_transitions

_CATEGORY = CATEGORY.MAIN.value + CATEGORY.VIDEO.value


class RvVideo_TransitionToNext(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Video Transition to Next [Eclipse Nova]", display_name="Video Transition to Next", category=_CATEGORY,
            description="Choose how a scene leads into the next. Chain additional nodes for individual outgoing scenes.",
            inputs=[
                io.Int.Input("after_scene", display_name="After scene", default=0, min=0, max=1000000,
                             tooltip="0 sets the default. 1 selects the transition from scene 1 to scene 2."),
                io.Combo.Input("shot", display_name="Shot", options=list(SHOT_CHANGES), default="Cut",
                               tooltip="Continue shot keeps camera motion across compatible H3 parts. Source-video edits in lip-sync retain their cuts."),
                io.Int.Input("previous_prompt", display_name="Previous prompt influence (%)", default=0, min=0, max=100,
                             tooltip="20 mixes 20% of the previous reviewed prompt with 80% of the new one in its first render."),
                io.Combo.Input("picture", display_name="Picture transition", options=["cut", *BLEND_MODES], default="cut"),
                io.Float.Input("seconds", display_name="Picture transition seconds", default=0.5, min=0, max=60, step=0.1),
                io.Custom(TRANSITIONS_TYPE).Input("previous", optional=True, tooltip="Connect another Transition to Next to add an override."),
                io.Custom("PIPE").Input("image_timeline", optional=True,
                                        tooltip="Inherit Blend to next on changes of assigned image. An explicit scene override takes precedence."),
            ],
            outputs=[io.Custom(TRANSITIONS_TYPE).Output("transitions")],
        )

    @classmethod
    def execute(cls, after_scene, shot, previous_prompt, picture, seconds, previous=None, image_timeline=None):
        return io.NodeOutput(transition_settings(after_scene, shot, previous_prompt, picture, seconds, previous, image_timeline))


class RvVideo_ApplySceneTransitions(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Apply Video Timeline Transitions [Eclipse Nova]", display_name="Apply Video Timeline Transitions",
            category=_CATEGORY, description="Apply the planned picture transitions to the assembled or loaded output.",
            inputs=[io.AnyType.Input("source"), io.Custom("PIPE").Input("context", optional=True,
                      tooltip="The caption_context from Video Loop End or Load Video Run includes saved picture transitions."),
                    io.Audio.Input("audio", optional=True, tooltip="Selected final soundtrack. Native video can supply its own audio.")],
            outputs=[io.AnyType.Output("source")],
        )

    @classmethod
    def execute(cls, source, context=None, audio=None):
        return io.NodeOutput(render_scene_transitions(source, context, audio))
