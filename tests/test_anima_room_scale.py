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

"""Anima room enlargement - issue #11.

Covers:
  1. Room spans hit the owner's 10-18 tiles-per-axis target
     (odd-span formula maps it to 11..17).
  2. Corridor lengths scale so adjacent rooms butt, never nest: a
     corridor runs from the parent room's edge to the next room's
     centre, so L >= new-room half-width keeps the AABBs disjoint.
  3. Carved segment rooms stay inside the grid and inside the span band.
  4. Hidden-wing pockets keep their rubble ring outside the (now larger)
     parent room footprint.
"""

import random
import unittest

import core.anima_gen as dg
from core.anima_gen import (CORRIDOR_LEN_MAX, CORRIDOR_LEN_MIN, GRID_H,
                            GRID_W, HIDDEN_WING_MIN_DIST, ROOM_MAX, ROOM_MIN,
                            generate_hidden_wing, generate_segment,
                            init_anima_room)


def aabb_overlap(ac, ar, ahw, ahh, bc, br, bhw, bhh):
    """Axis-aligned overlap of ((center_c, center_r), half_w, half_h) boxes."""
    return (abs(ac - bc) < ahw + bhw) and (abs(ar - br) < ahh + bhh)


class RoomSpanBand(unittest.TestCase):
    def test_owner_target_band(self):
        """Owner target 10-18 tiles/axis; odd carve formula -> 11..17."""
        self.assertGreaterEqual(ROOM_MIN * 2 + 1, 10)
        self.assertLessEqual(ROOM_MAX * 2 + 1, 18)

    def test_rooms_actually_carve_in_band(self):
        """Across seeds, start rooms always sit inside 11..17 per axis."""
        for seed in range(60):
            out = init_anima_room(seed=seed, depth=1)
            node = out['node']
            self.assertTrue(ROOM_MIN * 2 + 1 <= node['w'] <= ROOM_MAX * 2 + 1)
            self.assertTrue(ROOM_MIN * 2 + 1 <= node['h'] <= ROOM_MAX * 2 + 1)


class CorridorScaling(unittest.TestCase):
    def test_corridor_keeps_rooms_from_nesting(self):
        """Small rooms + long corridors must not create nested AABBs.

        Parent stays in a safe interior band so grid-edge clamping can't
        squash the geometry under test."""
        for seed in range(60):
            rng = random.Random(seed)
            data = init_anima_room(seed=seed, depth=2)
            grid, node = data['grid'], data['node']
            depth = 2
            for _ in range(12):
                if not (40 <= int(node['col']) <= 160
                        and 40 <= int(node['row']) <= 160):
                    break   # drifted to the clamp band - stop checking
                parent_w, parent_h = node['w'], node['h']
                px_, py_ = float(node['col']), float(node['row'])
                direction = rng.choice(dg._ALL_DIRS)
                new_node = generate_segment(grid, node, direction, rng, depth)
                depth += 1
                self.assertFalse(
                    aabb_overlap(px_, py_, parent_w // 2, parent_h // 2,
                                 new_node['col'], new_node['row'],
                                 new_node['w'] // 2, new_node['h'] // 2),
                    f'seed {seed}: segment rooms overlap')
                node = new_node

    def test_corridor_invariant_matches_room_band(self):
        """Min corridor clears the widest new room by at least 1 tile."""
        self.assertGreaterEqual(CORRIDOR_LEN_MIN, (ROOM_MAX * 2 + 1) // 2)

    def test_segment_rooms_bounded_in_grid(self):
        out = init_anima_room(seed=3, depth=1)
        grid, node = out['grid'], out['node']
        rng = random.Random(99)
        depth = 1
        for _ in range(24):
            direction = rng.choice(dg._ALL_DIRS)
            node = generate_segment(grid, node, direction, rng, depth)
            depth += 1
            for name, val, span in (('w', node['w'], GRID_W),
                                    ('h', node['h'], GRID_H)):
                self.assertLessEqual(val, span - 12)


class HiddenWingPlacement(unittest.TestCase):
    def test_ring_outside_enlarged_room(self):
        """Every successful wing keeps its 7x7 ring clear of the room AABB."""
        for seed in range(60):
            rng = random.Random(seed)
            grid = [[0] * GRID_H for _ in range(GRID_W)]
            node = {'col': GRID_W // 2, 'row': GRID_H // 2,
                    'w': ROOM_MAX * 2 + 1, 'h': ROOM_MAX * 2 + 1}
            wing = generate_hidden_wing(grid, node, rng, wing_id=seed)
            if wing is None:
                continue
            # The ring (radius 3) must be disjoint from the parent room AABB
            # - the offset only runs along the wing direction, so the
            # two-axis overlap test is the correct disjointness probe.
            self.assertFalse(
                aabb_overlap(node['col'], node['row'],
                             node['w'] // 2, node['h'] // 2,
                             wing['cx'], wing['cy'], 3, 3),
                f'seed {seed}: wing pocket ring overlaps parent room')

    def test_min_dist_clears_ring_radius(self):
        """dist counts from the room edge: ring radius 3 must stay outside."""
        self.assertGreaterEqual(HIDDEN_WING_MIN_DIST, 3)


if __name__ == '__main__':
    unittest.main()
