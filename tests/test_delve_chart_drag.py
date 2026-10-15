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

import unittest
from unittest.mock import patch

import ui.delve_chart as chart_mod
from ui.delve_chart import DelveChartScreen


class DelveChartDragTests(unittest.TestCase):
    def setUp(self):
        chart_mod.inp._key_prev.clear()
        chart_mod.inp._mouse_prev.clear()
        chart_mod.inp._mouse_release_prev.clear()
        chart_mod.inp._focus_was = True
        self.screen = DelveChartScreen(object())
        self.screen.open({
            'graph': {'nodes': {}, 'edges': []},
            'visited': [], 'looted': [], 'checkpoints': [], 'route': [],
            'charges': {}}, selectable_ids=('node',), on_select=lambda _nid: None)

    def _update(self, x, y, down=False, released=False, focused=True):
        # Use the real edge module: a competing consumer polls the same button
        # first, proving the chart still receives its own press and release.
        with patch.object(chart_mod.rl, 'get_screen_width', return_value=800), \
             patch.object(chart_mod.rl, 'get_screen_height', return_value=600), \
             patch.object(chart_mod.rl, 'get_mouse_x', return_value=x), \
             patch.object(chart_mod.rl, 'get_mouse_y', return_value=y), \
             patch.object(chart_mod.rl, 'is_window_focused', return_value=focused), \
             patch.object(chart_mod.rl, 'is_mouse_button_down', return_value=(not released and down)):
            chart_mod.inp.mouse_pressed('test-competitor', chart_mod.rl.MOUSE_BUTTON_LEFT)
            chart_mod.inp.mouse_released('test-competitor', chart_mod.rl.MOUSE_BUTTON_LEFT)
            return self.screen.update(0.016, view=(800, 600))

    def test_release_ends_drag_and_stops_panning(self):
        self._update(100, 100, down=True)
        self.assertIsNotNone(self.screen._drag_start)
        self._update(140, 100, down=True)
        self.assertTrue(self.screen._dragged)
        before = self.screen.cam_x
        self._update(140, 100, released=True)
        self.assertIsNone(self.screen._drag_start)
        self.assertFalse(self.screen._dragged)
        self._update(220, 100)
        self.assertEqual(self.screen.cam_x, before)

    def test_release_while_outside_clears_drag_before_reopen(self):
        self._update(100, 100, down=True)
        self._update(140, 100, down=True)
        # close/reopen is represented by open()
        self._update(1000, 1000, released=True)
        self.assertIsNone(self.screen._drag_start)
        self.screen.open(self.screen.chart, selectable_ids=())
        self.assertIsNone(self.screen._drag_start)

    def test_node_selection_clears_drag(self):
        self._update(100, 100, down=True)
        self._update(140, 100, down=True)
        # A selectable node selection is an early-return interaction.
        self.screen._tooltip_btn = ((0, 0, 20, 20), 'node')
        with patch.object(chart_mod.rl, 'check_collision_point_rec', return_value=True), \
             patch.object(chart_mod.rl, 'is_mouse_button_down', return_value=True), \
             patch.object(chart_mod.rl, 'is_window_focused', return_value=True), \
             patch.object(chart_mod.rl, 'get_mouse_x', return_value=5), \
             patch.object(chart_mod.rl, 'get_mouse_y', return_value=5):
            chart_mod.inp._mouse_prev.clear()
            result = self.screen.update(0.016, view=(800, 600))
        self.assertEqual(result, ('select', 'node'))
        self.assertIsNone(self.screen._drag_start)
        self.assertFalse(self.screen._dragged)


if __name__ == '__main__':
    unittest.main()
