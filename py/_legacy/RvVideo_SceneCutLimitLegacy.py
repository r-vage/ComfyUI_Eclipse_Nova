# ruff: noqa: N999 -- preserve the repository's role-based Legacy module names.
"""Minimum-spacing scene cut limiter for existing Nova workflows."""
from comfy_api.latest import io

from ...core import CATEGORY
from ...core.scene_analysis import PLAN_TYPE, limit_scene_cuts

_CATEGORY = CATEGORY.MAIN.value + CATEGORY.LEGACY.value


class RvVideo_SceneCutLimit(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="Scene Cut Limit [Eclipse Nova]", display_name="Scene Cut Limit", category=_CATEGORY,
                         description="Filter an existing scene plan before frame sampling. Keep the earliest cut meeting the spacing limit and merge across excluded cuts. Original cut positions and the complete source duration stay intact; detection is not rerun when this limit changes.",
                         inputs=[io.Custom(PLAN_TYPE).Input("scene_plan", tooltip="Connect Scene Detector's scene_plan. This node filters the existing boundaries without decoding the video again."),
                                 io.Float.Input("max_cuts_per_second", default=0.0, min=0.0, max=60.0, step=0.1,
                                                tooltip="0: unlimited. 1: at least 1 second between cuts. 2: at least 0.5 seconds. 0.5: at least 2 seconds. Keeps the earliest eligible cut and merges across excluded cuts. Spacing also applies from the start; the final scene can be shorter. Changing this limit requires new sampling and descriptions for the merged scenes.")],
                         outputs=[io.Custom(PLAN_TYPE).Output("scene_plan", tooltip="Filtered scene plan for Scene Analysis Plan. Retained cuts keep their original positions, and the complete video duration is preserved."),
                                  io.Int.Output("scene_count", tooltip="Number of scenes after filtering. Sampling can split each scene into several analysis windows, so drive the loop with window_count instead."),
                                  io.String.Output("report", tooltip="Retained scene/cut counts, number of excluded cuts and effective minimum spacing. Connect to Show Any to compare settings.")])

    @classmethod
    def execute(cls, scene_plan, max_cuts_per_second=0.0):
        plan = limit_scene_cuts(scene_plan, max_cuts_per_second)
        excluded = len(scene_plan.scenes) - len(plan.scenes)
        spacing = f"minimum spacing {1 / max_cuts_per_second:g}s" if max_cuts_per_second else "unlimited"
        return io.NodeOutput(plan, len(plan.scenes),
                             f"{len(plan.scenes) - 1} cuts / {len(plan.scenes)} scenes; {excluded} cuts excluded; {spacing}. Retained cut positions are unchanged.")
