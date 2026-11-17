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

"""Affix tooltip value conventions (issue #95 session bug).

Two value conventions live side by side in the affix table:
  * classic live-effect affixes store FRACTIONS (0.05 = 5%) - the tooltip
    shows them x100;
  * perk-keyed affixes (pk_* families) store PERCENTAGE POINTS (10 = 10%)
    - the tooltip must show them RAW, because compute_derived_stats
    divides by 100 when folding them into the percent axis.

The old x100-everything tooltip rule made a +10% Cold Damage roll display
"+1000% Cold Damage" - a 100x lie between tooltip and pipeline.
"""

import unittest

import systems.itemgen as itemgen


class AffixLabelConventionTests(unittest.TestCase):

    def test_perk_affixes_render_raw_points(self):
        inst = {'affixes': {'prefixes': {
            'pk_cold_dmg': 10,      # 10 points = +10% (NOT +1000%)
            'pk_cold_pen': 8,
            'pk_dark_resist': 18,
        }, 'suffixes': {}}}
        lines = itemgen.affix_lines(inst)
        self.assertIn('+10% Cold Damage', lines)
        self.assertIn('+8% Cold Penetration', lines)
        self.assertIn('+18% Darkness Resistance', lines)
        self.assertFalse(any('1000' in line for line in lines))

    def test_classic_fraction_affixes_render_x100(self):
        inst = {'affixes': {'prefixes': {
            'percent_max_health': 0.05,     # fraction: 0.05 = +5%
            'local_damage_reduction': 0.06,
        }, 'suffixes': {'crit_chance': 0.03, 'percent_attack_speed': 0.08}}}
        lines = itemgen.affix_lines(inst)
        self.assertIn('+5% Maximum Life', lines)
        self.assertIn('+6% Damage Reduction', lines)
        self.assertIn('+3% Critical Strike', lines)
        self.assertIn('+8% Attack Speed', lines)

    def test_flat_affixes_render_raw(self):
        inst = {'affixes': {'prefixes': {'pk_max_es': 8, 'flat_armor': 20},
                            'suffixes': {}}}
        lines = itemgen.affix_lines(inst)
        self.assertIn('+8 Maximum Energy Shield', lines)
        self.assertIn('+20 Armour', lines)

    def test_every_affix_label_renders_without_keyerror(self):
        for affix in itemgen._AFFIXES:
            inst = {'affixes': {'prefixes': {affix['id']: 4},
                                'suffixes': {}}}
            lines = itemgen.affix_lines(inst)   # must not raise
            self.assertEqual(len(lines), 1)


if __name__ == '__main__':
    unittest.main()
