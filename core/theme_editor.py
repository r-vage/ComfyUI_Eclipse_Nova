# Explicit theme editing. Bundled defaults stay untouched; saves are custom overrides.
import asyncio
import hashlib
import json

from aiohttp import web

from . import node_designs as designs
from .json_store import JsonStoreError, locked_path, write_json_object
from .logger import log
from .request_security import global_mutation_denial, read_json_object_request


class ThemeConflict(ValueError):
    pass


def theme_revision(theme):
    return hashlib.sha256(json.dumps(theme, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def editor_catalog():
    catalog = designs.load_node_designs()
    return {**catalog, 'revisions': {key: theme_revision(value) for key, value in catalog['themes'].items()},
            'fields': {'colors': sorted(designs._COLOR_KEYS), 'shadows': sorted(designs._SHADOW_KEYS),
                       'categories': sorted(designs._CATEGORIES)}}


def _real_directory(path):
    if path.is_symlink() or not path.is_dir():
        raise ValueError('Theme folders must be real directories, not symlinks.')


def save_theme(data):
    if set(data) != {'id', 'theme', 'mode', 'revision'}:
        raise ValueError('Expected theme ID, theme, mode and revision.')
    theme_id, theme, mode = data['id'], data['theme'], data['mode']
    if not designs.valid_design_id(theme_id):
        raise ValueError('Use a lowercase theme ID with letters, digits, hyphens or underscores (up to 64 characters).')
    if mode not in ('save', 'create'):
        raise ValueError('Choose Save or Save As.')
    if mode == 'save' and (not isinstance(data['revision'], str) or len(data['revision']) != 64):
        raise ValueError('Reload the theme before saving.')
    if mode == 'create' and data['revision'] is not None:
        raise ValueError('A new theme must not have a revision.')
    designs._validate_theme(theme)
    if len(json.dumps(theme, ensure_ascii=False).encode()) > designs.MAX_THEME_BYTES:
        raise ValueError('Theme exceeds the size limit.')
    root = designs.THEMES_DIR
    _real_directory(root)
    # Serialize ID checks and creates across editor requests/processes.
    with locked_path(root / '.editor.json'):
        _real_directory(root)
        custom = root / 'custom'
        custom.mkdir(exist_ok=True)
        _real_directory(custom)
        target, base = custom / f'{theme_id}.json', root / f'{theme_id}.json'
        if mode == 'create':
            if any(path.exists() or path.is_symlink() for path in (target, base)):
                raise ThemeConflict('That theme ID already exists. Choose another ID for Save As.')
        else:
            current = target if target.exists() or target.is_symlink() else base
            if not current.exists() and not current.is_symlink():
                raise ThemeConflict('The theme was removed. Reload it or use Save As with a new ID.')
            # Refuse malformed files and symlinks instead of replacing user data.
            if theme_revision(designs._read_theme(current)) != data['revision']:
                raise ThemeConflict('The theme changed since it was opened. Reopen the editor to load the latest version, or use Save As.')
        if not target.exists() and len(designs._theme_files(custom)) >= designs.MAX_THEME_FILES:
            raise ValueError('The custom theme folder is full.')
        _real_directory(custom)
        if target.is_symlink():
            raise ValueError('Theme files must not be symlinks.')
        write_json_object(target, theme)
    return {'success': True, 'id': theme_id, 'theme': theme, 'revision': theme_revision(theme)}


def register_theme_editor_routes(routes):
    @routes.get('/eclipse-nova/themes/editor')
    async def get_theme_editor(_request):
        return web.json_response(editor_catalog(), headers={'Cache-Control': 'no-store'})

    @routes.post('/eclipse-nova/themes/save')
    async def post_theme_editor(request):
        denial = global_mutation_denial(request)
        if denial is not None:
            return denial
        data = await read_json_object_request(request)
        try:
            return web.json_response(await asyncio.to_thread(save_theme, data))
        except ThemeConflict as error:
            return web.json_response({'success': False, 'error': str(error)}, status=409)
        except (TypeError, ValueError) as error:
            return web.json_response({'success': False, 'error': str(error)}, status=400)
        except (OSError, JsonStoreError) as error:
            log.error('Themes', f'Could not save theme: {type(error).__name__}')
            return web.json_response({'success': False, 'error': 'Could not write the theme file.'}, status=500)
