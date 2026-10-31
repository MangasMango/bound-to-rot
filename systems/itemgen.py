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
Item instance generator - Borderlands-style volatile affix rolls.

Static base stats live in items.ITEMS. This module produces a per-instance
`instance_data` dict (rarity, display_name, ilvl, affixes) that rides on the
inventory / grid slot WITHOUT mutating the static ITEMS database.

    FinalStat = BaseValue * (1 + ilvl/100) * M_rarity * V_rand

All generation functions accept an optional `seed` parameter. When provided,
every random roll becomes deterministic and reproducible from that seed.
"""

import random
import copy
from systems.items import ITEMS

# ── Rarity intensity multipliers ──────────────────────────────────────
M_RARITY = {
    'common':    1.00,
    'uncommon':  1.15,
    'rare':      1.35,
    'epic':      1.60,
    'legendary': 2.00,
    'mythic':    2.50,
}

RARITY_ORDER = ['common', 'uncommon', 'rare', 'epic', 'legendary', 'mythic']

# (prefix_count, suffix_min, suffix_max). Epic rolls 1-2 suffixes -> 3-4 total.
_AFFIX_RULES = {
    'common':    (0, 1, 1),
    'uncommon':  (0, 1, 1),
    'rare':      (1, 1, 1),
    'epic':      (2, 1, 2),
    'legendary': (2, 2, 2),   # + 1 unique red-text mod
    'mythic':    (2, 2, 2),   # + 1 unique red-text mod (King of Pikes upgrade path)
}

V_RAND_MIN = 0.75
V_RAND_MAX = 1.25


def _rng(seed=None):
    """Return a random-compatible RNG. With a seed, returns a deterministic Random."""
    return random.Random(seed) if seed is not None else random


def _v_rand(rng=None):
    rng = rng or random
    return rng.uniform(V_RAND_MIN, V_RAND_MAX)


# ── Affix pool ────────────────────────────────────────────────────────
# kind  : 'prefix' | 'suffix'
# slots : set of equipSlot names it can roll on, or None for any
# base  : base value before scaling
# round : 'int' | 1 | 2   (decimal places)
# pct   : True if value is a 0..1 ratio displayed as a percentage
# word  : adjective (prefix) / 'of ...' phrase (suffix) used in the name
# label : tooltip line, {v} substituted
_AFFIXES = [
    # ── prefixes ──
    {'id': 'flat_max_health',             'kind': 'prefix', 'slots': None,
     'base': 30,   'round': 'int', 'pct': False, 'word': 'Stalwart',
     'label': '+{v} Maximum Life'},
    {'id': 'local_damage_reduction',      'kind': 'prefix', 'slots': {'liver', 'lungs'},
     'base': 0.06, 'round': 2, 'pct': True,  'word': 'Plated',
     'label': '+{v}% Damage Reduction'},
    {'id': 'flat_armor',                  'kind': 'prefix', 'slots': {'liver', 'lungs'},
     'base': 20,   'round': 'int', 'pct': False, 'word': 'Reinforced',
     'label': '+{v} Armour'},
    {'id': 'percent_max_health',          'kind': 'prefix', 'slots': {'liver', 'heart'},
     'base': 0.05, 'round': 2, 'pct': True,  'word': 'Vigorous',
     'label': '+{v}% Maximum Life'},
    {'id': 'flat_melee_damage',           'kind': 'prefix', 'slots': {'intestine', 'kidney', 'heart'},
     'base': 5,    'round': 'int', 'pct': False, 'word': 'Savage',
     'label': '+{v} Melee Damage'},
    {'id': 'percent_attack_speed',        'kind': 'prefix', 'slots': {'lungs', 'heart'},
     'base': 0.08, 'round': 2, 'pct': True,  'word': 'Frenzied',
     'label': '+{v}% Attack Speed'},
    {'id': 'ability_crit_chance',         'kind': 'prefix', 'slots': {'heart', 'intestine', 'kidney'},
     'base': 0.03, 'round': 2, 'pct': True,  'word': 'Arcane',
     'label': '+{v}% Ability Critical Strike'},

    # ── suffixes ──
    {'id': 'percent_move_speed',          'kind': 'suffix', 'slots': None,
     'base': 0.05, 'round': 2, 'pct': True,  'word': 'of Swiftness',
     'label': '+{v}% Movement Speed'},
    {'id': 'crit_chance',                 'kind': 'suffix', 'slots': {'lungs', 'liver', 'intestine'},
     'base': 0.03, 'round': 2, 'pct': True,  'word': 'of Precision',
     'label': '+{v}% Critical Strike'},
    {'id': 'flat_evasion',                'kind': 'suffix', 'slots': {'lungs', 'liver'},
     'base': 25,   'round': 'int', 'pct': False, 'word': 'of Evasion',
     'label': '+{v} Evasion Rating'},

    # ── attribute suffixes (push a D.E.S.C.E.N.D. attribute beyond its
    #    point-allocation hardcap; consumed by compute_derived_stats._attr) ──
    {'id': 'attr_dexterity',  'kind': 'suffix', 'slots': None, 'base': 2, 'round': 'int', 'pct': False, 'word': 'of Dexterity',  'label': '+{v} Dexterity'},
    {'id': 'attr_endurance',  'kind': 'suffix', 'slots': None, 'base': 2, 'round': 'int', 'pct': False, 'word': 'of Endurance',  'label': '+{v} Endurance'},
    {'id': 'attr_strength',   'kind': 'suffix', 'slots': None, 'base': 2, 'round': 'int', 'pct': False, 'word': 'of Strength',   'label': '+{v} Strength'},
    {'id': 'attr_cunning',    'kind': 'suffix', 'slots': None, 'base': 2, 'round': 'int', 'pct': False, 'word': 'of Cunning',    'label': '+{v} Cunning'},
    {'id': 'attr_essence',    'kind': 'suffix', 'slots': None, 'base': 2, 'round': 'int', 'pct': False, 'word': 'of Essence',    'label': '+{v} Essence'},
    {'id': 'attr_nerve',      'kind': 'suffix', 'slots': None, 'base': 2, 'round': 'int', 'pct': False, 'word': 'of Nerve',      'label': '+{v} Nerve'},
    {'id': 'attr_destiny',   'kind': 'suffix', 'slots': None, 'base': 2, 'round': 'int', 'pct': False, 'word': 'of Destiny',    'label': '+{v} Destiny'},
]

# ── perk-style affixes ──────────────────────────────────────────────────
# These mirror the 28 DESCEND_PERKS templates (entities/descend.py). Each
# carries a `perk` key naming the DESCEND perk-bonus key it feeds
# (e.g. 'fire_damage_pct'); values are expressed in the SAME units the
# perk bonuses use (percentage points for *_pct keys, flat for *_flat).
#
# They are aggregated into compute_perk_bonuses() - the BLUEPRINT §6
# "passives come from items" aggregation point - so equipped gear can grant
# every one of the 28 perk effects. They are deliberately kept OUT of
# LIVE_EFFECT_MAP so they are NOT double-applied by the legacy per-frame
# _equipped_bonuses() path (which handles the classic affixes such as
# move speed / evasion / crit).
_PERK_AFFIXES = [
    # Energy shield / resistance
    {'id': 'pk_max_es',          'kind': 'prefix', 'slots': {'liver', 'heart', 'intestine'},
     'base': 4, 'round': 'int', 'pct': False, 'word': 'Shielded',
     'label': '+{v} Maximum Energy Shield', 'perk': 'max_energy_shield'},
    {'id': 'pk_dark_resist',     'kind': 'prefix', 'slots': {'liver', 'heart'},
     'base': 5, 'round': 'int', 'pct': True,  'word': 'Umbral',
     'label': '+{v}% Darkness Resistance', 'perk': 'darkness_resist_pct'},

    # Damage types (%)
    {'id': 'pk_phys_dmg',        'kind': 'prefix', 'slots': {'intestine', 'kidney', 'heart'},
     'base': 4, 'round': 'int', 'pct': True,  'word': 'Brutal',
     'label': '+{v}% Physical Damage', 'perk': 'physical_damage_pct'},
    {'id': 'pk_magic_dmg',       'kind': 'prefix', 'slots': {'intestine', 'kidney', 'heart'},
     'base': 4, 'round': 'int', 'pct': True,  'word': 'Arcanic',
     'label': '+{v}% Magic Damage', 'perk': 'magic_damage_pct'},
    {'id': 'pk_fire_dmg',        'kind': 'prefix', 'slots': {'intestine', 'kidney', 'heart'},
     'base': 4, 'round': 'int', 'pct': True,  'word': 'Searing',
     'label': '+{v}% Fire Damage', 'perk': 'fire_damage_pct'},
    {'id': 'pk_cold_dmg',        'kind': 'prefix', 'slots': {'intestine', 'kidney', 'heart'},
     'base': 4, 'round': 'int', 'pct': True,  'word': 'Frozen',
     'label': '+{v}% Cold Damage', 'perk': 'cold_damage_pct'},
    {'id': 'pk_light_dmg',       'kind': 'prefix', 'slots': {'intestine', 'kidney', 'heart'},
     'base': 4, 'round': 'int', 'pct': True,  'word': 'Stormbound',
     'label': '+{v}% Lightning Damage', 'perk': 'lightning_damage_pct'},
    {'id': 'pk_rot_dmg',         'kind': 'prefix', 'slots': {'intestine', 'kidney', 'heart'},
     'base': 4, 'round': 'int', 'pct': True,  'word': 'Blighted',
     'label': '+{v}% Rot Damage', 'perk': 'rot_damage_pct'},

    # Penetration (%)
    {'id': 'pk_phys_pen',        'kind': 'suffix', 'slots': {'intestine', 'kidney', 'heart'},
     'base': 3, 'round': 'int', 'pct': True,  'word': 'of Piercing',
     'label': '+{v}% Physical Penetration', 'perk': 'physical_penetration_pct'},
    {'id': 'pk_fire_pen',        'kind': 'suffix', 'slots': {'intestine', 'kidney', 'heart'},
     'base': 3, 'round': 'int', 'pct': True,  'word': 'of Ignition',
     'label': '+{v}% Fire Penetration', 'perk': 'fire_penetration_pct'},
    {'id': 'pk_cold_pen',        'kind': 'suffix', 'slots': {'intestine', 'kidney', 'heart'},
     'base': 3, 'round': 'int', 'pct': True,  'word': 'of Glaciation',
     'label': '+{v}% Cold Penetration', 'perk': 'cold_penetration_pct'},

    # Melee multiplier / accuracy / delve light
    {'id': 'pk_melee_mult',      'kind': 'prefix', 'slots': {'intestine', 'kidney', 'heart'},
     'base': 4, 'round': 'int', 'pct': True,  'word': 'Savage',
     'label': '+{v}% Melee Damage', 'perk': 'melee_dmg_mult_pct'},
    {'id': 'pk_accuracy',        'kind': 'suffix', 'slots': {'lungs', 'liver', 'intestine'},
     'base': 8, 'round': 'int', 'pct': False, 'word': 'of Precision',
     'label': '+{v} Accuracy', 'perk': 'accuracy_flat'},
    {'id': 'pk_delve_light',     'kind': 'suffix', 'slots': {'lungs', 'liver'},
     'base': 0.5, 'round': 1, 'pct': False, 'word': 'of Luminance',
     'label': '+{v} Anima Light Radius', 'perk': 'delve_light_radius'},

    # Entropy grace
    {'id': 'pk_entropy_grace',   'kind': 'suffix', 'slots': {'heart', 'intestine'},
     'base': 4, 'round': 'int', 'pct': True,  'word': 'of Fate',
     'label': '+{v}% Entropy Grace', 'perk': 'entropy_grace_pct'},
]

_AFFIXES = _AFFIXES + _PERK_AFFIXES
_AFFIX_BY_ID = {a['id']: a for a in _AFFIXES}
_PREFIXES = [a for a in _AFFIXES if a['kind'] == 'prefix']
_SUFFIXES = [a for a in _AFFIXES if a['kind'] == 'suffix']

# ── organ rot drawback suffixes (BLUEPRINT §22) ─────────────────────────
# Rolled ONLY by make_rotten() when an organ hits 100% rot - never part of
# the normal generation pools (_PREFIXES/_SUFFIXES above). Values are stored
# NEGATIVE so live_effect_totals / aggregate_item_bonuses subtract them; the
# label carries the minus and affix_lines() renders abs().
_ROT_DRAWBACKS = [
    {'id': 'rot_drawback_max_life',     'kind': 'suffix', 'slots': None,
     'base': 25,   'round': 'int', 'pct': False, 'word': 'of Withered Flesh',
     'label': '-{v} Maximum Life'},
    {'id': 'rot_drawback_move_speed',   'kind': 'suffix', 'slots': None,
     'base': 0.04, 'round': 2,     'pct': True,  'word': 'of Stagnation',
     'label': '-{v}% Movement Speed'},
    {'id': 'rot_drawback_evasion',      'kind': 'suffix', 'slots': None,
     'base': 25,   'round': 'int', 'pct': False, 'word': 'of Clumsiness',
     'label': '-{v} Evasion Rating'},
    {'id': 'rot_drawback_attack_speed', 'kind': 'suffix', 'slots': None,
     'base': 0.05, 'round': 2,     'pct': True,  'word': 'of Torpor',
     'label': '-{v}% Attack Speed'},
    {'id': 'rot_drawback_crit',         'kind': 'suffix', 'slots': None,
     'base': 0.02, 'round': 2,     'pct': True,  'word': 'of Blindness',
     'label': '-{v}% Critical Strike'},
]
_ROT_DRAWBACK_BY_ID = {a['id']: a for a in _ROT_DRAWBACKS}
# Registered for tooltip lookup / stat aggregation, but deliberately NOT
# appended to _AFFIXES (so generation, roll_for and Ace of Clubs never roll them).
_AFFIX_BY_ID.update(_ROT_DRAWBACK_BY_ID)

# Legendary behaviour-altering "red-text" mods. Static halves are aggregated
# with perk bonuses; dynamic halves are consumed by the combat pipeline.
_UNIQUES = [
    {'id': 'bang_bang', 'title': 'BANG BANG',
     'text': 'Melee attacks strike twice, dealing half damage per strike.'},
    {'id': 'glass_cannon', 'title': 'GLASS CANNON',
     'text': '+60% damage dealt. Your maximum life is halved.'},
    {'id': 'vampiric', 'title': 'VAMPIRIC',
     'text': 'Melee hits heal you for 10% of the damage dealt.'},
    {'id': 'juggernaut', 'title': 'JUGGERNAUT',
     'text': 'Immune to slows and stuns. -15% movement speed.'},
    {'id': 'second_wind', 'title': 'SECOND WIND',
     'text': 'Survive a lethal hit at 50% life. 60s cooldown.'},
]

# The depth-gated rot-set mythic (BLUEPRINT §27). Deliberately NOT in
# _UNIQUES - normal legendary/mythic rolls never pick it; only
# try_rot_mythic() (2% on organ drops at depth 1-10) grants it.
ROT_MYTHIC_UNIQUE = {
    'id': 'rot_eternal', 'title': 'ROT ETERNAL',
    'text': 'While every organ is rotten, their rot drawbacks are ignored. +10% damage.',
}
ROT_MYTHIC_DROP_CHANCE = 0.02
ROT_MYTHIC_DEPTH_MAX = 10

# Affix ids that map to a live player effect today. Everything else is
# display-only until its stat hook exists.
LIVE_EFFECT_MAP = {
    'local_damage_reduction': 'damage_reduction',
    'percent_move_speed':     'move_speed',
    'flat_max_health':         'max_health',
    'percent_max_health':      'max_health_pct',
    'flat_evasion':            'evasion',
    'flat_melee_damage':       'melee_damage',
    'percent_attack_speed':    'attack_speed_pct',
    'crit_chance':             'crit_chance',
    'ability_crit_chance':     'ability_crit_chance',
    # attribute suffixes -> D.E.S.C.E.N.D. attribute names (consumed by
    # compute_derived_stats._attr so items push beyond the point cap)
    'attr_dexterity':          'dexterity',
    'attr_endurance':          'endurance',
    'attr_strength':           'strength',
    'attr_cunning':            'cunning',
    'attr_essence':            'essence',
    'attr_nerve':              'nerve',
    'attr_destiny':            'destiny',
    # rot drawback suffixes - stored NEGATIVE, so the summed effect subtracts
    'rot_drawback_max_life':      'max_health',
    'rot_drawback_move_speed':    'move_speed',
    'rot_drawback_evasion':       'evasion',
    'rot_drawback_attack_speed':  'attack_speed_pct',
    'rot_drawback_crit':          'crit_chance',
}


# ── generation ────────────────────────────────────────────────────────

def _affixes_for_slot(pool, equip_slot):
    return [a for a in pool if a['slots'] is None or equip_slot in a['slots']]


def _round_val(value, mode):
    return int(round(value)) if mode == 'int' else round(value, mode)


def _scale(base, ilvl, rarity, rng=None):
    return base * (1 + ilvl / 100.0) * M_RARITY[rarity] * _v_rand(rng)


def roll_rarity(ilvl, rng=None):
    """Weighted rarity choice; higher ilvl skews rarer."""
    rng = rng or random
    weights = {
        'common':    max(4.0, 60.0 - ilvl * 0.5),
        'uncommon':  30.0,
        'rare':      10.0 + ilvl * 0.25,
        'epic':      3.0 + ilvl * 0.18,
        'legendary': 0.3 + ilvl * 0.05,
        'mythic':    0.05 + ilvl * 0.01,
    }
    roll = rng.uniform(0, sum(weights.values()))
    acc = 0.0
    for r in RARITY_ORDER:
        acc += weights[r]
        if roll <= acc:
            return r
    return 'common'


def generate_instance(item_id, ilvl, rarity=None, equip_slot=None, base_name=None, seed=None):
    """Return an `instance_data` dict for an equippable base item.

    When `seed` is provided, all random rolls are deterministic from that seed.
    """
    rng = _rng(seed)
    if rarity is None:
        rarity = roll_rarity(ilvl, rng)
    n_pre, suf_min, suf_max = _AFFIX_RULES[rarity]
    n_suf = rng.randint(suf_min, suf_max)

    chosen_pre = rng.sample(_affixes_for_slot(_PREFIXES, equip_slot),
                            k=min(n_pre, len(_affixes_for_slot(_PREFIXES, equip_slot))))
    chosen_suf = rng.sample(_affixes_for_slot(_SUFFIXES, equip_slot),
                            k=min(n_suf, len(_affixes_for_slot(_SUFFIXES, equip_slot))))

    prefixes = {a['id']: _round_val(_scale(a['base'], ilvl, rarity, rng), a['round'])
                for a in chosen_pre}
    suffixes = {a['id']: _round_val(_scale(a['base'], ilvl, rarity, rng), a['round'])
                for a in chosen_suf}

    name = base_name or ITEMS.get(item_id, {}).get('name', item_id)
    if chosen_pre:
        name = ' '.join(a['word'] for a in chosen_pre) + ' ' + name
    if chosen_suf:
        name = name + ' ' + ' '.join(a['word'] for a in chosen_suf)

    inst = {
        'rarity':       rarity,
        'display_name': name,
        'ilvl':         int(ilvl),
        # Issue #73 DESIGN PIVOT: ALL items drop unidentified - rolled stats
        # are hidden (and inert) until The Joker identifies the item. Legacy
        # instances without the key stay identified via is_identified().
        'identified':   False,
        'affixes':      {'prefixes': prefixes, 'suffixes': suffixes},
    }
    if rarity in ('legendary', 'mythic'):
        inst['unique'] = rng.choice(_UNIQUES)
    return inst


# ── identification (issue #73 DESIGN PIVOT) ───────────────────────────

def is_identified(entry):
    """True when an inventory slot's rolled stats are revealed/inert-off.

    Items without instance data (consumables, currency) are always identified.
    Current-format gear instances carry the flag explicitly."""
    if not isinstance(entry, dict):
        return True
    inst = entry.get('instance_data')
    if not isinstance(inst, dict):
        return True
    return bool(inst.get('identified', False))


def identify(entry):
    """Mark an item's instance identified (The Joker). Mutates in-place."""
    inst = entry.get('instance_data') if isinstance(entry, dict) else None
    if isinstance(inst, dict):
        inst['identified'] = True
    return entry


# ── organ rot (BLUEPRINT §22) ───────────────────────────────────────────
#
# Organs are the only equipment; instead of durability they ROT. Every
# successful wave the carried organs gain a flat chunk (ROT_PER_WAVE).
# At ROT_MAX the organ becomes ROTTEN (single state, no tiers): all rolled
# affixes are buffed by ROTTEN_STAT_MULT, one random drawback suffix is
# added, and the display name gets the "ROTTEN " prefix. A full snapshot
# (rot_prev) is kept so Queen of Hearts can fully revert the organ.

ROT_MAX = 100.0
ROT_PER_WAVE = 20.0
ROTTEN_STAT_MULT = 1.25
ROTTEN_NAME_PREFIX = 'ROTTEN '


def rot_of(inst):
    """Current rot percent (0..100) of an instance dict. Legacy instances
    without the key are at 0."""
    if not isinstance(inst, dict):
        return 0.0
    try:
        return float(inst.get('rot', 0.0))
    except (TypeError, ValueError):
        return 0.0


def is_rotten(inst):
    """True once the organ has hit 100% rot (ROTTEN state)."""
    return isinstance(inst, dict) and bool(inst.get('rotten'))


def apply_rotten_buff(aff):
    """Multiply every non-drawback affix value by ROTTEN_STAT_MULT.

    Mutates in place. Drawback suffixes keep their rolled magnitude - the
    rot buff applies to the organ's own stats, never to the drawback.
    Rounding is half-up (not banker's) so a "+2" really becomes "+3" and
    every stat visibly gains from rotting."""
    for group in ('prefixes', 'suffixes'):
        for affix_id, value in list(aff.get(group, {}).items()):
            if affix_id in _ROT_DRAWBACK_BY_ID:
                continue
            defn = _AFFIX_BY_ID.get(affix_id)
            scaled = value * ROTTEN_STAT_MULT
            mode = defn['round'] if defn else 2
            if mode == 'int':
                aff[group][affix_id] = int(scaled + 0.5)
            else:
                factor = 10 ** mode
                aff[group][affix_id] = int(scaled * factor + 0.5 + 1e-9) / factor


def make_rotten(inst, rng=None):
    """Flip an organ instance into the ROTTEN state: buff every rolled
    stat (+), roll one drawback suffix, prefix the display name.

    Mutates in place; idempotent (returns False when already rotten)."""
    if not isinstance(inst, dict) or inst.get('rotten'):
        return False
    rng = rng or random
    aff = inst.get('affixes')
    if not isinstance(aff, dict):
        aff = {'prefixes': {}, 'suffixes': {}}
        inst['affixes'] = aff
    # Full-revert snapshot for the Queen of Hearts cleanse (taken BEFORE the buff).
    inst['rot_prev'] = {'affixes': copy.deepcopy(aff),
                        'display_name': inst.get('display_name', '')}
    apply_rotten_buff(aff)
    choice = rng.choice(_ROT_DRAWBACKS)
    rolled = _scale(choice['base'], inst.get('ilvl', 1),
                    inst.get('rarity', 'common'), rng)
    aff.setdefault('suffixes', {})[choice['id']] = -_round_val(rolled, choice['round'])
    inst['rotten'] = True
    inst['rot'] = ROT_MAX
    name = inst.get('display_name', '')
    if not name.startswith(ROTTEN_NAME_PREFIX):
        inst['display_name'] = ROTTEN_NAME_PREFIX + name
    return True


def add_rot(entry):
    """Add one wave's flat rot chunk to an inventory entry.

    Only organ items (equipSlot) rot; gems, cards and flasks never do.
    Returns True only when this gain transitions the organ to ROTTEN."""
    if not isinstance(entry, dict):
        return False
    inst = entry.get('instance_data')
    if not isinstance(inst, dict):
        return False
    if not ITEMS.get(entry.get('item', ''), {}).get('equipSlot'):
        return False                      # only organs rot
    if not is_identified(entry):
        return False                      # unidentified: inert (§22) - no rot
    if inst.get('rotten'):
        return False                      # meter pinned at 100% once rotten
    rot = min(ROT_MAX, rot_of(inst) + ROT_PER_WAVE)
    inst['rot'] = rot
    if rot >= ROT_MAX:
        return make_rotten(inst)
    return False


def cleanse_rot(entry):
    """Queen of Hearts: FULL revert - rot to 0, drawback suffix removed, ROTTEN
    stat bonuses reverted, original name restored. Returns True when the
    entry carried any rot (i.e. the card application was meaningful)."""
    if not isinstance(entry, dict):
        return False
    inst = entry.get('instance_data')
    if not isinstance(inst, dict):
        return False
    # (no `or` short-circuit here - both keys must be popped unconditionally)
    had_rot = bool(inst.pop('rot', 0.0))
    had_rotten = bool(inst.pop('rotten', False))
    had_rot = had_rot or had_rotten
    prev = inst.pop('rot_prev', None)
    if isinstance(prev, dict):
        if isinstance(prev.get('affixes'), dict):
            inst['affixes'] = prev['affixes']
        if prev.get('display_name'):
            inst['display_name'] = prev['display_name']
    name = inst.get('display_name', '')
    if name.startswith(ROTTEN_NAME_PREFIX):   # legacy rotten without snapshot
        inst['display_name'] = name[len(ROTTEN_NAME_PREFIX):]
    return had_rot


def apply_wave_rot(inventory):
    """End-of-wave rot: every organ carried (equipped + backpack) gains
    ROT_PER_WAVE. Stash and ground items never rot.

    Returns the number of EQUIPPED organs that turned ROTTEN this call -
    callers recalc derived stats when the result is > 0 (only a rotten
    transform changes live affix values)."""
    if not isinstance(inventory, dict):
        return 0
    newly_rotten = 0
    for entry in (inventory.get('equipped') or {}).values():
        if add_rot(entry):
            newly_rotten += 1
    for entry in (inventory.get('grid') or []):
        add_rot(entry)
    return newly_rotten


def max_rot(inventory):
    """WORST-organ rot percent (0..100) across the equipped loadout.

    HUD organ-rot meter binding (owner ruling 2026-10-10): the bar shows the
    organ closest to the ROTTEN state, not an average - the danger state is
    per-organ (add_rot / make_rotten), so the worst organ is the one that
    needs the Queen of Hearts card. Follows the same guards as add_rot: only
    identified organs with a real equipSlot can contribute; backpack and
    stash items never show on the meter. Empty / malformed inventories
    return 0.0 (a fresh character's meter reads empty, never a crash)."""
    if not isinstance(inventory, dict):
        return 0.0
    worst = 0.0
    for entry in (inventory.get('equipped') or {}).values():
        if not isinstance(entry, dict):
            continue
        inst = entry.get('instance_data')
        if not isinstance(inst, dict):
            continue
        if not ITEMS.get(entry.get('item', ''), {}).get('equipSlot'):
            continue
        if not is_identified(entry):
            continue
        if is_rotten(inst):
            return ROT_MAX
        worst = max(worst, rot_of(inst))
    return worst


def rot_set_active(inventory):
    """ROT ETERNAL set condition (§27): EVERY organ slot holds an identified,
    ROTTEN organ. Callers check the unique itself separately via
    equipped_uniques. Unidentified organs can never contribute (they don't
    rot), so a blind loadout can never activate the set."""
    if not isinstance(inventory, dict):
        return False
    equipped = inventory.get('equipped') or {}
    if not equipped:
        return False
    for entry in equipped.values():
        if not entry or not is_identified(entry):
            return False
        inst = entry.get('instance_data')
        if not inst or not is_rotten(inst):
            return False
    return True


def try_rot_mythic(slot, depth, rng=None):
    """Depth 1-10 (§27): any ORGAN drop has a small chance to come out as
    the ROT ETERNAL mythic unique. Mutates the slot's instance in place and
    returns True when it fired; gems/flasks/out-of-range depths never fire."""
    rng = rng or random
    if not isinstance(slot, dict) or not (1 <= depth <= ROT_MYTHIC_DEPTH_MAX):
        return False
    defn = ITEMS.get(slot.get('item', ''), {})
    inst = slot.get('instance_data')
    if not defn.get('equipSlot') or not isinstance(inst, dict):
        return False
    if rng.random() >= ROT_MYTHIC_DROP_CHANCE:
        return False
    fresh = generate_instance(
        slot['item'], inst.get('ilvl', 1), rarity='mythic',
        equip_slot=defn.get('equipSlot'),
        base_name=defn.get('name', slot['item']))
    # generate_instance rolls a random unique at mythic - force ours
    fresh['unique'] = dict(ROT_MYTHIC_UNIQUE)
    slot['instance_data'] = fresh
    return True


def balanced_affix_values(inst):
    """Ace of Clubs: recompute every rolled affix at the exact "fair" value -
    V_rand collapses to 1.0 so each stat sits at the balanced midpoint of
    its numeric range. Returns {affix_id: value} (does not mutate)."""
    out = {}
    ilvl = inst.get('ilvl', 1)
    rarity = inst.get('rarity', 'common')
    aff = inst.get('affixes', {})
    for group in ('prefixes', 'suffixes'):
        for aid in aff.get(group, {}):
            a = _AFFIX_BY_ID.get(aid)
            if a:
                fair = a['base'] * (1 + ilvl / 100.0) * M_RARITY[rarity]
                val = _round_val(fair, a['round'])
                # rot drawbacks balance to a negative midpoint too
                if aid in _ROT_DRAWBACK_BY_ID:
                    val = -val
                out[aid] = val
    return out


def roll_for(item_id, count, ilvl, seed=None):
    """Build a loot/grid slot dict, attaching instance_data to equippables.

    Abilities are generated only for gems; ordinary gear never grants a
    skill or a legacy hotkey-bound ability.

    When `seed` is provided, item generation is deterministic from that seed.
    """
    defn = ITEMS.get(item_id, {})
    slot = {'item': item_id, 'count': count}
    eq = defn.get('equipSlot')
    if eq:
        inst = generate_instance(
            item_id, ilvl, equip_slot=eq, base_name=defn.get('name', item_id), seed=seed)
        slot['instance_data'] = inst
        return slot
    # Gems: roll an ability for the QWER key slot the gem color binds to.
    if defn.get('isGem'):
        import systems.gems as _gems
        slot_key = defn['isGem']
        rng = _rng(seed)
        rarity = rng.choice(_gems.GEM_RARITIES)
        ability = _gems.random_ability_for_gem_slot(slot_key, rng)
        slot['instance_data'] = {
            'rarity':       rarity,
            'display_name': (ability or 'Gem').replace('_', ' ').title(),
            'ilvl':         int(ilvl),
            'identified':   True,   # gems are always identified
            'ability':      ability,
        }
    # Flasks: initialize wave charges (issue #73 ADDITION; 1 use per wave)
    if defn.get('isFlask'):
        slot['charges'] = int(defn.get('charges', 1))
    return slot


# ── consumption helpers ───────────────────────────────────────────────

def affix_lines(instance_data):
    """Human-readable tooltip lines for an instance's affixes.

    Values are rendered as absolute numbers - the label itself carries the
    sign (rot drawback suffixes are stored negative with a '-{v}' label)."""
    lines = []
    aff = instance_data.get('affixes', {})
    for group in ('prefixes', 'suffixes'):
        for aid, val in aff.get(group, {}).items():
            a = _AFFIX_BY_ID.get(aid)
            if not a:
                continue
            v = f"{abs(val) * 100:.0f}" if a['pct'] else f"{abs(val):g}"
            lines.append(a['label'].format(v=v))
    return lines


def live_effect_totals(instance_data, include_drawbacks=True):
    """Sum affixes that map to live player effects -> {effect: value}.

    include_drawbacks=False drops the rot drawback suffixes - the ROT
    ETERNAL set condition nullifies them (§27)."""
    out = {}
    aff = instance_data.get('affixes', {})
    for group in ('prefixes', 'suffixes'):
        for aid, val in aff.get(group, {}).items():
            if not include_drawbacks and aid in _ROT_DRAWBACK_BY_ID:
                continue
            eff = LIVE_EFFECT_MAP.get(aid)
            if eff:
                out[eff] = out.get(eff, 0.0) + val
    return out



# ── item comparison (QoL #20 / issue #6) ─────────────────────────────────
#
# Display metadata for every comparable live-effect stat key. Stored as
# (label, is_pct) where pct stats live as 0..1 ratios (e.g. 0.04 -> "+4%").
STAT_META = {
    'damage_reduction':       ('Damage Reduction', True),
    'move_speed':             ('Move Speed', True),
    'max_health':             ('Max Health', False),
    'max_health_pct':         ('Max Health %', True),
    'evasion':                ('Evasion', False),
    'melee_damage':           ('Melee Damage', False),
    'attack_speed_pct':       ('Attack Speed', True),
    'cooldown_recovery_pct':  ('Cooldown Recovery', True),
    'crit_chance':            ('Critical Strike', True),
    'ability_crit_chance':    ('Ability Crit', True),
    'dexterity':              ('Dexterity', False),
    'endurance':              ('Endurance', False),
    'strength':               ('Strength', False),
    'cunning':                ('Cunning', False),
    'essence':                ('Essence', False),
    'nerve':                  ('Nerve', False),
    'destiny':                ('Destiny', False),
}


def compute_item_stat_totals(slot):
    """Aggregate every comparable stat of an inventory slot.

    Combines the base item's implicit `equip` stats with the live-effect
    totals of its rolled affixes. Returns {stat_key: value}; empty when the
    slot is None or carries no comparable stats.

    An UNIDENTIFIED item exposes no stats at all - neither its rolled affixes
    nor its base implicits - so tooltips, comparison rows and stat lists can
    simply test the result for emptiness.
    """
    totals = {}
    if not slot:
        return totals
    inst = slot.get('instance_data')
    if inst is not None and not is_identified(slot):
        return totals
    defn = ITEMS.get(slot.get('item', ''), {})
    for k, v in (defn.get('equip') or {}).items():
        totals[k] = totals.get(k, 0.0) + v
    if inst:
        for k, v in live_effect_totals(inst).items():
            totals[k] = totals.get(k, 0.0) + v
    return totals


def format_stat_total(key, value):
    """Format a single aggregated stat value for display (pct vs flat)."""
    meta = STAT_META.get(key)
    if meta:
        label, is_pct = meta
    else:
        label, is_pct = key.replace('_', ' ').title(), False
    if is_pct:
        return f"+{int(round(value * 100))}% {label}"
    return f"+{int(round(value))} {label}"


def comparison_rows(hover_slot, equip_slot):
    """Build comparison rows between a hovered item and the equipped item.

    Returns a list of (text, sign) tuples where sign is +1 (upgrade),
    -1 (downgrade) or 0 (no change). Text is the hovered item's stat line
    only (e.g. "+33 Max Health", "-4% Ability Crit") - no "(up)"/"(down)"/
    "(eq ...)" words: callers colour the row by sign and draw an arrow icon
    after it (sign 0 = no arrow). ASCII-only text for the project's font."""
    if (isinstance(hover_slot, dict) and hover_slot.get('instance_data')
            and not is_identified(hover_slot)):
        return []      # unidentified items expose no stat text at all
    h_t = compute_item_stat_totals(hover_slot)
    e_t = compute_item_stat_totals(equip_slot)
    rows = []
    for key in STAT_META:
        h = h_t.get(key, 0.0)
        e = e_t.get(key, 0.0)
        if h == 0 and e == 0:
            continue
        sign = 1 if h > e else (-1 if h < e else 0)
        rows.append((format_stat_total(key, h), sign))
    return rows


def equipped_item_levels(inventory):
    """Item levels of every equipped item that carries an instance.

    Unidentified gear is included: item level is a depth-derived drop property,
    not a rolled stat, and character_level() is a gear-comparison readout.
    """
    levels = []
    if not isinstance(inventory, dict):
        return levels
    for entry in (inventory.get('equipped') or {}).values():
        if not isinstance(entry, dict):
            continue
        inst = entry.get('instance_data')
        if not isinstance(inst, dict):
            continue
        ilvl = inst.get('ilvl')
        if isinstance(ilvl, (int, float)):
            levels.append(int(ilvl))
    return levels


def character_level(inventory):
    """CHARACTER LEVEL - the average item level of the character's gear.

    THE SINGLE SOURCE OF TRUTH for this value. Both display sites (the
    inventory panel header and the top-left HUD readout) call this one
    function, so they can never disagree.

    Rounding: ROUNDED to the nearest integer, halves rounding UP
    (i.e. floor(x + 0.5)), applied here once so both sites agree. Returns 0
    when nothing is equipped - no division by zero on an empty loadout.

    SCOPE: DISPLAY-ONLY, pending an owner decision. This value is rendered
    and nothing else. It is deliberately NOT an input to loot generation,
    item-level rolling, compute_derived_stats, monster scaling, access
    gating or difficulty. A previous character level did feed those systems;
    restoring that behaviour is a separate decision the owner has not made
    yet, so keep this wired to drawing code only until they do.
    """
    levels = equipped_item_levels(inventory)
    if not levels:
        return 0
    return int(sum(levels) / float(len(levels)) + 0.5)


def format_character_level(inventory):
    """The exact string both display sites render (shared formatting).

    Compact form: ``LVL 21``. Owner rule - the long "CHARACTER LEVEL" phrase
    is never drawn; both sites render this one string verbatim, so the compact
    label cannot drift between them.

    Owner rule (revision): an EMPTY loadout displays ``LVL 0``, exactly like any
    other value. There is no placeholder and no special case - the label is
    always ``LVL`` followed by the number.
    """
    return f'LVL {character_level(inventory)}'


def equipped_uniques(inventory):
    """Return the set of identified legendary unique ids currently equipped."""
    found = set()
    if not isinstance(inventory, dict):
        return found
    for entry in (inventory.get('equipped') or {}).values():
        if not isinstance(entry, dict) or not is_identified(entry):
            continue
        unique = (entry.get('instance_data') or {}).get('unique') or {}
        if unique.get('id'):
            found.add(unique['id'])
    return found


def aggregate_item_bonuses(inventory):
    """Aggregate item-sourced affixes that map to DESCEND perk-bonus keys.

    Returns a dict keyed by the same bonus keys consumed by
    ``compute_derived_stats`` / ``compute_perk_bonuses`` (e.g.
    ``'fire_damage_pct'``, ``'max_energy_shield'``). Only affixes carrying a
    ``perk`` field (the DESCEND_PERKS-style affixes) are included - the
    classic affixes applied directly by ``_equipped_bonuses()`` are excluded
    so they are not double-counted.

    This is the "passives come from items" wiring required by BLUEPRINT §6:
    the totals returned here are folded into ``compute_perk_bonuses`` so
    equipped gear grants the 28 DESCEND perk effects.
    """
    out = {}
    uniques = equipped_uniques(inventory)
    if 'glass_cannon' in uniques:
        for damage_type in ('physical', 'magic', 'lightning', 'cold', 'fire', 'rot'):
            out[f'{damage_type}_damage_pct'] = out.get(f'{damage_type}_damage_pct', 0) + 60
        out['max_health_pct'] = out.get('max_health_pct', 0) - 50
    if 'juggernaut' in uniques:
        out['move_speed_pct'] = out.get('move_speed_pct', 0) - 15
    if 'rot_eternal' in uniques and rot_set_active(inventory):
        # ROT ETERNAL set: +10% damage of every type (§27)
        for damage_type in ('physical', 'magic', 'lightning', 'cold', 'fire', 'rot'):
            out[f'{damage_type}_damage_pct'] = out.get(f'{damage_type}_damage_pct', 0) + 10
    if not isinstance(inventory, dict):
        return out
    equipped = inventory.get('equipped') or {}
    for entry in equipped.values():
        if not isinstance(entry, dict) or not is_identified(entry):
            continue
        inst = entry.get('instance_data')
        if not inst:
            continue
        aff = inst.get('affixes', {})
        for group in ('prefixes', 'suffixes'):
            for aid, val in aff.get(group, {}).items():
                pk = _AFFIX_BY_ID.get(aid, {}).get('perk')
                if pk:
                    out[pk] = out.get(pk, 0) + val
    return out
