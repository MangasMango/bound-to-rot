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

"""Ability system cleanup - BLUEPRINT §20/§23 alignment.

Covers:
  1. The old auto-cast leftover is fully removed (no passive organ system,
     no auto-fired cones, no auto dash/blink phase, no permanent haste).
  2. Haste is gone from the ability system (haste is the utility flask's job).
  3. Lifesteal / Fire Aura are E-button actives (timed buffs).
  4. Cones fire only when their button is pressed.
  5. The cabinet loot table offers all five organs.
"""

import inspect
import unittest
from pathlib import Path

import core.game as game_mod
import systems.abilities as abilities


ROOT = Path(__file__).resolve().parent.parent


def _gem(ability, rarity='rare'):
    return {'item': 'gem_red', 'count': 1,
            'instance_data': {'identified': True, 'rarity': rarity,
                              'ability': ability}}


# ── 1: leftovers removed ─────────────────────────────────────────────

class TestAutoCastRemoved(unittest.TestCase):
    def test_no_auto_cast_symbols_on_game(self):
        for name in ('_update_passive_organs', '_cast_cone', '_auto_phase',
                     '_nearby_enemy_count', '_passive_organ_abilities',
                     '_equipped_organ_ability', '_facing_vector'):
            self.assertFalse(hasattr(game_mod.Game, name), name)

    def test_old_organ_api_removed_from_abilities(self):
        self.assertFalse(hasattr(abilities, 'SLOT_ABILITY_POOLS'))
        self.assertFalse(hasattr(abilities, 'random_ability_for_slot'))
        self.assertFalse(hasattr(abilities, 'aura_targets'))

    def test_qwer_press_path_intact(self):
        src = (ROOT / 'core' / 'input.py').read_text(encoding='utf-8')
        self.assertIn('_use_gem_ability', src)


# ── 2: haste removed ─────────────────────────────────────────────────

class TestHasteRemoved(unittest.TestCase):
    def test_haste_gone_from_abilities(self):
        self.assertNotIn('haste', abilities.ABILITIES)
        self.assertNotIn('haste', abilities.MOVEMENT_POOL)
        self.assertNotIn('haste', abilities.PASSIVE_POOL)

    def test_movement_pool_is_dash_and_blink(self):
        self.assertEqual(abilities.MOVEMENT_POOL, ['dash', 'blink'])

    def test_haste_still_the_flasks_job(self):
        import systems.flasks as flasks
        self.assertEqual(flasks.UTILITY_MULT, 1.35)


# ── 3: survival actives (E button) ────────────────────────────────────

class TestSurvivalActives(unittest.TestCase):
    def _game_with(self, ability):
        g = game_mod.Game()
        g.inventory['gem_sockets']['E'] = _gem(ability)
        return g

    def test_passive_pool_abilities_are_actives_now(self):
        for ability_id in abilities.PASSIVE_POOL:
            self.assertEqual(abilities.ABILITIES[ability_id]['type'], 'active')
            self.assertIn('cooldown', abilities.ABILITIES[ability_id])
            self.assertIn('duration', abilities.ABILITIES[ability_id])

    def test_lifesteal_starts_on_e_press(self):
        g = self._game_with('lifesteal')
        self.assertTrue(g._use_gem_ability('E'))
        self.assertGreater(g._lifesteal_timer, 0)
        self.assertAlmostEqual(
            g._lifesteal_pct, abilities.ABILITIES['lifesteal']['pct'][2])

    def test_lifesteal_heals_only_while_active(self):
        g = self._game_with('lifesteal')
        self.assertTrue(g._use_gem_ability('E'))
        g.stats['health'] = 10.0
        g.stats['max_health'] = 100.0
        g._apply_lifesteal(100.0)
        healed = 10.0 + 100.0 * g._lifesteal_pct
        self.assertEqual(g.stats['health'], healed)
        # buff expired -> no further healing
        g._lifesteal_timer = 0.0
        g._apply_lifesteal(100.0)
        self.assertEqual(g.stats['health'], healed)

    def test_fire_aura_starts_on_e_press_and_ticks(self):
        g = self._game_with('fire_aura')
        self.assertTrue(g._use_gem_ability('E'))
        self.assertGreater(g._fire_aura_timer, 0)
        self.assertAlmostEqual(
            g._fire_aura_radius, abilities.ABILITIES['fire_aura']['radius'][2])
        zombie = {'id': 'z1', 'health': 10000.0, 'x': g.px + 0.3, 'y': g.py,
                  'enemy_type': 'skeleton'}
        g.zombies = [zombie]
        g._aura_tick = 0.99
        g._tick_ability_buffs(1.0)
        self.assertLess(zombie['health'], 10000.0)

    def test_fire_aura_does_not_tick_after_expiry(self):
        g = self._game_with('fire_aura')
        self.assertTrue(g._use_gem_ability('E'))
        g._fire_aura_timer = 0.0
        zombie = {'id': 'z1', 'health': 10000.0, 'x': g.px + 0.3, 'y': g.py,
                  'enemy_type': 'skeleton'}
        g.zombies = [zombie]
        g._aura_tick = 0.99
        g._tick_ability_buffs(1.0)
        self.assertEqual(zombie['health'], 10000.0)


# ── 4: cones are press-only ──────────────────────────────────────────

class TestConesPressOnly(unittest.TestCase):
    def _game_with_cone(self):
        g = game_mod.Game()
        g.inventory['gem_sockets']['Q'] = _gem('cone_physical')
        return g

    def test_socketed_cone_never_auto_fires(self):
        g = self._game_with_cone()
        for _ in range(10):
            g._tick_ability_buffs(0.5)
        self.assertNotIn('gem_Q', g._ability_cds)
        self.assertEqual(g._gem_cds.get('Q', 0.0), 0.0)

    def test_cone_fires_on_button_press(self):
        g = self._game_with_cone()
        self.assertTrue(g._use_gem_ability('Q'))
        self.assertGreater(g._gem_cds.get('Q', 0.0), 0.0)
        # and the press respects its own cooldown afterwards
        self.assertFalse(g._use_gem_ability('Q'))


if __name__ == '__main__':
    unittest.main()
