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

"""Flat armour roll-on-and-apply - issue #3.

Covers:
  1. `flat_armor` maps through LIVE_EFFECT_MAP into `flat_damage_reduction`,
     so a rolled Reinforced affix now reaches the damage pipeline.
  2. Armour mitigation is PoE-style ratio, not a flat subtraction:
     flat / (flat + ARMOUR_HIT_K * hit), capped at ARMOUR_MITIGATION_CAP.
  3. Chip hits are shredded, spikes barely register armour.
  4. Armour can never reduce a physical hit to zero.
  5. Armour does NOT touch elemental hits (they lean on resist_pct).
"""

import unittest

import pytest

from core.game import ARMOUR_MITIGATION_CAP, Game
import systems.itemgen as itemgen


def _game():
    """A Game stripped to what _apply_damage touches."""
    game = Game.__new__(Game)
    game.inventory = None
    game._second_wind_cooldown = 0.0
    game._incoming_dmg_by_type = {}
    game._shake_timer = 0.0
    game._shake_intensity = 0.0
    game._log_combat = lambda *args, **kwargs: None
    game._spawn_dmg_number = lambda *args, **kwargs: None
    return game


def _hit(raw, dmg_type='physical', flat=0.0, resist=0.0):
    game = _game()
    game.stats = {'health': 1000, 'max_health': 1000,
                  'energy_shield': 0.0, 'resist_pct': {dmg_type: resist}}
    game._apply_damage(raw, dmg_type, damage_reduction=0.0,
                       flat_damage_reduction=flat)
    return 1000 - game.stats['health']


class FlatArmourMapping(unittest.TestCase):
    def test_flat_armor_maps_into_live_effects(self):
        """A rolled flat_armor affix must surface in live_effect_totals."""
        inst = {'affixes': {'prefixes': {'flat_armor': 20.0}, 'suffixes': {}}}
        totals = itemgen.live_effect_totals(inst)
        self.assertAlmostEqual(totals.get('flat_damage_reduction'), 20.0)
        self.assertEqual(itemgen.LIVE_EFFECT_MAP['flat_armor'],
                         'flat_damage_reduction')


class ArmRatioMitigation(unittest.TestCase):
    def test_chip_hit_shredded(self):
        """Depth-1 melee hit (20) against a base 20-roll: ~50% mitigation."""
        self.assertAlmostEqual(_hit(20.0, flat=20.0), 10.0, places=6)

    def test_spike_barely_registered(self):
        """A 10x spike against the same armour loses under 5%."""
        # damage after ratio mitigation = raw * hit / (flat + hit)
        taken = _hit(200.0, flat=20.0)
        self.assertAlmostEqual(taken, 200.0 * 200.0 / (20.0 + 200.0), places=6)
        taken_deep = _hit(500.0, flat=20.0)
        self.assertAlmostEqual(taken_deep, 500.0 * 500.0 / (20.0 + 500.0),
                               places=6)
        # mitigation on the spikes (~4-9%) is far below the ~50% the chip took
        self.assertGreater(taken / 200.0, 0.90)
        self.assertGreater(taken_deep / 500.0, 0.95)

    def test_armour_never_zeroes_a_hit(self):
        """Even absurd armour leaves chip damage on the table."""
        self.assertGreater(_hit(20.0, flat=1e9), 0.0)

    def test_mitigation_capped(self):
        """Overwhelming flat armour clamps at ARMOUR_MITIGATION_CAP."""
        # 1000 flat vs a 50 hit would be 0.952 uncapped - capped to 0.90.
        self.assertAlmostEqual(_hit(50.0, flat=1000.0),
                               50.0 * (1.0 - ARMOUR_MITIGATION_CAP), places=6)

    def test_no_armour_untouched(self):
        self.assertAlmostEqual(_hit(77.0, flat=0.0), 77.0, places=6)

    def test_stacks_multiplicatively_with_percent_dr(self):
        """Armour applies before the % DR multiplier."""
        game = _game()
        game.stats = {'health': 1000, 'max_health': 1000,
                      'energy_shield': 0.0, 'resist_pct': {}}
        # flat 20 vs 100 hit: armour mitigates 20/120 = 16.67%, then %DR
        # multiplies the remainder: (100 * (1 - 1/6)) * (1 - 0.75) = 20.833
        game._apply_damage(100.0, 'physical', damage_reduction=0.75,
                           flat_damage_reduction=20.0)
        self.assertAlmostEqual(1000 - game.stats['health'],
                               100.0 * (120.0 - 20.0) / 120.0 * 0.25, places=6)

    def test_elemental_ignores_armour(self):
        """PoE split: armour is physical-only; elemental leans on resist."""
        self.assertAlmostEqual(_hit(20.0, dmg_type='fire', flat=20.0), 20.0,
                               places=6)
        self.assertAlmostEqual(_hit(20.0, dmg_type='fire', flat=20.0,
                                    resist=0.5), 10.0, places=6)


if __name__ == '__main__':
    unittest.main()
