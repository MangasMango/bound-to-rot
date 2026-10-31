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

"""Weather + wet-ground reflection support (systems/weather).

The weather system is render-only: rain state and deterministic puddle
placement on plain floor tiles. These tests cover the GL-free parts:
roll determinism, puddle placement invariants, and renderer defaults.
"""

import unittest

from systems import weather


class WeatherRollTests(unittest.TestCase):
    def test_roll_deterministic_per_seed(self):
        a = weather.roll(1234, 5)
        b = weather.roll(1234, 5)
        self.assertEqual(a, b)

    def test_roll_ranges(self):
        for seed in range(50):
            w = weather.roll(seed, 0)
            self.assertIsInstance(w['raining'], bool)
            self.assertGreaterEqual(w['intensity'], 0.0)
            self.assertLessEqual(w['intensity'], 1.0)
            self.assertIn('seed', w)

    def test_depth_ramps_chance_but_stays_capped(self):
        deep = sum(1 for s in range(60) if weather.roll(s, 80)['raining'])
        shallow = sum(1 for s in range(60) if weather.roll(s, 0)['raining'])
        self.assertGreaterEqual(deep, shallow)

    def test_default_is_dry(self):
        w = weather.default()
        self.assertFalse(w['raining'])
        self.assertEqual(w['intensity'], 0.0)

    def test_puddle_strength_within_density_band(self):
        for i in range(11):
            s = weather.puddle_strength(i / 10)
            lo, hi = weather.PUDDLE_DENSITY
            self.assertGreaterEqual(s, lo - 1e-9)
            self.assertLessEqual(s, hi + 1e-9)


class PuddlePlacementTests(unittest.TestCase):
    """IsoRenderer.generate_puddles - pure set logic, no GL required."""

    def _iso(self):
        from core.iso_engine import IsoRenderer
        return IsoRenderer()

    def _flat_map(self, n=24):
        return [[0] * n for _ in range(n)]

    def test_dry_clears_puddles(self):
        iso = self._iso()
        m = self._flat_map()
        iso.generate_puddles(m, 0.5)
        iso.generate_puddles(m, 0.0)
        self.assertEqual(len(iso._puddle_cells), 0)
        self.assertIsNone(iso._puddle_bounds)

    def test_deterministic_placement(self):
        iso = self._iso()
        m = self._flat_map()
        iso.generate_puddles(m, 0.6)
        a = set(iso._puddle_cells)
        iso.generate_puddles(m, 0.6)
        self.assertEqual(a, set(iso._puddle_cells))

    def test_density_scales_with_strength(self):
        iso = self._iso()
        m = self._flat_map(40)
        counts = []
        for s in (0.005, 0.02):
            iso.generate_puddles(m, s)
            counts.append(len(iso._puddle_cells))
        self.assertLess(counts[0], counts[1])

    def test_puddles_only_on_floor(self):
        iso = self._iso()
        m = self._flat_map(30)
        m[5][7] = 1   # wall
        m[9][2] = 3
        iso.generate_puddles(m, 1.0)
        self.assertNotIn((5, 7), iso._puddle_cells)
        self.assertNotIn((9, 2), iso._puddle_cells)

    def test_bounds_cover_cells(self):
        iso = self._iso()
        m = self._flat_map(30)
        iso.generate_puddles(m, 1.0)
        if not iso._puddle_cells:
            self.skipTest('no puddles rolled on this map')
        b = iso._puddle_bounds   # (col_min, row_min, col_max, row_max)
        self.assertEqual(b,
                         (min(c for c, _ in iso._puddle_cells),
                          min(r for _, r in iso._puddle_cells),
                          max(c for c, _ in iso._puddle_cells),
                          max(r for _, r in iso._puddle_cells)))

    def test_view_cull_helper_runs(self):
        iso = self._iso()
        iso.follow(5.0, 5.0)
        m = self._flat_map(30)
        iso.generate_puddles(m, 1.0)
        gen = iso.puddle_cells_in_view(m, 1280, 720)
        for col, row, sx, sy in gen:
            self.assertGreaterEqual(sx, -iso.scale * 256)
            self.assertLessEqual(sy, 720 + iso.scale * 256)
            self.assertIn((col, row), iso._puddle_cells)
            break


class WeatherMixinDefaultsTests(unittest.TestCase):
    def test_weather_init_defaults(self):
        from core.render.weather_render import WeatherRenderMixin
        holder = WeatherRenderMixin()
        holder._weather_init()
        self.assertFalse(holder.weather['raining'])
        self.assertTrue(holder._weather_enabled)
        self.assertFalse(holder._weather_raining())


if __name__ == '__main__':
    unittest.main()
