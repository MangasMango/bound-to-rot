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

"""Owner inventory rules: one cell per item, socketing gems with a
right-click, and the QWER/T slot styling.

  1. EVERY item occupies exactly one inventory cell, including the organs that
     used to be 2x2 (lungs) and 2x3 (liver).
  2. A gem sitting in the character inventory grid can be socketed with the
      right-click context menu.
  3. QWER/T slots: the key label is always gray, a filled slot shows its real
     gem at full opacity, an empty slot shows a 0.3 alpha ghost of the gem or
     flask that belongs in it — and never a ghost behind a filled slot.

Ends with a draw smoke test that opens the inventory panel for a real
Character so the panel, socket and flask render paths all execute.
"""

from pathlib import Path
from types import SimpleNamespace

import pyray as rl

import systems.gems as gems
import systems.items as items
from entities.progression import Character
from ui import inventory_ui as inv_ui
from ui.inventory_ui import GRID_ACELL, GRID_AX, GRID_AY, InventoryUI


# ── helpers ────────────────────────────────────────────────────────────

def _headless(monkeypatch):
    """Neutralise every raylib draw call; capture rendered text + textures."""
    from ui import fonts as fonts_mod
    from ui import icons as icons_mod
    rendered = []
    textures = []
    monkeypatch.setattr(rl, 'get_mouse_x', lambda: -1)
    monkeypatch.setattr(rl, 'get_mouse_y', lambda: -1)
    monkeypatch.setattr(rl, 'get_time', lambda: 0.0)
    monkeypatch.setattr(rl, 'get_frame_time', lambda: 0.016)
    monkeypatch.setattr(rl, 'get_screen_width', lambda: 1280)
    monkeypatch.setattr(rl, 'get_screen_height', lambda: 720)
    monkeypatch.setattr(rl, 'is_mouse_button_pressed', lambda _b: False)
    monkeypatch.setattr(rl, 'check_collision_point_rec', lambda *_a: False)
    for name in ('draw_rectangle', 'draw_rectangle_rec', 'draw_rectangle_lines',
                 'draw_rectangle_lines_ex', 'draw_rectangle_gradient_ex',
                 'draw_circle', 'draw_circle_v', 'draw_ellipse',
                 'draw_ellipse_lines', 'draw_line', 'draw_line_ex',
                 'draw_poly', 'draw_triangle', 'draw_texture',
                 'begin_texture_mode', 'end_texture_mode',
                 'begin_blend_mode', 'end_blend_mode',
                 'begin_scissor_mode', 'end_scissor_mode'):
        if hasattr(rl, name):
            monkeypatch.setattr(rl, name, lambda *a, **k: None)
    monkeypatch.setattr(rl, 'draw_texture_pro',
                        lambda tex, *a, **k: textures.append((tex, a)))
    monkeypatch.setattr(fonts_mod, 'draw',
                        lambda text, *a, **k: rendered.append(str(text)))
    monkeypatch.setattr(fonts_mod, 'measure',
                        lambda text, size: len(text) * size)
    monkeypatch.setattr(icons_mod, 'draw', lambda *a, **k: None)
    return rendered, textures


class _FakeTexture(SimpleNamespace):
    """Stand-in for a raylib Texture as far as the draw code is concerned."""


def _fake_tex(name):
    return _FakeTexture(id=1, width=64, height=64, name=name)


def _ui_with_icons():
    ui = InventoryUI()
    ui._err = _fake_tex('error')
    for item_id in items.ITEMS:
        ui._icons[item_id] = _fake_tex(item_id)
    ui._stash_grid = None
    return ui


def _grid_entry(item_id, col=0, row=0, ilvl=5, identified=True):
    return {'item': item_id, 'count': 1, 'col': col, 'row': row,
            'instance_data': {'rarity': 'common', 'ilvl': ilvl,
                              'identified': identified, 'affixes': {}}}


# ── rule 1: every item occupies one cell ────────────────────────────────

def test_every_item_is_one_cell():
    """Owner rule: no item spans more than one grid cell."""
    for item_id, defn in items.ITEMS.items():
        assert tuple(defn.get('size', (1, 1))) == (1, 1), item_id


def test_organs_are_one_cell():
    assert items.item_size('lungs') == (1, 1)
    assert items.item_size('liver') == (1, 1)


def test_liver_places_in_a_single_free_cell():
    """A (2,3) liver used to be unplaceable in the last row; at 1x1 it is."""
    inv = items.make_inventory()
    grid = []
    # fill the whole 8x4 inventory grid except the final cell
    for row in range(items.INV_ROWS):
        for col in range(items.INV_COLS - 1):
            grid.append(_grid_entry('heart', col, row))
    slot = _grid_entry('liver', 0, items.INV_ROWS - 1)
    gmap = items.grid_build_map(grid, cols=items.INV_COLS, rows=items.INV_ROWS)
    occupied = [(c, r) for r in range(items.INV_ROWS)
                for c in range(items.INV_COLS) if gmap[r][c] is not None]
    assert (items.INV_COLS - 1, items.INV_ROWS - 1) not in occupied
    assert items.grid_can_place(grid, 'liver', items.INV_COLS - 1,
                                items.INV_ROWS - 1,
                                cols=items.INV_COLS, rows=items.INV_ROWS)
    assert items.grid_can_place(grid, 'lungs', items.INV_COLS - 1,
                                items.INV_ROWS - 1,
                                cols=items.INV_COLS, rows=items.INV_ROWS)
    assert slot['item'] == 'liver'


def test_organ_occupies_exactly_one_cell_in_the_map():
    grid = []
    items.grid_auto_place_instance(grid, _grid_entry('lungs', 0, 0),
                                   cols=items.INV_COLS, rows=items.INV_ROWS)
    items.grid_auto_place_instance(grid, _grid_entry('liver', 0, 0),
                                   cols=items.INV_COLS, rows=items.INV_ROWS)
    gmap = items.grid_build_map(grid, cols=items.INV_COLS, rows=items.INV_ROWS)
    filled = [(c, r) for r in range(items.INV_ROWS)
              for c in range(items.INV_COLS) if gmap[r][c] is not None]
    assert filled == [(0, 0), (1, 0)]


def test_organ_grid_hit_test_is_single_cell():
    """Hit-testing must only claim the one cell the organ was placed on."""
    ui = _ui_with_icons()
    inv = items.make_inventory()
    inv['grid'] = []
    items.grid_auto_place_instance(inv['grid'], _grid_entry('lungs', 0, 0),
                                   cols=items.INV_COLS, rows=items.INV_ROWS)
    px, s = ui._panel(1280, 720)
    cell = max(8, int(round(GRID_ACELL * s)))
    gx = int(round(px + GRID_AX * s))
    gy = int(round(GRID_AY * s))
    hit = ui._grid_hit(gx + cell // 2, gy + cell // 2, inv, px, s)
    assert hit is not None and hit['slot']['item'] == 'lungs'
    # the cell to the right is empty even though lungs used to be 2x2
    assert ui._grid_hit(gx + cell + cell // 2, gy + cell // 2, inv, px, s) is None
    # the cell below is empty too (liver used to be 2x3 tall)
    assert ui._grid_hit(gx + cell // 2, gy + cell + cell // 2, inv, px, s) is None


def test_organ_grid_draws_as_one_cell(monkeypatch):
    """The grid draw path renders lungs with a 1x1 footprint."""
    _headless(monkeypatch)
    ui = _ui_with_icons()
    inv = items.make_inventory()
    inv['grid'] = [_grid_entry('lungs', 0, 0)]
    px, s = ui._panel(1280, 720)
    cell = max(8, int(round(GRID_ACELL * s)))
    gx = int(round(px + GRID_AX * s))
    gy = int(round(GRID_AY * s))
    # hovering the organ (its only cell) sets the hover tooltip source
    ui._hovered = None
    ui._draw_grid(inv, px, s, gx + cell // 2, gy + cell // 2)
    assert ui._hovered['item'] == 'lungs'
    # and the neighbouring cell is not part of the footprint
    ui._hovered = None
    ui._draw_grid(inv, px, s, gx + cell + cell // 2, gy + cell // 2)
    assert ui._hovered is None


# ── rule 2: a gem in the grid can be socketed from the context menu ────

def test_context_menu_offers_socket_for_a_grid_gem():
    ui = _ui_with_icons()
    inv = items.make_inventory()
    inv['grid'] = [_grid_entry('gem_blue')]
    ui._ctx = {'x': 0, 'y': 0, 'source': 'grid', 'index': 0,
               'slot': inv['grid'][0]}
    ui._inventory_for_menu = inv['grid']
    ui._inventory_for_ctx = inv
    labels = [o['label'] for o in ui._ctx_options()]
    assert 'SOCKET (Q)' in labels


def test_context_menu_socket_disabled_when_slot_occupied():
    ui = _ui_with_icons()
    inv = items.make_inventory()
    inv['grid'] = [_grid_entry('gem_blue')]
    inv['gem_sockets']['Q'] = {'item': 'gem_blue', 'count': 1}
    ui._ctx = {'x': 0, 'y': 0, 'source': 'grid', 'index': 0,
               'slot': inv['grid'][0]}
    ui._inventory_for_menu = inv['grid']
    ui._inventory_for_ctx = inv
    opt = next(o for o in ui._ctx_options() if o['type'] == 'socket')
    assert opt['enabled'] is False
    assert 'occupied' in opt['label']


def test_context_menu_has_no_socket_for_a_non_gem():
    ui = _ui_with_icons()
    inv = items.make_inventory()
    inv['grid'] = [_grid_entry('heart')]
    ui._ctx = {'x': 0, 'y': 0, 'source': 'grid', 'index': 0,
               'slot': inv['grid'][0]}
    ui._inventory_for_menu = inv['grid']
    ui._inventory_for_ctx = inv
    assert not any(o['type'] == 'socket' for o in ui._ctx_options())


def test_socket_from_grid_places_the_gem_in_its_own_slot():
    inv = items.make_inventory()
    inv['grid'] = [_grid_entry('gem_blue', col=2, row=1, ilvl=17)]
    assert items.socket_gem_from_grid(inv, 0) is True
    assert inv['gem_sockets']['Q']['item'] == 'gem_blue'
    assert inv['gem_sockets']['Q']['instance_data']['ilvl'] == 17
    assert inv['grid'] == []


def test_socket_refuses_an_occupied_slot():
    inv = items.make_inventory()
    inv['grid'] = [_grid_entry('gem_green', col=1, row=0)]
    inv['gem_sockets']['W'] = {'item': 'gem_green', 'count': 1,
                               'instance_data': {'ilvl': 3}}
    assert items.socket_gem_from_grid(inv, 0) is False
    # the existing gem and the grid entry are both untouched
    assert inv['gem_sockets']['W']['instance_data']['ilvl'] == 3
    assert len(inv['grid']) == 1
    assert inv['grid'][0]['item'] == 'gem_green'


def test_socket_refuses_the_wrong_colour():
    """A blue gem cannot go into W/E/R — the colour maps to exactly one key."""
    inv = items.make_inventory()
    inv['grid'] = [_grid_entry('gem_blue', col=0, row=0)]
    assert items.socket_gem_from_grid(inv, 0, dest_key='W') is False
    assert items.socket_gem_from_grid(inv, 0, dest_key='E') is False
    assert items.socket_gem_from_grid(inv, 0, dest_key='R') is False
    assert all(inv['gem_sockets'][k] is None for k in ('Q', 'W', 'E', 'R'))
    assert len(inv['grid']) == 1


def test_socket_gem_never_overwrites_another_slot():
    inv = items.make_inventory()
    inv['grid'] = [_grid_entry('gem_red', col=0, row=0)]
    inv['gem_sockets']['E'] = {'item': 'gem_red', 'count': 1}
    assert items.socket_gem_from_grid(inv, 0) is False
    assert inv['gem_sockets']['Q'] is None


def test_delve_gem_can_be_equipped_with_right_click_alone(monkeypatch):
    """End-to-end: a gem found in the delve, right-clicked, is socketed."""
    inv = items.make_inventory()
    inv['grid'] = []
    looted = gems.random_gem_slot('Q', 12, seed=7)
    items.grid_auto_place_instance(inv['grid'], looted,
                                   cols=items.INV_COLS, rows=items.INV_ROWS)
    assert inv['grid'][0]['item'] == 'gem_blue'

    changed = []
    ui = _ui_with_icons()
    ui.on_gear_change = lambda: changed.append(1)
    idx = 0
    ui._ctx = {'x': 10, 'y': 10, 'source': 'grid', 'index': idx,
               'slot': inv['grid'][idx]}
    ui._inventory_for_menu = inv['grid']
    ui._inventory_for_ctx = inv

    opt = next(o for o in ui._ctx_options() if o['type'] == 'socket')
    ui._exec({**opt, 'source': 'grid', 'index': idx}, inv, {})

    assert inv['gem_sockets']['Q']['item'] == 'gem_blue'
    assert inv['grid'] == []
    assert changed, 'socketing must notify the gear-change listener'


def test_socketed_gem_grants_the_ability():
    inv = items.make_inventory()
    inv['grid'] = [gems.random_gem_slot('W', 10, seed=3)]
    before = gems.socketed_ability(inv, 'W')
    assert before is None
    items.socket_gem_from_grid(inv, 0)
    found = gems.socketed_ability(inv, 'W')
    assert found is not None and found[1].get('label')


# ── rule 3: QWER + T slot styling ──────────────────────────────────────

def _socket_render(monkeypatch, sockets, flask=None):
    rendered, textures = _headless(monkeypatch)
    ui = _ui_with_icons()
    inv = items.make_inventory()
    inv['gem_sockets'] = dict(sockets)
    inv['flask_slot'] = flask
    px, s = ui._panel(1280, 720)
    ui._draw_sockets(inv, px, s, -1, -1)
    ui._draw_flask_socket(inv, px, s, -1, -1)
    return ui, rendered, textures


def _ghost_alpha():
    return int(round(255 * inv_ui.GHOST_ALPHA))


def _alpha(color):
    """Alpha of a draw tint — pyray exposes some constants as plain tuples."""
    if isinstance(color, (tuple, list)):
        return color[3]
    return color.a


def test_gem_key_colour_palette_is_unchanged_for_the_border():
    """The socket border still carries the slot colour; only the letter is gray."""
    assert set(inv_ui.GEM_KEY_COLOR) == set(gems.GEM_SLOTS)
    gray = inv_ui.GEM_KEY_GRAY
    assert gray[0] == gray[1] == gray[2], 'the key label colour must be gray'
    assert gray != inv_ui.GEM_KEY_COLOR['W']


def test_empty_sockets_draw_gray_keys_and_dimmed_ghosts(monkeypatch):
    sockets = {'Q': None, 'W': None, 'E': None, 'R': None}
    ui, rendered, textures = _socket_render(monkeypatch, sockets)
    for key in ('Q', 'W', 'E', 'R'):
        assert key in rendered
    # one ghost per socket, each showing the gem that belongs in that key
    for key in ('Q', 'W', 'E', 'R'):
        ghost = ui._icons[gems.GEM_ITEM_FOR_SLOT[key]]
        assert any(t is ghost and _alpha(a[-1]) == _ghost_alpha()
                   for t, a in textures), key


def test_filled_socket_draws_the_real_gem_and_no_ghost(monkeypatch):
    sockets = {'Q': gems.random_gem_slot('Q', 5, seed=1), 'W': None,
               'E': None, 'R': None}
    ui, rendered, textures = _socket_render(monkeypatch, sockets)
    blue = ui._icons['gem_blue']
    blue_calls = [a for t, a in textures if t is blue]
    assert blue_calls, 'the socketed blue gem must be drawn'
    assert all(_alpha(a[-1]) != _ghost_alpha() for a in blue_calls), \
        'a filled slot must not draw the ghost behind the real gem'
    # the empty sockets still ghost their own colour
    for key in ('W', 'E', 'R'):
        ghost = ui._icons[gems.GEM_ITEM_FOR_SLOT[key]]
        assert any(t is ghost and _alpha(a[-1]) == _ghost_alpha() for t, a in textures)


def test_ghosted_socket_is_still_clickable_and_hoverable(monkeypatch):
    """A ghosted slot keeps its hit rect (clicking casts nothing, but no crash)."""
    ui, rendered, textures = _socket_render(
        monkeypatch, {'Q': None, 'W': None, 'E': None, 'R': None})
    inv = items.make_inventory()
    px, s = ui._panel(1280, 720)
    for i, key in enumerate(inv_ui.GEM_KEYS):
        r = ui._socket_rect(px, s, i)
        hit = ui._slot_at(int(r.x + r.width / 2), int(r.y + r.height / 2),
                          inv, px, s)
        assert hit == {'source': 'gems', 'index': key, 'slot': None}


def test_empty_flask_slot_draws_the_flask_ghost(monkeypatch):
    ui, rendered, textures = _socket_render(
        monkeypatch, {'Q': None, 'W': None, 'E': None, 'R': None}, flask=None)
    flask_art = ui._icons[inv_ui.GHOST_FLASK_ITEM]
    assert any(t is flask_art and _alpha(a[-1]) == _ghost_alpha() for t, a in textures)
    assert 'T' in rendered


def test_filled_flask_slot_draws_no_ghost(monkeypatch):
    flask = {'item': 'flask_health', 'count': 1, 'charges': 1}
    ui, rendered, textures = _socket_render(
        monkeypatch, {'Q': None, 'W': None, 'E': None, 'R': None}, flask=flask)
    art = ui._icons['flask_health']
    for _t, a in textures:
        if _alpha(a[-1]) == _ghost_alpha():
            assert getattr(_t, 'name', None) != 'flask_health', \
                'a filled T slot must not ghost the flask art'


def test_socket_draw_uses_the_gray_label_not_the_gem_colour():
    src = Path('ui/inventory_ui.py').read_text(encoding='utf-8')
    body = src.split('def _draw_sockets', 1)[1].split('\n    def ', 1)[0]
    assert 'GEM_KEY_COLOR[key]' in body      # border keeps the slot identity
    assert 'rl.Color(*GEM_KEY_GRAY)' in body  # the letter is gray
    assert 'GHOST_ALPHA' not in body          # ghosts go through the helper
    assert 'def _draw_ghost_icon' in src


# ── draw smoke: the whole panel, with a real character ─────────────────

def test_inventory_draw_smoke_with_real_character_runs_socket_paths(monkeypatch):
    """Open the panel for a real Character and draw one full frame.

    Exercises the panel, the gem socket and the flask slot render paths for
    both the filled and the empty case, so a regression in any of them fails
    here instead of at runtime.
    """
    rendered, textures = _headless(monkeypatch)
    char = Character('smoke-char', 'Smoke Tester', 'fighter')
    inv = items.make_inventory()
    char.inventory = inv
    inv['grid'] = [_grid_entry('lungs', col=0, row=0),
                   _grid_entry('gem_blue', col=1, row=0)]
    inv['gem_sockets']['Q'] = None
    inv['gem_sockets']['R'] = {'item': 'gem_white', 'count': 1,
                               'instance_data': {'rarity': 'rare', 'ilvl': 9,
                                                 'identified': True,
                                                 'ability': 'cone_physical'}}
    inv['flask_slot'] = None

    ui = _ui_with_icons()
    ui.char_provider = lambda: char
    ui.open = True
    ui.stash_open = False
    ui._stash_grid = None
    ui.draw(inv, 1280, 720)

    for key in ('Q', 'W', 'E', 'R'):
        assert key in rendered, f'socket key {key} was not drawn'
    # the empty sockets ghosted, the filled one drew its real white gem
    for key in ('Q', 'W', 'E'):
        ghost = ui._icons[gems.GEM_ITEM_FOR_SLOT[key]]
        assert any(t is ghost and _alpha(a[-1]) == _ghost_alpha()
                   for t, a in textures), key
    white = ui._icons['gem_white']
    assert any(t is white and _alpha(a[-1]) == 255 for t, a in textures), \
        'the socketed white gem must be drawn at full opacity'
    flask_art = ui._icons[inv_ui.GHOST_FLASK_ITEM]
    assert any(t is flask_art and _alpha(a[-1]) == _ghost_alpha()
               for t, a in textures)
    # and the one-cell organs really rendered
    assert any(t is ui._icons['lungs'] for t, _a in textures)


# ── the LIVE click pipeline: InventoryUI.update() drives everything ─────

class _Mouse:
    """Controllable cursor position for the panel geometry."""
    def __init__(self):
        self.x = 0
        self.y = 0


class _Clicks:
    """Rising-edge queue standing in for systems.input.mouse_pressed.

    Tests feed one button edge; the next update() consumes it, and all
    later calls report False — exactly what the real edge detector counts
    with the 30 Hz fixed timestep.
    """
    def __init__(self):
        self.queue = []

    def feed(self, button):
        self.queue.append(button)

    def __call__(self, consumer, button):
        if button in self.queue:
            self.queue.remove(button)
            return True
        return False


def _screen_cell(ui, col, row):
    """Cursor coords for the centre of a backpack grid cell."""
    px, s = ui._panel(1280, 720)
    return (px + (GRID_AX + (col + 0.5) * GRID_ACELL) * s,
            (GRID_AY + (row + 0.5) * GRID_ACELL) * s)


def _screen_socket(ui, i):
    """Cursor coords for the centre of socket i (0=Q, 1=W, 2=E, 3=R)."""
    px, s = ui._panel(1280, 720)
    r = ui._socket_rect(px, s, i)
    return (r.x + r.width / 2, r.y + r.height / 2)


def _pipeline(monkeypatch, clicks, mouse):
    _headless(monkeypatch)
    monkeypatch.setattr(rl, 'get_mouse_x', lambda: mouse.x)
    monkeypatch.setattr(rl, 'get_mouse_y', lambda: mouse.y)
    import ui.inventory_ui as inv_mod
    monkeypatch.setattr(inv_mod.inp, 'mouse_pressed', clicks)
    return inv_mod


def test_live_click_pipeline_sockets_green_gem_into_W(monkeypatch):
    """End-to-end through update(): right-click a grid gem, left-click the
    SOCKET (W) offer — the W socket takes the gem and the grid entry is
    consumed. No direct _ctx injection."""
    mouse, clicks = _Mouse(), _Clicks()
    _pipeline(monkeypatch, clicks, mouse)

    ui = _ui_with_icons()
    ui.open = True
    inv = items.make_inventory()
    inv['grid'] = [_grid_entry('gem_green', col=1, row=2)]

    mouse.x, mouse.y = _screen_cell(ui, 1, 2)
    clicks.feed(rl.MOUSE_BUTTON_RIGHT)
    ui.update(inv, {})
    assert ui._ctx is not None, 'right-clicking the gem must open the menu'
    assert ui._ctx['source'] == 'grid' and ui._ctx['index'] == 0

    sidx = next(i for i, o in enumerate(ui._ctx_options())
                if o['type'] == 'socket' and o['enabled'] and 'W' in o['label'])
    mouse.x = ui._ctx['x'] + 110
    mouse.y = ui._ctx['y'] + 2 + sidx * 26 + 13
    clicks.feed(rl.MOUSE_BUTTON_LEFT)
    ui.update(inv, {})

    assert ui._ctx is None
    assert inv['gem_sockets']['W'] is not None
    assert inv['gem_sockets']['W']['item'] == 'gem_green'
    assert inv['grid'] == []


def test_live_click_pipeline_removes_a_socketed_gem(monkeypatch):
    """End-to-end through update(): right-click the W socket, left-click
    REMOVE — the gem returns to the backpack and the socket empties."""
    mouse, clicks = _Mouse(), _Clicks()
    _pipeline(monkeypatch, clicks, mouse)

    ui = _ui_with_icons()
    ui.open = True
    inv = items.make_inventory()
    inv['gem_sockets']['W'] = _grid_entry('gem_green')

    mouse.x, mouse.y = _screen_socket(ui, 1)
    clicks.feed(rl.MOUSE_BUTTON_RIGHT)
    ui.update(inv, {})
    assert ui._ctx is not None, 'right-clicking the W socket must open the menu'
    assert ui._ctx['source'] == 'gems' and ui._ctx['index'] == 'W'

    ridx = next(i for i, o in enumerate(ui._ctx_options())
                if o['type'] == 'remove_gem')
    mouse.x = ui._ctx['x'] + 110
    mouse.y = ui._ctx['y'] + 2 + ridx * 26 + 13
    clicks.feed(rl.MOUSE_BUTTON_LEFT)
    ui.update(inv, {})

    assert ui._ctx is None
    assert inv['gem_sockets']['W'] is None
    assert any(e['item'] == 'gem_green' for e in inv['grid'])


def test_remove_gem_into_full_backpack_keeps_the_gem(monkeypatch):
    """Full backpack: sockets are never silently emptied — the gem stays
    and the panel shows 'Backpack full!' (regression: the auto-place
    result used to be ignored and the gem was destroyed)."""
    _headless(monkeypatch)
    ui = _ui_with_icons()
    ui.open = True
    inv = items.make_inventory()
    n_cells = items.INV_COLS * items.INV_ROWS
    inv['grid'] = [_grid_entry('health_potion', col=c % items.INV_COLS,
                               row=c // items.INV_COLS)
                   for c in range(n_cells)]
    inv['gem_sockets']['W'] = _grid_entry('gem_green')
    ui._exec({'type': 'remove_gem', 'source': 'gems', 'index': 'W'}, inv, {})

    assert inv['gem_sockets']['W'] is not None
    assert inv['gem_sockets']['W']['item'] == 'gem_green'
    assert len(inv['grid']) == n_cells
    assert ui._notice == 'Backpack full!'


