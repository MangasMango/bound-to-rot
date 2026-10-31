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

"""Character-bound delve layout + compact dark hub.

- The delve seed is derived from the character id: same character → same
  chart and rooms on every visit; death deletes the character → new seed →
  fresh layout.
- The hub is a 3×3 open floor with no walls; torches/braziers/the Delve
  Heart anchor the light.
"""

import unittest

import entities.progression as prog
from entities.progression import Character
from systems.items import ITEMS
import core.delve_gen as delve_gen


def _graph_shape(graph):
    """Seed-deterministic layout signature (node ids are process-global
    counters, so graphs must be compared by structure, not by id)."""
    id_key = {nid: (n['depth'], round(n['col'], 4), n['type'])
              for nid, n in graph['nodes'].items()}
    return {
        'nodes': sorted(id_key.values()),
        'edges': sorted((id_key[a], id_key[b]) for a, b in graph['edges']),
        'start': id_key[graph['start_node_id']],
    }


class CharSeedTests(unittest.TestCase):
    def test_seed_stable_for_same_id(self):
        c1 = Character('12345', 'A')
        c2 = Character('12345', 'A')
        self.assertEqual(c1.seed, c2.seed)

    def test_seed_differs_between_characters(self):
        self.assertNotEqual(Character('1').seed, Character('2').seed)

    def test_deterministic_chart_from_seed(self):
        """Same seed → same layout shape: the layout is bound to the
        character. (Node ids are process-global counters, so compare shape.)"""
        g1 = delve_gen.init_delve(Character('777').seed)
        g2 = delve_gen.init_delve(Character('777').seed)
        self.assertEqual(_graph_shape(g1), _graph_shape(g2))
        g3 = delve_gen.init_delve(Character('778').seed)
        self.assertNotEqual(_graph_shape(g1), _graph_shape(g3))


class DelvePersistenceTests(unittest.TestCase):
    def test_save_load_round_trip_preserves_chart(self):
        seed = 424242
        graph = delve_gen.init_delve(seed)
        chart = {
            'seed': seed,
            'graph': graph,
            'current_node_id': graph['start_node_id'],
            'visited': [graph['start_node_id']],
            'looted': [], 'checkpoints': [], 'route': [],
            'best_depth': 1,
        }
        delve = {
            'state': 'ready', 'depth': 2, 'node': {'col': 3, 'row': 3},
            'enemy_ids': [], 'pending_rewards': [],
            'pulse_x': 3.0, 'pulse_y': 3.0, 'light_r': 2.0,
            'darkness_dps': 13.0, 'dark_timer': 0.0,
            'relics': [], 'chart': chart,
        }
        snapshot = {
            'delve': delve, 'map': [], 'zombies': [],
            'ground_items': [], 'decor_items': [],
        }
        char_id = 'test-persist-1'
        try:
            prog.save_delve_data(char_id, snapshot)
            loaded = prog.load_delve_data(char_id)
            self.assertIsNotNone(loaded)
            saved_chart = loaded['delve']['chart']
            self.assertEqual(saved_chart['seed'], seed)
            self.assertEqual(saved_chart['visited'], chart['visited'])
            # The chart is deterministic from the seed, so a rebuilt graph
            # matches what was saved - the layout never changes mid-journey.
            self.assertEqual(_graph_shape(delve_gen.init_delve(seed)),
                             _graph_shape(saved_chart['graph']))
        finally:
            prog.clear_delve_data(char_id)

    def test_clear_removes_layout(self):
        char_id = 'test-persist-2'
        prog.save_delve_data(char_id, {'delve': {'chart': {}}, 'map': [],
                                       'zombies': [], 'ground_items': [],
                                       'decor_items': []})
        self.assertIsNotNone(prog.load_delve_data(char_id))
        prog.clear_delve_data(char_id)
        self.assertIsNone(prog.load_delve_data(char_id))


class DelveHeartChartLifecycleTests(unittest.TestCase):
    """The heart popup opens for every cleared delve wave (#92)."""

    class _RecordingScreen:
        def __init__(self):
            self.selectable_ids = ()

        def open(self, chart, selectable_ids=(), **kwargs):
            self.selectable_ids = tuple(selectable_ids)

    def test_heart_chart_reopens_after_first_and_second_wave(self):
        import random
        from core.game import Game

        game = Game.__new__(Game)
        graph = delve_gen.init_delve(92)
        chart = {
            'graph': graph,
            'current_node_id': graph['start_node_id'],
            'visited': [graph['start_node_id']],
            'looted': [], 'checkpoints': [], 'route': [],
            'best_depth': 1,
        }
        # A stale persisted/runtime value must not masquerade as the source of
        # truth: the transient instance flag starts closed and is never saved.
        game._delve = {'state': 'ready', 'depth': 1, 'chart': chart,
                       '_chart_open': True}
        game._chart_screen = self._RecordingScreen()
        game._chart_rng = random.Random(92)
        game._delve_chart_open = False

        opened_children = []
        current_per_wave = []
        for wave in range(3):
            expected = [kid['id'] for kid in game._delve_children()]
            self.assertTrue(game._open_delve_anima_panel(),
                            f'heart did not open after wave {wave}')
            self.assertTrue(game._delve_chart_is_open())
            self.assertEqual(game._chart_screen.selectable_ids, tuple(expected))
            opened_children.append(tuple(expected))
            current_per_wave.append(chart['current_node_id'])

            # Close as a player would between waves, then simulate entering
            # and clearing the next node/wave.  Repeating this catches a stale
            # open flag that would swallow the next heart press.
            game._close_delve_anima_panel()
            self.assertFalse(game._delve_chart_is_open())
            self.assertNotIn('_chart_open', chart)
            child_id = expected[0]
            game._delve_mark_cleared()
            chart['current_node_id'] = child_id
            chart['route'].append(child_id)
            game._delve['depth'] = graph['nodes'][child_id]['depth']
            game._delve['state'] = 'ready'

        # Each wave must refresh the selection. Backward (left-behind) nodes
        # are now enterable too, so instead of "a different set each wave"
        # assert the rule itself: every forward child of the current node is
        # offered, and no cleared node ever is.
        import core.delve_gen as _dg
        for wave, (offered, current) in enumerate(
                zip(opened_children, current_per_wave)):
            forward = {k['id'] for k in _dg.chart_children(graph, current)
                       if not k.get('dead_end')}
            self.assertTrue(forward, f'wave {wave}: current node has no children')
            self.assertTrue(forward <= set(offered),
                            f'wave {wave}: forward children not selectable')
            self.assertNotIn(graph['start_node_id'], offered,
                             f'wave {wave}: cleared node offered')
            self.assertNotIn(current, offered,
                             f'wave {wave}: current node offered')


class CompactHubTests(unittest.TestCase):
    def test_hub_map_matches_delve_floor(self):
        """The hub sits on the same 200×200 open floor as the delve -
        infinite-feel darkness hides the bounds."""
        import core.delve_gen as delve_gen
        from core.game import Game
        hub = Game()._build_hub_map()
        self.assertEqual(len(hub), delve_gen.GRID_W)
        self.assertEqual(len(hub[0]), delve_gen.GRID_H)
        # no walls - every tile is open floor (0)
        self.assertTrue(all(tile == 0 for row in hub for tile in row))

    def test_hub_layout_has_exactly_three_waypoints(self):
        from core.game import _HUB_LAYOUT, _HEART_POS, _STASH_POS, _VENDOR_POS
        self.assertEqual(len(_HUB_LAYOUT), 3)
        self.assertEqual({o['type'] for o in _HUB_LAYOUT},
                         {'delve', 'vendor', 'stash'})
        self.assertEqual((_HUB_LAYOUT[0]['x'], _HUB_LAYOUT[0]['y']), _HEART_POS)
        self.assertEqual((_HUB_LAYOUT[1]['x'], _HUB_LAYOUT[1]['y']), _VENDOR_POS)
        self.assertEqual((_HUB_LAYOUT[2]['x'], _HUB_LAYOUT[2]['y']), _STASH_POS)
        # sanctuary sits near the centre of the 200×200 floor; the spread
        # grew with the native desert tile density (tiles ~2.7× smaller on
        # screen than the old LoP canvas)
        import core.delve_gen as delve_gen
        for obj in _HUB_LAYOUT:
            self.assertTrue(delve_gen.GRID_W // 2 - 5 < obj['x'] < delve_gen.GRID_W // 2 + 5)
            self.assertTrue(delve_gen.GRID_H // 2 - 5 < obj['y'] < delve_gen.GRID_H // 2 + 5)

    def test_hub_lights_cover_the_sanctuary(self):
        """Every sanctuary tile must be within reach of some torch/brazier/
        heart - the sanctuary only works if the light actually reaches it."""
        from core.game import _HUB_LIGHTS, DELVE_PERSONAL_LIGHT
        sanctuary = [(99, 99), (100, 99), (101, 99),
                     (99, 100), (100, 100), (101, 100),
                     (99, 101), (100, 101), (101, 101)]
        for col, row in sanctuary:
            covered = any(
                ((col + 0.5) - l['x']) ** 2 + ((row + 0.5) - l['y']) ** 2
                <= (l['r'] + DELVE_PERSONAL_LIGHT) ** 2
                for l in _HUB_LIGHTS)
            self.assertTrue(covered, f"tile ({col},{row}) is in true darkness")

    def test_hub_spawn_starts_between_the_braziers(self):
        from core.game import HUB_SPAWN, _HUB_LIGHTS, DELVE_PERSONAL_LIGHT
        # spawn must be inside at least one light pool (incl. personal light)
        covered = any(((HUB_SPAWN[0] - l['x']) ** 2 + (HUB_SPAWN[1] - l['y']) ** 2)
                      <= (l['r'] + DELVE_PERSONAL_LIGHT) ** 2 for l in _HUB_LIGHTS)
        self.assertTrue(covered)

    def test_hub_lights_carry_kind_for_flicker(self):
        from core.game import _HUB_LIGHTS
        # the campfires are gone - the Delve Heart carries the light alone
        kinds = {l['kind'] for l in _HUB_LIGHTS}
        self.assertEqual(kinds, {'heart'})

    def test_hub_light_covers_the_waypoints(self):
        """The single heart pool's visible edge must swallow the sanctuary:
        spawn and both waypoints inside the rendered pool edge."""
        from core.game import (HUB_SPAWN, _HUB_LIGHTS, _HUB_LAYOUT)
        heart = _HUB_LIGHTS[0]
        for spot in (HUB_SPAWN,
                     (_HUB_LAYOUT[1]['x'], _HUB_LAYOUT[1]['y']),
                     (_HUB_LAYOUT[2]['x'], _HUB_LAYOUT[2]['y'])):
            dist = ((spot[0] - heart['x']) ** 2
                    + (spot[1] - heart['y']) ** 2) ** 0.5
            self.assertLessEqual(dist, heart['r'],
                                 f'{spot} outside the visible pool edge')


if __name__ == '__main__':
    unittest.main(verbosity=2)
