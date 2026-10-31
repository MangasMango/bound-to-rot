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

"""
The D2-style run/walk mechanic and the potion belt were removed - flasks
(equipped in the T slot) are the only consumable, R is purely the white-gem
slot, and the HUD has a clickable action bar (QWER + T + attack/move) with
active_action flashes.

These tests lock the removals in so they cannot silently return, and cover
the HUD action-bar plumbing.
"""

import inspect
import unittest

from pyray import Rectangle

import core.game as game_mod
from core.game import Game
from entities import player_stats


class TestRunMechanicRemoved(unittest.TestCase):
    """Run/walk (R toggle + RUN_MULT + stamina drain) is gone for good."""

    def test_run_mult_gone(self):
        self.assertFalse(hasattr(player_stats, 'RUN_MULT'))

    def test_stats_have_no_stamina(self):
        s = player_stats.create_stats()
        self.assertNotIn('stamina', s)
        self.assertNotIn('max_stamina', s)
        self.assertNotIn('stamina_regen', s)

    def test_update_stats_has_no_running_param(self):
        params = inspect.signature(player_stats.update_stats).parameters
        self.assertNotIn('running', params)

    def test_r_fallback_gone_from_delve_loop(self):
        src = inspect.getsource(game_mod.Game._update_game)
        self.assertNotIn('_run_toggle', src,
                         'run/walk toggle must not return to the delve loop')
        self.assertNotIn('running = moving', src)

    def test_belt_hotkeys_gone(self):
        src = inspect.getsource(game_mod.Game._update_game)
        self.assertNotIn('KEY_ONE', src)
        self.assertNotIn('_drink_potion', src)

    def test_inventory_has_no_belt(self):
        g = game_mod.Game()
        self.assertNotIn('belt', g.inventory)

    def test_move_speed_pct_still_applies(self):
        s = player_stats.create_stats()
        s['_move_speed_pct'] = 0.5
        out = player_stats.update_stats(s, dt=1.0, moving=True)
        self.assertAlmostEqual(out['speed_mult'], 1.5)


class TestHudFlash(unittest.TestCase):
    """active_action flash timers: set on use, tick down, expire."""

    def test_flash_timer_ticks_down_and_expires(self):
        g = game_mod.Game()
        g._flash_hud('Q', dur=0.4)
        self.assertGreater(g._hud_flash.get('Q', 0), 0)
        g._tick_hud_flash(0.2)
        self.assertGreater(g._hud_flash.get('Q', 0), 0)
        g._tick_hud_flash(0.3)
        self.assertNotIn('Q', g._hud_flash)

    def test_gem_cast_success_flashes(self):
        g = game_mod.Game()
        g._use_organ_ability = lambda *a, **k: True   # dispatch stub
        inv = g.inventory
        inv['gem_sockets']['R'] = {'item': 'gem_white', 'count': 1,
                                   'instance_data': {'identified': True,
                                                     'ability': 'dash'}}
        self.assertTrue(g._use_gem_ability('R'))
        self.assertGreater(g._hud_flash.get('R', 0), 0)

    def test_gem_cast_failure_does_not_flash(self):
        g = game_mod.Game()
        g.inventory['gem_sockets']['R'] = None
        self.assertFalse(g._use_gem_ability('R'))
        self.assertNotIn('R', g._hud_flash)

    def test_flask_drink_flashes_and_consumes_charge(self):
        g = game_mod.Game()
        entry = g.inventory.get('flask_slot')
        self.assertIsNotNone(entry, 'starter flask expected in the T slot')
        charges0 = int(entry.get('charges', 1))
        kind = g._use_flask()
        self.assertIsNotNone(kind)
        self.assertGreater(g._hud_flash.get('T', 0), 0)
        self.assertEqual(int(entry.get('charges', 1)), charges0 - 1)

    def test_hud_over_action_blocks_world_clicks(self):
        g = game_mod.Game()
        g._hud_action_rects['Q'] = __import__('pyray').Rectangle(
            100.0, 100.0, 50.0, 50.0)
        self.assertTrue(g._hud_over_action(110, 110))
        self.assertFalse(g._hud_over_action(10, 10))


if __name__ == '__main__':
    unittest.main(verbosity=2)
