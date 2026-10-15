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

"""Weather — rain state for the wet-look rendering pipeline.

Render-only: nothing here touches simulation, loot, movement or combat.
The manager is a small dict read by the renderer each frame; rolls are
seed-hashed per level load so the same map always gets the same weather.
"""

import random

# Rain probability per level load; intensity is rolled once at load.
RAIN_CHANCE       = 0.6
RAIN_INTENSITY    = (0.55, 1.0)   # min..max streak opacity/speed factor
PUDDLE_DENSITY    = (0.010, 0.030)  # fraction of floor tiles per puddle-seed tier

# Deep Anima ramps the urge to rain up (depth drives everything —
# here it is cosmetic only, no gameplay input).
DEPTH_RAIN_BONUS  = 0.15          # added chance per 10 depth, capped
DEPTH_RAIN_CAP    = 0.9


def roll(seed: int, depth: int = 0) -> dict:
    """Deterministic weather roll for a level load."""
    rng = random.Random(seed)
    chance = min(DEPTH_RAIN_CAP, RAIN_CHANCE + (depth // 10) * DEPTH_RAIN_BONUS)
    if rng.random() >= chance:
        return {'raining': False, 'intensity': 0.0, 'seed': seed}
    intensity = rng.uniform(*RAIN_INTENSITY)
    return {'raining': True, 'intensity': intensity, 'seed': seed}


def default() -> dict:
    return {'raining': False, 'intensity': 0.0, 'seed': 0}


def puddle_strength(intensity: float) -> float:
    """Map rain intensity → per-cell puddle fraction (density band)."""
    lo, hi = PUDDLE_DENSITY
    return lo + (hi - lo) * intensity
