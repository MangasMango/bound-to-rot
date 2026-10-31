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

"""Pure letterbox math for the fixed virtual canvas (no raylib dependency).

The frame is drawn at a fixed virtual resolution (SCREEN_W x SCREEN_H in
config.py) and aspect-fit into the (resizable) real window with black bars.
The same math drives BOTH the letterbox blit and the mouse coordinate
transform, so they can never disagree - a half-updated pair of these is
exactly what caused the 1080p click-misalignment bug.
"""


def letterbox_transform(win_w: int, win_h: int, virt_w: int, virt_h: int):
    """Aspect-fit a (virt_w x virt_h) canvas into a (win_w x win_h) window.

    Returns (scale, off_x, off_y):
      scale  - uniform scale factor applied to the virtual canvas
      off_x  - left edge of the canvas inside the window (letterbox)
      off_y  - top edge of the canvas inside the window (letterbox)

    Window mouse coords map into canvas coords via:
        canvas = (window - offset) / scale
    and the blit destination rectangle is (off_x, off_y, virt_w*scale, virt_h*scale).
    """
    scale = min(win_w / virt_w, win_h / virt_h)
    off_x = (win_w - virt_w * scale) * 0.5
    off_y = (win_h - virt_h * scale) * 0.5
    return scale, off_x, off_y
