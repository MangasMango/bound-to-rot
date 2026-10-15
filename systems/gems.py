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
Gem system — gems grant QWER abilities (issue #73 DESIGN PIVOT).

The ability hotbar is no longer organ-driven: four gem COLORS map onto the
four action keys, and every gem ability is cast by PRESSING its key:

    Q  ->  blue gem   (primary offense: cone actives, aimed with the mouse)
    W  ->  green gem  (mobility actives: dash / blink)
    E  ->  red gem    (survival actives: lifesteal / fire aura — timed buffs)
    R  ->  white gem  (ultimate: any ability, rolled at a higher floor;
                       white = prismatic "all colors at once")

Equipping a gem item into that key's socket (inventory['gem_sockets'])
grants/sets that slot's ability. Socketing a different gem re-rolls nothing —
the ability is rolled when the gem ITEM is generated (itemgen.roll_for) and
The Star (Gemcutter's Prism) can reroll it later.

Tier (power) comes from the gem's rarity, same RARITY_TIER ladder as organs.
"""

import random

import systems.abilities as abilities
from systems.abilities import CONE_POOL, MOVEMENT_POOL, PASSIVE_POOL

# ── key slot -> gem color/item ────────────────────────────────────────
GEM_SLOTS    = ('Q', 'W', 'E', 'R')
GEM_COLOR_FOR_SLOT = {'Q': 'blue', 'W': 'green', 'E': 'red', 'R': 'white'}
GEM_SLOT_FOR_COLOR = {v: k for k, v in GEM_COLOR_FOR_SLOT.items()}
GEM_ITEM_FOR_SLOT = {slot: f'gem_{color}'
                     for slot, color in GEM_COLOR_FOR_SLOT.items()}

# Ability pool offered to each key slot when the gem item is generated.
SLOT_GEM_POOLS = {
    'Q': list(CONE_POOL),
    'W': list(MOVEMENT_POOL),
    'E': list(PASSIVE_POOL) + list(CONE_POOL),
    'R': list(CONE_POOL) + list(MOVEMENT_POOL) + list(PASSIVE_POOL),
}

GEM_RARITIES = ('common', 'uncommon', 'rare', 'epic', 'legendary')


def random_ability_for_gem_slot(slot_key, rng=None):
    """Roll an ability id for a gem destined for a QWER key slot."""
    pool = SLOT_GEM_POOLS.get(slot_key)
    if not pool:
        return None
    rng = rng or random
    return rng.choice(pool)


def gem_item_id(slot_key):
    return GEM_ITEM_FOR_SLOT.get(slot_key, 'gem_white')


def random_gem_slot(slot_key, ilvl, seed=None):
    """Build a full grid slot dict for a random gem bound to a key slot."""
    rng = random.Random(seed) if seed is not None else random
    item_id = gem_item_id(slot_key)
    rarity = rng.choice(GEM_RARITIES)
    ability = random_ability_for_gem_slot(slot_key, rng)
    inst = {
        'rarity':     rarity,
        'display_name': f'{ability}'.replace('_', ' ').title() if ability else 'Gem',
        'ilvl':       int(ilvl),
        'identified': True,          # gems are always identified
        'ability':    ability,
    }
    return {'item': item_id, 'count': 1, 'instance_data': inst}


def socketed_ability(inventory, slot_key):
    """Return (instance_data, ability_def, tier) for a socketed gem, or None."""
    if not isinstance(inventory, dict):
        return None
    entry = (inventory.get('gem_sockets') or {}).get(slot_key)
    if not entry:
        return None
    inst = entry.get('instance_data') or {}
    ab = abilities.ABILITIES.get(inst.get('ability'))
    if not ab:
        return None
    tier = min(abilities.tier_for_rarity(inst.get('rarity', 'common')), 4)
    return inst, ab, tier


def is_gem_item(item_id):
    return isinstance(item_id, str) and item_id.startswith('gem_')


def gem_slot_for_item(item_id):
    """Which key slot this gem color belongs to, or None for foreign gems."""
    color = item_id[len('gem_'):] if is_gem_item(item_id) else ''
    return GEM_SLOT_FOR_COLOR.get(color)
