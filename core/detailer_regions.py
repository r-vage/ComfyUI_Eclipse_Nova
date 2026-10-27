# Batch-aware region preparation. Detection/matting finish before sampling starts.
import math

import cv2
import numpy as np
import torch

from ..extern.impact.core import SEG
from ..extern.impact.utils import make_crop_region
from .detailer_conditioning import label_groups
from .detailer_configuration import parse_indices
from .detailer_execution import fixed_segs_scale_match
from .detailer_matting import refine_masks
from .detailer_models import sam2_masks, yolo_regions
from .detailer_pipe import none_detection
from .seg_masks import MetadataWrapper, custom_mask_to_segs


def _is_box(value):
    return isinstance(value, (list, tuple)) and len(value) == 4 and all(type(v) in (int, float) and math.isfinite(v) for v in value)


def detection_source(*, bboxes=None, segs=None):
    if not none_detection(segs):
        return 'SEGS'
    return 'BBOXES' if not none_detection(bboxes) else 'YOLO'


def _frame_boxes(value):
    # Detection to Bboxes wraps each image's boxes in one additional list.
    while isinstance(value, (list, tuple)) and len(value) == 1 and not _is_box(value[0]):
        value = value[0]
    if _is_box(value):
        return [value]
    if isinstance(value, (list, tuple)) and all(_is_box(box) for box in value):
        return value
    raise ValueError('BBOXES must contain [x1, y1, x2, y2] boxes per image. Connect Detection to Bboxes from SmartLLM Nova.')


def boxes_for_images(value, images, parameters):
    if value is None:
        raise ValueError('BBOXES input is None.')
    # A connection-only IO node can carry the complete per-image collection as
    # one opaque BBOXES value. Unwrap its execution envelope, not individual boxes.
    if len(images) > 1 and isinstance(value, (list, tuple)) and len(value) == 1:
        nested = value[0]
        if isinstance(nested, (list, tuple)) and len(nested) == len(images) and not _is_box(nested):
            value = nested
    if len(images) == 1:
        groups = [_frame_boxes(value)]
    elif isinstance(value, (list, tuple)) and len(value) == len(images):
        groups = [_frame_boxes(group) for group in value]
    else:
        raise ValueError('BBOXES image count must match the input image count; boxes are never broadcast to unrelated images.')
    result = []
    for frame, boxes in zip(images, groups, strict=True):
        selection = parameters['box_selection']
        if selection == 'First':
            boxes = boxes[:1]
        elif selection == 'Indices':
            indices = parse_indices(parameters['box_indices'])
            boxes = [boxes[i] for i in indices if i < len(boxes)]
        h, w = frame.shape[1:3]
        clipped = []
        for x1, y1, x2, y2 in boxes:
            x1, x2 = max(0, min(w, x1)), max(0, min(w, x2))
            y1, y2 = max(0, min(h, y1)), max(0, min(h, y2))
            if x2 > x1 and y2 > y1:
                clipped.append([x1, y1, x2, y2])
        result.append(clipped)
    return result


def select_regions(segments, parameters):
    if parameters['selection'] == 'All':
        return list(segments)
    target = parameters['sort_by']

    def score(seg):
        x1, y1, x2, y2 = seg.crop_region
        return {'confidence': seg.confidence, 'area': (x2 - x1) * (y2 - y1),
                'width': x2 - x1, 'height': y2 - y1, 'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2}[target]

    ordered = list(segments) if target == 'none' else sorted(segments, key=score, reverse=parameters['descending'])
    start = parameters['take_start']
    return ordered[start:start + parameters['take_count']]


def _detection_segs(frame, detections, parameters, *, external=False):
    h, w = frame.shape[1:3]
    labels = {part.strip().casefold() for part in parameters['detection'].split(',') if part.strip()}
    regions = []
    for detection in detections:
        if not external and labels and 'all' not in labels and detection['label'].casefold() not in labels:
            continue
        x1, y1, x2, y2 = detection['bbox']
        box = (max(0, int(x1)), max(0, int(y1)), min(w, math.ceil(x2)), min(h, math.ceil(y2)))
        x1, y1, x2, y2 = box
        if x2 - x1 <= parameters['drop_size'] or y2 - y1 <= parameters['drop_size']:
            continue
        mask = detection.get('mask')
        if mask is None:
            mask = np.zeros((h, w), dtype=np.float32)
            mask[y1:y2, x1:x2] = 1
        dilation = parameters['bbox_dilation']
        if dilation:
            mask = cv2.dilate(mask, np.ones((dilation, dilation), np.uint8))
        crop = make_crop_region(w, h, box, parameters['crop_factor'])
        cx1, cy1, cx2, cy2 = crop
        regions.append(SEG(None, mask[cy1:cy2, cx1:cx2].copy(), detection['confidence'], crop, box,
                           detection['label'], MetadataWrapper(None, 0)))
    return (h, w), select_regions(regions, parameters)


def _is_segs(value):
    return (isinstance(value, (list, tuple)) and len(value) == 2
            and isinstance(value[0], (tuple, list)) and len(value[0]) == 2
            and all(type(n) is int for n in value[0]) and isinstance(value[1], (list, tuple)))


def external_regions(value, images, parameters):
    if value is None:
        raise ValueError('SEGS input is None.')
    groups = [value] if _is_segs(value) else value
    if isinstance(groups, (list, tuple)) and not groups:
        return [(tuple(frame.shape[1:3]), []) for frame in images]
    if not isinstance(groups, (list, tuple)) or not groups or not all(_is_segs(group) for group in groups):
        raise ValueError('Invalid SEGS input.')
    aggregate = len(groups) == 1
    if not aggregate and len(groups) != len(images):
        raise ValueError('SEGS must contain one shared batch result or one result per input image.')
    prepared = []
    for index, frame in enumerate(images):
        scaled = fixed_segs_scale_match(groups[0 if aggregate else index], frame.shape)
        owned = []
        for seg in scaled[1]:
            owner = getattr(seg.control_net_wrapper, 'batch_index', 0)
            if aggregate and owner != index:
                continue
            # Each frame will be sampled separately. Retain actual ControlNet
            # hooks, but make the per-call ownership start at zero again.
            wrapper = seg.control_net_wrapper
            if isinstance(wrapper, MetadataWrapper):
                wrapper = wrapper.original_wrapper
            owned.append(seg._replace(control_net_wrapper=MetadataWrapper(wrapper, 0)))
        prepared.append((scaled[0], select_regions(owned, parameters)))
    return prepared


def detect_regions(images, parameters, *, bboxes=None, segs=None):
    source = detection_source(bboxes=bboxes, segs=segs)
    if source == 'SEGS':
        prepared = external_regions(segs, images, parameters)
    elif source == 'BBOXES':
        boxes = boxes_for_images(bboxes, images, parameters)
        prepared = [_detection_segs(frame, [{'bbox': box, 'confidence': 1., 'label': 'A'} for box in found],
                                     parameters, external=True) for frame, found in zip(images, boxes, strict=True)]
    else:
        detections = yolo_regions(images, parameters)
        prepared = [_detection_segs(frame, found, parameters) for frame, found in zip(images, detections, strict=True)]
    return prepared


def refine_regions(images, prepared, parameters, *, group_by_label=False):
    modify = any(parameters[key] for key in ('sam2_enabled', 'refine_edges', 'mask_grow', 'mask_blur',
                                            'invert_mask', 'combined', 'bbox_fill', 'contour_fill'))
    if not modify or not any(regions[1] for regions in prepared):
        return prepared
    if parameters['sam2_enabled']:
        masks = sam2_masks(images, [[seg.bbox for seg in regions[1]] for regions in prepared], parameters, combine=False)
    else:
        masks = [[combined_mask((regions[0], [seg]))[0].numpy() for seg in regions[1]] for regions in prepared]
    # One model load for the whole matting pass, retaining instance provenance.
    work_images, work_masks, owners = [], [], []
    for index, (frame, regions, frame_masks) in enumerate(zip(images, prepared, masks, strict=True)):
        segments = regions[1]
        if not segments:
            continue
        if parameters['combined'] or parameters['invert_mask']:
            grouped = label_groups(segments).values() if group_by_label else [segments]
            masks_by_segment = {id(seg): mask for seg, mask in zip(segments, frame_masks, strict=True)}
            merged_segments, merged_masks = [], []
            for group in grouped:
                hooks = [getattr(seg.control_net_wrapper, 'original_wrapper', seg.control_net_wrapper) for seg in group]
                if any(hook is not None for hook in hooks) and len(group) > 1:
                    raise ValueError('Combining/inverting multiple SEGS with ControlNet hooks is unsupported. Keep their masks separate.')
                merged_masks.append(np.maximum.reduce([masks_by_segment[id(seg)] for seg in group]))
                merged_segments.append(group[0]._replace(confidence=max(seg.confidence for seg in group)))
            segments, frame_masks = merged_segments, merged_masks
        for seg, mask in zip(segments, frame_masks, strict=True):
            if np.any(mask):
                owners.append((index, seg))
                work_images.append(frame)
                work_masks.append(mask)
    refined = refine_masks(work_images, work_masks, parameters) if work_masks else []
    result = [(regions[0], []) for regions in prepared]
    for (index, original), mask in zip(owners, refined, strict=True):
        segments = custom_mask_to_segs(mask, parameters['combined'], parameters['crop_factor'],
            parameters['bbox_fill'], parameters['drop_size'], is_contour=parameters['contour_fill'])
        for seg in segments:
            if min(seg.bbox[2] - seg.bbox[0], seg.bbox[3] - seg.bbox[1]) > parameters['drop_size']:
                result[index][1].append(seg._replace(confidence=original.confidence, label=original.label,
                                                    control_net_wrapper=original.control_net_wrapper))
    return result


def prepare_regions(images, parameters, *, bboxes=None, segs=None):
    return refine_regions(images, detect_regions(images, parameters, bboxes=bboxes, segs=segs), parameters)


def combined_mask(segs):
    mask = np.zeros(segs[0], dtype=np.float32)
    for seg in segs[1]:
        x1, y1, x2, y2 = seg.crop_region
        cropped = seg.cropped_mask
        if isinstance(cropped, torch.Tensor):
            cropped = cropped.detach().cpu().numpy()
        mask[y1:y2, x1:x2] = np.maximum(mask[y1:y2, x1:x2], np.asarray(cropped).reshape(y2 - y1, x2 - x1))
    return torch.from_numpy(mask).unsqueeze(0).clamp(0, 1)
