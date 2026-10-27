# Encoded conditioning and denoise per SEGS category; YOLO uses the first values.
import math
import re

from .image_helpers import is_conditioning


def conditioning_list(value, name='conditioning'):
    # A CONDITIONING contains one or more tensor/metadata pairs. Keep scheduled
    # and combined entries together; only unwrap the outer execution list.
    if value is None:
        return []
    if is_conditioning(value) or isinstance(value, (list, tuple)) and not value:
        return [value]
    if isinstance(value, (list, tuple)) and all(
        is_conditioning(item) or isinstance(item, (list, tuple)) and not item for item in value
    ):
        return list(value)
    raise ValueError(f'Detailer {name} must be encoded CONDITIONING or a list of conditionings. Connect a text encoder output.')


def label_groups(segments):
    groups = {}
    for seg in segments:
        groups.setdefault(str(seg.label).strip().casefold(), []).append(seg)
    return groups


def denoise_list(value):
    values = list(value) if isinstance(value, (list, tuple)) else [value]
    # A non-list output can carry a list inside ComfyUI's execution wrapper.
    if len(values) == 1 and isinstance(values[0], (list, tuple)):
        values = list(values[0])
    if not values:
        raise ValueError('Detailer denoise requires one value or one value per Detection category; the list is empty.')
    for index, item in enumerate(values):
        if (isinstance(item, bool) or not isinstance(item, (int, float))
                or not .0001 <= item <= 1 or not math.isfinite(item)):
            raise ValueError(f'Detailer denoise value {index + 1} must be a finite number between 0.0001 and 1. '
                             'Convert text to FLOAT before connecting it.')
    return [float(item) for item in values]


class DetailerConditioning:
    def __init__(self, context, source, detection, *, denoise=None):
        self.positive = conditioning_list(context.get('positive'), 'positive')
        self.negative = conditioning_list(context.get('negative'), 'negative')
        self.denoises = denoise_list(denoise) if denoise is not None else []
        if source == 'YOLO':
            self.denoises = self.denoises[:1]
        if not self.positive or not self.negative:
            raise ValueError('Detailer requires positive and negative conditioning in the PIPE.')
        count = max(len(self.positive), len(self.negative), len(self.denoises))
        self.group_by_label = count > 1 and source == 'SEGS'
        self.mapping = {}
        if count == 1 or source == 'YOLO':
            return
        if (len(self.positive) not in (1, count) or len(self.negative) not in (1, count)
                or len(self.denoises) not in (0, 1, count)):
            raise ValueError('Detailer positive, negative and denoise lists must match, or supply one shared value on an input.')
        if source != 'SEGS':
            raise ValueError('Multiple detailer conditionings or denoise values need labeled SEGS. Connect Smart Detection SEGS directly; BBOXES do not contain category labels.')
        categories = list(dict.fromkeys(part.strip().casefold() for part in re.split(r'[,;\r\n]+', detection) if part.strip()))
        if not categories or categories == ['all']:
            raise ValueError('A detailer category list needs names in Detection, in the same order as the encoded prompts and denoise values (for example: eye, mouth, breast).')
        if len(categories) != count:
            raise ValueError(f'Detailer received {count} category values for {len(categories)} categories. Supply one shared value or one per category.')
        self.mapping = {category: index for index, category in enumerate(categories)}

    def validate_regions(self, prepared):
        if self.mapping:
            unknown = {str(seg.label).strip().casefold() for _shape, segs in prepared for seg in segs} - self.mapping.keys()
            if unknown:
                raise ValueError('Detailer SEGS labels have no matching category: ' + ', '.join(sorted(unknown))
                                 + '. Use the exact detection labels in the category list.')

    def groups(self, regions):
        if not self.group_by_label:
            return [regions]
        grouped = label_groups(regions[1])
        order = self.mapping if self.mapping else grouped
        return [(regions[0], grouped[key]) for key in order if key in grouped]

    def conditioning(self, label):
        index = self.mapping[str(label).strip().casefold()] if self.mapping else 0
        return (self.positive[index if len(self.positive) > 1 else 0],
                self.negative[index if len(self.negative) > 1 else 0])

    def denoise(self, label, default):
        if not self.denoises:
            return default
        index = self.mapping[str(label).strip().casefold()] if len(self.denoises) > 1 else 0
        return self.denoises[index]
