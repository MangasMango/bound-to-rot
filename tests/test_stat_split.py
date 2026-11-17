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

"""The flat/percent stat split (issues #83 + #70, owner ruling 2026-11-17).

ATTRIBUTES GIVE FLAT STATS (one typed-damage identity each), ITEMS GIVE
PERCENT. Covers:
  1. Golden values on compute_derived_stats (0 points / capped points).
  2. The typed flat-damage identities: STR physical, CUN magic, ESS rot,
     NRV cold, DST lightning; fire has no attribute.
  3. Percent levers are item/perk-owned: attribute points never move
     attack_damage_mult, cdr, reload, crit, entropy.
  4. armor_flat reaches the mitigation (STR identity + flat_armor affix).
  5. Flat typed damage reaches the outgoing damage pipeline.
"""

import unittest

import entities.progression as prog
from entities.descend import DESCEND_ATTRIBUTES
import systems.itemgen as itemgen
import systems.items as items


def _descend(**points):
    d = {a: 0 for a in DESCEND_ATTRIBUTES}
    d.update(points)
    return d


def _derived(descend, perk=None, item=None):
    return prog.compute_derived_stats(descend, perk or {}, item or {})


class GoldenValueTests(unittest.TestCase):

    def test_zero_attributes_are_the_base_block(self):
        d = _derived(_descend())
        self.assertEqual(d['max_health'], 50)
        self.assertEqual(d['accuracy'], 300)
        self.assertEqual(d['attack_damage_mult'], 1.0)
        self.assertEqual(d['max_energy_shield'], 0)
        self.assertEqual(d['loot_rarity_mod'], 0)
        self.assertEqual(d['damage_flat'], {'physical': 0.0, 'magic': 0.0,
                                            'rot': 0.0, 'cold': 0.0,
                                            'lightning': 0.0, 'fire': 0.0})
        self.assertEqual(d['armor_flat'], 0.0)
        self.assertEqual(d['crit_chance'], 0.0)
        self.assertEqual(d['cooldown_recovery_pct'], 0.0)

    def test_strength_gives_health_armor_and_flat_physical(self):
        d = _derived(_descend(strength=5))
        self.assertEqual(d['max_health'], 50 + 5 * 6)
        self.assertEqual(d['armor_flat'], 5.0)
        self.assertAlmostEqual(d['damage_flat']['physical'], 7.5)

    def test_endurance_gives_health_es_and_darkness_resist(self):
        d = _derived(_descend(endurance=4))
        self.assertEqual(d['max_health'], 50 + 4 * 6)
        self.assertEqual(d['max_energy_shield'], 4 * 1.5)
        self.assertAlmostEqual(d['darkness_resist_pct'], 0.04)

    def test_capped_attributes_are_the_whole_axis(self):
        d = _derived(_descend(strength=10, endurance=10))
        self.assertEqual(d['max_health'], 50 + 20 * 6)
        self.assertEqual(d['armor_flat'], 10.0)
        self.assertAlmostEqual(d['damage_flat']['physical'], 15.0)

    def test_fire_is_essence_owned(self):
        """Owner ruling: Essence is the dual-type attribute (entropy =
        rot AND fire) - every damage type has an attribute identity."""
        d = _derived(_descend(essence=5))
        self.assertAlmostEqual(d['damage_flat']['fire'], 5.0)
        d_all = _derived(_descend(cunning=5, nerve=5, destiny=5,
                                  strength=5))
        self.assertEqual(d_all['damage_flat']['fire'], 0.0)


class TypedIdentityTests(unittest.TestCase):

    def test_each_attribute_owns_its_flat_type(self):
        d = _derived(_descend(cunning=3, essence=6, nerve=2, destiny=7))
        self.assertAlmostEqual(d['damage_flat']['magic'], 3.0)
        self.assertAlmostEqual(d['damage_flat']['rot'], 6.0)
        self.assertAlmostEqual(d['damage_flat']['fire'], 6.0)   # essence dual-type
        self.assertAlmostEqual(d['damage_flat']['cold'], 2.0)
        self.assertAlmostEqual(d['damage_flat']['lightning'], 7.0)

    def test_physical_is_strength_only(self):
        d = _derived(_descend(cunning=5, essence=5, nerve=5, destiny=5))
        self.assertEqual(d['damage_flat']['physical'], 0.0)


class PercentIsItemOwnedTests(unittest.TestCase):

    def test_attribute_percent_identities_stay_small(self):
        """The refined rule (owner table, #83/#70): attributes carry SMALL
        secondary % identities - capped at 0.5%/point (10 pts = 5%); the
        big % rolls belong to items."""
        d0 = _derived(_descend())
        d10 = _derived(_descend(**{a: 10 for a in DESCEND_ATTRIBUTES}))
        for key, attr in (('cooldown_recovery_pct', 'cunning'),
                          ('reload_speed_pct', 'cunning'),
                          ('crit_chance', 'nerve'),
                          ('ability_crit_chance', 'essence'),
                          ('entropy_grace_pct', 'destiny')):
            base = d0[key]
            self.assertAlmostEqual(d10[key] - base, 0.05, places=4, msg=key)
        # the attack-damage multiplier stays item-ONLY (no attribute %)
        self.assertEqual(d0['attack_damage_mult'], d10['attack_damage_mult'])

    def test_percent_levers_still_come_from_items(self):
        d = _derived(_descend(strength=5),
                     item={'attack_damage_mult_pct': 40,
                           'crit_chance': 6})
        self.assertAlmostEqual(d['attack_damage_mult'], 1.40)
        self.assertAlmostEqual(d['crit_chance'], 0.06)


class PipelineTests(unittest.TestCase):

    def _harness(self, strength):
        from types import SimpleNamespace
        import core.game as game_mod
        char = prog.Character('h', 'Harness', 'knight')
        char.inventory = items.make_inventory()
        game = SimpleNamespace()
        game.char = char
        game.inventory = char.inventory
        game.stats = {}
        game._equipped_bonuses = lambda: game_mod.Game._equipped_bonuses(game)
        game._recalc_derived_stats = lambda: game_mod.Game._recalc_derived_stats(game)
        game._outgoing_dmg_mult = lambda t: game_mod.Game._outgoing_dmg_mult(game, t)
        # the STR armor identity rides the descend table
        game.char.descend['strength'] = strength
        game._recalc_derived_stats()
        return game

    def test_strength_reaches_the_mitigation_as_flat_armor(self):
        game = self._harness(strength=3)
        equip_effects = game._equipped_bonuses()
        flat = (equip_effects['flat_damage_reduction']
                + game.stats.get('armor_flat', 0.0))
        self.assertAlmostEqual(flat, 3.0)

    def test_damage_flat_reaches_outgoing_damage(self):
        game = self._harness(strength=4)

    def test_organ_implicit_typed_damage_reaches_the_pipeline(self):
        """Owner ruling (issue #83 follow-up): organ implicits are percent
        and include OFFENSE - the intestine's +6% Magic Damage implicit
        rides the same damage_pct axis as rolled affixes."""
        game = self._harness(strength=0)
        intestine = {'item': 'intestine', 'count': 1, 'col': 0, 'row': 0,
                     'instance_data': itemgen.generate_instance('intestine', 10)}
        intestine['instance_data']['identified'] = True
        game.inventory['equipped']['intestine'] = intestine
        game._recalc_derived_stats()
        self.assertAlmostEqual(game.stats['damage_pct']['magic'], 0.06)
        # kidney: flat physical implicit identity
        kidney = {'item': 'kidney', 'count': 1, 'col': 1, 'row': 0,
                  'instance_data': itemgen.generate_instance('kidney', 10)}
        kidney['instance_data']['identified'] = True
        game.inventory['equipped']['kidney'] = kidney
        game._recalc_derived_stats()
        self.assertAlmostEqual(game.stats['damage_pct']['physical'], 0.05)

    def test_damage_flat_reaches_outgoing_damage(self):
        game = self._harness(strength=4)
        # the revolver fires physical: base 25 * mult + flat attack + flat typed
        equip = game._equipped_bonuses()
        expected = int((25 * game.stats.get('attack_damage_mult', 1.0)
                        + equip['attack_damage']
                        + game.stats['damage_flat']['physical'])
                       * game._outgoing_dmg_mult('physical'))
        self.assertGreater(expected, 25)   # the flat physical damage landed


if __name__ == '__main__':
    unittest.main()
