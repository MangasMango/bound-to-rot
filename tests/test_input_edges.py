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

"""Per-tick input edge latches (systems/input.py) - regression guards.

The 30 Hz fixed timestep makes game.update run zero ticks on most render
frames, so raw rl.is_key_pressed scans dropped most presses (the "hub input
is dead" bug). The latches in systems/input re-derive edges from persistent
down-state; these tests pin the edge semantics that keep hub/raid/menus
input alive.
"""

import unittest
from unittest.mock import patch

import pyray as rl

from systems import input as tick_input

MOUSE_L = rl.MOUSE_BUTTON_LEFT


def down(key, is_down):
    return patch.object(rl, 'is_key_down', lambda k: is_down if k == key else False)


def btn_down(button, is_down):
    return patch.object(rl, 'is_mouse_button_down',
                        lambda b: is_down if b == button else False)


class KeyEdgeTests(unittest.TestCase):
    def setUp(self):
        tick_input._key_prev.clear()
        tick_input._mouse_prev.clear()
        tick_input._mouse_release_prev.clear()
        tick_input._focus_was = True
        self._focus_patch = patch.object(rl, 'is_window_focused', return_value=True)
        self._focus_patch.start()

    def tearDown(self):
        self._focus_patch.stop()

    def test_press_seen_even_after_zero_tick_frames(self):
        """A key pressed and held across zero-tick frames still yields an edge
        on the first tick that queries it."""
        with down(rl.KEY_ESCAPE, True):
            self.assertTrue(tick_input.key_pressed('test', rl.KEY_ESCAPE))
            for _ in range(10):                     # further ticks in same press
                self.assertFalse(tick_input.key_pressed('test', rl.KEY_ESCAPE))

    def test_release_then_repress_gives_second_edge(self):
        with down(rl.KEY_ESCAPE, True):
            tick_input.key_pressed('test', rl.KEY_ESCAPE)
        with down(rl.KEY_ESCAPE, False):
            self.assertFalse(tick_input.key_pressed('test', rl.KEY_ESCAPE))
        with down(rl.KEY_ESCAPE, True):
            self.assertTrue(tick_input.key_pressed('test', rl.KEY_ESCAPE))

    def test_edge_consumed_once_across_consumers(self):
        """Two consumers in the same tick: first gets the edge, second does
        not (prevents the double-fire raw flags caused on multi-tick frames)."""
        with down(rl.KEY_I, True):
            self.assertTrue(tick_input.key_pressed('test', rl.KEY_I))
            self.assertFalse(tick_input.key_pressed('test', rl.KEY_I))

    def test_first_query_while_already_held_fires_once(self):
        """Matches the legacy _KeyEdge behavior: a key held at the very first
        query registers one edge, then stays quiet until re-pressed."""
        with down(rl.KEY_C, True):
            self.assertTrue(tick_input.key_pressed('test', rl.KEY_C))
            self.assertFalse(tick_input.key_pressed('test', rl.KEY_C))

    def test_unrelated_keys_do_not_interfere(self):
        with down(rl.KEY_S, True):
            self.assertTrue(tick_input.key_pressed('test', rl.KEY_S))
            self.assertFalse(tick_input.key_pressed('test', rl.KEY_C))


class MouseEdgeTests(unittest.TestCase):
    def setUp(self):
        tick_input._key_prev.clear()
        tick_input._mouse_prev.clear()
        tick_input._mouse_release_prev.clear()
        tick_input._focus_was = True
        self._focus_patch = patch.object(rl, 'is_window_focused', return_value=True)
        self._focus_patch.start()

    def tearDown(self):
        self._focus_patch.stop()

    def test_press_edge(self):
        with btn_down(MOUSE_L, True):
            self.assertTrue(tick_input.mouse_pressed('test', MOUSE_L))
            self.assertFalse(tick_input.mouse_pressed('test', MOUSE_L))

    def test_released_only_after_press_was_seen(self):
        """No spurious release for a button that was never pressed."""
        with btn_down(MOUSE_L, False):
            self.assertFalse(tick_input.mouse_released('test', MOUSE_L))
        with btn_down(MOUSE_L, True):
            self.assertTrue(tick_input.mouse_pressed('test', MOUSE_L))
        with btn_down(MOUSE_L, False):
            self.assertTrue(tick_input.mouse_released('test', MOUSE_L))
            self.assertFalse(tick_input.mouse_released('test', MOUSE_L))

    def test_pressed_and_released_in_same_tick(self):
        with btn_down(MOUSE_L, True):
            self.assertTrue(tick_input.mouse_pressed('test', MOUSE_L))
        with btn_down(MOUSE_L, False):
            self.assertTrue(tick_input.mouse_released('test', MOUSE_L))
            self.assertFalse(tick_input.mouse_pressed('test', MOUSE_L))

    def test_press_hold_release_pattern(self):
        """Press and release may land several ticks apart on different
        render frames; each edge fires exactly once."""
        with btn_down(MOUSE_L, True):
            self.assertTrue(tick_input.mouse_pressed('test', MOUSE_L))
            self.assertFalse(tick_input.mouse_released('test', MOUSE_L))
        with btn_down(MOUSE_L, False):
            self.assertTrue(tick_input.mouse_released('test', MOUSE_L))
    def test_independent_consumers_both_see_press_and_release(self):
        with btn_down(MOUSE_L, True):
            self.assertTrue(tick_input.mouse_pressed('a', MOUSE_L))
            self.assertTrue(tick_input.mouse_pressed('b', MOUSE_L))
        with btn_down(MOUSE_L, False):
            self.assertTrue(tick_input.mouse_released('a', MOUSE_L))
            self.assertTrue(tick_input.mouse_released('b', MOUSE_L))

    def test_focus_loss_resyncs_held_button_without_phantom_edge(self):
        with btn_down(MOUSE_L, True):
            self.assertTrue(tick_input.mouse_pressed('chart', MOUSE_L))
        with patch.object(rl, 'is_window_focused', return_value=False):
            self.assertFalse(tick_input.mouse_released('chart', MOUSE_L))
        with patch.object(rl, 'is_window_focused', return_value=True):
            self.assertFalse(tick_input.mouse_pressed('chart', MOUSE_L))


if __name__ == '__main__':
    unittest.main(verbosity=2)
