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

"""Huge-horde crowd reach + engagement compression (issue #91).

The stock body spacing (PUSH_MIN_SEP 0.42 / SEPARATION_RADIUS 0.45) was
wider than the melee reach (0.22) - around the player only ~3 bodies fit
on the attack ring, so a huge horde could barely connect. Covers:

  1. Crowd reach: a PACKED body (jostling with neighbours) attacks from
     MELEE_RANGE * CROWD_REACH_MULT; a lone body keeps the stock range.
  2. Engagement compression: bodies near the target separate less, and
     body push rests pairs tighter beside the player.
  3. Integration: a packed ring of bodies around the player deals damage
     that SCALES with the horde size - the actual #91 complaint.
"""

import math
import unittest

import entities.zombies as zombies


def _body(body_id, x, y, **extra):
    body = {
        'id': body_id, 'x': x, 'y': y, 'health': 100,
        'enemy_type': 'skeleton', 'level': 1, 'accuracy': 100,
        'move_speed': zombies.ZOMBIE_SPEED, 'state': 'chase',
        'anim_timer': 0.0, 'attack_cd': 0.0, 'rot_timer': 0.0,
    }
    body.update(extra)
    return body


def _players(x=5.0, y=5.0):
    return [{'x': x, 'y': y, 'evasion': 0, 'entropy_grace_pct': 0.0}]


def _grid():
    return [[0] * 24 for _ in range(24)]


def _ring(count, radius=0.5, cx=5.0, cy=5.0):
    """Bodies packed on a ring around the player."""
    out = []
    for i in range(count):
        ang = (i / count) * math.tau
        out.append(_body(f'r{i}', cx + math.cos(ang) * radius,
                         cy + math.sin(ang) * radius))
    return out


class CrowdReachTests(unittest.TestCase):

    def test_packed_body_reaches_farther_than_stock(self):
        # three bodies huddled inside SEPARATION_RADIUS of each other
        packed = _body('a', 5.0, 5.2), _body('b', 5.15, 5.1), _body('c', 5.05, 5.05)
        grid = zombies._build_body_grid(packed)
        self.assertTrue(zombies._is_packed(packed[0], grid))
        self.assertAlmostEqual(zombies._crowd_reach(packed[0], grid),
                               zombies.MELEE_RANGE * zombies.CROWD_REACH_MULT)

    def test_lone_body_keeps_the_stock_range(self):
        lone = _body('a', 5.0, 5.0)
        grid = zombies._build_body_grid([lone])
        self.assertFalse(zombies._is_packed(lone, grid))
        self.assertEqual(zombies._crowd_reach(lone, grid), zombies.MELEE_RANGE)

    def test_crowd_reach_stays_inside_the_chase_acquire_range(self):
        """Range invariant (issue #111): attack reach must never exceed
        DETECT_RANGE - the packed crowd reach is well below it."""
        self.assertLess(zombies.MELEE_RANGE * zombies.CROWD_REACH_MULT,
                        zombies.DETECT_RANGE)

    def test_dead_neighbours_do_not_count_as_pack(self):
        dead = _body('x', 5.1, 5.0, health=0)
        near = _body('y', 5.15, 5.05)
        body = _body('a', 5.0, 5.0)
        grid = zombies._build_body_grid([dead, near, body])
        self.assertFalse(zombies._is_packed(body, grid))


class EngagementCompressionTests(unittest.TestCase):

    def test_separation_with_reduced_radius_pushes_less(self):
        a = _body('a', 5.0, 5.0)
        b = _body('b', 5.2, 5.0)   # 0.2 apart - inside both radii
        grid = zombies._build_body_grid([a, b])
        full_x, full_y = zombies._separation_vector(a, grid)
        comp_x, comp_y = zombies._separation_vector(
            a, grid, radius=zombies.SEPARATION_RADIUS * zombies.ENGAGE_SEP_MULT)
        self.assertLess(math.hypot(comp_x, comp_y), math.hypot(full_x, full_y))

    def test_body_push_rests_tighter_beside_the_player(self):
        """Two overlapping bodies beside the player rest at the compressed
        spacing; the same pair far from any center keeps the stock one."""
        a = _body('a', 5.0, 5.0)
        b = _body('b', 5.1, 5.0)
        grid = zombies._build_body_grid([a, b])
        for _ in range(120):
            zombies._resolve_body_push([a, b], grid, 1 / 30,
                                       compress_centers=((5.0, 5.0),))
        rest_close = abs(a['x'] - b['x'])
        self.assertLess(rest_close, zombies.PUSH_MIN_SEP * 0.9)

        far_a = _body('c', 15.0, 15.0)
        far_b = _body('d', 15.1, 15.0)
        grid2 = zombies._build_body_grid([far_a, far_b])
        for _ in range(120):
            zombies._resolve_body_push([far_a, far_b], grid2, 1 / 30,
                                       compress_centers=((5.0, 5.0),))
        rest_far = abs(far_a['x'] - far_b['x'])
        self.assertGreaterEqual(rest_far, zombies.PUSH_MIN_SEP - 1e-6)


class HordeDamageScalingTests(unittest.TestCase):
    """The actual #91 complaint: a packed ring must deal damage, and MORE
    bodies must deal MORE damage."""

    def _ring_damage(self, count, seconds=3.0, radius=0.5):
        horde = _ring(count, radius=radius)
        player = _players()[0]
        total = 0.0
        frames = int(seconds / (1 / 30))
        for _ in range(frames):
            dmg = zombies.update_zombies(1 / 30, horde, [player], _grid(),
                                         light_center=None, light_radius=0.0)
            total += sum(dmg.values())
        return total

    def test_packed_ring_deals_damage(self):
        self.assertGreater(self._ring_damage(10), 0.0)

    def test_bigger_horde_deals_more_damage(self):
        small = self._ring_damage(8)
        big = self._ring_damage(20)
        self.assertGreater(big, small,
                           'a larger packed horde must hit harder (issue #91)')

    def test_lone_body_hits_only_from_stock_range(self):
        """Regression guard: an ISOLATED body (never packed) must attack at
        the stock reach even while walking in - the crowd reach belongs to
        jostling bodies, not lone ones."""
        horde = [_body('a', 5.6, 5.0)]
        player = _players()[0]
        first_hit_dist = None
        for _ in range(60):
            before = math.hypot(horde[0]['x'] - player['x'],
                                horde[0]['y'] - player['y'])
            dmg = zombies.update_zombies(1 / 30, horde, [player], _grid(),
                                         light_center=None, light_radius=0.0)
            after = math.hypot(horde[0]['x'] - player['x'],
                               horde[0]['y'] - player['y'])
            if dmg and first_hit_dist is None:
                first_hit_dist = before
            if first_hit_dist is not None:
                break
            _ = after
        self.assertIsNotNone(first_hit_dist)
        self.assertLessEqual(first_hit_dist, zombies.MELEE_RANGE + 0.05)


if __name__ == '__main__':
    unittest.main()
