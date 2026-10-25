# Eclipse Server Endpoints
#
# Centralized REST API endpoints for all Eclipse functionality:
# - Wildcard management (list, refresh, preview)
# - Config management (log_level, dev_mode)
# - Smart Prompt folder/file access

import asyncio
import os
import re
import secrets
import sys
import threading
import time
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any

# Prevent shadowing of ComfyUI's top-level utils package by comfy/utils.py when nodes.py has been imported first.
if "utils" not in sys.modules:
    try:
        import utils  # type: ignore  # noqa: F401
    except ImportError:
        pass

import folder_paths  # type: ignore
from aiohttp import web  # type: ignore
from PIL import Image, ImageOps, UnidentifiedImageError  # type: ignore
from server import PromptServer  # type: ignore

from .common import (
    get_config_value,
    update_config_value,
    update_config_values,
)
from .logger import log
from .network_security import read_stream_limited
from .node_designs import available_node_design, load_node_designs, valid_design_id
from .request_security import (
    global_mutation_denial,
    read_json_object_request,
)
from .wildcard_engine import get_wildcard_list, wildcard_load

# Inline pattern to avoid regex_patterns dependency
RE_LEADING_NUMBERS = re.compile(r"^\d+[._-]*", re.IGNORECASE)

# Module-level storage for wildcard path (set by WildcardEndpoints)
_wildcard_path: str | None = None

# Debounce repeat /eclipse-nova/reload_all calls — multiple Eclipse extensions
# can request a shared library refresh in quick succession.
_RELOAD_ALL_DEBOUNCE_S = 2.0
_last_reload_all_ts: float = 0.0
_last_reload_all_result: dict[str, Any] | None = None
_MAX_IMAGE_BYTES = 100 * 1024 * 1024
_LOAD_IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".gif",
    ".tiff",
    ".tif",
}
_LOAD_IMAGE_THUMBNAIL_SIZE = (192, 192)
_LOAD_IMAGE_THUMBNAIL_QUALITY = 80
_AUDIO_SLICE_SEMAPHORE = asyncio.Semaphore(2)
# Detect ComfyUI native dynamic VRAM:
# 0.18.x: ModelPatcher gained 'model_mmap_residency'
# 0.23.0+: ModelPatcherDynamic subclass (is_dynamic() returns True) replaces that attribute
try:
    import comfy.model_patcher as _mp  # type: ignore

    _HAS_NATIVE_DYNAMIC_VRAM = hasattr(
        _mp, "ModelPatcherDynamic"
    ) or hasattr(  # 0.23.0+
        _mp.ModelPatcher, "model_mmap_residency"
    )  # 0.18.x
except Exception:  # noqa: BLE001 - optional ComfyUI compatibility probe
    _HAS_NATIVE_DYNAMIC_VRAM = False


def _read_nonempty_text_lines(path: str) -> list[str]:
    with open(path, encoding="utf-8") as file_handle:
        return [line.strip() for line in file_handle if line.strip()]


def _save_uploaded_image(input_dir: str, filename: str, data: bytes) -> str:
    # Reserve a name in the same operation that opens it. An existence check
    # followed by write_bytes can overwrite another upload (or follow a link).
    stem, suffix = os.path.splitext(filename)
    counter = 0
    while True:
        name = filename if counter == 0 else f"{stem} ({counter}){suffix}"
        destination = Path(input_dir) / name
        try:
            handle = destination.open("xb")
        except FileExistsError:
            counter += 1
            continue
        try:
            with handle:
                handle.write(data)
        except OSError:
            destination.unlink(missing_ok=True)
            raise
        return name


def _resolve_load_image_path(filename: str, subfolder: str, source_type: str) -> str:
    # Resolve the same input/output tuple used by ComfyUI's /view endpoint while
    # keeping every thumbnail read inside its selected base directory.
    if source_type not in {"input", "output"}:
        raise ValueError("Invalid image type")
    if (
        not filename
        or filename in {".", ".."}
        or "\x00" in filename
        or "/" in filename
        or "\\" in filename
    ):
        raise ValueError("Invalid filename")
    if os.path.splitext(filename)[1].lower() not in _LOAD_IMAGE_EXTENSIONS:
        raise ValueError("Unsupported image format")

    normalized_subfolder = subfolder
    if "\x00" in normalized_subfolder or "\\" in normalized_subfolder:
        raise ValueError("Invalid subfolder")
    parts = normalized_subfolder.split("/") if normalized_subfolder else []
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Invalid subfolder")

    base_dir = (
        folder_paths.get_input_directory()
        if source_type == "input"
        else folder_paths.get_output_directory()
    )
    real_base = os.path.realpath(base_dir)
    real_path = os.path.realpath(os.path.join(real_base, *parts, filename))
    try:
        if os.path.commonpath((real_base, real_path)) != real_base:
            raise ValueError("Invalid image path")
    except ValueError as error:
        raise ValueError("Invalid image path") from error
    return real_path


def _render_load_image_thumbnail(image_path: str) -> bytes:
    # Decode and resize in a worker thread. copy() fixes the selected initial
    # frame before the source container is closed, including animated formats.
    with Image.open(image_path) as source_image:
        source_image.seek(0)
        frame = ImageOps.exif_transpose(source_image.copy())
        frame.thumbnail(_LOAD_IMAGE_THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
        if "A" in frame.getbands() or "transparency" in frame.info:
            frame = frame.convert("RGBA")
        else:
            frame = frame.convert("RGB")
        output = BytesIO()
        frame.save(
            output,
            format="WEBP",
            quality=_LOAD_IMAGE_THUMBNAIL_QUALITY,
            save_all=False,
        )
        return output.getvalue()


class WildcardEndpoints:
    # Manages wildcard server endpoints.

    def __init__(self, wildcard_path: str | None = None):
        # nitialize endpoints.
        #
        # Args:
        #     wildcard_path: Path to wildcard directory. If None, uses default.
        global _wildcard_path

        if wildcard_path is None:
            wildcard_path = self._get_default_wildcard_path()

        self.wildcard_path = wildcard_path
        _wildcard_path = wildcard_path  # Store at module level for reload_all

        # Load wildcards on initialization
        log.debug("Wildcard", f"Loading wildcards from: {wildcard_path}")
        wildcard_load(wildcard_path)

        self._register_endpoints()

    def _get_default_wildcard_path(self) -> str:
        # Determine the default wildcard path.
        #
        # Priority:
        # 1. ComfyUI/models/wildcards (create if doesn't exist and copy examples)
        # 2. Extension's wildcards/ folder (fallback)
        #
        # Returns:
        #     Path to wildcard directory
        # Extension's wildcard folder (fallback)
        extension_root = os.path.dirname(os.path.dirname(__file__))
        extension_wildcard_path = os.path.join(extension_root, "wildcards")

        # Try to find ComfyUI root (go up from custom_nodes/ComfyUI_Eclipse_X)
        comfyui_root = os.path.abspath(os.path.join(extension_root, "..", ".."))
        models_wildcard_path = os.path.join(comfyui_root, "models", "wildcards")

        # Check if we're actually in a ComfyUI installation
        if os.path.exists(os.path.join(comfyui_root, "models")):
            # Create models/wildcards directory if it doesn't exist
            if not os.path.exists(models_wildcard_path):
                try:
                    os.makedirs(models_wildcard_path, exist_ok=True)
                    log.msg("Wildcard", f"Created directory: {models_wildcard_path}")

                    # Copy example files from extension's wildcards folder
                    if os.path.exists(extension_wildcard_path):
                        self._copy_example_wildcards(
                            extension_wildcard_path, models_wildcard_path
                        )
                except Exception as e:  # noqa: BLE001 - filesystem fallback boundary
                    log.error(
                        "Wildcard", f"Failed to create {models_wildcard_path}: {e}"
                    )
                    return extension_wildcard_path

            return models_wildcard_path
        else:
            # Not in a standard ComfyUI structure, use extension folder
            log.msg(
                "Wildcard",
                "Using extension's wildcard folder (ComfyUI models dir not found)",
            )
            return extension_wildcard_path

    def _copy_example_wildcards(self, source_dir: str, dest_dir: str) -> None:
        # Copy example wildcard files from source to destination.
        #
        # Args:
        #     source_dir: Source directory with example wildcards
        #     dest_dir: Destination directory
        import shutil

        try:
            copied_count = 0
            for filename in os.listdir(source_dir):
                if filename.endswith((".txt", ".yaml", ".yml")):
                    source_file = os.path.join(source_dir, filename)
                    dest_file = os.path.join(dest_dir, filename)

                    # Only copy if destination doesn't exist
                    if not os.path.exists(dest_file):
                        shutil.copy2(source_file, dest_file)
                        copied_count += 1

            if copied_count > 0:
                log.msg(
                    "Wildcard",
                    f"Copied {copied_count} example wildcard files to {dest_dir}",
                )
        except Exception as e:  # noqa: BLE001 - filesystem migration boundary
            log.error("Wildcard", f"Error copying example wildcards: {e}")

    def _register_endpoints(self):
        # Register all endpoints with PromptServer.

        # ==================== CONFIG ====================

        @PromptServer.instance.routes.get("/eclipse-nova/config/log_level")
        async def get_log_level(request):
            # GET /eclipse-nova/config/log_level
            #
            # Returns current log level from config.json
            log_level = get_config_value("log_level", "warning")
            return web.json_response({"log_level": log_level})

        @PromptServer.instance.routes.post("/eclipse-nova/config/log_level")
        async def set_log_level(request):
            # POST /eclipse-nova/config/log_level
            #
            # Updates log level in config.json
            # Body: {"log_level": "error|warning|info|debug"}
            denial = global_mutation_denial(request)
            if denial is not None:
                return denial
            try:
                data = await read_json_object_request(request)
                log_level = data.get("log_level", "").lower()

                # Validate log level
                valid_levels = ["error", "warning", "info", "debug"]
                if log_level not in valid_levels:
                    return web.json_response(
                        {
                            "success": False,
                            "error": f"Invalid log level. Must be one of: {', '.join(valid_levels)}",
                        },
                        status=400,
                    )

                # Update config
                success = update_config_value("log_level", log_level)

                if success:
                    # Reload logger config
                    from .logger import log

                    log._reload_config()
                    return web.json_response({"success": True, "log_level": log_level})
                else:
                    return web.json_response(
                        {"success": False, "error": "Failed to update config"},
                        status=500,
                    )
            except web.HTTPException:
                raise
            except Exception as e:  # noqa: BLE001 - endpoint boundary sanitizes failures
                log.error("Config", f"Log-level update failed: {type(e).__name__}")
                return web.json_response(
                    {"success": False, "error": "Config update failed"}, status=500
                )

        @PromptServer.instance.routes.get("/eclipse-nova/themes")
        async def get_node_designs(_request):
            return web.json_response(load_node_designs(), headers={"Cache-Control": "no-store"})

        @PromptServer.instance.routes.get("/eclipse-nova/config/all")
        async def get_all_config(request):
            # GET /eclipse-nova/config/all
            #
            # Returns current Eclipse settings.
            node_design = get_config_value("node_design", "neutral")
            return web.json_response(
                {
                    "log_level": get_config_value("log_level", "warning"),
                    "vue_size_fix": get_config_value("vue_size_fix", False),
                    "hide_node_state_badges": get_config_value(
                        "hide_node_state_badges", False
                    ),
                    "use_sliders": get_config_value("use_sliders", False),
                    "theme_regular_nodes": get_config_value("theme_regular_nodes", False),
                    "theme_groups": get_config_value("theme_groups", False),
                    "link_nova_themes": get_config_value("link_nova_themes", False),
                    "node_design": node_design if valid_design_id(node_design) else "neutral",
                    "has_native_dynamic_vram": _HAS_NATIVE_DYNAMIC_VRAM,
                }
            )

        @PromptServer.instance.routes.post("/eclipse-nova/config/update")
        async def update_config(request):
            # POST /eclipse-nova/config/update
            #
            # Updates multiple config values at once
            # Body: {"key": value, ...}
            denial = global_mutation_denial(request)
            if denial is not None:
                return denial
            try:
                data = await read_json_object_request(request)

                # Validate and update each key
                valid_keys = [
                    "log_level",
                    "use_sliders",
                    "theme_regular_nodes",
                    "theme_groups",
                    "link_nova_themes",
                    "node_design",
                ]
                updated = {}

                for key, value in data.items():
                    if key not in valid_keys:
                        continue

                    # Type validation
                    if key == "log_level" and (
                        not isinstance(value, str)
                        or value
                        not in [
                            "error",
                            "warning",
                            "info",
                            "debug",
                        ]
                    ):
                        return web.json_response(
                            {
                                "success": False,
                                "error": "log_level must be one of: error, warning, info, debug",
                            },
                            status=400,
                        )
                    elif key in (
                        "use_sliders",
                        "theme_regular_nodes",
                        "theme_groups",
                        "link_nova_themes",
                    ) and not isinstance(value, bool):
                        return web.json_response(
                            {
                                "success": False,
                                "error": f"{key} must be true or false",
                            },
                            status=400,
                        )
                    elif key == "node_design" and (
                        not available_node_design(value)
                    ):
                        return web.json_response(
                            {"success": False, "error": "Select an available node design"},
                            status=400,
                        )

                    updated[key] = value

                if updated and not update_config_values(updated):
                    return web.json_response(
                        {"success": False, "error": "Failed to update config"},
                        status=500,
                    )

                return web.json_response(
                    {"success": True, "updated": updated}
                )
            except web.HTTPException:
                raise
            except Exception as e:  # noqa: BLE001 - endpoint boundary sanitizes failures
                log.error("Config", f"Config update failed: {type(e).__name__}")
                return web.json_response(
                    {"success": False, "error": "Config update failed"}, status=500
                )

        # ==================== WILDCARDS ====================

        @PromptServer.instance.routes.post("/eclipse-nova/wildcards/preview")
        async def handle_preview_wildcards(request):
            from .wildcard_configuration import MAX_CONFIG_BYTES, generate

            body = await read_json_object_request(request, max_bytes=MAX_CONFIG_BYTES)
            if set(body) != {"configuration"}:
                return web.json_response({"success": False, "error": "Expected a wildcard configuration."}, status=400)
            try:
                # Preview uses the displayed seed. Only queueing resolves random
                # seeds or advances local controls; upstream sockets run normally.
                text, _lines, seed = generate(body["configuration"], preview=True)
                return web.json_response({"success": True, "text": text, "seed": str(seed) if seed is not None else None})
            except (TypeError, ValueError, OverflowError) as error:
                return web.json_response({"success": False, "error": str(error)}, status=400)

        @PromptServer.instance.routes.get("/eclipse-nova/wildcards/list")
        async def handle_get_wildcard_list(request):
            # GET /eclipse-nova/wildcards/list
            #
            # Returns:
            #     JSON list of available wildcards in format: ['__keyword1__', '__keyword2__', ...]
            try:
                wildcard_list = get_wildcard_list()
                return web.json_response(wildcard_list)
            except Exception as e:  # noqa: BLE001 - endpoint boundary sanitizes failures
                log.error("Wildcard", f"Error getting wildcard list: {e}")
                return web.json_response([])

        @PromptServer.instance.routes.get("/eclipse-nova/wildcards/refresh")
        async def handle_refresh_wildcards(request):
            # GET /eclipse-nova/wildcards/refresh
            #
            # Reloads wildcards from disk. Useful for discovering newly added wildcard files.
            #
            # Returns:
            #     JSON with success status and count of loaded wildcards
            try:
                wildcard_load(self.wildcard_path)
                wildcard_list = get_wildcard_list()

                return web.json_response(
                    {
                        "success": True,
                        "message": f"Loaded {len(wildcard_list)} wildcard groups",
                        "count": len(wildcard_list),
                    }
                )
            except Exception as e:  # noqa: BLE001 - endpoint boundary sanitizes failures
                log.error("Wildcard", f"Error refreshing wildcards: {e}")
                return web.json_response(
                    {"success": False, "message": str(e), "count": 0}
                )

        log.debug("Wildcard", "Registered server endpoints")


class SmartPromptEndpoints:
    # The new editor uses the same prompts/ library as execution.

    def __init__(self):
        from . import smart_prompt

        async def respond(operation, *args):
            try:
                result = await asyncio.to_thread(operation, *args)
                return web.json_response(result, headers={"Cache-Control": "no-store"})
            except smart_prompt.PromptFileConflict as error:
                return web.json_response({"error": str(error)}, status=409)
            except FileNotFoundError as error:
                return web.json_response({"error": str(error)}, status=404)
            except (TypeError, ValueError) as error:
                return web.json_response({"error": str(error)}, status=400)
            except OSError:
                return web.json_response({"error": "Could not access the prompt library."}, status=500)

        @PromptServer.instance.routes.get("/eclipse-nova/smart_prompt/catalog")
        async def prompt_catalog(_request):
            return await respond(smart_prompt.catalog)

        @PromptServer.instance.routes.get("/eclipse-nova/smart_prompt/file")
        async def prompt_file(request):
            return await respond(smart_prompt.read_file, request.query.get("path"))

        @PromptServer.instance.routes.post("/eclipse-nova/smart_prompt/file")
        async def save_prompt_file(request):
            denied = global_mutation_denial(request)
            if denied is not None:
                return denied
            data = await read_json_object_request(request, max_bytes=smart_prompt.MAX_FILE_BYTES * 6 + 4096)
            if set(data) != {"path", "content", "revision"}:
                return web.json_response({"error": "Expected a prompt path, content and revision."}, status=400)
            return await respond(smart_prompt.save_file, data["path"], data["content"], data["revision"])


class EclipseRuntimeEndpoints:
    # Eclipse reload and Smart Prompt endpoints.

    def __init__(self):
        self.extension_root = os.path.dirname(os.path.dirname(__file__))
        self.eclipse_prompt_dir = os.path.join(self.extension_root, "prompt")
        self.repo_prompt_dir = self.eclipse_prompt_dir
        self._register_endpoints()

    def _register_endpoints(self):
        # ==================== RELOAD ALL ====================

        @PromptServer.instance.routes.get("/eclipse-nova/reload_all")
        async def reload_all_configs(request):
            # GET /eclipse-nova/reload_all
            #
            # Reloads ALL Eclipse configs and caches from disk:
            # - Config (invalidate cache + reload logger)
            # - Wildcards
            # - Styles
            global _last_reload_all_ts, _last_reload_all_result
            now = time.monotonic()
            if (
                _last_reload_all_result is not None
                and (now - _last_reload_all_ts) < _RELOAD_ALL_DEBOUNCE_S
            ):
                return web.json_response({**_last_reload_all_result, "debounced": True})

            results: dict = {"success": True, "reloaded": []}

            # 1. Invalidate config cache and reload logger
            try:
                from .common import invalidate_config_cache

                invalidate_config_cache()
                from .logger import log as _log

                _log._reload_config()
                results["reloaded"].append(
                    "Config (cache invalidated, log level reloaded)"
                )
            except Exception as e:  # noqa: BLE001 - optional reload boundary
                results["config_error"] = str(e)

            # 2. Reload wildcards
            try:
                from .wildcard_engine import get_wildcard_list, wildcard_load

                if _wildcard_path:
                    wildcard_load(_wildcard_path)
                    wc_count = len(get_wildcard_list())
                    results["reloaded"].append(f"Wildcards ({wc_count} groups)")
                    results["wildcards"] = {"count": wc_count}
                else:
                    results["wildcards_error"] = "Wildcard path not initialized"
            except Exception as e:  # noqa: BLE001 - optional reload boundary
                results["wildcards_error"] = str(e)

            # 3. Reload styles
            try:
                from .styles import reload_styles as core_reload_styles

                style_result = core_reload_styles()
                if style_result.get("success"):
                    results["reloaded"].append(
                        f"Styles ({style_result.get('total_styles', 0)} styles)"
                    )
                    results["styles"] = style_result
                else:
                    results["styles_error"] = style_result.get("error")
            except Exception as e:  # noqa: BLE001 - optional reload boundary
                results["styles_error"] = str(e)

            _last_reload_all_ts = time.monotonic()
            _last_reload_all_result = results
            return web.json_response(results)

        # ==================== SMART PROMPT / FOLDER FILES ====================

        @PromptServer.instance.routes.get("/eclipse-nova/folder_files/{folder}")
        async def get_folder_files(request):
            # Get files from a smart prompt folder.
            folder = request.match_info.get("folder", "")
            if not folder:
                return web.json_response({})

            folder_path = os.path.join(self.eclipse_prompt_dir, folder)
            if not os.path.isdir(folder_path):
                folder_path = os.path.join(self.repo_prompt_dir, folder)

            files = {}
            if os.path.isdir(folder_path):
                folder_name = os.path.basename(folder_path)
                clean_folder_name = RE_LEADING_NUMBERS.sub("", folder_name)

                folder_files = []
                for fname in os.listdir(folder_path):
                    if fname.lower().endswith(".txt") and fname.startswith(
                        ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9")
                    ):
                        try:
                            number = int(fname.split("_")[0])
                            folder_files.append((number, fname))
                        except ValueError:
                            continue
                folder_files.sort(key=lambda x: x[0])

                for number, fname in folder_files:
                    base = os.path.splitext(fname)[0]
                    clean_base = RE_LEADING_NUMBERS.sub("", base).replace("_", " ")
                    display = f"{clean_folder_name} {clean_base}"
                    fpath = os.path.join(folder_path, fname)
                    try:
                        files[display] = await asyncio.to_thread(
                            _read_nonempty_text_lines,
                            fpath,
                        )
                    except Exception:  # noqa: BLE001 - unreadable prompt files remain isolated
                        files[display] = []

            return web.json_response(files)

        @PromptServer.instance.routes.get("/eclipse-nova/widget_folder_mapping")
        async def get_widget_folder_mapping(request):
            # Get widget-to-folder mapping for smart prompt.
            prompt_dir = self.eclipse_prompt_dir
            if not os.path.isdir(prompt_dir):
                prompt_dir = self.repo_prompt_dir

            mapping = {}
            if os.path.isdir(prompt_dir):
                for item in os.listdir(prompt_dir):
                    item_path = os.path.join(prompt_dir, item)
                    if os.path.isdir(item_path):
                        folder_name = os.path.basename(item_path)
                        clean_folder_name = RE_LEADING_NUMBERS.sub("", folder_name)

                        folder_files = []
                        for fname in os.listdir(item_path):
                            if fname.lower().endswith(".txt") and fname.startswith(
                                ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9")
                            ):
                                try:
                                    number = int(fname.split("_")[0])
                                    folder_files.append((number, fname))
                                except ValueError:
                                    continue
                        folder_files.sort(key=lambda x: x[0])

                        for number, fname in folder_files:
                            base = os.path.splitext(fname)[0]
                            clean_base = RE_LEADING_NUMBERS.sub("", base).replace(
                                "_", " "
                            )
                            display = f"{clean_folder_name} {clean_base}"
                            mapping[display] = clean_folder_name

            return web.json_response(mapping)

        log.debug("", "Registered template and config endpoints")


class LoadFilesEndpoints:
    # Catalog and refresh for the structured folder/file loader.

    def __init__(self):
        self._register_endpoints()

    def _register_endpoints(self):
        @PromptServer.instance.routes.post("/eclipse-nova/load_files/catalog")
        async def files_catalog(request):
            denial = global_mutation_denial(request)
            if denial is not None:
                return denial
            data = await read_json_object_request(request)
            from .image_loader_configuration import validate_files
            from .image_loading import catalog
            try:
                config = validate_files(data.get("configuration"))
                refresh = data.get("refresh", False)
                if type(refresh) is not bool:
                    raise ValueError("Refresh must be a boolean.")
                sources, total, folders = await asyncio.to_thread(catalog, config, refresh)
                return web.json_response({"total": total, "files": len(sources), "folders": folders}, headers={"Cache-Control": "no-store"})
            except (ValueError, TypeError, OSError) as error:
                return web.json_response({"error": str(error)}, status=400)

        log.debug("LoadFiles", "Registered folder/file catalog endpoint")


class LoadImageEndpoints:
    # Image browser listing, thumbnails, upload and deletion.

    def __init__(self):
        self._register_endpoints()

    def _register_endpoints(self):

        @PromptServer.instance.routes.get("/eclipse-nova/load_image/metadata")
        async def image_metadata_endpoint(request):
            from .image_metadata import read_generation_metadata

            try:
                image_path = _resolve_load_image_path(
                    request.query.get("filename", ""), request.query.get("subfolder", ""),
                    request.query.get("type", ""),
                )
                values = await asyncio.to_thread(read_generation_metadata, image_path)
            except FileNotFoundError:
                return web.json_response({"error": "Image not found"}, status=404)
            except (OSError, UnidentifiedImageError, ValueError, TypeError, RecursionError):
                return web.json_response({"error": "Image metadata could not be read"}, status=400)
            return web.json_response({"values": values}, headers={"Cache-Control": "no-store"})

        @PromptServer.instance.routes.post("/eclipse-nova/load_image/delete")
        async def delete_image_endpoint(request):
            # POST /eclipse-nova/load_image/delete
            #
            # Deletes an image from the ComfyUI input or output folder.
            # Request body: {"filename": "image.png", "folder": "input"|"output"}
            denial = global_mutation_denial(request)
            if denial is not None:
                return denial
            try:
                data = await read_json_object_request(request)
                filename = data.get("filename", "")
                folder = data.get("folder", "input")
                if not isinstance(filename, str) or not isinstance(folder, str):
                    return web.json_response(
                        {"success": False, "error": "Filename and folder must be strings"}, status=400
                    )
                filename = filename.strip()
                folder = folder.strip()

                if not filename:
                    return web.json_response(
                        {"success": False, "error": "Filename is required"}, status=400
                    )
                if folder not in ("input", "output"):
                    return web.json_response(
                        {"success": False, "error": "Invalid folder"}, status=400
                    )

                # Block path traversal and null bytes
                if ".." in filename or "\\" in filename or "\x00" in filename:
                    log.warning(
                        "LoadImage", f"Blocked path traversal attempt: {filename}"
                    )
                    return web.json_response(
                        {"success": False, "error": "Invalid filename"}, status=400
                    )

                base_dir = (
                    folder_paths.get_input_directory()
                    if folder == "input"
                    else folder_paths.get_output_directory()
                )
                filepath = os.path.join(base_dir, filename)

                # Verify the resolved path is still inside the base directory
                real_base = os.path.realpath(base_dir)
                real_file = os.path.realpath(filepath)
                if (
                    not real_file.startswith(real_base + os.sep)
                    and real_file != real_base
                ):
                    log.warning("LoadImage", f"Blocked path escape attempt: {filename}")
                    return web.json_response(
                        {"success": False, "error": "Invalid filename"}, status=400
                    )

                if not os.path.isfile(filepath):
                    return web.json_response(
                        {"success": False, "error": "File not found"}, status=404
                    )

                os.remove(filepath)
                log.msg(
                    "LoadImage",
                    f"\u2713 Deleted image '{filename}' from {folder} folder",
                )
                return web.json_response({"success": True})
            except web.HTTPException:
                raise
            except Exception as e:  # noqa: BLE001 - endpoint boundary sanitizes failures
                log.error("LoadImage", f"Error deleting image: {e}")
                return web.json_response(
                    {"success": False, "error": str(e)}, status=500
                )

        @PromptServer.instance.routes.get("/eclipse-nova/load_image/list")
        async def list_input_images_endpoint(request):
            # GET /eclipse-nova/load_image/list
            #
            # Returns an up-to-date list of images in the ComfyUI input folder
            # (including subfolders), sorted alphabetically.
            _img_exts = {
                ".png",
                ".jpg",
                ".jpeg",
                ".webp",
                ".bmp",
                ".gif",
                ".tiff",
                ".tif",
            }
            try:
                input_dir = folder_paths.get_input_directory()
                results = []
                for root, _dirs, filenames in os.walk(input_dir):
                    for f in filenames:
                        if os.path.splitext(f)[1].lower() not in _img_exts:
                            continue
                        full = os.path.join(root, f)
                        if not os.path.isfile(full):
                            continue
                        rel = os.path.relpath(full, input_dir).replace("\\", "/")
                        results.append(rel)
                files = sorted(results)
                return web.json_response({"success": True, "files": files})
            except Exception as e:  # noqa: BLE001 - endpoint boundary sanitizes failures
                log.error("LoadImage", f"Error listing images: {e}")
                return web.json_response(
                    {"success": False, "error": str(e)}, status=500
                )

        @PromptServer.instance.routes.get("/eclipse-nova/load_image/list_output")
        async def list_output_images_endpoint(request):
            # GET /eclipse-nova/load_image/list_output
            #
            # Returns image files in the ComfyUI output folder (including subfolders),
            # sorted by modification time descending (newest first).
            _img_exts = {
                ".png",
                ".jpg",
                ".jpeg",
                ".webp",
                ".bmp",
                ".gif",
                ".tiff",
                ".tif",
            }
            try:
                output_dir = folder_paths.get_output_directory()
                results = []
                for root, _dirs, filenames in os.walk(output_dir):
                    for f in filenames:
                        if os.path.splitext(f)[1].lower() not in _img_exts:
                            continue
                        full = os.path.join(root, f)
                        if not os.path.isfile(full):
                            continue
                        rel = os.path.relpath(full, output_dir).replace("\\", "/")
                        try:
                            mtime = os.path.getmtime(full)
                        except Exception:  # noqa: BLE001 - cache cleanup is best effort
                            mtime = 0
                        results.append((rel, mtime))
                results.sort(key=lambda x: x[1], reverse=True)
                files = [r[0] for r in results]
                return web.json_response({"success": True, "files": files})
            except Exception as e:  # noqa: BLE001 - endpoint boundary sanitizes failures
                log.error("LoadImage", f"Error listing output images: {e}")
                return web.json_response(
                    {"success": False, "error": str(e)}, status=500
                )

        @PromptServer.instance.routes.get("/eclipse-nova/load_image/thumbnail")
        async def load_image_thumbnail_endpoint(request):
            # GET /eclipse-nova/load_image/thumbnail
            #
            # Returns a static, bounded picker thumbnail for an input/output image.
            # Animated sources deliberately contribute only their initial frame.
            filename = request.query.get("filename", "")
            subfolder = request.query.get("subfolder", "")
            source_type = request.query.get("type", "").strip()
            try:
                image_path = _resolve_load_image_path(
                    filename,
                    subfolder,
                    source_type,
                )
            except ValueError as error:
                return web.json_response({"error": str(error)}, status=400)

            if not os.path.isfile(image_path):
                return web.json_response({"error": "Image not found"}, status=404)

            try:
                thumbnail = await asyncio.to_thread(
                    _render_load_image_thumbnail,
                    image_path,
                )
            except FileNotFoundError:
                return web.json_response({"error": "Image not found"}, status=404)
            except (OSError, UnidentifiedImageError, ValueError):
                return web.json_response(
                    {"error": "Image could not be decoded"},
                    status=422,
                )
            except Exception as error:  # noqa: BLE001 - endpoint boundary
                log.error(
                    "LoadImage",
                    f"Thumbnail generation failed: {type(error).__name__}",
                )
                return web.json_response(
                    {"error": "Thumbnail generation failed"},
                    status=500,
                )

            return web.Response(
                body=thumbnail,
                content_type="image/webp",
                headers={"Cache-Control": "no-store"},
            )

        log.debug("LoadImage", "Registered Load Image endpoints")

        @PromptServer.instance.routes.post("/eclipse-nova/load_image/upload")
        async def upload_images_endpoint(request):
            # POST /eclipse-nova/load_image/upload (multipart/form-data)
            #
            # Accepts one or more image files and copies them to the input folder.
            # If a file with the same name exists, appends " (N)" to avoid overwriting.
            # Returns the list of saved filenames.
            denial = global_mutation_denial(request)
            if denial is not None:
                return denial
            _img_exts = {
                ".png",
                ".jpg",
                ".jpeg",
                ".webp",
                ".bmp",
                ".gif",
                ".tiff",
                ".tif",
            }
            saved = []
            errors = []
            try:
                reader = await request.multipart()
                input_dir = folder_paths.get_input_directory()

                async for part in reader:
                    if part.name != "images":
                        await read_stream_limited(
                            part, _MAX_IMAGE_BYTES, collect=False
                        )
                        continue

                    original_name = part.filename or ""
                    # Sanitize filename
                    safe_name = os.path.basename(original_name).strip()
                    if not safe_name or ".." in safe_name or "\x00" in safe_name:
                        errors.append(f"Invalid filename: {original_name}")
                        await read_stream_limited(
                            part, _MAX_IMAGE_BYTES, collect=False
                        )
                        continue

                    ext = os.path.splitext(safe_name)[1].lower()
                    if ext not in _img_exts:
                        errors.append(f"Unsupported format: {safe_name}")
                        await read_stream_limited(
                            part, _MAX_IMAGE_BYTES, collect=False
                        )
                        continue

                    # Read file data in bounded chunks. Do not trust multipart
                    # headers to enforce the per-file limit.
                    data = await read_stream_limited(part, _MAX_IMAGE_BYTES)
                    if not data:
                        errors.append(f"Empty file: {safe_name}")
                        continue

                    final_name = await asyncio.to_thread(
                        _save_uploaded_image, input_dir, safe_name, data
                    )

                    saved.append(final_name)
                    log.msg(
                        "LoadImage", f"\u2713 Uploaded '{final_name}' to input folder"
                    )

                return web.json_response(
                    {"success": True, "files": saved, "errors": errors}
                )
            except ValueError as e:
                log.warning("LoadImage", f"Rejected oversized upload: {e}")
                return web.json_response(
                    {
                        "success": False,
                        "error": "File too large (max 100MB per image)",
                        "files": saved,
                    },
                    status=413,
                )
            except Exception as e:  # noqa: BLE001 - endpoint boundary sanitizes failures
                log.error("LoadImage", f"Error uploading images: {e}")
                return web.json_response(
                    {"success": False, "error": str(e), "files": saved}, status=500
                )


class PromptStylerEndpoints:
    # Manages Prompt Styler server endpoints.

    def __init__(self):
        self._register_endpoints()

    def _register_endpoints(self):
        @PromptServer.instance.routes.get("/eclipse-nova/prompt_styler/styles/{mode}")
        async def get_styles_for_mode(request):
            # GET /eclipse-nova/prompt_styler/styles/{mode}
            #
            # Returns styles for the specified mode (tag_based or natural_language).
            mode = "unknown"
            try:
                mode = request.match_info.get("mode", "tag_based")

                # Import from core styles module
                from .styles import get_styles_for_mode as core_get_styles_for_mode

                # Get styles for the requested mode
                styles = core_get_styles_for_mode(mode)

                return web.json_response(
                    {"mode": mode, "styles": styles, "count": len(styles)}
                )
            except Exception as e:  # noqa: BLE001 - endpoint boundary sanitizes failures
                log.error("PromptStyler", f"Error getting styles for mode {mode}: {e}")
                return web.json_response({"error": str(e), "styles": []}, status=500)

        @PromptServer.instance.routes.get("/eclipse-nova/prompt_styler/reload")
        async def reload_styles(request):
            # GET /eclipse-nova/prompt_styler/reload
            #
            # Reloads styles from disk. Useful for discovering newly added style files.
            try:
                from .styles import reload_styles as core_reload_styles

                result = core_reload_styles()
                log.msg(
                    "PromptStyler", f"Reloaded styles: {result['total_styles']} total"
                )
                return web.json_response(result)
            except Exception as e:  # noqa: BLE001 - endpoint boundary sanitizes failures
                log.error("PromptStyler", f"Error reloading styles: {e}")
                return web.json_response(
                    {"success": False, "error": str(e)}, status=500
                )

        log.debug("PromptStyler", "Registered style endpoints")


class ShotPlannerEndpoints:
    # Editable pool reload and explicit project reservation reset.

    def __init__(self):
        from .shot_planner_pools import ensure_pool_files

        try:
            ensure_pool_files()
        except (OSError, ValueError):
            log.warning("ShotPlanner", "Could not initialize planner files; use Reload planner files for details.")

        @PromptServer.instance.routes.get("/eclipse-nova/shot_planner/pools")
        async def reload_pools(_request):
            from .shot_planner_pools import pool_summary

            try:
                result = await asyncio.to_thread(pool_summary)
            except ValueError as error:
                return web.json_response({"success": False, "error": str(error)}, status=400,
                                         headers={"Cache-Control": "no-store"})
            return web.json_response(result, headers={"Cache-Control": "no-store"})

        @PromptServer.instance.routes.post("/eclipse-nova/shot_planner/reset")
        async def reset_planner(request):
            denial = global_mutation_denial(request)
            if denial is not None:
                return denial
            from .json_store import JsonStoreError
            from .shot_planner import reset_reservations

            data = await read_json_object_request(request, max_bytes=4096)
            if data.get("confirmation") != "reset":
                return web.json_response({"success": False, "error": "Reset confirmation is required."}, status=400)
            try:
                result = await asyncio.to_thread(reset_reservations, folder_paths.get_output_directory(), data.get("project"))
            except ValueError as error:
                return web.json_response({"success": False, "error": str(error)}, status=400)
            except (OSError, JsonStoreError):
                return web.json_response({"success": False, "error": "Could not reset the ledger. Check its file permissions and JSON; no history was replaced."}, status=409)
            return web.json_response(result, headers={"Cache-Control": "no-store"})


class LoadVideoEndpoints:
    # File browsing/probes are read-only. Explicit previews own bounded temporary
    # artifacts and cancellation events, never a persistent server-side playlist.
    def __init__(self):
        from .request_security import same_origin_browser_request
        from .video_helpers import preview_video_file
        from .video_loader import (
            VIDEO_EXTENSIONS,
            file_version,
            load_playlist,
            probe_video,
            resolve_video_file,
            video_thumbnail,
        )
        from .video_timing import media_cancellation, media_progress_callback

        routes = PromptServer.instance.routes
        workers = asyncio.Semaphore(2)
        jobs = {}
        running = set()

        @lru_cache(maxsize=64)
        def thumbnail(path, version):
            return video_thumbnail(path)

        @lru_cache(maxsize=64)
        def probe(path, version):
            return probe_video(path)

        def reference(request):
            return {name: request.query.get(name, default) for name, default in
                    (("type", "input"), ("subfolder", ""), ("filename", ""))}

        def discard(identity):
            job = jobs.pop(identity, None)
            if job:
                job["cancel"].set()
                job.pop("video", None)
                job["expiry"].cancel()

        @routes.get("/eclipse-nova/load_video/list")
        async def video_list(request):
            source = request.query.get("type", "input")
            if source not in ("input", "output"):
                return web.json_response({"error": "Invalid video folder"}, status=400)

            def list_files():
                root = folder_paths.get_input_directory() if source == "input" else folder_paths.get_output_directory()
                result = []
                for directory, _subdirs, filenames in os.walk(root, followlinks=False):
                    for filename in filenames:
                        if os.path.splitext(filename)[1].lower() not in VIDEO_EXTENSIONS:
                            continue
                        subfolder = os.path.relpath(directory, root).replace(os.sep, "/")
                        ref = {"type": source, "subfolder": "" if subfolder == "." else subfolder, "filename": filename}
                        try:
                            path = resolve_video_file(ref)
                            version, size = file_version(path)
                        except (ValueError, OSError):
                            continue
                        result.append({**ref, "modified": version // 1000000, "size": size})
                        if len(result) >= 10000:
                            return result, True
                return result, False

            async with workers:
                files, truncated = await asyncio.to_thread(list_files)
            files.sort(key=lambda item: (item["subfolder"], item["filename"].casefold()))
            return web.json_response({"files": files, "truncated": truncated})

        @routes.get("/eclipse-nova/load_video/probe")
        async def video_probe(request):
            try:
                path = resolve_video_file(reference(request))
                version = file_version(path)
                async with workers:
                    result = await asyncio.to_thread(probe, path, version)
                return web.json_response(result)
            except (ValueError, OSError) as error:
                return web.json_response({"error": str(error)}, status=422)
            except Exception as error:  # noqa: BLE001 - media boundary
                return web.json_response({"error": f"Cannot probe video ({type(error).__name__})"}, status=422)

        @routes.get("/eclipse-nova/load_video/thumbnail")
        async def video_poster(request):
            try:
                path = resolve_video_file(reference(request))
                version = file_version(path)
                etag = f'"{version[0]}-{version[1]}"'
                if request.headers.get("If-None-Match") == etag:
                    return web.Response(status=304, headers={"ETag": etag})
                async with workers:
                    data = await asyncio.to_thread(thumbnail, path, version)
                return web.Response(body=data, content_type="image/webp", headers={"ETag": etag, "Cache-Control": "private, max-age=0, must-revalidate"})
            except Exception as error:  # noqa: BLE001 - media boundary
                return web.json_response({"error": f"Poster unavailable ({type(error).__name__})"}, status=422)

        async def render(identity, payload):
            job = jobs.get(identity)
            if job is None:
                return

            def process():
                token = media_cancellation.set(job["cancel"])
                progress_token = media_progress_callback.set(lambda progress: job.update(progress=progress))
                try:
                    return load_playlist(payload["playlist"],
                                         **{name: payload[name] for name in ("width", "height", "fit", "timing_mode", "fps",
                                                                           "blend_mode", "blend_duration", "style", "style_strength", "style_period") if name in payload})[0]
                finally:
                    media_progress_callback.reset(progress_token)
                    media_cancellation.reset(token)

            try:
                async with workers:
                    if job["cancel"].is_set():
                        return
                    video = await asyncio.to_thread(process)
                if identity in jobs and not job["cancel"].is_set():
                    job.update(video=video, result=preview_video_file(video)[1], status="complete")
            except Exception as error:  # noqa: BLE001 - job boundary
                job.update(status="error", error=str(error))
            finally:
                job.pop("task", None)

        @routes.post("/eclipse-nova/load_video/preview")
        async def create_video_preview(request):
            if not same_origin_browser_request(request):
                return web.json_response({"error": "Cross-origin preview request rejected"}, status=403)
            payload = await read_json_object_request(request, max_bytes=262144)
            if not isinstance(payload.get("playlist"), str):
                return web.json_response({"error": "playlist is required"}, status=400)
            if len(jobs) >= 8:
                return web.json_response({"error": "Preview limit reached; cancel or close an existing preview"}, status=429)
            identity = secrets.token_urlsafe(24)
            jobs[identity] = {"status": "running", "cancel": threading.Event(),
                              "expiry": asyncio.get_running_loop().call_later(1800, discard, identity)}
            task = asyncio.create_task(render(identity, payload))
            jobs[identity]["task"] = task
            running.add(task)
            task.add_done_callback(running.discard)
            return web.json_response({"id": identity, "status": "running"})

        @routes.get("/eclipse-nova/load_video/preview/{identity}")
        async def get_video_preview(request):
            job = jobs.get(request.match_info["identity"])
            if job is None:
                return web.json_response({"error": "Preview expired"}, status=404)
            return web.json_response({key: job[key] for key in ("status", "result", "error", "progress") if key in job},
                                     headers={"Cache-Control": "no-store"})

        @routes.delete("/eclipse-nova/load_video/preview/{identity}")
        async def cancel_video_preview(request):
            if not same_origin_browser_request(request):
                return web.json_response({"error": "Cross-origin preview request rejected"}, status=403)
            discard(request.match_info["identity"])
            return web.json_response({"success": True})

        async def cleanup(_app):
            for identity in list(jobs):
                discard(identity)
            if running:
                await asyncio.gather(*list(running), return_exceptions=True)

        server_app = getattr(PromptServer.instance, "app", None)
        if server_app is not None:
            server_app.on_cleanup.append(cleanup)


def initialize_endpoints(wildcard_path: str | None = None):
    # Initialize all Eclipse server endpoints.
    #
    # Args:
    #     wildcard_path: Path to wildcard directory. If None, uses default.
    try:
        WildcardEndpoints(wildcard_path)
        EclipseRuntimeEndpoints()
        SmartPromptEndpoints()
        LoadFilesEndpoints()
        LoadImageEndpoints()
        LoadVideoEndpoints()
        PromptStylerEndpoints()
        ShotPlannerEndpoints()
        ImageSelectorEndpoints()
        SystemAudioRecorderEndpoints()
        AudioSliceEndpoints()

        log.msg("", "All server endpoints initialized successfully")
    except Exception as e:  # noqa: BLE001 - optional processor initialization boundary
        log.error("", f"Failed to initialize endpoints: {e}")


class ImageSelectorEndpoints:
    # REST endpoints for the Image Selector node.
    #
    # POST /eclipse-nova/image_selector/confirm
    #   Body: {"node_id": str, "indices": [int, ...]}
    #   → Stores the selection; node will consume it on next re-queue.
    #
    # POST /eclipse-nova/image_selector/discard
    #   Body: {"node_id": str}
    #   → Clears all state for this node (next queue = fresh first run).

    def __init__(self):
        self._register_endpoints()

    @staticmethod
    def _validate_state_request(data, *, require_generation=False):
        node_id = str(data.get("node_id", ""))
        if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.:-]{0,255}", node_id):
            return web.json_response({"error": "Invalid node_id"}, status=400)
        generation = data.get("generation")
        if (generation is not None or require_generation) and (
            not isinstance(generation, str) or not re.fullmatch(r"[0-9a-f]{32}", generation)
        ):
            return web.json_response({"error": "Invalid generation"}, status=400)
        return None

    @staticmethod
    def _stale_generation(data):
        # Older frontends can still use the existing mutation contract.
        if "generation" not in data:
            return None
        from .image_selection import get_selector_state

        if get_selector_state(str(data["node_id"]), data["generation"]) is None:
            return web.json_response(
                {"ok": False, "error": "Run workflow to reload images"}, status=409
            )
        return None

    def _register_endpoints(self):
        @PromptServer.instance.routes.get("/eclipse-nova/image_selector/state")
        async def state(request):
            invalid = self._validate_state_request(request.query, require_generation=True)
            if invalid is not None:
                return invalid
            from .image_selection import get_selector_state

            saved = get_selector_state(request.query["node_id"], request.query["generation"])
            # Pure validation: loading a workflow must never confirm, reset, or execute it.
            return web.json_response(
                {"ok": saved is not None, "state": saved},
                headers={"Cache-Control": "no-store"},
            )

        @PromptServer.instance.routes.post("/eclipse-nova/image_selector/confirm")
        async def confirm(request):
            data = await read_json_object_request(request)
            invalid = self._validate_state_request(data)
            if invalid is None:
                invalid = self._stale_generation(data)
            if invalid is not None:
                return invalid
            try:
                node_id = str(data.get("node_id", ""))
                indices = data.get("indices", [])
                if not node_id:
                    return web.json_response({"error": "node_id required"}, status=400)
                if not isinstance(indices, list) or not all(
                    type(i) is int and i >= 0 for i in indices
                ):
                    return web.json_response(
                        {"error": "indices must be a list of ints"}, status=400
                    )
                unique_indices = []
                seen = set()
                for i in indices:
                    if i not in seen:
                        seen.add(i)
                        unique_indices.append(i)
                from .image_selection import store_selection

                if "generation" in data:
                    from .image_selection import get_selector_state

                    saved = get_selector_state(node_id, data["generation"])
                    if saved is None or any(i >= saved["total_count"] for i in indices):
                        return web.json_response({"error": "Invalid image indices"}, status=400)
                store_selection(node_id, unique_indices)
                log.msg("ImageSelector", f"Node {node_id}: confirmed indices {indices}")
                return web.json_response(
                    {"ok": True, "node_id": node_id, "indices": indices}
                )
            except Exception as e:  # noqa: BLE001 - endpoint boundary sanitizes failures
                log.error("ImageSelector", f"confirm error: {e}")
                return web.json_response({"error": str(e)}, status=500)

        @PromptServer.instance.routes.post("/eclipse-nova/image_selector/reset_selection")
        async def reset_selection(request):
            data = await read_json_object_request(request)
            invalid = self._validate_state_request(data)
            if invalid is None:
                invalid = self._stale_generation(data)
            if invalid is not None:
                return invalid
            try:
                node_id = str(data.get("node_id", ""))
                if not node_id:
                    return web.json_response({"error": "node_id required"}, status=400)
                from .image_selection import reset_selection as py_reset_selection

                py_reset_selection(node_id)
                log.msg("ImageSelector", f"Node {node_id}: selection reset")
                return web.json_response({"ok": True, "node_id": node_id})
            except Exception as e:  # noqa: BLE001 - endpoint boundary sanitizes failures
                log.error("ImageSelector", f"reset_selection error: {e}")
                return web.json_response({"error": str(e)}, status=500)

        @PromptServer.instance.routes.post("/eclipse-nova/image_selector/discard")
        async def discard(request):
            data = await read_json_object_request(request)
            invalid = self._validate_state_request(data)
            if invalid is None:
                invalid = self._stale_generation(data)
            if invalid is not None:
                return invalid
            try:
                node_id = str(data.get("node_id", ""))
                if not node_id:
                    return web.json_response({"error": "node_id required"}, status=400)
                from .image_selection import clear_state

                clear_state(node_id)
                log.msg("ImageSelector", f"Node {node_id}: state discarded")
                return web.json_response({"ok": True, "node_id": node_id})
            except Exception as e:  # noqa: BLE001 - endpoint boundary sanitizes failures
                log.error("ImageSelector", f"discard error: {e}")
                return web.json_response({"error": str(e)}, status=500)


class SystemAudioRecorderEndpoints:
    # Secure lifecycle endpoints for the process-wide system-output recorder.

    def __init__(self):
        from .system_audio import SystemAudioError, system_audio_recorder

        self._error_type = SystemAudioError
        self._recorder = system_audio_recorder
        self._register_endpoints()

    @staticmethod
    def _error_response(error) -> web.Response:
        return web.json_response(
            {"success": False, "error": str(error)}, status=error.status
        )

    def _required(self, data, *names):
        missing = [name for name in names if name not in data]
        if missing:
            raise self._error_type(
                f"Missing required recorder field(s): {', '.join(missing)}."
            )

    def _register_endpoints(self):
        @PromptServer.instance.routes.get("/eclipse-nova/system_audio/devices")
        async def get_devices(request):
            denial = global_mutation_denial(request)
            if denial is not None:
                return denial
            try:
                result = await asyncio.to_thread(self._recorder.list_devices)
                return web.json_response({"success": True, **result})
            except self._error_type as error:
                return self._error_response(error)
            except Exception as error:  # noqa: BLE001 - endpoint boundary
                log.error(
                    "SystemAudioRecorder",
                    f"Device enumeration failed: {type(error).__name__}",
                )
                return web.json_response(
                    {"success": False, "error": "Could not enumerate audio devices."},
                    status=500,
                )

        @PromptServer.instance.routes.post("/eclipse-nova/system_audio/start")
        async def start_recording(request):
            denial = global_mutation_denial(request)
            if denial is not None:
                return denial
            try:
                data = await read_json_object_request(request, max_bytes=4096)
                self._required(
                    data,
                    "node_id",
                    "filename_prefix",
                    "format",
                    "mp3_bitrate",
                    "output_device",
                    "strip_start_silence",
                    "silence_threshold_db",
                )
                result = await asyncio.to_thread(
                    self._recorder.start,
                    node_id=data["node_id"],
                    filename_prefix=data["filename_prefix"],
                    output_format=data["format"],
                    bitrate=data["mp3_bitrate"],
                    device_id=data["output_device"],
                    strip_start_silence=data["strip_start_silence"],
                    silence_threshold_db=data["silence_threshold_db"],
                )
                return web.json_response(result)
            except web.HTTPException:
                raise
            except self._error_type as error:
                return self._error_response(error)
            except Exception as error:  # noqa: BLE001 - endpoint boundary
                log.error(
                    "SystemAudioRecorder",
                    f"Start failed: {type(error).__name__}",
                )
                return web.json_response(
                    {"success": False, "error": "Could not start system audio capture."},
                    status=500,
                )

        async def _token_operation(request, operation):
            denial = global_mutation_denial(request)
            if denial is not None:
                return denial
            try:
                data = await read_json_object_request(request, max_bytes=4096)
                self._required(data, "node_id", "token")
                result = await asyncio.to_thread(
                    operation,
                    node_id=data["node_id"],
                    token=data["token"],
                )
                return web.json_response(result)
            except web.HTTPException:
                raise
            except self._error_type as error:
                return self._error_response(error)
            except Exception as error:  # noqa: BLE001 - endpoint boundary
                log.error(
                    "SystemAudioRecorder",
                    f"Lifecycle operation failed: {type(error).__name__}",
                )
                return web.json_response(
                    {"success": False, "error": "Recorder operation failed."},
                    status=500,
                )

        async def _processing_operation(request, operation):
            denial = global_mutation_denial(request)
            if denial is not None:
                return denial
            try:
                data = await read_json_object_request(request, max_bytes=4096)
                self._required(
                    data,
                    "node_id",
                    "token",
                    "filename_prefix",
                    "format",
                    "mp3_bitrate",
                    "strip_start_silence",
                    "silence_threshold_db",
                )
                result = await asyncio.to_thread(
                    operation,
                    node_id=data["node_id"],
                    token=data["token"],
                    filename_prefix=data["filename_prefix"],
                    output_format=data["format"],
                    bitrate=data["mp3_bitrate"],
                    strip_start_silence=data["strip_start_silence"],
                    silence_threshold_db=data["silence_threshold_db"],
                )
                return web.json_response(result)
            except web.HTTPException:
                raise
            except self._error_type as error:
                return self._error_response(error)
            except Exception as error:  # noqa: BLE001 - endpoint boundary
                log.error(
                    "SystemAudioRecorder",
                    f"Processing operation failed: {type(error).__name__}",
                )
                return web.json_response(
                    {"success": False, "error": "Recorder processing failed."},
                    status=500,
                )

        @PromptServer.instance.routes.post("/eclipse-nova/system_audio/stop")
        async def stop_recording(request):
            return await _processing_operation(request, self._recorder.stop)

        @PromptServer.instance.routes.post("/eclipse-nova/system_audio/reprocess")
        async def reprocess_recording(request):
            return await _processing_operation(request, self._recorder.reprocess)

        @PromptServer.instance.routes.post("/eclipse-nova/system_audio/abort")
        async def abort_recording(request):
            return await _token_operation(request, self._recorder.abort)

        @PromptServer.instance.routes.post("/eclipse-nova/system_audio/status")
        async def recording_status(request):
            return await _token_operation(request, self._recorder.status)

        @PromptServer.instance.routes.post("/eclipse-nova/system_audio/release")
        async def release_recording(request):
            return await _token_operation(request, self._recorder.release)


class AudioSliceEndpoints:
    # REST endpoints for serving sliced audio segments.
    #
    # GET /eclipse-nova/audio_slice
    #   Query: filename=str, start_time=float, duration=float
    #   → Returns the dynamically sliced audio file in WAV format.

    def __init__(self):
        self._register_endpoints()

    def _register_endpoints(self):
        @PromptServer.instance.routes.get("/eclipse-nova/audio/files")
        async def get_audio_files(request):
            from .audio_loading import audio_files

            return web.json_response({"files": await asyncio.to_thread(audio_files)})

        @PromptServer.instance.routes.get("/eclipse-nova/audio_slice")
        async def get_audio_slice(request):
            try:
                params = request.query
                filename = params.get("filename", "")
                if not filename:
                    return web.Response(text="filename parameter required", status=400)

                try:
                    audio_path = folder_paths.get_annotated_filepath(filename)
                except Exception as e:  # noqa: BLE001 - per-slice isolation
                    return web.Response(text=f"Invalid file path: {e}", status=400)

                if not os.path.isfile(audio_path):
                    return web.Response(text=f"File not found: {filename}", status=404)

                try:
                    start_time = float(params.get("start_time", 0.0))
                    duration = float(params.get("duration", 0.0))
                except ValueError:
                    return web.Response(
                        text="Invalid start_time or duration parameter", status=400
                    )

                from .audio import load_audio_file

                def _decode_and_encode_audio() -> bytes:
                    import io as python_io
                    import wave

                    import torch  # type: ignore

                    waveform, sample_rate = load_audio_file(
                        audio_path,
                        start_time=start_time,
                        duration=duration,
                    )

                    # waveform shape: [channels, samples], [samples], or
                    # [1, channels, samples]
                    if waveform.ndim == 3:
                        waveform = waveform[0]

                    waveform = torch.clamp(waveform, -1.0, 1.0)
                    int_waveform = (waveform * 32767.0).to(torch.int16)

                    if int_waveform.ndim == 2:
                        int_waveform = int_waveform.t()
                        num_channels = int_waveform.shape[1]
                    else:
                        num_channels = 1

                    pcm_data = int_waveform.cpu().numpy().tobytes()
                    buf = python_io.BytesIO()
                    with wave.open(buf, "wb") as wav_file:
                        wav_file.setnchannels(num_channels)
                        wav_file.setsampwidth(2)
                        wav_file.setframerate(sample_rate)
                        wav_file.writeframes(pcm_data)
                    return buf.getvalue()

                async with _AUDIO_SLICE_SEMAPHORE:
                    wav_bytes = await asyncio.to_thread(_decode_and_encode_audio)

                return web.Response(
                    body=wav_bytes,
                    content_type="audio/wav",
                    headers={
                        "Accept-Ranges": "bytes",
                        "Cache-Control": "no-cache",
                    },
                )
            except Exception as e:  # noqa: BLE001 - endpoint boundary sanitizes failures
                log.error("AudioSlice", f"Error slicing audio: {e}")
                return web.Response(text=str(e), status=500)
