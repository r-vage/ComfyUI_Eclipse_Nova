# Lossless batch/list conversion for semantic conditioning objects and latents.
# Execution lists and conditioning entries are different levels of structure.
from typing import Any

import comfy.utils
import torch

from .image_helpers import is_conditioning

# These ComfyUI metadata tensors use their first dimension for samples.
# Attention masks retain their token/head dimensions when split or combined.
_CONDITIONING_BATCH_FIELDS = ("pooled_output", "mask", "attention_mask")


def metadata_equal(left: Any, right: Any) -> bool:
    if isinstance(left, torch.Tensor) or isinstance(right, torch.Tensor):
        return (isinstance(left, torch.Tensor) and isinstance(right, torch.Tensor)
                and left.shape == right.shape and left.dtype == right.dtype
                and left.device == right.device and torch.equal(left, right))
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(metadata_equal(left[k], right[k]) for k in left)
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(metadata_equal(a, b) for a, b in zip(left, right))
    if left is right:
        return True
    return type(left) is type(right) and isinstance(left, (str, int, float, bool, type(None))) and left == right


def _cat(tensors: list[torch.Tensor], label: str) -> torch.Tensor:
    first = tensors[0]
    if any(t.shape[1:] != first.shape[1:] or t.dtype != first.dtype or t.device != first.device for t in tensors):
        raise ValueError(f"{label}: matching dimensions, dtype and device are required.")
    return torch.cat(tensors, dim=0)


def _broadcast(tensor: torch.Tensor, batch: int, label: str) -> torch.Tensor:
    if tensor.ndim == 0 or tensor.shape[0] not in (1, batch):
        raise ValueError(f"{label}: expected a singleton or {batch} samples.")
    return tensor.expand((batch,) + tensor.shape[1:])


def _has_tensor(value: Any) -> bool:
    if isinstance(value, torch.Tensor):
        return value.ndim > 0
    if isinstance(value, dict):
        return any(_has_tensor(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_has_tensor(v) for v in value)
    return False


def split_conditioning(conditioning: Any) -> list[list]:
    # Each result contains ALL entries that apply to one sample, in original order.
    if not is_conditioning(conditioning):
        raise ValueError("Conditioning must contain tensor/metadata pairs.")
    if any(t.ndim < 3 or t.shape[0] == 0 for t, _ in conditioning):
        raise ValueError("Conditioning embeddings must have a nonempty batch axis.")
    counts = [t.shape[0] for t, _ in conditioning]
    for _, metadata in conditioning:
        for key in _CONDITIONING_BATCH_FIELDS:
            value = metadata.get(key)
            if isinstance(value, torch.Tensor) and value.ndim >= (3 if key == 'mask' else 2):
                counts.append(value.shape[0])
    batch = max(counts)
    results = [[] for _ in range(batch)]
    for tensor, metadata in conditioning:
        tensor = _broadcast(tensor, batch, "Conditioning embeddings")
        per_sample = {}
        for key, value in metadata.items():
            # Optional encoder outputs can be absent without removing their keys.
            if key in ("pooled_output", "attention_mask") and value is None:
                continue
            if key in _CONDITIONING_BATCH_FIELDS:
                if not isinstance(value, torch.Tensor):
                    expected = "a tensor" if key == "mask" else "a tensor or None"
                    raise ValueError(f"Conditioning {key} must be {expected}.")
                if key == "mask" and value.ndim == 2:
                    value = value.unsqueeze(0)
                if value.ndim < 2:
                    raise ValueError(f"Conditioning {key} has no supported batch dimension.")
                per_sample[key] = _broadcast(value, batch, f"Conditioning {key}")
            elif _has_tensor(value):
                raise ValueError(f"Conditioning field '{key}' has unsupported per-sample tensors; keep these prompts as a list.")
        for index, result in enumerate(results):
            extra = dict(metadata)
            extra.update({key: value[index:index + 1] for key, value in per_sample.items()})
            result.append([tensor[index:index + 1], extra])
    return results


def conditioning_samples(value: Any) -> list[list]:
    if is_conditioning(value):
        return split_conditioning(value)
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [sample for item in value for sample in conditioning_samples(item)]
    raise ValueError('Conditioning inputs must contain complete tensor/metadata pairs; incompatible value found.')


def batch_conditionings(conditionings: Any) -> list:
    samples = conditioning_samples(conditionings)
    if not samples:
        raise ValueError("Conditioning batch contains no samples.")
    if any(len(sample) != len(samples[0]) for sample in samples):
        raise ValueError("Conditioning entry structure differs; keep separate prompts as a list.")
    result = []
    for index in range(len(samples[0])):
        entries = [sample[index] for sample in samples]
        reference = entries[0][1]
        if any(extra.keys() != reference.keys() for _, extra in entries):
            raise ValueError("Conditioning metadata fields differ; keep separate prompts as a list.")
        extra = dict(reference)
        for key in reference:
            values = [entry[1][key] for entry in entries]
            if key in _CONDITIONING_BATCH_FIELDS and all(isinstance(value, torch.Tensor) for value in values):
                extra[key] = _cat(values, f"Conditioning {key}")
            elif not all(metadata_equal(values[0], value) for value in values[1:]):
                raise ValueError(f"Conditioning metadata '{key}' conflicts; keep separate prompts as a list.")
        result.append([_cat([entry[0] for entry in entries], "Conditioning embeddings (token/embedding lengths)"), extra])
    return result


def _latent_samples(latent: dict) -> torch.Tensor:
    samples = latent.get("samples")
    if not isinstance(samples, torch.Tensor) or samples.ndim not in (4, 5) or samples.shape[0] == 0:
        raise ValueError("Latent samples must be a nonempty image [B,C,H,W] or video [B,C,T,H,W] tensor.")
    return samples


def _latent_mask(mask: torch.Tensor, samples: torch.Tensor) -> torch.Tensor:
    if not isinstance(mask, torch.Tensor) or mask.ndim < 2:
        raise ValueError("Latent noise_mask must be a spatial mask tensor.")
    if samples.ndim == 5:
        # ComfyUI interprets a mask without explicit B,C axes as one temporal mask.
        if mask.ndim < 5:
            mask = mask.reshape(1, 1, -1, *mask.shape[-2:])
        if mask.ndim != 5 or mask.shape[1] != 1:
            raise ValueError("Video latent noise_mask must have [B,1,T,H,W] shape.")
    elif mask.ndim == 2:
        mask = mask.unsqueeze(0)
    elif mask.ndim not in (3, 4) or (mask.ndim == 4 and mask.shape[1] != 1):
        raise ValueError("Image latent noise_mask must have [B,H,W] or [B,1,H,W] shape.")
    if mask.shape[0] == 0:
        raise ValueError("Latent noise_mask has no samples.")
    return comfy.utils.repeat_to_batch_size(mask, samples.shape[0])


def _latent_indices(latent: dict, batch: int) -> list:
    indices = latent.get("batch_index", list(range(batch)))
    if not isinstance(indices, (list, tuple)) or not indices:
        raise ValueError("Latent batch_index must be a nonempty list of sample indices.")
    return [indices[i % len(indices)] for i in range(batch)]


def split_latent(latent: dict) -> list[dict]:
    samples = _latent_samples(latent)
    mask = _latent_mask(latent["noise_mask"], samples) if "noise_mask" in latent else None
    indices = _latent_indices(latent, samples.shape[0]) if "batch_index" in latent else None
    result = []
    for index in range(samples.shape[0]):
        item = dict(latent)
        item["samples"] = samples[index:index + 1]
        if mask is not None:
            item["noise_mask"] = mask[index:index + 1]
        if indices is not None:
            item["batch_index"] = indices[index:index + 1]
        result.append(item)
    return result


def batch_latents(latents: list[dict]) -> dict:
    samples = [_latent_samples(latent) for latent in latents]
    reference = samples[0]
    shared = [{key: value for key, value in latent.items()
               if key not in ("samples", "noise_mask", "batch_index")} for latent in latents]
    if any(not metadata_equal(shared[0], value) for value in shared[1:]):
        raise ValueError("Latent shared metadata conflicts; cannot combine these samples.")
    prepared = []
    for sample in samples:
        if sample.ndim != reference.ndim or sample.shape[1] != reference.shape[1]:
            raise ValueError("Latent channel counts and ranks must match.")
        if sample.shape[2:] != reference.shape[2:]:
            if reference.ndim == 5:
                raise ValueError("Video latent temporal and spatial dimensions must match.")
            sample = comfy.utils.common_upscale(sample, reference.shape[-1], reference.shape[-2], "lanczos", "center")
        prepared.append(sample)
    result = {**shared[0], "samples": _cat(prepared, "Latent samples")}
    if any("batch_index" in latent for latent in latents):
        result["batch_index"] = [index for latent, sample in zip(latents, samples)
                                 for index in _latent_indices(latent, sample.shape[0])]
    if any("noise_mask" in latent for latent in latents):
        masks = [_latent_mask(latent["noise_mask"], sample) if "noise_mask" in latent else None
                 for latent, sample in zip(latents, samples)]
        first_mask = next(mask for mask in masks if mask is not None)
        mask_shape = first_mask.shape[1:]
        prepared_masks = []
        for mask, sample in zip(masks, samples):
            if mask is None:
                mask = first_mask.new_ones((sample.shape[0],) + mask_shape)
            if reference.ndim == 4:
                mask = mask.reshape(-1, 1, *mask.shape[-2:])
                if mask.shape[-2:] != first_mask.shape[-2:]:
                    mask = comfy.utils.common_upscale(mask, first_mask.shape[-1], first_mask.shape[-2], "bilinear", "center")
                if first_mask.ndim == 3:
                    mask = mask[:, 0]
            elif mask.shape[2:] != first_mask.shape[2:]:
                mask = torch.nn.functional.interpolate(mask, size=first_mask.shape[2:], mode="trilinear")
            prepared_masks.append(mask)
        result["noise_mask"] = _cat(prepared_masks, "Latent noise_mask")
    return result
