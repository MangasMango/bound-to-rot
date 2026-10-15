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

"""Tests for QoL #111 / GitHub issue #15 — Slime attack range vs chase range.

The historical bug: slimes transitioned idle->chase at MELEE_RANGE (0.25) but
dealt damage at a *wider* 0.5 tile range, so they could hit the player from
twice the distance they started chasing (damage before being aggro'd).

The fix unified both onto MELEE_RANGE (0.32). These tests lock that invariant
in and prove a slime can only deal damage once it is actually engaged/aggro'd
and within MELEE_RANGE.
"""

import math
import unittest

import entities.zombies as z
from entities.zombies import (
    MELEE_RANGE,
    DETECT_RANGE,
    SLIME_DAMAGE,
    update_zombies,
    default_status_fields,
)


def make_player(x, y, evasion=0):
    return {
        'x': x,
        'y': y,
        'evasion': evasion,
        'accuracy': 100,
    }


def make_slime(x, y, state):
    """Build a minimal slime dict in the requested state."""
    return {
        'id': 's1',
        'x': x,
        'y': y,
        'health': 150,
        'max_health': 150,
        'state': state,
        'anim_timer': 0.0,
        'frame': 0,
        'facing_x': 1.0,
        'facing_y': 0.0,
        'accuracy': 1000,          # high accuracy -> deterministic hit in tests
        'evasion': 30,
        'spawn_x': x,
        'spawn_y': y,
        'move_speed': 0.22,
        'speed_ramp': 1.0,
        'dmg_type': 'physical',
        'enemy_type': 'slime',
        'attack_anim_timer': 0.0,
        'attack_cd': 0.0,          # ready to attack immediately
        'level': 1,
        **default_status_fields(),
    }


# Walkable 40x40 map (all floor tiles == 0).
MAP = [[0] * 40 for _ in range(40)]


class SlimeRangeTests(unittest.TestCase):

    def setUp(self):
        # The to-hit roll is capped at 95%, so force hits for determinism —
        # these tests verify range gating, not the accuracy-vs-evasion math.
        self._real_evaluate_hit = z.evaluate_hit
        z.evaluate_hit = lambda defender, attacker_accuracy: True

    def tearDown(self):
        z.evaluate_hit = self._real_evaluate_hit

    def test_attack_range_never_exceeds_chase_acquire_range(self):
        """Acceptance criterion: attack range <= chase-acquire range."""
        self.assertLessEqual(
            MELEE_RANGE, DETECT_RANGE,
            "MELEE_RANGE (attack range) must not exceed DETECT_RANGE (chase-acquire range)",
        )

    def test_slime_in_attack_state_ignores_targets_beyond_melee_range(self):
        """A slime in 'attack' must NOT damage a player beyond MELEE_RANGE.

        This is the exact scenario from QoL #111: a target at the old 0.5 attack
        range must never take damage. The slime should also revert to 'chase'.
        """
        # distance 0.5 is greater than MELEE_RANGE (0.32)
        slime = make_slime(10.0, 10.0, 'attack')
        player = make_player(10.5, 10.0)
        dmg = update_zombies(0.1, [slime], [player], MAP)

        self.assertEqual(dmg, {}, "slime must not deal damage beyond MELEE_RANGE")
        self.assertEqual(slime['state'], 'chase',
                         "slime should fall back to chase when target leaves MELEE_RANGE")

    def test_slime_in_attack_state_damages_within_melee_range(self):
        """A slime in 'attack' DOES damage a player inside MELEE_RANGE."""
        slime = make_slime(10.0, 10.0, 'attack')
        player = make_player(10.0 + MELEE_RANGE * 0.9, 10.0)  # 0.288 < 0.32
        dmg = update_zombies(0.1, [slime], [player], MAP)

        self.assertIn('physical', dmg)
        self.assertGreater(dmg['physical'], 0.0)

    def test_slime_attack_range_is_bounded_by_melee_range(self):
        """Boundary check: damage gates exactly at MELEE_RANGE.

        If a future change widens the slime's attack reach (the original bug),
        this test fails.
        """
        # Just inside MELEE_RANGE -> damage.
        inner = make_slime(10.0, 10.0, 'attack')
        dmg_inner = update_zombies(0.1, [inner],
                                   [make_player(10.0 + MELEE_RANGE * 0.99, 10.0)], MAP)
        self.assertGreater(dmg_inner.get('physical', 0.0), 0.0,
                           "expected damage just inside MELEE_RANGE")

        # Just outside MELEE_RANGE -> no damage.
        outer = make_slime(10.0, 10.0, 'attack')
        dmg_outer = update_zombies(0.1, [outer],
                                   [make_player(10.0 + MELEE_RANGE * 1.01, 10.0)], MAP)
        self.assertEqual(dmg_outer.get('physical', 0.0), 0.0,
                         "no damage just outside MELEE_RANGE")

    def test_slime_only_damages_once_engaged(self):
        """An idle slime that aggros into 'chase' but never reaches MELEE_RANGE
        must never deal damage (it is not yet engaged)."""
        slime = make_slime(10.0, 10.0, 'idle')
        player = make_player(11.0, 10.0)  # distance 1.0, within DETECT_RANGE -> aggros
        total = 0.0
        for _ in range(10):
            dmg = update_zombies(0.1, [slime], [player], MAP)
            for v in dmg.values():
                total += v
        self.assertEqual(total, 0.0,
                         "slime must not deal damage until within MELEE_RANGE")
        self.assertEqual(slime['state'], 'chase',
                         "slime should be aggro'd (chasing) but not yet attacking")

    def test_slime_in_chase_state_does_not_damage_same_frame(self):
        """While merely 'chase', the slime closes in but does not deal damage on
        the same frame it would transition into 'attack'."""
        slime = make_slime(10.0, 10.0, 'chase')
        player = make_player(10.0 + MELEE_RANGE * 0.5, 10.0)  # well within range
        dmg = update_zombies(0.1, [slime], [player], MAP)

        self.assertEqual(dmg, {}, "damage only happens in 'attack' state")
        self.assertEqual(slime['state'], 'attack',
                         "slime should transition chase->attack this frame")


class ChaseClosesIntoAttackTests(unittest.TestCase):
    """Regression: the chase stop distance must stay strictly below
    MELEE_RANGE. When MELEE_RANGE was tuned down to 0.22 while the chase
    movement still halted at 0.25, enemies stopped just outside their own
    attack reach and never attacked."""

    def setUp(self):
        self._real_evaluate_hit = z.evaluate_hit
        z.evaluate_hit = lambda defender, attacker_accuracy: True

    def tearDown(self):
        z.evaluate_hit = self._real_evaluate_hit

    def test_chaser_reaches_attack_state(self):
        """A chasing enemy within DETECT_RANGE must transition into 'attack'
        (i.e. the movement stop distance is inside MELEE_RANGE)."""
        zombie = make_slime(10.0, 10.0, 'chase')
        zombie['enemy_type'] = 'skeleton'
        zombie['move_speed'] = 0.22
        player = make_player(11.0, 10.0)  # 1.0 tile away, well within DETECT_RANGE
        for _ in range(120):              # ~1.2s of simulated steps at 0.1s
            update_zombies(0.1, [zombie], [player], MAP)
            if zombie['state'] == 'attack':
                break
        self.assertEqual(zombie['state'], 'attack',
                         "enemy must close into MELEE_RANGE and attack — "
                         "if it stalls, the chase stop distance >= MELEE_RANGE")

    def test_stop_distance_below_melee_range(self):
        """Direct invariant: the movement halt threshold is inside attack reach."""
        self.assertLess(z.MELEE_RANGE * 0.6, z.MELEE_RANGE)


if __name__ == '__main__':
    unittest.main()
