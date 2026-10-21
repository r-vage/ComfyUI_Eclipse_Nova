# Shared dimension controls and validation for Nova resolution and folder panels.

import math


def number(label, default, minimum, maximum, step=1):
    return {"label": label, "default": default, "min": minimum, "max": maximum, "step": step}


DIMENSIONS = {key: number(key.title(), 1024, 16, 32768) for key in ("width", "height")}
SIZING = {
    "aspects": {name: [int(part) for part in name.split(":")] for name in
                ["1:1", "16:9", "21:9", "2:1", "3:2", "4:3", "5:4", "9:16", "9:21", "1:2", "2:3", "3:4", "4:5"]},
    "resolutions": {
        **{f"square-{side}": {"label": f"{side}²", "area": side * side, "group": "Base size"}
           for side in [512, 768, 1024, 1536, 2048]},
        **{f"mp-{mp}": {"label": f"{mp} MP", "area": int(mp * 1_000_000), "group": "Megapixels"}
           for mp in [0.25, 0.5, 1, 2, 4, 8]},
    },
    "divisors": [8, 16, 32, 64],
    "divisor": number("Divisible by", 16, 1, 32768),
    "ratio": number("Ratio", 1, 0.01, 10000, 0.01),
    "megapixels": number("Megapixels", 1, 0.000256, 1073.741824, 0.000001),
}


def require_fields(value, required, optional=(), name="Configuration"):
    if not isinstance(value, dict) or not set(required) <= value.keys() or set(value) - set(required) - set(optional):
        raise ValueError(f"{name} has missing or unsupported fields.")


def require_number(value, field):
    if (type(value) not in (int, float) or not field["min"] <= value <= field["max"]
            or not math.isfinite(value)
            or (field["step"] == 1 and int(value) != value)):
        raise ValueError(f"{field['label']} must be {'an integer ' if field['step'] == 1 else ''}between {field['min']} and {field['max']}.")
    return value


def require_choice(value, choices, label):
    if not isinstance(value, str) or value not in choices:
        raise ValueError(f"{label}: select one of {', '.join(choices)}.")


def resolve_dimensions(size):
    sizing = size["sizing"]
    require_fields(sizing, ("mode", "divisor"), ("aspect", "ratioWidth", "ratioHeight", "resolution", "megapixels"), "Size")
    require_choice(sizing["mode"], ("fixed", "preset", "megapixels"), "Size mode")
    divisor = require_number(sizing["divisor"], SIZING["divisor"])
    mode = sizing["mode"]
    required = {"mode", "divisor"}
    if mode == "fixed":
        width = require_number(size["width"], DIMENSIONS["width"])
        height = require_number(size["height"], DIMENSIONS["height"])
    else:
        required.add("aspect")
        aspect = sizing.get("aspect")
        require_choice(aspect, (*SIZING["aspects"], "custom"), "Aspect")
        if aspect == "custom":
            required.update(("ratioWidth", "ratioHeight"))
            ratio = [require_number(sizing.get(key), SIZING["ratio"]) for key in ("ratioWidth", "ratioHeight")]
        else:
            ratio = SIZING["aspects"][aspect]
        if mode == "preset":
            required.add("resolution")
            require_choice(sizing.get("resolution"), SIZING["resolutions"], "Resolution")
            area = SIZING["resolutions"][sizing["resolution"]]["area"]
        else:
            required.add("megapixels")
            area = require_number(sizing.get("megapixels"), SIZING["megapixels"]) * 1_000_000
        width = math.sqrt(area * ratio[0] / ratio[1])
        height = math.sqrt(area * ratio[1] / ratio[0])
    require_fields(sizing, required, name="Size")
    resolved = tuple(int(max(math.ceil(16 / divisor), math.floor(value / divisor + 0.5)) * divisor)
                     for value in (width, height))
    if max(resolved) > 32768:
        raise ValueError("Dimensions exceed the supported size (32768 pixels per edge).")
    return resolved


def default_image_size():
    sizing = {"mode": "preset", "aspect": "2:3", "resolution": "mp-1", "divisor": 16}
    width, height = resolve_dimensions({"sizing": sizing})
    return {"width": width, "height": height, "sizing": sizing}


def validate_size(size):
    require_fields(size, ("width", "height", "sizing"), name="Size")
    for key, field in DIMENSIONS.items():
        require_number(size[key], field)
    if (size["width"], size["height"]) != resolve_dimensions(size):
        raise ValueError("Dimensions do not match the aspect, resolution or divisor. Edit the size controls to align them.")
