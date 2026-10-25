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
Ability system — abilities live on GEMS (QWER), not organs.

Gem COLORS map onto the four action keys (see systems/gems.py):
    Q  blue  -> cone actives (aimed with the mouse)
    W  green -> movement actives (dash / blink)
    E  red   -> survival actives (lifesteal / fire aura — pressed on E)
    R  white -> ultimate: any ability, rolled at a higher floor

Tiers are driven by the item's rarity:
    common=0 -> uncommon=1 -> rare=2 -> epic=3 -> legendary=4
"""

import math

RARITY_TIER = {'common': 0, 'uncommon': 1, 'rare': 2, 'epic': 3, 'legendary': 4,
               'mythic': 4}   # mythic tops the same tier-5 ladder (King of Pikes)

ABILITIES = {
    # ── active: cones (liver) ─────────────────────────────────────────
    'cone_physical': {
        'label': 'Physical Cone', 'short': 'Phys', 'type': 'active', 'dmg_type': 'physical',
        'cooldown': [3.0, 2.4, 1.8, 1.2, 0.9],
        'damage':   [30,  55,  90,  150, 220],
        'range': 2.2, 'angle': 70,
    },
    'cone_fire': {
        'label': 'Fire Cone', 'short': 'Fire', 'type': 'active', 'dmg_type': 'fire',
        'cooldown': [3.0, 2.4, 1.8, 1.2, 0.9],
        'damage':   [25,  45,  80,  135, 200],
        'range': 2.0, 'angle': 70,
    },
    'cone_cold': {
        'label': 'Cold Cone', 'short': 'Cold', 'type': 'active', 'dmg_type': 'cold',
        'cooldown': [3.0, 2.4, 1.8, 1.2, 0.9],
        'damage':   [20,  38,  65,  110, 165],
        'range': 2.0, 'angle': 80,
    },
    'cone_lightning': {
        'label': 'Lightning Cone', 'short': 'Bolt', 'type': 'active', 'dmg_type': 'lightning',
        'cooldown': [3.0, 2.4, 1.8, 1.2, 0.9],
        'damage':   [15,  30,  55,  100, 155],
        'range': 2.4, 'angle': 60,
    },
    'cone_magic': {
        'label': 'Magic Cone', 'short': 'Magic', 'type': 'active', 'dmg_type': 'magic',
        'cooldown': [3.6, 3.0, 2.1, 1.5, 1.2],
        'damage':   [35,  65,  110, 180, 270],
        'range': 2.0, 'angle': 60,
    },
    # ── active: movement (lungs) ─────────────────────────────────────
    'dash': {
        'label': 'Dash', 'short': 'Dash', 'type': 'active',
        'cooldown': [3.6, 3.0, 2.1, 1.2, 0.9],
        'distance': [2.0, 2.5, 3.0, 4.0, 5.0],
    },
    'blink': {
        'label': 'Blink', 'short': 'Blink', 'type': 'active',
        'cooldown': [4.8, 3.6, 2.4, 1.5, 1.2],
        'max_range': [4.0, 6.0, 8.0, 12.0, 15.0],
    },
    # ── active: survival (E slot) — timed buffs ────────────────────────
    'lifesteal': {
        'label': 'Lifesteal', 'short': 'Leech', 'type': 'active',
        'cooldown': [10.0, 9.0, 8.0, 7.0, 6.0],
        'duration': [4.0, 5.0, 6.0, 7.0, 8.0],
        'pct': [0.05, 0.10, 0.18, 0.30, 0.40],
    },
    'fire_aura': {
        'label': 'Fire Aura', 'short': 'Aura', 'type': 'active',
        'cooldown': [12.0, 11.0, 10.0, 9.0, 8.0],
        'duration': [4.0, 5.0, 6.0, 7.0, 8.0],
        'radius': [0.35, 0.5, 0.65, 0.8, 1.0],
        'dps':    [5.0, 10.0, 18.0, 30.0, 45.0],
    },
}

CONE_POOL     = [k for k, v in ABILITIES.items() if k.startswith('cone_')]
MOVEMENT_POOL = ['dash', 'blink']
# Explicit list: these ARE actives now (pressed on E), the pool name only
# describes their former always-on life. Kept for gems.py pool wiring.
PASSIVE_POOL  = ['lifesteal', 'fire_aura']

def tier_for_rarity(rarity):
    return RARITY_TIER.get(rarity, 0)


def cone_targets(px, py, dir_x, dir_y, ability_id, tier, zombies):
    """Return (hit_list, damage) for a single cone activation."""
    ab   = ABILITIES[ability_id]
    dmg  = ab['damage'][tier]
    r    = ab['range']
    half = math.cos(math.radians(ab['angle'] / 2))

    dlen = math.hypot(dir_x, dir_y)
    if dlen < 0.001:
        return [], 0
    nx, ny = dir_x / dlen, dir_y / dlen

    hits = []
    for z in zombies:
        if z.get('health', 0) <= 0:
            continue
        dx = z['x'] - px
        dy = z['y'] - py
        dist = math.hypot(dx, dy)
        if dist > r or dist < 0.01:
            continue
        if (dx / dist) * nx + (dy / dist) * ny >= half:
            hits.append(z)
    return hits, dmg
