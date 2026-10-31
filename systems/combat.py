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

import random

CRIT_CHANCE = 0.05
CRIT_MULT   = 2.0    # deadly strike: double damage

DAMAGE_TYPES = {'physical', 'fire', 'cold', 'lightning', 'magic', 'rot'}

# ── To-hit roll ───────────────────────────────────────────────────────
HIT_CHANCE_MIN = 0.05   # floor: even a hopeless attacker connects sometimes
HIT_CHANCE_MAX = 0.95   # ceiling: even a hopeless defender dodges sometimes

# ── Crushing blow ─────────────────────────────────────────────────────
CRUSHING_BLOW_PCT = 0.125  # fraction of the target's current HP added on proc

# ── Status effect constants ───────────────────────────────────────────
BURNING_DURATION   = 3.0   # seconds a burning DoT lasts
BURNING_DPS_RATIO  = 0.30  # burning DPS = hit_damage * this ratio

COLD_SLOW_MULT     = 0.55  # speed multiplier per cold stack (stacks multiplicatively)
COLD_FREEZE_STACKS = 3     # cold stacks needed to freeze
COLD_STACK_DURATION = 4.0  # seconds before cold stacks expire

FROZEN_DURATION    = 2.0   # seconds a frozen enemy stays frozen

# Rot: a fixed total of damage dealt evenly over a fixed duration. A new rot
# application only overwrites an existing one if its total is higher - rot
# never stacks. Rot damage ignores armor and resistances entirely.
ROT_DURATION    = 6.0    # seconds over which the full rot total is dealt
ROT_TOTAL_RATIO = 0.50   # rot_total = hit_damage * this ratio

# (skeleton_level, accuracy) keyframes - calibrated for the accuracy-vs-evasion
# roll: chance = accuracy / (accuracy + evasion). Each value is solved from
# accuracy = target_chance / (1 - target_chance) * player_evasion using the
# actual base player evasion at that level (~300 at lvl1, ~600 at lvl100;
# Dexterity and gear push it higher, which lowers the enemy hit chance).
_ACCURACY_CURVE = [
    (1,   300),
    (3,   332),
    (5,   367),
    (8,   409),
    (15,  513),
    (30,  719),
    (50,  950),
    (70,  1183),
    (85,  1419),
    (100, 1791),
]

def skeleton_accuracy(level: int) -> int:
    """Return skeleton accuracy for the given character level via linear interpolation."""
    level = max(1, min(100, level))
    for i in range(len(_ACCURACY_CURVE) - 1):
        l0, a0 = _ACCURACY_CURVE[i]
        l1, a1 = _ACCURACY_CURVE[i + 1]
        if l0 <= level <= l1:
            t = (level - l0) / (l1 - l0)
            return int(a0 + t * (a1 - a0))
    return _ACCURACY_CURVE[-1][1]


def hit_chance(attacker_accuracy, defender_evasion):
    """Accuracy-vs-evasion to-hit percentage, clamped to 5-95%.

    Every point of accuracy pushes the roll toward the ceiling and every point
    of evasion pushes it toward the floor; neither side can ever be fully
    shut out."""
    if attacker_accuracy <= 0:
        return HIT_CHANCE_MIN
    rating  = float(attacker_accuracy)
    defense = float(max(1, defender_evasion))
    return max(HIT_CHANCE_MIN, min(HIT_CHANCE_MAX, rating / (rating + defense)))


def evaluate_hit(defender, attacker_accuracy):
    """Per-swing to-hit roll (D.E.S.C.E.N.D. style).

    Each attack is an independent roll against the defender's evasion (its
    analogue of Defense). No entropy pool - a miss is a miss, a hit is a hit,
    exactly like Diablo 2's per-swing attack rating check. The defender's
    entropy_grace_pct (Destiny/Essence-driven) acts as a straight dodge
    multiplier on the final chance."""
    chance = hit_chance(attacker_accuracy, defender.get('evasion', 0))
    grace  = min(0.30, max(0.0, defender.get('entropy_grace_pct', 0.0)))
    if grace > 0.0:
        chance = chance * (1.0 - grace)
    return random.random() < chance


def resolve_attack(attacker_accuracy, defender, base_damage, crit_chance=CRIT_CHANCE,
                   crushing_blow_chance=0.0, double_strike=False):
    """Resolve a melee attack into one or two damaging strikes.

    A double strike performs one to-hit roll, then rolls critical strike
    independently for each half-damage strike. This trades one reliable hit
    for two opportunities to crit, proc, and overcome mitigation.
    """
    if not evaluate_hit(defender, attacker_accuracy):
        return {'damage': 0, 'evaded': True, 'crit': False, 'crushing': False,
                'strikes': []}

    strike_count = 2 if double_strike else 1
    raw = [base_damage // strike_count + (1 if i < base_damage % strike_count else 0)
           for i in range(strike_count)]
    crits = [random.random() < crit_chance for _ in range(strike_count)]
    strikes = [int(value * (CRIT_MULT if crit else 1.0))
               for value, crit in zip(raw, crits)]
    damage = sum(strikes)

    is_crushing = random.random() < crushing_blow_chance
    if is_crushing:
        damage += int(defender.get('health', 0) * CRUSHING_BLOW_PCT)

    return {'damage': damage, 'evaded': False, 'crit': any(crits),
            'crushing': is_crushing, 'strikes': strikes}


def apply_health_damage(stats, amount, second_wind=False, cooldown_remaining=0.0):
    """Apply damage to health, optionally consuming a lethal-save effect.

    Returns True when the lethal save consumed the hit. A consumed save leaves
    the player at 50% of maximum health; a save on cooldown does nothing.
    """
    if amount >= stats.get('health', 0.0) and second_wind and cooldown_remaining <= 0.0:
        stats['health'] = stats.get('max_health', 0.0) * 0.5
        return True
    stats['health'] = max(0.0, stats.get('health', 0.0) - amount)
    return False


def apply_status_to_enemy(enemy, dmg_type, damage):
    """Apply a type-specific status effect to an enemy dict. Mutates enemy in place."""
    if dmg_type == 'fire':
        # Refresh burning; use the higher DPS of the current burn vs. this hit.
        new_dps = damage * BURNING_DPS_RATIO
        enemy['burning_dps']   = max(enemy.get('burning_dps', 0.0), new_dps)
        enemy['burning_timer'] = BURNING_DURATION

    elif dmg_type == 'cold':
        stacks = min(enemy.get('cold_stacks', 0) + 1, COLD_FREEZE_STACKS)
        enemy['cold_stacks'] = stacks
        enemy['cold_timer']  = COLD_STACK_DURATION
        if stacks >= COLD_FREEZE_STACKS and enemy.get('frozen_timer', 0.0) <= 0.0:
            enemy['frozen_timer'] = FROZEN_DURATION
            enemy['cold_stacks']  = 0  # consume stacks on freeze

    elif dmg_type == 'rot':
        # Fixed total over fixed duration; a new application only overwrites
        # an existing infection if its total is higher. Rot never stacks.
        new_total = damage * ROT_TOTAL_RATIO
        if new_total > enemy.get('rot_total', 0.0):
            enemy['rot_total'] = new_total
            enemy['rot_dps']   = new_total / ROT_DURATION
        enemy['rot_timer'] = ROT_DURATION


def spread_rot(target, rot_total):
    """Copy a rot infection from one enemy to another (rot spread). Follows the
    same no-stack rule: only overwrites if the incoming total is higher."""
    if rot_total <= 0.0:
        return
    if rot_total > target.get('rot_total', 0.0):
        target['rot_total'] = rot_total
        target['rot_dps']   = rot_total / ROT_DURATION
    target['rot_timer'] = ROT_DURATION


def tick_enemy_statuses(enemy, dt):
    """Advance all status timers for one enemy.
    Returns (fire_dot, rot_dot) damage to deal this tick. Rot damage ignores
    armor and resistances - apply it directly to health."""
    fire_dot_damage = 0.0
    rot_dot_damage  = 0.0

    # Burning DoT
    if enemy.get('burning_timer', 0.0) > 0.0:
        fire_dot_damage          = enemy.get('burning_dps', 0.0) * dt
        enemy['burning_timer']  -= dt
        if enemy['burning_timer'] <= 0.0:
            enemy['burning_timer'] = 0.0
            enemy['burning_dps']   = 0.0

    # Freeze (takes priority over cold slow)
    if enemy.get('frozen_timer', 0.0) > 0.0:
        enemy['frozen_timer'] -= dt
        if enemy['frozen_timer'] <= 0.0:
            enemy['frozen_timer'] = 0.0

    # Cold stacks expiry (only when not frozen)
    elif enemy.get('cold_timer', 0.0) > 0.0:
        enemy['cold_timer'] -= dt
        if enemy['cold_timer'] <= 0.0:
            enemy['cold_timer']  = 0.0
            enemy['cold_stacks'] = 0

    # Rot DoT - fixed total drains away over the duration, then clears
    if enemy.get('rot_timer', 0.0) > 0.0:
        rot_dot_damage = enemy.get('rot_dps', 0.0) * dt
        enemy['rot_timer'] -= dt
        if enemy['rot_timer'] <= 0.0:
            enemy['rot_timer'] = 0.0
            enemy['rot_total'] = 0.0
            enemy['rot_dps']   = 0.0

    return fire_dot_damage, rot_dot_damage
