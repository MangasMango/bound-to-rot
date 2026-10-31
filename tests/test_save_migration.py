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

"""Save schema versioning and migration chain (issue #126).

Covers the standing owner policy: a player save is upgraded in place, never
silently discarded, and a save that cannot be migrated is backed up and
reported instead of wiped.
"""

import copy
import json
import os
import tempfile
import unittest
import unittest.mock as mock

import entities.progression as prog


def _character_payload(**overrides) -> dict:
    """A character dict in the current save format, with recognisable data."""
    payload = {
        'id': 'char-migrate-1',
        'name': 'Operative',
        'looks': 'knight',
        'descend': {'strength': 4, 'endurance': 2},
        'perks': {'p1': 2},
        'available_points': 3,
        'inventory': {'grid': [{'item': 'sword', 'count': 1, 'col': 0, 'row': 0}]},
        # v1/v2 stash shape: four tabs. The v2->v3 step flattens it to one grid.
        'stash': [[{'item': 'potion', 'count': 2, 'col': 0, 'row': 0}], [], [], []],
    }
    payload.update(overrides)
    return payload


def _v2_save() -> dict:
    """A schema-v2 save: four stash tabs of 12x5 grids."""
    return {
        'save_schema_version': 2,
        'active_idx': 0,
        'unlocked_vessels': ['knight'],
        'best_depth': 3,
        'characters': [copy.deepcopy(_character_payload(stash=[
            [{'item': 'potion', 'count': 2, 'col': 0, 'row': 0},
             {'item': 'lungs', 'count': 1, 'col': 11, 'row': 4}],
            [{'item': 'heart', 'count': 1, 'col': 5, 'row': 2}],
            [],
            [],
        ]))],
    }


def _v1_save() -> dict:
    """A pre-framework save: legacy ``format_version`` plus retired fields."""
    return {
        'format_version': 1,
        'active_idx': 0,
        'unlocked_vessels': ['knight', 'seer'],
        'best_depth': 7,
        'characters': [copy.deepcopy(_character_payload(
            currency=4321,   # retired legacy field: preserved, never read
            level=12, xp=340, unlocked_nodes=['start', 'node_a'],
            skill_slots=[{'item': 'gem_01'}], flasks=[], belt=[],
        ))],
    }


def _current_save(version: int = None) -> dict:
    return {
        'save_schema_version': version if version is not None else prog.SAVE_SCHEMA_VERSION,
        'active_idx': 0,
        'unlocked_vessels': ['knight'],
        'best_depth': 3,
        'characters': [copy.deepcopy(_character_payload())],
    }


class SaveSchemaVersionTests(unittest.TestCase):
    def test_single_named_constant_defines_current_version(self):
        self.assertIsInstance(prog.SAVE_SCHEMA_VERSION, int)
        self.assertGreaterEqual(prog.SAVE_SCHEMA_VERSION, 1)
        # The legacy alias must track the single source of truth.
        self.assertEqual(prog.SAVE_FORMAT_VERSION, prog.SAVE_SCHEMA_VERSION)

    def test_current_version_is_at_the_end_of_the_chain(self):
        self.assertEqual(prog.supported_versions()[-1], prog.SAVE_SCHEMA_VERSION)

    def test_chain_is_contiguous_from_first_version(self):
        versions = prog.supported_versions()
        self.assertEqual(versions, list(range(versions[0], versions[-1] + 1)))


class MigrateOlderVersionsTests(unittest.TestCase):
    def test_every_supported_older_version_migrates_to_current(self):
        older = [v for v in prog.supported_versions() if v < prog.SAVE_SCHEMA_VERSION]
        self.assertTrue(older, 'expected at least one older supported version')
        for version in older:
            with self.subTest(version=version):
                save = _v1_save() if version == 1 else _current_save(version)
                if version != 1:
                    save.pop('save_schema_version')
                    save['format_version'] = version
                migrated = prog.migrate_save(save)
                self.assertEqual(migrated['save_schema_version'], prog.SAVE_SCHEMA_VERSION)

    def test_migrated_character_data_is_preserved(self):
        migrated = prog.migrate_save(_v1_save())
        entry = migrated['characters'][0]
        for key in ('id', 'name', 'looks', 'currency', 'descend',
                    'perks', 'available_points', 'inventory', 'stash'):
            self.assertIn(key, entry)
        self.assertEqual(entry['currency'], 4321)
        self.assertEqual(entry['descend'], {'strength': 4, 'endurance': 2})
        self.assertEqual(entry['perks'], {'p1': 2})
        self.assertEqual(entry['available_points'], 3)
        self.assertEqual(entry['inventory']['grid'][0]['item'], 'sword')
        self.assertIsInstance(entry['stash'], list)
        self.assertEqual(entry['stash'][0]['item'], 'potion')
        self.assertEqual(migrated['best_depth'], 7)
        self.assertEqual(migrated['unlocked_vessels'], ['knight', 'seer'])

    def test_retired_fields_are_dropped_by_migration(self):
        entry = prog.migrate_save(_v1_save())['characters'][0]
        for key in ('level', 'xp', 'unlocked_nodes', 'skill_slots', 'flasks', 'belt'):
            self.assertNotIn(key, entry)

    def test_migrated_save_loads_into_real_characters(self):
        manager = prog.CharacterManager.__new__(prog.CharacterManager)
        manager.characters = []
        manager.active_idx = 0
        manager.unlocked_vessels = ['knight']
        manager.best_depth = 0
        manager.load_error = ''
        manager.load_error_backup = ''
        manager.migrated_from_version = prog.SAVE_SCHEMA_VERSION
        with mock.patch.object(prog, 'CHARS_PATH', self._path(_v1_save())) as path, \
             mock.patch.object(prog, 'BACKUP_DIR', os.path.join(os.path.dirname(path), 'backups')):
            manager.load()
            self.assertEqual(manager.load_error, '')
            self.assertEqual(manager.migrated_from_version, 1)
            self.assertEqual(len(manager.characters), 1)
            self.assertEqual(manager.characters[0].name, 'Operative')
            # The migrated payload is persisted immediately, in current format.
            with open(path) as f:
                on_disk = json.load(f)
            self.assertEqual(on_disk['save_schema_version'], prog.SAVE_SCHEMA_VERSION)
            self.assertEqual(on_disk['characters'][0]['name'], 'Operative')

    @staticmethod
    def _path(payload) -> str:
        handle = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False)
        json.dump(payload, handle)
        handle.close()
        return handle.name


class MigrateV2ToV3Tests(unittest.TestCase):
    """v2 -> v3: the four stash tabs collapse into a single 8x8 bank grid."""

    def test_tabs_flatten_into_one_grid_and_relocate_out_of_bounds(self):
        migrated = prog.migrate_save(_v2_save())
        entry = migrated['characters'][0]
        self.assertEqual(migrated['save_schema_version'], 3)
        bank = entry['stash']
        self.assertIsInstance(bank, list)
        items = [slot['item'] for slot in bank]
        self.assertEqual(items, ['potion', 'lungs', 'heart'],
                         'tab order is preserved in the flattened bank')
        for slot in bank:
            col, row = slot['col'], slot['row']
            self.assertGreaterEqual(col, 0)
            self.assertLess(col, prog.GRID_COLS)
            self.assertGreaterEqual(row, 0)
            self.assertLess(row, prog.GRID_ROWS)

    def test_every_cell_inside_the_8x8_bounds(self):
        payload = _v2_save()
        # A 1x1 item parked at the far corner of the old 12x5 tab
        payload['characters'][0]['stash'][0].append(
            {'item': 'liver', 'count': 1, 'col': 11, 'row': 4})
        migrated = prog.migrate_save(payload)
        bank = migrated['characters'][0]['stash']
        self.assertEqual(len(bank), 4)
        for slot in bank:
            self.assertLess(slot['col'], prog.GRID_COLS)
            self.assertLess(slot['row'], prog.GRID_ROWS)

    def test_overflow_beyond_64_cells_is_discarded(self):
        payload = _v2_save()
        payload['characters'][0]['stash'] = [
            [{'item': 'liver', 'count': 1, 'col': c % 12, 'row': r}
             for r in range(7) for c in range(12)]
        ]
        migrated = prog.migrate_save(payload)
        bank = migrated['characters'][0]['stash']
        self.assertEqual(len(bank), prog.GRID_COLS * prog.GRID_ROWS)
        self.assertTrue(all(s['item'] == 'liver' for s in bank))


class IdempotencyTests(unittest.TestCase):
    def test_current_save_is_untouched(self):
        save = _current_save()
        before = copy.deepcopy(save)
        result = prog.migrate_save(save)
        self.assertEqual(result, before)
        self.assertIs(result, save)

    def test_running_the_chain_twice_yields_the_same_result(self):
        first = prog.migrate_save(_v1_save())
        second = prog.migrate_save(copy.deepcopy(first))
        self.assertEqual(first, second)

    def test_migration_chain_is_empty_at_current_version(self):
        self.assertEqual(prog.migration_chain(prog.SAVE_SCHEMA_VERSION), [])

    def test_registered_step_reached_by_chain(self):
        step = prog._MIGRATIONS[1]
        self.assertIn(step, prog.migration_chain(1))


class UnsafeSaveTests(unittest.TestCase):
    def test_future_version_is_rejected_without_data_loss(self):
        save = _current_save(version=prog.SAVE_SCHEMA_VERSION + 5)
        save['characters'][0]['perks'] = {'p1': 9}
        with self.assertRaises(prog.SaveMigrationError):
            prog.migrate_save(save)
        # Nothing was mutated: the caller's data is unchanged.
        self.assertEqual(save['characters'][0]['perks'], {'p1': 9})
        self.assertEqual(save['save_schema_version'], prog.SAVE_SCHEMA_VERSION + 5)

    def test_non_numeric_version_is_rejected(self):
        with self.assertRaises(prog.SaveMigrationError):
            prog.migrate_save({'save_schema_version': 'two', 'characters': []})

    def test_non_dict_payload_is_rejected(self):
        with self.assertRaises(prog.SaveMigrationError):
            prog.migrate_save([1, 2, 3])

    def test_known_future_version_manager_backs_up_and_reports(self):
        directory = tempfile.mkdtemp()
        path = os.path.join(directory, 'characters.json')
        payload = _current_save(version=prog.SAVE_SCHEMA_VERSION + 3)
        with open(path, 'w') as f:
            json.dump(payload, f)

        manager = prog.CharacterManager.__new__(prog.CharacterManager)
        manager.characters = []
        manager.active_idx = 0
        manager.unlocked_vessels = ['knight']
        manager.best_depth = 0
        manager.load_error = ''
        manager.load_error_backup = ''
        manager.migrated_from_version = prog.SAVE_SCHEMA_VERSION
        with mock.patch.object(prog, 'CHARS_PATH', path), \
             mock.patch.object(prog, 'BACKUP_DIR', os.path.join(directory, 'backups')):
            manager.load()

        self.assertNotEqual(manager.load_error, '')
        self.assertIn('newer version of the game', manager.load_error)
        self.assertEqual(manager.characters, [])
        # Original file untouched, backup present and identical.
        with open(path) as f:
            self.assertEqual(json.load(f), payload)
        self.assertTrue(os.path.exists(manager.load_error_backup))
        with open(manager.load_error_backup) as f:
            self.assertEqual(json.load(f), payload)

    def test_corrupt_file_is_backed_up_and_reported(self):
        directory = tempfile.mkdtemp()
        path = os.path.join(directory, 'characters.json')
        with open(path, 'w') as f:
            f.write('{"characters": [ truncated')

        manager = prog.CharacterManager.__new__(prog.CharacterManager)
        manager.characters = []
        manager.active_idx = 0
        manager.unlocked_vessels = ['knight']
        manager.best_depth = 0
        manager.load_error = ''
        manager.load_error_backup = ''
        manager.migrated_from_version = prog.SAVE_SCHEMA_VERSION
        with mock.patch.object(prog, 'CHARS_PATH', path), \
             mock.patch.object(prog, 'BACKUP_DIR', os.path.join(directory, 'backups')):
            manager.load()

        self.assertIn('corrupt or unreadable', manager.load_error)
        self.assertEqual(manager.characters, [])
        self.assertTrue(os.path.exists(path), 'corrupt file must not be deleted')
        self.assertTrue(os.path.exists(manager.load_error_backup))
        with open(manager.load_error_backup) as f:
            self.assertIn('truncated', f.read())

    def test_unmigratable_shape_is_backed_up_and_reported(self):
        directory = tempfile.mkdtemp()
        path = os.path.join(directory, 'characters.json')
        payload = _current_save()
        payload['characters'] = [{'id': 'half-a-character'}]
        with open(path, 'w') as f:
            json.dump(payload, f)

        manager = prog.CharacterManager.__new__(prog.CharacterManager)
        manager.characters = []
        manager.active_idx = 0
        manager.unlocked_vessels = ['knight']
        manager.best_depth = 0
        manager.load_error = ''
        manager.load_error_backup = ''
        manager.migrated_from_version = prog.SAVE_SCHEMA_VERSION
        with mock.patch.object(prog, 'CHARS_PATH', path), \
             mock.patch.object(prog, 'BACKUP_DIR', os.path.join(directory, 'backups')):
            manager.load()

        self.assertIn('after migration', manager.load_error)
        self.assertEqual(manager.characters, [])
        self.assertTrue(os.path.exists(manager.load_error_backup))

    def test_backup_never_overwrites_an_earlier_backup(self):
        directory = tempfile.mkdtemp()
        path = os.path.join(directory, 'characters.json')
        with open(path, 'w') as f:
            f.write('not json')
        backup_dir = os.path.join(directory, 'backups')
        with mock.patch.object(prog, 'BACKUP_DIR', backup_dir):
            first = prog.backup_save_file(path, 'test')
            second = prog.backup_save_file(path, 'test')
        self.assertNotEqual(first, second)
        self.assertTrue(os.path.exists(first))
        self.assertTrue(os.path.exists(second))

    def test_missing_save_file_is_not_an_error(self):
        directory = tempfile.mkdtemp()
        manager = prog.CharacterManager.__new__(prog.CharacterManager)
        manager.characters = []
        manager.active_idx = 0
        manager.unlocked_vessels = ['knight']
        manager.best_depth = 0
        manager.load_error = 'stale'
        manager.load_error_backup = ''
        manager.migrated_from_version = prog.SAVE_SCHEMA_VERSION
        with mock.patch.object(prog, 'CHARS_PATH', os.path.join(directory, 'nope.json')):
            manager.load()
        self.assertEqual(manager.load_error, '')


class RealPathTests(unittest.TestCase):
    """The live game path: creation, hub entry and delve entry all save/load."""

    def test_new_save_is_stamped_with_current_version(self):
        directory = tempfile.mkdtemp()
        path = os.path.join(directory, 'characters.json')
        with mock.patch.object(prog, 'CHARS_PATH', path):
            manager = prog.CharacterManager()
            manager.create('TestOp', 'knight')
        with open(path) as f:
            saved = json.load(f)
        self.assertEqual(saved['save_schema_version'], prog.SAVE_SCHEMA_VERSION)
        self.assertNotIn('format_version', saved)

    def test_create_then_reload_round_trips(self):
        directory = tempfile.mkdtemp()
        path = os.path.join(directory, 'characters.json')
        with mock.patch.object(prog, 'CHARS_PATH', path):
            manager = prog.CharacterManager()
            manager.create('RoundTrip', 'knight')
            manager.note_depth(4)
            manager.save()
            reloaded = prog.CharacterManager()
        self.assertEqual(reloaded.load_error, '')
        self.assertEqual(reloaded.best_depth, 4)
        self.assertEqual(len(reloaded.characters), 1)
        self.assertEqual(reloaded.characters[0].name, 'RoundTrip')

    def test_delve_snapshot_round_trip_keeps_version(self):
        directory = tempfile.mkdtemp()
        path = os.path.join(directory, 'delve_char-1.json')
        with mock.patch.object(prog, 'delve_save_path', lambda _cid: path):
            prog.save_delve_data('char-1', {'delve': {'state': 'ready', 'enemy_ids': {3}}})
            with open(path) as f:
                self.assertEqual(json.load(f)['save_schema_version'],
                                 prog.SAVE_SCHEMA_VERSION)
            restored = prog.load_delve_data('char-1')
        self.assertEqual(restored['delve']['enemy_ids'], {3})

    def test_future_delve_snapshot_is_ignored_not_loaded(self):
        directory = tempfile.mkdtemp()
        path = os.path.join(directory, 'delve_char-1.json')
        payload = {'save_schema_version': prog.SAVE_SCHEMA_VERSION + 1,
                   'delve': {'state': 'ready'}}
        with open(path, 'w') as f:
            json.dump(payload, f)
        backup_dir = os.path.join(directory, 'backups')
        with mock.patch.object(prog, 'delve_save_path', lambda _cid: path), \
             mock.patch.object(prog, 'BACKUP_DIR', backup_dir):
            self.assertIsNone(prog.load_delve_data('char-1'))
        with open(path) as f:
            self.assertEqual(json.load(f), payload)
        self.assertEqual(len(os.listdir(backup_dir)), 1)


if __name__ == '__main__':
    unittest.main()
