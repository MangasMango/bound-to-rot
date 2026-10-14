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

"""Stat-pool preservation + leveling-leftover removal.

Owner rulings (2026-10-07):
  * reset_stats PRESERVES health/mana/energy_shield (clamped to the new
    maxima) — a stat recalc (gear swap, identify, hub arrival, delve
    resume) never refills you. The level-up-era full heal is gone.
    Full refills exist only at character creation (empty dict → defaults)
    and a fresh delve start (explicit, delve_flow._enter_delve).
  * The dead DESCEND skills screen and its HUD "spend points" hint are
    removed from ui/menus.py and core/render/hud_render.py.
"""

import unittest
from pathlib import Path
from types import SimpleNamespace

from entities.player_stats import reset_stats


class TestResetStatsPreservesPools(unittest.TestCase):
    def test_empty_dict_starts_full(self):
        s = {}
        reset_stats(s, max_health=80, max_mana=30, mana=30,
                    max_energy_shield=10)
        self.assertEqual(s['health'], 80)
        self.assertEqual(s['mana'], 30)
        self.assertEqual(s['energy_shield'], 10)

    def test_recalc_keeps_pools_when_max_grows(self):
        s = {}
        reset_stats(s, max_health=100, max_mana=40, max_energy_shield=20)
        s['health'] = 37.0
        s['mana'] = 9.0
        s['energy_shield'] = 11.0
        # a gear swap raises every maximum — the pools must NOT refill
        reset_stats(s, max_health=150, max_mana=60, max_energy_shield=30)
        self.assertEqual(s['health'], 37.0)
        self.assertEqual(s['mana'], 9.0)
        self.assertEqual(s['energy_shield'], 11.0)
        self.assertEqual(s['max_health'], 150)

    def test_pools_clamp_when_max_shrinks(self):
        s = {}
        reset_stats(s, max_health=100, max_mana=40, max_energy_shield=20)
        s['health'] = 95.0
        s['mana'] = 38.0
        s['energy_shield'] = 19.0
        reset_stats(s, max_health=60, max_mana=25, max_energy_shield=0)
        self.assertEqual(s['health'], 60.0)
        self.assertEqual(s['mana'], 25.0)
        self.assertEqual(s['energy_shield'], 0.0)

    def test_max_health_pct_growth_does_not_heal(self):
        s = {}
        reset_stats(s, max_health=100)
        s['health'] = 50.0
        reset_stats(s, max_health=100, max_health_pct=20)   # max becomes 120
        self.assertEqual(s['max_health'], 120)
        self.assertEqual(s['health'], 50.0)


class TestRecalcKeepsPools(unittest.TestCase):
    """The reported repro: raising the display-only LVL (equipping better
    gear) ran a recalc that used to refill the player to full."""

    def _game(self):
        import core.game as game_mod
        from entities.progression import Character
        from systems import items
        char = Character('pools-1', 'Pools Tester', 'fighter')
        char.inventory = items.make_inventory()
        game = SimpleNamespace()
        game.char = char
        game.inventory = char.inventory
        game.stats = {}
        game._equipped_bonuses = lambda: game_mod.Game._equipped_bonuses(game)
        game._recalc_derived_stats = lambda: game_mod.Game._recalc_derived_stats(game)
        return game

    def test_gear_recalc_does_not_refill(self):
        game = self._game()
        game._recalc_derived_stats()              # first build: empty -> full
        full = game.stats['max_health']
        game.stats['health'] = full * 0.37
        game.stats['mana'] = 3.0
        game._recalc_derived_stats()              # equip-driven recalc
        self.assertEqual(game.stats['health'], full * 0.37)
        self.assertEqual(game.stats['mana'], 3.0)


class TestFreshDelveRefill(unittest.TestCase):
    def test_fresh_delve_explicitly_refills(self):
        src = Path('core/delve_flow.py').read_text(encoding='utf-8')
        body = src.split('def _enter_delve', 1)[1]
        self.assertIn('A FRESH run starts at full pools', body)
        self.assertIn("self.stats['health'] = self.stats['max_health']", body)


class TestLevelingLeftoversGone(unittest.TestCase):
    def test_skills_screen_removed_from_menus(self):
        menus = Path('ui/menus.py').read_text(encoding='utf-8')
        for needle in ('_skills_inc', '_skills_dec', '_skills_layout',
                       '_u_skills', '_d_skills', '_skills_focus',
                       '_pending_points', '_pending_descend',
                       '_descend_effect_label', '_draw_attr_desc_panel'):
            self.assertNotIn(needle, menus, needle)

    def test_dead_allocator_api_not_imported_by_menus(self):
        menus = Path('ui/menus.py').read_text(encoding='utf-8')
        for needle in ('purchase_perk', 'increase_attribute',
                       'is_perk_unlockable', 'get_available_descend_points',
                       'DESCEND_PERKS'):
            self.assertNotIn(needle, menus, needle)

    def test_hud_unspent_points_hint_removed(self):
        hud = Path('core/render/hud_render.py').read_text(encoding='utf-8')
        self.assertNotIn('S to spend', hud)
        self.assertNotIn('avail_pts', hud)


if __name__ == '__main__':
    unittest.main()
