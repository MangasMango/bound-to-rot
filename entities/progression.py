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

"""Characters and item-based progression.

Save schema versioning and migration (issue #126)
================================================

Owner policy: save migration is a STANDING requirement. A patch must never break
or silently discard a player save. Every save file carries an explicit
``save_schema_version``; on load the stored version is read and the ordered
migration chain is applied in place until the data reaches the current version.

The registry
------------
``_MIGRATIONS`` is the single place that has to change when the schema changes.
It maps a *from* version to the callable that upgrades a payload of that
version to ``from + 1``:

    _MIGRATIONS = {
        1: _migrate_1_to_2,
        2: _migrate_2_to_3,   # <- a future schema change adds exactly this line
    }

Adding a step for a new version is therefore: bump ``SAVE_SCHEMA_VERSION``, add
``_migrate_<n>_to_<n+1>``, and register it. Steps take the raw save ``dict`` and
return the upgraded ``dict``; they must be idempotent so a partially-migrated or
already-current file is never damaged by a second pass.

Safety contract
---------------
``migrate_save`` raises ``SaveMigrationError`` rather than guessing when a save
is corrupt, unreadable, or written by a NEWER build than this one. The caller
(``CharacterManager.load``) then copies the offending file to the save
directory's ``backups`` folder *before* anything destructive happens, records a
player-facing message on the manager, and leaves the original file on disk. A
save is never partially overwritten: writes go through a temp file and
``os.replace``, and a failing load never truncates the source file.
"""

import copy
import hashlib
import json
import os
import traceback
import time as _time

from config import ASSETS

from systems.items import GRID_COLS, GRID_ROWS, remap_legacy_card_ids
from systems.xp import MAX_LEVEL
from entities.descend import (DESCEND_ATTRIBUTES, ATTR_CAP,
                              compute_perk_bonuses,
                              get_available_descend_points, is_perk_unlockable,
                              purchase_perk, increase_attribute, DESCEND_PERKS,
                              VESSEL_DEFS, vessel_baseline_stats, LOOKS_OPTIONS)

_SAVE_DIR  = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'BTR')
os.makedirs(_SAVE_DIR, exist_ok=True)

CHARS_PATH = os.path.join(_SAVE_DIR, 'characters.json')

# ── Save schema versioning (issue #126) ────────────────────────────────────
# The one constant to bump when the save format changes. Bump it, add a
# _migrate_<n>_to_<n+1> step and register it in _MIGRATIONS below.
SAVE_SCHEMA_VERSION = 6
SAVE_FORMAT_VERSION = SAVE_SCHEMA_VERSION   # legacy alias kept for call sites

# Save files written before the framework existed carry no explicit key; the
# v1 migration step upgrades them.
FIRST_SCHEMA_VERSION = 1

BACKUP_DIR = os.path.join(_SAVE_DIR, 'backups')

ANIMA_SAVE_DIR = _SAVE_DIR                               # same dir for anima snapshots

def anima_save_path(char_id: str) -> str:
    return os.path.join(ANIMA_SAVE_DIR, f'anima_{char_id}.json')


def legacy_anima_save_path(char_id: str) -> str:
    """Pre-rename snapshot file name (issue #61: delve -> Anima). Older
    builds wrote delve_<char_id>.json; loaders fall back to it and a
    successful save to the new name clears it."""
    return os.path.join(ANIMA_SAVE_DIR, f'delve_{char_id}.json')


class SaveMigrationError(Exception):
    """A save cannot be migrated to the current schema.

    Carries a player-facing ``reason`` and the backup path once the offending
    file has been copied aside, so the UI can tell the player exactly what
    happened and where their data is.
    """

    def __init__(self, reason: str, source: str = '', backup_path: str = ''):
        super().__init__(reason)
        self.reason       = reason
        self.source       = source
        self.backup_path  = backup_path

    def player_message(self) -> str:
        msg = (f'Your save could not be loaded: {self.reason} '
               f'The file was left untouched and backed up so nothing is lost.')
        if self.backup_path:
            msg += f'  Backup: {self.backup_path}'
        return msg


def backup_save_file(path: str, reason: str) -> str:
    """Copy ``path`` into ``BACKUP_DIR`` and return the backup path.

    Never destructive: the original stays exactly as it was. Raises
    ``SaveMigrationError`` only when the file cannot be backed up, because at
    that point no safe recovery is possible.
    """
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        stamp = _time.strftime('%Y%m%d-%H%M%S')
        base  = os.path.splitext(os.path.basename(path))[0]
        dest  = os.path.join(BACKUP_DIR, f'{base}.{stamp}.bak')
        suffix = 0
        while os.path.exists(dest):
            suffix += 1
            dest = os.path.join(BACKUP_DIR, f'{base}.{stamp}-{suffix}.bak')
        with open(path, 'rb') as src, open(dest, 'wb') as out:
            out.write(src.read())
        return dest
    except OSError as exc:
        raise SaveMigrationError(
            f'{reason} and it could not be backed up ({exc})', path) from exc


def read_schema_version(data) -> int:
    """Return the schema version stamped in a decoded save payload.

    Raises ``SaveMigrationError`` for payloads that are not a dict, carry a
    non-numeric version, or were written by a newer build.
    """
    if not isinstance(data, dict):
        raise SaveMigrationError('the save file is not valid save data.')
    raw = data.get('save_schema_version', data.get('format_version'))
    if raw is None:
        # Pre-framework save: implicitly version 1.
        return FIRST_SCHEMA_VERSION
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise SaveMigrationError(f'its schema version {raw!r} is not a number.')
    if raw < FIRST_SCHEMA_VERSION:
        raise SaveMigrationError(f'its schema version {raw} is not a valid version.')
    if raw > SAVE_SCHEMA_VERSION:
        raise SaveMigrationError(
            f'it was written by a newer version of the game (schema v{raw}, '
            f'this build supports up to v{SAVE_SCHEMA_VERSION}).')
    return raw


def supported_versions() -> list[int]:
    """Every version this build can load, oldest first."""
    versions = [FIRST_SCHEMA_VERSION]
    while versions[-1] < SAVE_SCHEMA_VERSION:
        if versions[-1] not in _MIGRATIONS:
            break
        versions.append(versions[-1] + 1)
    return versions


# ── Migration steps ────────────────────────────────────────────────────────
# Retired per-character fields. A pre-#120 save can still carry them; the
# current Character model has no place for them, so they are dropped rather
# than being misread as live data.
_RETIRED_CHAR_FIELDS = ('level', 'xp', 'xp_progress', 'unlocked_nodes',
                        'skill_slots', 'flasks', 'belt')
_RETIRED_ROSTER_FIELDS = ('format_version', 'version', 'characters_v0')


def _migrate_1_to_2(data: dict) -> dict:
    """v1 -> v2: strip retired level/XP fields and normalise roster payload.

    v1 is the pre-framework save format. Character data (descend,
    perks, inventory, stash) is preserved as-is; only fields the
    current model cannot represent are removed, and missing optional keys are
    defaulted so the payload is loadable.
    """
    if not isinstance(data, dict):
        raise SaveMigrationError('the save file is not valid save data.')
    for key in _RETIRED_ROSTER_FIELDS:
        data.pop(key, None)
    characters = data.get('characters')
    if characters is None:
        characters = []
    if not isinstance(characters, list):
        raise SaveMigrationError('its character roster is not a list.')
    for entry in characters:
        if not isinstance(entry, dict):
            raise SaveMigrationError('one of its characters is not valid save data.')
        for key in _RETIRED_CHAR_FIELDS:
            entry.pop(key, None)
        stash = entry.get('stash')
        if not isinstance(stash, list):
            stash = []
        # Stash is four fixed tabs; shorter/empty saves are padded, not reshaped.
        tabs = [tab if isinstance(tab, list) else [] for tab in stash]
        while len(tabs) < 4:
            tabs.append([])
        entry['stash'] = tabs[:4]
    data['characters'] = characters
    data.setdefault('active_idx', 0)
    data.setdefault('unlocked_vessels', ['knight'])
    data.setdefault('best_depth', 0)
    return data


def _migrate_2_to_3(data: dict) -> dict:
    """v2 -> v3: collapse the four stash tabs into a single 8x8 bank grid.

    The bank has no tabs any more (the BankStash panel art paints one 8x8
    grid). Every entry from the old four-tab list is re-placed into the single
    grid with col/row stripped; the game is pre-production, so overflow beyond
    the 64 available cells is discarded rather than compensated.
    """
    if not isinstance(data, dict):
        raise SaveMigrationError('the save file is not valid save data.')
    characters = data.get('characters')
    if characters is None:
        characters = []
    if not isinstance(characters, list):
        raise SaveMigrationError('its character roster is not a list.')
    for entry in characters:
        if not isinstance(entry, dict):
            raise SaveMigrationError('one of its characters is not valid save data.')
        stash = entry.get('stash')
        if not isinstance(stash, list):
            stash = []
        flat = []
        for tab in stash:
            if not isinstance(tab, list):
                continue
            for slot in tab:
                if isinstance(slot, dict):
                    flat.append({k: v for k, v in slot.items()
                                 if k not in ('col', 'row')})
        bank = []
        for slot in flat:
            if len(bank) >= GRID_COLS * GRID_ROWS:
                break   # pre-production ruling: overflow is discarded
            placed = dict(slot)
            placed['col'] = len(bank) % GRID_COLS
            placed['row'] = len(bank) // GRID_COLS
            bank.append(placed)
        entry['stash'] = bank
    data['characters'] = characters
    return data


def _migrate_3_to_4(data: dict) -> dict:
    """v3 -> v4: leveling and XP return (issue #31).

    Owner rulings 2026-11-02. XP drops from kills, each level grants +1
    attribute point, the level hard-cap is 70 (7 attributes x cap 10).
    Vessel attribute baselines are removed: every DESCEND attribute starts
    at 0 and all spendable points come from level-ups, so the arithmetic is
    exact. Existing characters join at level 1 with an empty XP bar.
    Permadeath is replaced by a PoE-style XP loss on death; nothing else in
    the payload changes.
    """
    if not isinstance(data, dict):
        raise SaveMigrationError('the save file is not valid save data.')
    characters = data.get('characters')
    if characters is None:
        characters = []
    if not isinstance(characters, list):
        raise SaveMigrationError('its character roster is not a list.')
    for entry in characters:
        if not isinstance(entry, dict):
            raise SaveMigrationError('one of its characters is not valid save data.')
        entry.setdefault('level', 1)
        entry.setdefault('xp', 0)
        descend = entry.get('descend')
        if not isinstance(descend, dict):
            descend = {}
        entry['descend'] = {a: 0 for a in DESCEND_ATTRIBUTES}
    data['characters'] = characters
    return data


def _migrate_4_to_5(data: dict) -> dict:
    """v4 -> v5: leveling-rework item cleanup (plan .ai/
    LEVELS_REWORK_PLAN.md §2.3-§2.4, owner rulings 2026-11).

    - `flat_melee_damage` instances are renamed in place to
      `flat_attack_damage` (value preserved) - it is the same affix.
    - Attribute-point suffixes (attr_*) and the retired pk_* macros
      (pk_melee_mult, pk_accuracy, pk_entropy_grace, pk_reload_speed) and
      percent_move_speed (DEX-owned line) are stripped from every item.
    - Per BLUEPRINT §49, each stripped roll is compensated: one
      replacement stat suffix (the plan's new stat pool) is granted at a
      fair value for the item's ilvl + rarity, so compensation is
      equivalent-or-better, never a downgrade.
    - A summary is attached as ``data['migration_note']`` for a dismissable
      character-select notification.
    """
    if not isinstance(data, dict):
        raise SaveMigrationError('the save file is not valid save data.')
    import systems.itemgen as itemgen

    RETIRED = {
        'attr_dexterity', 'attr_endurance', 'attr_strength', 'attr_cunning',
        'attr_essence', 'attr_nerve', 'attr_destiny',
        'pk_melee_mult', 'pk_accuracy', 'pk_entropy_grace',
        'pk_reload_speed', 'percent_move_speed',
    }
    RENAMED = {'flat_melee_damage': 'flat_attack_damage'}

    def _compensate(inst, count):
        """Re-roll `count` replacement stat suffixes at fair value."""
        aff = inst.get('affixes')
        if not isinstance(aff, dict):
            aff = {'prefixes': {}, 'suffixes': {}}
            inst['affixes'] = aff
        suffixes = aff.setdefault('suffixes', {})
        taken = set(suffixes)
        equip_slot = (itemgen.ITEMS.get(inst.get('_item_id', ''), {})
                      .get('equipSlot'))
        pool = [a for a in itemgen._SUFFIXES if a['id'] not in taken]
        if not pool:
            return
        ilvl = int(inst.get('ilvl', 1))
        rarity = inst.get('rarity', 'common')
        for offset in range(count):
            a_def = pool[(ilvl + offset) % len(pool)]
            fair = (a_def['base'] * (1.0 + ilvl / 100.0)
                    * itemgen.M_RARITY[rarity])
            suffixes[a_def['id']] = itemgen._round_val(fair, a_def['round'])

    notes = []
    characters = data.get('characters')
    if characters is None:
        characters = []
    if not isinstance(characters, list):
        raise SaveMigrationError('its character roster is not a list.')
    for entry in characters:
        if not isinstance(entry, dict):
            raise SaveMigrationError(
                'one of its characters is not valid save data.')
        char_name = entry.get('name', 'Unnamed')
        retires, upgrades = 0, 0

        def _patch_inst(inst):
            nonlocal retires, upgrades
            if not isinstance(inst, dict):
                return
            aff = inst.get('affixes')
            if not isinstance(aff, dict):
                return
            stripped = 0
            for group in ('prefixes', 'suffixes'):
                vals = aff.get(group)
                if not isinstance(vals, dict):
                    continue
                for aid in list(vals):
                    if aid in RENAMED:
                        vals[RENAMED[aid]] = vals.pop(aid)
                        upgrades += 1
                    elif aid in RETIRED:
                        vals.pop(aid)
                        retires += 1
                        stripped += 1
            if stripped:
                _compensate(inst, stripped)

        def _walk_slots(container):
            if not isinstance(container, list):
                return
            for slot in container:
                if isinstance(slot, dict):
                    _patch_inst(slot.get('instance_data')
                                if isinstance(slot.get('instance_data'), dict)
                                else None)

        inv = entry.get('inventory')
        if isinstance(inv, dict):
            _walk_slots(inv.get('grid'))
            eq = inv.get('equipped')
            if isinstance(eq, dict):
                for slot in eq.values():
                    if isinstance(slot, dict) and isinstance(
                            slot.get('instance_data'), dict):
                        _patch_inst(slot['instance_data'])
        stash = entry.get('stash')
        if isinstance(stash, list):
            _walk_slots(stash)
        if retires or upgrades:
            notes.append(
                f"{char_name}: {retires} retired affix"
                f"{'s' if retires != 1 else ''} replaced with stat rolls"
                + (f"; {upgrades} melee-damage affix"
                   f"{'es' if upgrades != 1 else ''} renamed to attack damage"
                   if upgrades else ''))
    if notes:
        data['migration_note'] = '\n'.join(notes)
    data['characters'] = characters
    return data


def _migrate_5_to_6(data: dict) -> dict:
    """v5 -> v6: the R gem slot is gone (issue #45 - R is a pure reload
    key). Every stored white gem converts value-preserving into a random
    Q/W/E gem at the same rarity (ability re-rolled from the new slot's
    pool), and any 'R' key in gem_sockets disappears. Idempotent."""
    if not isinstance(data, dict):
        raise SaveMigrationError('the save file is not valid save data.')
    import random as _rnd
    import systems.gems as _gems
    import systems.itemgen as _itemgen

    GEM_IDS = ('gem_blue', 'gem_green', 'gem_red')
    notes = []

    def _convert_white(slot_dict):
        """gem_white -> a random Q/W/E gem at the same rarity (in place)."""
        inst = slot_dict.get('instance_data') or {}
        rarity = inst.get('rarity', 'uncommon')
        new_id = _gems.gem_item_id(_rnd.choice(('Q', 'W', 'E')))
        ability = _gems.random_ability_for_gem_slot(
            {'gem_blue': 'Q', 'gem_green': 'W', 'gem_red': 'E'}[new_id])
        slot_dict['item'] = new_id
        slot_dict['count'] = slot_dict.get('count', 1)
        old_name = inst.get('display_name', 'White Gem')
        slot_dict['instance_data'] = {
            'rarity': rarity,
            'display_name': (ability or 'Gem').replace('_', ' ').title(),
            'ilvl': int(inst.get('ilvl', 1)),
            'identified': True,          # gems are always identified
            'ability': ability,
        }
        return f'{old_name} -> {new_id}'

    def _walk(obj):
        if isinstance(obj, dict):
            for key in list(obj.keys()):
                if key == 'gem_sockets' and isinstance(obj[key], dict):
                    sockets = obj[key]
                    r_entry = sockets.pop('R', None)
                    if r_entry is not None:
                        notes.append(_convert_white(r_entry))
                        # the converted gem must keep a home: a free slot
                        # if one exists, else the inventory grid
                        free = [k for k, v in sockets.items() if v is None]
                        if free:
                            sockets[free[0]] = r_entry
                        else:
                            obj.setdefault('grid', []).append(r_entry)
                    for entry in sockets.values():
                        if isinstance(entry, dict) and entry.get('item') == 'gem_white':
                            notes.append(_convert_white(entry))
                    for keep in ('Q', 'W', 'E'):
                        sockets.setdefault(keep, None)   # normalize the slot set
                    continue    # do not descend into socket entries
                if isinstance(obj[key], list):
                    for gi in obj[key]:
                        if isinstance(gi, dict) and gi.get('item') == 'gem_white':
                            notes.append(_convert_white(gi))
                _walk(obj[key])
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(data)
    if notes:
        header = ('The White Gem was retired (R is a reload key now); '
                  'stored white gems were converted:')
        data['migration_note'] = '\n'.join(
            [header] + notes + [str(d.get('migration_note', ''))
                                for d in [data] if d.get('migration_note')])
    return data


# ── MIGRATION REGISTRY ─────────────────────────────────────────────────────
# Single place to update for any future schema change: bump
# SAVE_SCHEMA_VERSION and add the matching step here. Keys are *from* versions.
_MIGRATIONS: dict[int, callable] = {
    1: _migrate_1_to_2,
    2: _migrate_2_to_3,
    3: _migrate_3_to_4,
    4: _migrate_4_to_5,
    5: _migrate_5_to_6,
}


def register_migration(from_version: int, step: callable = None):
    """Register a migration step, as a decorator or called directly.

    ``step`` receives the raw save dict and returns the upgraded dict.
    """
    def _apply(fn):
        if not isinstance(from_version, int) or from_version < FIRST_SCHEMA_VERSION:
            raise ValueError(f'invalid migration source version {from_version!r}')
        _MIGRATIONS[from_version] = fn
        return fn
    return _apply if step is None else _apply(step)


def migration_chain(from_version: int) -> list[callable]:
    """The ordered steps that upgrade ``from_version`` to the current version."""
    steps = []
    version = from_version
    while version < SAVE_SCHEMA_VERSION:
        step = _MIGRATIONS.get(version)
        if step is None:
            raise SaveMigrationError(
                f'no migration path from schema v{version} to v{SAVE_SCHEMA_VERSION}.')
        steps.append(step)
        version += 1
    return steps


def migrate_save(data, source: str = '') -> dict:
    """Upgrade a decoded save payload to the current schema, in place.

    Returns the same dict when it is already current, so the call is
    idempotent: running the chain twice yields the same result and a
    current-version save is never modified.
    """
    version = read_schema_version(data)
    if version == SAVE_SCHEMA_VERSION:
        return data
    for step in migration_chain(version):
        data = step(data)
    data['save_schema_version'] = SAVE_SCHEMA_VERSION
    return data

def _anima_sanitize(data: dict) -> dict:
    """Deep-copy and convert non-JSON-safe types for serialization."""
    data = copy.deepcopy(data)
    anima = data.get('anima')
    if not anima:
        return data
    if isinstance(anima.get('enemy_ids'), set):
        anima['enemy_ids'] = list(anima['enemy_ids'])
    anima.pop('extend_rng', None)
    anima.pop('_chart_rng_state', None)
    anima.pop('_close_btn', None)
    anima.pop('_hub_btn', None)
    anima.pop('_hovered_node', None)
    anima.pop('anima_map_open', None)
    anima.pop('_dir_buttons', None)
    anima.pop('_dir_close_btn', None)
    anima.pop('_dir_hover', None)
    anima.pop('_dir_inline_btns', None)
    anima.pop('_dir_inline_hover', None)
    anima.pop('_card_close_btn', None)
    anima.pop('_card_flip_timer', None)
    anima.pop('_card_show_timer', None)
    anima.pop('hovered_card', None)
    anima.pop('cards', None)
    return data

def _anima_restore(data: dict) -> dict:
    """Convert JSON-safe types back to runtime equivalents."""
    # issue #61 rename: legacy snapshots keyed the payload 'delve' - read
    # either, normalize to the new key before the runtime conversion
    if 'anima' not in data and isinstance(data.get('delve'), dict):
        data['anima'] = data.pop('delve')
    # issue #45: the white gem is retired - convert any stored ones found
    # in older anima snapshots (ground items) the same way the save
    # migration does for character inventories
    import random as _rnd
    import systems.gems as _gems

    def _convert_white(gi):
        rarity = ((gi.get('instance_data') or {}).get('rarity', 'uncommon'))
        new_slot = _rnd.choice(('Q', 'W', 'E'))
        ability = _gems.random_ability_for_gem_slot(new_slot)
        gi['item'] = _gems.gem_item_id(new_slot)
        inst = gi.get('instance_data') or {}
        inst.update({
            'rarity': rarity,
            'display_name': (ability or 'Gem').replace('_', ' ').title(),
            'identified': True,
            'ability': ability,
        })
        gi['instance_data'] = inst

    for items in (data.get('ground_items') or []):
        if isinstance(items, dict) and items.get('item') == 'gem_white':
            _convert_white(items)
    anima = data.get('anima')
    if not anima:
        return data
    if isinstance(anima.get('enemy_ids'), list):
        anima['enemy_ids'] = set(anima['enemy_ids'])
    anima.setdefault('pending_rewards', [])
    # JSON stringifies dict keys - the chart graph's node map must come back
    # as int-keyed or every node lookup by id silently fails after a restart.
    graph = (anima.get('chart') or {}).get('graph')
    if isinstance(graph, dict) and isinstance(graph.get('nodes'), dict):
        graph['nodes'] = {int(k): v for k, v in graph['nodes'].items()}
        for id_key in ('start_node_id', 'current_node_id'):
            if isinstance(graph.get(id_key), str):
                graph[id_key] = int(graph[id_key])
    # Tarot cards are transient (regenerated on Pulse click); a saved
    # 'show_cards' state has no cards, so recover to 'ready'.
    if anima.get('state') == 'show_cards':
        anima['state'] = 'ready'
    if isinstance(anima.get('state'), str) and anima['state'] not in ('clearing', 'show_cards', 'ready', 'arriving'):
        anima['state'] = 'clearing'
    return data

def save_anima_data(char_id: str, data):
    """Write the anima snapshot to disk (JSON), stamped with the schema version."""
    try:
        sanitized = _anima_sanitize(data)
        sanitized['save_schema_version'] = SAVE_SCHEMA_VERSION
        with open(anima_save_path(char_id), 'w') as f:
            json.dump(sanitized, f)
        # a written new-name snapshot retires the legacy delve_<id>.json
        legacy = legacy_anima_save_path(char_id)
        if os.path.exists(legacy):
            os.remove(legacy)
    except Exception:
        print("[save] ERROR: Failed to save anima data")
        traceback.print_exc()

def load_anima_data(char_id: str):
    """Read the anima snapshot from disk, or None.

    A snapshot written by a newer build is backed up and ignored rather than
    misread: resuming a raid from a payload this build cannot understand risks
    corrupting a run, and the character save itself is unaffected.
    Legacy delve_<id>.json files (pre issue-#61 rename) are read as-is.
    """
    path = anima_save_path(char_id)
    if not os.path.exists(path):
        legacy = legacy_anima_save_path(char_id)
        if os.path.exists(legacy):
            path = legacy
    try:
        with open(path) as f:
            data = json.load(f)
        stored = data.get('save_schema_version') if isinstance(data, dict) else None
        if isinstance(stored, int) and not isinstance(stored, bool) \
                and stored > SAVE_SCHEMA_VERSION:
            backup = backup_save_file(path, 'anima snapshot is from a newer build')
            print(f"[save] Anima snapshot from a newer build ignored; backed up to {backup}")
            return None
        return _anima_restore(data)
    except Exception:
        return None

def clear_anima_data(char_id: str):
    """Remove the anima snapshot from disk (new and legacy file names)."""
    try:
        os.remove(anima_save_path(char_id))
    except FileNotFoundError:
        pass
    except Exception:
        print("[save] ERROR: Failed to clear anima data")
        traceback.print_exc()
    finally:
        try:
            os.remove(legacy_anima_save_path(char_id))
        except OSError:
            pass

# ── Derived stats ──────────────────────────────────────────────────────────

BASE_LIFE    = 50
BASE_EVASION = 300

def compute_derived_stats(descend: dict, perk_bonuses: dict = None,
                          item_bonuses: dict = None, looks: str = 'fighter') -> dict:
    pb = perk_bonuses or {}
    ib = item_bonuses or {}

    vessel_effects = VESSEL_DEFS.get(looks, {}).get('effects', {})

    def _attr(a):
        # Owner ruling (leveling rework 2026-11, plan §2.3): attribute
        # POINTS cap at 10 from level allocations only - with the attr_*
        # item suffixes retired, items carry stats, never attribute points.
        return min(ATTR_CAP, descend.get(a, 0))

    dex = _attr('dexterity')
    end = _attr('endurance')
    str_ = _attr('strength')
    cun = _attr('cunning')
    ess = _attr('essence')
    nrv = _attr('nerve')
    dst = _attr('destiny')

    def bonus(key):
        return pb.get(key, 0) + ib.get(key, 0) + vessel_effects.get(key, 0)

    return {
        # Attribute per-point identities (leveling rework, plan §2.1 - one
        # distinct lever per attribute; lines no item affix can roll):
        #   STR  raw attack damage % (+ hp floor)
        #   END  HP + energy shield + darkness resist
        #   DEX  move/attack speed, evasion, accuracy, block
        #   CUN  cooldown recovery + reload speed (x3 amplitudes)
        #   ESS  ability crit (+ entropy-grace share)
        #   NRV  crit chance + anima light radius
        #   DST  entropy grace + loot rarity
        'max_health':            50 + str_ * 8 + end * 6 + bonus('maxHealth'),
        'evasion':               int(300 * (1.0 + 0.03 * dex) + bonus('evasion_flat')),
        'accuracy':              300 + dex * 4 + bonus('accuracy_flat'),
        'attack_damage_mult':    1.0 + 0.05 * str_ + bonus('attack_damage_mult_pct') / 100.0,
        'max_energy_shield':     end * 3 + bonus('max_energy_shield'),
        'anima_light_radius':    nrv * 0.5 + bonus('anima_light_radius'),
        'darkness_resist_pct':   (end * 2 + bonus('darkness_resist_pct')) / 100.0,
        'move_speed_pct':        (bonus('move_speed_pct') + dex * 3.0) / 100.0,
        'attack_speed_pct':      (bonus('attack_speed_pct') + dex * 3.0) / 100.0,
        'cooldown_recovery_pct': (cun * 3.0 + bonus('cooldown_recovery_pct')) / 100.0,
        # Reload speed (ammo mechanic): Cunning and the '+X% Reload Speed'
        # affix family lower the 3.0 s base cylinder reload.
        'reload_speed_pct':      (cun * 3.0 + bonus('reload_speed_pct')) / 100.0,
        'crit_chance':           min(0.75, (bonus('crit_chance') + nrv * 1.0) / 100.0),
        'ability_crit_chance':   min(0.75, (bonus('ability_crit_chance') + ess * 1.0) / 100.0),
        'block_chance':          min(0.75, (bonus('block_chance') + dex * 1.5) / 100.0),
        'crushing_blow_pct':     min(0.75, bonus('crushing_blow_pct') / 100.0),
        'entropy_grace_pct':     (dst * 1.5 + ess * 1.0 + bonus('entropy_grace_pct')) / 100.0,
        # Loot rarity is DST-owned (plan §2.1 ruling): Destiny raises the
        # rarity weights of enemy drops; no item affix ever rolls it.
        'loot_rarity_mod':       dst * 2 + bonus('loot_rarity_mod'),
        'damage_pct':            {t: bonus(f'{t}_damage_pct') / 100.0 for t in ('physical', 'magic', 'lightning', 'cold', 'fire', 'rot')},
        'penetration_pct':       {t: bonus(f'{t}_penetration_pct') / 100.0 for t in ('physical', 'magic', 'lightning', 'cold', 'fire', 'rot')},
        'resist_pct':            {t: bonus(f'{t}_resist_pct') / 100.0 for t in ('fire', 'cold', 'lightning', 'physical', 'magic', 'rot', 'darkness')},
        'dexterity': dex, 'endurance': end, 'strength': str_,
        'cunning': cun, 'essence': ess, 'nerve': nrv, 'destiny': dst,
        # backward compat
        'total_str': str_, 'total_dex': dex, 'total_int': cun,
    }


# ── Character ─────────────────────────────────────────────────────────────

class Character:
    def __init__(self, char_id: str = '', name: str = 'Operative', looks: str = 'fighter'):
        self.id             = char_id or str(int(_time.time() * 1000))
        self.name           = name
        self.looks          = looks if looks in LOOKS_OPTIONS else 'fighter'
        self.descend: dict  = vessel_baseline_stats(self.looks)
        self.perks: dict    = {}
        self.available_points: int = 0
        self.level: int     = 1
        self.xp: int        = 0
        self.inventory: dict | None = None
        self.stash: list    = []   # single 8x8 bank grid (no tabs)
        self._grid_overflow: list = []
        self._save_cb       = None

    @property
    def seed(self) -> int:
        """Stable per-character anima seed, derived from the id.

        The anima layout is bound to the character: same character → same
        chart and rooms on every visit; death deletes the character (new
        id → new seed → fresh layout). Never stored - recomputed.
        """
        digest = hashlib.sha1(self.id.encode('utf-8')).digest()
        return int.from_bytes(digest[:4], 'big')

    def save(self):
        if self._save_cb:
            self._save_cb()

    def load(self):
        pass  # loading handled by CharacterManager

    def to_dict(self) -> dict:
        return {
            'id':             self.id,
            'name':           self.name,
            'looks':          self.looks,
            'descend':        self.descend,
            'perks':          self.perks,
            'available_points': self.available_points,
            'level':          self.level,
            'xp':             self.xp,
            'inventory':      self.inventory,
            'stash':          self.stash,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'Character':
        """Build a character from a save payload already migrated to current.

        Callers must run ``migrate_save`` (or ``migrate_save`` per character)
        first; this only validates the current shape. An unexpected shape raises
        ValueError, which CharacterManager turns into a backup + a visible
        message rather than a partially loaded roster.
        """
        required = {'id', 'name', 'looks', 'descend',
                    'perks', 'available_points', 'inventory', 'stash'}
        if not isinstance(d, dict) or not required.issubset(d):
            raise ValueError('incompatible character save')
        c = cls(d['id'], d['name'], d['looks'])
        c.inventory = d['inventory']
        c.descend = d['descend']
        c.perks = d['perks']
        c.available_points = d['available_points']
        # Level/XP re-landed with schema v4 (issue #31); read defensively so a
        # hand-edited or partially-written payload degrades instead of losing
        # the whole roster.
        try:
            level = int(d.get('level', 1))
        except (TypeError, ValueError):
            level = 1
        try:
            xp = int(d.get('xp', 0))
        except (TypeError, ValueError):
            xp = 0
        c.level = max(1, min(int(MAX_LEVEL), level))
        c.xp = max(0, xp)
        c.stash = d['stash']
        remap_legacy_card_ids(c.inventory, c.stash)
        return c


# ── Character Manager ─────────────────────────────────────────────────────

class CharacterManager:
    MAX_CHARS = 5

    def __init__(self):
        self.characters: list[Character] = []
        self.active_idx: int = 0
        self.unlocked_vessels: list[str] = ['knight']
        self.best_depth: int = 0
        # Set when the last load() could not read or migrate the save. Holds a
        # player-facing message plus the backup path of the offending file.
        self.load_error: str = ''
        self.load_error_backup: str = ''
        self.migration_note: str = ''   # blueprint §49 on-load notice
        self.migrated_from_version: int = SAVE_SCHEMA_VERSION
        self.load()

    @property
    def active(self) -> Character | None:
        if not self.characters:
            return None
        idx = max(0, min(self.active_idx, len(self.characters) - 1))
        return self.characters[idx]

    def is_vessel_unlocked(self, looks: str) -> bool:
        return looks in self.unlocked_vessels

    def unlock_vessel(self, looks: str) -> bool:
        """Record an account-wide vessel unlock. Returns True if newly unlocked."""
        if looks in self.unlocked_vessels:
            return False
        self.unlocked_vessels.append(looks)
        self.save()
        return True

    def note_depth(self, depth: int) -> list[str]:
        """Record the deepest point reached on any descent and auto-unlock any
        vessels whose veil has now been pierced.  Returns newly unlocked keys.

        Vessels in WIP_VESSELS are never auto-unlocked while they are
        unimplemented."""
        newly = []
        changed = False
        if depth > self.best_depth:
            self.best_depth = depth
            changed = True
        from entities.descend import VESSEL_UNLOCKS, WIP_VESSELS
        for lk, data in VESSEL_UNLOCKS.items():
            if lk in WIP_VESSELS:
                continue
            req = data['depth']
            if req <= 0 or req > self.best_depth:
                continue
            if lk in self.unlocked_vessels:
                continue
            self.unlocked_vessels.append(lk)
            newly.append(lk)
        if changed or newly:
            self.save()
        return newly

    def create(self, name: str, looks: str = 'fighter') -> Character:
        """Create a level-1 character. Vessels grant passives only - all
        attribute points come from level-ups (issue #31)."""
        c = Character(name=name, looks=looks)
        c.descend = vessel_baseline_stats(c.looks)
        c.available_points = 0
        c._save_cb = self.save
        self.characters.append(c)
        self.active_idx = len(self.characters) - 1
        self.save()
        return c

    def delete(self, idx: int):
        if 0 <= idx < len(self.characters):
            self.characters.pop(idx)
            self.active_idx = max(0, min(self.active_idx, len(self.characters) - 1))
            self.save()

    def select(self, idx: int):
        if 0 <= idx < len(self.characters):
            self.active_idx = idx
            self.save()

    def save(self):
        """Write the roster atomically, stamped with the current schema version.

        A load failure does not block saving: the offending file has already
        been copied into BACKUP_DIR by load(), so overwriting it here cannot
        lose the player's data.
        """
        try:
            tmp = CHARS_PATH + '.tmp'
            with open(tmp, 'w') as f:
                json.dump({
                    'save_schema_version': SAVE_SCHEMA_VERSION,
                    'active_idx': self.active_idx,
                    'unlocked_vessels': self.unlocked_vessels,
                    'best_depth': self.best_depth,
                    'characters': [c.to_dict() for c in self.characters],
                }, f, indent=2)
            os.replace(tmp, CHARS_PATH)
        except Exception:
            print("[save] ERROR: Failed to write characters.json")
            traceback.print_exc()

    def _fail_load(self, reason: str, exc: Exception = None) -> None:
        """Record a visible load failure after backing the save file up.

        The roster stays empty in memory and the original file is left on disk
        untouched, so nothing is silently wiped. The message and backup path
        stay available for the UI to show the player.
        """
        detail = reason if exc is None else f'{reason} ({exc})'
        backup = ''
        try:
            backup = backup_save_file(CHARS_PATH, 'the save could not be loaded')
        except SaveMigrationError as backup_exc:
            detail = f'{detail} {backup_exc.reason}'
        self.load_error = (
            f'Your save could not be loaded: {detail} Nothing was deleted - the '
            f'file was backed up so you can recover it.')
        self.load_error_backup = backup
        print(f"[save] {self.load_error}")
        if backup:
            print(f"[save] Backed up to: {backup}")

    def load(self):
        """Load the roster, migrating older schema versions up to current.

        Never discards or partially overwrites a save. A corrupt, unreadable or
        future-version file is backed up, reported on ``self.load_error``, and
        the roster starts empty so the game is still playable.
        """
        self.load_error = ''
        self.load_error_backup = ''
        if not os.path.exists(CHARS_PATH):
            return
        try:
            with open(CHARS_PATH) as f:
                data = json.load(f)
        except (OSError, ValueError) as exc:
            self._fail_load('the save file is corrupt or unreadable', exc)
            return

        try:
            stored_version = read_schema_version(data)
            data = migrate_save(data, CHARS_PATH)
        except SaveMigrationError as exc:
            exc.source = CHARS_PATH
            try:
                exc.backup_path = backup_save_file(CHARS_PATH, 'the save could not be migrated')
            except SaveMigrationError as backup_exc:
                self._fail_load(exc.reason, backup_exc)
                return
            self.load_error = exc.player_message()
            self.load_error_backup = exc.backup_path
            print(f"[save] {self.load_error}")
            return

        self.migration_note = str(data.pop('migration_note', '') or '')
        if self.migration_note:
            print(f"[save] migration compensation applied:\n{self.migration_note}")
        try:
            characters = [Character.from_dict(d) for d in data.get('characters', [])]
            self.active_idx = data.get('active_idx', 0)
            self.characters = characters
            self.unlocked_vessels = list(data.get('unlocked_vessels', ['knight']))
            self.best_depth = int(data.get('best_depth', 0))
            for c in self.characters:
                c._save_cb = self.save
                if c.looks in LOOKS_OPTIONS and c.looks not in self.unlocked_vessels:
                    self.unlocked_vessels.append(c.looks)
        except (ValueError, TypeError, KeyError) as exc:
            # Partially applied mutations are rolled back so the manager never
            # exposes a half-built roster.
            self.characters = []
            self.active_idx = 0
            self._fail_load('the save could not be read after migration', exc)
            return

        if stored_version != SAVE_SCHEMA_VERSION:
            self.migrated_from_version = stored_version
            print(f"[save] Migrated save from schema v{stored_version} to v{SAVE_SCHEMA_VERSION}")
            self.save()   # persist the upgraded payload
        else:
            self.migrated_from_version = stored_version


# ── D.E.S.C.E.N.D. aliases ────────────────────────────────────────────────

# ── Raid Tracker ──────────────────────────────────────────────────────────

class RaidTracker:
    def __init__(self):
        self.kills     = 0
        self.loot      = 0
        self.time      = 0.0
        self.extracted = False

    def reset(self):
        self.kills     = 0
        self.loot      = 0
        self.time      = 0.0
        self.extracted = False

    def finalize(self, char: Character) -> dict:
        """End-screen stats snapshot (the raid-task system was removed; the
        tracker keeps its raw counters only)."""
        char.save()

        return {
            'kills':       self.kills,
            'time':        self.time,
            'loot':        self.loot,
            'extracted':   self.extracted,
        }
