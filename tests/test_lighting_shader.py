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

"""Fire-light shader support (systems/lightgen + ShaderManager array setters).

The lighting shader (assets/shaders/lighting.fs) is a Godot-style port:
log falloff, dual scrolling noise churn, noise-perturbed edges and a fire
color curve. These tests cover the GL-free parts: texture generation and
uniform-array plumbing.
"""

import re
import unittest
from pathlib import Path

import numpy as np

from systems import lightgen
from systems.shaders import ShaderManager


class NoiseGenerationTests(unittest.TestCase):
    def setUp(self):
        self.noise = lightgen.make_light_noise(64)

    def test_shape_and_dtype(self):
        self.assertEqual(self.noise.shape, (64, 64, 4))
        self.assertEqual(self.noise.dtype, np.uint8)

    def test_tiles_seamlessly(self):
        """The generator wraps via np.roll, so the seam between the last and
        first column must be no rougher than any interior neighbour step -
        REPEAT sampling shows no visible discontinuity."""
        rgb = self.noise[..., 0].astype(np.int16)
        interior = np.abs(np.diff(rgb, axis=0)).mean() + np.abs(np.diff(rgb, axis=1)).mean()
        seam = (np.abs(rgb[:, 0].astype(int) - rgb[:, -1].astype(int)).mean()
                + np.abs(rgb[0, :].astype(int) - rgb[-1, :].astype(int)).mean())
        self.assertLessEqual(seam, interior * 3 + 8,
                             f'seam gap {seam:.1f} vs interior step {interior:.1f}')

    def test_not_flat_and_deterministic(self):
        self.assertGreater(int(np.ptp(self.noise[..., 0])), 30)
        again = lightgen.make_light_noise(64)
        self.assertTrue(np.array_equal(self.noise, again))


class FireCurveTests(unittest.TestCase):
    def test_shape_and_opaque(self):
        curve = lightgen.make_fire_curve()
        self.assertEqual(curve.shape, (1, 64, 4))
        self.assertTrue((curve[..., 3] == 255).all())

    def test_gradient_ascending_towards_hot(self):
        curve = lightgen.make_fire_curve()[0]
        self.assertLess(int(curve[0, 0]), int(curve[-1, 0]))      # red rises
        self.assertLess(int(curve[0, 2]), int(curve[-1, 2]))      # blue rises to white-hot
        self.assertGreaterEqual(int(curve[-1, 0]), 200)           # hot end is bright


class ActorLightTests(unittest.TestCase):
    def test_actor_floor_allows_visible_darkening(self):
        from core import game
        self.assertLess(game.ACTOR_MIN_LIGHT_TINT, 0.62)
        self.assertAlmostEqual(game._actor_tint_value(0.0), 0.24)
        self.assertAlmostEqual(game._actor_tint_value(0.5), 0.62)
        self.assertAlmostEqual(game._actor_tint_value(1.0), 1.0)
        self.assertLess(game._actor_tint_value(0.0), game._actor_tint_value(0.5))

    def test_python_mirrors_are_in_sync_with_shader(self):
        from core import game
        shader = Path('assets/shaders/lighting.fs').read_text(encoding='utf-8')
        fall = float(re.search(r'const float FALL_RATE = ([0-9.]+)', shader).group(1))
        core = float(re.search(r'const float CORE_RATE = ([0-9.]+)', shader).group(1))
        self.assertEqual(game.SHADER_FALL_RATE, fall)
        self.assertEqual(game.SHADER_CORE_RATE, core)


class OutlineTests(unittest.TestCase):
    def test_outline_colour_decays_from_red_to_black(self):
        from core.render.frame_render import _outline_color
        idle = _outline_color(0.0)
        hit = _outline_color(0.5)
        self.assertEqual((idle.r, idle.g, idle.b), (0, 0, 0))
        self.assertGreater(hit.r, 0)
        self.assertLess(_outline_color(0.05).r, hit.r)

    def test_outline_is_world_only_post_pass(self):
        from core.game import Game
        game_source = Path('core/game.py').read_text(encoding='utf-8')
        frame_source = Path('core/render/frame_render.py').read_text(encoding='utf-8')
        self.assertIn("self._pp_outline = False", game_source)
        self.assertIn("if self._pp_outline and self.shaders.has('pp_outline')", game_source)
        self.assertLess(frame_source.index('self._apply_post_chain(cw, ch)'),
                        frame_source.index('self._draw_hud(cw, ch)'))
        self.assertTrue(hasattr(Game, '_draw_hud'))



    def test_gear_affixes_and_rolls_do_not_offer_haste(self):
        from systems import itemgen
        self.assertNotIn('cooldown_recovery', itemgen._AFFIX_BY_ID)
        self.assertFalse(any('haste' in a['label'].lower() for a in itemgen._AFFIXES))
        for seed in range(100):
            inst = itemgen.generate_instance('lungs', 20, rarity='legendary', equip_slot='lungs', seed=seed)
            self.assertNotIn('cooldown_recovery', inst['affixes']['suffixes'])
            self.assertNotIn('Haste', inst['display_name'])
        slot = itemgen.roll_for('lungs', 1, 20, seed=1)
        self.assertNotIn('ability', slot['instance_data'])



    def test_set_vec2_array_missing_uniform_is_silent(self):
        """Unknown/unloaded shader must not raise."""
        mgr = ShaderManager('assets/shaders')
        mgr.set_vec2_array('nope', 'u_light_pos', [(1.0, 2.0)])
        mgr.set_vec4_array('nope', 'u_light_data', [(1.0, 2.0, 3.0, 4.0)])


if __name__ == '__main__':
    unittest.main(verbosity=2)
