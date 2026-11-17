#!/usr/bin/env python3
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

"""Leveling-pace simulator (leveling rework plan, .ai/LEVELING_REWORK_PLAN.md).

Drys out the two questions the rework keeps re-litigating:

1. how long a level takes (XP per level vs XP per wave at matched depth), and
2. how fast you fall off when farming below your level.

All live values are imported from `systems.xp` and `core.anima_gen` - the
simulator itself owns *no* progression data, only the pace model:

  - assumed seconds per kill (including walk/aim), rising gently with depth
  - assumed seconds between waves
  - assumed average kill-streak (the angel-meter chain bonus)

Pure stdlib; no numpy (BLUEPRINT §24). Run from the repo root:

    python3 tools/leveling_sim.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.anima_gen import effective_level
import systems.xp as xp

# ── pace assumptions (the only knobs here) ──────────────────────────────
def kill_interval(depth: float) -> float:
    """Seconds per effective kill (walk + aim + TTK), gently more at depth."""
    return 2.2 + 0.03 * depth

WAVE_INTERMISSION_S = 4.0   # wave-clear overlap / regroup breath
AVG_STREAK          = 4     # angel-meter chain average (+20% XP)

# ── proposed-curve helper (plan §2.2) ────────────────────────────
# Owner ruling 2026-11: ~150 real hours to level 70. Under this pace model
# that is ~105 h of pure matched-depth pushing (the other ~40 % is farming,
# deaths, hub time). The time budget per level follows
#   t(L) = 0.4936·L + 0.00639·L^2.5   (minutes at matched depth)
# calibrated so Σt ≈ 6300 min with t(1) ≈ 0.5 min. The SHIP artifact is the
# per-level XP requirement table derived from it - one line per level, no
# closed form - see plan §2.2 for the recipe: req(L) = round(t(L) ·
# kills_per_min(L) · kill_xp(L)). Kill-interval calibration (Phase 0)
# changes req by t·rate - re-fit and regenerate the table, never hand-edit
# single rows.

WAVE_CAP = 40   # owner-ruled lever 2026-11: raise ENEMY COUNT per wave;
                # live `core.anima_flow` spawns min(20, 5 + depth) - the cap
                # move lives there, this parameter previews the economy.

import math

_TIME_B, _TIME_A = 0.4936, 0.00639

def target_minutes(level: float) -> float:
    """Proposed matched-depth minutes/level for level `level`."""
    return _TIME_B * level + _TIME_A * level ** 2.5

def _depth_for(level: int) -> int:
    return next(d for d in range(1, 400) if effective_level(d) >= level)

def wave_size(depth: int, cap: int = WAVE_CAP) -> int:
    """Enemies per spawn charge: 5 + depth, floored at the depth cap."""
    return min(cap, 5 + depth)

def proposed_requirements() -> list:
    """69 per-level XP requirements hitting the 150 h budget.

    Uses the PLAN's proposed kill XP (6 + 3·monster_level, plan §2.2), not
    the live `xp.kill_xp` - this mode previews the Phase 4 data. Keep the
    two in sync when the plan's §2.2 amplitudes change."""
    streak = xp.streak_multiplier(AVG_STREAK)
    reqs = []
    for level in range(1, xp.MAX_LEVEL):
        depth = _depth_for(level)
        wave = wave_size(depth)
        per_min = 60.0 / (kill_interval(depth) + WAVE_INTERMISSION_S / wave)
        per_kill = (6 + 3.0 * effective_level(depth)) * streak
        reqs.append(max(1, int(round(target_minutes(level) * per_min * per_kill))))
    # monotone so the bar never shrinks
    for i in range(1, len(reqs)):
        reqs[i] = max(reqs[i], reqs[i - 1] + 1)
    return reqs

if '--proposal' in sys.argv:
    reqs = proposed_requirements()
    print('== PROPOSAL: 150 h budget ==')
    print('req table (69 entries) - total', f'{sum(reqs):,}', 'XP')
    for level in [1, 5, 10, 20, 30, 40, 50, 60, 65, 69]:
        req = reqs[level - 1]
        depth = _depth_for(level)
        wave = min(20, 5 + depth)
        per_kill = xp.kill_xp(effective_level(depth)) \
            * xp.streak_multiplier(AVG_STREAK)
        kills = req / per_kill
        print(f'  lvl {level:2d}: req {req:8d} | {kills:7.1f} kills '
              f'| {kills / wave:6.2f} waves | target {target_minutes(level):6.1f} min')
    print('first/last:', reqs[:4], '...', reqs[-2:])
    sys.exit(0)

if __name__ == '__main__':
    max_level = xp.MAX_LEVEL
    streak_mult = xp.streak_multiplier(AVG_STREAK)

    print('== XP curve (live systems/xp.py values) ==')
    total = xp.total_xp_for_level(max_level)
    print(f'total XP to level {max_level}: {total:,}')

    print()
    print('lvl |    req | depth | kills/level | waves/level | ~min/level')
    marks = list(range(1, 12)) + [15, 20, 25, 30, 35, 40, 45,
                                  50, 55, 60, 65, max_level - 1]
    for level in marks:
        need = xp.xp_for_level(level)
        if need == 0:
            print(f'{level:3d} | (cap)')
            continue
        depth = next(d for d in range(1, 400)
                     if effective_level(d) >= level)
        per_kill = xp.award_for_kill(level, effective_level(depth), AVG_STREAK)
        kills = need / per_kill
        wave = min(20, 5 + depth)
        waves = kills / wave
        minutes = (kills * kill_interval(depth)
                   + waves * WAVE_INTERMISSION_S) / 60.0
        print(f'{level:3d} | {need:6d} | {depth:5d} | {kills:11.1f} '
              f'| {waves:11.2f} | {minutes:10.1f}')

    print()
    print('== wave economy at matched depth ==')
    for level in [1, 5, 10, 20, 30, 40, 50, 60]:
        depth = next(d for d in range(1, 400) if effective_level(d) >= level)
        wave_xp = min(20, 5 + depth) * xp.award_for_kill(
            level, effective_level(depth), AVG_STREAK)
        print(f'level {level:2d}: wave XP ~ {wave_xp:5d} '
              f'| need {xp.xp_for_level(level):5d} '
              f'| {xp.xp_for_level(level) / wave_xp:.2f} waves')

    print()
    print('== farming below your level (streak-inclusive XP per kill) ==')
    for level in [20, 30, 40]:
        for under in [0, 3, 5, 8, 10, 15, 20]:
            monster_level = max(1, level - under)
            per_kill = xp.award_for_kill(level, monster_level, AVG_STREAK)
            need = xp.xp_for_level(level)
            print(f'level {level}: {under:2d} under '
                  f'-> {need / per_kill:7.1f} kills/level '
                  f'({per_kill:.0f} XP/kill)')
        print()

    print('== death penalty ==')
    for level in [5, 20, 40, 60]:
        need = xp.xp_for_level(level)
        print(f'level {level}: loses {need * xp.DEATH_XP_LOSS_PCT:6.0f} XP '
              f'(= {need * xp.DEATH_XP_LOSS_PCT / (6 + 3.0 * level):5.1f} '
              f'matched-depth kills)')
