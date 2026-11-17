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

"""Creation baseline and UI flow tests (issue #103, updated for #31)."""

import unittest
from unittest import mock

from entities.descend import DESCEND_ATTRIBUTES, vessel_baseline_stats
from entities.progression import Character, CharacterManager
from systems.xp import MAX_LEVEL
from ui.menus import MenuSystem


class CharacterCreationBaselineTests(unittest.TestCase):
    def _manager(self):
        manager = CharacterManager.__new__(CharacterManager)
        manager.characters = []
        manager.active_idx = 0
        manager.unlocked_vessels = ['knight', 'warrior', 'fighter']
        manager.save = mock.Mock()
        return manager

    def test_every_vessel_creates_zeroed_at_level_1(self):
        # Owner ruling (issue #31): vessels grant NO attribute baselines -
        # every attribute starts at 0 and points come from level-ups only.
        for looks in ('knight', 'warrior', 'fighter'):
            with self.subTest(looks=looks):
                manager = self._manager()
                char = manager.create('Vessel Pilot', looks)
                self.assertEqual(char.descend, vessel_baseline_stats(looks))
                self.assertEqual({k: v for k, v in char.descend.items() if v}, {})
                self.assertEqual(set(char.descend), set(DESCEND_ATTRIBUTES))
                self.assertEqual(char.available_points, 0)
                self.assertEqual(char.level, 1)
                self.assertEqual(char.xp, 0)

    def test_start_creates_directly_without_allocation_state(self):
        manager = self._manager()
        text_input = mock.Mock()
        menu = MenuSystem.__new__(MenuSystem)
        menu.char_mgr = manager
        menu._char_name = '  Vessel Pilot  '
        menu._char_looks = 'knight'
        menu.char_name_input = text_input

        MenuSystem._do_create(menu)

        self.assertEqual(manager.characters[0].name, 'Vessel Pilot')
        self.assertEqual(menu.state, 'characters')
        self.assertFalse(hasattr(menu, '_creation_mode'))
        text_input.clear.assert_called_once_with()

    def test_old_save_is_rejected_without_crashing(self):
        with self.assertRaises(ValueError):
            Character.from_dict({'id': 'legacy', 'name': 'Legacy', 'xp': 99})

    def test_new_character_save_carries_level_and_xp(self):
        data = Character('fresh', 'Fresh', 'knight').to_dict()
        self.assertEqual(data['level'], 1)
        self.assertEqual(data['xp'], 0)

    def test_from_dict_clamps_nonsense_level_xp(self):
        c = Character.from_dict({'id': 'x', 'name': 'X', 'looks': 'knight',
                                 'descend': {}, 'perks': {},
                                 'available_points': 0,
                                 'inventory': None, 'stash': [],
                                 'level': 9999, 'xp': -5})
        self.assertEqual(c.level, MAX_LEVEL)
        self.assertEqual(c.xp, 0)


class CharCursorSyncTests(unittest.TestCase):
    """The characters-screen cursor follows active_idx (issue #69).

    The manager was never wrong: create() appends and points active_idx at
    the new character. The menu cursor, however, stayed wherever it was -
    and Play/Enter select the CURSOR, so a fresh character was never the
    one that launched."""

    def _menu(self, manager):
        menu = MenuSystem.__new__(MenuSystem)
        menu.char_mgr = manager
        menu._char_sel_idx = 0
        menu._char_name = ''
        menu._char_looks = 'knight'
        menu.char_name_input = mock.Mock()
        return menu

    def test_create_puts_the_cursor_on_the_new_character(self):
        manager = CharacterManager.__new__(CharacterManager)
        manager.characters = [Character('First', looks='knight')]
        manager.active_idx = 0
        manager.unlocked_vessels = ['knight', 'warrior', 'fighter']
        manager.save = mock.Mock()
        menu = self._menu(manager)
        menu.state = 'char_create'
        menu._char_name = 'Second'

        MenuSystem._do_create(menu)

        self.assertEqual(len(manager.characters), 2)
        self.assertEqual(manager.active_idx, 1)
        # simulate the state-entry hook that update() runs on 'characters'
        menu._sync_char_cursor()
        self.assertEqual(menu._char_sel_idx, 1)
        # what Play/Enter actually do: select the cursor - now the NEW char
        manager.select(menu._char_sel_idx)
        self.assertIs(manager.active, manager.characters[1])

    def test_stale_cursor_resyncs_on_reentry(self):
        manager = CharacterManager.__new__(CharacterManager)
        manager.characters = [Character('First', looks='knight'),
                              Character('Second', looks='warrior')]
        manager.active_idx = 1
        manager.unlocked_vessels = ['knight', 'warrior', 'fighter']
        manager.save = mock.Mock()
        menu = self._menu(manager)
        menu._char_sel_idx = 0   # stale (e.g. left the screen mid-scroll)

        menu._sync_char_cursor()

        self.assertEqual(menu._char_sel_idx, 1)

    def test_delete_clamps_the_cursor_to_a_real_entry(self):
        manager = CharacterManager.__new__(CharacterManager)
        manager.characters = [Character('First', looks='knight'),
                              Character('Second', looks='warrior')]
        manager.active_idx = 0
        manager.unlocked_vessels = ['knight', 'warrior', 'fighter']
        manager.save = mock.Mock()
        menu = self._menu(manager)
        menu._char_sel_idx = 0

        manager.delete(0)
        menu._sync_char_cursor()

        self.assertEqual(len(manager.characters), 1)
        self.assertEqual(menu._char_sel_idx, 0)
        self.assertIs(manager.active, manager.characters[0])

    def test_empty_roster_keeps_the_cursor_at_zero(self):
        manager = CharacterManager.__new__(CharacterManager)
        manager.characters = []
        manager.active_idx = 0
        manager.unlocked_vessels = ['knight', 'warrior', 'fighter']
        manager.save = mock.Mock()
        menu = self._menu(manager)
        menu._char_sel_idx = 3   # stale beyond the end

        menu._sync_char_cursor()

        self.assertEqual(menu._char_sel_idx, 0)

    def test_manager_create_contract_is_untouched(self):
        """Guard: the fix lives in the menu layer, not the manager."""
        manager = CharacterManager.__new__(CharacterManager)
        manager.characters = []
        manager.active_idx = 0
        manager.unlocked_vessels = ['knight', 'warrior', 'fighter']
        manager.save = mock.Mock()

        char = manager.create('Third', 'fighter')

        self.assertIs(manager.characters[-1], char)
        self.assertEqual(manager.active_idx, 0)   # index OF the new char

    def test_create_syncs_the_cursor_without_the_entry_hook(self):
        """The state transition happens INSIDE _do_create, mid-tick -
        update()'s entry hook compares before the handler runs and
        _last_state catches up at the end of the same tick, so the hook
        never fires for this transition. The sync must be explicit."""
        manager = CharacterManager.__new__(CharacterManager)
        manager.characters = [Character('First', looks='knight')]
        manager.active_idx = 0
        manager.unlocked_vessels = ['knight', 'warrior', 'fighter']
        manager.save = mock.Mock()
        menu = self._menu(manager)
        menu.state = 'char_create'
        menu._char_name = 'Second'
        menu._char_sel_idx = 0

        MenuSystem._do_create(menu)

        self.assertEqual(menu.state, 'characters')
        self.assertEqual(menu._char_sel_idx, 1)   # no entry hook needed


if __name__ == '__main__':
    unittest.main()
