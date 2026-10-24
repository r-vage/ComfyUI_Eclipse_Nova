# Match generation-data records to the original image order before selection.
from bisect import bisect_right
from itertools import accumulate

from .image_helpers import flatten_images


def _contexts(value):
    if isinstance(value, (list, tuple)):
        return [context for item in value for context in _contexts(item)]
    if value is None or isinstance(value, dict):
        return [value]
    raise TypeError("IO Slice & Dice: generation-data pipes must be dictionaries.")


def select_generation_pipes(pipe, indices, images=None):
    # PIPEs are opaque generation records, not new media batches. Keep their
    # fields intact and use the dedicated image/latent outputs for sliced media.
    contexts = _contexts(pipe)
    if not contexts or all(context is None for context in contexts):
        return [None]
    if any(type(index) is not int or index < 0 for index in indices):
        raise ValueError("IO Slice & Dice: selection indices must be non-negative integers.")
    groups = list(images) if isinstance(images, (list, tuple)) else [images]
    image_counts = [len(flatten_images(group)) for group in groups]
    total = sum(image_counts)
    if total and any(index >= total for index in indices):
        raise ValueError("IO Slice & Dice: selection exceeds the original image count. Connect the full source images, before selection.")
    if len(contexts) == 1:
        return [dict(contexts[0]) for _ in indices]

    if total and len(image_counts) == len(contexts) and all(image_counts):
        # Original image-list batches can have different lengths.
        counts = image_counts
    else:
        counts = []
        for context in contexts:
            media = context.get("images") if context else None
            if media is None and context:
                media = context.get("image")
            counts.append(len(flatten_images(media)))
        if not all(counts):
            if any(counts):
                raise ValueError("IO Slice & Dice: generation-data pipes contain incomplete batch information. Supply one pipe per original image-list batch.")
            if total and total % len(contexts):
                raise ValueError("IO Slice & Dice: cannot match generation-data pipes to the original images. Supply one pipe per image or per original batch.")
            # Metadata-only records use the same equal expansion as prompt
            # lists. Without images, indices address the PIPE list directly.
            counts = [total // len(contexts) if total else 1] * len(contexts)
    boundaries = list(accumulate(counts))
    if total and boundaries[-1] != total:
        raise ValueError("IO Slice & Dice: generation-data pipes describe a different image count. Connect the original images and their matching pipes.")
    if any(index >= boundaries[-1] for index in indices):
        raise ValueError("IO Slice & Dice: selection exceeds the generation-data pipe range.")
    selected = [contexts[bisect_right(boundaries, index)] for index in indices]
    return [dict(context) if context is not None else None for context in selected]
