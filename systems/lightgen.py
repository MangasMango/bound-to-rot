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

"""Procedural textures for the fire-light shader (generated at load, no
asset files). The numpy arrays are GL-free and unit-testable; game.py turns
them into raylib textures.
"""

import numpy as np


def make_light_noise(size: int = 256, seed: int = 1337) -> np.ndarray:
    """Tileable two-octave value noise as (size, size, 4) uint8 RGBA.

    Built from periodic box blurs (np.roll wraps, so the texture tiles
    seamlessly for the shader's REPEAT sampling).
    """
    rng = np.random.default_rng(seed)
    base = rng.random((size, size)).astype(np.float32)

    def blur_wrap(img: np.ndarray, k: int) -> np.ndarray:
        out = img.copy()
        for off in range(1, k + 1):
            out += (np.roll(img, off, 0) + np.roll(img, -off, 0)
                    + np.roll(img, off, 1) + np.roll(img, -off, 1))
        return out / (4 * k + 1)

    fine  = blur_wrap(base, 3)      # flame detail
    large = blur_wrap(base, 24)     # broad churn
    noise = np.clip(fine * 0.55 + large * 0.75, 0.0, 1.0)

    rgba = np.empty((size, size, 4), dtype=np.uint8)
    rgba[..., 0] = (noise * 255).astype(np.uint8)
    rgba[..., 1] = rgba[..., 0]
    rgba[..., 2] = rgba[..., 0]
    rgba[..., 3] = 255
    return rgba


# Fire gradient stops: amount → (r, g, b). Deep ember red at the tail,
# near-white hot core.
_CURVE_STOPS = [
    (0.00, ( 10,   0,   0)),
    (0.25, (140,  20,   5)),
    (0.30, (255,  90,  15)),
    (0.50, (255, 180,  60)),
    (1.00, (255, 240, 190)),
]


def make_fire_curve(stops=None, width: int = 64) -> np.ndarray:
    """Fire color curve LUT as (1, width, 4) uint8 RGBA (Godot colo_curve)."""
    stops = _CURVE_STOPS if stops is None else stops
    row = np.zeros((width, 4), dtype=np.uint8)
    for i in range(width):
        t = i / max(1, width - 1)
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t0 <= t <= t1:
                k = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
                for ch in range(3):
                    row[i, ch] = int(round(c0[ch] + (c1[ch] - c0[ch]) * k))
                break
        row[i, 3] = 255
    return row.reshape(1, width, 4)
