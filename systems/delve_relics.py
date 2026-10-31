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
Delve relics - run-scoped boons offered at Anima Cart (checkpoint) shrines
Replaces the build-swing itch the old tarot card
effects provided: 1-of-3 boon choice at each checkpoint, scoped to the
current delve run (persists with the delve snapshot).

Only levers the delve already controls are used (light radius, darkness
DPS, enemy HP, move speed) so no combat-pipeline changes are required.
"""

import random

# Chance-based: rolled once when the offer is generated.
RELIC_BOONS = [
    {
        'id': 'ember_cartography',
        'name': 'Ember Cartography',
        'desc': '+25% light radius for this run.',
        'apply': {'light_mult': 1.25},
    },
    {
        'id': 'veil_sprint',
        'name': 'Veil Sprint',
        'desc': '+15% move speed for this run.',
        'apply': {'speed_mult': 1.15},
    },
    {
        'id': 'sturdy_stock',
        'name': 'Sturdy Stock',
        'desc': '-25% enemy HP for this run.',
        'apply': {'enemy_hp_mult': 0.75},
    },
    {
        'id': 'lantern_soul',
        'name': 'Lantern Soul',
        'desc': '-30% darkness damage for this run.',
        'apply': {'darkness_mult': 0.7},
    },
    {
        'id': 'dark_bargain',
        'name': 'Dark Bargain',
        'desc': '+50% darkness damage for this run.',
        'apply': {'darkness_mult': 1.5},
    },
]


def roll_relic_offer(rng: random.Random, taken_ids: list) -> list:
    """Roll 3 distinct boons, excluding already-taken unique boons."""
    pool = [b for b in RELIC_BOONS if b['id'] not in taken_ids]
    rng.shuffle(pool)
    return pool[:3]


def aggregate_relic_effects(relic_ids: list) -> dict:
    """Combine all taken boons into a single multiplier dict."""
    effects = {'light_mult': 1.0, 'speed_mult': 1.0, 'enemy_hp_mult': 1.0,
               'darkness_mult': 1.0}
    by_id = {b['id']: b for b in RELIC_BOONS}
    for relic_id in relic_ids:
        boon = by_id.get(relic_id)
        if boon is None:
            continue
        for key, value in boon['apply'].items():
            effects[key] = effects.get(key, 1.0) * value
    return effects
