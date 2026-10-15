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

"""Anima node display names + chart geometry guards (owner rulings
2026-10-07): no armour-era names survive, depth rows never run out, and
the chart sits closer/bigger than the old 380/60 layout."""

import random
import unittest

import core.delve_gen as delve_gen


LEGACY_STRINGS = ('armour', 'chest', 'delve entrance', 'rare cache',
                   'boss loot', 'breach chest')


def _all_names():
    """Every display string a chart/room node can carry."""
    graph = delve_gen.init_delve(seed=1234)
    delve_gen.ensure_depth_rows(graph, __import__('random').Random(7), 30)
    for node in graph['nodes'].values():
        yield node.get('label') or ''
        yield node.get('loot') or ''
    room = delve_gen.init_delve_room(seed=42, depth=3)
    yield room['node'].get('label') or ''
    yield room['node'].get('loot') or ''


class TestNodeNames(unittest.TestCase):
    def test_no_legacy_strings_in_generated_nodes(self):
        for text in _all_names():
            low = text.lower()
            for legacy in LEGACY_STRINGS:
                self.assertNotIn(legacy, low,
                                 f'legacy name survives: {text!r}')

    def test_expected_new_names_present(self):
        self.assertIn('Organ Rack',
                      [lt for _nt, _lb, lt in delve_gen.NODE_DEFS])
        self.assertIn('Organ Cache',
                      [lb for _nt, lb, _lt in delve_gen.NODE_DEFS])
        self.assertIn('Vital Hoard',
                      [lt for _nt, _lb, lt in delve_gen.NODE_DEFS_BOSS])

    def test_start_and_dead_end_names(self):
        graph = delve_gen.init_delve(seed=99)
        names = [(n.get('label'), n.get('loot'))
                 for n in graph['nodes'].values()]
        self.assertTrue(any(label == 'Anima Entrance' for label, _ in names))


class TestRowSupply(unittest.TestCase):
    """Depth rows never run out (§26.236): an exhausted standing row gets a
    fresh batch APPENDED to its left or right side — nothing is ever
    deleted, the beaten history stays on the chart."""

    def test_exhausted_row_appends_to_the_side(self):
        graph = delve_gen.init_delve(seed=7)
        start_id = graph['start_node_id']
        row1_before = {n['id'] for n in graph['nodes'].values()
                       if n['depth'] == 1}
        cols_before = sorted(n['col'] for n in graph['nodes'].values()
                             if n['depth'] == 1)
        for node in graph['nodes'].values():          # farm row 1 completely
            if node['depth'] == 1:
                node['state'] = delve_gen.STATE_CLEARED
        total_before = len(graph['nodes'])

        added = delve_gen.ensure_row_supply(graph, random.Random(3), start_id)
        self.assertGreaterEqual(added, 2)
        # append, not replace — every original node (incl. start) survives
        self.assertEqual(len(graph['nodes']), total_before + added)
        self.assertTrue(row1_before <= set(graph['nodes']))
        self.assertIn(start_id, graph['nodes'])
        # fresh nodes: beyond the original lanes on one side, never dead
        row1 = [n for n in graph['nodes'].values() if n['depth'] == 1]
        fresh = [n for n in row1 if n['state'] == delve_gen.STATE_AVAILABLE]
        self.assertGreaterEqual(len(fresh), added)
        self.assertTrue(all(not n.get('dead_end') for n in fresh))
        cols_after = sorted(n['col'] for n in row1)
        self.assertTrue(cols_after[-1] > cols_before[-1] + 1e-9
                        or cols_after[0] < cols_before[0] - 1e-9,
                        'fresh batch did not extend past the row edge')
        # bridge: the first fresh node links to a CLEARED row node; the
        # batch chains sideways — every new edge stays in-row (horizontal)
        fresh_ids = {n['id'] for n in fresh}
        inbound = [(p, c) for p, c in graph['edges']
                   if c in fresh_ids and p not in fresh_ids]
        self.assertTrue(inbound)
        cleared_row = {n['id'] for n in row1
                       if n['state'] == delve_gen.STATE_CLEARED}
        self.assertIn(inbound[0][0], cleared_row)
        for p, c in graph['edges']:
            if p in fresh_ids or c in fresh_ids:
                self.assertEqual(graph['nodes'][p]['depth'],
                                 graph['nodes'][c]['depth'])
        # stable: a second call sees live options and adds nothing
        self.assertEqual(delve_gen.ensure_row_supply(graph, random.Random(3),
                                                     start_id), 0)

    def test_populated_row_never_refreshes(self):
        graph = delve_gen.init_delve(seed=11)
        start_id = graph['start_node_id']
        self.assertEqual(
            delve_gen.ensure_row_supply(graph, random.Random(5), start_id), 0)


class TestChartDensity(unittest.TestCase):
    """Nodes closer together, icons bigger (owner ruling 2026-10-07)."""

    def test_spacing_constants_shrank(self):
        self.assertEqual(delve_gen.CHART_COL_SPACING, 300.0)
        self.assertEqual(delve_gen.CHART_ROW_SPACING, 46.0)

    def test_node_radius_grew(self):
        from pathlib import Path
        src = Path('ui/delve_chart.py').read_text(encoding='utf-8')
        self.assertIn("(8 if node['type'] in ('checkpoint', 'boss') else 6)",
                      src)
        # icons 2× bigger than the first pass — ~3.1× the circle diameter
        self.assertIn('radius * 2 * 1.55 * 2', src)
        self.assertIn('34 * self.zoom', src)          # glyph paired with icons
        self.assertIn('radius * 3.1', src)            # hitbox follows the icon


class TestDarkness(unittest.TestCase):
    """Almost pitch black in the Hub AND the Anima (§ ruling 2026-10-07)."""

    def test_ambient_is_near_black(self):
        from core.game import DARKNESS_AMBIENT
        self.assertLessEqual(DARKNESS_AMBIENT, 12)
        self.assertGreater(DARKNESS_AMBIENT, 0)   # 'almost' — not absolute


if __name__ == '__main__':
    unittest.main()
