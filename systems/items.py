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

# Bank (stash) grid: single 8x8 spatial grid — matches the painted cells of
# the BankStash panel art (assets/ui/BankStash.png).
GRID_COLS = 8
GRID_ROWS = 8

# Player-inventory grid (itsmars_Inventory panel art: 8 cols × 4 rows painted
# cells) — smaller than the bank grid.
INV_COLS = 8
INV_ROWS = 4
INV_GRID_VERSION = 2

ITEMS = {
    # OWNER RULE: every item occupies EXACTLY ONE grid cell — (1, 1). The
    # organs (lungs, liver) used to be 2×2 / 2×3; they are normalised here so
    # placement, highlight, hit-testing and drawing never have to reason about
    # a multi-cell footprint. The size key stays in the table (every consumer
    # reads it) but is always (1, 1) — see ``item_size``.
    # ── tarot currency cards (issue #73 phase B) — count is card quarters;
    #    4/4 completes a usable card. Faces reuse the Major Arcana decks. ──
    'tarot_card_00': {'name': 'The Fool',          'img': 'cards/arcanum/00.png', 'rarity': 'common',   'stackable': True, 'maxStack': 9999, 'size': (1, 1), 'isCard': 0},
    'tarot_card_01': {'name': 'The Magician',      'img': 'cards/arcanum/01.png', 'rarity': 'common',   'stackable': True, 'maxStack': 9999, 'size': (1, 1), 'isCard': 1},
    'tarot_card_04': {'name': 'The Emperor',       'img': 'cards/arcanum/04.png', 'rarity': 'rare',     'stackable': True, 'maxStack': 9999, 'size': (1, 1), 'isCard': 4},
    'tarot_card_10': {'name': 'Wheel of Fortune',  'img': 'cards/arcanum/10.png', 'rarity': 'uncommon', 'stackable': True, 'maxStack': 9999, 'size': (1, 1), 'isCard': 10},
    'tarot_card_11': {'name': 'Justice',           'img': 'cards/arcanum/11.png', 'rarity': 'rare',     'stackable': True, 'maxStack': 9999, 'size': (1, 1), 'isCard': 11},
    'tarot_card_13': {'name': 'Death',             'img': 'cards/arcanum/13.png', 'rarity': 'epic',     'stackable': True, 'maxStack': 9999, 'size': (1, 1), 'isCard': 13},
    'tarot_card_14': {'name': 'Temperance',        'img': 'cards/arcanum/14.png', 'rarity': 'rare',     'stackable': True, 'maxStack': 9999, 'size': (1, 1), 'isCard': 14},
    'tarot_card_15': {'name': 'The Devil',         'img': 'cards/arcanum/15.png', 'rarity': 'epic',     'stackable': True, 'maxStack': 9999, 'size': (1, 1), 'isCard': 15},
    'tarot_card_17': {'name': 'The Star',          'img': 'cards/arcanum/17.png', 'rarity': 'rare',     'stackable': True, 'maxStack': 9999, 'size': (1, 1), 'isCard': 17},
    # ── potions (Diablo 2-style belt, keys 1-6) ────────────────────────
    'health_potion': {'name': 'Health Potion', 'img': 'items/health_potion.png', 'rarity': 'common', 'stackable': True, 'maxStack': 10, 'size': (1, 1), 'isPotion': 'health', 'heal': 40},
    'mana_potion':   {'name': 'Mana Potion',   'img': 'items/mana_potion.png',   'rarity': 'common', 'stackable': True, 'maxStack': 10, 'size': (1, 1), 'isPotion': 'mana',   'heal': 40},
    # ── gems (issue #73 DESIGN PIVOT: gems grant QWER abilities) ───────
    'gem_blue':  {'name': 'Blue Gem',  'img': 'items/gem_blue.png',  'rarity': 'uncommon', 'stackable': False, 'maxStack': 1, 'size': (1, 1), 'isGem': 'Q'},
    'gem_green': {'name': 'Green Gem', 'img': 'items/gem_green.png', 'rarity': 'uncommon', 'stackable': False, 'maxStack': 1, 'size': (1, 1), 'isGem': 'W'},
    'gem_red':   {'name': 'Red Gem',   'img': 'items/gem_red.png',   'rarity': 'uncommon', 'stackable': False, 'maxStack': 1, 'size': (1, 1), 'isGem': 'E'},
    'gem_white': {'name': 'White Gem', 'img': 'items/gem_white.png', 'rarity': 'uncommon', 'stackable': False, 'maxStack': 1, 'size': (1, 1), 'isGem': 'R'},
    # ── flasks (issue #73 ADDITION: T-slot flask, one use per wave) ───
    'flask_health':  {'name': 'Health Flask',  'img': 'items/health.png', 'rarity': 'common', 'stackable': False, 'maxStack': 1, 'size': (1, 1), 'isFlask': 'health',  'charges': 1},
    'flask_mana':    {'name': 'Mana Flask',    'img': 'items/mana.png',   'rarity': 'common', 'stackable': False, 'maxStack': 1, 'size': (1, 1), 'isFlask': 'mana',    'charges': 1},
    'flask_utility': {'name': 'Haste Flask',   'img': 'items/mana.png',   'rarity': 'uncommon', 'stackable': False, 'maxStack': 1, 'size': (1, 1), 'isFlask': 'utility', 'charges': 1},
    # ── organs ────────────────────────────────────────────────────────
    'lungs':     {'name': 'Lungs',            'img': 'items/organ_lungs.png',  'rarity': 'uncommon', 'stackable': False, 'maxStack': 1, 'size': (1, 1), 'equipSlot': 'lungs',     'equip': {'move_speed': 0.04}},
    'heart':     {'name': 'Heart',            'img': 'items/organ_heart.png',  'rarity': 'uncommon', 'stackable': False, 'maxStack': 1, 'size': (1, 1), 'equipSlot': 'heart',     'equip': {'max_health': 10}},
    'liver':     {'name': 'Liver',            'img': 'items/organ_liver.png',  'rarity': 'uncommon', 'stackable': False, 'maxStack': 1, 'size': (1, 1), 'equipSlot': 'liver',     'equip': {'damage_reduction': 0.15}},
    'intestine': {'name': 'Intestine',           'img': 'items/organ_intestines.png', 'rarity': 'rare', 'stackable': False, 'maxStack': 1, 'size': (1, 1), 'equipSlot': 'intestine', 'equip': {'max_health': 8}},
    'kidney':    {'name': 'Kidney',           'img': 'items/organ_kidney.png', 'rarity': 'rare',    'stackable': False, 'maxStack': 1, 'size': (1, 1), 'equipSlot': 'kidney',    'equip': {'evasion': 8}},
}

def item_size(item_id):
    """Grid footprint of an item — always (1, 1) for every item in ITEMS.

    One accessor so placement, drawing, highlight and hit-testing all agree
    that no item spans more than a single cell.
    """
    return ITEMS.get(item_id, {}).get('size', (1, 1))


EQUIP_SLOT_LABELS = {
    'lungs':     'LUNGS',
    'heart':     'HEART',
    'liver':     'LIVER',
    'intestine': 'INTESTINE',
    'kidney':    'KIDNEY',
}

# Stats stored as 0..1 ratios (displayed as percentages)
_EQUIP_PCT_KEYS = {'damage_reduction', 'move_speed'}

# Human labels for implicit equip stats
_EQUIP_LABELS = {
    'damage_reduction': 'Damage Reduction',
    'move_speed':       'Move Speed',
    'max_health':       'Max Health',
    'evasion':          'Evasion',
    'melee_damage':     'Melee Damage',
}


def format_equip_stat(key: str, value) -> str:
    """Format one implicit `equip` stat for display (pct vs flat)."""
    label = _EQUIP_LABELS.get(key, key.replace('_', ' '))
    if key in _EQUIP_PCT_KEYS or key.endswith('_pct'):
        return f"+{int(value * 100)}% {label}"
    return f"+{value:g} {label}"


def is_identified_slot(entry):
    """True when an inventory slot's rolled stats may be equipped.

    Thin wrapper over ``systems.itemgen.is_identified`` so this module stays
    importable on its own (itemgen imports ITEMS from here). Items with no
    instance data (consumables, currency, tarot cards) are always identified.
    """
    from systems.itemgen import is_identified
    return is_identified(entry)


def can_equip(entry):
    """Whether a grid entry may be equipped right now.

    Owner rule: an item must be IDENTIFIED before it can be equipped
    (identify with a full 4/4 stack of The Fool from the right-click menu).
    This reverses the issue #84 behaviour that allowed equipping blind.
    """
    if not isinstance(entry, dict):
        return False
    if not ITEMS.get(entry.get('item', ''), {}).get('equipSlot'):
        return False
    return is_identified_slot(entry)


def equip_from_grid(inventory, index):
    """Equip a backpack entry in its matching organ slot.

    Refuses unidentified items (see ``can_equip``). Returns True when the
    inventory was mutated.
    """
    if not isinstance(inventory, dict):
        return False
    grid = inventory.get('grid') or []
    if not 0 <= index < len(grid):
        return False
    entry = grid[index]
    if not can_equip(entry):
        return False
    equip_slot = ITEMS[entry['item']]['equipSlot']
    equipped = inventory.setdefault('equipped', {})
    old = equipped.get(equip_slot)
    equipped[equip_slot] = {
        'item': entry['item'],
        'count': entry.get('count', 1),
        'instance_data': entry.get('instance_data'),
    }
    grid.pop(index)
    if old:
        grid_auto_place_instance(grid, old, cols=INV_COLS, rows=INV_ROWS)
    return True


def gem_socket_target(entry):
    """Which QWER key socket this entry's gem colour belongs to, else None.

    Thin wrapper over ``systems.gems.gem_slot_for_item`` (Q blue, W green,
    E red, R white) so this module stays importable on its own.
    """
    if not isinstance(entry, dict):
        return None
    from systems.gems import gem_slot_for_item
    return gem_slot_for_item(entry.get('item', ''))


def socket_gem_from_grid(inventory, index, dest_key=None):
    """Socket a grid gem into its colour's key slot. Returns True when it did.

    Owner rule for issue #94: gems must be equippable with the right-click
    SOCKET action alone, since left-click drag and drop is gone. Rules:

      * the gem's own colour picks the slot (Q blue / W green / E red /
        R white) — a wrong-colour destination is refused;
      * an OCCUPIED slot is never overwritten — the existing gem stays and
        the grid entry stays too;
      * on success the grid entry is consumed by the socket.

    ``dest_key`` defaults to the gem's own slot and exists so a caller can
    assert the colour matches an explicit destination.
    """
    if not isinstance(inventory, dict):
        return False
    grid = inventory.get('grid') or []
    if not 0 <= index < len(grid):
        return False
    entry = grid[index]
    slot_key = gem_socket_target(entry)
    if slot_key is None:
        return False
    if dest_key is not None and dest_key != slot_key:
        return False
    sockets = inventory.setdefault('gem_sockets', {})
    if sockets.get(slot_key):
        return False
    sockets[slot_key] = {'item': entry['item'],
                         'count': entry.get('count', 1),
                         'instance_data': entry.get('instance_data')}
    grid.pop(index)
    return True


def make_inventory():
    inv = {
        'equipped': {
            'lungs':     None,
            'heart':     None,
            'liver':     None,
            'intestine': None,
            'kidney':    None,
        },
        'grid':        [],
        'gem_sockets': {'Q': None, 'W': None, 'E': None, 'R': None},
        'flask_slot':  None,
        'grid_v':      INV_GRID_VERSION,
    }
    # Starter tarot currency (issue #73 phase B): one complete Fool, half a
    # Magician, a single Wheel quarter — enough to try the usage flow.
    try:
        import systems.currency as _currency
        for slot in _currency.starter_set():
            grid_auto_place(inv['grid'], slot['item'], slot['count'],
                            cols=INV_COLS, rows=INV_ROWS)
    except Exception:
        pass
    # Starter flask in the T slot (issue #73 ADDITION) so the keybind is
    # discoverable from the first run. One charge = one use per wave.
    inv['flask_slot'] = {'item': 'flask_health', 'count': 1, 'charges': 1}
    return inv


def add_instance_to_stash(stash_tab, slot):
    """Auto-place a full instanced slot into the stash tab grid.
    Strips col/row before placement. Returns the stash_tab (mutated in-place)."""
    entry = {k: v for k, v in slot.items() if k not in ('col', 'row')}
    grid_auto_place_instance(stash_tab, entry)
    return stash_tab


def add_to_stash(stash_tab, item_id, count):
    """Add items to a stash tab grid using auto-placement and stacking.
    Returns the stash_tab (mutated in-place)."""
    grid_auto_place(stash_tab, item_id, count)
    return stash_tab


# ── spatial grid helpers ──────────────────────────────────────────────

def grid_build_map(grid, cols=None, rows=None):
    """Return rows×cols 2-D list where each cell is the item index or None.
    Defaults to the stash grid dims (GRID_COLS/GRID_ROWS)."""
    cols = GRID_COLS if cols is None else cols
    rows = GRID_ROWS if rows is None else rows
    m = [[None] * cols for _ in range(rows)]
    for idx, entry in enumerate(grid):
        if not isinstance(entry, dict):
            continue
        idef = ITEMS.get(entry['item'], {})
        w, h = idef.get('size', (1, 1))
        c0, r0 = entry['col'], entry['row']
        for dr in range(h):
            for dc in range(w):
                r, c = r0 + dr, c0 + dc
                if 0 <= r < rows and 0 <= c < cols:
                    m[r][c] = idx
    return m


def grid_can_place(grid, item_id, col, row, cols=None, rows=None):
    cols = GRID_COLS if cols is None else cols
    rows = GRID_ROWS if rows is None else rows
    w, h = ITEMS.get(item_id, {}).get('size', (1, 1))
    if col + w > cols or row + h > rows:
        return False
    m = grid_build_map(grid, cols, rows)
    for dr in range(h):
        for dc in range(w):
            if m[row + dr][col + dc] is not None:
                return False
    return True


def grid_auto_place_instance(grid, slot, cols=None, rows=None):
    """Place a prebuilt slot dict (carrying 'instance_data') into the first free
    position, preserving all its keys. For non-stackable instanced gear.
    Returns True if placed, False if the grid is full."""
    item_id = slot['item']
    w, h = ITEMS.get(item_id, {}).get('size', (1, 1))
    cols = GRID_COLS if cols is None else cols
    rows = GRID_ROWS if rows is None else rows
    for row in range(rows - h + 1):
        for col in range(cols - w + 1):
            if grid_can_place(grid, item_id, col, row, cols, rows):
                grid.append({**slot, 'col': col, 'row': row})
                return True
    return False


def grid_auto_place(grid, item_id, count, cols=None, rows=None):
    """Place count of item_id into the first available grid position(s).
    Returns True if fully placed, False if the grid is full."""
    idef = ITEMS.get(item_id, {})
    w, h = idef.get('size', (1, 1))
    cols = GRID_COLS if cols is None else cols
    rows = GRID_ROWS if rows is None else rows

    # Merge into an existing stack if stackable
    if idef.get('stackable'):
        max_st = idef.get('maxStack', 9999)
        for entry in grid:
            if entry['item'] == item_id and entry['count'] < max_st:
                add = min(max_st - entry['count'], count)
                entry['count'] += add
                count -= add
                if count <= 0:
                    return True

    # Place remaining count into empty slots
    while count > 0:
        cap      = idef.get('maxStack', 1) if idef.get('stackable') else 1
        to_place = min(count, cap)
        placed   = False
        for row in range(rows - h + 1):
            if placed:
                break
            for col in range(cols - w + 1):
                if grid_can_place(grid, item_id, col, row, cols, rows):
                    grid.append({'item': item_id, 'count': to_place,
                                 'col': col, 'row': row})
                    count -= to_place
                    placed = True
                    break
        if not placed:
            return False
    return True
