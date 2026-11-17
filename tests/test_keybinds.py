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

Covers:
  1. Defaults + fail-safe load: missing / corrupt / partial keybinds.json.
  2. set_key: success, persistence, conflict refusal, reserved Esc.
  3. reset_all restores every default.
  4. key_name display mapping; GEM_SLOT_ACTIONS covers the real gem slots.
  5. A call-site sweep: the swapped gameplay/menu keys are never sampled
     hardcoded again (they must go through keybinds.key(...)).
"""

import json
import os
from pathlib import Path

import pyray as rl
import pytest

from systems import gems
from systems import keybinds


# ── fixtures ───────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _fresh_registry(tmp_path, monkeypatch):
    """Isolate the module singleton: fresh state + tmp keybinds.json."""
    path = tmp_path / 'keybinds.json'
    monkeypatch.setattr(keybinds, 'KEYBINDS_PATH', str(path))
    keybinds._bindings = dict(keybinds.DEFAULTS)
    keybinds._loaded = False
    yield path
    keybinds._bindings = dict(keybinds.DEFAULTS)
    keybinds._loaded = False


# ── load / fail-safe ──────────────────────────────────────────────────

def test_missing_file_falls_back_to_defaults():
    keybinds.load()
    assert keybinds.key('reload') == rl.KEY_R
    assert keybinds.key('toggle_inventory') == rl.KEY_I


def test_corrupt_file_falls_back_to_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(keybinds, 'KEYBINDS_PATH', str(tmp_path / 'bad.json'))
    (tmp_path / 'bad.json').write_text('{not json')
    keybinds.load()
    assert keybinds.key('flask') == rl.KEY_T


def test_partial_payload_merges_per_action(tmp_path):
    path = tmp_path / 'keybinds.json'
    path.write_text(json.dumps({'bindings': {
        'reload': rl.KEY_K,
        'bogus_action': rl.KEY_J,          # unknown id - ignored
        'flask': 'not-an-int',             # bad value - falls back
    }}))
    keybinds.load()
    assert keybinds.key('reload') == rl.KEY_K
    assert keybinds.key('flask') == rl.KEY_T
    assert keybinds.key('toggle_inventory') == rl.KEY_I


def test_save_roundtrip(tmp_path):
    keybinds.load()
    assert keybinds.set_key('reload', rl.KEY_K)
    reloaded_path = tmp_path / 'keybinds.json'
    assert reloaded_path.exists()
    keybinds._loaded = False
    keybinds._bindings = dict(keybinds.DEFAULTS)
    keybinds.load()
    assert keybinds.key('reload') == rl.KEY_K


# ── set_key ────────────────────────────────────────────────────────────

def test_set_key_conflict_refused():
    keybinds.load()
    assert not keybinds.set_key('reload', rl.KEY_I)   # I is toggle_inventory's
    assert keybinds.key('reload') == rl.KEY_R
    assert keybinds.conflict_owner(rl.KEY_I) == 'Inventory'


def test_set_key_reserved_esc_refused():
    keybinds.load()
    assert not keybinds.set_key('reload', rl.KEY_ESCAPE)
    assert keybinds.key('reload') == rl.KEY_R


def test_set_key_unknown_action_refused():
    keybinds.load()
    assert not keybinds.set_key('does_not_exist', rl.KEY_K)


def test_swap_two_actions_releases_the_old_key():
    keybinds.load()
    assert keybinds.set_key('reload', rl.KEY_K)
    assert keybinds.set_key('flask', rl.KEY_R)   # R freed by the first swap
    assert keybinds.key('flask') == rl.KEY_R


# ── reset ──────────────────────────────────────────────────────────────

def test_reset_all_restores_defaults(tmp_path):
    keybinds.load()
    keybinds.set_key('reload', rl.KEY_K)
    keybinds.reset_all()
    assert keybinds.key('reload') == rl.KEY_R
    stored = json.loads((tmp_path / 'keybinds.json').read_text())
    assert stored['bindings']['reload'] == rl.KEY_R


# ── display helpers / slot wiring ──────────────────────────────────────

def test_key_name_display():
    assert keybinds.key_name(rl.KEY_Q) == 'Q'
    assert keybinds.key_name(rl.KEY_GRAVE) == 'GRAVE'
    assert keybinds.key_name(rl.KEY_F5) == 'F5'


def test_gem_slot_actions_cover_gem_slots():
    assert set(gems.GEM_SLOTS) == set(keybinds.GEM_SLOT_ACTIONS)
    for slot_id, action_id in keybinds.GEM_SLOT_ACTIONS.items():
        assert action_id in keybinds.DEFAULTS


def test_registry_covers_all_documented_keys():
    action_ids = {row[0] for row in keybinds.ACTIONS}
    assert {'gem_1', 'gem_2', 'gem_3', 'reload', 'flask', 'toggle_inventory',
            'char_stats', 'combat_log', 'anima_chart', 'chat_console',
            'debug_overlay', 'screenshot'} == action_ids


# ── call-site sweep ────────────────────────────────────────────────────

def test_swapped_sites_sample_keys_through_the_registry():
    """The rebindable action keys must never be sampled hardcoded again."""
    banned = {
        'core/input.py': ['KEY_I', 'KEY_C', 'KEY_L', 'KEY_T', 'KEY_R',
                          'KEY_GRAVE', 'KEY_F4', 'KEY_F5', "KEY_' +"],
        'core/hub.py':   ['KEY_I', 'KEY_C', 'KEY_L'],
    }
    for rel_path, tokens in banned.items():
        code_lines = [line.split('#')[0]
                      for line in Path(rel_path).read_text().splitlines()]
        src = '\n'.join(code_lines)
        for token in tokens:
            assert token not in src, f'{rel_path} still samples {token} hardcoded'
        assert 'keybinds.key(' in src, f'{rel_path} does not use the registry'


def test_chat_console_open_keys():
    """Issue #13 follow-up: the chat console opens on `/` (+ the Y / `
    alternates) and NEVER on Enter - Enter interacts with the item grids.
    An explicit rebind silences the alternates."""
    keybinds._bindings = dict(keybinds.DEFAULTS)
    keybinds._loaded = True
    keys = [keybinds.key_name(k) for k in keybinds.chat_open_keys()]
    assert keys == ['SLASH', 'Y', 'GRAVE']
    keybinds.set_key('chat_console', rl.KEY_K)
    keys = [keybinds.key_name(k) for k in keybinds.chat_open_keys()]
    assert keys == ['K']


def test_menus_own_the_keybind_ui():
    src = Path('ui/menus.py').read_text()
    assert '_d_keybinds_tab' in src
    assert 'reset_all' in src
    assert 'PRESS A KEY' in src
    assert '_keybinds.load()' in src
