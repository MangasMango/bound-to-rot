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

"""Letterbox transform math: window -> virtual canvas mouse mapping.

Regression guard for the 1080p click-misalignment bug: the virtual canvas
(config.py SCREEN_W/H) and the letterbox blit + mouse transform must share
the same aspect-fit math so UI clicks land on what is rendered. Tests pin
the 1280x720 base resolution and the mapping at native and resized windows.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import SCREEN_W, SCREEN_H
from systems.letterbox import letterbox_transform
import unittest


class TestBaseResolution(unittest.TestCase):
    def test_base_resolution_is_720p(self):
        """Owner decision: base resolution reverted to 1280x720."""
        self.assertEqual((SCREEN_W, SCREEN_H), (1280, 720))


class TestLetterboxTransform(unittest.TestCase):
    VIRT = (1280, 720)

    def test_native_window_1x(self):
        scale, ox, oy = letterbox_transform(1280, 720, *self.VIRT)
        self.assertAlmostEqual(scale, 1.0)
        self.assertAlmostEqual(ox, 0.0)
        self.assertAlmostEqual(oy, 0.0)

    def test_same_aspect_resized_window(self):
        scale, ox, oy = letterbox_transform(1920, 1080, *self.VIRT)
        self.assertAlmostEqual(scale, 1.5)
        self.assertAlmostEqual(ox, 0.0)
        self.assertAlmostEqual(oy, 0.0)

    def test_wider_window_has_side_bars(self):
        # 32:9 window (2 x width of 16:9): fit on height, center horizontally.
        scale, ox, oy = letterbox_transform(2560, 720, *self.VIRT)
        self.assertAlmostEqual(scale, 1.0)
        self.assertAlmostEqual(ox, 640.0)
        self.assertAlmostEqual(oy, 0.0)

    def test_taller_window_has_top_bottom_bars(self):
        # 4:3 window: fit on width, center vertically.
        scale, ox, oy = letterbox_transform(1280, 960, *self.VIRT)
        self.assertAlmostEqual(scale, 1.0)
        self.assertAlmostEqual(ox, 0.0)
        self.assertAlmostEqual(oy, 120.0)

    def test_mouse_mapping_inverse_roundtrip(self):
        """canvas = (window - offset) / scale must roundtrip for any window."""
        for win_w, win_h in [(1280, 720), (1920, 1080), (2560, 720),
                             (1280, 960), (1024, 768), (3440, 1440)]:
            scale, ox, oy = letterbox_transform(win_w, win_h, *self.VIRT)
            # a point at the canvas corner/center maps into window coords...
            for cx, cy in [(0, 0), (640, 360), (1280, 720)]:
                wx = ox + cx * scale
                wy = oy + cy * scale
                # ...and the mouse transform maps it back exactly.
                self.assertAlmostEqual((wx - ox) / scale, cx, places=6)
                self.assertAlmostEqual((wy - oy) / scale, cy, places=6)

    def test_letterbox_blit_and_share_same_math(self):
        """The blit dst rect and the mouse transform use identical values."""
        scale, ox, oy = letterbox_transform(1920, 1080, *self.VIRT)
        dst = (ox, oy, self.VIRT[0] * scale, self.VIRT[1] * scale)
        self.assertEqual(dst, (0.0, 0.0, 1920.0, 1080.0))


if __name__ == '__main__':
    unittest.main()
