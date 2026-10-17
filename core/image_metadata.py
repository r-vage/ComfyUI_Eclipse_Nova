# Image metadata extraction utilities for ComfyUI image nodes.
# Supports: Auto1111, EasyDiffusion, InvokeAI (modern & legacy), NovelAI,
#           ComfyUI (with workflow-based prompt tracing), DrawThings
#
# credits to comfyanonymous for the initial code of the image load node
# credits to https://github.com/Jordach/comfy-plasma for the initial code of the metadata extraction

import json
import math
import re
from typing import Any
from xml.dom import minidom

from .common import SCHEDULERS_ANY
from .image_metadata_graph import graph_metadata, metadata_object
from .logger import log

_LOG_PREFIX = "ImageMetadata"


# ============================================================================
# Mapping constants
# ============================================================================

EASYDIFFUSION_MAPPING_A = {
    "prompt": "Prompt",
    "negative_prompt": "Negative Prompt",
    "seed": "Seed",
    "use_stable_diffusion_model": "Stable Diffusion model",
    "clip_skip": "Clip Skip",
    "use_vae_model": "VAE model",
    "sampler_name": "Sampler",
    "width": "Width",
    "height": "Height",
    "num_inference_steps": "Steps",
    "guidance_scale": "Guidance Scale",
}

EASYDIFFUSION_MAPPING_B = {
    "prompt": "prompt",
    "negative_prompt": "negative_prompt",
    "seed": "seed",
    "use_stable_diffusion_model": "use_stable_diffusion_model",
    "clip_skip": "clip_skip",
    "use_vae_model": "use_vae_model",
    "sampler_name": "sampler_name",
    "width": "width",
    "height": "height",
    "num_inference_steps": "num_inference_steps",
    "guidance_scale": "guidance_scale",
}

IMV_CIVITAI_SAMPLER_MAP = {
    "Euler a": "euler_ancestral",
    "Euler": "euler",
    "LMS": "lms",
    "Heun": "heun",
    "DPM2": "dpm_2",
    "DPM2 a": "dpm_2_ancestral",
    "DPM++ 2S a": "dpmpp_2s_ancestral",
    "DPM++ 2M": "dpmpp_2m",
    "DPM++ SDE": "dpmpp_sde",
    "DPM++ 2M SDE": "dpmpp_2m_sde",
    "DPM++ 3M SDE": "dpmpp_3m_sde",
    "DPM fast": "dpm_fast",
    "DPM adaptive": "dpm_adaptive",
    "DDIM": "ddim",
    "PLMS": "plms",
    "UniPC": "uni_pc",
    "LCM": "lcm",
}

INV_CIVITAI_SCHEDULER_MAP = {
    "Karras": "karras",
    "Exponential": "exponential",
    "SGM Uniform": "sgm_uniform",
    "Simple": "simple",
    "DDIM Uniform": "ddim_uniform",
    "Beta": "beta",
    "Linear Quadratic": "linear_quadratic",
    "KL Optimal": "kl_optimal",
    "Simple Test": "simple_test",
}


# ============================================================================
# Handler functions for specific generation tools
# ============================================================================


def handle_auto1111(params):
    if params and "\nSteps:" in params:
        if "Negative prompt:" in params:
            prompt_index = [
                params.index("\nNegative prompt:"),
                params.index("\nSteps:"),
            ]
            neg = params[
                prompt_index[0] + 1 + len("Negative prompt: ") : prompt_index[-1]
            ]
        else:
            prompt_index = [params.index("\nSteps:")]
            neg = ""
        pos = params[: prompt_index[0]]
        return pos, neg
    elif params:
        if "Negative prompt:" in params:
            prompt_index = [params.index("\nNegative prompt:")]
            neg = params[prompt_index[0] + 1 + len("Negative prompt: ") :]
        else:
            prompt_index = [len(params)]
            neg = ""
        pos = params[: prompt_index[0]]
        return pos, neg
    else:
        return "", ""


def handle_ezdiff(params):
    data = json.loads(params)
    if data.get("prompt"):
        ed = EASYDIFFUSION_MAPPING_B
    else:
        ed = EASYDIFFUSION_MAPPING_A
    pos = data.get(ed["prompt"])
    data.pop(ed["prompt"])
    neg = data.get(ed["negative_prompt"])
    return pos, neg


def handle_invoke_modern(params):
    meta = json.loads(params.get("sd-metadata"))
    img = meta.get("image")
    prompt = img.get("prompt")
    index = [prompt.rfind("["), prompt.rfind("]")]
    if -1 not in index:
        pos = prompt[: index[0]]
        neg = prompt[index[0] + 1 : index[1]]
        return pos, neg
    else:
        return prompt, ""


def handle_invoke_legacy(params):
    dream = params.get("Dream")
    pi = dream.rfind('"')
    ni = [dream.rfind("["), dream.rfind("]")]
    if -1 not in ni:
        pos = dream[1 : ni[0]]
        neg = dream[ni[0] + 1 : ni[1]]
        return pos, neg
    else:
        pos = dream[1:pi]
        return pos, ""


def handle_novelai(params):
    pos = params.get("Description")
    comment = params.get("Comment", "{}")
    comment_json = json.loads(comment)  # type: ignore
    neg = comment_json.get("uc")
    return pos, neg


def handle_drawthings(params):
    try:
        data = minidom.parseString(params.get("XML:com.adobe.xmp"))
        data_json = json.loads(data.getElementsByTagName("exif:UserComment")[0].childNodes[1].childNodes[1].childNodes[0].data)  # type: ignore
    except Exception:
        return "", ""
    else:
        pos = data_json.get("c")
        neg = data_json.get("uc")
        return pos, neg


# ============================================================================
# ComfyUI metadata handler (with workflow-based prompt tracing)
# ============================================================================


def handle_comfyui(params):
    # Parameter values take priority; graph connections fill only missing fields.
    gen_data = {}
    parameters = params.get("parameters")
    if isinstance(parameters, str) and parameters.strip():
        gen_data["parameters"] = parameters
        _parse_parameters_string(gen_data)
        prompt_part = re.split(r"(?:^|\n)Steps:\s*", parameters, maxsplit=1)[0]
        positive, separator, negative = prompt_part.partition("\nNegative prompt:")
        gen_data["text_pos"] = positive.strip()
        if separator:
            gen_data["text_neg"] = negative.strip()
    for key in ("workflow", "lora_weights"):
        if key in params:
            gen_data[key] = metadata_object(params[key])
    if "sampler_name" in gen_data:
        gen_data["sampler_name"] = IMV_CIVITAI_SAMPLER_MAP.get(gen_data["sampler_name"], gen_data["sampler_name"])
    if "scheduler" in gen_data:
        gen_data["scheduler"] = INV_CIVITAI_SCHEDULER_MAP.get(gen_data["scheduler"], gen_data["scheduler"])
    recovered = graph_metadata(params.get("prompt"), params.get("workflow"), gen_data)
    for key, value in recovered.items():
        gen_data.setdefault(key, value)
    return gen_data


def _parse_parameters_string(gen_data):
    # Parse each field independently: one blank/malformed value must not hide others.
    params_str = gen_data["parameters"]
    match = re.search(r"(?:^|\n)Steps:\s*", params_str)
    if not match:
        return
    settings = params_str[match.start():].strip()
    fields = dict(re.findall(r"(?:^|,\s*)([A-Za-z][A-Za-z _]*):\s*([^,\n]*)", settings))
    for label, key, cast in (("Steps", "steps", int), ("Seed", "seed", int), ("CFG scale", "cfg_scale", float)):
        try:
            value = cast(fields.get(label, ""))
        except (ValueError, OverflowError):
            continue
        upper = 2**64 - 1 if key == "seed" else 1000000
        if 0 <= value <= upper and math.isfinite(value) and (key != "steps" or value > 0):
            gen_data[key] = value
    sampler = fields.get("Sampler", "").strip()
    if sampler:
        gen_data["sampler_name"] = sampler
        schedulers = set(INV_CIVITAI_SCHEDULER_MAP) | set(SCHEDULERS_ANY)
        for scheduler in sorted(schedulers, key=len, reverse=True):
            suffix = " " + scheduler
            if sampler.lower().endswith(suffix.lower()):
                gen_data["sampler_name"] = sampler[:-len(suffix)].strip()
                gen_data["scheduler"] = scheduler
                break
        if "scheduler" not in gen_data and fields.get("Version", "").lower() == "comfyui":
            for scheduler in sorted(set(SCHEDULERS_ANY) - {"normal"}, key=len, reverse=True):
                suffix = "_" + scheduler
                if sampler.lower().endswith(suffix.lower()):
                    gen_data["sampler_name"] = sampler[:-len(suffix)]
                    gen_data["scheduler"] = scheduler
                    break
    if fields.get("Schedule type") or fields.get("Scheduler"):
        gen_data["scheduler"] = fields.get("Schedule type") or fields["Scheduler"]
    size = re.fullmatch(r"(\d+)x(\d+)", fields.get("Size", ""))
    if size:
        gen_data["width_param"], gen_data["height_param"] = map(int, size.groups())
    hashes = re.search(r"(?:^|,\s*)Hashes:\s*", settings)
    if hashes:
        try:
            value, _ = json.JSONDecoder().raw_decode(settings[hashes.end():])
            if isinstance(value, dict):
                gen_data["model_hashes"] = value
        except (ValueError, RecursionError):
            log.debug(_LOG_PREFIX, "Image contains an unreadable model-hash field.")
    if fields.get("Version"):
        gen_data["version"] = fields["Version"]


def extract_image_metadata(img) -> dict[str, Any]:
    # Absence differs from an explicitly empty prompt or zero CFG/seed.
    result = {"width": img.width, "height": img.height}
    if any(key in img.info for key in ("parameters", "workflow", "lora_weights")) or metadata_object(img.info.get("prompt")):
        data = handle_comfyui(img.info)
        for key in ("steps", "sampler_name", "scheduler", "seed", "text_pos", "text_neg"):
            if key in data:
                result[key] = data[key]
        if "cfg_scale" in data:
            result["cfg"] = data["cfg_scale"]
        hashes = data.get("model_hashes", {})
        for key in hashes:
            if key.startswith("Model:"):
                result["model_name"] = key[len("Model:"):]
                break
    else:
        prompts = None
        try:
            if "negative_prompt" in img.info or "Negative Prompt" in img.info:
                prompts = handle_ezdiff(json.dumps(img.info))
            elif "sd-metadata" in img.info:
                prompts = handle_invoke_modern(img.info)
            elif "Dream" in img.info:
                prompts = handle_invoke_legacy(img.info)
            elif img.info.get("Software") == "NovelAI":
                prompts = handle_novelai(img.info)
            elif "XML:com.adobe.xmp" in img.info:
                prompts = handle_drawthings(img.info)
        except (ValueError, TypeError, KeyError, AttributeError):
            log.debug(_LOG_PREFIX, "Image contains unreadable prompt metadata.")
        if prompts:
            result.update({key: value for key, value in zip(("text_pos", "text_neg"), prompts) if isinstance(value, str)})
    return result


GENERATION_GROUPS = {
    "sampler": ("sampler_name", "scheduler", "steps", "cfg"),
    "positive": ("text_pos",), "negative": ("text_neg",), "seed": ("seed",),
}


def selected_generation_metadata(metadata, enabled):
    return {key: metadata[key] for group, keys in GENERATION_GROUPS.items() if enabled.get(group, False)
            for key in keys if key in metadata}


def read_generation_metadata(path):
    # Header-only read for the selected file. No image tensors or workflow in the response.
    from PIL import Image

    with Image.open(path) as image:
        data = selected_generation_metadata(extract_image_metadata(image), dict.fromkeys(GENERATION_GROUPS, True))
    if "seed" in data:
        data["seed"] = str(data["seed"])  # Preserve all 64 bits through JSON/JavaScript.
    return data
