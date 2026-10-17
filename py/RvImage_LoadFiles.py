# Single/range/step frame loading with aligned IMAGE, MASK, PIPE and filename lists.

import json

from comfy_api.latest import io
from comfy_execution.graph_utils import ExecutionBlocker

from ..core import CATEGORY
from ..core.image_loader_configuration import (
    FILES_WIDGET,
    default_files,
    editor_spec,
    validate_files,
)
from ..core.image_loading import catalog, load_files, resolve_paths


class RvImage_LoadFiles(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Load Files From Folder [Eclipse Nova]", display_name="Load Files From Folder",
            category=CATEGORY.MAIN.value + CATEGORY.IMAGE_LOADERS.value,
            description="Load image folders, individual images or explicit video paths. Single selects a frame; Range is inclusive; Step offsets that range by a batch index. Metadata, matching masks and optional resize share one editor. Iteration advances on execution only.",
            inputs=[io.String.Input("configuration", socketless=True, default=json.dumps(default_files()),
                                    extra_dict={"widgetType": FILES_WIDGET, "editorSpec": editor_spec("files")}),
                    io.Int.Input("seed_input", optional=True, force_input=True, tooltip="Freeze Single advancement while this seed is unchanged. A changed seed advances once."),
                    io.Int.Input("width", optional=True, force_input=True, min=0, max=16384, tooltip="With Custom resize, supplies Width or Custom width. Longest/Shortest uses the larger/smaller connected dimension, or the only value. None uses the panel value; 0 uses source width. Fitting and divisibility apply."),
                    io.Int.Input("height", optional=True, force_input=True, min=0, max=16384, tooltip="With Custom resize, supplies Height or Custom height. Longest/Shortest uses the larger/smaller connected dimension, or the only value. None uses the panel value; 0 uses source height. Fitting and divisibility apply.")],
            outputs=[io.Image.Output("images", is_output_list=True), io.Mask.Output("masks", is_output_list=True),
                     io.Custom("PIPE").Output("pipe", is_output_list=True), io.String.Output("files", is_output_list=True)],
            hidden=[io.Hidden.unique_id, io.Hidden.extra_pnginfo], is_output_node=True,
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            config = validate_files(configuration)
            resolve_paths(config["paths"])
        except (TypeError, ValueError, OSError) as error:
            return str(error)
        return True

    @classmethod
    def fingerprint_inputs(cls, configuration, **_inputs):
        config = validate_files(configuration)
        if config["mode"] in ("single", "step") and config[config["mode"]]["advance"] != "fixed":
            return float("nan")
        sources, _, _ = catalog(config)
        return [(str(source.path), source.path.stat().st_mtime_ns, source.path.stat().st_size) for source in sources]

    @classmethod
    def execute(cls, configuration, seed_input=None, width=None, height=None):
        config = validate_files(configuration)
        workflow = (cls.hidden.extra_pnginfo or {}).get("workflow", {})
        key = (workflow.get("id", "api"), str(cls.hidden.unique_id))
        output, info = load_files(config, key=key, seed=seed_input, width=width, height=height)
        ui = {"eclipse_loader": [info]}
        if output is None:
            blocker = ExecutionBlocker(None)
            return io.NodeOutput(blocker, blocker, blocker, blocker, ui=ui)
        return io.NodeOutput(*output, ui=ui)
