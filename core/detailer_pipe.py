# Shared PIPE contract for the integrated detailer and its connection-only IO node.
from .detailer_conditioning import conditioning_list, denoise_list

SAMPLING_FIELDS = ('sampler_name', 'scheduler', 'steps', 'cfg', 'denoise')
RESOURCE_FIELDS = ('model', 'clip', 'vae', 'positive', 'negative')


def one_value(value, name):
    # Unwrap ComfyUI's execution list exactly once. CONDITIONING is itself a list.
    if isinstance(value, list):
        if len(value) != 1:
            raise ValueError(f'IO Detailer: provide one {name} for the image batch, not {len(value)} values.')
        return value[0]
    return value


def read_pipe(value):
    value = one_value(value, 'PIPE')
    if value is not None and not isinstance(value, dict):
        raise ValueError('Detailer requires a PIPE dictionary. Connect IO Detailer or IO KSampler.')
    return dict(value or {})


def none_detection(value):
    # An empty detection is intentional; only None asks for internal detection.
    return value is None or (isinstance(value, (list, tuple)) and len(value) > 0
                             and all(none_detection(item) for item in value))


def assemble_pipe(pipe=None, **inputs):
    context = read_pipe(pipe)
    for name in (*RESOURCE_FIELDS, *SAMPLING_FIELDS, 'seed', 'detection'):
        if name in ('positive', 'negative'):
            value = inputs.get(name)
            if not none_detection(value):
                values = conditioning_list(value, name)
                context[name] = values[0] if len(values) == 1 else values
            continue
        if name == 'denoise':
            value = inputs.get(name)
            if not none_detection(value):
                values = denoise_list(value)
                context[name] = values[0] if len(values) == 1 else values
            continue
        value = one_value(inputs.get(name), name)
        if value is not None:
            context[name] = value
    # Keep image-list detection groups intact, including empty groups. A new
    # BBOXES connection replaces inherited SEGS instead of being shadowed by it.
    for name in ('bboxes', 'segs'):
        value = inputs.get(name)
        if not none_detection(value):
            context.pop('segs' if name == 'bboxes' else 'bboxes', None)
            context[name] = value
    return context


def basic_pipe(context):
    required = ('model', 'vae', 'positive', 'negative')
    missing = [key for key in required if context.get(key) is None]
    if missing:
        raise ValueError('Detailer PIPE is missing: ' + ', '.join(missing) + '. Connect IO Detailer or IO KSampler.')
    # Encoded conditioning does not require CLIP. Preserve it when available.
    return (context['model'], context.get('clip'), context['vae'],
            conditioning_list(context['positive'], 'positive')[0],
            conditioning_list(context['negative'], 'negative')[0])


def segs_output(value):
    if none_detection(value):
        return []
    if (isinstance(value, (list, tuple)) and len(value) == 2
            and isinstance(value[0], (list, tuple)) and len(value[0]) == 2
            and all(type(n) is int for n in value[0])):
        return [value]
    return list(value)
