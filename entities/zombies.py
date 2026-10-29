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

import math
import random
from systems.combat import evaluate_hit, apply_status_to_enemy, spread_rot, tick_enemy_statuses, COLD_SLOW_MULT
from core.iso_engine import is_walkable
from systems import frames

# Enemy chase speeds ride the same tile-scale compensation as the player's
# MOVE_SPEED (native desert tiles are ~2.7x smaller on screen than the old
# LoP canvas) so the chase feel matches the pre-swap pacing.
ZOMBIE_SPEED = 0.6
DETECT_RANGE   = 22.0       # tiles — enemies acquire the player inside this radius
HIT_DAMAGE     = 10
MAX_HEALTH     = 100
IDLE_FPS       = 4
WALK_FPS       = 3
FRAME_COUNT    = 8
DEATH_FPS      = 3
DEATH_FRAMES   = 8
MELEE_RANGE    = 0.22
MELEE_DAMAGE   = 20
ATTACK_CD      = 1.1
ATTACK_FPS     = 10
ATTACK_FRAMES  = 8

SLIME_SPEED     = 0.22
SLIME_HEALTH    = 150
SLIME_DAMAGE    = 12
SLIME_ATTACK_CD = 10

# Gunslinger knockback decay — a shove dies out over this window (mirror of
# KNOCKBACK_DECAY_TIME in core/game.py; kept local to avoid a core import
# cycle — the impulse magnitude and the timer length live there).
KNOCKBACK_DECAY_TIME = 0.25
KNOCKBACK_STOP_TPS   = 0.3   # residual speed below which the slide ends

# D2-style quantized attack cooldowns: legacy wall-clock cooldowns
# authored as D2 frame counts (seconds × 25 Hz), snapped to whole 30 Hz ticks.
ZOMBIE_BASE_ATTACK_FRAMES = frames.D2_HZ * ATTACK_CD        # 27.5 D2 frames
SLIME_BASE_ATTACK_FRAMES  = frames.D2_HZ * SLIME_ATTACK_CD  # 250 D2 frames
ZOMBIE_ATTACK_CD_S  = frames.attack_seconds(ZOMBIE_BASE_ATTACK_FRAMES)
SLIME_ATTACK_CD_S   = frames.attack_seconds(SLIME_BASE_ATTACK_FRAMES)

# ── Movement feel ──────────────────────────────────────────────────────
# Enemies surround the player instead of stacking into a single pile, ramp up
# to full speed rather than snapping into motion, give up the chase and walk
# home once the player escapes, and slide along walls instead of sticking.
SEPARATION_RADIUS   = 0.45   # tiles — enemies repel each other inside this radius
SEPARATION_STRENGTH = 0.55   # how strongly repulsion blends into pursuit
SPEED_RAMP_TIME     = 0.35   # seconds to accelerate from standstill to full speed
MOVE_SPEED_VARIANCE = 0.15   # per-enemy speed variance (± this fraction)

# ── Range invariant (QoL #111 / issue #15) ──────────────────────────────
# An enemy may only deal damage while inside MELEE_RANGE, and MELEE_RANGE must
# never exceed the range at which it acquires the chase (DETECT_RANGE). If this
# were violated, a slime could hit the player from farther away than it starts
# chasing — i.e. damage the player before it is actually aggro'd. Both the
# chase->attack transition and the damage check use the same MELEE_RANGE, so the
# attack range can never exceed the chase-acquire range.
assert MELEE_RANGE <= DETECT_RANGE, "attack range must not exceed chase-acquire range"

# Rot spread: every this many seconds, rot ticks outward from infected enemies.
_ROT_SPREAD_INTERVAL = 2.0
_ROT_SPREAD_RADIUS   = 1.5

_next_id = 0
_rot_spread_timer = 0.0


def default_status_fields():
    """Return a fresh dict of all status effect fields for a newly spawned enemy."""
    return {
        'burning_timer': 0.0,
        'burning_dps':   0.0,
        'cold_stacks':   0,
        'cold_timer':    0.0,
        'frozen_timer':  0.0,
        'rot_total':     0.0,
        'rot_dps':       0.0,
        'rot_timer':     0.0,
        # Mitigation — overridden per-spawn with level-scaled values by the
        # game's enemy-spawn helpers. Defaults are zero (level-1 one-shot).
        'damage_reduction': 0.0,
        'hit_flash':       0.0,
        'resist_pct': {
            'fire': 0.0, 'cold': 0.0, 'lightning': 0.0, 'physical': 0.0,
            'magic': 0.0, 'rot': 0.0, 'darkness': 0.0,
        },
        # Gunslinger knockback — shove velocity along the shot line, decaying
        # over KNOCKBACK_DECAY_TIME. `knockback_immune` enemies ignore it
        # entirely (bosses/elites can flip the flag later; nobody does at launch).
        'kb_x':             0.0,
        'kb_y':             0.0,
        'kb_timer':         0.0,
        'knockback_immune': False,
    }


def enemy_evasion(enemy_type, level):
    """Defensive rating the player's accuracy rolls against, scaling with depth
    so the accuracy-vs-evasion roll stays meaningful at every level."""
    base = 20 if enemy_type == 'slime' else 15
    return int(base * (1.0 + max(1, int(level)) / 10.0))


def make_move_speed(enemy_type):
    """Per-enemy speed with slight variance so groups don't march in lockstep."""
    base = SLIME_SPEED if enemy_type == 'slime' else ZOMBIE_SPEED
    return base * random.uniform(1.0 - MOVE_SPEED_VARIANCE, 1.0 + MOVE_SPEED_VARIANCE)


def _step_enemy(z, dir_x, dir_y, move_dist, map_data):
    """Advance one enemy by move_dist along the unit vector (dir_x, dir_y).

    Slides along walls: if the direct step is blocked, try each axis
    separately so enemies glide around obstacles instead of sticking to them.
    Returns True if the enemy moved."""
    step_x = dir_x * move_dist
    step_y = dir_y * move_dist
    new_x  = z['x'] + step_x
    new_y  = z['y'] + step_y
    if is_walkable(map_data, int(new_x), int(new_y)):
        z['x'], z['y'] = new_x, new_y
        return True
    if is_walkable(map_data, int(z['x'] + step_x), int(z['y'])):
        z['x'] += step_x
        return True
    if is_walkable(map_data, int(z['x']), int(z['y'] + step_y)):
        z['y'] += step_y
        return True
    return False


def _separation_vector(z, alive_zombies):
    """Repulsion away from nearby enemies. Blended into pursuit so groups fan
    out and surround the player instead of stacking into a single pile."""
    sep_x = 0.0
    sep_y = 0.0
    for other in alive_zombies:
        if other is z:
            continue
        off_x = z['x'] - other['x']
        off_y = z['y'] - other['y']
        dist_sq = off_x * off_x + off_y * off_y
        if dist_sq <= 1e-9 or dist_sq >= SEPARATION_RADIUS * SEPARATION_RADIUS:
            continue
        dist = math.sqrt(dist_sq)
        push = (SEPARATION_RADIUS - dist) / SEPARATION_RADIUS
        sep_x += (off_x / dist) * push
        sep_y += (off_y / dist) * push
    return sep_x, sep_y


def init_zombies(map_data):
    """Scan map for tile 9, replace with floor 0, return zombie list."""
    global _next_id
    zombies = []
    for x in range(len(map_data)):
        for y in range(len(map_data[x])):
            if map_data[x][y] == 9:
                map_data[x][y] = 0
                zombies.append({
                    'id':               f'z{_next_id}',
                    'x':                x + 0.5,
                    'y':                y + 0.5,
                    'health':           MAX_HEALTH,
                    'max_health':       MAX_HEALTH,
                    'state':            'idle',
                    'anim_timer':       0.0,
                    'frame':            0,
                    'facing_x':         1.0,
                    'facing_y':         0.0,
                    'accuracy':         100,
                    'evasion':          enemy_evasion('skeleton', 1),
                    'spawn_x':          x + 0.5,
                    'spawn_y':          y + 0.5,
                    'move_speed':       make_move_speed('skeleton'),
                    'speed_ramp':       0.0,
                    'dmg_type':         'physical',
                    **default_status_fields(),
                })
                _next_id += 1
    return zombies


def _has_los(map_data, x0, y0, x1, y1):
    dx, dy = x1 - x0, y1 - y0
    dist = math.hypot(dx, dy)
    steps = max(1, int(dist / 0.1))
    for i in range(1, steps):
        t = i / steps
        mx = int(x0 + dx * t)
        my = int(y0 + dy * t)
        if mx < 0 or my < 0 or mx >= len(map_data) or my >= len(map_data[0]):
            return False
        tile = map_data[mx][my]
        if tile != 0:
            return False
    return True


def _delve_damage_mult(level: int) -> float:
    """Scale enemy damage by level so deeper delve enemies hit harder."""
    return max(0.5, level / 2.0)


def update_zombies(dt, zombies, players, map_data):
    """
    players: list of dicts with 'x', 'y'.  players[0] is local.
    Returns a dict of typed damage to apply to the local player:
      {'physical': float, 'rot': float}
    """
    global _rot_spread_timer
    incoming_damage = {}  # keyed by dmg_type, accumulated per frame

    # ── Rot spread tick ───────────────────────────────────────────────
    _rot_spread_timer += dt
    do_rot_spread = _rot_spread_timer >= _ROT_SPREAD_INTERVAL
    if do_rot_spread:
        _rot_spread_timer = 0.0

    alive_zombies = [z for z in zombies if z['health'] > 0]

    if do_rot_spread:
        for z in alive_zombies:
            if z.get('rot_timer', 0.0) <= 0.0:
                continue
            for other in alive_zombies:
                if other is z:
                    continue
                # Rot-type enemies are immune to rot spread
                if other.get('dmg_type') == 'rot':
                    continue
                if math.hypot(other['x'] - z['x'], other['y'] - z['y']) <= _ROT_SPREAD_RADIUS:
                    spread_rot(other, z.get('rot_total', 0.0))

    for z in zombies:
        if z['health'] <= 0:
            if not z.get('death_done'):
                z['state'] = 'dead'
                z['death_anim_timer'] = z.get('death_anim_timer', 0.0) + dt
                z['frame'] = min(DEATH_FRAMES - 1, int(z['death_anim_timer'] * DEATH_FPS))
                if z['death_anim_timer'] * DEATH_FPS >= DEATH_FRAMES:
                    z['death_done'] = True
            continue

        # ── Status effect ticks ───────────────────────────────────────
        fire_dot, rot_dot = tick_enemy_statuses(z, dt)
        if fire_dot > 0.0:
            z['health'] = max(0.0, z['health'] - fire_dot)
        # Rot damage ignores armor and resistances — drain straight from health.
        if rot_dot > 0.0:
            z['health'] = max(0.0, z['health'] - rot_dot)
        if z['health'] <= 0:
            continue

        is_frozen = z.get('frozen_timer', 0.0) > 0.0
        cold_stacks = z.get('cold_stacks', 0)

        # ── Hit flash decay (white tint when damaged) ─────────────────
        hf = z.get('hit_flash', 0.0)
        if hf > 0.0:
            z['hit_flash'] = max(0.0, hf - dt * 2.0)

        # ── Gunslinger knockback slide (frozen enemies don't budge) ───
        # Runs before the state machines: shoving works out of chase AND
        # attack (the victim gets pushed out of MELEE_RANGE and re-chases)
        # and never flips the enemy's facing.
        if not is_frozen and z.get('kb_timer', 0.0) > 0.0:
            kb_speed = math.hypot(z['kb_x'], z['kb_y'])
            if kb_speed > KNOCKBACK_STOP_TPS:
                _step_enemy(z, z['kb_x'] / kb_speed, z['kb_y'] / kb_speed,
                            kb_speed * dt, map_data)
                decay = math.exp(-dt / KNOCKBACK_DECAY_TIME)
                z['kb_x'] *= decay
                z['kb_y'] *= decay
            else:
                z['kb_x'] = z['kb_y'] = 0.0
            if z['kb_x'] == 0.0 and z['kb_y'] == 0.0:
                z['kb_timer'] = 0.0
            else:
                z['kb_timer'] = max(0.0, z['kb_timer'] - dt)

        enemy_dmg_type = z.get('dmg_type', 'physical')

        if z['state'] == 'attack':
            if z.get('enemy_type') == 'slime':
                z['attack_anim_timer'] = z.get('attack_anim_timer', 0.0) + dt
                z['attack_cd'] = z.get('attack_cd', 0.0) - dt
                if z['attack_cd'] <= 0:
                    z['attack_cd'] = SLIME_ATTACK_CD_S
                    p = players[0]
                    if math.hypot(p['x'] - z['x'], p['y'] - z['y']) <= MELEE_RANGE:
                        if evaluate_hit(p, z.get('accuracy', 80)):
                            lvl = z.get('level', 1)
                            incoming_damage[enemy_dmg_type] = (
                                incoming_damage.get(enemy_dmg_type, 0.0) + SLIME_DAMAGE * _delve_damage_mult(lvl))
                if math.hypot(players[0]['x'] - z['x'], players[0]['y'] - z['y']) > MELEE_RANGE:
                    z['state'] = 'chase'
                    z['attack_anim_timer'] = 0.0
            else:
                z['attack_anim_timer'] = z.get('attack_anim_timer', 0.0) + dt
                z['frame'] = min(ATTACK_FRAMES - 1, int(z['attack_anim_timer'] * ATTACK_FPS))
                hit_register_time = (ATTACK_FRAMES / ATTACK_FPS) * 0.75
                if z.get('hit_pending') and z['attack_anim_timer'] >= hit_register_time:
                    p = players[0]
                    hit_dist = math.hypot(p['x'] - z['x'], p['y'] - z['y'])
                    if hit_dist <= MELEE_RANGE and evaluate_hit(p, z.get('accuracy', 100)):
                        lvl = z.get('level', 1)
                        incoming_damage[enemy_dmg_type] = (
                            incoming_damage.get(enemy_dmg_type, 0.0) + MELEE_DAMAGE * _delve_damage_mult(lvl))
                    z['hit_pending'] = False
                if z['attack_anim_timer'] * ATTACK_FPS >= ATTACK_FRAMES:
                    z['state'] = 'chase'
                    z['attack_anim_timer'] = 0.0
                    z['hit_pending'] = False
            continue

        # ── Frozen enemies cannot move or attack ─────────────────────
        if is_frozen:
            z['state'] = 'idle'
            z['anim_timer'] += dt
            z['frame'] = int(z['anim_timer'] * IDLE_FPS) % FRAME_COUNT
            continue

        # Find nearest player
        nearest_dist = float('inf')
        target = None
        for p in players:
            d = math.hypot(p['x'] - z['x'], p['y'] - z['y'])
            if d < nearest_dist:
                nearest_dist = d
                target = p

        if target is not None and nearest_dist <= DETECT_RANGE:
            z['state'] = 'chase'
            # Keep closing until well inside attack reach — the stop distance
            # must stay strictly below MELEE_RANGE or the enemy halts just
            # outside it and never enters 'attack' (regression guard).
            if nearest_dist > MELEE_RANGE * 0.6:
                # Blend pursuit with separation so enemies fan out and
                # surround the player instead of stacking into one pile.
                pursuit_x = (target['x'] - z['x']) / nearest_dist
                pursuit_y = (target['y'] - z['y']) / nearest_dist
                sep_x, sep_y = _separation_vector(z, alive_zombies)
                move_x = pursuit_x + sep_x * SEPARATION_STRENGTH
                move_y = pursuit_y + sep_y * SEPARATION_STRENGTH
                norm = math.hypot(move_x, move_y)
                if norm > 1e-6:
                    move_x /= norm
                    move_y /= norm
                    base_speed = z.get('move_speed') or (
                        SLIME_SPEED if z.get('enemy_type') == 'slime' else ZOMBIE_SPEED)
                    # Cold slows stack multiplicatively up to freeze threshold
                    speed_mult = COLD_SLOW_MULT ** cold_stacks if cold_stacks > 0 else 1.0
                    # Smooth acceleration from standstill to full speed
                    z['speed_ramp'] = min(1.0, z.get('speed_ramp', 1.0) + dt / SPEED_RAMP_TIME)
                    move_dist = base_speed * speed_mult * z['speed_ramp'] * dt
                    if _step_enemy(z, move_x, move_y, move_dist, map_data):
                        z['facing_x'] = move_x
                        z['facing_y'] = move_y

            if target is players[0] and nearest_dist < MELEE_RANGE:
                z['attack_cd'] = z.get('attack_cd', 0.0) - dt
                if z['attack_cd'] <= 0:
                    z['attack_cd'] = ZOMBIE_ATTACK_CD_S
                    z['state'] = 'attack'
                    z['attack_anim_timer'] = 0.0
                    z['frame'] = 0
                    z['hit_pending'] = True
                    z['speed_ramp'] = 0.0

        elif z.get('spawn_x') is not None:
            # Player escaped the detect radius: give up the chase and walk
            # home. Re-aggro happens automatically next frame if the player
            # steps back inside DETECT_RANGE.
            home_dx = z['spawn_x'] - z['x']
            home_dy = z['spawn_y'] - z['y']
            home_dist = math.hypot(home_dx, home_dy)
            if home_dist > 0.25:
                z['state'] = 'return'
                base_speed = z.get('move_speed') or (
                    SLIME_SPEED if z.get('enemy_type') == 'slime' else ZOMBIE_SPEED)
                z['speed_ramp'] = min(1.0, z.get('speed_ramp', 1.0) + dt / SPEED_RAMP_TIME)
                move_dist = base_speed * z['speed_ramp'] * dt
                if _step_enemy(z, home_dx / home_dist, home_dy / home_dist,
                               move_dist, map_data):
                    z['facing_x'] = home_dx / home_dist
                    z['facing_y'] = home_dy / home_dist
            else:
                z['state'] = 'idle'
                z['speed_ramp'] = 0.0
        else:
            z['state'] = 'idle'

        z['anim_timer'] += dt
        fps = WALK_FPS if z['state'] in ('chase', 'return') else IDLE_FPS
        z['frame'] = int(z['anim_timer'] * fps) % FRAME_COUNT

    return incoming_damage



