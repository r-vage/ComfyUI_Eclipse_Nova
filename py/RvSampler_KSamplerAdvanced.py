# Eclipse KSampler with compact structured settings; same sampling engine as Kargim.

import json
from functools import partial

from comfy_api.latest import io

from ..core import CATEGORY
from ..core.advanced_sampler import sample_stages
from ..core.common import get_workflow_node
from ..core.sampler_configuration import (
    WIDGET_TYPE,
    default_configuration,
    editor_spec,
    resolve_seed,
    validate_configuration,
)
from ..core.sampler_execution import sample_kargim
from ..core.sampler_extras import extra_fields
from ..core.seed_cache import automatic_fingerprint, record_automatic_execution


class RvSampler_KSamplerAdvanced(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Eclipse KSampler Advanced [Eclipse Nova]",
            display_name="Eclipse KSampler Advanced",
            category=CATEGORY.MAIN.value + CATEGORY.SAMPLER.value,
            description="Standard or two-stage sampling with independent step ranges and noise controls. Stage 2 uses model_2 from the PIPE when supplied, otherwise reuses model_1, independently of Use pipe settings. Optional latent upscale runs between stages; only the final latent is decoded. Use pipe settings overrides supplied settings for both stages, upscale, decode and preview. Stage 2 uses its explicit seed when supplied, otherwise base plus offset. Optional Qwen schedule, DiT skip guidance and Detail Daemon sections always use local controls and apply to both stages; Detail Daemon is built in and needs no additional custom node.",
            inputs=[
                io.Custom("PIPE").Input("pipe"),
                io.String.Input("configuration", socketless=True,
                                default=json.dumps(default_configuration("advanced")),
                                extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": editor_spec("advanced")}),
            ],
            outputs=[io.Custom("PIPE").Output("pipe")],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo, io.Hidden.unique_id],
            is_output_node=True,
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            validate_configuration(configuration, "advanced")
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def fingerprint_inputs(cls, configuration, **_inputs):
        config = validate_configuration(configuration, "advanced")
        return automatic_fingerprint() if config["seed"]["policy"] == "random" else configuration

    @classmethod
    def execute(cls, configuration, pipe):
        if not isinstance(pipe, dict):
            raise TypeError("Connect a PIPE containing model, VAE, conditioning and a latent or image.")
        config = validate_configuration(configuration, "advanced")
        values = config["parameters"]
        if values["allow_overwrite"] and isinstance(pipe, dict):
            local_fields = extra_fields().keys()
            for key in values:
                if key == "allow_overwrite" or key in local_fields:
                    continue
                if pipe.get(key) is not None:
                    value = pipe[key]
                    if key == "second_seed":
                        if type(value) is not int or not 0 <= value < 2**64:
                            raise ValueError("Stage 2 seed must be an unsigned 64-bit integer.")
                        value = str(value)
                    values[key] = value
            if pipe.get("preview") is not None:
                if type(pipe["preview"]) is not bool:
                    raise ValueError("Preview must be a boolean.")
                values["preview_mode"] = "Preview" if pipe["preview"] else "None"
            config = validate_configuration(json.dumps(config), "advanced")
        seed = pipe.get("seed") if values["allow_overwrite"] and isinstance(pipe, dict) else None
        local_seed = seed is None
        if seed is None:
            seed = resolve_seed(config["seed"])
        if type(seed) is not int or not 0 <= seed < 2**64:
            raise ValueError("The base seed must be an unsigned 64-bit integer.")
        # A sampled pipe can contain both; continue from its latent without a lossy round trip.
        if pipe.get("latent") is not None:
            pipe = {key: value for key, value in pipe.items() if key != "image"}
        # Record the actual seed before PreviewImage writes the workflow metadata.
        concrete = {**config, "seed": {"value": str(seed), "policy": "fixed"}}
        saved = get_workflow_node(cls.hidden.extra_pnginfo, str(cls.hidden.unique_id)) if cls.hidden.extra_pnginfo and cls.hidden.unique_id is not None else None
        if saved is not None:
            saved["widgets_values"] = [json.dumps(concrete)]
        if cls.hidden.prompt is not None and str(cls.hidden.unique_id) in cls.hidden.prompt:
            cls.hidden.prompt[str(cls.hidden.unique_id)]["inputs"]["configuration"] = json.dumps(concrete)
        engine_values = {key: values[key] for key in editor_spec("sampler")["fields"]}
        # All settings have already been resolved, using the basic fields for Stage 1.
        engine_values["allow_overwrite"] = False
        result = sample_kargim(
            **engine_values, sampling_function=partial(sample_stages, parameters=values, model_2=pipe.get("model_2")), seed=seed, pipe=pipe,
            prompt=cls.hidden.prompt, extra_pnginfo=cls.hidden.extra_pnginfo, unique_id=cls.hidden.unique_id,
        )
        # Include the resolved pipe seed so the local last-seed action also works
        # when a connected settings node controls sampling.
        result.ui = {**(result.ui or {}), "eclipse_seed": [str(result.result[0]["seed"])],
                     "eclipse_preview_enabled": [values["preview_mode"] == "Preview"],
                     "eclipse_local_seed": [config["seed"] if local_seed and values["allow_overwrite"] else None]}
        out_pipe = result.result[0]
        out_pipe.update({key: value for key, value in values.items() if key not in ("allow_overwrite", "second_seed")})
        out_pipe["preview"] = values["preview_mode"] == "Preview"
        out_pipe["second_seed"] = int(values["second_seed"]) if values["second_seed"] != "" else (seed + values["seed_offset"]) % (2**64)
        out_pipe["sampling_stages"] = {"base_seed": seed, "configuration": concrete}
        if values["two_stage"]:
            out_pipe.update({key: values["second_" + key] for key in ("steps", "cfg", "sampler_name", "scheduler")})
            out_pipe["seed"] = out_pipe["second_seed"]
            out_pipe["denoise"] = 1.0
        record_automatic_execution(local_seed and config["seed"]["policy"] == "random")
        return io.NodeOutput(result.result[0], ui=result.ui)
