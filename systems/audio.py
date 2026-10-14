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

from config import ASSETS
"""
Audio system — loads all sound pools once, exposes simple play calls.

Music: every scene state maps to one track, and every transition is a
CROSSFADE (old stream fades out while the new one fades in — never an
instant stop). States (BLUEPRINT §25):

    menu        WAV_End_of_the_Road_Full     main menu
    (loading)   off — silence while the loading screen runs
    hub         WAV_Unyielding_Undying_Full  the Hub
    death       WAV_End_of_the_Road_B        permadeath screen
    wilds_N     WAV_Hexed_Wilds_A/B/C        Anima combat, depth-rotated
    pulse_wait  WAV_Dark_Alleys_Full         wave cleared, node not chosen yet
"""

import os
import random
import pyray as rl

_PUBLIC = os.path.join(os.path.dirname(__file__), 'public')
_ASSETS = ASSETS

def _p(rel):  return os.path.join(_PUBLIC, rel)
def _a(rel):  return os.path.join(_ASSETS, rel)

# Track registry: logical music state -> asset path (relative to assets/).
_MUSIC_FILES = {
    'menu':       'ost/WAV_End_of_the_Road_Full.wav',
    'hub':        'ost/WAV_Unyielding_Undying_Full.wav',
    'death':      'ost/WAV_End_of_the_Road_B.wav',
    'pulse_wait': 'ost/WAV_Dark_Alleys_Full.wav',
    'wilds_1':    'ost/WAV_Hexed_Wilds_A.wav',
    'wilds_2':    'ost/WAV_Hexed_Wilds_B.wav',
    'wilds_3':    'ost/WAV_Hexed_Wilds_C.wav',
}

FADE_SECONDS = 2.5    # crossfade length for every music transition


def wilds_key_for_depth(depth: int) -> str:
    """Anima combat track for a depth: 1->A, 2->B, 3->C, 4->A again…"""
    return f'wilds_{((max(1, int(depth)) - 1) % 3) + 1}'


def fade_step(vol: float, target: float, dt: float, seconds: float) -> float:
    """Move `vol` toward `target` by a full fade's fraction of dt."""
    step = dt / max(0.001, seconds)
    if vol < target:
        return min(target, vol + step)
    return max(target, vol - step)


class AudioSystem:
    def __init__(self):
        self.sounds    = {}
        self.pools     = {}
        self.master    = 0.8
        self.music_vol = 0.4

        self._music       = {}
        self._music_state = 'off'
        self._music_ready = False
        self._fades       = []   # [{'music': stream, 'vol': cur, 'target': tgt}]

        self._step_t      = 0.0
        self._enemy_t     = {}
        self._enemy_alert = set()

    # ── init ─────────────────────────────────────────────────────────

    def init_music(self):
        for name, rel in _MUSIC_FILES.items():
            self._load_music_a(name, rel)
        # UI clicks
        self._load_pool_a('ui_click', [f'ui-sfx/click{i}.ogg' for i in range(1, 6)])
        self._load_pool_a('ui_hover', [f'ui-sfx/rollover{i}.ogg' for i in range(1, 7)])
        self._music_ready = True

    def init(self):
        # Melee hit / hitmarker
        self._load_pool_a('hitmark', ['ingame-sfx/impactPlate_heavy_000.ogg', 'ingame-sfx/impactPlate_heavy_001.ogg'])


        # Footsteps
        self._load_pool_a('footstep', ['ingame-sfx/footstep_concrete_000.ogg'])

        # Item handling
        self._load_pool_a('item_pickup', ['ingame-sfx/handleSmallLeather.ogg',
                                          'ingame-sfx/handleSmallLeather2.ogg',
                                          'ingame-sfx/cloth1.ogg', 'ingame-sfx/cloth2.ogg'])
        self._load_pool_a('item_drop',   ['ingame-sfx/dropLeather.ogg', 'ingame-sfx/cloth3.ogg'])
        self._load_pool_a('item_equip',  ['ingame-sfx/beltHandle1.ogg', 'ingame-sfx/beltHandle2.ogg',
                                          'ingame-sfx/clothBelt.ogg',   'ingame-sfx/clothBelt2.ogg'])

        # Inventory open / close
        self._load_a('inv_open',  'ingame-sfx/bookOpen.ogg')
        self._load_a('inv_close', 'ingame-sfx/bookClose.ogg')
        self._load_pool_a('inv_flip', ['ingame-sfx/bookFlip1.ogg',
                                       'ingame-sfx/bookFlip2.ogg',
                                       'ingame-sfx/bookFlip3.ogg'])

        # Enemy hurt / death
        self._load_pool_a('enemy_hurt', ['ingame-sfx/metalPot1.ogg', 'ingame-sfx/metalPot2.ogg'])
        self._load_a('enemy_dead', 'ingame-sfx/metalPot3.ogg')

        # Enemy melee hit on player
        self._load_a('enemy_hit', 'ingame-sfx/impactPunch_medium_000.ogg')

        # Crate destruction
        self._load_pool_a('crate_break', [f'ingame-sfx/impactWood_heavy_{i:03d}.ogg' for i in range(5)] +
                                          [f'ingame-sfx/impactPlank_medium_{i:03d}.ogg' for i in range(5)])

        # Item landing on ground (staggered drops from crate)
        self._load_pool_a('item_land', [f'ingame-sfx/impactSoft_heavy_{i:03d}.ogg' for i in range(5)])

    # ── helpers ──────────────────────────────────────────────────────

    def _load_music(self, name, rel):
        path = _p(rel)
        if os.path.exists(path):
            self._music[name] = rl.load_music_stream(path)

    def _load_music_a(self, name, rel):
        path = _a(rel)
        if os.path.exists(path):
            self._music[name] = rl.load_music_stream(path)

    def _load(self, name, rel):
        path = _p(rel)
        if os.path.exists(path):
            self.sounds[name] = rl.load_sound(path)

    def _load_a(self, name, rel):
        path = _a(rel)
        if os.path.exists(path):
            self.sounds[name] = rl.load_sound(path)

    def _load_pool_a(self, name, rels):
        pool = []
        for rel in rels:
            path = _a(rel)
            if os.path.exists(path):
                pool.append(rl.load_sound(path))
        if pool:
            self.pools[name] = pool

    def _play(self, name, vol=1.0):
        s = self.sounds.get(name)
        if s:
            rl.set_sound_volume(s, vol * self.master)
            rl.play_sound(s)

    def _play_random(self, pool_name, vol=1.0):
        pool = self.pools.get(pool_name)
        if pool:
            s = random.choice(pool)
            rl.set_sound_volume(s, vol * self.master)
            rl.play_sound(s)

    # ── volume / music state ─────────────────────────────────────────

    def set_sfx_volume(self, v: float):
        self.master = max(0.0, min(1.0, v))

    def set_music_volume(self, v: float):
        self.music_vol = max(0.0, min(1.0, v))
        # apply to every audible stream — respecting any in-flight fade so
        # the settings slider can't fight the crossfade (it runs every tick)
        for m in self._music.values():
            if rl.is_music_stream_playing(m):
                vol = 1.0
                for f in self._fades:
                    if f['music'] is m:
                        vol = f['vol']
                        break
                rl.set_music_volume(m, vol * self.music_vol)

    def set_music_state(self, state: str):
        """Scene-state music with a crossfade: the old track fades out while
        the new one fades in (FADE_SECONDS each way) — never an instant stop."""
        if not self._music_ready:
            self._music_state = state
            return
        if state == self._music_state:
            return
        self._crossfade_to(state)
        self._music_state = state

    def set_delve_depth_music(self, depth: int):
        """Anima combat music — Hexed Wilds A/B/C rotated by depth."""
        self.set_music_state(wilds_key_for_depth(depth))

    def set_pulse_wait_music(self):
        """Wave cleared and no node selected yet — Dark Alleys."""
        self.set_music_state('pulse_wait')

    def _crossfade_to(self, state: str):
        # `_music` is keyed by LOGICAL STATE NAME ('menu', 'hub', 'wilds_1'…)
        # — look the stream up by state, not by its file path. Every stream
        # keeps EXACTLY ONE fader: the incoming track fades in (target 1.0),
        # every other stream fades out (target 0.0), retargeting mid-fade
        # streams in place so a cut never restarts a fade from zero.
        target = None if state == 'off' else self._music.get(state)
        for f in self._fades:
            f['target'] = 1.0 if f['music'] is target else 0.0
        for m in self._music.values():
            if any(m is f['music'] for f in self._fades):
                continue                      # already fading (either way)
            if m is target:
                rl.set_music_volume(m, 0.0)
                if not rl.is_music_stream_playing(m):
                    rl.play_music_stream(m)
                    rl.seek_music_stream(m, 0.0)   # restart from the top
                self._fades.append({'music': m, 'vol': 0.0, 'target': 1.0})
            elif rl.is_music_stream_playing(m):
                self._fades.append({'music': m, 'vol': 1.0, 'target': 0.0})

    def tick(self, dt):
        for m in self._music.values():
            if rl.is_music_stream_playing(m):
                rl.update_music_stream(m)
        remaining = []
        for f in self._fades:
            f['vol'] = fade_step(f['vol'], f['target'], dt, FADE_SECONDS)
            rl.set_music_volume(f['music'], f['vol'] * self.music_vol)
            if f['vol'] == f['target']:
                if f['target'] == 0.0:
                    rl.stop_music_stream(f['music'])
                continue          # fade complete — volume pinned, drop fader
            remaining.append(f)
        self._fades = remaining

    # ── UI sounds ────────────────────────────────────────────────────

    def ui_click(self):
        self._play_random('ui_click', 0.5)

    def ui_hover(self):
        self._play_random('ui_hover', 0.25)

    # ── hit / impact ─────────────────────────────────────────────────

    def hitmarker(self):
        self._play_random('hitmark', 0.8)

    # ── world sounds ─────────────────────────────────────────────────

    def item_pickup(self):
        self._play_random('item_pickup', 0.6)

    def item_drop(self):
        self._play_random('item_drop', 0.6)

    def crate_break(self):
        self._play_random('crate_break', 0.75)

    def item_land(self):
        self._play_random('item_land', 0.35)

    def item_equip(self):
        self._play_random('item_equip', 0.65)

    def inv_open(self):
        self._play('inv_open', 0.5)

    def inv_close(self):
        self._play('inv_close', 0.5)

    def inv_flip(self):
        self._play_random('inv_flip', 0.35)

    # ── enemy sounds ─────────────────────────────────────────────────

    def enemy_hurt(self):
        self._play_random('enemy_hurt', 0.7)

    def enemy_dead(self):
        self._play('enemy_dead', 0.8)

    def enemy_attack_sound(self):
        self._play('enemy_hit', 0.8)

    # back-compat aliases
    def zombie_hurt(self):         self.enemy_hurt()
    def zombie_dead(self):         self.enemy_dead()
    def zombie_attack_sound(self): self.enemy_attack_sound()
    # ── per-frame update ─────────────────────────────────────────────

    def update(self, dt, enemies, is_moving, is_sprinting):
        self._update_footsteps(dt, is_moving, is_sprinting)

    def _update_footsteps(self, dt, is_moving, is_sprinting):
        if not is_moving:
            self._step_t = 0.0
            return
        interval = 0.28 if is_sprinting else 0.42
        self._step_t += dt
        if self._step_t >= interval:
            self._step_t = 0.0
            self._play_random('footstep', 0.45)

    def reset(self):
        """Run start: stop every stream and clear fade state."""
        self._enemy_alert.clear()
        self._enemy_t.clear()
        self._step_t = 0.0
        self._fades  = []
        for m in self._music.values():
            if rl.is_music_stream_playing(m):
                rl.stop_music_stream(m)

    def cleanup(self):
        for s in self.sounds.values():
            rl.unload_sound(s)
        for pool in self.pools.values():
            for s in pool:
                rl.unload_sound(s)
        for m in self._music.values():
            rl.unload_music_stream(m)
