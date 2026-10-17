# Smart Folder with the Eclipse Nova DOM panel; the original node remains available.

import json

import folder_paths
from comfy_api.latest import io

from ..core import CATEGORY
from ..core.smart_folder import (
    WIDGET_TYPE,
    date_folder,
    default_configuration,
    editor_spec,
    folder_pipe,
    validate_configuration,
)


class RvFolder_SmartFolder(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Smart Folder [Eclipse Nova]",
            display_name="Smart Folder",
            category=CATEGORY.MAIN.value + CATEGORY.FOLDER.value,
            description="Output folders and optional image/video dimensions in one PIPE. Aspect, resolution, custom pixels or megapixels, video loading/context/loop settings, and a separate seed section.",
            inputs=[io.String.Input("configuration", socketless=True,
                                    default=json.dumps(default_configuration()),
                                    extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": editor_spec()})],
            outputs=[io.Custom("PIPE").Output("pipe")],
            is_output_node=True,
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            validate_configuration(configuration)
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def fingerprint_inputs(cls, configuration, **_inputs):
        config = validate_configuration(configuration)
        if config.get("seed", {}).get("policy") == "random":
            return float("nan")
        return date_folder(config)

    @classmethod
    def execute(cls, configuration):
        config = validate_configuration(configuration)
        pipe = folder_pipe(config, folder_paths.get_output_directory())
        ui = {"eclipse_folder": [pipe["path"]]}
        if "seed" in pipe:
            ui["eclipse_seed"] = [str(pipe["seed"])]
        return io.NodeOutput(pipe, ui=ui)
