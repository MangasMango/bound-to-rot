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

"""Horde lever (console `horde <0..10>`) - wave size, default x10.

Owner ruling (issue #53): every delve wave spawns x10 by default;
HORDE_DEFAULT_MULT in core/game.py is the source of truth and
`core.delve_flow._delve_spawn_wave` consumes it after the 40-cap. The
console lever only overrides per delve ('horde 0' restores the default,
'horde 1' forces the old stock pacing for QA comparisons).
"""

import unittest

from core.game import HORDE_DEFAULT_MULT, STATE_HUB, STATE_PLAYING, Game


def _game(state=STATE_PLAYING, delve=True):
    game = Game.__new__(Game)
    game.state = state
    game._console_log = []
    game._delve = {} if delve else None
    return game


def _exec(game, cmd):
    game._exec_console(cmd)
    # latest appended entry is the output for the executed command
    return game._console_log[-1]


class HordeCommand(unittest.TestCase):
    def test_default_is_x10_even_without_an_override(self):
        """A fresh delve dict reports the owner-ruling default."""
        game = _game()
        self.assertEqual(HORDE_DEFAULT_MULT, 10.0)
        self.assertNotIn('_horde_mult', game._delve)
        out = _exec(game, 'horde')
        self.assertIn('x10', out)
        self.assertIn('horde <1..10>', out)

    def test_usable_only_inside_a_delve(self):
        self.assertEqual(_exec(_game(state=STATE_HUB), 'horde 5'),
                         'Not in raid')
        self.assertEqual(_exec(_game(state=STATE_PLAYING, delve=False),
                               'horde 5'), 'Not in raid')

    def test_explicit_override_sticks(self):
        game = _game()
        self.assertIn('x5', _exec(game, 'horde 5'))
        self.assertEqual(game._delve['_horde_mult'], 5)

    def test_zero_restores_the_default_by_dropping_the_override(self):
        game = _game()
        _exec(game, 'horde 5')
        out = _exec(game, 'horde 0')
        self.assertIn('default x10', out)
        self.assertNotIn('_horde_mult', game._delve)
        self.assertIn('x10', _exec(game, 'horde'))

    def test_one_forces_old_stock_pacing(self):
        """`horde 1` remains a real override for QA comparisons."""
        game = _game()
        _exec(game, 'horde 1')
        self.assertEqual(game._delve['_horde_mult'], 1)

    def test_above_10_clamps(self):
        game = _game()
        _exec(game, 'horde 999')
        self.assertEqual(game._delve['_horde_mult'], 10)

    def test_non_numeric_arg_prints_usage(self):
        self.assertIn('Usage: horde <1..10>', _exec(_game(), 'horde lots'))


if __name__ == '__main__':
    unittest.main()
