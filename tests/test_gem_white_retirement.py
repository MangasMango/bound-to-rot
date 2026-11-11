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

"""White gem retirement + R slot removal (issue #45, schema v5 -> v6).

Covers:
  1. `systems.gems` - GEM_SLOTS is Q/W/E, white is not a slot, pools have
     no R entry, `gem_item_id` never answers 'gem_white'.
  2. Items/drops - `gem_white` is gone from ITEMS and the drop tables.
  3. Migration `_migrate_5_to_6` - socketed white gems convert to a
     random Q/W/E gem at the same rarity, the R key vanishes from
     gem_sockets, grid/stash whites convert, the note is attached, and
     the step is idempotent + version-bumping.
  4. Anima snapshot restore converts ground-item whites.
"""

import pytest

import entities.progression as prog
from systems import gems
from systems.itemgen import ITEMS


def test_gem_slots_are_qwe():
    assert gems.GEM_SLOTS == ('Q', 'W', 'E')
    assert 'R' not in gems.GEM_COLOR_FOR_SLOT
    assert 'R' not in gems.SLOT_GEM_POOLS


def test_white_gem_removed_from_items():
    assert 'gem_white' not in ITEMS
    # and never served by the slot fallback
    assert gems.gem_item_id('Q') == 'gem_blue'
    assert gems.gem_item_id('nonsense') == 'gem_blue'


def test_drop_table_no_longer_lists_the_white_gem():
    import core.game as core_game
    ids = [row[0] for row in core_game.SKELETON_DROP_TABLE]
    assert 'gem_white' not in ids
    # the freed weight was redistributed, not dropped
    gem_weight = sum(row[3] for row in core_game.SKELETON_DROP_TABLE
                     if row[0].startswith('gem_'))
    assert gem_weight == pytest.approx(0.034)


def test_socketing_r_is_no_longer_possible():
    import systems.items as items
    inv = items.make_inventory()
    assert 'R' not in inv['gem_sockets']
    assert set(inv['gem_sockets']) == {'Q', 'W', 'E'}


def _v5_payload(**extra):
    payload = {
        'save_schema_version': 5,
        'characters': [{
            'inventory': {
                'grid': [{'item': 'gem_white', 'count': 1,
                          'instance_data': {'rarity': 'rare', 'ilvl': 9}}],
                'gem_sockets': {
                    'Q': None,
                    'R': {'item': 'gem_white', 'count': 1,
                          'instance_data': {'rarity': 'epic', 'ilvl': 20}},
                },
            },
            'stash': [{'item': 'gem_white', 'count': 1,
                       'instance_data': {'rarity': 'uncommon', 'ilvl': 3}}],
        }],
    }
    payload.update(extra)
    return payload


def test_migration_converts_socketed_and_loose_whites():
    migrated = prog.migrate_save(_v5_payload())
    assert migrated['save_schema_version'] == 6
    inv = migrated['characters'][0]['inventory']
    # R socket gone entirely
    assert 'R' not in inv['gem_sockets']
    assert set(inv['gem_sockets']) == {'Q', 'W', 'E'}
    # every converted gem: valid new slot item, same rarity, ability set
    converted = [inv['gem_sockets']['Q'], *inv['grid'], *migrated['characters'][0]['stash']]
    for slot in converted:
        item_id = slot['item']
        assert item_id in ('gem_blue', 'gem_green', 'gem_red')
        inst = slot.get('instance_data') or {}
        assert inst.get('ability')
    # value preserved: rarities carried over
    assert inv['gem_sockets']['Q']['instance_data']['rarity'] == 'epic'
    assert inv['grid'][0]['instance_data']['rarity'] == 'rare'
    assert migrated['characters'][0]['stash'][0]['instance_data']['rarity'] \
        == 'uncommon'
    # a dismissable note was attached
    assert 'White Gem' in migrated['migration_note']


def test_migration_is_idempotent():
    once = prog.migrate_save(_v5_payload())
    twice = prog.migrate_save(dict(once))
    assert twice['save_schema_version'] == 6
    sockets = twice['characters'][0]['inventory']['gem_sockets']
    assert set(sockets) == {'Q', 'W', 'E'}      # nothing re-converted


def test_anima_restore_converts_ground_whites():
    data = {'anima': {'state': 'ready'}, 'ground_items': [
        {'item': 'gem_white', 'count': 1,
         'instance_data': {'rarity': 'rare', 'ilvl': 9}},
    ]}
    out = prog._anima_restore(data)
    gi = out['ground_items'][0]
    assert gi['item'] in ('gem_blue', 'gem_green', 'gem_red')
    assert gi['instance_data']['ability']
    assert gi['instance_data']['rarity'] == 'rare'
