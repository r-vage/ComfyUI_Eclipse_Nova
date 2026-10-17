# Eclipse KSampler with compact structured settings; same sampling engine as Kargim.

import json

from comfy_api.latest import io

from ..core import CATEGORY
from ..core.common import get_workflow_node
from ..core.sampler_configuration import (
    WIDGET_TYPE,
    default_configuration,
    editor_spec,
    resolve_seed,
    validate_configuration,
)
from ..core.sampler_execution import sample_kargim


class RvSampler_KSamplerKargim(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Eclipse KSampler (Kargim) [Eclipse Nova]",
            display_name="Eclipse KSampler (Kargim)",
            category=CATEGORY.MAIN.value + CATEGORY.SAMPLER.value,
            description="Sample and decode with direct model/conditioning inputs or a PIPE. Use pipe settings gives supplied pipe parameters priority over local controls; direct model, VAE and conditioning inputs keep priority. Alpha is off by default to return RGB; enable it to keep decoded transparency.",
            inputs=[
                io.Custom("PIPE").Input("pipe", optional=True),
                io.Model.Input("model", optional=True), io.Vae.Input("vae", optional=True),
                io.Conditioning.Input("positive", optional=True), io.Conditioning.Input("negative", optional=True),
                io.Latent.Input("latent", optional=True), io.Image.Input("image", optional=True),
                io.String.Input("configuration", socketless=True,
                                default=json.dumps(default_configuration("sampler")),
                                extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": editor_spec("sampler")}),
            ],
            outputs=[io.Custom("PIPE").Output("pipe"), io.Model.Output("model"), io.Vae.Output("vae"),
                     io.Conditioning.Output("positive"), io.Conditioning.Output("negative"),
                     io.Latent.Output("latent"), io.Image.Output("image")],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo, io.Hidden.unique_id],
            is_output_node=True,
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            validate_configuration(configuration, "sampler")
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def fingerprint_inputs(cls, configuration, **_inputs):
        config = validate_configuration(configuration, "sampler")
        return float("nan") if config["seed"]["policy"] == "random" else configuration

    @classmethod
    def execute(cls, configuration, pipe=None, model=None, vae=None, positive=None, negative=None, latent=None, image=None):
        config = validate_configuration(configuration, "sampler")
        values = config["parameters"]
        seed = pipe.get("seed") if values["allow_overwrite"] and isinstance(pipe, dict) else None
        local_seed = seed is None
        if seed is None:
            seed = resolve_seed(config["seed"])
        # Record the actual seed before PreviewImage writes the workflow metadata.
        concrete = {**config, "seed": {"value": str(seed), "policy": "fixed"}}
        saved = get_workflow_node(cls.hidden.extra_pnginfo, str(cls.hidden.unique_id)) if cls.hidden.extra_pnginfo and cls.hidden.unique_id is not None else None
        if saved is not None:
            saved["widgets_values"] = [json.dumps(concrete)]
        result = sample_kargim(
            **values, seed=seed, pipe=pipe, model=model, vae=vae,
            positive=positive, negative=negative, latent=latent, image=image,
            prompt=cls.hidden.prompt, extra_pnginfo=cls.hidden.extra_pnginfo, unique_id=cls.hidden.unique_id,
        )
        # Include the resolved pipe seed so the local last-seed action also works
        # when a connected settings node controls sampling.
        result.ui = {**(result.ui or {}), "eclipse_seed": [str(result.result[0]["seed"])]}
        if local_seed and values["allow_overwrite"]:
            result.ui["eclipse_local_seed"] = [config["seed"]]
        return result
