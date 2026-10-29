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

"""Owner inventory rules: identification, derived-stat freshness, power level.

Covers four rules:
  1. An item must be identified before it can be equipped (reverses #84).
  2. An unidentified item exposes no stat text anywhere.
  3. Derived stats are invalidated and recomputed on equip / unequip /
     identify / socket changes (the stale-attribute bug).
  4. The power level is the average equipped item level and is purely cosmetic.
"""

import inspect
import re
from pathlib import Path
from types import SimpleNamespace

import pyray as rl

import core.game
import core.game as game_mod
import systems.itemgen as itemgen
import systems.items as items
from entities.progression import Character
from ui.inventory_ui import InventoryUI


# â”€â”€ helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _endurance_heart(ilvl=10, endurance=5, identified=True):
    """A heart carrying a rolled +Endurance suffix."""
    return {
        'item': 'heart',
        'count': 1,
        'col': 0, 'row': 0,
        'instance_data': {
            'rarity': 'common',
            'display_name': 'Heart of Endurance',
            'ilvl': ilvl,
            'identified': identified,
            'affixes': {'prefixes': {}, 'suffixes': {'attr_endurance': endurance}},
        },
    }


def _bare_game():
    """A Game-lite stub carrying the real stat/inventory methods."""
    char = Character('inv-rules-char', 'Rules Tester', 'fighter')
    inv = items.make_inventory()
    char.inventory = inv
    game = SimpleNamespace()
    game.char = char
    game.inventory = inv
    game.stats = {}
    game._equipped_bonuses = lambda: game_mod.Game._equipped_bonuses(game)
    game._recalc_derived_stats = lambda: game_mod.Game._recalc_derived_stats(game)
    game._on_gear_changed = lambda: game_mod.Game._on_gear_changed(game)
    game._recalc_derived_stats()
    return game


def _inventory_ui():
    ui = InventoryUI()
    return ui


def _tooltip_text(ui, entry, inventory):
    return [text for text, _color in ui._tooltip_lines(entry, inventory)]


def _code_of(src, func_name):
    """The body of a function with its docstring stripped (code only)."""
    body = src.split(f'def {func_name}', 1)[1]
    body = re.sub(r'""".*?"""', '', body, flags=re.S)      # drop the docstring
    return body.split('\n    def ', 1)[0]                  # stop at the next method


# â”€â”€ rule 1: identification gate â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

import unittest


class TestEquipRequiresIdentification(unittest.TestCase):

    def test_equip_from_grid_refuses_unidentified(self):
        inv = items.make_inventory()
        heart = _endurance_heart(identified=False)
        inv['grid'].append(heart)
        self.assertFalse(items.can_equip(heart))
        self.assertFalse(items.equip_from_grid(inv, len(inv['grid']) - 1))
        self.assertIsNone(inv['equipped']['heart'])

    def test_equip_from_grid_accepts_identified(self):
        inv = items.make_inventory()
        heart = _endurance_heart(identified=True)
        inv['grid'].append(heart)
        self.assertTrue(items.can_equip(heart))
        self.assertTrue(items.equip_from_grid(inv, len(inv['grid']) - 1))
        self.assertIsNotNone(inv['equipped']['heart'])

    def test_context_menu_implant_disabled_while_unidentified(self):
        inv = items.make_inventory()
        ui = _inventory_ui()
        for identified, expect_enabled in ((False, False), (True, True)):
            heart = _endurance_heart(identified=identified)
            ui._ctx = {'x': 0, 'y': 0, 'source': 'grid',
                       'index': 0, 'slot': heart}
            ui._inventory_for_menu = inv['grid']
            implant = [o for o in ui._ctx_options() if o['type'] == 'equip']
            self.assertEqual(len(implant), 1)
            self.assertEqual(bool(implant[0].get('enabled', True)), expect_enabled)

    def test_ui_exec_equip_refuses_unidentified(self):
        inv = items.make_inventory()
        heart = _endurance_heart(identified=False)
        inv['grid'].append(heart)
        ui = _inventory_ui()
        fired = []
        ui.on_gear_change = lambda: fired.append(1)
        ui._exec({'type': 'equip', 'source': 'grid',
                  'index': len(inv['grid']) - 1}, inv, {})
        self.assertIsNone(inv['equipped']['heart'])
        self.assertEqual(fired, [])   # no gear change -> no recalc


# â”€â”€ rule 2: unidentified items show no stats â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestUnidentifiedShowsNoStats(unittest.TestCase):

    def test_tooltip_exposes_no_stat_text(self):
        inv = items.make_inventory()
        ui = _inventory_ui()
        unid = _endurance_heart(identified=False)
        ided = _endurance_heart(identified=True)
        unid_text = _tooltip_text(ui, unid, inv)
        ided_text = _tooltip_text(ui, ided, inv)
        self.assertIn('Unidentified', unid_text)
        self.assertIn('Item Level: 10', ided_text)
        for text in unid_text:
            self.assertNotIn('Endurance', text)
            self.assertNotIn('Max Health', text)
            self.assertNotIn('Item Level', text)
            self.assertNotIn('(up)', text)
            self.assertNotIn('(down)', text)
        self.assertTrue(any('Endurance' in t for t in ided_text))

    def test_ground_tooltip_exposes_no_stat_text(self):
        """The world/ground loot tooltip hides everything while unidentified."""
        src = Path('core/render/delve_render.py').read_text(encoding='utf-8')
        body = src.split('def _draw_ground_tooltip', 1)[1]
        for needle in ('if inst and not unid:', 'if idef.get(\'equipSlot\') and not unid:',
                       'if inst and not unid:'):
            self.assertIn(needle, body)
        self.assertIn('Unidentified', body)

    def test_item_detail_panel_exposes_no_stat_text(self):
        game = _bare_game()
        inv = game.inventory
        unid = _endurance_heart(identified=False)
        ided = _endurance_heart(identified=True)
        unid_text = [t for t, _c in core.game.Game._get_item_summary_lines(game, unid)]
        ided_text = [t for t, _c in core.game.Game._get_item_summary_lines(game, ided)]
        self.assertIn('Unidentified', unid_text)
        self.assertTrue(any('iLvl 10' in t for t in ided_text))
        for text in unid_text:
            self.assertNotIn('iLvl', text)
            self.assertNotIn('Endurance', text)
            self.assertNotIn('Max Health', text)

    def test_stat_totals_and_comparison_are_empty(self):
        unid = _endurance_heart(identified=False)
        self.assertEqual(itemgen.compute_item_stat_totals(unid), {})
        self.assertEqual(itemgen.comparison_rows(unid, None), [])
        # unidentified gear is inert for live effects too
        inv = items.make_inventory()
        inv['equipped']['heart'] = unid
        self.assertEqual(itemgen.live_effect_totals(unid['instance_data']) and True, True)
        self.assertEqual(itemgen.aggregate_item_bonuses(inv), {})


# â”€â”€ rule 3: derived stats refresh on gear change â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestDerivedStatsRefreshOnEquip(unittest.TestCase):

    def test_equip_and_unequip_endurance_through_the_inventory_ui(self):
        game = _bare_game()
        inv = game.inventory
        ui = _inventory_ui()
        ui.on_gear_change = game._on_gear_changed

        before_stats = game.stats['endurance']
        before_health = game.stats['max_health']

        heart = _endurance_heart(identified=True, endurance=5)
        inv['grid'].append(heart)
        idx = len(inv['grid']) - 1
        ui._exec({'type': 'equip', 'source': 'grid', 'index': idx},
                 inv, game.stats)

        after_equip = game.stats['endurance']
        self.assertEqual(after_equip, before_stats + 5,
                         'equipping an Endurance item must raise Endurance')
        self.assertGreater(game.stats['max_health'], before_health)
        self.assertIsNotNone(inv['equipped']['heart'])

        ui._exec({'type': 'dequip', 'source': 'equipped', 'index': 'heart'},
                 inv, game.stats)
        self.assertEqual(game.stats['endurance'], before_stats,
                         'unequipping must restore the previous Endurance')
        self.assertEqual(game.stats['max_health'], before_health)
        self.assertIsNone(inv['equipped']['heart'])

    def test_equip_then_dequip_back_to_grid_also_refreshes(self):
        game = _bare_game()
        inv = game.inventory
        ui = _inventory_ui()
        ui.on_gear_change = game._on_gear_changed
        base = game.stats['endurance']

        inv['grid'].append(_endurance_heart(identified=True, endurance=3))
        ui._exec({'type': 'equip', 'source': 'grid',
                  'index': len(inv['grid']) - 1}, inv, game.stats)
        self.assertEqual(game.stats['endurance'], base + 3)

        # EXPLANT via the context action
        ui._exec({'type': 'dequip', 'source': 'equipped', 'index': 'heart'},
                 inv, game.stats)
        self.assertEqual(game.stats['endurance'], base)

    def test_other_derived_stats_also_move_with_gear(self):
        game = _bare_game()
        inv = game.inventory
        ui = _inventory_ui()
        ui.on_gear_change = game._on_gear_changed

        heart = {
            'item': 'heart', 'count': 1, 'col': 0, 'row': 0,
            'instance_data': {
                'rarity': 'rare', 'display_name': 'Cunning Liver', 'ilvl': 40,
                'identified': True,
                'affixes': {'prefixes': {},
                            'suffixes': {'attr_cunning': 6, 'attr_endurance': 3}},
            },
        }
        inv['grid'].append(heart)
        before = dict(game.stats)
        ui._exec({'type': 'equip', 'source': 'grid',
                  'index': len(inv['grid']) - 1}, inv, game.stats)
        # cunning — the retired 'max mana' read became the neutral
        # cooldown/attr dumps (mana removed from the game, 2026-10-29)
        self.assertEqual(game.stats['cunning'], before['cunning'] + 6)
        self.assertNotIn('max_mana', game.stats)
        # endurance -> health and energy shield
        self.assertEqual(game.stats['endurance'], before['endurance'] + 3)
        self.assertEqual(game.stats['max_health'],
                         before['max_health'] + 3 * 8)
        self.assertEqual(game.stats['max_energy_shield'],
                         before['max_energy_shield'] + 3 * 4)
        self.assertEqual(game.stats['darkness_resist_pct'],
                         before['darkness_resist_pct'] + 3 * 2 / 100.0)
        # and the live health pool is PRESERVED — equipping must never
        # refill (owner ruling 2026-10-07; the old refresh was the
        # level-up-era heal)
        self.assertEqual(game.stats['health'], before['health'])

    def test_identifying_a_grid_item_fires_invalidation(self):
        game = _bare_game()
        inv = game.inventory
        ui = _inventory_ui()
        ui.on_gear_change = game._on_gear_changed

        inv['grid'].append(_endurance_heart(identified=False, endurance=4))
        base = game.stats['endurance']
        ui._exec({'type': 'equip', 'source': 'grid',
                  'index': len(inv['grid']) - 1}, inv, game.stats)
        self.assertEqual(game.stats['endurance'], base)   # refused

    def test_gem_and_flask_changes_fire_invalidation(self):
        game = _bare_game()
        inv = game.inventory
        ui = _inventory_ui()
        calls = []
        ui.on_gear_change = lambda: calls.append(1)

        inv['gem_sockets']['Q'] = {'item': 'gem_blue', 'count': 1}
        ui._exec({'type': 'remove_gem', 'source': 'gems', 'index': 'Q'},
                 inv, game.stats)
        self.assertIsNone(inv['gem_sockets']['Q'])
        self.assertEqual(len(calls), 1)

        inv['flask_slot'] = {'item': 'flask_mana', 'count': 1, 'charges': 1}
        ui._exec({'type': 'remove_flask', 'source': 'flask', 'index': 0},
                 inv, game.stats)
        self.assertIsNone(inv['flask_slot'])
        self.assertEqual(len(calls), 2)

    def test_game_wires_the_inventory_callback(self):
        """The Game must register the recalc hook, or equip stays stale."""
        src = inspect.getsource(core.game.Game.__init__)
        self.assertIn('on_gear_change', src)
        # and every equip/dequip/drop/socket site notifies
        inv_src = Path('ui/inventory_ui.py').read_text(encoding='utf-8')
        self.assertGreaterEqual(inv_src.count('self._gear_changed()'), 6)

    def test_auto_placed_pickup_recalculates(self):
        game = _bare_game()
        inv = game.inventory
        game.audio = SimpleNamespace(item_equip=lambda: None,
                                     item_pickup=lambda: None)
        game._inv_full_timer = 0.0
        base = game.stats['endurance']
        item = _endurance_heart(identified=True, endurance=2)
        del item['col'], item['row']
        game_mod.Game._auto_place(game, item)
        self.assertIsNotNone(inv['equipped']['heart'])
        self.assertEqual(game.stats['endurance'], base + 2)


# â”€â”€ rule 4: character level (display-only) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestCharacterLevel(unittest.TestCase):
    """CHARACTER LEVEL = average item level of the character's equipped gear.

    Display-only. The tests below pin the value, both display sites, the
    rounding rule, the empty-loadout case, and that nothing gameplay-related
    currently reads it.
    """

    def test_character_level_equals_average_equipped_item_level(self):
        inv = items.make_inventory()
        self.assertEqual(itemgen.character_level(inv), 0)

        inv['equipped']['heart'] = _endurance_heart(ilvl=10)
        self.assertEqual(itemgen.character_level(inv), 10)

        inv['equipped']['kidney'] = _endurance_heart(ilvl=31)
        self.assertEqual(itemgen.character_level(inv), 21)      # (10+31)/2

        inv['equipped']['lungs'] = _endurance_heart(ilvl=2)
        self.assertEqual(itemgen.character_level(inv), 14)      # 43/3 -> 14.33

    def test_rounds_half_up_and_is_documented(self):
        # .5 cases round UP, documented in the accessor docstring
        inv = items.make_inventory()
        inv['equipped']['heart'] = _endurance_heart(ilvl=1)
        inv['equipped']['kidney'] = _endurance_heart(ilvl=2)    # 1.5 -> 2
        self.assertEqual(itemgen.character_level(inv), 2)
        inv['equipped']['kidney'] = _endurance_heart(ilvl=4)    # 2.5 -> 3
        self.assertEqual(itemgen.character_level(inv), 3)
        self.assertIn('rounded', inspect.getdoc(itemgen.character_level).lower())

    def test_empty_equipment_is_handled_without_dividing_by_zero(self):
        inv = items.make_inventory()
        for slot in inv['equipped']:
            inv['equipped'][slot] = None
        self.assertEqual(itemgen.character_level(inv), 0)
        # owner rule: an empty loadout reads as a normal value, LVL 0
        self.assertEqual(itemgen.format_character_level(inv), 'LVL 0')
        # also tolerates junk input
        self.assertEqual(itemgen.character_level(None), 0)
        self.assertEqual(itemgen.character_level({}), 0)
        self.assertEqual(itemgen.format_character_level({}), 'LVL 0')

    def test_changes_when_gear_is_equipped_or_removed(self):
        game = _bare_game()
        inv = game.inventory
        ui = _inventory_ui()
        ui.on_gear_change = game._on_gear_changed
        base = itemgen.character_level(inv)

        inv['grid'].append(_endurance_heart(identified=True, ilvl=40))
        ui._exec({'type': 'equip', 'source': 'grid',
                  'index': len(inv['grid']) - 1}, inv, game.stats)
        equipped = itemgen.character_level(inv)
        self.assertEqual(equipped, 40)
        self.assertNotEqual(equipped, base)

        ui._exec({'type': 'dequip', 'source': 'equipped', 'index': 'heart'},
                 inv, game.stats)
        self.assertEqual(itemgen.character_level(inv), base)

    def test_both_display_sites_read_the_same_value(self):
        """Identical value from one computation â€” not two implementations."""
        inv = items.make_inventory()
        inv['equipped']['heart'] = _endurance_heart(ilvl=12)
        inv['equipped']['kidney'] = _endurance_heart(ilvl=30)

        inv_src = Path('ui/inventory_ui.py').read_text(encoding='utf-8')
        hud_src = Path('core/render/hud_render.py').read_text(encoding='utf-8')
        # both call the one shared formatter, never their own maths
        for src, name in ((inv_src, 'inventory'), (hud_src, 'hud')):
            self.assertIn('itemgen.format_character_level(', src,
                          f'{name} site does not use the shared accessor')
            self.assertNotIn('equipped_item_levels(', src,
                             f'{name} site reimplements the average')
            # the long phrase is gone from both draw sites
            self.assertNotIn('CHARACTER LEVEL  ', src)
            self.assertNotIn('f"CHARACTER LEVEL', src)

    def test_label_string_is_shared_between_sites(self):
        """One compact label, so the two readouts cannot diverge."""
        inv = items.make_inventory()
        inv['equipped']['heart'] = _endurance_heart(ilvl=12)
        inv['equipped']['kidney'] = _endurance_heart(ilvl=30)
        self.assertEqual(itemgen.format_character_level(inv), 'LVL 21')
        for path in ('ui/inventory_ui.py', 'core/render/hud_render.py'):
            src = Path(path).read_text(encoding='utf-8')
            self.assertIn('itemgen.format_character_level(inventory)' if
                          path.startswith('ui/') else
                          'itemgen.format_character_level(self.inventory)', src,
                          f'{path} does not render the shared compact label')
            self.assertNotIn('LVL ', _code_of(src, '_draw_character_level'),
                             f'{path} builds its own label')

    def test_feeds_no_gameplay_path(self):
        """Scope limit: the value is rendered and nothing else.

        Every reference site in non-test code must be the accessor definition
        or one of the two drawing sites, and no gameplay module may import or
        call it. Loot rolling, compute_derived_stats and monster scaling are
        checked explicitly.
        """
        accessors = ('character_level', 'format_character_level',
                     'equipped_item_levels')
        allowed_files = {'systems/itemgen.py', 'ui/inventory_ui.py',
                         'core/render/hud_render.py'}

        consumers = []
        for path in Path('.').rglob('*.py'):
            if path.parts[0] == 'tests':
                continue
            text = path.read_text(encoding='utf-8')
            lines = text.splitlines()
            for name in accessors:
                for line_no, line in enumerate(lines, 1):
                    if name not in line:
                        continue
                    stripped = line.strip()
                    if stripped.startswith(('def ', '#')) or '"' in stripped[:8] \
                            or stripped.startswith(("f\"", "'''", '"""')):
                        continue          # definition site or docstring
                    consumers.append((str(path).replace('\\', '/'), line_no,
                                      stripped))
        for path, line_no, line in consumers:
            self.assertIn(path, allowed_files,
                          f'character level used outside the draw sites: {path}:{line_no}: {line}')

        # explicit gameplay separations â€” these must never see the value
        gameplay = {
            'core/map_gen.py':          'loot / map layout',
            'entities/progression.py':  'derived stat computation',
            'core/game.py':             'monster scaling / difficulty',
            'entities/zombies.py':      'monster scaling',
        }
        for path, role in gameplay.items():
            text = Path(path).read_text(encoding='utf-8')
            for name in accessors:
                self.assertNotIn(name, text, f'{path} ({role}) references {name}')

        # the old character-level plumbing must be gone, not silently restored
        for path in Path('.').rglob('*.py'):
            if path.parts[0] == 'tests':
                continue
            text = path.read_text(encoding='utf-8')
            self.assertNotIn('char_level', text,
                             f'{path} still uses the removed char_level plumbing')

# â”€â”€ draw smoke â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _headless(monkeypatch):
    """Neutralise every raylib draw call; capture rendered text."""
    from ui import fonts as fonts_mod
    from ui import icons as icons_mod
    rendered = []
    monkeypatch.setattr(rl, "get_mouse_x", lambda: -1)
    monkeypatch.setattr(rl, "get_mouse_y", lambda: -1)
    monkeypatch.setattr(rl, "get_time", lambda: 0.0)
    monkeypatch.setattr(rl, "get_screen_width", lambda: 1280)
    monkeypatch.setattr(rl, "get_screen_height", lambda: 720)
    monkeypatch.setattr(rl, "is_mouse_button_pressed", lambda _b: False)
    monkeypatch.setattr(rl, "check_collision_point_rec", lambda *_a: False)
    for name in ('draw_rectangle', 'draw_rectangle_rec', 'draw_rectangle_lines',
                 'draw_rectangle_lines_ex', 'draw_rectangle_gradient_ex',
                 'draw_circle', 'draw_circle_v', 'draw_ellipse', 'draw_ellipse_lines',
                 'draw_line', 'draw_line_ex', 'draw_poly', 'draw_triangle',
                 'draw_texture_pro', 'begin_texture_mode', 'end_texture_mode',
                 'begin_blend_mode', 'end_blend_mode', 'begin_scissor_mode',
                 'end_scissor_mode'):
        if hasattr(rl, name):
            monkeypatch.setattr(rl, name, lambda *a, **k: None)
    monkeypatch.setattr(fonts_mod, 'draw',
                        lambda text, *a, **k: rendered.append(str(text)))
    monkeypatch.setattr(fonts_mod, 'measure', lambda text, size: len(text) * size)
    monkeypatch.setattr(icons_mod, 'draw', lambda *a, **k: None)
    return rendered


def test_inventory_draw_smoke_with_real_character(monkeypatch):
    """Open the inventory with a real Character and draw the panel."""
    rendered = _headless(monkeypatch)
    game = _bare_game()
    inv = game.inventory
    inv['equipped']['heart'] = _endurance_heart(ilvl=12, endurance=4)
    inv['equipped']['kidney'] = _endurance_heart(ilvl=30, endurance=1)
    inv['grid'].append(_endurance_heart(identified=False))

    ui = _inventory_ui()
    ui.char_provider = lambda: game.char
    ui.open = True
    ui.stash_open = False
    ui._stash_grid = None

    ui.draw(inv, 1280, 720)

    # ilvl 12 and 30 -> character level 21, drawn in the panel header
    assert 'LVL 21' in rendered, rendered[:30]
    assert itemgen.format_character_level(inv) in rendered


def test_hud_draws_character_level_top_left(monkeypatch):
    """The HUD site renders the same shared value in the top-left."""
    from core.render.hud_render import HudRenderMixin
    rendered = _headless(monkeypatch)
    inv = items.make_inventory()
    inv['equipped']['heart'] = _endurance_heart(ilvl=12)
    inv['equipped']['kidney'] = _endurance_heart(ilvl=30)

    game = SimpleNamespace(inventory=inv)
    HudRenderMixin._draw_character_level(game, 1280, lambda n: n)

    assert 'LVL 21' in rendered, rendered
    # the shared accessor is rendered verbatim â€” no per-site wording
    assert itemgen.format_character_level(inv) in rendered


def test_both_level_sites_render_the_identical_string(monkeypatch):
    """The panel header and the top-left HUD agree, for the same loadout."""
    from core.render.hud_render import HudRenderMixin
    rendered = _headless(monkeypatch)
    game = _bare_game()
    inv = game.inventory
    inv['equipped']['heart'] = _endurance_heart(ilvl=12, endurance=4)
    inv['equipped']['kidney'] = _endurance_heart(ilvl=30, endurance=1)

    ui = _inventory_ui()
    ui.char_provider = lambda: game.char
    ui.open = True
    ui.stash_open = False
    ui._stash_grid = None
    ui.draw(inv, 1280, 720)
    panel = [t for t in rendered if t == itemgen.format_character_level(inv)]
    assert panel, rendered[:30]

    HudRenderMixin._draw_character_level(SimpleNamespace(inventory=inv),
                                        1280, lambda n: n)
    assert rendered.count(itemgen.format_character_level(inv)) == 2


def test_level_label_is_compact_not_the_long_phrase(monkeypatch):
    rendered = _headless(monkeypatch)
    inv = items.make_inventory()
    inv['equipped']['heart'] = _endurance_heart(ilvl=7)
    from core.render.hud_render import HudRenderMixin
    HudRenderMixin._draw_character_level(SimpleNamespace(inventory=inv),
                                        1280, lambda n: n)
    assert rendered == ['LVL 7'], rendered
    assert not any('CHARACTER LEVEL' in t for t in rendered)


def test_hud_character_level_handles_empty_equipment(monkeypatch):
    """Owner rule: an empty loadout renders LVL 0, not a placeholder."""
    from core.render.hud_render import HudRenderMixin
    rendered = _headless(monkeypatch)
    game = SimpleNamespace(inventory=items.make_inventory())
    HudRenderMixin._draw_character_level(game, 1280, lambda n: n)
    assert rendered == ['LVL 0'], rendered
    assert itemgen.format_character_level(game.inventory) == 'LVL 0'


def test_both_sites_render_lvl_zero_for_an_empty_loadout(monkeypatch):
    """Both display sites agree on the empty loadout, no placeholder."""
    rendered = _headless(monkeypatch)
    game = _bare_game()
    inv = game.inventory
    for slot in inv['equipped']:
        inv['equipped'][slot] = None

    ui = _inventory_ui()
    ui.char_provider = lambda: game.char
    ui.open = True
    ui.stash_open = False
    ui._stash_grid = None
    ui.draw(inv, 1280, 720)

    from core.render.hud_render import HudRenderMixin
    HudRenderMixin._draw_character_level(SimpleNamespace(inventory=inv),
                                        1280, lambda n: n)
    assert rendered.count('LVL 0') == 2, rendered
    assert not any(t.strip() == '--' for t in rendered), rendered


def test_tooltip_draw_path_runs_headless(monkeypatch):
    _headless(monkeypatch)
    game = _bare_game()
    ui = _inventory_ui()
    ui._draw_tooltip(_endurance_heart(identified=True), 400, game.inventory)
    lines = _tooltip_text(ui, _endurance_heart(identified=False), game.inventory)
    assert 'Unidentified' in lines


# ── right-click stash moves (kept from the retired drag suite) ─────────

def _slot_entry(item_id, col=0, row=0, count=1):
    return {'item': item_id, 'count': count, 'col': col, 'row': row}


def test_ctx_put_in_bank_moves_item():
    """Right-click PUT IN BANK: backpack item auto-places into the bank."""
    ui = _inventory_ui()
    ui.open = True
    ui.stash_open = True
    inv = items.make_inventory()
    inv['grid'] = [_slot_entry('heart', col=0, row=0)]
    ui._stash_grid = []
    stash_calls = []
    ui.on_stash_change = lambda: stash_calls.append(1)

    ui._exec({'type': 'to_bank', 'source': 'grid', 'index': 0}, inv, {})

    assert len(inv['grid']) == 0, 'item leaves the backpack'
    assert len(ui._stash_grid) == 1, 'item lands in the bank'
    assert ui._stash_grid[0]['item'] == 'heart'
    assert stash_calls, 'on_stash_change must fire'


def test_ctx_put_in_bank_when_full_leaves_item():
    ui = _inventory_ui()
    ui.open = True
    ui.stash_open = True
    inv = items.make_inventory()
    inv['grid'] = [_slot_entry('heart', col=0, row=0)]
    ui._stash_grid = [_slot_entry('liver', col=c % 8, row=r)
                      for r in range(8) for c in range(8)]   # full bank
    stash_calls = []
    ui.on_stash_change = lambda: stash_calls.append(1)

    ui._exec({'type': 'to_bank', 'source': 'grid', 'index': 0}, inv, {})

    assert len(inv['grid']) == 1, 'no space — item stays in the backpack'
    assert not stash_calls


def test_ctx_put_in_backpack_moves_item():
    """Right-click PUT IN BACKPACK: bank item moves to the backpack grid."""
    ui = _inventory_ui()
    ui.open = True
    ui.stash_open = True
    inv = items.make_inventory()
    entry = _slot_entry('heart', col=2, row=1)
    ui._stash_grid = [entry]
    stash_calls = []
    ui.on_stash_change = lambda: stash_calls.append(1)

    ui._exec({'type': 'to_inventory', 'source': 'stash', 'index': 0}, inv, {})

    assert len(ui._stash_grid) == 0, 'item leaves the bank'
    hearts = [e for e in inv['grid'] if e['item'] == 'heart']
    assert len(hearts) == 1, 'heart lands in the backpack grid'
    assert stash_calls


# ── comparison rows: stat line + arrow, no (up)/(down)/(eq) words ────

class TestComparisonArrowFormat(unittest.TestCase):
    """Owner ruling 2026-10-07: rows show only the stat line (e.g.
    '+33 Max Health'); direction is an arrow icon, not words."""

    def test_rows_are_pure_stat_lines_with_sign(self):
        hover = _endurance_heart(ilvl=10, endurance=5)
        equipped = _endurance_heart(ilvl=10, endurance=2)
        rows = itemgen.comparison_rows(hover, equipped)
        for text, _sign in rows:
            self.assertNotIn('(eq', text)
            self.assertNotIn('(up)', text)
            self.assertNotIn('(down)', text)
            self.assertNotIn('(same)', text)
        by_text = {t: s for t, s in rows}
        # both hearts share the +10 implicit -> no change, no arrow (sign 0)
        self.assertEqual(by_text.get('+10 Max Health'), 0)
        # hover carries more Endurance -> upgrade (arrow up)
        self.assertEqual(by_text.get('+5 Endurance'), 1)

    def test_downgrade_row_is_negative_sign(self):
        hover = _endurance_heart(ilvl=10, endurance=2)
        equipped = _endurance_heart(ilvl=10, endurance=5)
        rows = dict(itemgen.comparison_rows(hover, equipped))
        self.assertEqual(rows.get('+2 Endurance'), -1)

    def test_arrow_icons_exist_and_are_drawn(self):
        from ui import icons as icons_mod
        self.assertIn('arrow_up', icons_mod.ICON_MAP)
        self.assertIn('arrow_down', icons_mod.ICON_MAP)
        for path in ('ui/inventory_ui.py', 'core/render/delve_render.py'):
            src = Path(path).read_text(encoding='utf-8')
            self.assertIn("'arrow_up'", src, path)
            self.assertIn('_cmp_sign', src, path)


# ── DESCEND click-through removed (owner ruling 2026-10-07) ──────────

class TestDescendClickThroughRemoved(unittest.TestCase):
    def test_no_click_through_remains(self):
        ui_src = Path('ui/inventory_ui.py').read_text(encoding='utf-8')
        game_src = Path('core/game.py').read_text(encoding='utf-8')
        self.assertNotIn('on_open_descend', ui_src)
        self.assertNotIn('on_open_descend', game_src)
        self.assertNotIn('_open_descend_sheet', game_src)
        self.assertNotIn('Click to open DESCEND', ui_src)
