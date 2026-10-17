# Character panels retain the existing reference objects, image order and laziness.
import json

from comfy_api.latest import io

from ..core import CATEGORY
from ..core import character_references as references
from ..core import character_sheets as sheets
from ..core.character_configuration import (
    NUMBERS,
    TEXTS,
    TIPS,
    TITLES,
    WIDGET_TYPE,
    default_configuration,
    editor_spec,
    resolved_parameters,
    validate_configuration,
)

_MISSING = object()


def _configuration(kind):
    return io.String.Input("configuration", socketless=True, default=json.dumps(default_configuration(kind)),
                           extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": editor_spec(kind)})


def _overrides(kind):
    return [
        *[io.Int.Input(key, optional=True, force_input=True, min=256, max=2048, step=32, tooltip=TIPS[key])
          for key in ("width", "height") if key in NUMBERS[kind]],
        *[io.String.Input(key, optional=True, force_input=True,
                          tooltip=f"{TIPS[key]} Connected text overrides the panel; empty text clears it and None uses the local text.")
          for key in TEXTS[kind]],
    ]


def _prompt_overrides():
    return [io.String.Input("positive_override", optional=True, force_input=True,
                            tooltip="Replace the file positive. Prepare replaces Description and Instructions too. Sheet Pack still adds role mapping and Details. Empty text clears the base; None uses file text."),
            io.String.Input("negative_override", optional=True, force_input=True,
                            tooltip="Replace the file negative independently. Empty text clears it; None uses the file.")]


def _validate(configuration, kind):
    try:
        validate_configuration(configuration, kind)
    except (TypeError, ValueError) as error:
        return str(error)
    return True


def _schema(kind, inputs, outputs, description):
    title = TITLES[kind]
    return io.Schema(node_id=f"{title} [Eclipse Nova]", display_name=title,
                     category=CATEGORY.MAIN.value + CATEGORY.CHARACTER.value, description=description,
                     inputs=[*inputs, _configuration(kind)], outputs=outputs)


def _output(result):
    return io.NodeOutput(*result, ui={"eclipse_character_report": [result[-1]]})


class RvImage_CharacterReferencePrepare(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return _schema("prepare", [
            io.Image.Input("image", optional=True, lazy=True, tooltip="One source image for Reference/Extract. Generate/Disabled skip it. Prepare preserves the full image; crop upstream if needed."),
            *_prompt_overrides(), *_overrides("prepare"),
        ], [
            io.Custom("ECLIPSE_CHARACTER_REFERENCE").Output("reference", tooltip="Connect to Character Reference Select. Its mode chooses the source, generated image or no image."),
            io.String.Output("positive"), io.String.Output("negative"),
            io.Image.Output("source", tooltip="Source for the preparation encoder. None in Generate/Disabled; Select outputs the final reference."),
        ], "Prepare one face/body/clothing/rear reference using file prompts or connected overrides. Pair with Character Reference Select; the workflow's encoder and sampler generate images.")

    @classmethod
    def validate_inputs(cls, configuration):
        return _validate(configuration, "prepare")

    @classmethod
    def fingerprint_inputs(cls, positive_override=None, negative_override=None, **kwargs):
        return references.rules_fingerprint() if positive_override is None or negative_override is None else "overrides"

    @classmethod
    def check_lazy_status(cls, configuration, image=_MISSING, **kwargs):
        p = validate_configuration(configuration, "prepare")["parameters"]
        return ["image"] if p["mode"] in ("reference", "extract") and image is None else []

    @classmethod
    def execute(cls, configuration, image=None, positive_override=None, negative_override=None,
                description=None, instructions=None):
        config = validate_configuration(configuration, "prepare")
        p = resolved_parameters(config, description=description, instructions=instructions)
        return io.NodeOutput(*references.prepare_reference(**p, image=image, positive_override=positive_override, negative_override=negative_override))


class RvImage_CharacterReferencePack(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return _schema("reference_pack", [
            *[io.Image.Input(key, optional=True, tooltip=tip) for key, tip in {
                "face": "Required single identity portrait; controls identity, hair and skin tone.",
                "body": "Optional single physique reference; does not supply face or wardrobe.",
                "clothing": "Optional wardrobe reference; supply written choices for missing items.",
                "rear": "Optional compatible rear appearance; does not force rear-facing shots.",
                "anchor": "Approved assembled character. Leave empty for first assembly; becomes image_1 when supplied.",
            }.items()], *_overrides("reference_pack"),
        ], [
            io.String.Output("character_lock", tooltip="Identity, wardrobe and numbered roles for Character Shot Planner; excludes the fixed review pose and Scene."),
            io.String.Output("anchor_prompt", tooltip="Complete prompt for generating the full-body review character; this is text, not the anchor image."),
            io.String.Output("negative"),
            *[io.Image.Output(f"image_{i}", tooltip="Consecutive roles: anchor if present, face, body, clothing, rear. Pair with this Pack's prompt. Check Report.") for i in range(1, 6)],
            io.String.Output("report"),
        ], "Pack one face plus optional body, clothing, rear and approved anchor references. Connected dimensions/text override local settings. Outputs keep their numbered image-role map.")

    @classmethod
    def validate_inputs(cls, configuration):
        return _validate(configuration, "reference_pack")

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return references.rules_fingerprint()

    @classmethod
    def execute(cls, configuration, face=None, body=None, clothing=None, rear=None, anchor=None,
                width=None, height=None, identity=None, body_description=None, outfit=None, scene=None, extra_rules=None):
        config = validate_configuration(configuration, "reference_pack")
        p = resolved_parameters(config, width=width, height=height, identity=identity, body_description=body_description,
                                outfit=outfit, scene=scene, extra_rules=extra_rules)
        return _output(references.pack_references(**p, face=face, body=body, clothing=clothing, rear=rear, anchor=anchor))


class RvImage_CharacterSheetPack(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        tips = {
            "layout": "Mannequin Reference: optional framing template. Sheet: required approved mannequin guide. Mannequin Preset skips this branch.",
            "face": "Sheet/Dataset: required single identity portrait.",
            "wardrobe": "Wardrobe: required outfit photograph. Sheet: approved wardrobe board if enabled. Ignored by other stages.",
            "front_body": "Mannequin Reference only: optional original frontal physique image if enabled. Ignored by other stages and Preset.",
            "rear_body": "Mannequin Reference only: optional original rear physique image if enabled. Distinct from the finished character's rear crop.",
            "front": "Dataset: required approved single front character crop.",
            "rear": "Dataset: approved single rear character crop if enabled; does not force rear-facing shots.",
        }
        return _schema("sheet_pack", [
            *[io.Image.Input(key, optional=True, lazy=True, tooltip=tips[key]) for key in sheets.IMAGE_INPUTS],
            *_prompt_overrides(), *_overrides("sheet_pack"),
        ], [
            io.String.Output("positive", tooltip="Resolved stage prompt. Dataset: connect to Character Shot Planner's character_lock. Other stages: connect to their encoder."),
            io.String.Output("negative"),
            *[io.Image.Output(f"image_{i}", tooltip="Connect to the same Qwen encoder as positive/negative. Actual roles appear in Report; unused slots return None.") for i in range(1, 4)],
            io.String.Output("report"),
        ], "Separate mannequin, wardrobe, sheet and dataset tasks with lazy reference inputs. Connected width, height, Details and prompt overrides support shared workflow settings. Defaults and mannequin choices come from prompts/character_sheets.json.")

    @classmethod
    def validate_inputs(cls, configuration):
        return _validate(configuration, "sheet_pack")

    @classmethod
    def fingerprint_inputs(cls, configuration, positive_override=None, negative_override=None, **kwargs):
        p = validate_configuration(configuration, "sheet_pack")["parameters"]
        return sheets.rules_fingerprint() if p["stage"] == "mannequin" or positive_override is None or negative_override is None else "overrides"

    @classmethod
    def check_lazy_status(cls, configuration, **kwargs):
        p = validate_configuration(configuration, "sheet_pack")["parameters"]
        roles = sheets.active_roles(p["stage"], p["use_front_body"], p["use_rear_body"], p["use_wardrobe"], p["use_rear"], p["generation_mode"])
        return [name for name, _ in roles if name in kwargs and kwargs[name] is None]

    @classmethod
    def execute(cls, configuration, width=None, height=None, details=None, positive_override=None, negative_override=None, **images):
        config = validate_configuration(configuration, "sheet_pack")
        p = resolved_parameters(config, width=width, height=height, details=details)
        return _output(sheets.pack_sheet(**p, positive_override=positive_override, negative_override=negative_override, **images))


class RvImage_CharacterSheetSplit(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return _schema("sheet_split", [io.Image.Input("sheet", tooltip="One approved front / rear / portrait sheet. Crops pixels; does not detect or repair generated panel contents.")], [
            io.Image.Output("front"), io.Image.Output("rear"), io.Image.Output("portrait"), io.String.Output("report"),
        ], "Split one sheet into three separate single images. Auto uses actual image thirds; Manual uses saved fractional boundaries. Gutter applies in both. No width connection is needed.")

    @classmethod
    def validate_inputs(cls, configuration):
        return _validate(configuration, "sheet_split")

    @classmethod
    def execute(cls, sheet, configuration):
        p = validate_configuration(configuration, "sheet_split")["parameters"]
        return _output(sheets.split_sheet(sheet, **p))
