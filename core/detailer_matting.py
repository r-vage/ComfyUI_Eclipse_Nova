# Mask refinement between SAM2 segmentation and SEGS conversion.
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image

from .detailer_models import _missing_dependency, local_model
from .image_helpers import expand_mask


def make_trimap(mask, erode, dilate):
    binary = (mask > 0.5).astype(np.uint8)
    foreground = cv2.erode(binary, np.ones((erode, erode), np.uint8), iterations=5) if erode else binary
    envelope = cv2.dilate(binary, np.ones((dilate, dilate), np.uint8), iterations=5) if dilate else binary
    trimap = np.full(mask.shape, 128, dtype=np.uint8)
    trimap[envelope == 0] = 0
    trimap[foreground > 0] = 255
    return trimap


def _vitmatte_path():
    import folder_paths

    for name in ('vitmatte', 'vitmatte-base-composition-1k'):
        path = Path(folder_paths.models_dir) / name / 'model.safetensors'
        if path.is_file():
            return path
    raise FileNotFoundError('ViTMatte needs local model.safetensors, config.json and preprocessor_config.json in models/vitmatte (or models/vitmatte-base-composition-1k).')


def _load_vitmatte(path):
    try:
        from transformers import VitMatteForImageMatting
    except ImportError as error:
        _missing_dependency('Transformers with ViTMatte', error)
    return VitMatteForImageMatting.from_pretrained(str(path.parent), local_files_only=True, use_safetensors=True).eval()


def _working_size(width, height, megapixels):
    scale = min(1.0, (megapixels * 1024**2 / (width * height)) ** 0.5)
    return max(1, round(width * scale)), max(1, round(height * scale))


def vitmatte_masks(images, masks, parameters):
    path = _vitmatte_path()
    try:
        from transformers import VitMatteImageProcessor
    except ImportError as error:
        _missing_dependency('Transformers with ViTMatte', error)
    processor = VitMatteImageProcessor.from_pretrained(str(path.parent), local_files_only=True)
    refined = []
    with local_model(path, _load_vitmatte, device=parameters['detection_device'], precision=parameters['precision']) as (model, device):
        for frame, mask in zip(images, masks, strict=True):
            import comfy.model_management as mm
            mm.throw_exception_if_processing_interrupted()
            if not np.any(mask):
                refined.append(mask)
                continue
            height, width = mask.shape
            size = _working_size(width, height, parameters['max_megapixels'])
            pixels = (frame[0, ..., :3].detach().cpu().clamp(0, 1).numpy() * 255).astype(np.uint8)
            image = Image.fromarray(pixels).resize(size, Image.Resampling.BILINEAR)
            trimap = Image.fromarray(make_trimap(mask, parameters['detail_erode'], parameters['detail_dilate'])).resize(size, Image.Resampling.NEAREST)
            inputs = processor(images=image, trimaps=trimap, return_tensors='pt')
            inputs = {key: value.to(device) for key, value in inputs.items()}
            alpha = model(**inputs).alphas[0, 0, :size[1], :size[0]].float().cpu().numpy()
            refined.append(cv2.resize(alpha, (width, height), interpolation=cv2.INTER_LINEAR))
    return refined


def _guided_mask(frame, mask, radius):
    image = frame[0, ..., :3].detach().cpu().float().numpy()
    guide = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    size = (radius * 2 + 1,) * 2
    def mean(value):
        return cv2.boxFilter(value, -1, size)
    mean_i, mean_p = mean(guide), mean(mask)
    covariance = mean(guide * mask) - mean_i * mean_p
    variance = mean(guide * guide) - mean_i * mean_i
    a = covariance / (variance + 0.01)
    return mean(a) * guide + mean(mean_p - a * mean_i)


def _pymatting_mask(frame, mask, parameters):
    try:
        from pymatting import estimate_alpha_cf
    except ImportError as error:
        _missing_dependency('PyMatting', error)
    h, w = mask.shape
    size = _working_size(w, h, parameters['max_megapixels'])
    image = cv2.resize(frame[0, ..., :3].detach().cpu().numpy(), size).astype(np.float64)
    trimap = cv2.resize(make_trimap(mask, parameters['detail_erode'], parameters['detail_dilate']), size,
                        interpolation=cv2.INTER_NEAREST).astype(np.float64) / 255
    # Closed-form matting needs both known foreground and background.
    if not np.any(trimap == 1) or not np.any(trimap == 0):
        return mask
    alpha = estimate_alpha_cf(image, trimap)
    return cv2.resize(alpha.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)


def refine_masks(images, masks, parameters):
    method = parameters['detail_method'] if parameters['refine_edges'] else 'None'
    if method == 'ViTMatte' and any(np.any(mask) for mask in masks):
        masks = vitmatte_masks(images, masks, parameters)
    result = []
    for frame, mask in zip(images, masks, strict=True):
        if np.any(mask):
            if method == 'Guided filter':
                radius = (parameters['detail_erode'] + parameters['detail_dilate']) // 6 + 1
                mask = _guided_mask(frame, mask, radius)
            elif method == 'PyMatting':
                mask = _pymatting_mask(frame, mask, parameters)
            if method != 'None':
                mask = np.clip((mask - parameters['black_point']) / (parameters['white_point'] - parameters['black_point']), 0, 1)
        mask = torch.from_numpy(np.asarray(mask, dtype=np.float32).copy()).unsqueeze(0).clamp(0, 1)
        if parameters['invert_mask']:
            mask = 1 - mask
        result.append(expand_mask(mask, parameters['mask_grow'], parameters['mask_blur'])[0].numpy())
    return result
