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
Flask system — the T-slot flask (issue #73 ADDITION, Phase A scope).

A single flask is equipped in inventory['flask_slot'] and drunk with T.
Fresh implementation (commit cc7b03b removed the old potion-belt code) with
ONE-USE-PER-WAVE semantics (owner's tuning rule):

  - The flask has exactly ONE charge. Drinking it consumes that charge;
    it cannot be used again mid-wave (empty charges block the drink).
  - Charges RESET TO 1 when the next delve wave/encounter begins — the
    reset is tied to the wave lifecycle hook (_delve_spawn_wave), NOT a
    plain timer and NOT the earlier "refill at checkpoints" idea.
  - Effects are duration-based (regen over time / timed haste), gated by a
    short shared drink cooldown so a wave's single sip still plays out.

Kinds: health (life regen), mana (mana regen), utility (timed haste).
"""

FLASK_CD = 2.0          # shared drink cooldown, seconds
WAVE_CHARGES = 1        # owner's tuning rule: exactly one use per wave
REGEN_DURATION = 3.0    # s over which a regen flask is drunk
REGEN_FRACTION = 0.40   # fraction of the pool restored over the duration
UTILITY_DURATION = 4.0  # s of haste from the utility flask
UTILITY_MULT = 1.35

FLASK_KINDS = ('health', 'mana', 'utility')

FLASK_ITEM_FOR_KIND = {
    'health':  'flask_health',
    'mana':    'flask_mana',
    'utility': 'flask_utility',
}


def is_flask(item_id):
    return isinstance(item_id, str) and item_id.startswith('flask_')


def kind_of(item_id):
    return item_id[len('flask_'):] if is_flask(item_id) else None


def equipped_flask(inventory):
    """Return the equipped flask entry, or None."""
    if not isinstance(inventory, dict):
        return None
    entry = inventory.get('flask_slot')
    if entry and is_flask(entry.get('item', '')):
        return entry
    return None


def charges_of(entry):
    import systems.items as items
    defn = items.ITEMS.get(entry.get('item', ''), {})
    defn_charges = defn.get('charges', WAVE_CHARGES)
    return int(entry.get('charges', defn_charges)), int(defn_charges)


def reset_for_wave(inventory):
    """Owner's tuning rule: reset the equipped flask to its single
    wave charge when a new delve wave/encounter begins."""
    flask = equipped_flask(inventory)
    if not flask:
        return
    flask['charges'] = WAVE_CHARGES


# Backwards-compatible alias for the earlier checkpoint-refill naming.
refill = reset_for_wave


def refill_inventory(inventory):
    reset_for_wave(inventory)


def use_flask(inventory, state, stats=None):
    """Drink the equipped flask. Mutates: spends a charge, sets the drink
    cooldown in `state` and appends active effect dicts to `state['flask_effects']`.

    Returns a short result string ('health'/'mana'/'utility') or None when the
    drink was blocked (no flask / empty charges / on cooldown)."""
    entry = equipped_flask(inventory)
    if not entry:
        return None
    if state.get('_flask_cd', 0.0) > 0.0:
        return None
    charges, _max = charges_of(entry)
    if charges <= 0:
        return None
    entry['charges'] = charges - 1
    state['_flask_cd'] = FLASK_CD

    kind = kind_of(entry['item'])
    effects = state.setdefault('flask_effects', [])
    if kind == 'health':
        max_hp = float((stats or {}).get('max_health', 100))
        effects.append({'stat': 'health', 'amount': max_hp * REGEN_FRACTION,
                        'duration': REGEN_DURATION, 'elapsed': 0.0})
    elif kind == 'mana':
        max_mp = float((stats or {}).get('max_mana', 100))
        effects.append({'stat': 'mana', 'amount': max_mp * REGEN_FRACTION,
                        'duration': REGEN_DURATION, 'elapsed': 0.0})
    else:
        effects.append({'haste': UTILITY_MULT, 'duration': UTILITY_DURATION,
                        'elapsed': 0.0})
    return kind


def tick_flask_effects(state, stats, dt):
    """Advance active flask effects. Applies regen to `stats`, computes the
    haste multiplier. Returns the current flask haste multiplier (1.0 = none)."""
    effects = state.get('flask_effects')
    haste = 1.0
    if not effects:
        return haste
    alive = []
    for eff in effects:
        eff['elapsed'] += dt
        if eff['elapsed'] >= eff['duration']:
            continue   # effect finished
        frac = dt / eff['duration']
        if 'stat' in eff:
            stat = eff['stat']
            cap = stats.get('max_' + stat, 100.0)
            stats[stat] = min(cap, stats.get(stat, 0.0) + eff['amount'] * frac)
        else:
            haste = max(haste, eff['haste'])
        alive.append(eff)
    state['flask_effects'] = alive
    return haste
