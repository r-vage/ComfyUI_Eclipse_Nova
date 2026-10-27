# Local model discovery and isolated inference for the integrated SEGS detailer.
import importlib
from contextlib import contextmanager, nullcontext
from pathlib import Path
from threading import RLock

import numpy as np
import torch

_LOCK = RLock()
_FOLDERS = {'yolo': ('ultralytics/bbox', {'.pt'}), 'yolo_segm': ('ultralytics/segm', {'.pt'}),
            'sam2': ('sam2', {'.pt', '.pth', '.safetensors'})}


def model_files(kind):
    import folder_paths

    directory, extensions = _FOLDERS[kind]
    key = 'eclipse_nova_detailer_' + kind
    if key not in folder_paths.folder_names_and_paths:
        roots = [str(Path(folder_paths.models_dir) / directory)]
        source = {'yolo': 'ultralytics_bbox', 'yolo_segm': 'ultralytics_segm', 'sam2': 'sam2'}[kind]
        for root in folder_paths.folder_names_and_paths.get(source, ([], set()))[0]:
            if root not in roots:
                roots.append(root)
        folder_paths.folder_names_and_paths[key] = (roots, extensions)
    return sorted(folder_paths.get_filename_list(key), key=str.casefold)


def model_path(kind, name):
    import folder_paths

    if not isinstance(name, str) or not name or '\x00' in name or '\\' in name:
        raise ValueError('Choose a local detailer model filename.')
    relative = Path(name)
    if relative.is_absolute() or '..' in relative.parts or relative.suffix.lower() not in _FOLDERS[kind][1]:
        raise ValueError('Detailer model must be a supported file inside its model folder.')
    model_files(kind)
    key = 'eclipse_nova_detailer_' + kind
    for directory in folder_paths.folder_names_and_paths[key][0]:
        root = Path(directory).resolve()
        candidate = (root / relative).resolve()
        if candidate.is_relative_to(root) and candidate.is_file():
            return candidate
    raise FileNotFoundError(f'Detailer {kind.upper()} model not found: {name}. Place it in models/{_FOLDERS[kind][0]}.')


def yolo_files():
    # Prefix the source folder so identically named files stay selectable.
    return sorted((f'{folder}/{name}' for folder, kind in (('bbox', 'yolo'), ('segm', 'yolo_segm'))
                   for name in model_files(kind)), key=str.casefold)


def yolo_path(name):
    if not isinstance(name, str):
        raise TypeError('Choose a YOLO model from bbox/ or segm/.')
    folder, separator, relative = name.partition('/')
    if not separator or folder not in ('bbox', 'segm'):
        raise ValueError('Choose a YOLO model from bbox/ or segm/.')
    return model_path('yolo' if folder == 'bbox' else 'yolo_segm', relative)


def model_fingerprint(parameters, *, detection=True, refinement=True):
    kinds = ['yolo'] if detection else []
    if refinement and parameters['sam2_enabled']:
        kinds.append('sam2')
    signature = []
    for kind in kinds:
        name = parameters[kind + '_model']
        try:
            path = yolo_path(name) if kind == 'yolo' else model_path(kind, name)
        except (ValueError, FileNotFoundError):
            signature.append((kind, name, 'unavailable'))
            continue
        stat = path.stat()
        signature.append((str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
    if refinement and parameters['refine_edges'] and parameters['detail_method'] == 'ViTMatte':
        import folder_paths
        for folder in ('vitmatte', 'vitmatte-base-composition-1k'):
            for filename in ('model.safetensors', 'config.json', 'preprocessor_config.json'):
                candidate = Path(folder_paths.models_dir) / folder / filename
                if candidate.is_file():
                    stat = candidate.stat()
                    signature.append((str(candidate), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
    return tuple(signature)


def device_and_dtype(device, precision):
    import comfy.model_management as mm

    # ComfyUI owns accelerator selection and its GPU index (including ROCm).
    # Accept earlier saved Auto/CUDA choices without assuming a CUDA backend.
    selected = mm.get_torch_device() if device in ('default', 'auto', 'cuda') else torch.device(device)
    if selected.type == 'cuda' and not torch.cuda.is_available():
        raise ValueError('ComfyUI’s selected GPU is unavailable. Select CPU for detailer detection.')
    dtype = {'fp32': torch.float32, 'fp16': torch.float16, 'bf16': torch.bfloat16}[precision]
    if selected.type == 'cpu':
        dtype = torch.float32
    if selected.type == 'cuda' and dtype == torch.bfloat16 and not torch.cuda.is_bf16_supported():
        raise ValueError('This GPU does not support BF16. Select FP16 or FP32.')
    return selected, dtype


def _missing_dependency(name, error):
    raise RuntimeError(f'{name} is required for this detailer mode. Install requirements-detailer.txt in the ComfyUI Python environment.') from error


@contextmanager
def local_model(path, loader, *, device, precision):
    # No model cache. Serialize inference and offload on success or interruption.
    selected, dtype = device_and_dtype(device, precision)
    with _LOCK:
        model = loader(path)
        try:
            if selected.type != 'cpu':
                import comfy.model_management as mm
                required = sum(p.numel() * p.element_size() for p in model.parameters())
                mm.free_memory(required + 512 * 1024**2, selected)
            # Autocast selects inference precision while weights remain FP32.
            model.to(device=selected, dtype=torch.float32).eval()
            with torch.inference_mode(), (torch.autocast(selected.type, dtype=dtype) if selected.type == 'cuda' and dtype != torch.float32 else nullcontext()):
                yield model, selected
        finally:
            model.to('cpu')


def _yolo_checkpoint_attribute(owner, name):
    # Early YOLOv8 Segment checkpoints stored Detect.forward via getattr. Do
    # not expose unrestricted attribute access to the weights-only unpickler.
    from ultralytics.nn.modules import Detect
    if owner is Detect and name == 'forward':
        return Detect.forward
    raise ValueError('Unsupported attribute reference in YOLO checkpoint.')


def _yolo_checkpoint_type(name):
    # Older Dill-saved checkpoints encode nn.Module's buffer sets this way.
    # Resolve only that builtin, without importing Dill or exposing its typemap.
    if name == 'set':
        return set
    raise ValueError('Unsupported type reference in YOLO checkpoint.')


def _load_yolo(path):
    try:
        tasks = importlib.import_module('ultralytics.nn.tasks')
        modules = importlib.import_module('ultralytics.nn.modules')
        architectures = [importlib.import_module(f'ultralytics.nn.modules.{name}')
                         for name in ('block', 'conv', 'head', 'transformer')]
        utilities = importlib.import_module('ultralytics.utils')
        losses = importlib.import_module('ultralytics.utils.loss')
        assigners = importlib.import_module('ultralytics.utils.tal')
    except ImportError as error:
        _missing_dependency('Ultralytics', error)
    # Restrict pickle globals to installed architecture classes. Never retry
    # weights_only=False, import checkpoint-named modules, or patch torch.load.
    allowed = {}
    # The package exports omit nested blocks such as YOLO11's C3k/PSABlock
    # and YOLO9's RepCSP. Inspect these fixed installed architecture modules too.
    for module in (torch.nn, modules, *architectures):
        for name, value in vars(module).items():
            if isinstance(value, type) and issubclass(value, torch.nn.Module):
                allowed[f'{value.__module__}.{value.__name__}'] = value
                allowed[f'{module.__name__}.{name}'] = value
    allowed['ultralytics.nn.tasks.DetectionModel'] = tasks.DetectionModel
    allowed['ultralytics.nn.tasks.SegmentationModel'] = tasks.SegmentationModel
    allowed['builtins.getattr'] = _yolo_checkpoint_attribute
    allowed['dill._dill._load_type'] = _yolo_checkpoint_type
    for name in ('ultralytics.yolo.utils.IterableSimpleNamespace', 'ultralytics.utils.IterableSimpleNamespace'):
        allowed[name] = utilities.IterableSimpleNamespace
    # Some fine-tuned inference checkpoints retain their training criterion.
    # These concrete installed classes restore plain object/nn.Module state;
    # never allow every loss class or import a checkpoint-provided module path.
    for module, names in ((losses, ('v8DetectionLoss', 'v8SegmentationLoss', 'BboxLoss')),
                          (assigners, ('TaskAlignedAssigner',))):
        for name in names:
            value = getattr(module, name)
            for prefix in ('ultralytics.utils', 'ultralytics.yolo.utils'):
                allowed[f'{prefix}.{module.__name__.rsplit(".", 1)[-1]}.{name}'] = value
    checkpoint_globals = set(torch.serialization.get_unsafe_globals_in_checkpoint(path))
    if 'ultralytics.nn.tasks.ClassificationModel' in checkpoint_globals:
        raise ValueError(f'YOLO checkpoint {path.name!r} is a classification model and does not produce boxes or masks. '
                         'Choose a detection or segmentation checkpoint for the detailer.')
    unknown = checkpoint_globals - allowed.keys()
    if unknown:
        names = ', '.join(repr(name[:160]) for name in sorted(unknown)[:6])
        raise ValueError(f'YOLO checkpoint {path.name!r} contains unsupported serialized objects: {names}. '
                         'Use a checkpoint saved with supported Ultralytics detection or segmentation classes.')
    with torch.serialization.safe_globals([(value, name) for name, value in allowed.items()]):
        checkpoint = torch.load(path, map_location='cpu', weights_only=True)
    model = checkpoint.get('ema') if isinstance(checkpoint, dict) else None
    if model is None and isinstance(checkpoint, dict):
        model = checkpoint.get('model')
    if type(model) not in (tasks.DetectionModel, tasks.SegmentationModel):
        raise ValueError('Select a standard YOLO detection or segmentation checkpoint, not a classification model.')
    return model.float().eval()


def yolo_regions(images, parameters):
    path = yolo_path(parameters['yolo_model'])
    try:
        from ultralytics.models.yolo.detect import DetectionPredictor
        from ultralytics.models.yolo.segment import SegmentationPredictor
        from ultralytics.nn.modules import Segment
        from ultralytics.nn.tasks import SegmentationModel
    except ImportError as error:
        _missing_dependency('Ultralytics', error)
    results = []
    with local_model(path, _load_yolo, device=parameters['detection_device'], precision='fp32') as (model, device):
        # Folder and filename are only locations. Some detection checkpoints
        # live under segm/; choose inference from the loaded architecture.
        segmentation = isinstance(model, SegmentationModel) or isinstance(model.model[-1], Segment)
        labels = {part.strip().casefold() for part in parameters['detection'].split(',') if part.strip()}
        names = model.names if isinstance(model.names, dict) else dict(enumerate(model.names))
        classes = None
        if labels and 'all' not in labels:
            known = {str(name).casefold() for name in names.values()}
            if labels - known:
                raise ValueError('YOLO cannot detect these labels: ' + ', '.join(sorted(labels - known))
                                 + '. This model knows: ' + ', '.join(map(str, names.values()))
                                 + '. For free-text detection, use SmartLLM and connect its boxes through IO Detailer.')
            classes = [index for index, name in names.items() if str(name).casefold() in labels]
        predictor = (SegmentationPredictor if segmentation else DetectionPredictor)(overrides={
            'conf': parameters['threshold'], 'iou': parameters['nms_iou'],
            'device': device, 'verbose': False, 'save': False, 'save_txt': False,
            'retina_masks': True, 'classes': classes, 'task': 'segment' if segmentation else 'detect',
        })
        try:
            predictor.setup_model(model=model, verbose=False)
            for frame in images:
                import comfy.model_management as mm
                mm.throw_exception_if_processing_interrupted()
                pixels = (frame[0, ..., :3].detach().cpu().clamp(0, 1).numpy() * 255).astype(np.uint8)
                prediction = predictor(source=np.ascontiguousarray(pixels[..., ::-1]), stream=False)[0]
                boxes = prediction.boxes
                regions = [{'bbox': box, 'confidence': float(score), 'label': str(prediction.names[int(label)])}
                           for box, score, label in zip(boxes.xyxy.cpu().tolist(), boxes.conf.cpu().tolist(), boxes.cls.cpu().tolist(), strict=True)]
                if segmentation and regions:
                    masks = prediction.masks.data.float().cpu().numpy()
                    if masks.shape != (len(regions), *frame.shape[1:3]):
                        raise ValueError('YOLO returned masks with unexpected source-image dimensions.')
                    for region, mask in zip(regions, masks, strict=True):
                        region['mask'] = mask
                results.append(regions)
        finally:
            if getattr(predictor, 'model', None) is not None:
                predictor.model.to('cpu')
    return results


def sam2_config(name):
    lower = name.lower()
    variant = next((value for key, value in [('base_plus', 'b+'), ('large', 'l'), ('small', 's'), ('tiny', 't')]
                    if key in lower), None)
    if variant is None:
        raise ValueError('SAM2 filenames must identify Hiera tiny, small, base_plus or large.')
    version = 'sam2.1' if 'sam2.1' in lower else 'sam2'
    return f'configs/{version}/{version}_hiera_{variant}.yaml'


def _load_sam2(path):
    try:
        import sam2
        from hydra.utils import instantiate
        from omegaconf import OmegaConf
    except ImportError as error:
        _missing_dependency('Meta SAM 2', error)
    # Load only trusted package YAML, without replacing another extension's Hydra
    # search path or using user-provided executable configuration.
    config = OmegaConf.load(Path(sam2.__file__).parent / sam2_config(path.name))
    model = instantiate(config.model, _recursive_=True)
    if path.suffix == '.safetensors':
        from safetensors.torch import load_file
        state = load_file(str(path), device='cpu')
    else:
        state = torch.load(path, map_location='cpu', weights_only=True)
        if isinstance(state, dict) and 'model' in state:
            state = state['model']
    model.load_state_dict(state, strict=True)
    return model.eval()


def sam2_masks(images, boxes, parameters, *, combine=True):
    path = model_path('sam2', parameters['sam2_model'])
    try:
        from sam2.sam2_image_predictor import SAM2ImagePredictor
    except ImportError as error:
        _missing_dependency('Meta SAM 2', error)
    masks = []
    with local_model(path, _load_sam2, device=parameters['detection_device'], precision=parameters['precision']) as (model, _device):
        predictor = SAM2ImagePredictor(model)
        try:
            for frame, frame_boxes in zip(images, boxes, strict=True):
                import comfy.model_management as mm
                mm.throw_exception_if_processing_interrupted()
                h, w = frame.shape[1:3]
                if not frame_boxes:
                    masks.append(np.zeros((h, w), dtype=np.float32) if combine else [])
                    continue
                pixels = (frame[0, ..., :3].detach().cpu().clamp(0, 1).numpy() * 255).astype(np.uint8)
                predictor.set_image(pixels)
                predicted, scores, _ = predictor.predict(box=np.asarray(frame_boxes, dtype=np.float32), multimask_output=True)
                if predicted.ndim == 3:
                    predicted, scores = predicted[None], scores[None]
                selected = predicted[np.arange(len(predicted)), np.argmax(scores, axis=-1)]
                masks.append(np.max(selected, axis=0).astype(np.float32) if combine else list(selected.astype(np.float32)))
                predictor.reset_predictor()
        finally:
            predictor.reset_predictor()
    return masks
