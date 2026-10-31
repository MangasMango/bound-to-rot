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

"""ROT ETERNAL - the depth-gated rot-set mythic (BLUEPRINT §27).

    * 2% chance on any ORGAN drop at depth 1-10 (never depth 11+, never
      gems/flasks/cards).
    * Set condition: unique equipped AND every organ slot identified+ROTTEN.
    * Effect: rot drawbacks are ignored + 10% of every damage type.
"""

import random
import unittest

import systems.itemgen as itemgen
from systems.items import ITEMS


def _organ_slot(item_id='heart', unique=None):
    """A minimal identified organ entry (controlled affixes)."""
    inst = {
        'rarity': 'common',
        'display_name': ITEMS[item_id]['name'],
        'ilvl': 5,
        'identified': True,
        'affixes': {'prefixes': {}, 'suffixes': {}},
    }
    if unique:
        inst['unique'] = dict(unique)
    return {'item': item_id, 'count': 1, 'instance_data': inst}


def _roster(unique_on='heart'):
    """Five identified, ROTTEN organs - the full set."""
    inv = {'equipped': {}, 'grid': []}
    for slot in ('lungs', 'heart', 'liver', 'intestine', 'kidney'):
        entry = _organ_slot(
            slot, unique=itemgen.ROT_MYTHIC_UNIQUE if slot == unique_on else None)
        itemgen.make_rotten(entry['instance_data'])
        inv['equipped'][slot] = entry
    return inv


class TestMythicDrop(unittest.TestCase):
    def test_fires_within_depth_range(self):
        rng = random.Random(11)
        fired = False
        for _ in range(600):
            slot = _organ_slot()
            if itemgen.try_rot_mythic(slot, 5, rng):
                inst = slot['instance_data']
                self.assertEqual(inst['rarity'], 'mythic')
                self.assertEqual(inst['unique']['id'], 'rot_eternal')
                self.assertIn(slot['item'], ITEMS)
                fired = True
                break
        self.assertTrue(fired, '2% should fire within 600 organ rolls')

    def test_never_fires_beyond_depth_10(self):
        rng = random.Random(13)
        for _ in range(400):
            slot = _organ_slot()
            self.assertFalse(itemgen.try_rot_mythic(slot, 11, rng))

    def test_non_organs_never_fire(self):
        rng = random.Random(17)
        gem = {'item': 'gem_blue', 'count': 1,
               'instance_data': {'rarity': 'common', 'display_name': 'Gem',
                                 'ilvl': 5, 'identified': True, 'ability': 'dash'}}
        card = {'item': 'poker_ace_pikes', 'count': 1}
        for _ in range(100):
            self.assertFalse(itemgen.try_rot_mythic(dict(gem), 1, rng))
            self.assertFalse(itemgen.try_rot_mythic(dict(card), 1, rng))

    def test_stays_out_of_the_normal_unique_pool(self):
        self.assertNotIn(itemgen.ROT_MYTHIC_UNIQUE, itemgen._UNIQUES)
        ids = {u['id'] for u in itemgen._UNIQUES}
        self.assertNotIn('rot_eternal', ids)


class TestRotSetCondition(unittest.TestCase):
    def test_active_with_full_rotten_roster(self):
        self.assertTrue(itemgen.rot_set_active(_roster()))

    def test_inactive_with_empty_slot(self):
        inv = _roster()
        inv['equipped']['kidney'] = None
        self.assertFalse(itemgen.rot_set_active(inv))

    def test_inactive_with_one_unrotten_organ(self):
        inv = _roster()
        fresh = _organ_slot('kidney')
        inv['equipped']['kidney'] = fresh
        self.assertFalse(itemgen.rot_set_active(inv))

    def test_inactive_with_one_unidentified_organ(self):
        inv = _roster()
        blind = _organ_slot('kidney')
        blind['instance_data']['identified'] = False
        inv['equipped']['kidney'] = blind
        self.assertFalse(itemgen.rot_set_active(inv))

    def test_cleansing_one_organ_drops_the_set(self):
        inv = _roster()
        itemgen.cleanse_rot(inv['equipped']['heart'])
        self.assertFalse(itemgen.rot_set_active(inv))


class TestRotSetEffect(unittest.TestCase):
    def test_aggregate_adds_ten_percent_all_damage(self):
        out = itemgen.aggregate_item_bonuses(_roster())
        for dmg in ('physical', 'magic', 'lightning', 'cold', 'fire', 'rot'):
            self.assertEqual(out.get(f'{dmg}_damage_pct', 0), 10)

    def test_aggregate_silent_without_unique(self):
        inv = _roster(unique_on=None)
        out = itemgen.aggregate_item_bonuses(inv)
        self.assertNotIn('magic_damage_pct', out)

    def test_live_totals_skip_drawbacks_when_set_active(self):
        entry = _organ_slot('lungs')
        itemgen.make_rotten(entry['instance_data'])
        inst = entry['instance_data']
        drawback = next(a for a in inst['affixes']['suffixes']
                        if a in itemgen._ROT_DRAWBACK_BY_ID)
        effect = itemgen.LIVE_EFFECT_MAP[drawback]
        with_dw = itemgen.live_effect_totals(inst).get(effect, 0.0)
        without = itemgen.live_effect_totals(inst, include_drawbacks=False)
        self.assertLess(with_dw, 0)                       # drawback subtracts
        self.assertEqual(without.get(effect, 0.0), 0.0)   # ...unless ignored

    def test_equipped_bonuses_wire_is_source_visible(self):
        src = open('core/game.py', encoding='utf-8').read()
        body = src.split('def _equipped_bonuses', 1)[1]
        self.assertIn('include_drawbacks=not nullify', body)
        self.assertIn('rot_set_active', body)


if __name__ == '__main__':
    unittest.main()
