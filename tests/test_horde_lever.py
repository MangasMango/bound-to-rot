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

"""Horde QA lever (console `horde <1..10>`) - wave-size experiment.

Covers the console surface. The lever itself is applied in
`core.delve_flow._delve_spawn_wave`, which multiplies the depth-capped
base count AFTER the 40-cap (QA backdoor per rule 44, not progression).
"""

import unittest

from core.game import STATE_HUB, STATE_PLAYING, Game


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
    def test_status_reports_default_and_usage(self):
        out = _exec(_game(), 'horde')
        self.assertIn('x1', out)
        self.assertIn('horde <1..10>', out)

    def test_usable_only_inside_a_delve(self):
        self.assertEqual(_exec(_game(state=STATE_HUB), 'horde 5'),
                         'Not in raid')
        self.assertEqual(_exec(_game(state=STATE_PLAYING, delve=False),
                               'horde 5'), 'Not in raid')

    def test_scales_wave_size(self):
        game = _game()
        self.assertIn('x10', _exec(game, 'horde 10'))
        self.assertEqual(game._delve['_horde_mult'], 10)

    def test_zero_resets_to_stock(self):
        game = _game()
        _exec(game, 'horde 10')
        self.assertEqual(_exec(game, 'horde 0'),
                         'Wave size x1 from the next wave on')
        self.assertEqual(game._delve['_horde_mult'], 1)

    def test_above_10_clamps(self):
        game = _game()
        _exec(game, 'horde 999')
        self.assertEqual(game._delve['_horde_mult'], 10)

    def test_non_numeric_arg_prints_usage(self):
        self.assertIn('Usage: horde <1..10>', _exec(_game(), 'horde lots'))


if __name__ == '__main__':
    unittest.main()
