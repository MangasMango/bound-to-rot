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

"""Bottom HUD bar layout + organ-rot meter bindings.

Owner ruling 2026-10-10 (BLUEPRINT §20.204 / §20.205 / §20.208 / §20.211):
the bottom bar mirrors assets/ui/result.png's STRUCTURE inside the 800 px
container —
  * left box: organ-rot meter row (worst equipped organ) over the 3 menu
    buttons (the mockup's stamina row is rot now, never stamina),
  * centre box: five CENTRED mockup-size Q/W/E/R/T slots (no numbered
    hotkeys, no potion belt),
  * right box: attack / move only (the four decorative golden frames are
    gone),
  * bronze section boxes + four divider.png strips + two chevron tabs.
"""

import unittest
from pathlib import Path

import systems.itemgen as itemgen
from systems.items import make_inventory

from tests.test_render_smoke import _game_stub, _install_headless_drawing

HUD_SRC = Path('core/render/hud_render.py').read_text(encoding='utf-8')


def _organ(item_id='heart', ilvl=10, identified=True, seed=5):
    entry = itemgen.roll_for(item_id, 1, ilvl, seed=seed)
    entry['instance_data']['identified'] = identified
    return entry


# ── itemgen.max_rot — the meter's binding ─────────────────────────────

class TestMaxRot(unittest.TestCase):
    def test_empty_or_malformed_inventory_reads_zero(self):
        self.assertEqual(itemgen.max_rot({}), 0.0)
        self.assertEqual(itemgen.max_rot(None), 0.0)
        self.assertEqual(itemgen.max_rot({'equipped': None}), 0.0)

    def test_fresh_equipped_organ_reads_zero(self):
        inv = make_inventory()
        inv['equipped']['heart'] = _organ()
        self.assertEqual(itemgen.max_rot(inv), 0.0)

    def test_returns_the_worst_equipped_organ(self):
        inv = make_inventory()
        low, high = _organ('heart', seed=5), _organ('lungs', seed=6)
        low['instance_data']['rot'] = 40.0
        high['instance_data']['rot'] = 80.0
        inv['equipped']['heart'] = low
        inv['equipped']['lungs'] = high
        self.assertEqual(itemgen.max_rot(inv), 80.0)

    def test_rotten_organ_reads_rot_max(self):
        inv = make_inventory()
        rotten = _organ('liver', seed=7)
        itemgen.make_rotten(rotten['instance_data'], rng=__import__('random').Random(3))
        inv['equipped']['liver'] = rotten
        self.assertEqual(itemgen.max_rot(inv), itemgen.ROT_MAX)

    def test_backpack_and_stash_organs_never_show_on_the_meter(self):
        inv = make_inventory()
        bag = _organ('kidney', seed=8)
        bag['instance_data']['rot'] = 90.0
        inv['grid'].append(bag)
        self.assertEqual(itemgen.max_rot(inv), 0.0)

    def test_unidentified_equipped_organ_never_shows(self):
        inv = make_inventory()
        blind = _organ('heart', identified=False, seed=9)
        blind['instance_data']['rot'] = 60.0      # inert until identified
        inv['equipped']['heart'] = blind
        self.assertEqual(itemgen.max_rot(inv), 0.0)


# ── layout: five centred slots, trimmed right cluster ────────────────

def _draw_bar(monkeypatch):
    game = _game_stub()
    _install_headless_drawing(monkeypatch)
    from core.render.hud_render import HudRenderMixin
    HudRenderMixin._draw_hud(game, 1280, 720)
    return game


def test_action_rects_are_exactly_qwer_t_attack_move(monkeypatch):
    game = _draw_bar(monkeypatch)
    assert set(game._hud_action_rects) == {
        'Q', 'W', 'E', 'R', 'T', 'attack', 'move'}
    # no numbered belt hotkeys ever come back (§20.205)
    for n in '123456':
        assert n not in game._hud_action_rects


def test_centre_row_is_five_equal_slots_centred_on_the_container(monkeypatch):
    game = _draw_bar(monkeypatch)
    rects = game._hud_action_rects
    row = [rects[k] for k in ('Q', 'W', 'E', 'R', 'T')]

    sizes = {(round(r.width), round(r.height)) for r in row}
    assert len(sizes) == 1, f'slots must be uniform: {sizes}'
    w, h = sizes.pop()
    assert w == h, f'slots must be square: {w}x{h}'

    gaps = {round(row[i + 1].x) - (round(row[i].x) + round(row[i].width))
            for i in range(4)}
    assert len(gaps) == 1, f'gaps must be even: {gaps}'

    centre = (row[0].x + row[-1].x + row[-1].width) / 2.0
    assert abs(centre - 640.0) <= 6.0, f'row centre {centre} vs screen 640'

    # stays inside the 800 px container (hud_x=240 .. 1040), clear of the
    # life orb (ends at x=384) on the left and of the right cluster
    assert row[0].x >= 400, f'row starts at {row[0].x}, too close to the orb'
    assert row[-1].x + row[-1].width <= 1040
    assert row[-1].x + row[-1].width < rects['attack'].x


def test_slot_and_button_ordering(monkeypatch):
    game = _draw_bar(monkeypatch)
    rects = game._hud_action_rects
    assert rects['Q'].x < rects['W'].x < rects['E'].x < rects['R'].x < rects['T'].x
    assert rects['attack'].x < rects['move'].x


# ── source guards for the removed / added pieces ─────────────────────

def test_source_carries_the_new_bindings():
    assert 'itemgen.max_rot' in HUD_SRC
    assert "'seg_point'" in HUD_SRC
    assert '_rot_col' in HUD_SRC
    for helper in ('_section_box', '_divider(', '_chevron('):
        assert helper in HUD_SRC, f'missing mockup dressing helper: {helper}'


def test_source_dropped_the_decorative_and_belt_pieces():
    assert 'golden_frame' not in HUD_SRC      # right cluster: dropped (§20.208)
    assert 'belt_slot' not in HUD_SRC         # T shares skill_base (§20.205)
    # the meter must never read a stamina stat — stamina is gone for good
    # (tests/test_run_toggle.py guards the stats side)
    for stale in ("stats['stamina'", 'stats.get(\'stamina\'', 'max_stamina'):
        assert stale not in HUD_SRC, f'stale stamina read: {stale}'
