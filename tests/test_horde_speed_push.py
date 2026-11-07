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

"""Horde feel pass - issue #53.

Covers:
  1. Enemies are faster than the pre-#53 baselines (owner: "enemies faster").
  2. Steering separation runs on the shared spatial hash (O(n), not O(n²)).
  3. Body push resolves overlapping pairs positionally, capped so shoves
     read as jostling; frozen bodies never budge.
  4. Dark charge: bodies outside the pulse's light radius close at
     DARK_CHARGE_MULT speed and snap back at the pool edge.
  5. One integration frame of update_zombies with an overlapping horde
     runs clean end to end.
"""

import math
import unittest

import entities.zombies as zombies
from entities.zombies import DARK_CHARGE_MULT


def _body(body_id, x, y, **extra):
    body = {
        'id': body_id, 'x': x, 'y': y, 'health': 100,
        'enemy_type': 'skeleton', 'level': 1, 'accuracy': 100,
        'move_speed': zombies.ZOMBIE_SPEED, 'state': 'chase',
        'anim_timer': 0.0, 'attack_cd': 0.0, 'rot_timer': 0.0,
    }
    body.update(extra)
    return body


def _players():
    return [{'x': 5.0, 'y': 5.0, 'evasion': 300, 'entropy_grace_pct': 0.0}]


def _grid():
    return [[0] * 20 for _ in range(20)]


def _run(body_list, frames, geometry=True):
    """Tick bodies toward the player at (5,5); geometry toggles the pulse."""
    rect = _grid()
    light_center = (5.0, 5.0) if geometry else None
    light_radius = 5.5 if geometry else 0.0
    for _ in range(frames):
        zombies.update_zombies(1 / 60, body_list, _players(), rect,
                               light_center=light_center,
                               light_radius=light_radius)


class Speeds(unittest.TestCase):
    def test_enemies_faster_than_pre_53_baselines(self):
        """The #53 buff: chase speeds up from 0.6 / 0.22."""
        self.assertEqual(zombies.ZOMBIE_SPEED, 0.9)
        self.assertEqual(zombies.SLIME_SPEED, 0.45)
        self.assertGreater(zombies.SLIME_SPEED, 0.22)
        # Slime must keep the slow-tank identity.
        self.assertLess(zombies.SLIME_SPEED, zombies.ZOMBIE_SPEED)


class SpatialHash(unittest.TestCase):
    def test_nearby_finds_cross_cell_bodies(self):
        """Two bodies in adjacent cells still see each other."""
        a = _body('a', 0.48, 10.5)
        b = _body('b', 0.52, 10.5)      # one cell to the east
        grid = zombies._build_body_grid([a, b])
        self.assertIn(b, zombies._nearby_bodies(grid, a))
        self.assertIn(a, zombies._nearby_bodies(grid, b))

    def test_far_bodies_are_not_neighbours(self):
        a = _body('a', 10.0, 10.0)
        b = _body('b', 20.0, 20.0)
        grid = zombies._build_body_grid([a, b])
        self.assertNotIn(b, zombies._nearby_bodies(grid, a))

    def test_separation_vector_pushes_away(self):
        """Sep steering points the mover away from its overlapping mate."""
        a = _body('a', 10.0, 10.0)
        b = _body('b', 10.2, 10.0)
        grid = zombies._build_body_grid([a, b])
        sx, sy = zombies._separation_vector(a, grid)
        self.assertLess(sx, 0.0)       # away from +x where b sits
        self.assertAlmostEqual(sy, 0.0, places=9)


class BodyPush(unittest.TestCase):
    def test_overlapping_pair_separates(self):
        a = _body('a', 10.0, 10.0)
        b = _body('b', 10.05, 10.0)
        before = abs(b['x'] - a['x'])
        grid = zombies._build_body_grid([a, b])
        zombies._resolve_body_push([a, b], grid, dt=1 / 120)
        after = b['x'] - a['x']
        self.assertGreater(after, before)
        # symmetric, capped shove - no teleports
        self.assertLessEqual(after - before,
                             2 * zombies.PUSH_SEPARATION_TPS * (1 / 120)
                             + 1e-9)

    def test_pair_converges_to_rest_distance(self):
        a = _body('a', 10.0, 10.0)
        b = _body('b', 10.4, 10.0)   # tiny 0.02 overlap
        grid = zombies._build_body_grid([a, b])
        zombies._resolve_body_push([a, b], grid, dt=1 / 120)
        self.assertAlmostEqual(b['x'] - a['x'], zombies.PUSH_MIN_SEP, places=9)

    def test_frozen_never_budges(self):
        a = _body('a', 10.0, 10.0, frozen_timer=5.0)
        b = _body('b', 10.05, 10.0)
        ax, ay = a['x'], a['y']
        grid = zombies._build_body_grid([a, b])
        zombies._resolve_body_push([a, b], grid, dt=1 / 60)
        self.assertEqual((a['x'], a['y']), (ax, ay))
        self.assertGreater(b['x'], 10.05)

    def test_two_frozen_bodies_stay_frozen(self):
        a = _body('a', 10.0, 10.0, frozen_timer=5.0)
        b = _body('b', 10.05, 10.0, frozen_timer=5.0)
        grid = zombies._build_body_grid([a, b])
        zombies._resolve_body_push([a, b], grid, dt=1 / 60)
        self.assertAlmostEqual(b['x'] - a['x'], 0.05, places=9)

    def test_touching_body_cluster_runs_clean(self):
        """A 5-body pile resolves one pass without blowing up distances."""
        pile = [_body(f'p{i}', 10.0 + i * 0.02, 10.0) for i in range(5)]
        grid = zombies._build_body_grid(pile)
        zombies._resolve_body_push(pile, grid, dt=1 / 120)
        for a in pile:
            for b in pile:
                if a is b:
                    continue
                d = ((a['x'] - b['x']) ** 2 + (a['y'] - b['y']) ** 2) ** 0.5
                self.assertGreater(d, 0.0)


class DarkCharge(unittest.TestCase):
    """Bodies outside the pool edge close at DARK_CHARGE_MULT; the speed is
    a pure function of light distance and snaps back inside the light."""

    def test_charge_ratio_matches_constant(self):
        dark = _body('dark', 5.0, 12.0, state='chase')    # 7 tiles - darkness
        lit = _body('lit', 5.0, 8.0, state='chase')       # 3 tiles - lit
        dark0, lit0 = dark['y'], lit['y']
        _run([dark, lit], 30)
        dark_travel = dark0 - dark['y']
        lit_travel = lit0 - lit['y']
        # both moved straight toward the player with identical ramp, so the
        # travel ratio IS the charge multiplier
        self.assertGreater(dark_travel, lit_travel)
        self.assertAlmostEqual(dark_travel / lit_travel, DARK_CHARGE_MULT,
                               delta=0.35)

    def test_no_geometry_no_charge(self):
        """Hub fights (no pulse passed) run at plain chase speed."""
        with_geo = _body('g', 5.0, 12.0, state='chase')
        without = _body('n', 5.0, 12.0, state='chase')
        _run([with_geo], 30, geometry=True)
        _run([without], 30, geometry=False)
        charged_travel = 12.0 - with_geo['y']
        plain_travel = 12.0 - without['y']
        self.assertAlmostEqual(plain_travel * DARK_CHARGE_MULT,
                               charged_travel, delta=plain_travel * 0.35 + 1e-9)
        self.assertLess(plain_travel, charged_travel)

    def test_charge_snaps_back_inside_the_light(self):
        """Per-frame step shrinks once the body crosses the pool edge."""
        b = _body('b', 5.0, 11.0, state='chase')
        rect = _grid()
        first_step = None
        prev_y = b['y']
        for _ in range(200):
            zombies.update_zombies(1 / 60, [b], _players(), rect,
                                   light_center=(5.0, 5.0),
                                   light_radius=5.5)
            step = abs(prev_y - b['y'])
            if first_step is None:
                first_step = step
            prev_y = b['y']
            if math.hypot(b['x'] - 5.0, b['y'] - 5.0) <= 4.0:
                break
        # deep inside the light the frame step is well below the charged step
        self.assertLess(step, first_step * 0.7)
        self.assertGreater(first_step, 0.0)


class IntegrationFrame(unittest.TestCase):
    def test_update_zombies_runs_a_horde_frame(self):
        """End-to-end: overlap cluster chases a far player, one frame OK."""
        horde = []
        for i in range(12):
            horde.append(_body(f'h{i}', 10.0 + (i % 4) * 0.05,
                               10.0 + (i // 4) * 0.05))
        damage = zombies.update_zombies(1 / 60, horde, _players(), _grid())
        self.assertEqual(damage, {})
        for z in horde:
            self.assertGreater(z['health'], 0)


if __name__ == '__main__':
    unittest.main()
