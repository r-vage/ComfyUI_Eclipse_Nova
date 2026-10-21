# Assemble or unpack only sampler-related PIPE fields, preserving other metadata.
from comfy_api.latest import io

from ..core import CATEGORY
from ..core.sampler_configuration import editor_spec


def fields():
    result = [
        ('model_1', io.Model, False), ('model_2', io.Model, False), ('vae', io.Vae, False),
        ('positive', io.Conditioning, False), ('negative', io.Conditioning, False),
        ('latent', io.Latent, False), ('image', io.Image, False),
        ('seed', io.Int, True), ('steps', io.Int, True), ('cfg', io.Float, True),
        ('sampler_name', io.AnyType, False), ('scheduler', io.AnyType, False),
        ('denoise', io.Float, True),
    ]
    existing = {name for name, _, _ in result}
    for name, field in editor_spec('advanced')['fields'].items():
        if name in existing or name == 'allow_overwrite' or field.get('optional'):
            continue
        if name == 'second_seed':
            kind, force = io.Int, True
        elif field.get('text'):
            kind, force = io.String, True
        elif name == 'preview_mode':
            name, kind, force = 'preview', io.Boolean, True
        elif isinstance(field['default'], bool):
            kind, force = io.Boolean, True
        elif 'options' in field:
            kind, force = io.AnyType, False
        else:
            kind, force = (io.Int if field.get('integer') else io.Float), True
        result.append((name, kind, force))
    return result



class RvPipe_IO_KSampler(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id='IO KSampler [Eclipse Nova]', display_name='IO KSampler',
            category=CATEGORY.MAIN.value + CATEGORY.PIPE.value,
            description='Assemble or unpack a sampler PIPE. Connected values override pipe fields; unconnected fields and other metadata are preserved. A new image clears an inherited latent, and a new latent clears an inherited image. If both are supplied, the sampler uses the latent.',
            inputs=[io.Custom('PIPE').Input('pipe', optional=True)] + [
                kind.Input(name, optional=True, tooltip=('Optional Stage 2 model, e.g. a compatible low-noise model. When absent from the PIPE, Stage 2 reuses model_1. Ignored in standard mode; independent of Use pipe settings.' if name == 'model_2' else 'Primary model for standard sampling and Stage 1. Stored in the standard PIPE model field.' if name == 'model_1' else editor_spec('advanced')['fields'].get(name, {}).get('tooltip', '')), **({'force_input': True} if force else {}))
                for name, kind, force in fields()],
            outputs=[io.Custom('PIPE').Output('pipe')] + [kind.Output(name) for name, kind, _ in fields()],
        )

    @classmethod
    def execute(cls, pipe=None, **kwargs):
        if pipe is not None and not isinstance(pipe, dict):
            raise ValueError('Expected a PIPE dictionary.')
        context = dict(pipe or {})
        for name, _kind, _force in fields():
            if kwargs.get(name) is not None:
                context['model' if name == 'model_1' else name] = kwargs[name]
        if kwargs.get('second_seed') is None and any(kwargs.get(key) is not None for key in ('seed', 'seed_offset')):
            context.pop('second_seed', None)
        if kwargs.get('image') is not None and kwargs.get('latent') is None:
            context.pop('latent', None)
        elif kwargs.get('latent') is not None and kwargs.get('image') is None:
            context.pop('image', None)
        return io.NodeOutput(context, *(context.get('model' if name == 'model_1' else name) for name, _kind, _force in fields()))
