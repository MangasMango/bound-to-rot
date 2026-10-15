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

"""Regression tests for item/depth progression and incompatible save handling."""

import json
from pathlib import Path
from unittest import mock

from core.delve_gen import effective_level
from entities.progression import Character, CharacterManager
from entities.zombies import enemy_evasion
from systems.combat import skeleton_accuracy


def test_new_save_has_no_character_level_or_xp():
    data = Character('fresh', 'Fresh', 'knight').to_dict()
    assert 'level' not in data
    assert 'xp' not in data


def test_old_format_save_starts_fresh_without_crashing(tmp_path):
    old_path = tmp_path / 'characters.json'
    old_path.write_text(json.dumps({
        'characters': [{'id': 'old', 'name': 'Old', 'looks': 'knight', 'xp': 999}],
    }))
    with mock.patch('entities.progression.CHARS_PATH', str(old_path)):
        manager = CharacterManager()
    assert manager.characters == []
    assert manager.active is None


def test_monster_difficulty_and_item_level_are_driven_by_depth():
    shallow, deep = effective_level(1), effective_level(30)
    assert deep > shallow
    assert enemy_evasion('skeleton', deep) > enemy_evasion('skeleton', shallow)
    assert skeleton_accuracy(deep) > skeleton_accuracy(shallow)
