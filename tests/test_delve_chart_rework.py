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

"""Delve chart rework: compact layout, navigation rules, depth record, modal UI.

Covers the four delivered parts:
- generator-owned compact node positions (+ re-layout of older saved charts)
- selection rules: cleared never, discovered-uncleared and forward children yes
- depth follows the current node while the record only ever increases
- modal has no counters, BEST DEPTH lives on the screen frame, and the
  RETURN TO HUB button reports its click
"""

import random
import unittest
from unittest.mock import patch

import pyray as rl

import core.delve_gen as delve_gen
import ui.delve_chart as chart_mod
from ui.delve_chart import DelveChartScreen, ZOOM_DEFAULT, ZOOM_MAX


def _chart(seed=7, depth_rows=3):
    graph = delve_gen.init_delve(seed)
    rng = random.Random(seed ^ 0x5EED)
    while graph['max_depth'] < depth_rows:
        delve_gen.generate_next_depth(graph, rng)
    delve_gen.layout_positions(graph)
    return {
        'graph': graph,
        'current_node_id': graph['start_node_id'],
        'visited': [graph['start_node_id']],
        'looted': [], 'checkpoints': [],
        'route': [graph['start_node_id']],
        'best_depth': 1,
    }


def _play_forward(chart, steps):
    """Walk `steps` depth rows forward, clearing each node on the way."""
    graph = chart['graph']
    for _ in range(steps):
        enterable = delve_gen.enterable_node_ids(graph, chart)
        forward = [nid for nid in enterable
                   if graph['nodes'][nid]['depth']
                   == graph['nodes'][chart['current_node_id']]['depth'] + 1]
        if not forward:
            break
        nxt = forward[0]
        prev = chart['current_node_id']
        graph['nodes'][prev]['state'] = delve_gen.STATE_CLEARED
        if prev not in chart['visited']:
            chart['visited'].append(prev)
        chart['current_node_id'] = nxt
        chart['route'].append(nxt)
        chart['best_depth'] = max(chart['best_depth'],
                                  graph['nodes'][nxt]['depth'])
    return chart


# ── Part 1: zoom ───────────────────────────────────────────────────────


class ZoomTests(unittest.TestCase):
    def test_zoom_max_raised_and_default_is_zoomed_out_three_notches(self):
        self.assertGreater(ZOOM_MAX, 2.0)
        # opens exactly three wheel-notches (×0.85 each) out from the max
        self.assertEqual(ZOOM_DEFAULT, round(ZOOM_MAX * 0.85 ** 3, 3))
        self.assertLess(ZOOM_DEFAULT, ZOOM_MAX)

    def test_open_centres_camera_on_current_node(self):
        chart = _play_forward(_chart(), 2)
        screen = DelveChartScreen(object())
        screen.open(chart, selectable_ids=())
        node = chart['graph']['nodes'][chart['current_node_id']]
        self.assertEqual(screen.cam_x, node['px'])
        self.assertEqual(screen.cam_y, node['py'])
        self.assertEqual(screen.zoom, ZOOM_DEFAULT)


# ── Part 2: compact, generator-owned positions ─────────────────────────


class LayoutTests(unittest.TestCase):
    def test_generator_assigns_positions_for_every_node(self):
        chart = _chart()
        for node in chart['graph']['nodes'].values():
            self.assertIn('px', node)
            self.assertIn('py', node)
            self.assertEqual((node['px'], node['py']),
                             delve_gen.node_pos(node['depth'], node['col']))

    def test_rows_are_compact(self):
        """Row spacing must be visibly tighter than the old 170px layout."""
        self.assertLess(delve_gen.CHART_ROW_SPACING, 170.0 * 0.5)
        self.assertLess(delve_gen.CHART_COL_SPACING, 900.0 * 0.5)

    def test_layout_positions_is_deterministic_and_rebuilds_old_charts(self):
        chart = _chart()
        graph = chart['graph']
        before = {nid: (n['px'], n['py']) for nid, n in graph['nodes'].items()}

        # Simulate a chart persisted under the old, looser spacing.
        for node in graph['nodes'].values():
            node['px'] = node['col'] * 900.0
            node['py'] = node['depth'] * 170.0
        delve_gen.layout_positions(graph)
        after = {nid: (n['px'], n['py']) for nid, n in graph['nodes'].items()}
        self.assertEqual(before, after)

        # Re-running is a no-op: same graph, same positions, always.
        delve_gen.layout_positions(graph)
        self.assertEqual(after, {nid: (n['px'], n['py'])
                                 for nid, n in graph['nodes'].items()})

    def test_renderer_does_not_own_the_layout(self):
        """The renderer only projects the generator's coordinates."""
        node = {'depth': 4, 'col': 0.5, 'px': 123.0, 'py': 456.0}
        self.assertEqual(chart_mod.node_world_pos(node), (123.0, 456.0))
        # Nodes without stored coordinates fall back to the same formula.
        self.assertEqual(
            chart_mod.node_world_pos({'depth': 4, 'col': 0.5}),
            delve_gen.node_pos(4, 0.5))


# ── Part 3: navigation rules ───────────────────────────────────────────


class SelectionRuleTests(unittest.TestCase):
    def test_forward_children_are_enterable(self):
        chart = _chart()
        graph = chart['graph']
        start = graph['start_node_id']
        forward = {k['id'] for k in delve_gen.chart_children(graph, start)
                   if not k.get('dead_end')}
        self.assertTrue(forward)
        self.assertTrue(forward <= set(delve_gen.enterable_node_ids(graph, chart)))

    def test_cleared_nodes_are_never_enterable(self):
        chart = _play_forward(_chart(), 3)
        graph = chart['graph']
        enterable = delve_gen.enterable_node_ids(graph, chart)
        for nid in chart['visited']:
            self.assertNotIn(nid, enterable,
                             f'cleared node {nid} offered for entry')

    def test_discovered_uncleared_left_behind_nodes_stay_enterable(self):
        chart = _chart()
        graph = chart['graph']
        start = graph['start_node_id']
        # Left-behind siblings: the start row's lateral neighbour (the grid
        # topology links row 1 as a chain, so start has exactly one).
        start_depth = graph['nodes'][start]['depth']
        siblings = [k for k in delve_gen.chart_children(graph, start)
                    if not k.get('dead_end')
                    and k['depth'] == start_depth][:2]
        self.assertGreaterEqual(len(siblings), 1)
        # Clear the start row only.
        graph['nodes'][start]['state'] = delve_gen.STATE_CLEARED
        enterable = set(delve_gen.enterable_node_ids(graph, chart))
        for kid in siblings:
            self.assertIn(kid['id'], enterable)

        # Now move somewhere else entirely: the left-behind nodes must
        # still be enterable (retreating is legal).
        forward = sorted(n for n in enterable
                         if graph['nodes'][n]['depth'] == 2)
        self.assertTrue(forward)
        chart['current_node_id'] = forward[0]
        graph['nodes'][forward[0]]['state'] = delve_gen.STATE_CLEARED
        chart['visited'].append(forward[0])
        enterable = set(delve_gen.enterable_node_ids(graph, chart))
        for kid in siblings:
            self.assertIn(kid['id'], enterable,
                          'left-behind node became unenterable')

    def test_locked_far_off_nodes_are_not_enterable(self):
        chart = _chart()
        graph = chart['graph']
        cleared = {graph['start_node_id']}
        current = chart['current_node_id']
        forward = {k['id'] for k in delve_gen.chart_children(graph, current)}
        enterable = set(delve_gen.enterable_node_ids(graph, chart))
        for parent, child in graph['edges']:
            if parent in cleared or child in forward:
                continue
            self.assertNotIn(child, enterable,
                             f'undiscovered node {child} offered')

    def test_dead_ends_are_not_enterable(self):
        chart = _chart()
        graph = chart['graph']
        enterable = set(delve_gen.enterable_node_ids(graph, chart))
        for nid in enterable:
            self.assertFalse(graph['nodes'][nid].get('dead_end'))

    def test_beaten_child_cannot_be_redone_after_retreat(self):
        """Owner fix 2026-10-07: retreating to a cleared parent must never
        re-offer its already-beaten children (the force-add used to
        override the cleared filter)."""
        chart = _chart()
        graph = chart['graph']
        start = graph['start_node_id']
        forward = [k for k in delve_gen.chart_children(graph, start)
                   if k['depth'] == 2 and not k.get('dead_end')]
        self.assertTrue(forward, 'seed produced no live depth-2 child')
        child = forward[0]
        for nid in (start, child['id']):
            graph['nodes'][nid]['state'] = delve_gen.STATE_CLEARED
            if nid not in chart['visited']:
                chart['visited'].append(nid)
        chart['current_node_id'] = start            # retreated to the parent
        enterable = set(delve_gen.enterable_node_ids(graph, chart))
        self.assertNotIn(child['id'], enterable,
                         'beaten child offered for a redo')
        self.assertNotIn(start, enterable)


class DepthTests(unittest.TestCase):
    def test_retreating_lowers_current_depth(self):
        # Children are vertical now (a lane); follow one alive lane three
        # rows deep, then stand back on its row-2 node.
        chart = None
        graph = None
        chain = []
        for seed in range(1, 60):
            chart = _chart(seed=seed)
            graph = chart['graph']
            node = graph['nodes'][graph['start_node_id']]
            chain = [node]
            for _ in range(2):
                kids = [k for k in delve_gen.chart_children(graph, node['id'])
                        if k['depth'] == node['depth'] + 1
                        and not k.get('dead_end')]
                if not kids:
                    break
                node = kids[0]
                chain.append(node)
            if len(chain) == 3:
                break
        if len(chain) != 3:
            self.skipTest('no seeded chart kept one lane alive to depth 3')
        self.assertEqual(chain[2]['depth'], 3)

        # Retreat: standing back on the row-2 node of the same lane.
        chart['current_node_id'] = chain[1]['id']
        self.assertEqual(graph['nodes'][chart['current_node_id']]['depth'], 2)
        self.assertLess(graph['nodes'][chart['current_node_id']]['depth'],
                        graph['nodes'][chain[2]['id']]['depth'])

    def test_depth_record_never_decreases(self):
        chart = _play_forward(_chart(), 3)
        record = delve_gen.chart_best_depth(chart)
        self.assertGreaterEqual(record, 3)

        # Retreat to a shallower node: the record must stay put.
        graph = chart['graph']
        shallow = min((nid for nid in chart['visited']),
                      key=lambda nid: graph['nodes'][nid]['depth'])
        chart['current_node_id'] = shallow
        self.assertEqual(delve_gen.chart_best_depth(chart), record)

    def test_record_survives_a_chart_with_only_a_stored_value(self):
        chart = _chart()
        chart['best_depth'] = 42
        chart['visited'] = []
        self.assertEqual(delve_gen.chart_best_depth(chart), 42)


class FlowSelectionTests(unittest.TestCase):
    """The flow-level entry points must expose the same rule as the helper."""

    def _game(self, chart, depth):
        from core.game import Game
        game = Game.__new__(Game)
        game._delve = {'state': 'ready', 'depth': depth, 'chart': chart}
        game._chart_rng = random.Random(3)
        return game

    def test_delve_children_exposes_backward_and_forward_nodes(self):
        chart = _chart()
        graph = chart['graph']
        start = graph['start_node_id']
        forward = [k['id'] for k in delve_gen.chart_children(graph, start)
                   if not k.get('dead_end') and k['depth'] == 2]
        graph['nodes'][start]['state'] = delve_gen.STATE_CLEARED
        chart['current_node_id'] = forward[0]
        graph['nodes'][forward[0]]['state'] = delve_gen.STATE_CLEARED
        chart['visited'].append(start)

        game = self._game(chart, 2)
        ids = [k['id'] for k in game._delve_children()]
        self.assertNotIn(start, ids)                       # cleared: no
        kids = {k['id'] for k in delve_gen.chart_children(graph, forward[0])
                if not k.get('dead_end')}
        self.assertTrue(kids, 'the depth-2 node has no children')
        self.assertTrue(kids <= set(ids), 'forward children not offered')

    def test_hub_resume_chart_offers_more_than_the_current_node(self):
        """The hub resume path used to lock selection to current_node_id."""
        from core.game import Game

        class _Screen:
            def __init__(self):
                self.selectable_ids = ()
                self.zoom = None

            def open(self, chart, selectable_ids=(), **kwargs):
                self.selectable_ids = tuple(selectable_ids)

        chart = _chart()
        graph = chart['graph']
        start = graph['start_node_id']
        forward = [k['id'] for k in delve_gen.chart_children(graph, start)
                   if not k.get('dead_end') and k['depth'] == 2]
        graph['nodes'][start]['state'] = delve_gen.STATE_CLEARED
        chart['current_node_id'] = forward[0]
        chart['visited'].append(start)

        from entities.progression import Character
        game = Game.__new__(Game)
        game._saved_delve = {'delve': {'chart': chart}, 'map': [], 'zombies': [],
                             'ground_items': [], 'decor_items': []}
        game._char = Character('audit-1', 'Audit')
        game._chart_screen = _Screen()
        game._chart_resume = True
        game._hub_popup = None
        game._open_anima_panel()
        offered = game._chart_screen.selectable_ids
        kids = {k['id'] for k in delve_gen.chart_children(
            graph, chart['current_node_id']) if not k.get('dead_end')}
        self.assertTrue(kids <= set(offered),
                        'the resume path locked out forward children')
        self.assertNotIn(start, offered)
        self.assertNotIn(chart['current_node_id'], offered)

    def test_cleared_node_entry_is_impossible_so_no_respawn(self):
        """A cleared node can never be entered, so it can never respawn
        enemies; a discovered-uncleared node is a normal entry."""
        chart = _play_forward(_chart(), 2)
        graph = chart['graph']
        cleared = set(chart['visited'])
        enterable = set(delve_gen.enterable_node_ids(graph, chart))
        self.assertEqual(cleared & enterable, set())
        uncleared = enterable - cleared
        self.assertTrue(uncleared,
                        'no discovered-uncleared node to re-enter')
        for nid in uncleared:
            self.assertNotEqual(graph['nodes'][nid]['state'],
                                delve_gen.STATE_CLEARED)


# ── Part 4: modal UI ───────────────────────────────────────────────────


def _install_headless(monkeypatch_text=None):
    """Patch the pyray calls the chart screen makes; return captured text."""
    drawn = []
    patches = {}
    for name, value in (
        ('get_screen_width', lambda: 1280),
        ('get_screen_height', lambda: 720),
        ('get_mouse_x', lambda: -1),
        ('get_mouse_y', lambda: -1),
        ('get_mouse_wheel_move', lambda: 0.0),
        ('is_window_focused', lambda: True),
        ('is_mouse_button_down', lambda _b: False),
        ('check_collision_point_rec', lambda *_a: False),
        ('begin_scissor_mode', lambda *_a: None),
        ('end_scissor_mode', lambda *_a: None),
        ('clear_background', lambda *_a: None),
    ):
        patches[name] = patch.object(chart_mod.rl, name, value)
    for name in ('draw_rectangle', 'draw_rectangle_lines', 'draw_circle',
                 'draw_line', 'draw_line_ex', 'draw_texture_pro'):
        patches[name] = patch.object(chart_mod.rl, name, lambda *_a, **_k: None)
    for p in patches.values():
        p.start()
    # Capture (text, x, y) so tests can assert *where* text landed, not just
    # that it was drawn.
    patches['_text'] = patch.object(
        chart_mod.fonts, 'draw',
        lambda text, x=0, y=0, *a, **k: drawn.append((str(text), x, y)))
    patches['_text'].start()
    patches['_measure'] = patch.object(
        chart_mod.fonts, 'measure', lambda text, size: len(text) * size)
    patches['_measure'].start()
    # Loading a real texture needs a GL context; the glyph fallback path is
    # what the draw smoke test is about.
    patches['_icon'] = patch.object(
        chart_mod, '_reward_icon', lambda _item_id: None)
    patches['_icon'].start()
    from ui import icons
    patches['_uiicons'] = patch.object(icons, 'draw', lambda *_a, **_k: None)
    patches['_uiicons'].start()
    patches['_btn_tex'] = patch.object(
        chart_mod, '_enter_button_tex', lambda pressed=False: None)
    patches['_btn_tex'].start()
    return patches, drawn


def _stop(patches):
    for p in patches.values():
        p.stop()


class ModalUiTests(unittest.TestCase):
    VIEW = (1000, 600)
    ORIGIN = (140, 60)

    def _draw_modal(self, chart, selectable=()):
        patches, drawn = _install_headless()
        try:
            screen = DelveChartScreen(object())
            screen.open(chart, selectable_ids=selectable)
            screen.draw(1280, 720, origin=self.ORIGIN, view=self.VIEW)
            return screen, drawn
        finally:
            _stop(patches)

    def _in_modal(self, x, y):
        ox, oy = self.ORIGIN
        return ox <= x < ox + self.VIEW[0] and oy <= y < oy + self.VIEW[1]

    def test_modal_draws_no_counters_or_best_depth(self):
        """Nothing but the chart is drawn INSIDE the modal: no flare/dynamite
        counters and no best-depth text."""
        chart = _play_forward(_chart(), 2)
        _screen, drawn = self._draw_modal(chart)
        for banned in ('Flares', 'Dynamite', 'Best Depth', 'BEST DEPTH'):
            offenders = [d for d in drawn
                         if banned in d[0] and self._in_modal(d[1], d[2])]
            self.assertEqual(offenders, [], f'{banned!r} drawn inside the modal')

    def test_best_depth_is_drawn_on_the_screen_frame(self):
        chart = _play_forward(_chart(), 2)
        record = delve_gen.chart_best_depth(chart)
        _screen, drawn = self._draw_modal(chart)
        outside = [d for d in drawn
                   if 'BEST DEPTH' in d[0] and not self._in_modal(d[1], d[2])]
        self.assertTrue(outside, 'BEST DEPTH is not drawn outside the modal')
        # The record value, not the current (possibly shallower) depth.
        current = chart['graph']['nodes'][chart['current_node_id']]['depth']
        self.assertEqual(record, delve_gen.chart_best_depth(chart))
        self.assertGreaterEqual(record, current)
        values = [d for d in drawn
                  if d[0].strip() == str(record)
                  and not self._in_modal(d[1], d[2])]
        self.assertTrue(values,
                        'the best-depth record value is not shown outside')

    def test_return_to_hub_button_is_drawn(self):
        screen, drawn = self._draw_modal(_chart())
        self.assertTrue(any('RETURN TO HUB' in d[0] for d in drawn))
        self.assertIsNotNone(screen._return_btn)
        rect = screen._return_btn
        # Bottom-right of the modal surface, not of the whole screen.
        self.assertGreater(rect.x, self.VIEW[0] * 0.6)
        self.assertGreater(rect.y, self.VIEW[1] * 0.8)

    def test_return_button_click_is_reported(self):
        patches, _drawn = _install_headless()
        try:
            screen = DelveChartScreen(object())
            screen.open(_chart(), selectable_ids=())
            screen.draw(1280, 720, origin=self.ORIGIN, view=self.VIEW)
            rect = screen._return_btn
            # Cursor over the button, in screen coords (origin is added back).
            cx = self.ORIGIN[0] + rect.x + rect.width / 2
            cy = self.ORIGIN[1] + rect.y + rect.height / 2
            chart_mod.inp._mouse_prev.clear()
            chart_mod.inp._mouse_release_prev.clear()
            chart_mod.inp._focus_was = True
            with patch.object(chart_mod.rl, 'get_mouse_x', return_value=int(cx)), \
                 patch.object(chart_mod.rl, 'get_mouse_y', return_value=int(cy)), \
                 patch.object(chart_mod.rl, 'check_collision_point_rec',
                              side_effect=lambda pt, r: _hits(pt, r)), \
                 patch.object(chart_mod.rl, 'is_mouse_button_down',
                              return_value=True):
                result = screen.update(0.016, origin=self.ORIGIN,
                                       view=self.VIEW)
            self.assertEqual(result, ('return_hub', None))
        finally:
            _stop(patches)

    def test_no_code_reads_a_removed_tool_field(self):
        """Repo guard for removed flare/dynamite reads lives in
        test_render_smoke.py; here we pin the saved-chart shape so a stale
        'charges' entry can never come back through persistence."""
        import ast
        from pathlib import Path
        tree = ast.parse(Path('core/delve_flow.py').read_text(encoding='utf-8'))
        literals = {n.value for n in ast.walk(tree)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        self.assertNotIn('charges', literals)
        self.assertNotIn('flares', literals)
        self.assertNotIn('dynamite', literals)

    def test_removed_tool_state_is_absent_from_saved_chart_shape(self):
        """A fresh chart must not carry the removed tool bookkeeping."""
        chart = _chart()
        for key in ('charges',):
            self.assertNotIn(key, chart)

    def test_removed_tool_keybinds_are_gone(self):
        from pathlib import Path
        source = Path('core/input.py').read_text(encoding='utf-8')
        self.assertNotIn('_throw_flare', source)
        self.assertNotIn('_throw_dynamite', source)


def _hits(point, rect):
    return (rect.x <= point.x <= rect.x + rect.width
            and rect.y <= point.y <= rect.y + rect.height)


class DrawSmokeTests(unittest.TestCase):
    def test_open_update_and_draw_smoke(self):
        chart = _play_forward(_chart(), 2)
        patches, _drawn = _install_headless()
        try:
            screen = DelveChartScreen(object())
            enterable = delve_gen.enterable_node_ids(chart['graph'], chart)
            screen.open(chart, selectable_ids=enterable,
                        on_select=lambda _nid: None)
            for _ in range(3):
                self.assertIsNone(
                    screen.update(0.016, origin=(10, 10), view=(800, 500)))
            screen.draw(1280, 720, origin=(10, 10), view=(800, 500))
            # Fullscreen (in-delve minimap) mode too.
            screen.draw(1280, 720)
            self.assertIsNone(screen._tooltip_btn)
        finally:
            _stop(patches)


if __name__ == '__main__':
    unittest.main(verbosity=2)
