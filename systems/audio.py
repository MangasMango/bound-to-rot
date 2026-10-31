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
Audio system - loads all sound pools once, exposes simple play calls.

Music: every scene state maps to one track, and every transition is a
CROSSFADE (old stream fades out while the new one fades in - never an
instant stop). States:

    menu        Western menu               main menu + title screen
    (loading)   off - silence while the loading screen runs
    hub         Settlers Caravan           the Hub
    death       Western guitar stab        permadeath screen
    game        western_ingame playlist    the delve - the three in-game
                western_ingame1/2/3.ogg    tracks play one after another,
                continuously (crossfaded end-to-end, endless loop) and are
                NEVER re-triggered by waves, depths or node choices.

    (retired tracks were removed; current soundtrack licences live in
    assets/ost/credits.txt)
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
    'menu':       'ost/Western_menu.ogg',
    'hub':        'ost/western_hub.ogg',
    'death':      'ost/westernguitarstab.ogg',
}
# The delve playlist - plays continuously, one after another, forever.
_GAME_PLAYLIST = (
    'ost/western_ingame1.ogg',
    'ost/western_ingame2.ogg',
    'ost/western_ingame3.ogg',
)
GAME_MUSIC_STATE = 'game'   # logical state name for the delve playlist

FADE_SECONDS = 2.5    # crossfade length for every music transition


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
        self._file_streams = {}   # asset path -> single shared music stream
        self._music_state = 'off'
        self._music_ready = False
        self._fades       = []   # [{'music': stream, 'vol': cur, 'target': tgt}]

        self._playlist_streams = []   # shared streams, _GAME_PLAYLIST order
        self._playlist_index   = 0

        self._step_t      = 0.0
        self._enemy_t     = {}
        self._enemy_alert = set()

    # ── init ─────────────────────────────────────────────────────────

    def init_music(self):
        # One stream PER FILE, shared by the states that use it - loading
        # the same file once per state would run six independent copies
        # of the same track against each other during crossfades.
        for name, rel in _MUSIC_FILES.items():
            stream = self._file_streams.get(rel)
            if stream is None:
                stream = self._load_music(rel)
                self._file_streams[rel] = stream
            if stream is not None:
                self._music[name] = stream
        # Delve playlist - every track loaded once, in playlist order
        self._playlist_streams = []
        for rel in _GAME_PLAYLIST:
            stream = self._file_streams.get(rel)
            if stream is None:
                stream = self._load_music(rel)
                self._file_streams[rel] = stream
            if stream is not None:
                self._playlist_streams.append(stream)
        # UI clicks
        self._load_pool_a('ui_click', [f'ui-sfx/click1.ogg'])
        self._load_pool_a('ui_hover', [f'ui-sfx/rollover1.ogg'])
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

        # Gunslinger - revolver shot + bullet impacts on undead (bone crack)
        self._load_pool_a('revolver_shot', ['ingame-sfx/revolverShoot1.ogg'])
        self._load_pool_a('bullet_impact', [f'ingame-sfx/impactGlass_heavy_{i:03d}.ogg'
                                            for i in range(5)])
        self._load_pool_a('bullet_impact', [f'ingame-sfx/impactGlass_heavy_{i:03d}.ogg'
                                            for i in range(5)])

        # Crate destruction
        self._load_pool_a('crate_break', [f'ingame-sfx/impactWood_heavy_{i:03d}.ogg' for i in range(5)] +
                                          [f'ingame-sfx/impactPlank_medium_{i:03d}.ogg' for i in range(5)])

        # Item landing on ground (staggered drops from crate)
        self._load_pool_a('item_land', [f'ingame-sfx/impactSoft_heavy_{i:03d}.ogg' for i in range(5)])

    # ── helpers ──────────────────────────────────────────────────────

    def _load_music(self, rel):
        """Load a music stream by asset-relative path; None when missing."""
        path = _a(rel)
        if os.path.exists(path):
            return rl.load_music_stream(path)
        return None

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
        # apply to every audible stream - respecting any in-flight fade so
        # the settings slider can't fight the crossfade (it runs every tick)
        for m in list(self._music.values()) + list(self._playlist_streams):
            if rl.is_music_stream_playing(m):
                vol = 1.0
                for f in self._fades:
                    if f['music'] is m:
                        vol = f['vol']
                        break
                rl.set_music_volume(m, vol * self.music_vol)

    def set_music_state(self, state: str):
        """Scene-state music with a crossfade: the old track fades out while
        the new one fades in (FADE_SECONDS each way) - never an instant stop.
        State 'game' is the delve playlist: entering it RESTARTS the playlist
        at the first track (owner ruling), and track-to-track switching is
        then driven purely by track ends in tick() - never by gameplay."""
        if not self._music_ready:
            self._music_state = state
            return
        if state == self._music_state:
            return
        if state == GAME_MUSIC_STATE:
            self._playlist_index = 0   # entering the delve restarts the list
        self._crossfade_to(state)
        self._music_state = state

    def set_delve_music(self):
        """Delve music - the continuous western playlist."""
        self.set_music_state(GAME_MUSIC_STATE)

    def _state_stream(self, state: str):
        """The single stream a logical state plays right now ('game' resolves
        to the playlist track at the current index)."""
        if state == GAME_MUSIC_STATE:
            if not self._playlist_streams:
                return None
            return self._playlist_streams[self._playlist_index % len(self._playlist_streams)]
        return None if state == 'off' else self._music.get(state)

    def _crossfade_to(self, state: str):
        # `_music` is keyed by LOGICAL STATE NAME ('menu', 'hub', …) and the
        # delve playlist lives in _playlist_streams - resolve the target
        # stream, then every stream keeps EXACTLY ONE fader: the incoming
        # track fades in (target 1.0), every other stream fades out
        # (target 0.0), retargeting mid-fade streams in place so a cut never
        # restarts a fade from zero.
        self._crossfade_streams(self._state_stream(state))

    def _crossfade_streams(self, target):
        for f in self._fades:
            f['target'] = 1.0 if f['music'] is target else 0.0
        for m in list(self._music.values()) + list(self._playlist_streams):
            if any(m is f['music'] for f in self._fades):
                continue                      # already fading (either way)
            if target is not None and m is target:
                rl.set_music_volume(m, 0.0)
                if not rl.is_music_stream_playing(m):
                    rl.play_music_stream(m)
                    rl.seek_music_stream(m, 0.0)   # restart from the top
                self._fades.append({'music': m, 'vol': 0.0, 'target': 1.0})
            elif rl.is_music_stream_playing(m):
                self._fades.append({'music': m, 'vol': 1.0, 'target': 0.0})

    def _advance_playlist(self):
        """Track ended - start the next one with a crossfade, wrapping
        around the playlist endlessly."""
        if not self._playlist_streams:
            return
        self._playlist_index = (self._playlist_index + 1) % len(self._playlist_streams)
        self._crossfade_streams(self._state_stream(GAME_MUSIC_STATE))

    def tick(self, dt):
        for m in self._music.values():
            if rl.is_music_stream_playing(m):
                rl.update_music_stream(m)
        for m in self._playlist_streams:
            if rl.is_music_stream_playing(m):
                rl.update_music_stream(m)
        remaining = []
        for f in self._fades:
            f['vol'] = fade_step(f['vol'], f['target'], dt, FADE_SECONDS)
            rl.set_music_volume(f['music'], f['vol'] * self.music_vol)
            if f['vol'] == f['target']:
                if f['target'] == 0.0:
                    rl.stop_music_stream(f['music'])
                continue          # fade complete - volume pinned, drop fader
            remaining.append(f)
        self._fades = remaining
        # Continuous delve playlist of last resort: while in the delve the
        # playlist is the ONLY music driver - when the current track ends
        # (and nothing is fading), roll to the next one, forever.
        if (self._music_state == GAME_MUSIC_STATE and not self._fades
                and self._playlist_index < len(self._playlist_streams)):
            stream = self._state_stream(GAME_MUSIC_STATE)
            if stream is not None and not rl.is_music_stream_playing(stream):
                self._advance_playlist()

    # ── UI sounds ────────────────────────────────────────────────────

    def ui_click(self):
        self._play_random('ui_click', 0.5)

    def ui_hover(self):
        self._play_random('ui_hover', 0.25)

    # ── hit / impact ─────────────────────────────────────────────────

    def hitmarker(self):
        self._play_random('hitmark', 0.8)

    def revolver_shot(self):
        self._play_random('revolver_shot', 0.85)

    def bullet_impact(self):
        self._play_random('bullet_impact', 0.8)

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
        """Run start: clear run-local SFX state. Music is deliberately NOT
        touched - stream starts/stops belong to the crossfade machinery
        (set_music_state), never a hard stop."""
        self._enemy_alert.clear()
        self._enemy_t.clear()
        self._step_t = 0.0

    def cleanup(self):
        for s in self.sounds.values():
            rl.unload_sound(s)
        for pool in self.pools.values():
            for s in pool:
                rl.unload_sound(s)
        for m in list(self._music.values()) + list(self._playlist_streams):
            rl.unload_music_stream(m)
