# Structured Detailer with the shared SEGS engine and native final-image preview.

import json

import nodes
from comfy_api.latest import io

from ..core import CATEGORY
from ..core.common import get_workflow_node
from ..core.detailer_execution import detail_images
from ..core.image_helpers import unwrap_value
from ..core.sampler_configuration import (
    WIDGET_TYPE,
    default_configuration,
    editor_spec,
    resolve_seed,
    validate_configuration,
)


class RvSampler_DetailerForEach(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Detailer (SEGS/pipe) [Eclipse Nova]",
            display_name="Detailer (SEGS/pipe)",
            category=CATEGORY.MAIN.value + CATEGORY.SAMPLER.value,
            description="Detail image regions from SEGS and a BASIC_PIPE. Compact sampler, sizing, mask and seed sections. Preview shows live sampling followed by the final detailed image; disabling it leaves image outputs available.",
            is_input_list=True,
            is_output_node=True,
            inputs=[
                io.Image.Input("image", tooltip="Input images, as a batch or list."),
                io.Custom("SEGS").Input("segs", tooltip="Regions to detail, including per-frame segment ownership."),
                io.Custom("BASIC_PIPE").Input("basic_pipe", tooltip="Model, CLIP, VAE, positive and negative conditioning."),
                io.Custom("SCHEDULER_FUNC").Input("scheduler_func_opt", optional=True, tooltip="Optional custom scheduler function."),
                io.Custom("PIPE").Input("pipe_opt", optional=True,
                                        tooltip="Optional sampler settings and seed. Enable Use pipe settings to override the panel; missing/None values keep local settings."),
                io.String.Input("configuration", socketless=True,
                                default=json.dumps(default_configuration("detailer")),
                                extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": editor_spec("detailer")}),
            ],
            outputs=[io.Image.Output("image", is_output_list=True),
                     io.Custom("SEGS").Output("segs", is_output_list=True),
                     io.Custom("BASIC_PIPE").Output("basic_pipe", is_output_list=True)],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo, io.Hidden.unique_id],
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            validate_configuration(unwrap_value(configuration), "detailer")
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def fingerprint_inputs(cls, configuration, **_inputs):
        raw = unwrap_value(configuration)
        config = validate_configuration(raw, "detailer")
        pipe = unwrap_value(_inputs.get("pipe_opt"))
        pipe_seed = config["parameters"]["allow_overwrite"] and isinstance(pipe, dict) and pipe.get("seed") is not None
        return float("nan") if config["seed"]["policy"] == "random" and not pipe_seed else raw

    @classmethod
    def execute(cls, image, segs, basic_pipe, configuration, scheduler_func_opt=None, pipe_opt=None):
        config = validate_configuration(unwrap_value(configuration), "detailer")
        local_seed = dict(config["seed"])
        pipe_seed = False
        if config["parameters"]["allow_overwrite"]:
            pipe = unwrap_value(pipe_opt)
            if pipe is not None and not isinstance(pipe, dict):
                raise ValueError("Sampler settings pipe must be a PIPE dictionary.")
            pipe = pipe or {}
            for key in ("sampler_name", "scheduler", "steps", "cfg", "denoise"):
                if pipe.get(key) is not None:
                    config["parameters"][key] = pipe[key]
            if pipe.get("seed") is not None:
                value = pipe["seed"]
                if type(value) is not int or not 0 <= value <= 2**64 - 1:
                    raise ValueError("Pipe seed must be an unsigned 64-bit integer.")
                config["seed"] = {"value": str(value), "policy": "fixed"}
                pipe_seed = True
            config = validate_configuration(json.dumps(config), "detailer")
        seed = resolve_seed(config["seed"])
        extra = cls.hidden.extra_pnginfo
        saved = get_workflow_node(extra, str(cls.hidden.unique_id)) if extra and cls.hidden.unique_id is not None else None
        if saved is not None:
            saved["widgets_values"] = [json.dumps({**config, "seed": {"value": str(seed), "policy": "fixed"}})]
        parameters = {key: value for key, value in config["parameters"].items() if key != "allow_overwrite"}
        images, detailed_segs, pipes = detail_images(
            image, unwrap_value(segs), unwrap_value(basic_pipe), seed=seed,
            scheduler_func_opt=unwrap_value(scheduler_func_opt), **parameters,
        )
        ui = {"images": [], "eclipse_seed": [str(seed)]}
        if config["parameters"]["allow_overwrite"] and not pipe_seed:
            ui["eclipse_local_seed"] = [local_seed]
        if config["parameters"]["live_preview"] and images:
            # A list of HWC frames supports mixed dimensions without resizing or
            # concatenating the image outputs just to create their previews.
            preview = nodes.PreviewImage().save_images(
                images=[frame[0] for frame in images], prompt=cls.hidden.prompt, extra_pnginfo=extra,
            )
            ui["images"] = preview["ui"]["images"]
        return io.NodeOutput(images, detailed_segs, pipes, ui=ui)
