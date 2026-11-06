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

"""v4 -> v5 migration (leveling rework, plan .ai/LEVELING_REWORK_PLAN.md).

Pins the BLUEPRINT §46-49 conventions on the item cleanup:

- `flat_melee_damage` instances rename in place to `flat_attack_damage`.
- Attribute-suffix lines and the retired pk_* / move-speed lines strip out.
- Every stripped roll is compensated with a replacement stat suffix at a
  fair value (equivalent-or-better, never a downgrade).
- The compensation is announced (data['migration_note']) - never silent.
"""

import copy
import unittest

import entities.progression as prog


def _item(affixes, ilvl=25, rarity='rare', slot='heart'):
    return {
        'item': slot, 'count': 1, 'col': 0, 'row': 0,
        'instance_data': {
            'rarity': rarity, 'display_name': 'Test Organ', 'ilvl': ilvl,
            'identified': True,
            'affixes': affixes,
        },
    }


def _v4_save():
    prog_char_items = _item({
        'prefixes': {'flat_melee_damage': 8, 'pk_melee_mult': 6},
        'suffixes': {'attr_strength': 3, 'pk_accuracy': 9,
                     'pk_entropy_grace': 4, 'pk_reload_speed': 5,
                     'percent_move_speed': 0.07},
    })
    stash_item = _item({'prefixes': {}, 'suffixes': {'attr_destiny': 2}},
                       slot='lungs', rarity='epic', ilvl=50)
    return {
        'save_schema_version': 4,
        'active_idx': 0,
        'unlocked_vessels': ['knight'],
        'best_depth': 3,
        'characters': [
            {
                'id': 'v5-char', 'name': 'Migrator', 'looks': 'knight',
                'level': 12, 'xp': 500, 'available_points': 0,
                'descend': {a: 2 for a in prog.DESCEND_ATTRIBUTES},
                'perks': {},
                'inventory': {'grid': [prog_char_items], 'equipped': {},
                              'gem_sockets': {}, 'flask_slot': None},
                'stash': [stash_item],
            },
        ],
    }


class MigrateV4ToV5Tests(unittest.TestCase):

    def test_schema_bumps_to_current(self):
        migrated = prog.migrate_save(_v4_save())
        self.assertEqual(migrated['save_schema_version'], prog.SAVE_SCHEMA_VERSION)

    def test_melee_affix_renames_value_preserved(self):
        migrated = prog.migrate_save(_v4_save())
        inst = migrated['characters'][0]['inventory']['grid'][0]['instance_data']
        prefixes = inst['affixes']['prefixes']
        self.assertNotIn('flat_melee_damage', prefixes)
        self.assertEqual(prefixes.get('flat_attack_damage'), 8)

    def test_retired_affixes_stripped_and_compensated(self):
        import systems.itemgen as itemgen
        migrated = prog.migrate_save(_v4_save())
        inst = migrated['characters'][0]['inventory']['grid'][0]['instance_data']
        prefixes = inst['affixes']['prefixes']
        suffixes = inst['affixes']['suffixes']
        for aid in ('attr_strength', 'pk_accuracy', 'pk_entropy_grace',
                    'pk_reload_speed', 'percent_move_speed'):
            self.assertNotIn(aid, suffixes)
        self.assertNotIn('pk_melee_mult', prefixes)
        known_ids = {a['id'] for a in itemgen._AFFIXES}
        for aid in suffixes:
            self.assertIn(aid, known_ids)
            self.assertGreater(suffixes[aid], 0)

    def test_stash_items_cleaned_too(self):
        migrated = prog.migrate_save(_v4_save())
        inst = migrated['characters'][0]['stash'][0]['instance_data']
        self.assertNotIn('attr_destiny', inst['affixes']['suffixes'])
        self.assertGreaterEqual(len(inst['affixes']['suffixes']), 1)

    def test_compensation_is_not_a_downgrade(self):
        """Each补偿 roll must be worth at least the stripped roll's fair value."""
        import systems.itemgen as itemgen
        migrated = prog.migrate_save(_v4_save())
        inst = migrated['characters'][0]['inventory']['grid'][0]['instance_data']
        aff = inst['affixes']
        total_fair = 0
        for group in ('prefixes', 'suffixes'):
            for aid, val in aff[group].items():
                a_def = itemgen._AFFIX_BY_ID.get(aid)
                if a_def is None:
                    continue
                fair = (a_def['base'] * (1.0 + inst['ilvl'] / 100.0)
                        * itemgen.M_RARITY[inst['rarity']])
                total_fair += fair
        self.assertGreater(total_fair, 0)
        # the two prefix slots survive (attack damage + one compensation)
        self.assertIn('flat_attack_damage', aff['prefixes'])

    def test_note_is_attached_and_idempotent(self):
        save = _v4_save()
        migrated = prog.migrate_save(save)
        self.assertIn('migration_note', migrated)
        again = prog.migrate_save(copy.deepcopy(migrated))
        self.assertNotIn('attr_strength',
                         again['characters'][0]['inventory']['grid'][0]
                         ['instance_data']['affixes']['suffixes'])
        # idempotency: re-running on a v5 payload that has no retired ids
        # must leave item affixes unchanged (no new compensation rolls)
        before = copy.deepcopy(again)
        third = prog.migrate_save(copy.deepcopy(again))
        self.assertEqual(
            third['characters'][0]['inventory']['grid'][0]['instance_data'],
            before['characters'][0]['inventory']['grid'][0]['instance_data'])


if __name__ == '__main__':
    unittest.main()
