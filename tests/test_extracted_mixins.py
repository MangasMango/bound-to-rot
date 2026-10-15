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

import ast
import builtins
import symtable
from pathlib import Path
from types import SimpleNamespace

import core.game  # Bind the established mixin composition before helper modules.
import core.hub as hub
import core.input as game_input
import pyray as rl


MODULES = [Path('core/hub.py'), Path('core/delve_flow.py'), Path('core/input.py')]
EXTRACTED = MODULES + list(Path('core/render').glob('*_render.py'))


def _module_names(path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update(alias.asname or alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(target.id for target in node.targets if isinstance(target, ast.Name))
    return names


def test_extracted_modules_have_no_unbound_module_globals():
    """Catch names accidentally lost when methods moved out of game.py."""
    for path in EXTRACTED:
        source = path.read_text(encoding='utf-8')
        module = symtable.symtable(source, str(path), 'exec')
        module_name = '.'.join(path.with_suffix('').parts)
        loaded = __import__(module_name, fromlist=['*'])
        bound = set(module.get_identifiers()) | set(dir(builtins)) | set(vars(loaded))
        missing = set()
        def visit(table):
            for symbol in table.get_symbols():
                if symbol.is_global() and symbol.get_name() not in bound:
                    missing.add(symbol.get_name())
            for child in table.get_children():
                visit(child)
        visit(module)
        assert not missing, f'{path}: unresolved module names {sorted(missing)}'


def test_enter_hub_constructs_layout_and_interactables(monkeypatch):
    game = SimpleNamespace()
    game.char = SimpleNamespace(perks={}, descend={}, looks='fighter', inventory={})
    game.inventory = game.char.inventory
    game.stats = {'health': 100.0}
    game._equipped_bonuses = lambda: {}
    game._build_hub_map = lambda: [['0']]
    game.iso = SimpleNamespace(set_path_cells=lambda cells: None, follow=lambda x, y: None)
    game.audio = SimpleNamespace(set_music_state=lambda state: None)
    game.inv = SimpleNamespace(on_drop_item=None)
    game._on_inv_drop = lambda *args: None
    game._sync_weather = lambda strength, seed: None

    monkeypatch.setattr(hub, 'compute_perk_bonuses', lambda *args, **kwargs: {})
    monkeypatch.setattr(hub, 'compute_derived_stats', lambda *args, **kwargs: {'max_health': 100.0, 'health': 100.0})
    monkeypatch.setattr(hub, 'reset_stats', lambda stats, **values: stats.update(values))
    monkeypatch.setattr(hub, 'make_inventory', lambda: {})
    monkeypatch.setattr(hub.rl, 'hide_cursor', lambda: None)
    monkeypatch.setattr(hub.rl, 'Color', lambda *args: tuple(args))

    hub.HubMixin._enter_hub(game)

    assert len(game._hub_objects) == len(hub._HUB_LAYOUT)
    assert game._hub_objects[0]['color'] == tuple(hub._HUB_LAYOUT[0]['color'])
    assert any(obj['type'] == 'delve' for obj in game._hub_objects)
    assert any(obj['type'] == 'stash' for obj in game._hub_objects)
    assert game._hub_lights == hub._HUB_LIGHTS


def test_input_dispatch_turns_key_press_into_inventory_intent(monkeypatch):
    game = SimpleNamespace()
    game.state = game_input.STATE_PLAYING
    game._delve = None
    game._minimap_open = False
    game._console_open = False
    game._char_stats_open = False
    game._combat_log_open = False
    game._update_mouse_transform = lambda: None
    game._update_game = lambda dt: None
    game.menu_sys = SimpleNamespace(
        settings=SimpleNamespace(volume=50, music_volume=50, debug_overlay=False),
        char_name_input=SimpleNamespace(push=lambda ch: None),
    )
    game.audio = SimpleNamespace(
        set_sfx_volume=lambda volume: None,
        set_music_volume=lambda volume: None,
        tick=lambda dt: None,
        inv_open=lambda: None,
        inv_close=lambda: None,
    )
    game.inv = SimpleNamespace(
        open=False, toggle=lambda: setattr(game.inv, 'open', True),
        update=lambda inventory, stats: None,
    )
    game.inventory = {}
    game.stats = {}
    monkeypatch.setattr(game_input.inp, 'key_pressed', lambda *args: args[-1] == rl.KEY_I)

    game_input.InputMixin.update(game, 1 / 30)

    assert game.inv.open is True


def test_mouse_dispatch_turns_right_click_into_move_intent(monkeypatch):
    game = SimpleNamespace(
        inv=SimpleNamespace(open=False), _minimap_open=False, px=1.0, py=1.0,
        map=[[0]], iso=SimpleNamespace(screen_to_world=lambda x, y, w, h: (3.0, 2.0)),
        attack_target=None, interact_target=None, drop_target=None,
        _drop_label_rects=[], _delve=None,
        _delve_chart_is_open=lambda: False,
        _hud_over_action=lambda x, y: False,
        _flash_hud=lambda action: None,
    )
    monkeypatch.setattr(game_input.inp, 'mouse_pressed',
                        lambda *args: args[-1] == rl.MOUSE_BUTTON_RIGHT)
    monkeypatch.setattr(game_input.rl, 'get_mouse_x', lambda: 10)
    monkeypatch.setattr(game_input.rl, 'get_mouse_y', lambda: 20)
    monkeypatch.setattr(game_input.rl, 'is_mouse_button_down', lambda button: False)

    handled = game_input.InputMixin._dispatch_game_mouse_input(game, 100, 100)

    assert handled is False
    assert (game.dest_col, game.dest_row) == (3.0, 2.0)
    assert game.click_marker == {'col': 3.0, 'row': 2.0, 'timer': 0.6}
