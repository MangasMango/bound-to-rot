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

"""Steamworks isolation adapter (issue #97).

THIS FILE IS THE ONLY PLACE Steamworks may ever be touched. The game's
core is GPLv3; Valve's Steamworks SDK is proprietary and its terms do not
mix with GPLv3 (see the additional permission at the bottom of LICENSE).
Keeping every Steamworks call behind this seam means:

  * the open-source build runs cleanly with no SDK present (every call
    below no-ops when the runtime/library is missing);
  * the SDK binaries are never committed - .gitignore blocks them and the
    Steam build pipeline injects them next to the executable at package
    time;
  * if a future wrapper needs proprietary code, it lives in its own
    non-GPL module and is loaded from here at runtime.

Current state: detection + no-op stubs. When the Steam build lands, wire
the real calls (achievements, overlay) into these functions via ctypes
against steam_api64.dll / libsteam_api.so - the rest of the game only
ever imports this module, never the SDK.
"""

import os
import sys

_STEAM_LIB_NAMES = ('steam_api64.dll', 'steam_api64.dll'.replace('64', ''),
                    'libsteam_api.so', 'libsteam_api.dylib')

_state = {'available': None}


def _sdk_present():
    """Is a Steamworks runtime library sitting next to the executable?"""
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    for name in _STEAM_LIB_NAMES:
        if os.path.exists(os.path.join(exe_dir, name)):
            return True
        if os.path.exists(os.path.join(os.getcwd(), name)):
            return True
    return False


def is_steam_build() -> bool:
    """True when a Steamworks runtime is present (the Steam distribution)."""
    if _state['available'] is None:
        _state['available'] = _sdk_present()
    return _state['available']


def init() -> bool:
    """Bring the Steamworks API up. No-op (False) in the open-source build."""
    return False   # real binding lands with the Steam build


def unlock_achievement(achievement_id: str) -> bool:
    """Pop one achievement. No-op in the open-source build."""
    return False


def shutdown() -> None:
    """Tear the API down. No-op in the open-source build."""
    return None
