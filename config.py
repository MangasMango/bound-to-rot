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

"""Single source of truth for project-root-relative paths."""
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(PROJECT_ROOT, 'assets')

# Boot resolution - the window opens at this size and can be resized freely;
# the game renders at the current window size (no fixed virtual canvas).
SCREEN_W = 1280
SCREEN_H = 720
