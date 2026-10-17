# Shared rendering for the image and text FX panels.
import textwrap

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont

from .common import make_comfy_progress
from .fonts import get_font_path
from .image_helpers import (
    expand_mask,
    hex_to_rgb,
    image2mask,
    lerp,
    pil2tensor,
    shift_image,
    step_color,
    tensor2pil,
)
from .logger import log


def _blend_screen(bg: np.ndarray, fg: np.ndarray) -> np.ndarray:
    return 255.0 - (255.0 - bg) * (255.0 - fg) / 255.0


def _composite_with_mask(
    canvas: Image.Image,
    color: tuple,
    mask: Image.Image,
    opacity: int,
    blend: str = "normal",
) -> Image.Image:
    color_img = Image.new("RGBA", canvas.size, (*color, 255))
    if blend == "screen":
        bg_arr = np.array(canvas.convert("RGBA"), dtype=float)
        fg_arr = np.array(color_img, dtype=float)
        blended = _blend_screen(bg_arr[:, :, :3], fg_arr[:, :, :3])
        blended = np.clip(blended, 0, 255)
        result_arr = bg_arr.copy()
        result_arr[:, :, :3] = blended
        result_arr[:, :, 3] = 255  # Full opacity — paste mask controls blending
        blended_img = Image.fromarray(np.uint8(result_arr))
    else:
        blended_img = color_img

    mask_arr = np.array(mask.convert("L"), dtype=float) * (opacity / 100.0)
    opacity_mask = Image.fromarray(np.uint8(np.clip(mask_arr, 0, 255)))

    canvas_copy = canvas.copy()
    canvas_copy.paste(blended_img, mask=opacity_mask)
    return canvas_copy


# ---------------------------------------------------------------------------
# Position calculation
# ---------------------------------------------------------------------------

POSITIONS = [
    "top_left",
    "top_center",
    "top_right",
    "center_left",
    "center",
    "center_right",
    "bottom_left",
    "bottom_center",
    "bottom_right",
]


def _compute_position(
    position: str,
    canvas_w: int,
    canvas_h: int,
    obj_w: int,
    obj_h: int,
    margin_x: int,
    margin_y: int,
) -> tuple[int, int]:
    if "left" in position:
        x = margin_x
    elif "right" in position:
        x = canvas_w - obj_w - margin_x
    else:
        x = (canvas_w - obj_w) // 2

    if "top" in position:
        y = margin_y
    elif "bottom" in position:
        y = canvas_h - obj_h - margin_y
    else:
        y = (canvas_h - obj_h) // 2

    return (x, y)




def render_image_with_fx(
    input_image,
    image_scale,
    opacity,
    position,
    margin_x,
    margin_y,
    enable_glow,
    glow_intensity,
    glow_range,
    glow_blur,
    glow_inner_color,
    glow_outer_color,
    enable_shadow,
    shadow_offset_x,
    shadow_offset_y,
    shadow_grow,
    shadow_blur,
    shadow_color,
    shadow_opacity,
    background_image,
    mask=None,
    invert_mask=True,
):

    # --- Process input image once (single watermark/logo, applied to every background frame) ---
    n_frames = background_image.shape[0]

    canvas_w, canvas_h = tensor2pil(background_image[0]).size

    # --- Convert input image to RGBA ---
    src_pil = tensor2pil(input_image[0]).convert("RGBA")

    # --- Resolve shape mask (before cropping) ---
    if mask is not None:
        mask_pil = tensor2pil(mask[0]).convert("L")
        if invert_mask:
            mask_pil = Image.fromarray(255 - np.array(mask_pil))
        if mask_pil.size != src_pil.size:
            mask_pil = mask_pil.resize(src_pil.size, Image.Resampling.LANCZOS)
        src_pil.putalpha(mask_pil)

    # --- Auto-crop to non-transparent content ---
    # Threshold alpha to ignore near-transparent edge artifacts (alpha < 10)
    alpha = src_pil.split()[3]
    alpha_thresh = Image.fromarray((np.array(alpha) >= 10).astype(np.uint8) * 255)
    bbox = alpha_thresh.getbbox()  # (left, top, right, bottom) of solid pixels
    if bbox and bbox != (0, 0, src_pil.width, src_pil.height):
        src_pil = src_pil.crop(bbox)
        log.debug(
            'ImageWithFX',
            f"Auto-cropped transparent padding: {src_pil.size[0]}x{src_pil.size[1]}",
        )

    # --- Fit input image to background (keep aspect ratio) then apply scale ---
    # 100% = input fits entirely within the background (contained)
    fit_ratio = min(canvas_w / src_pil.width, canvas_h / src_pil.height)
    final_scale = fit_ratio * (image_scale / 100.0)
    new_w = max(1, int(src_pil.width * final_scale))
    new_h = max(1, int(src_pil.height * final_scale))
    if (new_w, new_h) != src_pil.size:
        src_pil = src_pil.resize((new_w, new_h), Image.Resampling.LANCZOS)

    src_w, src_h = src_pil.size
    src_alpha = src_pil.split()[3]  # L mode

    # --- Compute position on canvas ---
    img_x, img_y = _compute_position(
        position, canvas_w, canvas_h, src_w, src_h, margin_x, margin_y
    )

    # --- Place the source image + alpha onto canvas-sized layers (once) ---
    img_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    img_layer.paste(src_pil, (img_x, img_y))

    canvas_alpha = Image.new("L", (canvas_w, canvas_h), 0)
    canvas_alpha.paste(src_alpha, (img_x, img_y))

    shape_mask = image2mask(canvas_alpha)  # [1, H, W] tensor

    # --- Pre-compute shadow mask (once — only depends on input image shape) ---
    shadow_mask_pil: Image.Image | None = None
    if enable_shadow and shadow_opacity > 0:
        shadow_mask_pil = canvas_alpha.copy()
        if shadow_offset_x != 0 or shadow_offset_y != 0:
            shadow_mask_pil = shift_image(
                shadow_mask_pil, shadow_offset_x, shadow_offset_y
            )
        if shadow_grow > 0 or shadow_blur > 0:
            sm_tensor = expand_mask(
                image2mask(shadow_mask_pil), shadow_grow, shadow_blur
            )
            shadow_mask_pil = tensor2pil(sm_tensor).convert("L")
        shadow_rgb = hex_to_rgb(shadow_color)
    else:
        shadow_rgb = (0, 0, 0)  # unused

    # --- Pre-compute glow steps (once — only depends on input image shape) ---
    glow_steps: list[tuple[tuple[int, int, int], Image.Image, int]] = []
    if enable_glow:
        blur_factor = glow_blur / 20.0
        grow = glow_range
        for step in range(glow_intensity):
            step_blur = int(grow * blur_factor)
            color = step_color(
                glow_outer_color, glow_inner_color, glow_intensity, step
            )
            glow_mask_tensor = expand_mask(shape_mask, grow, max(step_blur, 1))
            glow_mask_pil = tensor2pil(glow_mask_tensor).convert("L")
            step_opacity = (
                int(lerp(1, 100, step / glow_intensity))
                if glow_intensity > 0
                else 100
            )
            glow_steps.append((color, glow_mask_pil, step_opacity))
            grow = grow - int(glow_range / glow_intensity)
            if grow <= 0:
                break

    # --- Composite onto each background frame ---
    out_images: list[torch.Tensor] = []
    out_masks: list[torch.Tensor] = []
    pbar = make_comfy_progress(n_frames)

    for frame_idx in range(n_frames):
        bg_pil = tensor2pil(background_image[frame_idx]).convert("RGBA")
        canvas = bg_pil.copy()

        # --- Drop shadow ---
        if shadow_mask_pil is not None:
            canvas = _composite_with_mask(
                canvas, shadow_rgb, shadow_mask_pil, shadow_opacity
            )

        # --- Outer glow ---
        for glow_color, glow_mask_pil, step_opacity in glow_steps:
            canvas = _composite_with_mask(
                canvas, glow_color, glow_mask_pil, step_opacity, blend="screen"
            )

        # --- Composite input image on top ---
        canvas.paste(img_layer, mask=canvas_alpha)

        # --- Apply opacity: blend in RGB to avoid RGBA→RGB black artifacts ---
        canvas_rgb = canvas.convert("RGB")
        if opacity < 100:
            bg_rgb = bg_pil.convert("RGB")
            canvas_rgb = Image.blend(bg_rgb, canvas_rgb, opacity / 100.0)

        out_images.append(pil2tensor(canvas_rgb))
        out_masks.append(shape_mask)
        pbar.update(1)

    out_image = torch.cat(out_images, dim=0)  # [N, H, W, C]
    out_mask = torch.cat(out_masks, dim=0)  # [N, H, W]

    log.msg(
        'ImageWithFX',
        f"Composited image ({canvas_w}x{canvas_h}), frames={n_frames}, glow={enable_glow}, shadow={enable_shadow}",
    )
    return out_image, out_mask


def render_text_with_fx(
    text,
    font_file,
    font_size,
    text_scale,
    text_color,
    text_align,
    char_per_line,
    leading,
    stroke_width,
    stroke_color,
    opacity,
    position,
    margin_x,
    margin_y,
    enable_glow,
    glow_intensity,
    glow_range,
    glow_blur,
    glow_inner_color,
    glow_outer_color,
    enable_shadow,
    shadow_offset_x,
    shadow_offset_y,
    shadow_grow,
    shadow_blur,
    shadow_color,
    shadow_opacity,
    background_image=None,
):

    # --- Scale font size ---
    effective_font_size = max(1, int(font_size * text_scale / 100.0))

    # --- Load font ---
    font_path = get_font_path(font_file)
    try:
        font = ImageFont.truetype(font_path, effective_font_size)
    except (OSError, ValueError) as error:
        raise ValueError(f"Cannot load font {font_file!r} from models/fonts.") from error

    # --- Wrap and measure text (once — same for all frames) ---
    paragraphs = text.split("\n")
    all_lines: list[str] = []
    for paragraph in paragraphs:
        if paragraph.strip() == "":
            all_lines.append("")
        else:
            lines = textwrap.wrap(
                paragraph,
                width=char_per_line,
                expand_tabs=False,
                replace_whitespace=False,
                drop_whitespace=False,
            )
            all_lines.extend(lines if lines else [""])

    # Measure each line
    line_metrics: list[tuple[int, int, int]] = (
        []
    )  # (width, height, baseline_offset)
    for line in all_lines:
        if line == "":
            # Empty line — use font height for spacing
            bbox = font.getbbox("Mg")
            h = bbox[3] - bbox[1]
            line_metrics.append((0, h, bbox[1]))
        else:
            bbox = font.getbbox(line)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            line_metrics.append((w, h, bbox[1]))

    # Total text block dimensions
    total_text_h = sum(m[1] for m in line_metrics) + leading * max(
        0, len(all_lines) - 1
    )
    max_text_w = max((m[0] for m in line_metrics), default=0)
    # Account for stroke width
    if stroke_width > 0:
        max_text_w += stroke_width * 2
        total_text_h += stroke_width * 2

    # --- Determine batch size and canvas dimensions (from first background frame) ---
    n_frames = background_image.shape[0] if background_image is not None else 1

    if background_image is not None:
        canvas_w, canvas_h = tensor2pil(background_image[0]).size
    else:
        # Auto-size canvas to fit text + effect padding (uniform)
        pad = 0
        if enable_glow:
            pad = max(pad, glow_range + glow_blur)
        if enable_shadow:
            pad = max(
                pad,
                abs(shadow_offset_x) + shadow_grow + shadow_blur,
                abs(shadow_offset_y) + shadow_grow + shadow_blur,
            )
        canvas_w = max(1, max_text_w + pad * 2 + margin_x * 2)
        canvas_h = max(1, total_text_h + pad * 2 + margin_y * 2)

    # --- Compute text position (based on first-frame canvas size) ---
    if background_image is not None:
        text_x, text_y = _compute_position(
            position,
            canvas_w,
            canvas_h,
            max_text_w,
            total_text_h,
            margin_x,
            margin_y,
        )
    else:
        # Auto-size: center text within padded canvas
        text_x = (canvas_w - max_text_w) // 2
        text_y = (canvas_h - total_text_h) // 2

    # --- Draw text layer once (shared across all frames of the same canvas size) ---
    text_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(text_layer)
    y_cursor = text_y + (max(0, stroke_width))

    text_rgb = hex_to_rgb(text_color)
    stroke_rgb = hex_to_rgb(stroke_color) if stroke_width > 0 else None

    for i, line in enumerate(all_lines):
        lw, lh, lbase = line_metrics[i]
        if line == "":
            y_cursor += lh + leading
            continue

        # Horizontal alignment within text block
        if text_align == "left":
            lx = text_x
        elif text_align == "right":
            lx = text_x + max_text_w - lw
        else:  # center
            lx = text_x + (max_text_w - lw) // 2

        draw.text(
            (lx, y_cursor - lbase),
            line,
            fill=(*text_rgb, 255),
            font=font,
            stroke_width=stroke_width,
            stroke_fill=(*stroke_rgb, 255) if stroke_rgb else None,
        )
        y_cursor += lh + leading

    # Extract alpha as mask — computed once, reused for all frames
    text_alpha = text_layer.split()[3]  # L mode
    text_mask = image2mask(text_alpha)  # [1, H, W] tensor

    # Pre-compute shadow mask (same for every frame — only depends on text shape)
    shadow_mask_precomp: Image.Image | None = None
    if enable_shadow and shadow_opacity > 0:
        shadow_mask_precomp = text_alpha.copy()
        if shadow_offset_x != 0 or shadow_offset_y != 0:
            shadow_mask_precomp = shift_image(
                shadow_mask_precomp, shadow_offset_x, shadow_offset_y
            )
        if shadow_grow > 0 or shadow_blur > 0:
            sm_tensor = expand_mask(
                image2mask(shadow_mask_precomp), shadow_grow, shadow_blur
            )
            shadow_mask_precomp = tensor2pil(sm_tensor).convert("L")
        shadow_rgb = hex_to_rgb(shadow_color)
    else:
        shadow_rgb = (0, 0, 0)  # unused

    # Pre-compute glow masks (same for every frame — only depends on text shape)
    glow_steps: list[tuple[tuple[int, int, int], Image.Image, int]] = (
        []
    )  # (color, mask_pil, opacity)
    if enable_glow:
        blur_factor = glow_blur / 20.0
        grow = glow_range
        for step in range(glow_intensity):
            step_blur = int(grow * blur_factor)
            color = step_color(
                glow_outer_color, glow_inner_color, glow_intensity, step
            )
            glow_mask_tensor = expand_mask(text_mask, grow, max(step_blur, 1))
            glow_mask_pil = tensor2pil(glow_mask_tensor).convert("L")
            step_opacity = (
                int(lerp(1, 100, step / glow_intensity))
                if glow_intensity > 0
                else 100
            )
            glow_steps.append((color, glow_mask_pil, step_opacity))
            grow = grow - int(glow_range / glow_intensity)
            if grow <= 0:
                break

    # --- Process each background frame ---
    out_images: list[torch.Tensor] = []
    out_masks: list[torch.Tensor] = []
    pbar = make_comfy_progress(n_frames)

    for frame_idx in range(n_frames):
        if background_image is not None:
            bg_pil = tensor2pil(background_image[frame_idx]).convert("RGBA")
            canvas = bg_pil.copy()
        else:
            bg_pil = None
            canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

        # --- Drop shadow (behind everything) ---
        if shadow_mask_precomp is not None:
            canvas = _composite_with_mask(
                canvas, shadow_rgb, shadow_mask_precomp, shadow_opacity
            )

        # --- Outer glow (between shadow and text) ---
        for glow_color, glow_mask_pil, step_opacity in glow_steps:
            canvas = _composite_with_mask(
                canvas, glow_color, glow_mask_pil, step_opacity, blend="screen"
            )

        # --- Composite text on top ---
        canvas.paste(text_layer, mask=text_alpha)

        # --- Build output tensors for this frame ---
        if bg_pil is None:
            # No background: flatten RGBA onto black for RGB output
            flat = Image.new("RGBA", canvas.size, (0, 0, 0, 255))
            flat.paste(canvas, mask=canvas.split()[3])
            canvas_rgb = flat.convert("RGB")
            if opacity < 100:
                canvas_rgb = Image.blend(Image.new("RGB", canvas.size), canvas_rgb, opacity / 100.0)
            out_img_frame = pil2tensor(canvas_rgb)
        else:
            # Apply opacity: blend in RGB to avoid RGBA→RGB black artifacts
            canvas_rgb = canvas.convert("RGB")
            if opacity < 100:
                bg_rgb = bg_pil.convert("RGB")
                canvas_rgb = Image.blend(bg_rgb, canvas_rgb, opacity / 100.0)
            out_img_frame = pil2tensor(canvas_rgb)

        out_images.append(out_img_frame)
        out_masks.append(text_mask)
        pbar.update(1)

    out_image = torch.cat(out_images, dim=0)  # [N, H, W, C]
    out_mask = torch.cat(out_masks, dim=0)  # [N, H, W]

    log.msg(
        'TextImageWithFX',
        f"Rendered text ({canvas_w}x{canvas_h}), frames={n_frames}, glow={enable_glow}, shadow={enable_shadow}",
    )
    return out_image, out_mask
