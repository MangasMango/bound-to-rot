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

"""Missing-asset detection (systems/asset_guard.py).

The excluded packs are gitignored, so a CI checkout has README-only folders;
these tests use temp roots so they behave identically on dev machines.
"""

import os
import tempfile
import unittest

from systems import asset_guard


class TestExcludedDirs(unittest.TestCase):
    def test_expected_six_folders(self):
        self.assertEqual(len(asset_guard.EXCLUDED_ASSET_DIRS), 6)
        for name in ('boss', 'environment', 'enemy', 'none-playable character',
                     'playable character', 'prop'):
            self.assertIn(name, asset_guard.EXCLUDED_ASSET_DIRS)


class TestMissingDetection(unittest.TestCase):
    def _root(self, spec):
        """Build a temp assets root. spec: {folder: [files]} — folder None = absent."""
        tmp = tempfile.mkdtemp()
        for name, files in spec.items():
            d = os.path.join(tmp, name)
            if files is None:
                continue
            os.makedirs(d, exist_ok=True)
            for f in files:
                with open(os.path.join(d, f), 'w') as fh:
                    fh.write('x')
        return tmp

    def test_all_readme_only_counts_as_missing(self):
        root = self._root({name: ['README.md']
                           for name in asset_guard.EXCLUDED_ASSET_DIRS})
        self.assertEqual(sorted(asset_guard.missing_asset_folders(root)),
                         sorted(asset_guard.EXCLUDED_ASSET_DIRS))

    def test_real_content_not_missing(self):
        spec = {name: ['frame.png']
                for name in asset_guard.EXCLUDED_ASSET_DIRS}
        root = self._root(spec)
        self.assertEqual(asset_guard.missing_asset_folders(root), [])

    def test_absent_folder_is_missing(self):
        self.assertEqual(asset_guard.missing_asset_folders('/nonexistent'), 
                         list(asset_guard.EXCLUDED_ASSET_DIRS))

    def test_readme_case_insensitive_and_hidden_files_ignored(self):
        spec = {name: ['x.png']
                for name in asset_guard.EXCLUDED_ASSET_DIRS}
        spec['boss'] = ['ReadMe.MD', '.gitkeep']
        root = self._root(spec)
        self.assertEqual(asset_guard.missing_asset_folders(root), ['boss'])

    def test_partial_repo_missing_reported(self):
        root = self._root({'boss': ['demonlord.png'],
                           'enemy': ['README.md'],
                           'environment': ['ground.png'],
                           'none-playable character': ['README.md'],
                           'playable character': ['knight.png'],
                           'prop': ['README.md']})
        self.assertEqual(
            sorted(asset_guard.missing_asset_folders(root)),
            ['enemy', 'none-playable character', 'prop'])


class TestNotice(unittest.TestCase):
    def test_notice_lists_folders_and_docs(self):
        text = asset_guard.missing_notice(['boss', 'prop'])
        self.assertIn('boss', text)
        self.assertIn('prop', text)
        self.assertIn('THIRD_PARTY_ASSETS.md', text)
        self.assertIn('placeholder', text)

    def test_kind_classification(self):
        self.assertEqual(asset_guard._kind_for('knight_armed_idle'), 'player')
        self.assertEqual(asset_guard._kind_for('skeleton_default_walk'), 'enemy')
        self.assertEqual(asset_guard._kind_for('sk_idle'), 'enemy')
        self.assertEqual(asset_guard._kind_for('sl_death'), 'enemy')
        self.assertEqual(asset_guard._kind_for('crate_1'), 'prop')
        self.assertEqual(asset_guard._kind_for('gold_drop'), 'prop')
        self.assertEqual(asset_guard._kind_for('subservient_special_working'), 'npc')
        self.assertEqual(asset_guard._kind_for('mystery'), 'generic')

    def test_placeholders_headless_return_none(self):
        # No GL context in tests → placeholders refuse to build,
        # and IsoSprite keeps its empty-frames (invisible) behaviour.
        self.assertIsNone(asset_guard.entity_placeholder('skeleton'))


if __name__ == '__main__':
    unittest.main()
