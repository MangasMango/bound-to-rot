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

"""Fallout-style rank words for the DESCEND attribute display (owner wording)."""

from entities.descend import ATTR_CAP

RANK_WORDS = (
    'Cowardly', 'Awful', 'Poor', 'Fair', 'Decent', 'Good',
    'Great', 'Excellent', 'Exceptional', 'Heroic', 'Godly',
)


def rank_word(value: int) -> str:
    """Word ladder for a (hard-capped) attribute value 0-10."""
    value = max(0, min(ATTR_CAP, int(value)))
    return RANK_WORDS[value]
