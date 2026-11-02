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

"""XP, leveling and attribute allocation (issue #31, ADR-006).

Owner rulings under test:
- XP from kills, depth-scaled, over-level diminishing, streak bonus.
- One attribute point per level; attributes hard-clamp at 10 from ALL
  sources; level hard-cap 70 (= 7 x 10) with vessels granting no baselines.
- Death costs 10% of the current level's XP requirement, never de-levels,
  nothing is lost at the cap.
"""

import unittest
from unittest import mock

import entities.progression as prog
import systems.xp as xp
from entities.descend import (ATTR_CAP, DESCEND_ATTRIBUTES,
                              increase_attribute, vessel_baseline_stats)


def _char(**kw):
    c = prog.Character('xp-test', 'Tester', 'knight')
    for k, v in kw.items():
        setattr(c, k, v)
    return c


class XpCurveTests(unittest.TestCase):
    def test_requirements_are_monotonic_and_positive(self):
        reqs = [xp.xp_for_level(n) for n in range(1, xp.MAX_LEVEL)]
        self.assertTrue(all(r > 0 for r in reqs))
        self.assertEqual(reqs, sorted(reqs))

    def test_cap_level_requires_zero(self):
        self.assertEqual(xp.xp_for_level(xp.MAX_LEVEL), 0)
        self.assertEqual(xp.xp_for_level(xp.MAX_LEVEL + 10), 0)

    def test_deep_kills_are_worth_more_than_shallow_ones(self):
        self.assertGreater(xp.kill_xp(30.0), xp.kill_xp(1.0))

    def test_over_level_kills_diminish(self):
        self.assertEqual(xp.over_level_factor(1, 1.0), 1.0)
        self.assertEqual(xp.over_level_factor(6, 1.0), 1.0)   # inside grace
        self.assertLess(xp.over_level_factor(10, 1.0), 1.0)
        self.assertEqual(xp.over_level_factor(200, 1.0),
                         xp._OVER_LEVEL_FLOOR)

    def test_streak_bonus_capped_at_half(self):
        self.assertEqual(xp.streak_multiplier(0), 1.0)
        self.assertEqual(xp.streak_multiplier(1), 1.05)
        self.assertEqual(xp.streak_multiplier(10), 1.5)
        self.assertEqual(xp.streak_multiplier(50), 1.5)   # hard cap


class GrantXpTests(unittest.TestCase):
    def test_gain_one_level_adds_one_attribute_point(self):
        c = _char()
        points_before = c.available_points
        gained = xp.grant_xp(c, xp.xp_for_level(1))
        self.assertEqual(gained, 1)
        self.assertEqual(c.level, 2)
        self.assertEqual(c.available_points, points_before + 1)

    def test_multi_level_gain_in_one_award(self):
        c = _char()
        total = sum(xp.xp_for_level(n) for n in range(1, 6))
        gained = xp.grant_xp(c, total)
        self.assertEqual(gained, 5)
        self.assertEqual(c.level, 6)
        self.assertEqual(c.available_points, 5)

    def test_surplus_xp_rolls_over_between_levels(self):
        c = _char()
        # 1.5 levels of XP: level 2 with half a bar banked
        award = xp.xp_for_level(1) + xp.xp_for_level(2) // 2
        xp.grant_xp(c, award)
        self.assertEqual(c.level, 2)
        self.assertEqual(c.xp, xp.xp_for_level(2) // 2)

    def test_capped_character_ignores_xp(self):
        c = _char(level=xp.MAX_LEVEL, xp=0)
        gained = xp.grant_xp(c, 10_000_000)
        self.assertEqual(gained, 0)
        self.assertEqual(c.level, xp.MAX_LEVEL)
        self.assertEqual(c.xp, 0)

    def test_cannot_level_past_hard_cap(self):
        c = _char(level=xp.MAX_LEVEL - 1, xp=0)
        total = sum(xp.xp_for_level(n)
                    for n in range(xp.MAX_LEVEL - 1, xp.MAX_LEVEL + 50))
        gained = xp.grant_xp(c, total)
        self.assertEqual(gained, 1)
        self.assertEqual(c.level, xp.MAX_LEVEL)
        self.assertEqual(c.xp, 0)

    def test_negative_award_is_ignored(self):
        c = _char()
        xp.grant_xp(c, -50)
        self.assertEqual(c.level, 1)
        self.assertEqual(c.xp, 0)


class DeathPenaltyTests(unittest.TestCase):
    def test_loses_ten_percent_of_current_level_requirement(self):
        c = _char(level=4, xp=xp.xp_for_level(4))
        lost = xp.death_penalty(c)
        self.assertEqual(lost, int(round(xp.xp_for_level(4) * 0.10)))
        self.assertEqual(c.level, 4)      # no de-leveling
        self.assertEqual(c.xp, xp.xp_for_level(4) - lost)

    def test_penalty_floors_at_level_start(self):
        c = _char(level=4, xp=5)
        lost = xp.death_penalty(c)
        self.assertEqual(lost, 5)
        self.assertEqual(c.level, 4)
        self.assertEqual(c.xp, 0)
        # A second death at an empty bar loses nothing
        self.assertEqual(xp.death_penalty(c), 0)

    def test_no_penalty_at_the_cap(self):
        c = _char(level=xp.MAX_LEVEL, xp=1234)
        self.assertEqual(xp.death_penalty(c), 0)
        self.assertEqual(c.xp, 1234)

    def test_penalty_never_moves_below_zero(self):
        c = _char(level=2, xp=0)
        self.assertEqual(xp.death_penalty(c), 0)


class AttributeAllocationTests(unittest.TestCase):
    def test_cap_is_ten_and_points_fully_spend_via_levels(self):
        # The arithmetic ruling: 70 levels x 1 point = 7 attributes x 10.
        self.assertEqual(xp.MAX_LEVEL, 7 * ATTR_CAP)
        c = _char(level=xp.MAX_LEVEL, available_points=70)
        for attr in DESCEND_ATTRIBUTES:
            for _ in range(ATTR_CAP):
                self.assertTrue(increase_attribute(c, attr))
        self.assertEqual(sum(c.descend[a] for a in DESCEND_ATTRIBUTES), 70)
        self.assertEqual(c.available_points, 0)

    def test_allocation_beyond_cap_is_refused(self):
        c = _char(available_points=ATTR_CAP)
        for _ in range(ATTR_CAP):
            self.assertTrue(increase_attribute(c, 'dexterity'))
        self.assertFalse(increase_attribute(c, 'dexterity'))
        self.assertEqual(c.descend['dexterity'], ATTR_CAP)

    def test_vessels_grant_no_baselines(self):
        for looks in ('knight', 'warrior', 'fighter'):
            self.assertEqual(vessel_baseline_stats(looks),
                             {a: 0 for a in DESCEND_ATTRIBUTES})


class HardClampTests(unittest.TestCase):
    """Owner ruling: attributes hard-clamp at 10 from ALL sources."""

    def _derived(self, descend, items):
        return prog.compute_derived_stats(descend, {}, item_bonuses=items,
                                          looks='knight')

    def test_items_beyond_ten_are_clamped(self):
        items = {a: 99 for a in DESCEND_ATTRIBUTES}
        d = self._derived({}, items)
        for attr in DESCEND_ATTRIBUTES:
            self.assertEqual(d[attr], ATTR_CAP)

    def test_allocation_plus_items_is_clamped(self):
        descend = {a: 0 for a in DESCEND_ATTRIBUTES}
        descend['strength'] = 7
        d = self._derived(descend, {'strength': 50})
        self.assertEqual(d['strength'], ATTR_CAP)

    def test_clamped_attributes_drive_derived_stats_at_cap_values(self):
        items = {a: 99 for a in DESCEND_ATTRIBUTES}
        d = self._derived({}, items)
        self.assertEqual(d['max_health'], 50 + ATTR_CAP * 8 * 2)


class CharacterSerializationTests(unittest.TestCase):
    def test_level_xp_round_trip(self):
        c = _char(level=13, xp=450)
        c2 = prog.Character.from_dict(c.to_dict())
        self.assertEqual(c2.level, 13)
        self.assertEqual(c2.xp, 450)

    def test_garbage_level_xp_degrade_to_safe_values(self):
        c2 = prog.Character.from_dict({
            'id': 'g', 'name': 'G', 'looks': 'knight', 'descend': {},
            'perks': {}, 'available_points': 0,
            'inventory': None, 'stash': [], 'level': 'nope', 'xp': None})
        self.assertEqual(c2.level, 1)
        self.assertEqual(c2.xp, 0)


if __name__ == '__main__':
    unittest.main()
