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

def create_stats(max_health=50, evasion=53,
                 accuracy=0, melee_dmg_mult=1.0, max_energy_shield=0):
    return {
        'health':             float(max_health),
        'max_health':         float(max_health),
        'evasion':            int(evasion),
        'accuracy':           int(accuracy),
        'melee_dmg_mult':     float(melee_dmg_mult),
        'energy_shield':      float(max_energy_shield),
        'max_energy_shield':  float(max_energy_shield),
    }


def update_stats(s, dt, moving=False):
    speed_mult = 1.0 + s.get('_move_speed_pct', 0.0)

    return {
        'speed_mult': speed_mult,
    }


def reset_stats(s, max_health=50, evasion=53,
                accuracy=0, melee_dmg_mult=1.0, max_energy_shield=0,
                move_speed_pct=0.0, dexterity=0,
                attack_speed_pct=0.0, cooldown_recovery_pct=0.0,
                crit_chance=0.0, ability_crit_chance=0.0,
                max_health_pct=0.0, **_):
    """Rebuild the derived stat block IN PLACE.

    Owner ruling 2026-10-07: the current POOLS (health / energy shield)
    are PRESERVED and only clamped to the new maxima — a stat recalc
    (gear swap, identify, hub arrival, delve resume) must never refill
    you. The level-up-era full refill is gone; the only full refills live
    at character creation (empty dict → defaults) and a fresh delve start
    (explicit, see delve_flow._enter_delve). Mana was retired from the
    game (owner ruling 2026-10-29); old saves carrying ``mana`` /
    ``max_mana`` keys load fine — they are simply ignored.
    """
    prev_health   = s.get('health')
    prev_es       = s.get('energy_shield')
    s.clear()
    s.update(create_stats(max_health, evasion,
                          accuracy, melee_dmg_mult, max_energy_shield))
    s['_base_max_health'] = float(max_health)
    max_health_pct = float(max_health_pct)
    if max_health_pct:
        s['max_health'] = max(1.0, s['max_health'] * (1.0 + max_health_pct / 100.0))
    s['_base_evasion']    = int(evasion)
    s['_base_accuracy']   = int(accuracy)
    s['_base_melee_dmg_mult'] = float(melee_dmg_mult)
    s['_move_speed_pct']  = float(move_speed_pct)
    s['_dexterity']       = int(dexterity)
    s['_attack_speed_pct'] = float(attack_speed_pct)
    s['_cooldown_recovery_pct'] = float(cooldown_recovery_pct)
    s['_crit_chance']     = float(crit_chance)
    s['_ability_crit_chance'] = float(ability_crit_chance)
    # Store the remaining derived-stat keys (damage_pct, penetration_pct,
    # resist_pct, entropy_grace_pct, delve_light_radius, and the attribute
    # totals) so the live game code can read them off stats.
    s.update(_)
    # Restore the pools LAST (so nothing in the derived dump can clobber
    # them), clamped to the rebuilt maxima.
    if prev_health is not None:
        s['health'] = min(float(prev_health), s['max_health'])
    if prev_es is not None:
        s['energy_shield'] = min(float(prev_es),
                                 float(s.get('max_energy_shield', 0.0)))
