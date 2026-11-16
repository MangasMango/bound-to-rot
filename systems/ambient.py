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

"""Ambient delve particles (issue #17).

Two layers of world-space atmosphere, driven per sim tick and drawn as
screen-space point markers by the anima renderer:

  * ``smoke``  - slow wisps rising from lit torch decor, growing and
                 fading as they climb (torch = the lit-campfire atlas
                 crop ``_spawn_anima_objects`` places);
  * ``dust``   - tiny motes drifting inside lit ground (around the
                 player's own light and each torch), with a slow alpha
                 pulse.

Particles are runtime VFX (not map data), so they use the level RNG and
live in a small fixed budget - the caps below are hard limits, emission
simply stops while the budget is full.
"""

import math

import pyray as rl

MAX_SMOKE   = 48
MAX_DUST    = 24
SMOKE_LIFE  = 3.4      # seconds a wisp lives
DUST_LIFE   = 7.0      # seconds a mote lives
SMOKE_INTERVAL = 1.1   # per-torch emission cadence (seconds)
DUST_INTERVAL  = 0.55  # dust respawn cadence (seconds)
DUST_RADIUS    = 2.6   # lit-ground radius (tiles) around a source

# world-units/tile particle motion
SMOKE_RISE   = 0.11    # vertical climb per second
SMOKE_DRIFT  = 0.04    # horizontal wander per second
DUST_DRIFT   = 0.08


def _wobble(phase: float, t: float, amp: float) -> float:
    """Two smooth sine harmonics - drift that never traces a circle."""
    return (amp * math.sin(t * 0.9 + phase)
            + amp * 0.6 * math.sin(t * 2.3 + phase * 1.7))


# ── soft sprite textures (built lazily once a GL context exists) ──────

def _soft_disc_texture(size: int, hardness: float = 2.2):
    """Radial-falloff white puff - no hard edges for the renderer to tint.

    hardness>1 keeps a soft core; pure 1.0 would be a hard circle again."""
    img = rl.gen_image_color(size, size, rl.BLANK)
    half = size / 2 - 0.5
    for pixel_y in range(size):
        for pixel_x in range(size):
            dist = math.hypot(pixel_x - half, pixel_y - half) / half
            if dist >= 1.0:
                continue
            alpha = int(255 * max(0.0, 1.0 - dist) ** hardness)
            if alpha > 0:
                rl.image_draw_pixel(img, pixel_x, pixel_y,
                                    rl.Color(255, 255, 255, alpha))
    tex = rl.load_texture_from_image(img)
    rl.unload_image(img)
    if tex and tex.id > 0:
        rl.set_texture_filter(tex, rl.TEXTURE_FILTER_BILINEAR)
    return tex


class AmbientParticles:
    """Budgeted particle pool + per-source emission timers."""

    def __init__(self):
        self.particles: list[dict] = []
        self.time = 0.0
        self._dust_timer = 0.0
        self._puff_tex  = None    # soft smoke sprite, built on first draw
        self._mote_tex  = None    # soft dust sprite

    def dispose(self):
        """Free the cached soft sprites (VRAM cleanup order, rule 43)."""
        for attr in ('_puff_tex', '_mote_tex'):
            tex = getattr(self, attr, None)
            if tex and tex.id > 0:
                rl.unload_texture(tex)
            setattr(self, attr, None)

    def clear(self):
        """Drop all particles (scene change / anima exit)."""
        self.particles = []
        self.time = 0.0
        self._dust_timer = 0.0

    def update(self, dt, rng, torch_spots, light_x, light_y):
        """Emit, advance and cull. ``torch_spots`` is the list of (x, y)
        world positions of lit torch decor (re-read every tick so it can
        never go stale); ``light_x/y`` is the player's light anchor."""
        self.time += dt

        # ── smoke: one wisp per torch per SMOKE_INTERVAL, phase-staggered ──
        for idx, (tx, ty) in enumerate(torch_spots):
            phase = (idx * 0.37 + self.time / SMOKE_INTERVAL) % 1.0
            if phase * SMOKE_INTERVAL <= dt and len(self.particles) < MAX_SMOKE:
                self._spawn_smoke(tx, ty, rng)

        # ── dust: motes respawn around lit ground on a shared cadence ──
        self._dust_timer -= dt
        if self._dust_timer <= 0.0:
            self._dust_timer = DUST_INTERVAL
            if sum(1 for p in self.particles if p['kind'] == 'dust') < MAX_DUST:
                anchors = [(light_x, light_y)] + list(torch_spots)
                ax, ay = anchors[rng.randrange(len(anchors))]
                ang = rng.uniform(0.0, math.tau)
                dist = rng.uniform(0.3, DUST_RADIUS)
                self._spawn_dust(ax + math.cos(ang) * dist,
                                 ay + math.sin(ang) * dist, rng)

        # ── advance + cull ────────────────────────────────────────────
        live = []
        for p in self.particles:
            p['life'] -= dt
            if p['life'] <= 0.0:
                continue
            p['x'] += (p['vx'] + _wobble(p['phase'], self.time, p['wob'])) * dt
            p['y'] += (p['vy'] + _wobble(p['phase'] + 1.3, self.time,
                                         p['wob'])) * dt
            p['z'] += p['vz'] * dt
            live.append(p)
        self.particles = live

    # ── spawners ──────────────────────────────────────────────────────

    def _spawn_smoke(self, x, y, rng):
        self.particles.append({
            'kind': 'smoke',
            'x': x + rng.uniform(-0.08, 0.08),
            'y': y + rng.uniform(-0.08, 0.08),
            'z': 0.12,
            'vx': rng.uniform(-SMOKE_DRIFT, SMOKE_DRIFT),
            'vy': rng.uniform(-SMOKE_DRIFT, SMOKE_DRIFT),
            'vz': SMOKE_RISE * rng.uniform(0.8, 1.2),
            'wob': 0.05,
            'life': SMOKE_LIFE,
            'max_life': SMOKE_LIFE,
            'size': rng.uniform(0.5, 0.7),     # peak puff, fraction of tile
            'spin': rng.uniform(-0.5, 0.5),    # slow sprite rotation
            'phase': rng.uniform(0.0, math.tau),
        })

    def _spawn_dust(self, x, y, rng):
        self.particles.append({
            'kind': 'dust',
            'x': x,
            'y': y,
            'z': rng.uniform(0.15, 0.55),
            'vx': rng.uniform(-DUST_DRIFT, DUST_DRIFT),
            'vy': rng.uniform(-DUST_DRIFT, DUST_DRIFT),
            'vz': 0.0,
            'wob': 0.07,
            'life': DUST_LIFE * rng.uniform(0.7, 1.0),
            'max_life': DUST_LIFE,
            'size': rng.uniform(0.05, 0.08),
            'spin': 0.0,
            'phase': rng.uniform(0.0, math.tau),
        })
