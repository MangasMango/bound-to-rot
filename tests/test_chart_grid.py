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

"""Orthogonal Anima chart grid (BLUEPRINT §26 - owner ruling 2026-10-07).

  1. Paths never run diagonally: every edge is vertical (same column,
     next depth) or horizontal (same row).
  2. Row 1 is exactly CHART_LANES nodes on the fixed lane columns.
  3. Every generated batch keeps at least one live (non-dead-end) path.
  4. Dead ends terminate their lane - nothing is ever generated below
     them, so no unreachable node can exist.
  5. Every non-dead node is reachable from the start (one-hop adjacency).
"""

import random
import unittest

import core.delve_gen as delve_gen


def _grown_graph(seed=7, rows=6):
    graph = delve_gen.init_delve(seed)
    rng = random.Random(seed ^ 0x5EED)
    for _ in range(rows):
        delve_gen.generate_next_depth(graph, rng)
    return graph


def _assert_orthogonal(test, graph):
    for p, c in graph['edges']:
        a, b = graph['nodes'][p], graph['nodes'][c]
        if a['depth'] == b['depth']:
            continue                      # lateral: same row is fine
        test.assertEqual(b['depth'], a['depth'] + 1,
                         f'{p}->{c} jumps depth {a["depth"]}->{b["depth"]}')
        test.assertAlmostEqual(a['col'], b['col'], places=9,
                               msg=f'{p}->{c} runs diagonally')


def _reachable_from(graph, start_id):
    adj = {}
    for p, c in graph['edges']:
        adj.setdefault(p, set()).add(c)
        adj.setdefault(c, set()).add(p)
    seen = {start_id}
    stack = [start_id]
    while stack:
        nid = stack.pop()
        for nxt in adj.get(nid, ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


class TestOrthogonalEdges(unittest.TestCase):
    def test_no_edge_ever_runs_diagonally(self):
        for seed in (1, 7, 42):
            _assert_orthogonal(self, _grown_graph(seed))

    def test_children_inherit_the_parent_lane(self):
        graph = _grown_graph()
        for p, c in graph['edges']:
            a, b = graph['nodes'][p], graph['nodes'][c]
            if b['depth'] == a['depth'] + 1:
                self.assertEqual(a['col'], b['col'])


class TestRowShape(unittest.TestCase):
    def test_row_one_is_four_fixed_lanes(self):
        graph = delve_gen.init_delve(seed=3)
        row1 = [n for n in graph['nodes'].values() if n['depth'] == 1]
        self.assertEqual(len(row1), delve_gen.CHART_LANES)
        self.assertEqual(sorted(round(n['col'], 4) for n in row1),
                         sorted(round(c, 4) for c in delve_gen.LANE_COLS))
        self.assertTrue(all(not n.get('dead_end') for n in row1),
                        'row 1 is always fully alive')

    def test_row_one_laterals_form_a_full_chain(self):
        graph = delve_gen.init_delve(seed=3)
        row1 = sorted((n for n in graph['nodes'].values() if n['depth'] == 1),
                      key=lambda n: n['col'])
        for a, b in zip(row1, row1[1:]):
            self.assertIn((a['id'], b['id']), graph['edges'],
                          'row 1 discovery depends on the lateral chain')

    def test_every_batch_keeps_at_least_one_live_lane(self):
        for seed in (1, 7, 42):
            graph = delve_gen.init_delve(seed)
            rng = random.Random(seed ^ 0xABCD)
            for _ in range(8):
                before = set(graph['nodes'])
                delve_gen.generate_next_depth(graph, rng)
                newborn = [n for nid, n in graph['nodes'].items()
                           if nid not in before]
                self.assertTrue(newborn)
                self.assertTrue(any(not n.get('dead_end') for n in newborn),
                                f'seed {seed}: batch generated all dead ends')


class TestReachability(unittest.TestCase):
    def test_every_live_node_is_reachable_from_start(self):
        for seed in (1, 7, 42):
            graph = _grown_graph(seed)
            seen = _reachable_from(graph, graph['start_node_id'])
            orphans = [n['id'] for n in graph['nodes'].values()
                       if n['id'] not in seen and not n.get('dead_end')]
            self.assertEqual(orphans, [],
                             f'seed {seed}: unreachable live nodes {orphans}')

    def test_dead_lanes_end(self):
        graph = _grown_graph()
        for p, c in graph['edges']:
            parent = graph['nodes'][p]
            child = graph['nodes'][c]
            if child['depth'] > parent['depth']:
                self.assertFalse(parent.get('dead_end'),
                                 'a dead end parented a deeper node')

    def test_laterals_exist_but_are_not_guaranteed(self):
        """New rows roll ~70% - over enough rows both cases must occur."""
        graph = _grown_graph(seed=9, rows=10)
        same_row_edges = [e for e in graph['edges']
                          if graph['nodes'][e[0]]['depth']
                          == graph['nodes'][e[1]]['depth']]
        self.assertTrue(same_row_edges)
        # not every consecutive pair is linked (random subset)
        total_pairs = 0
        rows = {}
        for n in graph['nodes'].values():
            rows.setdefault(n['depth'], []).append(n)
        for row in rows.values():
            total_pairs += max(0, len(row) - 1)
        self.assertLess(len(same_row_edges), total_pairs)


class TestFindRouteBothWays(unittest.TestCase):
    def test_route_walks_edges_in_either_direction(self):
        graph = _grown_graph(seed=7)
        # lateral edges are stored left→right; walking right→left must work
        lateral = next((e for e in graph['edges']
                        if graph['nodes'][e[0]]['depth']
                        == graph['nodes'][e[1]]['depth']), None)
        if lateral is None:
            self.skipTest('seed produced no lateral edges')
        left, right = lateral
        self.assertEqual(delve_gen.find_route(graph, right, left),
                         [right, left])
        # and up-lanes (against the parent→child direction)
        down = next(e for e in graph['edges']
                    if graph['nodes'][e[1]]['depth']
                    == graph['nodes'][e[0]]['depth'] + 1)
        up_from, down_to = down
        self.assertEqual(delve_gen.find_route(graph, down_to, up_from),
                         [down_to, up_from])


if __name__ == '__main__':
    unittest.main()
