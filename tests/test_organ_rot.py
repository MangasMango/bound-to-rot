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

"""Organ rot (durability replacement) — BLUEPRINT §22.

Covers:
  1. Every organ carried gains a flat rot chunk per successful wave.
  2. Only organs rot (gems, cards, flasks never do).
  3. At 100% the organ turns ROTTEN: stats buffed (+), one random drawback
     suffix added, display name prefixed "ROTTEN ".
  4. The Temperance currency card (arcana 14) FULLY reverts a rotten organ.
  5. The tooltip shows the rot meter and the ROTTEN marker.
"""

import unittest
from pathlib import Path

import systems.currency as currency
import systems.itemgen as itemgen
from systems.items import ITEMS, make_inventory
from ui.inventory_ui import InventoryUI
import ui.inventory_ui as inventory_ui_mod


# ── helpers ───────────────────────────────────────────────────────────

def _organ(item_id='heart', ilvl=10, rarity='rare', identified=True, seed=5):
    """A ready-to-use organ inventory entry."""
    entry = itemgen.roll_for(item_id, 1, ilvl, seed=seed)
    inst = entry['instance_data']
    inst['rarity'] = rarity
    inst['identified'] = identified
    return entry


def _rot_n_times(entry, n):
    for _ in range(n):
        itemgen.add_rot(entry)


def _fake_game():
    class FakeChar:
        level = 5
        available_points = 0

    class FakeGame:
        char = FakeChar()

    game = FakeGame()
    game.inventory = make_inventory()
    return game


def _apply_temperance(game, target):
    """Place target + one whole Temperance card (non-Fool cards are whole)
    and apply the card."""
    game.inventory['grid'].append(target)
    t_idx = game.inventory['grid'].index(target)
    game.inventory['grid'].append(currency.make_card_slot(14, 1, col=1, row=0))
    c_idx = len(game.inventory['grid']) - 1
    game._card_apply_target = ('grid', t_idx)
    return currency.apply_card(game, 14, 'grid', c_idx)


# ── 1/2: rot gain ─────────────────────────────────────────────────────

class TestWaveRotGain(unittest.TestCase):
    def test_carried_organs_gain_flat_rot_per_wave(self):
        inv = make_inventory()
        inv['grid'] = []                      # drop starter cards
        inv['equipped']['heart'] = _organ('heart')
        inv['grid'].append(_organ('lungs', seed=6))
        itemgen.apply_wave_rot(inv)
        self.assertEqual(itemgen.rot_of(inv['equipped']['heart']['instance_data']), 20.0)
        self.assertEqual(itemgen.rot_of(inv['grid'][0]['instance_data']), 20.0)
        itemgen.apply_wave_rot(inv)
        self.assertEqual(itemgen.rot_of(inv['equipped']['heart']['instance_data']), 40.0)

    def test_five_waves_punch_through_to_rotten(self):
        inv = make_inventory()
        inv['equipped']['heart'] = _organ('heart')
        for _ in range(5):
            itemgen.apply_wave_rot(inv)
        inst = inv['equipped']['heart']['instance_data']
        self.assertTrue(itemgen.is_rotten(inst))
        self.assertEqual(itemgen.rot_of(inst), itemgen.ROT_MAX)
        self.assertTrue(inst['display_name'].startswith('ROTTEN '))

    def test_rot_never_exceeds_max(self):
        entry = _organ('kidney', seed=8)
        for _ in range(30):
            itemgen.add_rot(entry)
        self.assertEqual(itemgen.rot_of(entry['instance_data']), itemgen.ROT_MAX)

    def test_non_organs_never_rot(self):
        inv = make_inventory()
        inv['grid'].append(itemgen.roll_for('gem_blue', 1, 5, seed=3))
        inv['grid'].append({'item': 'poker_ace_pikes', 'count': 4, 'col': 0, 'row': 1})
        inv['grid'].append({'item': 'flask_health', 'count': 1, 'charges': 1,
                            'col': 1, 'row': 0})
        itemgen.apply_wave_rot(inv)
        gem = next(e for e in inv['grid'] if e['item'] == 'gem_blue')
        self.assertNotIn('rot', gem['instance_data'])

    def test_unidentified_organs_never_rot(self):
        """Owner ruling 2026-10-07: unidentified = inert — no rot either."""
        entry = _organ('heart', identified=False, seed=61)
        inv = make_inventory()
        inv['grid'] = []
        inv['equipped']['heart'] = entry
        for _ in range(6):
            itemgen.apply_wave_rot(inv)
            itemgen.add_rot(entry)
        self.assertEqual(itemgen.rot_of(entry['instance_data']), 0.0)
        self.assertFalse(itemgen.is_rotten(entry['instance_data']))

    def test_apply_wave_rot_counts_only_equipped_rotten(self):
        inv = make_inventory()
        inv['grid'] = []                      # drop starter cards
        inv['equipped']['heart'] = _organ('heart')
        inv['grid'].append(_organ('lungs', seed=6))
        # four waves: nothing rotten yet
        for _ in range(4):
            self.assertEqual(itemgen.apply_wave_rot(inv), 0)
        # fifth wave rots BOTH — return counts the equipped one
        self.assertEqual(itemgen.apply_wave_rot(inv), 1)
        self.assertTrue(itemgen.is_rotten(inv['equipped']['heart']['instance_data']))
        self.assertTrue(itemgen.is_rotten(inv['grid'][0]['instance_data']))


# ── 3: ROTTEN transform ───────────────────────────────────────────────

class TestRottenState(unittest.TestCase):
    def test_rotten_buffs_every_rolled_stat(self):
        entry = _organ('liver', rarity='epic', seed=9)
        inst = entry['instance_data']
        before = {g: dict(inst['affixes'][g]) for g in ('prefixes', 'suffixes')}
        _rot_n_times(entry, 5)
        self.assertTrue(itemgen.is_rotten(inst))
        for group in ('prefixes', 'suffixes'):
            for aid, val in inst['affixes'][group].items():
                if aid in itemgen._ROT_DRAWBACK_BY_ID:
                    continue
                self.assertGreater(val, before[group][aid],
                                   f'{aid} was not buffed')

    def test_rotten_adds_exactly_one_negative_drawback(self):
        entry = _organ('intestine', rarity='epic', seed=11)
        inst = entry['instance_data']
        _rot_n_times(entry, 5)
        drawbacks = [a for a in inst['affixes']['suffixes']
                     if a in itemgen._ROT_DRAWBACK_BY_ID]
        self.assertEqual(len(drawbacks), 1)
        self.assertLess(inst['affixes']['suffixes'][drawbacks[0]], 0)

    def test_rotten_is_idempotent(self):
        entry = _organ('heart', seed=13)
        _rot_n_times(entry, 5)
        inst = entry['instance_data']
        snapshot = {g: dict(inst['affixes'][g]) for g in ('prefixes', 'suffixes')}
        self.assertFalse(itemgen.make_rotten(inst))
        self.assertFalse(itemgen.add_rot(entry))
        for group in ('prefixes', 'suffixes'):
            self.assertEqual(inst['affixes'][group], snapshot[group])

    def test_rot_prev_snapshots_original_values(self):
        entry = _organ('heart', rarity='rare', seed=15)
        inst = entry['instance_data']
        name_before = inst['display_name']
        before = {g: dict(inst['affixes'][g]) for g in ('prefixes', 'suffixes')}
        _rot_n_times(entry, 5)
        prev = inst['rot_prev']
        self.assertEqual(prev['display_name'], name_before)
        self.assertEqual(prev['affixes'], before)

    def test_drawback_shows_as_negative_line(self):
        entry = _organ('lungs', rarity='epic', seed=17)
        _rot_n_times(entry, 5)
        lines = itemgen.affix_lines(entry['instance_data'])
        negatives = [l for l in lines if l.startswith('-')]
        self.assertEqual(len(negatives), 1)

    def test_drawback_reduces_stat_totals(self):
        """The drawback is a real effect, not just text."""
        entry = _organ('lungs', rarity='epic', seed=19)
        inst = entry['instance_data']
        _rot_n_times(entry, 5)
        drawback_id = next(a for a in inst['affixes']['suffixes']
                           if a in itemgen._ROT_DRAWBACK_BY_ID)
        effect = itemgen.LIVE_EFFECT_MAP[drawback_id]
        with_drawback = itemgen.live_effect_totals(inst).get(effect, 0.0)
        # same instance with the drawback stripped: strictly higher (or equal
        # only if the drawback were 0, which it never is)
        stripped = {g: {k: v for k, v in inst['affixes'][g].items()
                        if k != drawback_id}
                    for g in ('prefixes', 'suffixes')}
        without = itemgen.live_effect_totals({'affixes': stripped}).get(effect, 0.0)
        self.assertLess(with_drawback, without)


# ── 4: Queen of Hearts cleanse ────────────────────────────────────────

class TestTemperanceCleanse(unittest.TestCase):
    def test_card_is_registered(self):
        self.assertIn(14, currency.CURRENCY_CARDS)
        self.assertIn('poker_queen_hearts', ITEMS)
        self.assertEqual(ITEMS['poker_queen_hearts']['img'], 'cards/dark/Q-H.png')

    def test_temperance_full_reverts_rotten_organ(self):
        target = _organ('heart', rarity='rare', seed=21)
        inst = target['instance_data']
        name_before = inst['display_name']
        affixes_before = {g: dict(inst['affixes'][g])
                          for g in ('prefixes', 'suffixes')}
        _rot_n_times(target, 5)
        self.assertTrue(itemgen.is_rotten(inst))

        game = _fake_game()
        result = _apply_temperance(game, target)
        self.assertIsNotNone(result)
        self.assertFalse(itemgen.is_rotten(inst))
        self.assertEqual(itemgen.rot_of(inst), 0.0)
        self.assertNotIn('rot_prev', inst)
        self.assertEqual(inst['display_name'], name_before)
        self.assertEqual(inst['affixes'], affixes_before)

    def test_temperance_consumes_the_card_on_success(self):
        target = _organ('heart', seed=23)
        _rot_n_times(target, 5)
        game = _fake_game()
        game.inventory['grid'].append(target)
        game.inventory['grid'].append(currency.make_card_slot(14, 1, col=1, row=0))
        c_idx = len(game.inventory['grid']) - 1
        game._card_apply_target = ('grid', game.inventory['grid'].index(target))
        currency.apply_card(game, 14, 'grid', c_idx)
        # the single whole card was consumed; the stack is gone
        self.assertNotIn(currency.card_item_id(14),
                         [e['item'] for e in game.inventory['grid']])

    def test_temperance_clears_partial_rot(self):
        target = _organ('liver', seed=25)
        itemgen.add_rot(target)          # 20% — not rotten yet
        game = _fake_game()
        result = _apply_temperance(game, target)
        self.assertIsNotNone(result)
        self.assertEqual(itemgen.rot_of(target['instance_data']), 0.0)

    def test_temperance_refuses_a_clean_organ(self):
        target = _organ('kidney', seed=27)     # 0% rot
        game = _fake_game()
        result = _apply_temperance(game, target)
        self.assertIsNone(result)
        # nothing consumed — the whole card is still there
        cards = [e for e in game.inventory['grid'] if e['item'] == 'poker_queen_hearts']
        self.assertEqual(cards[0]['count'], 1)

    def test_temperance_refuses_non_organs(self):
        gem = itemgen.roll_for('gem_blue', 1, 5, seed=29)
        self.assertFalse(currency.valid_target(14, gem))

    def test_reroll_preserves_rotten_state(self):
        target = _organ('heart', rarity='rare', seed=31)
        _rot_n_times(target, 5)
        game = _fake_game()
        game.inventory['grid'].append(target)
        t_idx = game.inventory['grid'].index(target)
        game.inventory['grid'].append(currency.make_card_slot(13, 4, col=1, row=0))
        c_idx = len(game.inventory['grid']) - 1
        game._card_apply_target = ('grid', t_idx)
        result = currency.apply_card(game, 13, 'grid', c_idx)
        self.assertIsNotNone(result)
        inst = target['instance_data']
        self.assertTrue(itemgen.is_rotten(inst))
        self.assertTrue(inst['display_name'].startswith('ROTTEN '))
        drawbacks = [a for a in inst['affixes']['suffixes']
                     if a in itemgen._ROT_DRAWBACK_BY_ID]
        self.assertEqual(len(drawbacks), 1)

    def test_justice_keeps_rotten_bonus(self):
        target = _organ('lungs', rarity='epic', seed=33)
        _rot_n_times(target, 5)
        game = _fake_game()
        game.inventory['grid'].append(target)
        t_idx = game.inventory['grid'].index(target)
        game.inventory['grid'].append(currency.make_card_slot(11, 4, col=1, row=0))
        c_idx = len(game.inventory['grid']) - 1
        game._card_apply_target = ('grid', t_idx)
        result = currency.apply_card(game, 11, 'grid', c_idx)
        self.assertIsNotNone(result)
        inst = target['instance_data']
        self.assertTrue(itemgen.is_rotten(inst))
        ilvl, rarity = inst['ilvl'], inst['rarity']
        for aid, val in inst['affixes']['prefixes'].items():
            a = itemgen._AFFIX_BY_ID[aid]
            fair = a['base'] * (1 + ilvl / 100.0) * itemgen.M_RARITY[rarity]
            scaled = fair * itemgen.ROTTEN_STAT_MULT
            if a['round'] == 'int':
                expected = int(scaled + 0.5)
            else:
                factor = 10 ** a['round']
                expected = int(scaled * factor + 0.5 + 1e-9) / factor
            self.assertAlmostEqual(val, expected)


# ── 5: tooltip ────────────────────────────────────────────────────────

class TestRotTooltip(unittest.TestCase):
    def _texts(self, entry):
        ui = InventoryUI()
        return [t for t, _ in ui._tooltip_lines(entry, None)]

    def test_fresh_organ_shows_zero_meter(self):
        lines = self._texts(_organ('heart', seed=41))
        self.assertTrue(any(l.startswith('Rot: 0%') for l in lines))

    def test_meter_tracks_percent(self):
        entry = _organ('heart', seed=43)
        _rot_n_times(entry, 2)
        self.assertTrue(any(l.startswith('Rot: 40%') for l in self._texts(entry)))

    def test_rotten_marker_on_identified_organ(self):
        entry = _organ('heart', seed=45)
        _rot_n_times(entry, 5)
        lines = self._texts(entry)
        self.assertTrue(any(l.startswith('ROTTEN ') for l in lines))
        self.assertIn('Rot: 100% (ROTTEN)', lines)

    def test_rotten_marker_on_unidentified_organ(self):
        entry = _organ('heart', identified=False, seed=47)
        inst = entry['instance_data']
        # Gameplay can't produce rotten+unidentified any more (unidentified
        # organs don't rot, owner ruling 2026-10-07) — but saves from the
        # interim build could, so the tooltip must still render it.
        inst['rot'] = 100.0
        inst['rotten'] = True
        lines = self._texts(entry)
        # unidentified exposes no stats — but the ROTTEN condition shows
        self.assertTrue(any(l.startswith('ROTTEN ') for l in lines))
        self.assertFalse(any('Item Level' in l for l in lines))

    def test_non_organs_have_no_meter(self):
        gem = itemgen.roll_for('gem_blue', 1, 5, seed=49)
        self.assertFalse(any(l.startswith('Rot:') for l in self._texts(gem)))

    # ── rotten-yellow colouring (owner ruling 2026-10-07) ─────────────

    def _lines(self, entry):
        return InventoryUI()._tooltip_lines(entry, None)

    def test_rotten_affix_lines_turn_yellow(self):
        entry = _organ('liver', rarity='epic', seed=51)
        inst = entry['instance_data']
        rotten = inventory_ui_mod.C_ROTTEN
        # fresh: rolled affixes keep the classic blue
        fresh_texts = set(itemgen.affix_lines(inst))
        fresh_affix_colors = [c for t, c in self._lines(entry) if t in fresh_texts]
        self.assertTrue(fresh_affix_colors)
        for c in fresh_affix_colors:
            self.assertEqual((c.r, c.g, c.b), (120, 160, 255))
        # rotten: every rolled line (buffed stats + drawback) turns yellow
        _rot_n_times(entry, 5)
        rotten_texts = set(itemgen.affix_lines(inst))
        self.assertTrue(rotten_texts - fresh_texts)   # drawback line added
        rotten_affix_colors = [c for t, c in self._lines(entry) if t in rotten_texts]
        self.assertTrue(rotten_affix_colors)
        for c in rotten_affix_colors:
            self.assertEqual((c.r, c.g, c.b), (rotten.r, rotten.g, rotten.b))

    def test_meter_ramps_green_to_rotten_yellow(self):
        t0 = inventory_ui_mod._rot_col(0)
        t100 = inventory_ui_mod._rot_col(100)
        self.assertEqual((t0.r, t0.g, t0.b), (90, 210, 60))
        rotten = inventory_ui_mod.C_ROTTEN
        self.assertEqual((t100.r, t100.g, t100.b), (rotten.r, rotten.g, rotten.b))

    def test_title_split_draw_is_wired(self):
        src = Path('ui/inventory_ui.py').read_text(encoding='utf-8')
        body = src.split('def _draw_tooltip', 1)[1]
        self.assertIn('ROTTEN_NAME_PREFIX', body)
        self.assertIn('C_ROTTEN', body)


if __name__ == '__main__':
    unittest.main()
