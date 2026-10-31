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

"""Blacksmith dismantle forge (BLUEPRINT §24): recipes, sell table, UI flow.

Covers:
  * the sell table — organs (identified or not), gems and potions pay
    Joker quarters by rarity (x stack count), flasks pay flat, cards pay
    1 per card; only zero-value junk refuses;
  * the item recipes — organ ascension chains, the Queen of Hearts cleanse
    income, the gem tier-up;
  * the InventoryUI forge flow — DISMANTLE / TAKE context moves, the
    dismantle execution, leftover return on close (never a lost item).
"""

import random

import pytest
import pyray as rl

import systems.currency as currency
import systems.items as items
import systems.recipes as recipes
from ui.inventory_ui import (InventoryUI, FBG_AX, FBG_AY,
                             forge_panel_scale, forge_cell_px)


# ── helpers ───────────────────────────────────────────────────────────

def _organ(slot='heart', rarity='common', ilvl=5, identified=False):
    """A grid slot carrying an organ instance."""
    return {
        'item': slot,
        'count': 1,
        'col': 0, 'row': 0,
        'instance_data': {
            'rarity': rarity,
            'display_name': f'{slot} of the Forge',
            'ilvl': ilvl,
            'identified': identified,
            'affixes': {'prefixes': {}, 'suffixes': {}},
        },
    }


def _gem(color='blue', rarity='uncommon', ilvl=3):
    """A grid slot carrying an ability gem (always identified)."""
    return {
        'item': f'gem_{color}',
        'count': 1,
        'col': 0, 'row': 0,
        'instance_data': {
            'rarity': rarity,
            'display_name': 'Dash',
            'ilvl': ilvl,
            'identified': True,
            'ability': 'dash',
        },
    }


def _forge_ui():
    ui = InventoryUI()
    ui.open = True
    ui.open_forge()
    return ui


def _quarter_total(match):
    """Sum of Joker quarters across a match's output slots."""
    total = 0
    for group in match['groups']:
        for out in group['outputs']:
            if currency.arcana_of(out['item']) == 0:
                total += out['count']
    return total


def _cell_center_px(col, row):
    """Screen pixel of the centre of forge offerings cell (col,row) at 720p."""
    s = forge_panel_scale(720)
    cell = forge_cell_px(720)
    return (int(FBG_AX * s) + col * cell + cell // 2,
            int(FBG_AY * s) + row * cell + cell // 2)


# ── headless draw fixture ─────────────────────────────────────────────

@pytest.fixture()
def headless_draw(monkeypatch):
    """Silence every raylib draw/query call and the font/icon layers."""
    for name in ('draw_texture_pro', 'draw_rectangle', 'draw_rectangle_rec',
                 'draw_rectangle_lines', 'draw_rectangle_lines_ex',
                 'draw_rectangle_gradient_ex', 'draw_circle', 'draw_circle_v',
                 'draw_ellipse', 'draw_ellipse_lines', 'draw_line',
                 'draw_line_ex', 'draw_poly', 'draw_triangle',
                 'check_collision_point_rec', 'is_mouse_button_pressed',
                 'is_mouse_button_down'):
        monkeypatch.setattr(rl, name, lambda *a, **k: None)
    monkeypatch.setattr(rl, 'get_screen_width', lambda: 1280)
    monkeypatch.setattr(rl, 'get_screen_height', lambda: 720)
    monkeypatch.setattr(rl, 'get_mouse_x', lambda: -1)
    monkeypatch.setattr(rl, 'get_mouse_y', lambda: -1)
    monkeypatch.setattr(rl, 'get_frame_time', lambda: 0.0)
    monkeypatch.setattr(rl, 'get_time', lambda: 0.0)
    import ui.fonts as fonts_mod
    import ui.icons as icons_mod
    monkeypatch.setattr(fonts_mod, 'draw', lambda *a, **k: None)
    monkeypatch.setattr(fonts_mod, 'measure',
                        lambda text, size: len(text) * size)
    monkeypatch.setattr(icons_mod, 'draw', lambda *a, **k: None)
    return True


# ── the sell table (§24.225) ──────────────────────────────────────────

@pytest.mark.parametrize('rarity,quarters', [
    ('common', 1), ('uncommon', 2), ('rare', 4),
    ('epic', 6), ('legendary', 8), ('mythic', 12),
])
def test_unidentified_organs_sell_by_rarity(rarity, quarters):
    entry = _organ(rarity=rarity)
    assert recipes.sell_quarters_for(entry) == quarters
    match = recipes.match_forge([entry])
    assert _quarter_total(match) == quarters
    assert match['confirm'] == (rarity in recipes.SELL_CONFIRM_RARITIES)


@pytest.mark.parametrize('rarity,quarters', [
    ('common', 1), ('uncommon', 2), ('rare', 4),
    ('epic', 6), ('legendary', 8), ('mythic', 12),
])
def test_identified_organs_sell_by_rarity_too(rarity, quarters):
    """Owner revised §24.225: identification no longer protects an organ —
    it only stops the ASCENSION recipes (sell same price either way)."""
    entry = _organ(rarity=rarity, identified=True)
    assert recipes.sell_quarters_for(entry) == quarters
    match = recipes.match_forge([entry])
    assert _quarter_total(match) == quarters
    assert match['confirm'] == (rarity in recipes.SELL_CONFIRM_RARITIES)


def test_identified_organs_still_never_ascend():
    match = recipes.match_forge([_organ('liver', 'common', identified=True)
                                 for _ in range(4)])
    assert not _organ_outs(match), 'recipes stay unidentified-only'
    assert _quarter_total(match) == 4, '...they just sell'


def test_cards_sell_one_quarter_per_card():
    assert recipes.sell_quarters_for(
        {'item': 'poker_ace_hearts', 'count': 1}) == 1
    assert recipes.sell_quarters_for(
        {'item': 'poker_joker', 'count': 4}) == 4, \
        'a Joker stack pays its own quarters back'
    match = recipes.match_forge([{'item': 'poker_ace_hearts', 'count': 1}])
    assert _quarter_total(match) == 1
    assert not match['confirm'], 'cards never trip the confirm popup'


def test_potions_sell_by_rarity_times_stack():
    one = {'item': 'health_potion', 'count': 1, 'col': 0, 'row': 0}
    stack = {'item': 'health_potion', 'count': 10, 'col': 0, 'row': 0}
    assert recipes.sell_quarters_for(one) == 1, 'common potion = 1 quarter'
    assert recipes.sell_quarters_for(stack) == 10, 'x stack size'
    match = recipes.match_forge([stack])
    assert _quarter_total(match) == 10


def test_flask_sells_for_four_quarters():
    flask = {'item': 'flask_health', 'count': 1, 'col': 0, 'row': 0,
             'charges': 1}
    assert recipes.sell_quarters_for(flask) == recipes.SELL_QUARTERS_FLASK


def test_gem_sells_by_its_instance_rarity():
    assert recipes.sell_quarters_for(_gem(rarity='uncommon')) == 2
    assert recipes.sell_quarters_for(_gem(rarity='epic')) == 6


def test_unknown_junk_is_not_sellable():
    junk = {'item': 'scrap_never_defined', 'count': 1, 'col': 0, 'row': 0}
    assert recipes.sell_quarters_for(junk) is None
    match = recipes.match_forge([junk])
    assert not match['groups'], 'zero-value junk rides back'


def test_mixed_sells_merge_into_one_joker_stack():
    grid = [_organ('lungs', 'common'), _organ('kidney', 'rare'),
            _gem('red', 'uncommon')]
    match = recipes.match_forge(grid)
    assert len(match['groups']) == 1, 'sells merge into a single payout'
    outs = match['groups'][0]['outputs']
    assert len(outs) == 1
    assert outs[0]['item'] == 'poker_joker'
    assert outs[0]['count'] == 1 + 4 + 2


def test_legendary_sell_requires_confirmation():
    match = recipes.match_forge([_organ('heart', 'legendary')])
    assert match['confirm']
    assert _quarter_total(match) == 8
    assert not recipes.match_forge([_organ('heart', 'epic')])['confirm']


# ── the item recipes (§24.226) ────────────────────────────────────────

def _organ_outs(match):
    return [out for group in match['groups'] for out in group['outputs']
            if items.ITEMS.get(out['item'], {}).get('equipSlot')]


def test_organ_ascension_common_to_uncommon():
    rng = random.Random(7)
    grid = [_organ('lungs', 'common', ilvl=4) for _ in range(4)]
    match = recipes.match_forge(grid, rng)
    outs = _organ_outs(match)
    assert len(outs) == 1
    inst = outs[0]['instance_data']
    assert inst['rarity'] == 'uncommon'
    assert inst['ilvl'] == 4
    assert not inst['identified']
    assert outs[0]['item'] in recipes.ORGAN_SLOTS
    assert _quarter_total(match) == 0, 'recipe items never also sell'


@pytest.mark.parametrize('n_from,from_r,to_r', [
    (4, 'common', 'uncommon'), (3, 'uncommon', 'rare'),
    (3, 'rare', 'epic'), (2, 'epic', 'legendary'),
])
def test_ascension_chains_by_blueprint_table(n_from, from_r, to_r):
    grid = [_organ('heart', from_r, ilvl=2) for _ in range(n_from)]
    match = recipes.match_forge(grid)
    outs = _organ_outs(match)
    assert len(outs) == 1
    assert outs[0]['instance_data']['rarity'] == to_r


def test_queen_of_hearts_recipe():
    grid = [_organ('liver', 'uncommon') for _ in range(5)]
    match = recipes.match_forge(grid)
    outs = [out for group in match['groups'] for out in group['outputs']]
    assert len(outs) == 1
    assert currency.arcana_of(outs[0]['item']) == recipes.QUEEN_ARCANA
    assert outs[0]['count'] == currency.quarters_needed(recipes.QUEEN_ARCANA)


def test_queen_recipe_fires_despite_ascension_drain():
    """The uncommon ascension drains in threes — the Queen must be matched
    first so 5 uncommons reach the cleanse recipe instead of a remainder."""
    grid = [_organ('liver', 'uncommon') for _ in range(5)]
    match = recipes.match_forge(grid)
    kinds = [currency.arcana_of(out['item'])
             for group in match['groups'] for out in group['outputs']]
    assert recipes.QUEEN_ARCANA in kinds


def test_gem_tier_up_recipe():
    grid = [_gem('blue', 'uncommon') for _ in range(5)]
    match = recipes.match_forge(grid)
    outs = [out for group in match['groups'] for out in group['outputs']]
    assert len(outs) == 1
    inst = outs[0]['instance_data']
    assert outs[0]['item'] == 'gem_blue'
    assert inst['rarity'] == 'rare'
    assert inst['identified']
    assert inst['ability']


def test_unsellable_entries_stay_unmatched():
    junk = {'item': 'scrap_never_defined', 'count': 1, 'col': 0, 'row': 0}
    grid = [_organ('lungs', 'common'), junk]
    match = recipes.match_forge(grid)
    consumed = {i for group in match['groups'] for i in group['consumed']}
    assert consumed == {0}, 'only the organ burns; the junk rides back'


def test_forge_signature_tracks_grid_changes():
    grid = [_organ('lungs', 'common')]
    sig = recipes.forge_signature(grid)
    assert recipes.forge_signature(grid) == sig
    grid.append(_organ('heart', 'common'))
    assert recipes.forge_signature(grid) != sig


# ── the InventoryUI forge flow ────────────────────────────────────────

def test_ctx_dismantle_moves_item_into_forge():
    ui = _forge_ui()
    inv = items.make_inventory()
    inv['grid'] = [_organ('heart', 'common')]
    calls = []
    ui.on_forge_change = lambda: calls.append(1)

    ui._exec({'type': 'to_forge', 'source': 'grid', 'index': 0}, inv, {})

    assert len(inv['grid']) == 0, 'item leaves the backpack'
    assert len(ui._forge_grid) == 1, 'item lands in the offerings grid'
    assert calls, 'on_forge_change must fire'


def test_ctx_dismantle_accepts_identified_organs():
    """§24.225 revised: identification no longer blocks the forge."""
    ui = _forge_ui()
    inv = items.make_inventory()
    inv['grid'] = [_organ('heart', 'rare', identified=True)]
    ui._exec({'type': 'to_forge', 'source': 'grid', 'index': 0}, inv, {})
    assert len(inv['grid']) == 0, 'identified gear dismantles too'
    assert len(ui._forge_grid) == 1


def test_ctx_dismantle_accepts_cards():
    """§24.225 revised: currency cards can be fed to the forge (1 quarter
    per card)."""
    ui = _forge_ui()
    inv = items.make_inventory()
    inv['grid'] = [{'item': 'poker_joker', 'count': 4, 'col': 0, 'row': 0}]
    ui._exec({'type': 'to_forge', 'source': 'grid', 'index': 0}, inv, {})
    assert len(inv['grid']) == 0
    assert len(ui._forge_grid) == 1


def test_take_back_moves_offering_to_backpack():
    ui = _forge_ui()
    inv = items.make_inventory()
    ui._forge_grid = [_organ('lungs', 'common')]
    ui._exec({'type': 'from_forge', 'source': 'forge', 'index': 0}, inv, {})
    assert len(ui._forge_grid) == 0
    assert any(e['item'] == 'lungs' for e in inv['grid'])


def test_receipt_is_not_takable():
    """The results grid is a display-only receipt — its items already live
    in the backpack, so a TAKE/duplicate must not exist."""
    ui = _forge_ui()
    inv = items.make_inventory()
    ui._forge_out = [currency.make_card_slot(0, 4, col=0, row=0)]
    ui._exec({'type': 'from_forge', 'source': 'forge_out', 'index': 0},
             inv, {})
    # the receipt slot dict survives untouched; the backpack's only Joker
    # is the untouched starter stack (4/4) — no duplicate entered
    assert len(ui._forge_out) == 1
    jokers = [e for e in inv['grid']
              if currency.arcana_of(e.get('item', '')) == 0]
    assert len(jokers) == 1 and jokers[0]['count'] == 4


def test_new_offering_clears_stale_receipt():
    ui = _forge_ui()
    inv = items.make_inventory()
    ui._forge_out = [currency.make_card_slot(0, 4, col=0, row=0)]
    inv['grid'] = [_organ('heart', 'common')]
    ui._exec({'type': 'to_forge', 'source': 'grid', 'index': 0}, inv, {})
    assert ui._forge_out == [], 'old receipt dies with the new offering set'


def test_forge_preview_matches_dismantle_outputs():
    """The LIVE receipt previews the exact slots a dismantle will produce —
    same cached rolls, same placement — then the receipt keeps showing them."""
    ui = _forge_ui()
    inv = items.make_inventory()
    inv['grid'] = []
    ui._forge_grid = [_organ('kidney', 'epic', ilvl=9),
                      _organ('liver', 'epic', ilvl=4)]
    preview = ui._forge_preview_slots()
    assert preview and len(preview) == 1
    assert preview[0]['instance_data']['rarity'] == 'legendary'

    # stable across reads (no flicker of the random organ slot)
    assert [p['item'] for p in ui._forge_preview_slots()] \
        == [preview[0]['item']]

    assert ui.dismantle(inv)
    # the receipt mirrors the preview; the real organ is in the backpack
    assert [(e['item'], e['count']) for e in ui._forge_out] \
        == [(preview[0]['item'], 1)]
    assert any(e['item'] == preview[0]['item'] for e in inv['grid'])


def test_dismantle_sends_outputs_straight_to_backpack():
    ui = _forge_ui()
    inv = items.make_inventory()
    ui._forge_grid = [_organ('kidney', 'epic', ilvl=9),
                      _organ('liver', 'epic', ilvl=4)]
    calls = []
    ui.on_forge_change = lambda: calls.append(1)

    assert ui.dismantle(inv)
    assert ui._forge_grid == [], 'consumed offerings burn'
    inst = ui._forge_out[0]['instance_data']
    assert ui._forge_out[0]['item'] in recipes.ORGAN_SLOTS
    assert inst['rarity'] == 'legendary'
    assert inst['ilvl'] == 9, 'output ilvl is the max of the inputs'
    # the REAL item is in the backpack; the receipt is a mirror
    organ_outs = [e for e in inv['grid']
                  if items.ITEMS.get(e['item'], {}).get('equipSlot')]
    assert len(organ_outs) == 1
    assert organ_outs[0]['instance_data']['rarity'] == 'legendary'
    assert calls


def test_dismantle_receipt_matches_backpack_items():
    """What the receipt shows is exactly what was received."""
    ui = _forge_ui()
    inv = items.make_inventory()
    inv['grid'] = []   # drop the starter cards so the diff is exact
    ui._forge_grid = [_organ('lungs', 'common'), _organ('heart', 'common')]
    assert ui.dismantle(inv)
    before = [(e['item'], e['count']) for e in inv['grid']]
    shown = [(e['item'], e['count']) for e in ui._forge_out]
    assert sorted(shown) == sorted(before)


def test_dismantle_full_backpack_consumes_nothing():
    ui = _forge_ui()
    inv = items.make_inventory()
    for r in range(items.INV_ROWS):
        for c in range(items.INV_COLS):
            inv['grid'].append({'item': 'lungs', 'count': 1,
                                'col': c, 'row': r,
                                'instance_data': {
                                    'rarity': 'common', 'ilvl': 1,
                                    'identified': True,
                                    'affixes': {'prefixes': {},
                                                'suffixes': {}}}})
    ui._forge_grid = [_organ('kidney', 'epic'), _organ('liver', 'epic')]
    assert not ui.dismantle(inv), 'no backpack room — refuse the trade'
    assert len(ui._forge_grid) == 2, 'offerings are never lost'
    assert ui._forge_out == []


def test_dismantle_without_match_is_a_noop():
    ui = _forge_ui()
    inv = items.make_inventory()
    # zero-value junk matches nothing and must not burn
    ui._forge_grid = [{'item': 'scrap_never_defined', 'count': 1,
                       'col': 0, 'row': 0}]
    assert not ui.dismantle(inv)
    assert len(ui._forge_grid) == 1


def test_close_forge_returns_offerings_to_backpack():
    """Only offerings return on close — the receipt is display-only."""
    ui = _forge_ui()
    inv = items.make_inventory()
    ui._forge_grid = [_organ('lungs', 'common')]
    ui._forge_out = [currency.make_card_slot(0, 2, col=1, row=0)]  # receipt

    assert ui.close_forge(inv)
    assert not ui.forge_open
    kinds = sorted(e['item'] for e in inv['grid'])
    assert kinds == ['lungs', 'poker_ace_hearts', 'poker_joker',
                     'poker_queen_diamonds'], \
        'only the offering returns; the receipt never duplicates'
    assert ui._forge_grid is None and ui._forge_out is None


def test_close_forge_fires_save_callback():
    """The close-path return must persist: to_forge saved the item's
    ABSENCE from the backpack, so the return needs its own save."""
    ui = _forge_ui()
    inv = items.make_inventory()
    ui._forge_grid = [_organ('lungs', 'common')]
    calls = []
    ui.on_forge_change = lambda: calls.append(1)
    assert ui.close_forge(inv)
    assert calls, 'close_forge must fire on_forge_change after the return'


def test_close_forge_with_full_backpack_keeps_panel_open():
    ui = _forge_ui()
    inv = items.make_inventory()
    # fill every backpack cell
    for r in range(items.INV_ROWS):
        for c in range(items.INV_COLS):
            inv['grid'].append({'item': 'lungs', 'count': 1,
                                'col': c, 'row': r,
                                'instance_data': {
                                    'rarity': 'common', 'ilvl': 1,
                                    'identified': True,
                                    'affixes': {'prefixes': {},
                                                'suffixes': {}}}})
    lung = _organ('lungs', 'common')
    ui._forge_grid = [lung]
    assert not ui.close_forge(inv), 'backpack full — nothing may be lost'
    assert ui.forge_open, 'panel stays open'
    assert ui._forge_grid == [{k: v for k, v in lung.items()
                               if k not in ('col', 'row')}], \
        'the stranded offering stays offered'


def test_forge_slot_hit_testing(headless_draw):
    ui = _forge_ui()
    entry = _organ('lungs', 'common')
    entry['col'] = 2
    entry['row'] = 1
    ui._forge_grid = [entry]

    mx, my = _cell_center_px(2, 1)
    hit = ui._slot_at_forge(mx, my)
    assert hit and hit['source'] == 'forge' and hit['index'] == 0
    assert ui._slot_at_forge(4000, 4000) is None


# ── headless draw smoke ───────────────────────────────────────────────

def test_forge_panel_draw_smoke(headless_draw):
    ui = _forge_ui()
    inv = items.make_inventory()
    ui._forge_grid = [_organ('lungs', 'common'),
                      _organ('heart', 'legendary')]
    ui._forge_out = [currency.make_card_slot(0, 4, col=0, row=0)]
    ui._draw_forge_panel(inv, 1280, 720, 0, 0)
    ui._confirm_dismantle = {'inventory': inv}
    ui._draw_confirm_dismantle(1280, 720, 0, 0)


def test_forge_panel_needs_no_art_file(headless_draw):
    """The stone side-panel fallback covers a missing blacksmith.png."""
    ui = _forge_ui()
    ui._forge_bg = None
    ui._forge_grid = []
    ui._draw_forge_panel(items.make_inventory(), 1280, 720, 0, 0)


# ── context-menu click integrity (dead-click fix) ─────────────────────

def _inv_cell_center_px(col, row):
    """Screen pixel of the centre of backpack grid cell (col,row) at 720p."""
    s = 720 / 1080
    px = 1280 - 554 * s
    return (int(px + (24 + col * 64 + 32) * s),
            int((541 + row * 64 + 32) * s))


def test_ctx_hit_uses_drawn_rect_at_screen_edge(headless_draw):
    """The menu clamps to the screen when drawn (the panel is anchored to
    the right screen edge) — the hit-test must clamp identically or the
    visible rows are dead: 'SOCKET was there, click did nothing'."""
    ui = _forge_ui()
    slot = _organ('heart', 'rare', identified=True)
    ui._ctx = {'x': 1270, 'y': 600, 'source': 'grid', 'index': 0, 'slot': slot}
    cx, cy, menu_w, menu_h, item_h, opts = ui._ctx_rect()
    assert cx + menu_w <= 1280 and cy + menu_h <= 720, 'draw rect is clamped'
    # a click on the DRAWN first row resolves to an option
    action, inside = ui._ctx_hit(cx + 10, cy + 2 + item_h // 2)
    assert inside and action is not None, 'drawn rows are clickable'


def test_ctx_hit_returns_disabled_options(headless_draw):
    """Disabled options are returned with their flag so the caller can keep
    the menu open — and refusals are VISIBLE (zero-value junk)."""
    ui = _forge_ui()
    slot = {'item': 'scrap_never_defined', 'count': 1, 'col': 0, 'row': 0}
    ui._ctx = {'x': 100, 'y': 100, 'source': 'grid', 'index': 0, 'slot': slot}
    cx, cy, menu_w, menu_h, item_h, opts = ui._ctx_rect()
    assert 'DISMANTLE (no value)' in [o['label'] for o in opts]
    didx = next(i for i, o in enumerate(opts)
                if not o.get('enabled', True))
    action, inside = ui._ctx_hit(cx + 10, cy + 2 + didx * item_h + item_h // 2)
    assert inside and action is not None and not action.get('enabled', True)
    # menu padding: inside the menu but no option under the click
    action, inside = ui._ctx_hit(cx + 5, cy)
    assert inside and action is None
    # off the menu: a full miss
    action, inside = ui._ctx_hit(cx - 50, cy + 10)
    assert not inside and action is None


def test_disabled_option_click_keeps_menu_open(headless_draw, monkeypatch):
    """Clicking a disabled option (zero-value junk) used to close the menu
    with zero effect — the menu must stay open AND say why."""
    import systems.input as inp_mod
    ui = _forge_ui()
    inv = items.make_inventory()
    inv['grid'] = [{'item': 'scrap_never_defined', 'count': 1,
                    'col': 0, 'row': 0}]
    ui._ctx = {'x': 1270, 'y': 600, 'source': 'grid', 'index': 0,
               'slot': inv['grid'][0]}
    cx, cy, menu_w, menu_h, item_h, opts = ui._ctx_rect()
    row_y = next(cy + 2 + i * item_h for i, o in enumerate(opts)
                 if not o.get('enabled', True))
    mx, my = cx + 20, row_y + 2
    monkeypatch.setattr(rl, 'get_mouse_x', lambda: mx)
    monkeypatch.setattr(rl, 'get_mouse_y', lambda: my)
    monkeypatch.setattr(inp_mod, 'mouse_pressed',
                        lambda c, b: b == rl.MOUSE_BUTTON_LEFT)
    ui.update(inv, {})
    assert ui._ctx is not None, 'a disabled option never closes the menu'
    assert len(inv['grid']) == 1, 'nothing was executed'
    assert ui._notice, 'the click must SAY why (never a silent dead click)'
    assert 'no dismantle value' in ui._notice
    # a click OUTSIDE the menu closes it
    monkeypatch.setattr(rl, 'get_mouse_x', lambda: 5)
    monkeypatch.setattr(rl, 'get_mouse_y', lambda: 5)
    ui.update(inv, {})
    assert ui._ctx is None


def test_rmb_on_another_item_swaps_menu_in_one_click(headless_draw, monkeypatch):
    """Right-clicking another item while the menu is open moves the menu
    straight there — close-then-reopen cost two clicks."""
    import systems.input as inp_mod
    ui = _forge_ui()
    inv = items.make_inventory()
    a = _organ('heart', 'common'); a['col'] = 0; a['row'] = 0
    b = _organ('lungs', 'common'); b['col'] = 1; b['row'] = 0
    inv['grid'] = [a, b]
    mx, my = _inv_cell_center_px(1, 0)
    monkeypatch.setattr(rl, 'get_mouse_x', lambda: mx)
    monkeypatch.setattr(rl, 'get_mouse_y', lambda: my)
    monkeypatch.setattr(inp_mod, 'mouse_pressed',
                        lambda c, b: b == rl.MOUSE_BUTTON_RIGHT)
    ui._ctx = {'x': 100, 'y': 100, 'source': 'grid', 'index': 0, 'slot': a}
    ui.update(inv, {})
    assert ui._ctx and ui._ctx['index'] == 1, 'menu swapped in one click'
    # right-clicking empty panel space still closes the menu
    monkeypatch.setattr(rl, 'get_mouse_x', lambda: 5)
    monkeypatch.setattr(rl, 'get_mouse_y', lambda: 5)
    ui.update(inv, {})
    assert ui._ctx is None


def test_forge_dismantle_labels_follow_sell_table(headless_draw):
    """§24.225 revised: identified organs, cards and potions all get a LIVE
    DISMANTLE; only zero-value junk gets the disabled option."""
    ui = _forge_ui()
    for slot in (_organ('heart', 'rare', identified=True),
                 {'item': 'poker_joker', 'count': 4},
                 {'item': 'health_potion', 'count': 3},
                 {'item': 'flask_health', 'count': 1, 'charges': 1}):
        ui._ctx = {'x': 100, 'y': 100, 'source': 'grid', 'index': 0,
                   'slot': slot}
        opts = ui._ctx_options()
        d = next(o for o in opts if o['type'] == 'to_forge')
        assert d['label'] == 'DISMANTLE' and d.get('enabled', True), \
            f"sellable: {slot['item']}"
    # zero-value junk: disabled with a reason sentence
    ui._ctx = {'x': 100, 'y': 100, 'source': 'grid', 'index': 0,
               'slot': {'item': 'scrap_never_defined', 'count': 1}}
    d = next(o for o in ui._ctx_options() if o['type'] == 'to_forge')
    assert not d.get('enabled', True) and d['label'] == 'DISMANTLE (no value)'
    assert 'no dismantle value' in d['why']
