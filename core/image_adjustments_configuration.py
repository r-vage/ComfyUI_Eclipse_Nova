# One bounded configuration for the combined image adjustment pipeline.
import copy
import json
from pathlib import Path

import folder_paths

from .image_color_match import COLOR_MATCH_METHODS
from .image_helpers import unwrap_value
from .resolution_sizing import number, require_choice, require_fields, require_number

WIDGET_TYPE = "ECLIPSE_NOVA_IMAGE_ADJUSTMENTS"
OPTIONAL = ("soften", "scale", "color_match", "sharpen")


def choice(label, default, values):
    return {"label": label, "default": default, "choices": values}


GROUPS = {
    "soften": {
        "method": choice("Method", "wavelet", {key: label for key, label in [
            ("gaussian", "Gaussian"), ("bilateral", "Bilateral"), ("wavelet", "Wavelet"),
            ("median", "Median"), ("anisotropic", "Anisotropic"), ("edge_blur", "Edge blur")]}),
        "strength": number("Strength", .5, -1, 1, .01),
        "radius": number("Radius", 1.5, .1, 10, .1),
        "iterations": number("Iterations", 8, 1, 50),
    },
    "scale": {
        "model": {"label": "Upscale model", "default": "", "files": "upscale_models"},
        "target": choice("Target", "factor", {"factor": "Factor", "fixed": "Fixed size", "native": "Native model size"}),
        "factor": number("Factor", 2, .01, 16, .01),
        "width": number("Width", 1024, 1, 48000),
        "height": number("Height", 1024, 1, 48000),
        "resampling": choice("Resampling", "lanczos", {key: key for key in ["nearest-exact", "bilinear", "area", "bicubic", "lanczos"]}),
        "divisor": number("Divisible by", 8, 1, 256),
        "supersample": {"label": "Supersample", "default": False},
        "supersample_factor": choice("Supersample factor", "8", {str(value): f"{value}×" for value in [2, 4, 6, 8]}),
    },
    "color_match": {
        "method": choice("Method", "mkl", {key: key for key in COLOR_MATCH_METHODS}),
        "strength": number("Strength", 1, 0, 10, .01),
        "pairing": choice("Reference pairing", "first", {"first": "First reference for all frames", "frames": "Match frames; repeat last reference"}),
    },
    "color": {
        "brightness": number("Brightness", 0, -1, 1, .01),
        "contrast": number("Contrast", 1, -1, 2, .01),
        "saturation": number("Saturation", 1, 0, 5, .01),
        "temperature": number("Temperature", 0, -1, 1, .01),
        "tint": number("Tint", 0, -1, 1, .01),
        "hue": number("Hue (°)", 0, -180, 180, .1),
    },
    "detail": {
        "sharpness": number("Sharpness", 1, -5, 5, .01),
        "blur": number("Blur passes", 0, 0, 16),
        "gaussian": number("Gaussian radius", 0, 0, 1024, .1),
        "edge": number("Edge enhance", 0, 0, 1, .01),
    },
    "grade": {
        "solarize": number("Solarize threshold", 0, 0, 1, .01),
        "lut": {"label": "LUT file", "default": "", "files": "luts"},
        "strength": number("LUT strength", 1, 0, 1, .01),
    },
    "sharpen": {
        "amount": number("Amount", 5, 0, 25, .5),
        "blend": number("Blend", .5, 0, 1, .01),
        "noise_radius": number("Noise radius", 7, 1, 25),
        "preserve_edges": number("Preserve edges", .75, 0, 1, .01),
    },
    "finish": {
        "vignette": number("Vignette", 0, 0, 1, .01),
        "center_x": number("Center X", .5, 0, 1, .01),
        "center_y": number("Center Y", .5, 0, 1, .01),
        "aberration": number("Chromatic aberration", 0, 0, 1, .01),
        "grain": number("Grain strength", 0, 0, 1, .01),
        "grain_size": number("Grain size", 1, 1, 10, .1),
        "grain_color": number("Grain color", 0, 0, 1, .01),
    },
}
PROCESSING = {"detail_enhance": False, "per_frame": True, "cpu_threads": False}
EXTERNAL_FACTOR = number("Connected upscale_by", 0, 0, 16, .01)

# Editor help is metadata only; saved version 1 configurations keep their values.
TOOLTIPS = {
    "soften": {
        "method": "Smoothing method before scaling. Gaussian blurs broadly; bilateral and anisotropic protect edges; wavelet adjusts fine detail; median removes isolated noise; edge blur targets detected edges.",
        "strength": "0 leaves the image unchanged. Positive values soften; negative values sharpen. Larger absolute values increase the effect before scaling.",
        "radius": "Neighborhood size for the selected spatial method. Larger values affect broader detail; edge blur also changes edge detection. Unused by wavelet and anisotropic methods.",
        "iterations": "Number of anisotropic diffusion passes. More passes smooth further and take longer. Used only by the Anisotropic method.",
    },
    "scale": {
        "model": "Optional model from models/upscale_models. None uses resampling only. A model runs at its native scale before resizing to the selected target.",
        "target": "Factor uses the original image dimensions; Fixed size sets both dimensions and can stretch the image; Native model size skips the final resize. Connected upscale_by overrides this setting when non-None.",
        "factor": "Output size relative to the original input: 1 keeps its size, 2 doubles each dimension, 0.5 halves them. Applies only to Factor target; connected upscale_by takes priority.",
        "width": "Target width in pixels for Fixed size. Width and height are independent, so the image may stretch. Rounded to Divisible by; connected upscale_by takes priority.",
        "height": "Target height in pixels for Fixed size. Width and height are independent, so the image may stretch. Rounded to Divisible by; connected upscale_by takes priority.",
        "resampling": "Final resize filter. Nearest-exact keeps hard pixel steps; bilinear is smoother; area averages when reducing; bicubic and lanczos retain more detail but may add edge ringing. Also used for alpha.",
        "divisor": "Round each target dimension to the nearest multiple; ties round up. 1 allows any whole-pixel size. Native model size, including connected upscale_by = 0, skips rounding.",
        "supersample": "Resample above the target size before the final resize. Requires Scale with an explicit target; native size or connected upscale_by = 0 skips this. Higher factors cost more time and do not create new detail.",
        "supersample_factor": "Intermediate size multiplier, followed by reduction to the same final dimensions. Larger values cost more processing time; they do not increase the final resolution or guarantee sharper detail.",
    },
    "color_match": {
        "method": "Algorithm for transferring colors from image_ref after scaling. Different methods change tones differently; they do not copy the reference's objects or composition.",
        "strength": "0 skips color matching and does not require image_ref. 1 applies the full matched result; values between 0 and 1 blend with the target, and values above 1 exaggerate the transfer.",
        "pairing": "Use the first reference for every target, or match target and reference indices and repeat the last reference when needed. Independent of Per frame and CPU threads.",
    },
    "color": {
        "brightness": "Add a brightness offset: 0 is neutral, positive values lighten, negative values darken. Applied before contrast; values outside the image range are clipped.",
        "contrast": "Multiply RGB values: 1 is neutral, values below 1 darken, and values above 1 brighten and may clip highlights. This is a gain adjustment, not contrast around mid-gray; 0 or negative values produce black.",
        "saturation": "Color intensity: 1 is neutral, 0 is grayscale, and values above 1 increase saturation. Applied after brightness and contrast.",
        "temperature": "0 is neutral. Positive values warm the image by boosting red and some green; negative values cool it by boosting blue. Strong values can clip channels.",
        "tint": "0 is neutral. Positive values boost red and blue toward magenta; negative values boost green. Applied after temperature.",
        "hue": "Rotate hue in degrees without intentionally changing saturation or brightness. 0 is neutral; -180 and 180 reach the same opposite hues.",
    },
    "detail": {
        "sharpness": "Simple PIL sharpening at the final resolution. 1 is neutral, 0 softens, values above 1 sharpen, and negative values soften further. Independent of Smart sharpen; later blur controls can reduce its effect.",
        "blur": "Number of PIL blur passes after simple Sharpness. 0 disables this blur; additional passes smooth more and can undo fine sharpening.",
        "gaussian": "Gaussian blur radius in output pixels, applied after Blur passes. 0 disables it. Larger values blur broader features and can remove detail added by sharpening.",
        "edge": "Blend with PIL's stronger edge enhancement after blurring. 0 is off; 1 applies the full filter. High values can emphasize noise and halos.",
    },
    "grade": {
        "solarize": "Invert values at or above this threshold, before the LUT. 0 disables solarize; lower nonzero values affect more of the image.",
        "lut": "Optional 3D .cube color lookup table from models/luts, applied after solarize. None skips LUT grading; 1D LUTs are not supported.",
        "strength": "Blend with the LUT result: 0 skips it, 1 applies it fully. Unused when LUT file is None. Does not control solarize.",
    },
    "sharpen": {
        "amount": "Fixed 3×3 sharpening at the final resolution: 1 is neutral, above 1 sharpens, between 0 and 1 softens; 0 skips this branch. Requires Blend above 0. Inspect at 100% zoom; increasing Amount does not widen the sharpening radius.",
        "blend": "Mix the noise-reduced image (0) with the sharpened original (1). At 0, Amount has no effect; at 1, Noise radius and Preserve edges have no effect. This is not an overall effect opacity; disable Smart sharpen to bypass both branches.",
        "noise_radius": "Neighborhood size for bilateral noise reduction, not the sharpening radius. 1 disables noise reduction; larger values smooth broader neighborhoods. Only contributes when Blend is below 1.",
        "preserve_edges": "Protect color boundaries during noise reduction. Higher values smooth less across edges; they do not add sharpening. Only contributes with Noise radius above 1 and Blend below 1. The strongest protection is reached at 0.95.",
    },
    "finish": {
        "vignette": "Darken toward the edges around Center X/Y. 0 is off; larger values darken more. Applied after Smart sharpen.",
        "center_x": "Horizontal vignette center: 0 = left, 0.5 = middle, 1 = right. Unused when Vignette is 0.",
        "center_y": "Vertical vignette center: 0 = top, 0.5 = middle, 1 = bottom. Unused when Vignette is 0.",
        "aberration": "Separate red and blue channels radially toward the edges. 0 is off; larger values increase color fringing. Applied after sharpening, so it can reduce perceived crispness.",
        "grain": "Add random film grain last, strongest in midtones. 0 disables it; larger values add more noise. Enabled grain changes on each execution and invalidates cached results.",
        "grain_size": "Grain texture size in output pixels. 1 uses fine pixel noise; larger values produce broader, smoother grain. Unused when Grain strength is 0.",
        "grain_color": "0 uses monochrome grain; 1 uses fully colored grain, with a blend between them. Unused when Grain strength is 0.",
    },
}
MODE_TOOLTIPS = {
    "soften": "Enable smoothing or signed sharpening before scaling. Disabling retains the section's settings.",
    "scale": "Enable model upscaling and/or resampling. When disabled, upscale_by is ignored and the input dimensions stay unchanged. Settings are retained.",
    "supersample": TOOLTIPS["scale"]["supersample"],
    "color_match": "Transfer reference colors before manual adjustments. Requires image_ref when strength is above 0. Disabling retains the section's settings.",
    "sharpen": "Enable final 3×3 sharpening blended with bilateral noise reduction, after scaling and grading. Independent of Detail & blur's Sharpness. Disabling bypasses both branches and retains settings.",
    "detail": "Enable the Detail & blur section. Disabling bypasses its sharpness, blur, edge enhancement and Detail filter, hides the section and retains its settings for re-enabling.",
    "detail_enhance": "Apply the PIL DETAIL filter after the controls in Detail & blur. It adds fine contrast independently of Sharpness and Smart sharpen.",
    "per_frame": "Finish each frame before starting the next to limit memory use. Disabling processes all frames stage by stage without changing reference pairing.",
    "cpu_threads": "Parallelize eligible CPU work across up to four frames when Per frame is off. Model/GPU stages remain serial. No benefit for a single frame.",
}


def group_defaults(group):
    return {key: field["default"] for key, field in GROUPS[group].items()}


def default_configuration():
    return {"version": 1, "processing": dict(PROCESSING),
            **{group: None if group in OPTIONAL else group_defaults(group) for group in GROUPS}}


def register_luts():
    if "luts" not in folder_paths.folder_names_and_paths:
        folder_paths.folder_names_and_paths["luts"] = ([str(Path(folder_paths.models_dir) / "luts")], {".cube"})


def editor_spec():
    register_luts()
    groups = copy.deepcopy(GROUPS)
    for group, fields in groups.items():
        for key, field in fields.items():
            field["tooltip"] = TOOLTIPS[group][key]
    return {"groups": groups, "optional": OPTIONAL, "processing": dict(PROCESSING),
            "mode_tooltips": dict(MODE_TOOLTIPS),
            "files": {key: folder_paths.get_filename_list(key) for key in ["luts", "upscale_models"]}}


def selected_path(category, name):
    if category == "luts":
        register_luts()
    path = folder_paths.get_full_path(category, name)
    if not path:
        raise ValueError(f"Selected {category} file is missing: {name}")
    return path


def validate_configuration(raw, *, check_files=True):
    raw = unwrap_value(raw)
    if not isinstance(raw, str) or len(raw) > 16384:
        raise ValueError("Image adjustments configuration must be a JSON string of at most 16 KB.")
    try:
        config = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid image adjustments configuration JSON.") from error
    require_fields(config, ("version", "processing", *GROUPS))
    if type(config["version"]) is not int or config["version"] != 1:
        raise ValueError("Expected version 1 image adjustments configuration.")
    require_fields(config["processing"], PROCESSING, name="Processing options")
    if any(type(value) is not bool for value in config["processing"].values()):
        raise ValueError("Processing options must be enabled or disabled.")
    for group, fields in GROUPS.items():
        values = config[group]
        if group in OPTIONAL and values is None:
            continue
        require_fields(values, fields, name=group.replace("_", " ").title())
        for key, field in fields.items():
            value = values[key]
            if "min" in field:
                require_number(value, field)
            elif "choices" in field:
                require_choice(value, field["choices"], field["label"])
            elif "files" in field:
                if not isinstance(value, str) or len(value) > 1024 or "\x00" in value:
                    raise ValueError(f"{field['label']} must be a local filename.")
                if check_files and value and (group != "grade" or values["strength"] != 0):
                    selected_path(field["files"], value)
            elif type(value) is not bool:
                raise ValueError(f"{field['label']} must be enabled or disabled.")
    return config


def configuration_fingerprint(raw):
    config = validate_configuration(raw, check_files=False)
    if config["finish"]["grain"] > 0:
        return float("nan")
    files = []
    for category, name in [("upscale_models", (config["scale"] or {}).get("model")),
                           ("luts", config["grade"]["lut"] if config["grade"]["strength"] else "")]:
        if name:
            path = selected_path(category, name)
            stat = Path(path).stat()
            files.append((path, stat.st_mtime_ns, stat.st_size))
    return files
