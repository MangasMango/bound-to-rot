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

"""
Regression tests for anima snapshot isolation (GitHub issue #16 / QoL #113).

These guard against the fragile shallow-copy snapshot that previously lived in
``Game._exit_anima()``. The snapshot must be a *deep* copy so that any later
mutation of the live anima objects cannot leak into the saved data (neither the
in-memory resume snapshot nor the on-disk save).
"""

import os
import tempfile
import unittest

import entities.progression as _prog
from core.game import Game


def _make_sample_anima():
    """A realistic-ish anima payload with nested mutable containers + a set."""
    return {
        'state': 'ready',
        'pulse_x': 3.0,
        'pulse_y': 4.0,
        'enemy_ids': {1, 2, 3},
        'nodes': [{'id': 1, 'cleared': False}, {'id': 2, 'cleared': True}],
        'meta': {'depth': 5, 'score': [10, 20, 30]},
    }


class TestBuildAnimaSnapshot(unittest.TestCase):
    def test_snapshot_is_deep_copy_and_isolated(self):
        anima = _make_sample_anima()
        game_map = {'tiles': [[1, 2], [3, 4]], 'seed': 42}
        zombies = [{'id': 1, 'hp': 100, 'pos': [0, 0]}]
        ground_items = [{'type': 'drop', 'items': ['a', 'b']}]
        decor_items = [{'kind': 'rock', 'pos': [1, 1]}]

        snap = Game._build_anima_snapshot(
            anima, game_map, zombies, ground_items, decor_items)

        # Top-level keys present and the right (copied) objects.
        self.assertEqual(set(snap.keys()),
                         {'anima', 'map', 'zombies', 'ground_items', 'decor_items'})

        # Mutate every live source *after* the snapshot was taken.
        anima['state'] = 'MUTATED'
        anima['enemy_ids'].add(999)
        anima['nodes'][0]['cleared'] = True
        anima['meta']['score'].append(999)
        game_map['tiles'][0][0] = -1
        zombies[0]['hp'] = -1
        zombies[0]['pos'][0] = 123
        ground_items[0]['items'].append('leak')
        decor_items[0]['pos'][0] = 77

        # The snapshot must be untouched by any of those mutations.
        self.assertEqual(snap['anima']['state'], 'ready')
        self.assertEqual(snap['anima']['enemy_ids'], {1, 2, 3})
        self.assertFalse(snap['anima']['nodes'][0]['cleared'])
        self.assertEqual(snap['anima']['meta']['score'], [10, 20, 30])
        self.assertEqual(snap['map']['tiles'], [[1, 2], [3, 4]])
        self.assertEqual(snap['zombies'][0]['hp'], 100)
        self.assertEqual(snap['zombies'][0]['pos'], [0, 0])
        self.assertEqual(snap['ground_items'][0]['items'], ['a', 'b'])
        self.assertEqual(snap['decor_items'][0]['pos'], [1, 1])

    def test_snapshot_independence_between_calls(self):
        anima = _make_sample_anima()
        a = Game._build_anima_snapshot(anima, {}, [], [], [])
        b = Game._build_anima_snapshot(anima, {}, [], [], [])
        # Two snapshots must not share identity.
        self.assertIsNot(a['anima'], b['anima'])
        self.assertIsNot(a['anima']['nodes'], b['anima']['nodes'])


class TestAnimaDiskIsolation(unittest.TestCase):
    """The on-disk save must also be isolated from later live mutations."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix='anima_iso_')
        self._orig_dir = _prog.ANIMA_SAVE_DIR
        _prog.ANIMA_SAVE_DIR = self._tmp

    def tearDown(self):
        _prog.ANIMA_SAVE_DIR = self._orig_dir
        for name in os.listdir(self._tmp):
            try:
                os.remove(os.path.join(self._tmp, name))
            except OSError:
                pass
        try:
            os.rmdir(self._tmp)
        except OSError:
            pass

    def test_save_is_immune_to_later_mutation(self):
        anima = _make_sample_anima()
        live = {
            'anima': anima,
            'map': {'tiles': [[1, 2]]},
            'zombies': [{'id': 1, 'hp': 50}],
            'ground_items': [],
            'decor_items': [],
        }

        # Save using the live references (the pre-fix "shallow" pattern).
        _prog.save_anima_data('hero', live)

        # Now mutate the live objects after the save call.
        anima['state'] = 'MUTATED'
        anima['enemy_ids'].add(777)
        anima['nodes'][0]['cleared'] = True
        anima['meta']['score'].append(0)
        live['map']['tiles'][0][0] = -9
        live['zombies'][0]['hp'] = -5

        # The restored data must reflect the state at save time, not the
        # post-save mutation.
        loaded = _prog.load_anima_data('hero')
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded['anima']['state'], 'ready')
        self.assertEqual(loaded['anima']['enemy_ids'], {1, 2, 3})
        self.assertFalse(loaded['anima']['nodes'][0]['cleared'])
        self.assertEqual(loaded['anima']['meta']['score'], [10, 20, 30])
        self.assertEqual(loaded['map']['tiles'], [[1, 2]])
        self.assertEqual(loaded['zombies'][0]['hp'], 50)


if __name__ == '__main__':
    unittest.main(verbosity=2)
