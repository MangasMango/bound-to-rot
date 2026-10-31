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

"""
Poker currency — PoE-style stacking currency cards (issue #73 DESIGN PIVOT,
re-skinned to poker cards for the western dark fantasy migration).

**The Joker is the ONLY quarter-stacked card** (BLUEPRINT §19.193): its drops
and starter grant come as 4 quarters, it needs 4/4 to complete, and applying
consumes 4. Every OTHER card is WHOLE: 1 count = 1 usable card, applying
consumes 1 — drops, starter grants and vendor recipes all hand out single
cards. All cards stack by item id in the inventory (entry['count']).

Semantics (owner's list in issue #73, keyed by the legacy arcana id — the
apply logic, drop tables and tests all key off those integers):

    0   The Joker           - identify an item (all items drop unidentified)
    1   Ace of Hearts       - common item -> uncommon
    4   King of Pikes       - item -> mythic
    10  Queen of Diamonds   - random reroll of an item's rolls
    11  Ace of Clubs        - fine-tune implicit numeric ranges toward balance
    13  Ace of Pikes        - divine overhaul: destroy current values, full new roll
    14  Queen of Hearts     - organ rot cleanse (full revert of a rotten organ)
    15  Jack of Pikes       - duplicate the item as a cursed perfect reflection
    17  Ace of Diamonds     - Gemcutter's Prism: reroll a gem's ability

Card faces come from the poker deck (assets/cards/dark).
"""

import random

import systems.itemgen as itemgen
from systems.items import (ITEMS, grid_auto_place_instance,
                           INV_COLS, INV_ROWS)

QUARTERS_PER_CARD = 4
# Fresh-vessel card grant (owner ruling 2026-10-07): one complete Joker
# (quarters — it's the only stacked card) plus one whole Ace of Hearts +
# Queen of Diamonds.
STARTER_CARD_QUARTERS = {
    0: 4,   # The Joker — one complete card (4/4 quarters)
    1: 1,   # Ace of Hearts — one whole card
    10: 1,  # Queen of Diamonds — one whole card
}

# Card ids used as currency (legacy arcana ints are the internal keys);
# depth gate (>=) drives what can drop where.
CURRENCY_CARDS = {
    0:  {'name': 'The Joker',         'target': 'item',  'depth_min': 1,
         'description': 'Press right click on an item to identify it'},
    1:  {'name': 'Ace of Hearts',     'target': 'item',  'depth_min': 1,
         'description': 'Upgrades a common item to uncommon.'},
    4:  {'name': 'King of Pikes',     'target': 'item',  'depth_min': 3,
         'description': 'Ascends an item to MYTHIC rarity.'},
    10: {'name': 'Queen of Diamonds', 'target': 'item',  'depth_min': 2,
         'description': 'Randomly rerolls all of an item\'s affixes.'},
    11: {'name': 'Ace of Clubs',      'target': 'item',  'depth_min': 3,
         'description': 'Fine-tunes every affix to its balanced midpoint.'},
    13: {'name': 'Ace of Pikes',      'target': 'item',  'depth_min': 4,
         'description': 'Divine overhaul: destroys current values, full new roll.'},
    14: {'name': 'Queen of Hearts',   'target': 'organ', 'depth_min': 1,
         'description': 'Cleanses an organ\'s rot — a ROTTEN organ fully reverts.'},
    15: {'name': 'Jack of Pikes',     'target': 'item',  'depth_min': 4,
         'description': 'Duplicates the item as a cursed perfect reflection.'},
    17: {'name': 'Ace of Diamonds',   'target': 'gem',   'depth_min': 3,
         'description': "Gemcutter's Prism: rerolls a gem's ability."},
}

DEFAULT_ARCANA_ORDER = (0, 1, 4, 10, 11, 13, 14, 15, 17)

# arcana id -> poker item-id suffix (systems.items.ITEMS key: 'poker_' + it)
_CARD_SUFFIX = {
    0:  'joker',
    1:  'ace_hearts',
    4:  'king_pikes',
    10: 'queen_diamonds',
    11: 'ace_clubs',
    13: 'ace_pikes',
    14: 'queen_hearts',
    15: 'jack_pikes',
    17: 'ace_diamonds',
}
_SUFFIX_ARCANA = {v: k for k, v in _CARD_SUFFIX.items()}


def card_item_id(arcana):
    suffix = _CARD_SUFFIX.get(int(arcana))
    return f'poker_{suffix}' if suffix else f'poker_card_{int(arcana)}'


def arcana_of(item_id):
    """Arcana id for a card item id (poker or legacy tarot), or None."""
    if not isinstance(item_id, str):
        return None
    if item_id.startswith('poker_'):
        suffix = item_id[len('poker_'):]
        if suffix in _SUFFIX_ARCANA:
            return _SUFFIX_ARCANA[suffix]
        if suffix.startswith('card_'):
            try:
                return int(suffix[len('card_'):])
            except ValueError:
                return None
        return None
    if item_id.startswith('tarot_card_'):
        # legacy saves keep working even before the load remap runs
        try:
            return int(item_id[len('tarot_card_'):])
        except ValueError:
            return None
    return None


def is_card_item(item_id):
    return arcana_of(item_id) is not None


def quarters_needed(arcana):
    """Counts required to complete/consume one use of an arcana.

    The Joker is the ONLY quarter-stacked card (needs QUARTERS_PER_CARD);
    every other card is whole — 1 count = 1 usable card (§19.193)."""
    return QUARTERS_PER_CARD if arcana == 0 else 1


def card_complete(entry):
    """Is this stack usable right now? (Joker: >= 4/4, others: >= 1)"""
    if not entry:
        return False
    arcana = arcana_of(entry.get('item', ''))
    return entry.get('count', 0) >= quarters_needed(arcana)


def stack_label(entry):
    """Grid counter. A COMPLETE Joker stack shows its plain quarter count
    (e.g. '41') so each 4-quarter spend stays visible — the old cap read
    '4/4' for a 45-stack and identification looked free. Partial stacks
    read 'n/4'; whole cards show their plain count."""
    arcana = arcana_of(entry.get('item', ''))
    count = int(entry.get('count', 0))
    if arcana == 0 and 0 < count < QUARTERS_PER_CARD:
        return f"{count}/{QUARTERS_PER_CARD}"
    return str(count)


def make_card_slot(arcana, quarters=1, col=0, row=0):
    return {'item': card_item_id(arcana), 'count': int(quarters),
            'col': col, 'row': row}


def starter_set():
    """Starter currency handed to a fresh vessel (make_inventory)."""
    return [make_card_slot(arcana, quarters)
            for arcana, quarters in STARTER_CARD_QUARTERS.items()]


# ── per-card drop weights (BLUEPRINT §23.219) ─────────────────────────
# Whole-card drops: every card drop event is one COMPLETE card. The Joker is
# the most likely drop early on (identification income); its weight tapers
# with depth because vendoring trash (§24, planned) will become the steady
# Joker source — PoE-style, without any gold economy.
CARD_DROP_WEIGHTS = {
    0: 40,   # The Joker         — identification
    1: 15,   # Ace of Hearts     — common -> uncommon
    14: 12,  # Queen of Hearts   — organ rot cleanse
    10: 8,   # Queen of Diamonds — reroll
    11: 8,   # Ace of Clubs      — balance
    4: 6,    # King of Pikes     — mythic
    13: 4,   # Ace of Pikes      — full reroll
    15: 4,   # Jack of Pikes     — cursed reflection
    17: 3,   # Ace of Diamonds   — gemcutter's prism
}
# fool_* identifiers kept from the tarot era — they key the Joker's taper.
FOOL_TAPER_START_DEPTH = 5    # full Joker weight up to here...
FOOL_TAPER_RATE = 0.08        # ...then -8% of its weight per extra depth...
FOOL_TAPER_FLOOR = 0.15       # ...never below 15% of its base weight


def fool_weight(depth):
    """The Joker's depth-tapered drop weight."""
    taper = 1.0 if depth <= FOOL_TAPER_START_DEPTH else (
        max(FOOL_TAPER_FLOOR, 1.0 - FOOL_TAPER_RATE * (depth - FOOL_TAPER_START_DEPTH)))
    return CARD_DROP_WEIGHTS[0] * taper


def roll_fraction_drop(depth=1, rng=None):
    """A loot-table card drop: (arcana, counts).

    Weighted per-card selection (CARD_DROP_WEIGHTS) over the cards that
    pass their depth_min gate; the Joker's weight decays with depth.
    Whole-card drops: a Joker arrives as its 4 quarters, every other card
    as 1 count — both are exactly one complete card (§23.218)."""
    rng = rng or random
    pool = [a for a, c in CURRENCY_CARDS.items() if depth >= c['depth_min']]
    if not pool:
        pool = [0]
    weights = [fool_weight(depth) if a == 0 else CARD_DROP_WEIGHTS.get(a, 1)
               for a in pool]
    arcana = rng.choices(pool, weights=weights, k=1)[0]
    return arcana, quarters_needed(arcana)


def roll_card_drop_slot(depth=1, rng=None, col=0, row=0):
    """Full grid slot dict for a card drop (always one whole card)."""
    arcana, quarters = roll_fraction_drop(depth, rng)
    return make_card_slot(arcana, quarters, col, row)


def add_card_to_grid(grid, arcana, quarters):
    """Merge counts into an existing stack of this arcana (or auto-place)."""
    item_id = card_item_id(arcana)
    for entry in grid:
        if entry['item'] == item_id:
            entry['count'] = entry.get('count', 0) + quarters
            return True
    return grid_auto_place_instance(grid, make_card_slot(arcana, quarters))


def consume_card(inventory, entry, src, idx):
    """Spend one card use (Joker: 4 quarters, others: 1 count). entry may
    live in the inventory grid or the gem sockets; returns True when
    consumed."""
    if not card_complete(entry):
        return False
    arcana = arcana_of(entry.get('item', ''))
    entry['count'] -= quarters_needed(arcana)
    if entry['count'] <= 0:
        if src == 'gems':
            inventory['gem_sockets'][idx] = None
        elif src == 'grid':
            inventory['grid'].pop(idx)
    return True


# ── application ───────────────────────────────────────────────────────

def _target_entry(inventory, src, idx):
    if src == 'grid':
        return inventory['grid'][idx] if idx < len(inventory['grid']) else None
    if src == 'equipped':
        return inventory['equipped'].get(idx)
    if src == 'gems':
        return (inventory.get('gem_sockets') or {}).get(idx)
    return None


def valid_target(arcana, target):
    """Is `target` (inventory slot dict) a legal target for this card?"""
    info = CURRENCY_CARDS.get(arcana)
    if not info or target is None:
        return False
    kind = info['target']
    if kind == 'item':
        return isinstance(target.get('instance_data'), dict) \
            and not is_card_item(target.get('item', ''))
    if kind == 'organ':
        # Queen of Hearts: only an organ (equipSlot) that actually carries rot.
        inst = target.get('instance_data')
        if not isinstance(inst, dict) or is_card_item(target.get('item', '')):
            return False
        if not ITEMS.get(target.get('item', ''), {}).get('equipSlot'):
            return False
        return itemgen.rot_of(inst) > 0 or itemgen.is_rotten(inst)
    if kind == 'gem':
        return bool(target.get('instance_data', {}).get('ability'))
    return False


def apply_card(game, arcana, src, idx):
    """Apply a complete card to a target. Consumes one card use on success
    (Joker: 4 quarters, every other card: 1 count).

    `game` is duck-typed and needs .inventory. Returns a human-readable result
    or None when the application is invalid."""
    inventory = game.inventory
    card_entry = _target_entry(inventory, src, idx)
    arc = arcana_of(card_entry.get('item', '')) if card_entry else arcana
    if arc is None or arc not in CURRENCY_CARDS:
        return None
    info = CURRENCY_CARDS[arc]

    # Item-target cards: read the target from the pending UI state. The UI
    # passes the target slot coords through `game._card_apply_target`.
    tgt = getattr(game, '_card_apply_target', None) or ()
    if len(tgt) != 2:
        return None
    t_src, t_idx = tgt
    target = _target_entry(inventory, t_src, t_idx)
    if not valid_target(arc, target):
        return None

    result = None
    if arc == 0:      # The Joker
        itemgen.identify(target)
        result = 'Identified.'
    elif arc == 1:    # Ace of Hearts
        inst = target['instance_data']
        if inst.get('rarity') != 'common':
            return None
        inst['rarity'] = 'uncommon'
        result = 'Upgraded to uncommon.'
    elif arc == 4:    # King of Pikes
        inst = target['instance_data']
        inst['rarity'] = 'mythic'
        result = 'Ascended to MYTHIC.'
    elif arc == 10:   # Queen of Diamonds
        _reroll(target, seed=random.getrandbits(24), keep_rarity=True)
        result = 'Fate rerolled.'
    elif arc == 11:   # Ace of Clubs
        inst = target['instance_data']
        balanced = itemgen.balanced_affix_values(inst)
        prefixes, suffixes = {}, {}
        for aid, val in balanced.items():
            (prefixes if itemgen._AFFIX_BY_ID[aid]['kind'] == 'prefix'
             else suffixes)[aid] = val
        inst['affixes'] = {'prefixes': prefixes, 'suffixes': suffixes}
        # a ROTTEN organ stays buffed after balancing (BLUEPRINT §22)
        if itemgen.is_rotten(inst):
            itemgen.apply_rotten_buff(inst['affixes'])
        result = 'Balanced to the midpoint.'
    elif arc == 13:   # Ace of Pikes
        _reroll(target, seed=random.getrandbits(24), keep_rarity=True)
        result = 'Divine overhaul: new stat roll.'
    elif arc == 14:   # Queen of Hearts — organ rot cleanse
        if itemgen.cleanse_rot(target):
            result = 'Rot cleansed: the organ is pure again.'
        else:
            return None
    elif arc == 15:   # Jack of Pikes
        twin = _cursed_reflection(target)
        if grid_auto_place_instance(inventory['grid'], twin,
                                    cols=INV_COLS, rows=INV_ROWS):
            result = 'A cursed reflection appears.'
        else:
            return None   # no room — don't consume
    elif arc == 17:   # Ace of Diamonds
        inst = target['instance_data']
        new_ab = _reroll_gem_ability(inst)
        if new_ab:
            result = f"Gem ability rerolled: {new_ab.replace('_', ' ').title()}."
        else:
            return None

    if result is not None:
        consume_card(inventory, card_entry, src, idx)
    return result


def _reroll(target, seed=None, keep_rarity=False):
    """Queen of Diamonds / Ace of Pikes: destroy the current values and roll
    anew, keeping the item's base, ilvl and (for the Queen) its rarity. Rot
    is a physical property of the organ — the meter carries over, and a
    rotten organ stays ROTTEN on its fresh roll (buff + drawback re-applied)."""
    inst = target['instance_data']
    item_id = target.get('item', '')
    defn = ITEMS.get(item_id, {})
    prev_rot = itemgen.rot_of(inst)
    was_rotten = itemgen.is_rotten(inst)
    fresh = itemgen.generate_instance(
        item_id, inst.get('ilvl', 1),
        rarity=inst.get('rarity') if keep_rarity else None,
        equip_slot=defn.get('equipSlot'),
        base_name=defn.get('name', item_id),
        seed=seed)
    fresh['identified'] = True   # was visibly rolled in front of the player
    if prev_rot:
        fresh['rot'] = min(itemgen.ROT_MAX, prev_rot)
    if was_rotten:
        itemgen.make_rotten(fresh)
    target['instance_data'] = fresh


def _cursed_reflection(target):
    """Jack of Pikes: a perfect duplicate, bound by curse."""
    import copy
    twin = copy.deepcopy(target)
    twin.pop('col', None)
    twin.pop('row', None)
    twin.pop('ability', None)
    inst = twin.get('instance_data')
    if isinstance(inst, dict):
        inst['cursed'] = True
        base = inst.get('display_name') or ITEMS.get(twin.get('item', ''), {}).get('name', '')
        inst['display_name'] = f"{base} of the Cursed Reflection"
    return twin


def _reroll_gem_ability(inst):
    """Ace of Diamonds: reroll a gem's ability within its key-slot pool."""
    import systems.gems as gems
    ab_id = inst.get('ability')
    for slot_key, pool in gems.SLOT_GEM_POOLS.items():
        if ab_id in pool:
            new_ab = gems.random_ability_for_gem_slot(slot_key)
            inst['ability'] = new_ab
            inst['display_name'] = new_ab.replace('_', ' ').title()
            return new_ab
    return None
