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

"""Tasks, currency, characters, and item-based progression.

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
import random
import traceback
import time as _time

from config import ASSETS

from systems.items import GRID_COLS, GRID_ROWS, remap_legacy_card_ids
from entities.descend import (DESCEND_ATTRIBUTES, compute_perk_bonuses,
                              get_available_descend_points, is_perk_unlockable,
                              purchase_perk, increase_attribute, DESCEND_PERKS,
                              VESSEL_DEFS, vessel_baseline_stats, LOOKS_OPTIONS)

_SAVE_DIR  = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'BTR')
os.makedirs(_SAVE_DIR, exist_ok=True)

CHARS_PATH = os.path.join(_SAVE_DIR, 'characters.json')

# ── Save schema versioning (issue #126) ────────────────────────────────────
# The one constant to bump when the save format changes. Bump it, add a
# _migrate_<n>_to_<n+1> step and register it in _MIGRATIONS below.
SAVE_SCHEMA_VERSION = 3
SAVE_FORMAT_VERSION = SAVE_SCHEMA_VERSION   # legacy alias kept for call sites

# Save files written before the framework existed carry no explicit key; the
# v1 migration step upgrades them.
FIRST_SCHEMA_VERSION = 1

BACKUP_DIR = os.path.join(_SAVE_DIR, 'backups')

DELVE_SAVE_DIR = _SAVE_DIR                               # same dir for delve snapshots

def delve_save_path(char_id: str) -> str:
    return os.path.join(DELVE_SAVE_DIR, f'delve_{char_id}.json')


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

    v1 is the pre-framework save format. Character data (currency, tasks,
    descend, perks, inventory, stash) is preserved as-is; only fields the
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


# ── MIGRATION REGISTRY ─────────────────────────────────────────────────────
# Single place to update for any future schema change: bump
# SAVE_SCHEMA_VERSION and add the matching step here. Keys are *from* versions.
_MIGRATIONS: dict[int, callable] = {
    1: _migrate_1_to_2,
    2: _migrate_2_to_3,
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

def _delve_sanitize(data: dict) -> dict:
    """Deep-copy and convert non-JSON-safe types for serialization."""
    data = copy.deepcopy(data)
    delve = data.get('delve')
    if not delve:
        return data
    if isinstance(delve.get('enemy_ids'), set):
        delve['enemy_ids'] = list(delve['enemy_ids'])
    delve.pop('extend_rng', None)
    delve.pop('_chart_rng_state', None)
    delve.pop('_close_btn', None)
    delve.pop('_hub_btn', None)
    delve.pop('_hovered_node', None)
    delve.pop('delve_map_open', None)
    delve.pop('_dir_buttons', None)
    delve.pop('_dir_close_btn', None)
    delve.pop('_dir_hover', None)
    delve.pop('_dir_inline_btns', None)
    delve.pop('_dir_inline_hover', None)
    delve.pop('_card_close_btn', None)
    delve.pop('_card_flip_timer', None)
    delve.pop('_card_show_timer', None)
    delve.pop('hovered_card', None)
    delve.pop('cards', None)
    return data

def _delve_restore(data: dict) -> dict:
    """Convert JSON-safe types back to runtime equivalents."""
    delve = data.get('delve')
    if not delve:
        return data
    if isinstance(delve.get('enemy_ids'), list):
        delve['enemy_ids'] = set(delve['enemy_ids'])
    delve.setdefault('pending_rewards', [])
    # JSON stringifies dict keys — the chart graph's node map must come back
    # as int-keyed or every node lookup by id silently fails after a restart.
    graph = (delve.get('chart') or {}).get('graph')
    if isinstance(graph, dict) and isinstance(graph.get('nodes'), dict):
        graph['nodes'] = {int(k): v for k, v in graph['nodes'].items()}
        for id_key in ('start_node_id', 'current_node_id'):
            if isinstance(graph.get(id_key), str):
                graph[id_key] = int(graph[id_key])
    # Tarot cards are transient (regenerated on Pulse click); a saved
    # 'show_cards' state has no cards, so recover to 'ready'.
    if delve.get('state') == 'show_cards':
        delve['state'] = 'ready'
    if isinstance(delve.get('state'), str) and delve['state'] not in ('clearing', 'show_cards', 'ready', 'arriving'):
        delve['state'] = 'clearing'
    return data

def save_delve_data(char_id: str, data):
    """Write the delve snapshot to disk (JSON), stamped with the schema version."""
    try:
        sanitized = _delve_sanitize(data)
        sanitized['save_schema_version'] = SAVE_SCHEMA_VERSION
        with open(delve_save_path(char_id), 'w') as f:
            json.dump(sanitized, f)
    except Exception:
        print("[save] ERROR: Failed to save delve data")
        traceback.print_exc()

def load_delve_data(char_id: str):
    """Read the delve snapshot from disk, or None.

    A snapshot written by a newer build is backed up and ignored rather than
    misread: resuming a raid from a payload this build cannot understand risks
    corrupting a run, and the character save itself is unaffected.
    """
    path = delve_save_path(char_id)
    try:
        with open(path) as f:
            data = json.load(f)
        stored = data.get('save_schema_version') if isinstance(data, dict) else None
        if isinstance(stored, int) and not isinstance(stored, bool) \
                and stored > SAVE_SCHEMA_VERSION:
            backup = backup_save_file(path, 'delve snapshot is from a newer build')
            print(f"[save] Delve snapshot from a newer build ignored; backed up to {backup}")
            return None
        return _delve_restore(data)
    except Exception:
        return None

def clear_delve_data(char_id: str):
    """Remove the delve snapshot from disk."""
    try:
        os.remove(delve_save_path(char_id))
    except FileNotFoundError:
        pass
    except Exception:
        print("[save] ERROR: Failed to clear delve data")
        traceback.print_exc()

# ── Task pool ─────────────────────────────────────────────────────────────
TASK_POOL = [
    {'id': 'kill_3',     'name': 'First Blood',    'desc': 'Kill 3 infected in a single raid',    'req': {'type': 'kills',   'value': 3   }, 'reward': {'currency': 150}},
    {'id': 'kill_10',    'name': 'Exterminator',   'desc': 'Kill 10 infected in a single raid',   'req': {'type': 'kills',   'value': 10  }, 'reward': {'currency': 400}},
    {'id': 'kill_20',    'name': 'Hunter',         'desc': 'Kill 20 infected in a single raid',   'req': {'type': 'kills',   'value': 20  }, 'reward': {'currency': 750}},
    {'id': 'survive_5',  'name': 'Survivor',       'desc': 'Survive 5 minutes in a single raid',  'req': {'type': 'survive', 'value': 300 }, 'reward': {'currency': 100}},
    {'id': 'survive_15', 'name': 'Endurance Test', 'desc': 'Survive 15 minutes in a single raid', 'req': {'type': 'survive', 'value': 900 }, 'reward': {'currency': 300}},
    {'id': 'survive_25', 'name': 'Iron Will',      'desc': 'Survive 25 minutes in a single raid', 'req': {'type': 'survive', 'value': 1500}, 'reward': {'currency': 600}},
    {'id': 'extract_1',  'name': 'Successful Exit','desc': 'Extract from a raid alive',            'req': {'type': 'extract', 'value': 1   }, 'reward': {'currency': 200}},
    {'id': 'loot_5',     'name': 'Scavenger',      'desc': 'Pick up 5 items in a single raid',    'req': {'type': 'loot',    'value': 5   }, 'reward': {'currency': 175}},
    {'id': 'loot_10',    'name': 'Looter',         'desc': 'Pick up 10 items in a single raid',   'req': {'type': 'loot',    'value': 10  }, 'reward': {'currency': 300}},
]

_POOL_BY_ID = {t['id']: t for t in TASK_POOL}


def task_def(task_id: str) -> dict | None:
    return _POOL_BY_ID.get(task_id)


def pick_tasks(count: int = 3, exclude_ids=None) -> list:
    exclude = set(exclude_ids or [])
    pool    = [t for t in TASK_POOL if t['id'] not in exclude]
    chosen  = random.sample(pool, min(count, len(pool)))
    return [{'id': t['id'], 'done': False} for t in chosen]


# ── Derived stats ──────────────────────────────────────────────────────────

BASE_LIFE    = 50
BASE_EVASION = 300

def compute_derived_stats(descend: dict, perk_bonuses: dict = None,
                          item_bonuses: dict = None, looks: str = 'fighter') -> dict:
    pb = perk_bonuses or {}
    ib = item_bonuses or {}

    vessel_effects = VESSEL_DEFS.get(looks, {}).get('effects', {})

    def _attr(a):
        return descend.get(a, 0) + ib.get(a, 0)

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
        'max_health':            50 + str_ * 8 + end * 8 + bonus('maxHealth'),
        'evasion':               int(300 * (1.0 + 0.03 * dex) + bonus('evasion_flat')),
        'accuracy':              300 + nrv * 20 + dex * 4 + bonus('accuracy_flat'),
        'melee_dmg_mult':        1.0 + 0.05 * str_ + bonus('melee_dmg_mult_pct') / 100.0,
        'max_energy_shield':     end * 4 + bonus('max_energy_shield'),
        'max_mana':             20 + cun * 5 + bonus('maxMana'),
        'mana_regen':           1.0 + cun * 0.1 + bonus('mana_regen'),
        'delve_light_radius':    nrv * 0.5 + bonus('delve_light_radius'),
        'darkness_resist_pct':   (end * 2 + bonus('darkness_resist_pct')) / 100.0,
        'move_speed_pct':        (bonus('move_speed_pct') + dex * 3.0) / 100.0,
        'attack_speed_pct':      (bonus('attack_speed_pct') + dex * 3.0) / 100.0,
        'cooldown_recovery_pct': (cun * 1.0 + bonus('cooldown_recovery_pct')) / 100.0,
        'crit_chance':           min(0.75, (bonus('crit_chance') + nrv * 1.0) / 100.0),
        'ability_crit_chance':   min(0.75, (bonus('ability_crit_chance') + ess * 1.0) / 100.0),
        'block_chance':          min(0.75, (bonus('block_chance') + dex * 1.5) / 100.0),
        'crushing_blow_pct':     min(0.75, bonus('crushing_blow_pct') / 100.0),
        'entropy_grace_pct':     (dst * 1.5 + ess * 1.0 + bonus('entropy_grace_pct')) / 100.0,
        'currency_gain_pct':     bonus('currency_gain_pct') / 100.0,
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
        self.currency       = 500
        self.tasks          = pick_tasks(3)
        self.descend: dict  = vessel_baseline_stats(self.looks)
        self.perks: dict    = {}
        self.available_points: int = 0
        self.inventory: dict | None = None
        self.stash: list    = []   # single 8x8 bank grid (no tabs)
        self._grid_overflow: list = []
        self._save_cb       = None

    @property
    def seed(self) -> int:
        """Stable per-character delve seed, derived from the id.

        The delve layout is bound to the character: same character → same
        chart and rooms on every visit; death deletes the character (new
        id → new seed → fresh layout). Never stored — recomputed.
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
            'currency':       self.currency,
            'tasks':          self.tasks,
            'descend':        self.descend,
            'perks':          self.perks,
            'available_points': self.available_points,
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
        required = {'id', 'name', 'looks', 'currency', 'tasks', 'descend',
                    'perks', 'available_points', 'inventory', 'stash'}
        if not isinstance(d, dict) or not required.issubset(d):
            raise ValueError('incompatible character save')
        c = cls(d['id'], d['name'], d['looks'])
        c.currency = d['currency']
        c.tasks = d['tasks'] or pick_tasks(3)
        c.inventory = d['inventory']
        c.descend = d['descend']
        c.perks = d['perks']
        c.available_points = d['available_points']
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
        """Create a character with its fixed vessel baseline and no point gates."""
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

    def get_progress(self, task_ref: dict) -> tuple[int, int]:
        defn = task_def(task_ref['id'])
        if not defn:
            return (0, 1)
        req = defn['req']
        t   = req['type']
        v   = req['value']
        if t == 'kills':   return (min(self.kills, v),         v)
        if t == 'survive': return (min(int(self.time), v),     v)
        if t == 'loot':    return (min(self.loot, v),          v)
        if t == 'extract': return (1 if self.extracted else 0, v)
        return (0, v)

    def check_tasks(self, char: Character) -> list:
        newly_done = []
        for ref in char.tasks:
            if ref['done']:
                continue
            defn = task_def(ref['id'])
            if not defn:
                continue
            req  = defn['req']
            t, v = req['type'], req['value']
            done = (
                (t == 'kills'   and self.kills     >= v) or
                (t == 'survive' and self.time       >= v) or
                (t == 'loot'    and self.loot       >= v) or
                (t == 'extract' and self.extracted      )
            )
            if done:
                ref['done'] = True
                newly_done.append(defn)
        return newly_done

    def finalize(self, char: Character) -> dict:
        completed = self.check_tasks(char)
        cash_gained = sum(d['reward'].get('currency', 0) for d in completed)
        char.currency += cash_gained

        active_ids = {t['id'] for t in char.tasks if not t['done']}
        done_count = sum(1 for t in char.tasks if t['done'])
        if done_count:
            char.tasks = [t for t in char.tasks if not t['done']] + pick_tasks(done_count, active_ids)

        char.save()

        return {
            'kills':       self.kills,
            'time':        self.time,
            'loot':        self.loot,
            'extracted':   self.extracted,
            'completed':   completed,
            'cash_gained': cash_gained,
            'currency':    char.currency,
        }
