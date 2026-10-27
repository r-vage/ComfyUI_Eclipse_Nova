# Node device choices follow ComfyUI's active device and memory manager.
import torch

DEVICE_OPTIONS = ['default', 'cpu']
DEVICE_TIP = 'Default uses ComfyUI’s configured device. CPU forces CPU processing. Backends without support for the configured accelerator use CPU.'


def device_selection(value):
    # Older workflows used these names for automatic/accelerated processing.
    if value in ('auto', 'gpu', 'cuda', 'mps'):
        return 'default'
    if value not in DEVICE_OPTIONS:
        raise ValueError('Device must be Default or CPU.')
    return value


def resolve_device(value='default'):
    if device_selection(value) == 'cpu':
        return torch.device('cpu')
    import comfy.model_management as mm
    return mm.get_torch_device()


def whisper_device(value='default'):
    # CTranslate2 supports NVIDIA CUDA, not PyTorch's ROCm/MPS/XPU backends.
    device = resolve_device(value)
    if device.type != 'cuda' or torch.version.hip:
        return torch.device('cpu')
    return device
