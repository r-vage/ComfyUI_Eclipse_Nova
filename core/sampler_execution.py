# Shared Kargim sampling engine for Eclipse Nova's native and DOM nodes.
# Accepts direct inputs and a PIPE, samples, decodes and returns the updated pipe.

import random
from datetime import datetime, timezone

import comfy.sample  # type: ignore
import comfy.samplers  # type: ignore
import comfy.utils  # type: ignore
import latent_preview  # type: ignore
import nodes  # type: ignore
import torch
from comfy_api.latest import io  # type: ignore

from .common import get_workflow_node
from .logger import log

_LOG_PREFIX = "Sampler (Kargim)"

# Same seed generator state for backend resolution
initial_random_state = random.getstate()
random.seed(datetime.now(timezone.utc).timestamp())
eclipse_seed_random_state = random.getstate()
random.setstate(initial_random_state)


def new_random_seed():
    global eclipse_seed_random_state
    prev_random_state = random.getstate()
    random.setstate(eclipse_seed_random_state)
    seed = random.randint(0, 2**64 - 1)
    eclipse_seed_random_state = random.getstate()
    random.setstate(prev_random_state)
    return seed


def sample_kargim(steps, cfg, sampler_name, scheduler, denoise, seed,
                  model=None, vae=None, positive=None, negative=None,
                  preview_mode="Preview", tiled_decode=False, tile_size=512,
                  latent=None, image=None, pipe=None, allow_overwrite=False,
                  *, prompt=None, extra_pnginfo=None, unique_id=None, alpha=True):
    def is_input_connected(key):
        if prompt is not None and unique_id is not None and unique_id in prompt:
            node_inputs = prompt[unique_id].get("inputs", {})
            # Converted widgets and slots connected via wires are lists in ComfyUI prompt [node_id, output_index]
            if key in node_inputs and isinstance(node_inputs[key], list):
                return True
        return False

    # Priority resolution helper:
    # For connection slots (model, vae, positive, negative, latent, image):
    # direct input ALWAYS takes priority if connected (not None), regardless of allow_overwrite.
    # For widgets: if physically connected via a wire, connected input always takes priority.
    # Otherwise, allow_overwrite dictates priority.
    def resolve_val(key, direct_val, default=None):
        is_slot = key in {"model", "vae", "positive", "negative", "latent", "image"}
        if is_slot:
            if direct_val is not None:
                return direct_val
        else:
            if is_input_connected(key):
                return direct_val

        if (
            pipe is not None
            and isinstance(pipe, dict)
            and key in pipe
            and pipe[key] is not None
        ):
            pipe_val = pipe[key]
            if allow_overwrite:
                return pipe_val
            else:
                return direct_val if direct_val is not None else pipe_val
        return direct_val if direct_val is not None else default

    # Resolve primary modules and settings
    model = resolve_val("model", model)
    vae = resolve_val("vae", vae)
    positive = resolve_val("positive", positive)
    negative = resolve_val("negative", negative)
    steps = resolve_val("steps", steps, default=8)
    cfg = resolve_val("cfg", cfg, default=1.0)
    sampler_name = resolve_val(
        "sampler_name", sampler_name, default="res_multistep"
    )
    scheduler = resolve_val("scheduler", scheduler, default="simple")
    denoise = resolve_val("denoise", denoise, default=1.0)
    seed = resolve_val("seed", seed, default=42)

    # Enforce presence of required variables
    if model is None:
        raise ValueError(
            "Eclipse KSampler (Kargim): A 'model' must be provided either directly or via the input 'pipe'."
        )
    if vae is None:
        raise ValueError(
            "Eclipse KSampler (Kargim): A 'vae' must be provided either directly or via the input 'pipe'."
        )
    if positive is None:
        raise ValueError(
            "Eclipse KSampler (Kargim): A 'positive' conditioning must be provided either directly or via the input 'pipe'."
        )
    if negative is None:
        raise ValueError(
            "Eclipse KSampler (Kargim): A 'negative' conditioning must be provided either directly or via the input 'pipe'."
        )

    # Resolve special seeds (-1, -2, -3) and save to metadata/workflow
    if seed in (-1, -2, -3):
        log.warning(
            _LOG_PREFIX,
            f'Got "{seed}" as passed seed. '
            "This shouldn't happen when queueing from the ComfyUI frontend.",
        )
        if seed in (-2, -3):
            log.warning(
                _LOG_PREFIX,
                f'Cannot {"increment" if seed == -2 else "decrement"} seed from '
                "server, but will generate a new random seed.",
            )

        original_seed = seed
        seed = new_random_seed()
        log.msg(
            _LOG_PREFIX,
            f"Server-generated random seed {seed} and saving to workflow.",
        )

        if unique_id is not None:
            if extra_pnginfo is not None:
                workflow_node = get_workflow_node(extra_pnginfo, unique_id)
                if workflow_node is not None and "widgets_values" in workflow_node:
                    for index, widget_value in enumerate(
                        workflow_node["widgets_values"]
                    ):
                        if widget_value == original_seed:
                            workflow_node["widgets_values"][index] = seed
            if prompt is not None:
                prompt_node = prompt[str(unique_id)]
                if (
                    prompt_node is not None
                    and "inputs" in prompt_node
                    and "seed" in prompt_node["inputs"]
                ):
                    prompt_node["inputs"]["seed"] = seed

    # Resolve latent and image inputs
    resolved_image = image
    if resolved_image is None and pipe is not None and isinstance(pipe, dict):
        resolved_image = pipe.get("image")

    resolved_latent = latent
    if resolved_latent is None and pipe is not None and isinstance(pipe, dict):
        resolved_latent = pipe.get("latent")

    # Prefer image if one is connected/resolved, otherwise fallback to latent
    if resolved_image is not None:
        if isinstance(resolved_image, dict) and "image" in resolved_image:
            img_tensor = resolved_image["image"]
        else:
            img_tensor = resolved_image

        pixels = img_tensor[:, :, :, :3]
        if tiled_decode:
            overlap = max(16, tile_size // 8)
            t = vae.encode_tiled(
                pixels, tile_x=tile_size, tile_y=tile_size, overlap=overlap
            )
        else:
            t = vae.encode(pixels)
        resolved_latent = {"samples": t}
    elif resolved_latent is None:
        raise ValueError(
            "Eclipse KSampler (Kargim): You must connect/provide either a 'latent' or an 'image' input."
        )

    # 1. Perform sampling
    latent_samples = resolved_latent["samples"]
    latent_samples = comfy.sample.fix_empty_latent_channels(
        model,
        latent_samples,
        resolved_latent.get("downscale_ratio_spacial", None),
        resolved_latent.get("downscale_ratio_temporal", None),
    )

    batch_inds = resolved_latent.get("batch_index")
    noise = comfy.sample.prepare_noise(latent_samples, seed, batch_inds)

    noise_mask = None
    if "noise_mask" in resolved_latent:
        noise_mask = resolved_latent["noise_mask"]

    # Conditional latent preview callback
    if preview_mode == "None":
        callback = None
    else:
        callback = latent_preview.prepare_callback(model, steps)
    disable_pbar = not comfy.utils.PROGRESS_BAR_ENABLED
    batch_size = latent_samples.shape[0]
    if batch_size > 1:
        # Process each batch element individually and concatenate
        sampled_list = []
        for i in range(batch_size):
            curr_latent = latent_samples[i : i + 1]
            curr_noise = noise[i : i + 1]
            curr_noise_mask = None
            if noise_mask is not None:
                if noise_mask.shape[0] >= batch_size:
                    curr_noise_mask = noise_mask[i : i + 1]
                else:
                    curr_noise_mask = noise_mask

            curr_samples = comfy.sample.sample(
                model,
                curr_noise,
                steps,
                cfg,
                sampler_name,
                scheduler,
                positive,
                negative,
                curr_latent,
                denoise=denoise,
                disable_noise=False,
                start_step=None,
                last_step=None,
                force_full_denoise=False,
                noise_mask=curr_noise_mask,
                callback=callback,
                disable_pbar=disable_pbar,
                seed=seed,
            )
            sampled_list.append(curr_samples)
        samples = torch.cat(sampled_list, dim=0)
    else:
        samples = comfy.sample.sample(
            model,
            noise,
            steps,
            cfg,
            sampler_name,
            scheduler,
            positive,
            negative,
            latent_samples,
            denoise=denoise,
            disable_noise=False,
            start_step=None,
            last_step=None,
            force_full_denoise=False,
            noise_mask=noise_mask,
            callback=callback,
            disable_pbar=disable_pbar,
            seed=seed,
        )

    latent_output = resolved_latent.copy()
    latent_output.pop("downscale_ratio_spacial", None)
    latent_output.pop("downscale_ratio_temporal", None)
    latent_output["samples"] = samples

    # 2. Perform VAE decode (either tiled or standard)
    if tiled_decode:
        decoder = nodes.VAEDecodeTiled()
        overlap = max(16, tile_size // 8)
        images = decoder.decode(
            vae=vae, samples=latent_output, tile_size=tile_size, overlap=overlap
        )[0]
    else:
        latent_val = latent_output["samples"]
        if latent_val.is_nested:
            latent_val = latent_val.unbind()[0]
        images = vae.decode(latent_val)
        if len(images.shape) == 5:
            images = images.reshape(
                -1, images.shape[-3], images.shape[-2], images.shape[-1]
            )

    # Apply the same channel policy to final previews, the image output and PIPE.
    # The native-widget node keeps its existing behavior via the default above.
    if not alpha and images.shape[-1] == 4:
        images = images[..., :3]

    # 3. Handle UI render preview output
    if preview_mode == "None":
        ui_output = {"images": []}
    else:
        preview_node = nodes.PreviewImage()
        save_result = preview_node.save_images(
            images=images, prompt=prompt, extra_pnginfo=extra_pnginfo
        )
        ui_output = save_result.get("ui", {})

    # Extract dimensions from images tensor (shape: [batch, height, width, channels])
    height = 0
    width = 0
    if images is not None and len(images.shape) >= 3:
        height = int(images.shape[1])
        width = int(images.shape[2])

    # Construct updated output pipe
    pipe_out = pipe.copy() if (pipe is not None and isinstance(pipe, dict)) else {}
    pipe_out.update(
        {
            "model": model,
            "vae": vae,
            "latent": latent_output,
            "image": images,
            "width": width,
            "height": height,
            "positive": positive,
            "negative": negative,
            "steps": steps,
            "cfg": cfg,
            "sampler_name": sampler_name,
            "scheduler": scheduler,
            "denoise": denoise,
            "seed": seed,
        }
    )

    # Return updated pipe, model, vae, positive, negative, latent_output, images, and UI preview data
    return io.NodeOutput(
        pipe_out,
        model,
        vae,
        positive,
        negative,
        latent_output,
        images,
        ui=ui_output,
    )
