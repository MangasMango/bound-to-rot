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

"""Player-facing enemy names - #53 follow-up ruling.

Display rule: the player never sees the internal enemy_type keys. The
keys themselves are load-bearing (assets/enemy/<key> sprite folders,
combat helpers, frame tuning) and stay 'skeleton' / 'slime' / ...
"""

import unittest

from entities.zombies import ENEMY_DISPLAY_NAMES, enemy_display_name


class EnemyDisplayNames(unittest.TestCase):
    def test_ruling_names(self):
        """skeleton shows as Undead; slime shows as Slow Undead."""
        self.assertEqual(ENEMY_DISPLAY_NAMES['skeleton'], 'Undead')
        self.assertEqual(ENEMY_DISPLAY_NAMES['slime'], 'Slow Undead')
        self.assertEqual(enemy_display_name('skeleton'), 'Undead')
        self.assertEqual(enemy_display_name('slime'), 'Slow Undead')

    def test_internal_keys_unchanged(self):
        """The load-bearing keys must not be renamed (sprites/combat key on
        them); only the display map changes."""
        self.assertIn('skeleton', ENEMY_DISPLAY_NAMES)
        self.assertIn('slime', ENEMY_DISPLAY_NAMES)

    def test_unknown_key_falls_back_to_capitalized(self):
        self.assertEqual(enemy_display_name('zombie_licker'),
                         'Zombie_licker')
        self.assertEqual(enemy_display_name('boss'), 'Boss')

    def test_empty_name_falls_back(self):
        self.assertEqual(enemy_display_name(None), 'enemy')
        self.assertEqual(enemy_display_name(''), 'enemy')

    def test_no_raw_internal_key_reaches_the_log(self):
        """The combat-log surface leaks no raw keys: every site in
        core/game.py that formats a kill/hit/immune line uses the helper."""
        import re
        from pathlib import Path
        # scan the source for raw enemy_type interpolation inside log calls
        src = (Path(__file__).resolve().parents[1] / 'core' / 'game.py').read_text()
        raw_pattern = re.compile(r"_log_combat\(f\"[^\"]*\{z\.get\('enemy_type'|"
                                 r"_log_combat\(f\"[^\"]*\{candidate\.get\('enemy_type'")
        self.assertEqual(raw_pattern.findall(src), [])


if __name__ == '__main__':
    unittest.main()
