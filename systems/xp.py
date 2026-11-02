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

"""Character XP and leveling (issue #31).

Owner rulings (2026-11-02, issue #31 - supersedes ADR-004 and the
2026-09-27 permadeath ruling):

- XP drops from enemy kills, scaled by the enemy's level (which comes from
  Anima depth via ``core.delve_gen.effective_level``).
- Over-level kills diminish rapidly: farming shallow depths is worthless.
- Each level grants exactly +1 attribute point; the 7 DESCEND attributes
  hard-cap at 10, so the level hard-cap is exactly 7 * ATTR_CAP = 70.
- Vessels grant NO attribute baselines: 70 levels = 70 points = 7x10.
- Death costs 10% of the current level's XP requirement (PoE-style); XP can
  never go below the current level's start, so no de-leveling. No penalty at
  the level cap.
- Permadeath is removed: the character survives death; the delve is lost.

All rules live in this one module so they stay testable in one place.
"""

MAX_LEVEL = 7 * 10   # 70: one attribute point per level, 10 cap, 7 attributes

# XP required to advance from level n to n+1 grows mildly super-linear so
# keeping pace demands pushing deeper (deeper kills are worth more).
_XP_BASE = 40
_XP_LINEAR = 15
_XP_QUAD = 0.35

# Kill XP as a function of the enemy's level.
_KILL_XP_BASE = 8
_KILL_XP_PER_LEVEL = 6

# Over-level diminishing: kills stay full-value while the enemy is at most
# OVER_LEVEL_GRACE levels behind the player, then decay per level to the floor.
OVER_LEVEL_GRACE = 5
_OVER_LEVEL_DECAY = 0.08
_OVER_LEVEL_FLOOR = 0.05

# Kill-streak bonus: +5% per chained kill, capped at +50% (streak 10).
STREAK_BONUS_PER_KILL = 0.05
STREAK_BONUS_MAX_KILLS = 10

# Death penalty: fraction of the current level's XP requirement.
DEATH_XP_LOSS_PCT = 0.10


def xp_for_level(level: int) -> int:
    """XP needed to advance from ``level`` to ``level + 1``.

    Returns 0 at MAX_LEVEL: the bar is capped and nothing more is required.
    """
    if level >= MAX_LEVEL:
        return 0
    n = max(1, int(level))
    raw = _XP_BASE + _XP_LINEAR * (n - 1) + _XP_QUAD * n * (n - 1)
    return max(1, int(round(raw)))


def total_xp_for_level(level: int) -> int:
    """Total accumulated XP needed to reach ``level`` from level 1."""
    return sum(xp_for_level(n) for n in range(1, max(1, int(level))))


def kill_xp(monster_level: float) -> int:
    """Base XP for killing an enemy of the given level."""
    return _KILL_XP_BASE + _KILL_XP_PER_LEVEL * max(0.0, float(monster_level))


def over_level_factor(player_level: int, monster_level: float) -> float:
    """Multiplier for killing an enemy far below the player's level."""
    over = float(player_level) - float(monster_level)
    if over <= OVER_LEVEL_GRACE:
        return 1.0
    return max(_OVER_LEVEL_FLOOR, 1.0 - _OVER_LEVEL_DECAY * (over - OVER_LEVEL_GRACE))


def streak_multiplier(kill_streak: int) -> float:
    """Multiplier for chained kills (the angel-meter streak window)."""
    return 1.0 + STREAK_BONUS_PER_KILL * max(0, min(int(kill_streak), STREAK_BONUS_MAX_KILLS))


def award_for_kill(player_level: int, monster_level: float, kill_streak: int = 0) -> int:
    """Final XP award for one kill. Never below 1."""
    award = kill_xp(monster_level) \
        * over_level_factor(player_level, monster_level) \
        * streak_multiplier(kill_streak)
    return max(1, int(round(award)))


def grant_xp(char, amount: int) -> int:
    """Add XP to a character, rolling level-ups. Returns levels gained.

    XP accrues only below MAX_LEVEL; a capped character ignores XP and the
    bar reads MAX. Each gained level adds exactly one spendable attribute
    point. Recalculation of derived stats is the caller's job.
    """
    amount = max(0, int(amount))
    gained = 0
    level = max(1, int(getattr(char, 'level', 1)))
    xp = max(0, int(getattr(char, 'xp', 0)))
    xp += amount
    while level < MAX_LEVEL:
        need = xp_for_level(level)
        if xp < need:
            break
        xp -= need
        level += 1
        gained += 1
    if level >= MAX_LEVEL:
        xp = 0
    char.level = level
    char.xp = xp
    if gained:
        char.available_points = getattr(char, 'available_points', 0) + gained
    return gained


def death_penalty(char) -> int:
    """Apply the death XP loss. Returns the XP lost (for the death screen).

    PoE-style: the loss is DEATH_XP_LOSS_PCT of the current level's XP
    requirement, floored at the current level's start (no de-leveling) and
    never applied at the level cap.
    """
    level = max(1, int(getattr(char, 'level', 1)))
    if level >= MAX_LEVEL:
        return 0
    need = xp_for_level(level)
    loss = int(round(need * DEATH_XP_LOSS_PCT))
    xp = max(0, int(getattr(char, 'xp', 0)))
    lost = min(xp, loss)
    char.xp = xp - lost
    return lost


def level_progress(char) -> tuple[int, int]:
    """(current XP, XP required for the next level). Required is 0 at cap."""
    level = max(1, int(getattr(char, 'level', 1)))
    return max(0, int(getattr(char, 'xp', 0))), xp_for_level(level)
