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

"""Console `help` text matches the real command list - issue #4.

Covers:
  1. `money` is NOT advertised - the gold economy was retired by ruling
     (BLUEPRINT §2/§18) and the handler no longer exists.
  2. `descend <attr> <0..10>` matches the handler's actual range
     (ATTR_CAP = 10, usage string '0..10').
  3. Every help-advertised command name is a real handler branch.
"""

import unittest
from unittest import mock

from core.game import STATE_PLAYING, Game
from entities.descend import ATTR_CAP


def _game():
    """A Game stripped to what _exec_console touches."""
    game = Game.__new__(Game)
    game.state = STATE_PLAYING
    game._console_log = []
    return game


def _exec(game, cmd):
    game._exec_console(cmd)
    # log layout: [(prompt, output), (command, output), ...] - output of the
    # executed command is the last appended entry.
    return game._console_log[-1]


class HelpText(unittest.TestCase):
    def test_help_does_not_advertise_money(self):
        """No gold/money command: banned economy must not resurface in help."""
        self.assertNotIn('money', _exec(_game(), 'help'))

    def test_help_descend_range_matches_handler(self):
        """Help must say 0..10 (ATTR_CAP), the same range the handler clamps to."""
        self.assertIn('descend <attr> <0..10>', _exec(_game(), 'help'))

    def test_help_advertises_real_commands(self):
        """Each bare command word the help shows has a handler branch."""
        text = _exec(_game(), 'help')
        for known in ('god', 'heal', 'kill', 'give', 'zoom', 'descend',
                      'perk', 'pp', 'pp_bloom', 'weather', 'horde'):
            self.assertIn(known, text)


class DescendCommand(unittest.TestCase):
    def setUp(self):
        self.game = _game()
        # `Game.char` is a read-only property over char_mgr.active
        self.game.char_mgr = mock.Mock()
        self.game.char_mgr.active = mock.Mock()
        self.game.char_mgr.active.descend = {}
        self.game._recalc_derived_stats = mock.Mock()

    def test_descend_accepts_cap_value(self):
        """0..10 is the accepted range - the cap itself must be legal."""
        self.assertIn('dexterity = ', _exec(self.game, 'descend dexterity 10'))
        char = self.game.char_mgr.active
        self.assertEqual(char.descend['dexterity'], ATTR_CAP)
        self.game._recalc_derived_stats.assert_called_once()
        self.game.char_mgr.save.assert_called_once()

    def test_descend_range_matches_help_and_usage(self):
        """Handler usage string and ATTR_CAP agree on 10."""
        self.assertEqual(ATTR_CAP, 10)
        self.assertIn('<0..10>',
                      _exec(self.game, 'descend dexterity notanumber'))

    def test_descend_clamps_above_cap(self):
        _exec(self.game, 'descend nerve 11')
        self.assertEqual(self.game.char_mgr.active.descend['nerve'], ATTR_CAP)


if __name__ == '__main__':
    unittest.main()
