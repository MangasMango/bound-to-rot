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

"""Vessel attributes and legacy perk definitions; progression is item-driven."""

# ── Vessel definitions ───────────────────────────────────────────────────

LOOKS_OPTIONS = ['knight', 'warrior', 'fighter']
LOOKS_LABELS = {'knight': 'Knight Vessel', 'warrior': 'Warrior Vessel', 'fighter': 'Fighter Vessel'}

# Only the knight (Pyrrhian) is playable; the rest stay behind this flag
# until their western-fantasy redesigns ship.
WIP_VESSELS = {'warrior', 'fighter'}

VESSEL_DEFS = {
    'knight': {
        'name': 'Pyrrhian',
        'passive': '5% entropy grace',
        'effects': {'entropy_grace_pct': 5},
    },
    'warrior': {
        'name': 'Myronian',
        'passive': '5% darkness resistance',
        'effects': {'darkness_resist_pct': 5},
    },
    'fighter': {
        'name': 'Theran',
        'passive': '5% fire resistance',
        'effects': {'fire_resist_pct': 5},
    },
}

# Fixed vessel baselines. Item bonuses drive effectiveness.
VESSEL_BASELINE_STATS = {
    'knight':  {'dexterity': 2, 'essence': 1},
    'warrior': {'endurance': 2, 'strength': 1},
    'fighter': {'strength': 1, 'endurance': 1, 'dexterity': 1},
}


def vessel_baseline_stats(looks: str) -> dict:
    """Return a complete fixed attribute baseline for a new vessel."""
    baseline = {a: 0 for a in DESCEND_ATTRIBUTES}
    baseline.update(VESSEL_BASELINE_STATS.get(looks, VESSEL_BASELINE_STATS['knight']))
    return baseline

# Vessel unlock data — framed as piercing the Veils of the Anima.  A depth of 0
# means the vessel is available from the start.  Unlocks are account-wide and
# persist once earned; the account's best depth is tracked to show progress.
VESSEL_UNLOCKS = {
    'knight': {
        'depth': 0,
        'veil': None,
        'requirement': 'Available from the start',
        'flavor': "Born at the light's edge, where fate bends first.",
    },
    'warrior': {
        'depth': 10,
        'veil': 'First Veil',
        'requirement': 'Pierce the First Veil — reach Depth 10',
        'flavor': "Those who held the dark at arm's length.",
    },
    'fighter': {
        'depth': 20,
        'veil': 'Second Veil',
        'requirement': 'Walk the Second Veil — reach Depth 20',
        'flavor': 'Forged where the deep burns.',
    },
}

DESCEND_ATTRIBUTES = ('dexterity', 'endurance', 'strength', 'cunning', 'essence', 'nerve', 'destiny')
ATTR_SHORT =    ('DEX', 'END', 'STR', 'CUN', 'ESS', 'NRV', 'DST')
ATTR_LABEL = {
    'dexterity': 'Dexterity',
    'endurance': 'Endurance',
    'strength':  'Strength',
    'cunning':   'Cunning',
    'essence':   'Essence',
    'nerve':     'Nerve',
    'destiny':   'Destiny',
}
ATTR_CAP = 10

# ── 28 Perk definitions ─────────────────────────────────────────────────

def _perk(name, desc, max_ranks, effects_fn, attr, threshold):
    return {
        'name': name,
        'description': desc,
        'max_ranks': max_ranks,
        'effects_fn': effects_fn,
        'attribute': attr,
        'threshold': threshold,
    }


def _ef(*pairs):
    """Build an effects_fn that returns a dict of {key: value per rank}."""
    d = dict(pairs)
    return lambda rank: {k: d.get(k, 0) * rank for k in d}


DESCEND_PERKS: dict[str, dict] = {
    # ── Dexterity column ────────────────────────────────────────────────
    'dex1': _perk('Fleet Footed',  '+move & attack speed % per rank',      3, _ef(('move_speed_pct', 2), ('attack_speed_pct', 2)), 'dexterity', 1),
    'dex2': _perk('Quick Reflexes','+evasion per rank',                     3, _ef(('evasion_flat', 8)),        'dexterity', 2),
    'dex3': _perk('Shadow Step',   '+move & attack speed %, +evasion per rank', 3, _ef(('move_speed_pct', 1), ('evasion_flat', 5), ('attack_speed_pct', 1)), 'dexterity', 3),
    'dex4': _perk('Phase Walker',  '+evasion, -energy shield at rank 3',    3, _ef(('evasion_flat', 10), ('max_energy_shield', -6)), 'dexterity', 4),

    # ── Endurance column ────────────────────────────────────────────────
    'end1': _perk('Toughness',       '+max HP per rank',                    3, _ef(('maxHealth', 4)),            'endurance', 1),
    'end2': _perk('Arcane Ward',     '+energy shield per rank',             3, _ef(('max_energy_shield', 3)),    'endurance', 2),
    'end3': _perk('Shadow Cloak',    '+darkness resist % per rank',         3, _ef(('darkness_resist_pct', 5)),  'endurance', 3),
    'end4': _perk('Stone Skin',      '+max HP, +energy shield per rank',    3, _ef(('maxHealth', 3), ('max_energy_shield', 2)), 'endurance', 4),

    # ── Strength column ─────────────────────────────────────────────────
    'str1': _perk('Iron Body',       '+max HP per rank',                    3, _ef(('maxHealth', 4)),            'strength', 1),
    'str2': _perk('Heavy Hitter',    '+melee damage % per rank',            3, _ef(('melee_dmg_mult_pct', 3)),   'strength', 2),
    'str3': _perk('Brute Force',     '+phys dmg %, +phys pen %, rank 3: -magic dmg %', 3,
                  _ef(('physical_damage_pct', 3), ('physical_penetration_pct', 2)),
                  'strength', 3),
    'str4': _perk('Titan Grip',      '+phys dmg %, +Strength per rank',     3, _ef(('physical_damage_pct', 2), ('strength', 1)), 'strength', 4),

    # ── Cunning column ──────────────────────────────────────────────────
    # 'Deep Well' (+max mana) was retired when mana left the game;
    # the cun1 slot is reserved for the bullets mechanic — the guarded
    # 'maxBullets' bonus key stays inert until that system lands
    # (owner ruling 2026-10-29).
    'cun1': _perk('Deep Holster',    '+bullet capacity per rank',           3, _ef(('maxBullets', 5)),           'cunning', 1),
    'cun2': _perk('Arcanist',        '+magic damage % per rank',            3, _ef(('magic_damage_pct', 4)),     'cunning', 2),
    'cun3': _perk('Pyromancer',      '+fire dmg %, +fire pen % per rank',   3, _ef(('fire_damage_pct', 3), ('fire_penetration_pct', 2)), 'cunning', 3),
    'cun4': _perk('Overcharge',      '+lightning dmg %, rank 3: -ES',       3, _ef(('lightning_damage_pct', 3), ('max_energy_shield', -3)), 'cunning', 4),

    # ── Essence column ──────────────────────────────────────────────────
    'ess1': _perk('Grace Period',    '+entropy grace % per rank',           3, _ef(('entropy_grace_pct', 4)),    'essence', 1),
    'ess2': _perk('Blight Touch',    '+rot damage % per rank',              3, _ef(('rot_damage_pct', 4)),       'essence', 2),
    'ess3': _perk('Void Attunement', '+darkness resist %, rank 3: -max HP', 3, _ef(('darkness_resist_pct', 4), ('maxHealth', -3)), 'essence', 3),
    'ess4': _perk('Soul Anchor',     '+entropy grace %, +ability crit % per rank', 3, _ef(('entropy_grace_pct', 2), ('ability_crit_chance', 1)), 'essence', 4),

    # ── Nerve column ────────────────────────────────────────────────────
    'nrv1': _perk('Eagle Eye',       '+accuracy per rank',                  3, _ef(('accuracy_flat', 6)),        'nerve', 1),
    'nrv2': _perk('Bright Light',    '+light radius per rank',              3, _ef(('delve_light_radius', 0.5)), 'nerve', 2),
    'nrv3': _perk('Piercing Sight',  '+phys penetration % per rank',        3, _ef(('physical_penetration_pct', 3)), 'nerve', 3),
    'nrv4': _perk('Frost Weaver',    '+cold dmg %, +cold pen % per rank',   3, _ef(('cold_damage_pct', 3), ('cold_penetration_pct', 2)), 'nerve', 4),

    # ── Destiny column ──────────────────────────────────────────────────
    'dst1': _perk('Lucky Break',     '+entropy grace % per rank',           3, _ef(('entropy_grace_pct', 4)),    'destiny', 1),
    'dst2': _perk('Treasure Hunter', '+loot rarity modifier per rank',      3, _ef(('loot_rarity_mod', 2)),      'destiny', 2),
    'dst3': _perk('Sixth Sense',     '+entropy grace %, +CDR % per rank',   3, _ef(('entropy_grace_pct', 2), ('cooldown_recovery_pct', 2)), 'destiny', 3),
    'dst4': _perk('Sharp Nerve',     '+accuracy, +crit chance per rank',    3, _ef(('accuracy_flat', 4), ('crit_chance', 1)), 'destiny', 4),
}

# ── Perk helpers ────────────────────────────────────────────────────────

def _attr_val(descend: dict, attr: str) -> int:
    return descend.get(attr, 0)


def _has_prereq_perk(perks: dict, perk_id: str) -> bool:
    """A perk at threshold T requires the threshold T-1 perk in the same column."""
    col_map = {
        'dex': 'dexterity', 'end': 'endurance', 'str': 'strength',
        'cun': 'cunning',   'ess': 'essence',   'nrv': 'nerve', 'dst': 'destiny',
    }
    prefix = perk_id[:3]
    if prefix not in ('dex', 'end', 'str', 'cun', 'ess', 'nrv', 'dst'):
        return False
    thresh = int(perk_id[3:])
    if thresh <= 1:
        return True
    prev_id = f'{prefix}{thresh - 1}'
    return perks.get(prev_id, 0) > 0


def is_perk_unlockable(char, perk_id: str) -> bool:
    """Return True if `char` can purchase the next rank of `perk_id`."""
    perk = DESCEND_PERKS.get(perk_id)
    if not perk:
        return False
    descend = getattr(char, 'descend', {})
    attr = perk['attribute']
    threshold = perk['threshold']
    if _attr_val(descend, attr) < threshold:
        return False
    perks = getattr(char, 'perks', {})
    current_rank = perks.get(perk_id, 0)
    if current_rank >= perk['max_ranks']:
        return False
    if not _has_prereq_perk(perks, perk_id):
        return False
    points = getattr(char, 'available_points', 0)
    if points < 1:
        return False
    return True


def purchase_perk(char, perk_id: str) -> bool:
    """Buy one rank of `perk_id`. Returns True on success."""
    if not is_perk_unlockable(char, perk_id):
        return False
    perks = getattr(char, 'perks', {})
    perks[perk_id] = perks.get(perk_id, 0) + 1
    char.available_points = max(0, char.available_points - 1)
    char.save()
    return True


def increase_attribute(char, attr: str, cap: int = ATTR_CAP) -> bool:
    """Raise one DESCEND attribute by +1. Returns True on success."""
    if attr not in DESCEND_ATTRIBUTES:
        return False
    descend = getattr(char, 'descend', {})
    if descend.get(attr, 0) >= cap:
        return False
    points = getattr(char, 'available_points', 0)
    if points < 1:
        return False
    descend[attr] = descend.get(attr, 0) + 1
    char.available_points = max(0, char.available_points - 1)
    char.save()
    return True


def compute_perk_bonuses(perks: dict, descend: dict, item_bonuses: dict = None) -> dict:
    """Aggregate all stat bonuses from owned perk ranks AND item-sourced bonuses.

    Per BLUEPRINT §6 ("passives come from items"), `item_bonuses` carries the
    perk-style totals aggregated from equipped gear (see
    ``systems.itemgen.aggregate_item_bonuses``). They are summed into the same
    bonus dict the DESCEND perk ranks use, so gear and perks feed the exact
    same derivation pipeline in ``compute_derived_stats``.
    """
    bonuses = {}
    for perk_id, rank in (perks or {}).items():
        if rank <= 0:
            continue
        perk = DESCEND_PERKS.get(perk_id)
        if not perk:
            continue
        effects = perk['effects_fn'](rank)
        for k, v in effects.items():
            bonuses[k] = bonuses.get(k, 0) + v
    for k, v in (item_bonuses or {}).items():
        bonuses[k] = bonuses.get(k, 0) + v
    return bonuses


def get_available_descend_points(char) -> int:
    """Return the number of unspent Descend Points for `char`."""
    return getattr(char, 'available_points', 0)


# ── Respec ──────────────────────────────────────────────────────────────

def full_respec(char) -> bool:
    """Refund all spent attributes and perks into available_points."""
    descend = getattr(char, 'descend', {})
    perks = getattr(char, 'perks', {})

    spent_attr = sum(max(0, descend.get(a, 0)) for a in DESCEND_ATTRIBUTES)
    spent_perk = sum(perks.values())
    total_refund = spent_attr + spent_perk

    char.descend = {a: 0 for a in DESCEND_ATTRIBUTES}
    char.perks = {}
    char.available_points += total_refund
    char.save()
    return True
