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

"""Stash search / filters and backpack sort (issue #12).

Covers:
  1. Item-type classification from the ITEMS table (incl. `isCard: 0` Joker).
  2. Search text: unidentified gear exposes NO rolled display name
     (owner rule - affix words are stat text), identified gear matches both.
  3. Rarity / item-type filter matching.
  4. sort_grid_entries: ordering per key, keys preserved, grid placement
     stays legal, stack counts survive, guard rails.
  5. InventoryUI filter state: visibility gate + reset on bank close.
"""

import systems.items as items
from systems.itemgen import generate_instance
from ui.inventory_ui import InventoryUI


# ── helpers ────────────────────────────────────────────────────────────

def _entry(item_id, col=0, row=0, ilvl=10, identified=True, count=1):
    entry = {'item': item_id, 'count': count, 'col': col, 'row': row}
    if items.ITEMS.get(item_id, {}).get('equipSlot'):
        entry['instance_data'] = generate_instance(
            item_id, ilvl, seed=f'{item_id}-{ilvl}')
        entry['instance_data']['identified'] = identified
    return entry


# ── item-type classification ───────────────────────────────────────────

def test_item_type_classification():
    assert items.entry_item_type('heart') == 'organ'
    assert items.entry_item_type('gem_blue') == 'gem'
    assert items.entry_item_type('poker_ace_hearts') == 'card'
    # The Joker carries `isCard: 0` - presence, not truthiness, is the test
    assert items.entry_item_type('poker_joker') == 'card'
    assert items.entry_item_type('flask_health') == 'flask'
    assert items.entry_item_type('health_potion') == 'potion'


# ── search text ────────────────────────────────────────────────────────

def test_search_text_identified_includes_rolled_name():
    entry = _entry('heart', identified=True)
    text = items.entry_search_text(entry)
    assert 'heart' in text
    assert text.split() != ['heart']   # rolled affix words joined the text


def test_search_text_unidentified_hides_rolled_name():
    entry = _entry('heart', identified=False)
    text = items.entry_search_text(entry)
    assert 'heart' in text
    # no affix words may leak through search (unidentified = no stat text)
    rolled = entry['instance_data']['display_name'].lower()
    rolled_words = [w for w in rolled.split() if w != 'heart']
    assert not any(w in text for w in rolled_words)


def test_search_matches_base_name_case_insensitive():
    entry = _entry('heart')
    assert items.entry_matches_search(entry, 'HEA')
    assert not items.entry_matches_search(entry, 'kidney')


# ── filters ────────────────────────────────────────────────────────────

def test_rarity_filter():
    entry = _entry('heart')   # rolls may upgrade; pin the actual rarity
    entry['instance_data']['rarity'] = 'rare'
    assert items.entry_matches_filters(entry, rarity='rare')
    assert not items.entry_matches_filters(entry, rarity='mythic')
    assert items.entry_matches_filters(entry, rarity='all')


def test_type_filter():
    assert items.entry_matches_filters(_entry('gem_blue'), item_type='gem')
    assert not items.entry_matches_filters(_entry('gem_blue'), item_type='organ')
    assert items.entry_matches_filters(_entry('gem_blue'), item_type='all')


# ── sort ───────────────────────────────────────────────────────────────

def _grid_with(entries):
    grid = []
    for entry in entries:
        grid.append(dict(entry))
    return grid


def test_sort_by_name_preserves_everything():
    grid = _grid_with([
        _entry('kidney', col=2, row=0, ilvl=30),
        _entry('lungs', col=0, row=1, ilvl=5),
        _entry('health_potion', col=1, row=0, count=7),
    ])
    snapshot = [dict(entry) for entry in grid]
    assert items.sort_grid_entries(grid, 'name')
    names = [items.ITEMS[entry['item']]['name'] for entry in grid]
    assert names == sorted(names)
    # nothing lost, counts intact, placement legal
    assert sorted(e['item'] for e in grid) == sorted(e['item'] for e in snapshot)
    assert [e['count'] for e in grid if e['item'] == 'health_potion'] == [7]
    cell_map = items.grid_build_map(grid)
    for entry in grid:
        assert cell_map[entry['row']][entry['col']] is not None


def test_sort_by_rarity_then_ilvl_ordering():
    def _inst_entry(item_id, rarity, ilvl):
        entry = _entry(item_id, ilvl=ilvl)
        if 'instance_data' in entry:
            entry['instance_data']['rarity'] = rarity
            entry['instance_data']['identified'] = True
        return entry

    grid = _grid_with([
        _inst_entry('heart', 'common', 10),
        _inst_entry('lungs', 'mythic', 60),
        _inst_entry('kidney', 'rare', 40),
    ])
    assert items.sort_grid_entries(grid, 'rarity')
    rarities = [items.entry_rarity(e) for e in grid]
    assert rarities == sorted(rarities, key=lambda r: items.RARITY_RANK[r])

    grid2 = _grid_with([
        _inst_entry('heart', 'rare', 10),
        _inst_entry('lungs', 'rare', 50),
        _inst_entry('kidney', 'rare', 30),
    ])
    assert items.sort_grid_entries(grid2, 'ilvl')
    ilvls = [e['instance_data']['ilvl'] for e in grid2]
    assert ilvls == sorted(ilvls, reverse=True)   # highest first


def test_sort_guard_rails():
    assert not items.sort_grid_entries([], 'depth')     # unknown key
    assert not items.sort_grid_entries('nope', 'name')  # not a list
    empty = []
    assert items.sort_grid_entries(empty, 'name')       # empty grid is a no-op
    assert empty == []


# ── InventoryUI filter state ───────────────────────────────────────────

def test_ui_entry_visible_gates_search_and_filters():
    ui = InventoryUI()
    ui.search_text = 'heart'
    assert ui._entry_visible(_entry('heart'))
    assert not ui._entry_visible(_entry('kidney'))
    ui.search_text = ''
    ui.stash_type = 'gem'
    assert not ui._entry_visible(_entry('heart'))
    ui.stash_type = 'all'
    ui.stash_rarity = 'mythic'
    entry = _entry('heart')
    entry['instance_data']['rarity'] = 'rare'
    assert not ui._entry_visible(entry)


def test_ui_reset_on_bank_close():
    ui = InventoryUI()
    ui.stash_open = True
    ui.search_focused = True
    ui.search_text = 'gem'
    ui.stash_search.buf = 'gem'
    ui.stash_rarity = 'rare'
    ui.stash_type = 'flask'
    ui.close_stash()
    assert not ui.search_focused
    assert ui.search_text == ''
    assert ui.stash_search.buf == ''
    assert ui.stash_rarity == 'all'
    assert ui.stash_type == 'all'
