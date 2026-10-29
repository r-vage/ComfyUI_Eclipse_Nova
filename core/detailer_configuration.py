# Additional controls for the integrated detailer. No model imports at startup.
from .detailer_models import model_files, yolo_files
from .image_color_match import COLOR_MATCH_METHODS

PROFILE = 'detailer_auto'
NODE_ID = 'Detailer (Advanced) [Eclipse Nova]'


def integrated_spec(base):
    fields = base['fields']
    fields.pop('live_preview', None)

    def number(key, label, default, low, high, step=1, integer=True, tooltip=''):
        fields[key] = {'label': label, 'default': default, 'min': low, 'max': high, 'step': step, 'integer': integer, 'tooltip': tooltip}

    def choice(key, label, default, options, tooltip=''):
        fields[key] = {'label': label, 'default': default, 'options': options, 'tooltip': tooltip}

    choice('yolo_model', 'YOLO model', 'bbox/face_yolov8m.pt', yolo_files(),
        'Scans models/ultralytics/bbox and models/ultralytics/segm. Detects boxes or segmentation from the loaded checkpoint, regardless of its folder or filename. Non-None pipe detections bypass YOLO.')
    choice('sam2_model', 'SAM2 model', 'sam2.1_hiera_base_plus.safetensors', model_files('sam2'),
        'Local SAM2 model file. Only loads when SAM2 is enabled; missing files report an error when run.')
    for key in ('yolo_model', 'sam2_model'):
        fields[key]['model_file'] = True
    choice('detection_device', 'Detection device', 'default', ['default', 'cpu'],
        'Default uses ComfyUI’s configured device, including its selected GPU and accelerator backend. CPU forces CPU inference. Older Auto/CUDA selections use Default.')
    choice('precision', 'SAM2 / matting precision', 'fp16', ['fp32', 'fp16', 'bf16'], 'CPU always uses FP32. YOLO uses FP32 on every device.')
    fields['sam2_enabled'] = {'label': 'SAM2', 'default': False, 'tooltip': 'Segment the original image using the selected region boxes. For SEGS, uses each segment’s bounding box; replaces its mask. SAM2 does not read detection text.'}
    fields['refine_edges'] = {'label': 'Edges', 'default': False, 'tooltip': 'Refine mask edges with ViTMatte, Guided filter or PyMatting after detection and optional SAM2.'}
    for stage in ('detection', 'segmentation'):
        fields['stop_' + stage] = {'label': 'Stop', 'default': False, 'optional': True,
            'tooltip': f'Stop after the {stage} preview, before the next stage. Queue again with unchanged images and region settings to continue. Sampling seeds advance only when sampling finishes.'}
    number('threshold', 'Confidence threshold', .5, .01, 1, .01, False)
    number('nms_iou', 'NMS overlap', .7, .01, 1, .01, False, 'Suppress overlapping YOLO detections above this intersection-over-union ratio.')
    number('bbox_dilation', 'Detection mask dilation', 10, 0, 128, tooltip='Square dilation kernel size for internal detections and external boxes, matching Bbox Detector SEGS. 0 disables dilation. SAM2 replaces this mask when enabled; supplied SEGS masks are unchanged.')
    number('crop_factor', 'Crop factor', 2.2, 1, 10, .1, False, 'Context around detected or refined regions for diffusion detailing.')
    number('drop_size', 'Drop small regions', 1, 1, 8192)
    fields['detection'] = {'label': 'Detection', 'default': 'all', 'free_text': True, 'tooltip': 'YOLO class labels, comma-separated, or all. Limited to labels learned by the chosen model. Not a text prompt for SAM2. A pipe detection string takes priority; external boxes/SEGS are already selected upstream.'}
    choice('selection', 'Region selection', 'Ordered', ['All', 'Ordered'], 'Ordered sorts regions and selects the requested range separately for every image.')
    choice('sort_by', 'Sort by', 'confidence', ['confidence', 'area', 'width', 'height', 'x1', 'y1', 'x2', 'y2', 'none'], 'Size and position use the crop region, matching SEGS Ordered Filter.')
    fields['descending'] = {'label': 'Descending', 'default': True, 'tooltip': 'Highest confidence/largest region first; disable for ascending order.'}
    number('take_start', 'First region', 0, 0, 10000, tooltip='Zero-based position after sorting.')
    number('take_count', 'Region count', 1, 0, 10000, tooltip='Number of regions to detail. 0 selects none. Use All to keep every region.')
    choice('box_selection', 'External boxes', 'All', ['All', 'First', 'Indices'], 'Optional preselection of BBOXES from the pipe. Ignored for internal YOLO and external SEGS.')
    fields['box_indices'] = {'label': 'Box indices', 'default': '0,', 'free_text': True, 'tooltip': 'Zero-based, comma-separated box indices, applied to each input image.'}
    choice('detail_method', 'Edge refinement', 'ViTMatte', ['Guided filter', 'PyMatting', 'ViTMatte'], 'Refine the current mask before grow/blur. ViTMatte receives the original image and a trimap made from this mask, not a detection prompt.')
    number('detail_erode', 'Detail erode', 3, 0, 64, tooltip='Trimap foreground erosion kernel; five iterations. Used by matting methods.')
    number('detail_dilate', 'Detail dilate', 4, 0, 64, tooltip='Trimap unknown-region dilation kernel; five iterations.')
    number('black_point', 'Black point', .15, 0, .99, .01, False)
    number('white_point', 'White point', .99, .01, 1, .01, False)
    number('max_megapixels', 'Matting megapixels', 2., .1, 16, .1, False, 'Limit matting resolution; masks are restored to the original image size afterward.')
    fields['invert_mask'] = {'label': 'Invert mask', 'default': False, 'tooltip': 'Invert the refined mask before growing/blurring.'}
    number('mask_grow', 'Grow / shrink', 0, -128, 128, tooltip='Pixels to grow the mask. Negative values shrink it.')
    number('mask_blur', 'Mask blur', 0, 0, 128, tooltip='Gaussian blur radius after grow/shrink.')
    fields['combined'] = {'label': 'Combined region', 'default': False, 'tooltip': 'With external SEGS and conditioning lists or active denoise lists, combine masks within each label so both eyes share a sampling pass. Otherwise combine all selected masks. Disabled keeps individual regions. YOLO uses the first supplied conditioning and denoise.'}
    fields['bbox_fill'] = {'label': 'Fill bounding box', 'default': False, 'tooltip': 'Fill the complete bounding box instead of retaining the segmentation shape.'}
    fields['contour_fill'] = {'label': 'Fill contours', 'default': False, 'tooltip': 'Fill holes inside disconnected contours when Combined region is disabled.'}
    fields['color_match_enabled'] = {'label': 'Color match', 'default': False, 'optional': True,
        'tooltip': 'Match each detailed region to its original colors and tones after sampling, before blending it back. Uses the region mask, independently of Noise mask and Use pipe settings.'}
    choice('color_match_method', 'Method', 'mkl', list(COLOR_MATCH_METHODS),
        'Same methods as Image Filter Adjustments. MKL matches color statistics; HM and ScatterSort match histograms. Wavelet matches low-frequency LAB tones while preserving fine detail; Reinhard LAB matches LAB color statistics. Each method uses the original masked region as reference. Wavelet, ScatterSort and Reinhard LAB use ComfyUI’s configured device.')
    number('color_match_strength', 'Strength', 1., 0, 1, .1, False,
        '0 keeps the sampled colors; 1 fully matches the original region. Intermediate values blend the correction without blending away sampled detail.')
    for key in ('color_match_method', 'color_match_strength'):
        fields[key]['optional'] = True
    return {**base, 'profile': PROFILE, 'fields': fields}


def upgrade_parameters(parameters, fields):
    # Retired sampling preview; detection/segmentation reviews remain available.
    parameters.pop('live_preview', None)
    if parameters.get('detection_device') in ('auto', 'cuda'):
        parameters['detection_device'] = 'default'
    for key, field in fields.items():
        if field.get('optional'):
            parameters.setdefault(key, field['default'])
    # Accept configurations saved during the unpublished three-mode design.
    mode = parameters.get('detection_mode')
    if mode in ('BBox', 'Segm'):
        field, folder, default = ('yolo_segm_model', 'segm', 'person_yolov8m-seg.pt') if mode == 'Segm' else ('yolo_model', 'bbox', 'face_yolov8m.pt')
        parameters['yolo_model'] = f'{folder}/{parameters.get(field, default)}'
        parameters.pop('yolo_segm_model', None)
        parameters.pop('detection_mode')
        return
    if mode not in ('YOLO', 'SAM2', 'SEGS'):
        return
    parameters.pop('cache_model', None)
    parameters.pop('detection_mode')
    parameters['yolo_model'] = 'bbox/' + parameters.get('yolo_model', 'face_yolov8m.pt')
    parameters.pop('yolo_segm_model', None)
    parameters['sam2_enabled'] = mode == 'SAM2'
    parameters['refine_edges'] = mode == 'SAM2' and parameters.get('detail_method') != 'None'
    parameters['detection'] = parameters.pop('labels', 'all')
    parameters['crop_factor'] = parameters.get('sam_crop_factor' if mode == 'SAM2' else 'yolo_crop_factor', 2.2)
    parameters['drop_size'] = parameters.get('sam_drop_size' if mode == 'SAM2' else 'yolo_drop_size', 1)
    for key in ('sam_crop_factor', 'yolo_crop_factor', 'sam_drop_size', 'yolo_drop_size'):
        parameters.pop(key, None)
    if parameters.get('detail_method') == 'None':
        parameters['detail_method'] = 'ViTMatte'
    if mode != 'SAM2':
        parameters.update(mask_grow=0, mask_blur=0, invert_mask=False, combined=False, bbox_fill=False, contour_fill=False)
    else:
        parameters['selection'] = 'All'
    for key, field in fields.items():
        parameters.setdefault(key, field['default'])


def validate_integrated(parameters):
    if parameters['black_point'] >= parameters['white_point']:
        raise ValueError('Black point must be below White point.')
    if parameters['box_selection'] == 'Indices':
        parse_indices(parameters['box_indices'])


def parse_indices(text):
    parts = [part.strip() for part in text.split(',') if part.strip()]
    if not parts or any(not value.isascii() or not value.isdecimal() or len(value) > 5 for value in parts):
        raise ValueError('Box indices must be comma-separated nonnegative integers.')
    return list(dict.fromkeys(int(part) for part in parts))
