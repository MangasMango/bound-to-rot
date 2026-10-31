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
Blacksmith dismantle recipes — static data + pure matcher (BLUEPRINT §24).

The forge panel (assets/ui/blacksmith.png) shows two 8×4 grids: the TOP grid
holds the player's offered items, the BOTTOM grid previews what they are
worth. Everything runs on ONE flow: upgrade recipes are matched first (they
pay better than selling), then every remaining sellable item is dismantled
into The Joker quarters — the card-stacking currency stands in for the gold
economy that was removed (owner ruling 2026-09-27).

Rules carried over from the blueprint (sell scope revised by owner):
  * Sells pay Joker quarters (rarity-scaled for organs/gems/potions,
    flasks flat, cards 1 per card) — PoE wisdom-scrap pattern; this is the
    steady Joker income that lets its drop weight taper with depth
    (§23.220).
  * Selling a legendary or mythic item requires a confirmation popup — those
    are chase items, never destroyed by a misclick.
  * Recipe inputs must be unidentified organs; the output rolls a random
    organ slot at ilvl = max of the inputs (identified organs only SELL).
"""

import random

import systems.itemgen as itemgen
import systems.gems as gems
import systems.currency as currency
from systems.items import ITEMS

# Forge grid dims — matches the painted cells of the blacksmith panel art
# (568×798): two 8 cols × 4 rows grids.
FORGE_COLS = 8
FORGE_ROWS = 4

# Organ base item ids == equip slot names in ITEMS (systems/items.py).
ORGAN_SLOTS = ('lungs', 'heart', 'liver', 'intestine', 'kidney')

# ── sell table (§24.225, revised by owner): everything burns for Joker
# quarters ── organs (identified or not), gems and potions pay by rarity
# (× stack count), flasks pay flat, cards pay 1 quarter per card ────────
SELL_QUARTERS_BY_RARITY = {
    'common': 1, 'uncommon': 2, 'rare': 4,
    'epic': 6, 'legendary': 8, 'mythic': 12,
}
SELL_QUARTERS_FLASK = 4
SELL_QUARTERS_CARD = 1    # per card count (a Joker 4/4 pays itself back)
# Legendary/mythic sells pop a confirmation popup before the item burns.
SELL_CONFIRM_RARITIES = ('legendary', 'mythic')

# ── organ ascension recipes (§24.226) ─────────────────────────────────
# from-rarity → (inputs needed, output rarity); ordered common → epic.
ORGAN_RECIPES = {
    'common':   (4, 'uncommon'),
    'uncommon': (3, 'rare'),
    'rare':     (3, 'epic'),
    'epic':     (2, 'legendary'),
}
# 5× unidentified uncommon organs → 1 complete Queen of Hearts (§24.227).
QUEEN_ORGAN_COUNT = 5
QUEEN_ARCANA = 14


def sell_quarters_for(entry):
    """Joker-quarter value of ONE grid entry (x its stack count), or None
    for zero-value junk. Everything sellable (owner revised §24.225):
    organs — IDENTIFIED OR NOT — gems and potions pay by rarity, flasks
    pay flat, cards pay 1 quarter per card (a Joker stack pays its own
    quarters back). Unknown item ids / rarities refuse."""
    if not isinstance(entry, dict):
        return None
    item_id = entry.get('item', '')
    defn = ITEMS.get(item_id, {})
    count = max(1, int(entry.get('count', 1)))
    if currency.is_card_item(item_id):
        return SELL_QUARTERS_CARD * count
    if defn.get('isFlask'):
        return SELL_QUARTERS_FLASK * count
    if defn.get('isGem') or defn.get('isPotion') or defn.get('equipSlot'):
        quarters = SELL_QUARTERS_BY_RARITY.get(_rarity_of(entry))
        return None if quarters is None else quarters * count
    return None


def _rarity_of(entry):
    inst = entry.get('instance_data')
    if isinstance(inst, dict):
        return inst.get('rarity', 'common')
    return ITEMS.get(entry.get('item', ''), {}).get('rarity', 'common')


def _ilvl_of(entry):
    inst = entry.get('instance_data')
    if isinstance(inst, dict):
        return int(inst.get('ilvl', 1))
    return 1


def _unid_organ_rarity(entry):
    """Rarity key for the organ recipes, or None when the entry does not
    qualify (organs only, unidentified only)."""
    item_id = entry.get('item', '')
    if not ITEMS.get(item_id, {}).get('equipSlot'):
        return None
    if itemgen.is_identified(entry):
        return None
    return _rarity_of(entry)


def _organ_output_slot(rarity, ilvl, rng=None):
    """An unidentified organ of `rarity` in a random slot (§24.226)."""
    rng = rng or random
    item_id = rng.choice(ORGAN_SLOTS)
    inst = itemgen.generate_instance(item_id, max(1, ilvl), rarity=rarity)
    return {'item': item_id, 'count': 1, 'instance_data': inst}


def _gem_output_slot(gem_item_id, next_rarity, ilvl, rng=None):
    """A gem of the same colour, one rarity tier higher (§24.226)."""
    rng = rng or random
    slot_key = gems.gem_slot_for_item(gem_item_id)
    ability = gems.random_ability_for_gem_slot(slot_key, rng)
    inst = {
        'rarity':       next_rarity,
        'display_name': (ability.replace('_', ' ').title()
                         if ability else 'Gem'),
        'ilvl':         max(1, ilvl),
        'identified':   True,          # gems are always identified
        'ability':      ability,
    }
    return {'item': gem_item_id, 'count': 1, 'instance_data': inst}


def _organ_group(grid, consumed, indices, output_slot, label):
    return {'consumed': list(indices), 'outputs': [output_slot],
            'label': label, 'confirm': False}


def match_forge(grid, rng=None):
    """Match a forge (offerings) grid against recipes + the sell table.

    Pure function of the grid's item-id multiset (random output rolls use
    `rng`/module random — callers cache the result by `forge_signature` so a
    resting preview never flickers). Greedy priority: organ ascension →
    Queen of Hearts → gem tier-up → sell everything left for Joker quarters.

    Returns {'groups': [...], 'confirm': bool} where each group is
    {'consumed': [grid indices], 'outputs': [slot dicts],
     'label': str, 'confirm': bool}. Unmatched/unsellable entries are left
    untouched (they ride the grid back to the backpack on close)."""
    rng = rng or random
    consumed = set()
    groups = []

    def free_indices():
        return [i for i, e in enumerate(grid)
                if isinstance(e, dict) and i not in consumed]

    # ── 1. Queen of Hearts (rot-cleanse income, §24.227) ──────────────
    # Runs BEFORE the uncommon ascension: that chain drains uncommons in
    # threes (leaving a remainder of 0-2), so a Queen could never fire from
    # the leftovers. Queen-first keeps both recipes reachable.
    while True:
        pool = [i for i in free_indices()
                if _unid_organ_rarity(grid[i]) == 'uncommon']
        if len(pool) < QUEEN_ORGAN_COUNT:
            break
        take = pool[:QUEEN_ORGAN_COUNT]
        consumed.update(take)
        out = currency.make_card_slot(QUEEN_ARCANA,
                                      currency.quarters_needed(QUEEN_ARCANA))
        groups.append({
            'consumed': take, 'outputs': [out],
            'label': f'{QUEEN_ORGAN_COUNT}× uncommon organ -> '
                     '1× Queen of Hearts',
            'confirm': False,
        })

    # ── 2. organ ascension chains ─────────────────────────────────────
    for from_rarity in ('common', 'uncommon', 'rare', 'epic'):
        n_needed, to_rarity = ORGAN_RECIPES[from_rarity]
        while True:
            pool = [i for i in free_indices()
                    if _unid_organ_rarity(grid[i]) == from_rarity]
            if len(pool) < n_needed:
                break
            take = pool[:n_needed]
            consumed.update(take)
            ilvl = max(_ilvl_of(grid[i]) for i in take)
            out = _organ_output_slot(to_rarity, ilvl, rng)
            groups.append({
                'consumed': take, 'outputs': [out],
                'label': f'{n_needed}× {from_rarity} organ -> '
                         f'1× {to_rarity} organ',
                'confirm': False,
            })

    # ── 3. gem tier-up: 5× same colour AND same rarity ────────────────
    while True:
        buckets = {}
        for i in free_indices():
            entry = grid[i]
            if not ITEMS.get(entry.get('item', ''), {}).get('isGem'):
                continue
            buckets.setdefault(
                (entry['item'], _rarity_of(entry)), []).append(i)
        take = None
        for key in sorted(buckets):
            if len(buckets[key]) >= 5:
                take = buckets[key][:5]
                break
        if take is None:
            break
        gem_item = grid[take[0]]['item']
        from_rarity = _rarity_of(grid[take[0]])
        next_r = itemgen.RARITY_ORDER[min(
            itemgen.RARITY_ORDER.index(from_rarity) + 1,
            len(itemgen.RARITY_ORDER) - 1)]
        consumed.update(take)
        ilvl = max(_ilvl_of(grid[i]) for i in take)
        out = _gem_output_slot(gem_item, next_r, ilvl, rng)
        groups.append({
            'consumed': take, 'outputs': [out],
            'label': f'5× {gem_item.replace("gem_", "")} gem -> '
                     f'1× {next_r} gem',
            'confirm': False,
        })

    # ── 4. sell every remaining sellable item for Joker quarters ──────
    sold, total, confirm = [], 0, False
    for i in free_indices():
        entry = grid[i]
        quarters = sell_quarters_for(entry)
        if quarters is None:
            continue
        sold.append(i)
        total += quarters
        if _rarity_of(entry) in SELL_CONFIRM_RARITIES:
            confirm = True
    if sold:
        groups.append({
            'consumed': sold,
            'outputs': [currency.make_card_slot(0, total)],
            'label': f'Sold {len(sold)} item(s) -> {total} Joker quarters',
            'confirm': confirm,
        })

    return {'groups': groups, 'confirm': confirm}


def forge_signature(grid):
    """Cache key for a forge grid's current match state."""
    return tuple((e.get('item'), e.get('count', 1), e.get('col'), e.get('row'))
                 for e in grid if isinstance(e, dict))
