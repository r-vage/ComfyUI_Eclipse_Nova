# Main detailer connections only; detection/refinement controls remain in the panel.
from comfy_api.latest import io

from ..core import CATEGORY
from ..core.detailer_conditioning import conditioning_list, denoise_list
from ..core.detailer_pipe import assemble_pipe, segs_output


def fields():
    return [
        ('model', io.Model, False), ('clip', io.Clip, False), ('vae', io.Vae, False),
        ('positive', io.Conditioning, False), ('negative', io.Conditioning, False),
        ('bboxes', io.Custom('BBOXES'), False), ('segs', io.Custom('SEGS'), False),
        ('detection', io.String, True), ('seed', io.Int, True),
        ('sampler_name', io.AnyType, False), ('scheduler', io.AnyType, False),
        ('steps', io.Int, True), ('cfg', io.Float, True), ('denoise', io.Float, True),
    ]


class RvPipe_IO_Detailer(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        tooltips = {
            'bboxes': 'SmartLLM Detection to Bboxes or compatible pixel boxes. One group per image. Non-None replaces inherited SEGS and bypasses internal YOLO; an empty group selects nothing.',
            'segs': 'External regions. Non-None takes priority over BBOXES and internal YOLO. Retains image ownership and ControlNet hooks.',
            'detection': 'YOLO: class labels or all. External SEGS with conditioning or denoise lists: category names in list order, such as eye, mouth, breast. Use the same target string as Smart Detection; labels must match. SAM2 uses boxes, not this text.',
            'clip': 'Optional. Encode positive and negative prompts upstream; the detailer uses the supplied conditioning unchanged.',
            'positive': 'One shared conditioning or a list from an upstream text encoder, in Detection category order. Keeps weighting, guidance and other metadata. Internal YOLO uses the first conditioning.',
            'negative': 'One shared negative conditioning, or a list matching the Detection categories (including zero-out results from the positive list). Internal YOLO uses the first conditioning.',
            'denoise': 'One shared FLOAT or a FLOAT list in Detection category order, independent of detection count. Values: 0.0001 to 1. Use String Multiline string_list through Convert Primitive (FLOAT) for editable values. Requires Use pipe settings. Internal YOLO uses the first value; BBOXES require one value.',
        }
        return io.Schema(
            node_id='IO Detailer [Eclipse Nova]', display_name='IO Detailer',
            category=CATEGORY.MAIN.value + CATEGORY.PIPE.value, is_input_list=True,
            description='Assemble or unpack the main detailer PIPE fields. Accepts IO KSampler or model-loader pipes. Connected non-None values override existing fields; other metadata is preserved. Sampling overrides require Use pipe settings on the detailer.',
            inputs=[io.Custom('PIPE').Input('pipe', optional=True)] + [
                kind.Input(name, optional=True, tooltip=tooltips.get(name, ''),
                           **({'force_input': True} if force else {})) for name, kind, force in fields()],
            outputs=[io.Custom('PIPE').Output('pipe')] + [
                kind.Output(name, **({'is_output_list': True} if name in ('positive', 'negative', 'segs', 'denoise') else {}))
                for name, kind, _force in fields()] + [io.Mask.Output('mask', is_output_list=True)],
        )

    @classmethod
    def execute(cls, pipe=None, **inputs):
        context = assemble_pipe(pipe, **inputs)
        values = []
        for name, _kind, _force in fields():
            value = context.get(name)
            if name == 'segs':
                value = segs_output(value)
            elif name in ('positive', 'negative'):
                value = conditioning_list(value, name) if value is not None else [None]
            elif name == 'denoise':
                value = denoise_list(value) if value is not None else [None]
            values.append(value)
        masks = context.get('mask')
        masks = [] if masks is None else masks if isinstance(masks, list) else [masks]
        return io.NodeOutput(context, *values, masks)
