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

"""Accuracy now comes from vessel attributes and item bonuses, never levels."""

import unittest

from core.delve_gen import effective_level
from entities.progression import compute_derived_stats
from entities.zombies import enemy_evasion
from systems.combat import hit_chance, skeleton_accuracy


class ItemProgressionAccuracyTests(unittest.TestCase):
    def test_base_accuracy_connects_at_depth_one(self):
        stats = compute_derived_stats({})
        for enemy_type in ('skeleton', 'slime'):
            chance = hit_chance(stats['accuracy'], enemy_evasion(enemy_type, 1))
            self.assertGreaterEqual(chance, 0.90)

    def test_nerve_and_dexterity_still_push_accuracy(self):
        plain = compute_derived_stats({})['accuracy']
        buffed = compute_derived_stats({'nerve': 5, 'dexterity': 5})['accuracy']
        self.assertGreater(buffed, plain)

    def test_enemy_scaling_is_derived_from_depth(self):
        self.assertGreater(effective_level(20), effective_level(1))
        self.assertGreater(enemy_evasion('skeleton', 20), enemy_evasion('skeleton', 1))
        self.assertGreater(skeleton_accuracy(20), skeleton_accuracy(1))


if __name__ == '__main__':
    unittest.main()
