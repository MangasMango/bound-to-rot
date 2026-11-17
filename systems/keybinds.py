# Copyright (C) 2026 MangasMango
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Rebindable keybindings (issue #14).

A module-level registry of rebindable ACTION keys with a JSON persistence
file (``keybinds.json``) next to ``settings.json``. Call sites sample keys
through :func:`key`::

    if inp.key_pressed(self, keybinds.key('reload')):

The per-consumer edges in ``systems/input.py`` are keyed by the raw key
constant, so rebinding changes WHICH constant is sampled - the edge
machinery itself needs no changes. Navigation keys (Esc / Enter / arrows /
backspace) stay hardcoded: this system covers action and menu keys only,
and movement stays right-click (owner scope, issue #14).

Gem slots keep their save-schema ids ('Q' / 'W' / 'E' in ``gem_sockets``);
``GEM_SLOT_ACTIONS`` maps a slot id to its rebindable action so rebinding
never touches save data.
"""

import json
import os
import traceback

import pyray as rl

_SAVE_DIR      = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'BTR')
KEYBINDS_PATH  = os.path.join(_SAVE_DIR, 'keybinds.json')

# ── action registry ───────────────────────────────────────────────────
# (action_id, label, default_key, group). 'gameplay' actions fire during a
# delve; 'interface' actions toggle screens/tools. Membership is data -
# the Controls tab renders straight from this table.

ACTIONS = (
    ('gem_1',           'Gem Ability 1',        rl.KEY_Q,    'gameplay'),
    ('gem_2',           'Gem Ability 2',        rl.KEY_W,    'gameplay'),
    ('gem_3',           'Gem Ability 3',        rl.KEY_E,    'gameplay'),
    ('reload',          'Reload',               rl.KEY_R,    'gameplay'),
    ('flask',           'Flask',                rl.KEY_T,    'gameplay'),
    ('toggle_inventory','Inventory',            rl.KEY_I,    'interface'),
    ('char_stats',      'D.E.S.C.E.N.D. Panel', rl.KEY_C,    'interface'),
    ('combat_log',      'Combat Log',           rl.KEY_L,    'interface'),
    ('anima_chart',     'Anima Chart',          rl.KEY_TAB,  'interface'),
    ('chat_console',    'Chat Console',         rl.KEY_GRAVE,'interface'),
    ('debug_overlay',   'Debug Overlay',        rl.KEY_F4,   'interface'),
    ('screenshot',      'Screenshot',           rl.KEY_F5,   'interface'),
)

DEFAULTS = {action_id: key for action_id, _label, key, _grp in ACTIONS}

ACTION_GROUPS = ('gameplay', 'interface')

# Save-schema slot ids (systems/gems.GEM_SLOTS / inventory GEM_KEYS) → the
# rebindable action that drives the slot. Slot ids NEVER change.
GEM_SLOT_ACTIONS = {'Q': 'gem_1', 'W': 'gem_2', 'E': 'gem_3'}

# ── module state (settings.json-style singleton) ──────────────────────
_bindings: dict[str, int] = dict(DEFAULTS)
_loaded:   bool           = False


def load(path: str | None = None) -> None:
    """Load ``keybinds.json`` over the defaults, falling back per action.

    A missing file is the normal first-boot case. A corrupt file or unknown
    values never crash: unknown action ids are ignored and invalid key
    values fall back to that action's default (settings-style fail-safe)."""
    global _bindings, _loaded
    path = path or KEYBINDS_PATH
    try:
        with open(path) as f:
            data = json.load(f)
        stored = data.get('bindings', data) if isinstance(data, dict) else {}
        merged = dict(DEFAULTS)
        if isinstance(stored, dict):
            for action_id, key in stored.items():
                if action_id in DEFAULTS and isinstance(key, int):
                    merged[action_id] = key
        _bindings = merged
    except FileNotFoundError:
        _bindings = dict(DEFAULTS)
    except Exception:
        # corrupt payload - defaults win, never crash the boot
        print("[keybinds] ERROR: Failed to load keybinds.json")
        traceback.print_exc()
        _bindings = dict(DEFAULTS)
    _loaded = True


def save(path: str | None = None) -> None:
    """Persist the current bindings (same directory as settings.json)."""
    path = path or KEYBINDS_PATH
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump({'bindings': dict(_bindings)}, f)
    except Exception:
        print("[keybinds] ERROR: Failed to save keybinds.json")
        traceback.print_exc()


def _ensure_loaded() -> None:
    """Import-time safety net: the registry always answers, even if a boot
    path forgot to call :func:`load` (then defaults are in force)."""
    if not _loaded:
        load()


def key(action_id: str) -> int:
    """The raylib key constant currently bound to ``action_id``."""
    _ensure_loaded()
    return _bindings.get(action_id, DEFAULTS.get(action_id, 0))


def binding(action_id: str) -> int | None:
    """The raw stored binding, or None for an unknown action id."""
    _ensure_loaded()
    return _bindings.get(action_id) if action_id in DEFAULTS else None


def set_key(action_id: str, key_constant: int) -> bool:
    """Bind ``action_id`` to ``key_constant``; refuses conflicts.

    Returns False (registry unchanged) when the action is unknown, the key
    is not a usable constant, or another action already holds the key."""
    _ensure_loaded()
    if action_id not in DEFAULTS:
        return False
    if not key_constant or key_constant == rl.KEY_ESCAPE:
        return False   # Esc is the universal cancel/close key - reserved
    for other_id, bound in _bindings.items():
        if other_id != action_id and bound == key_constant:
            return False
    _bindings[action_id] = key_constant
    save()
    return True


def conflict_owner(key_constant: int) -> str | None:
    """Label of the action already bound to ``key_constant``, if any."""
    _ensure_loaded()
    for action_id, bound in _bindings.items():
        if bound == key_constant:
            return action_label(action_id)
    return None


def reset_all() -> None:
    """Restore every action to its default key and persist."""
    global _bindings
    _ensure_loaded()
    _bindings = dict(DEFAULTS)
    save()


# ── display helpers ───────────────────────────────────────────────────

def action_label(action_id: str) -> str:
    """Human label of an action ('Reload', 'Gem Ability 2', ...)."""
    for row_id, label, _key, _grp in ACTIONS:
        if row_id == action_id:
            return label
    return action_id


def action_group(action_id: str) -> str:
    for row_id, _label, _key, grp in ACTIONS:
        if row_id == action_id:
            return grp
    return 'interface'


_KEY_NAMES: dict[int, str] = {}


def _key_name_map() -> dict[int, str]:
    """Reverse map of raylib KEY_* constants → short display names,
    built once from the pyray module (deterministic: dir() is sorted)."""
    global _KEY_NAMES
    if not _KEY_NAMES:
        for name in dir(rl):
            if name.startswith('KEY_') and isinstance(getattr(rl, name), int):
                _KEY_NAMES.setdefault(getattr(rl, name), name[len('KEY_'):])
    return _KEY_NAMES


def key_name(key_constant: int) -> str:
    """Short display name of a key constant ('Q', 'F5', 'GRAVE', 'TAB')."""
    return _key_name_map().get(key_constant, '?')


def key_name_compact(key_constant: int) -> str:
    """Very short name for HUD slot letters (single char when possible)."""
    name = key_name(key_constant)
    aliases = {'GRAVE': '`', 'SPACE': 'SP', 'TAB': 'TB',
               'LEFT_CONTROL': 'CT', 'RIGHT_CONTROL': 'CT',
               'LEFT_SHIFT': 'SH', 'RIGHT_SHIFT': 'SH',
               'LEFT_ALT': 'AL', 'RIGHT_ALT': 'AL'}
    return aliases.get(name, name[:2])
