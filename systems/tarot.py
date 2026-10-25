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

"""
Tarot (Major Arcana) card system — Bound To Rot.

The Pulse's card choice is now a tarot spread. Each of the 22 Major Arcana
carries a direction (descend / stay / ascend / return) and a themed effect
applied to the next room. Cards are dealt face-down (back.png) and flipped
one-by-one; the player picks one to steer the delve.

Asset source: jcanabal's "major-arcana-pixel-art-free" (see credits.txt).

Effect keys understood by Game._delve_apply_card():
    darkness_mult : float  -> scale next room darkness_dps
    light_bonus   : float  -> + tiles to pulse light radius
    enemy_hp_mult : float  -> scale next wave enemy HP
    enemy_count   : int    -> +/- to next wave enemy count
    reward_ilvl   : int    -> bonus ilvl on the card's rolled reward
    reward_rarity : str    -> force reward to an equippable of this rarity
    heal_pct      : float  -> heal this fraction of max HP immediately
    currency      : int    -> grant gold immediately
    haste         : dict   -> {'duration': s, 'mult': f} move-speed buff
"""

import random

# Direction a card steers the run (depth change + room carve)
DIRECTION_DESCEND = 'descend'
DIRECTION_STAY    = 'stay'
DIRECTION_ASCEND  = 'ascend'
DIRECTION_RETURN  = 'return'

DIRECTIONS = (DIRECTION_DESCEND, DIRECTION_STAY, DIRECTION_ASCEND, DIRECTION_RETURN)

# The Major Arcana always used for the guaranteed "Return to Hub" escape card.
RETURN_ARCANA = 21  # The World

# Card decks — 'dark' is the default poker deck, 'light' is the bundled
# alternative skin.
TAROT_DECKS = {
    'dark':  {'folder': 'cards/dark',  'point_filter': True},
    'light': {'folder': 'cards/light', 'point_filter': True},
}
DEFAULT_DECK = 'dark'

CARD_BACK = 'cards/dark/BACK.png'


def _img(arcana_id: int) -> str:
    return f'cards/{arcana_id:02d}.png'


def card_face_rel(deck: str, arcana_id: int) -> str:
    """Asset-relative path of a card face for the given deck."""
    folder = TAROT_DECKS.get(deck, TAROT_DECKS[DEFAULT_DECK])['folder']
    return f'{folder}/{arcana_id:02d}.png'


def card_back_rel(deck: str) -> str:
    """Asset-relative path of the card back for the given deck."""
    folder = TAROT_DECKS.get(deck, TAROT_DECKS[DEFAULT_DECK])['folder']
    return f'{folder}/back.png'


TAROT_CARDS = {
    0:  {'name': 'The Fool',         'direction': DIRECTION_DESCEND,
         'effect': {'reward_ilvl': 2, 'darkness_mult': 1.2},
         'description': 'A leap into the unknown. Riches for the reckless, darkness for the bold.'},
    1:  {'name': 'The Magician',     'direction': DIRECTION_DESCEND,
         'effect': {'reward_rarity': 'uncommon', 'darkness_mult': 1.15},
         'description': 'Will made manifest. A rarer prize, a deeper shadow.'},
    2:  {'name': 'The High Priestess', 'direction': DIRECTION_STAY,
         'effect': {'heal_pct': 0.3, 'reward_ilvl': 1},
         'description': 'Hidden wisdom. Rest and find what is concealed.'},
    4:  {'name': 'The Emperor',      'direction': DIRECTION_STAY,
         'effect': {'enemy_count': -1, 'heal_pct': 0.2},
         'description': 'Order imposed. Fewer foes, steady ground.'},
    5:  {'name': 'The Hierophant',   'direction': DIRECTION_STAY,
         'effect': {'currency': 40, 'light_bonus': 1.0},
         'description': 'Guidance. Gold and a brighter path.'},
    6:  {'name': 'The Lovers',       'direction': DIRECTION_ASCEND,
         'effect': {'reward_rarity': 'uncommon', 'heal_pct': 0.2},
         'description': 'A favorable choice. A rare gift and healing.'},
    7:  {'name': 'The Chariot',      'direction': DIRECTION_STAY,
         'effect': {'haste': {'duration': 12.0, 'mult': 1.35}},
         'description': 'Momentum. A burst of speed.'},
    8:  {'name': 'Strength',         'direction': DIRECTION_STAY,
         'effect': {'enemy_hp_mult': 0.9, 'heal_pct': 0.3},
         'description': 'Fortitude. Your enemies weaken as you endure.'},
    9:  {'name': 'The Hermit',       'direction': DIRECTION_DESCEND,
         'effect': {'light_bonus': 1.5, 'enemy_count': 1},
         'description': 'The lone light. Carry your flame deeper, but not alone.'},
    10: {'name': 'Wheel of Fortune', 'direction': DIRECTION_ASCEND,
         'effect': {'currency': 60},
         'description': 'Turn of fate. A windfall.'},
    11: {'name': 'Justice',          'direction': DIRECTION_STAY,
         'effect': {'currency': 25, 'light_bonus': 0.5},
         'description': 'Balance restored. What is owed returns to you.'},
    12: {'name': 'The Hanged Man',   'direction': DIRECTION_ASCEND,
         'effect': {'reward_ilvl': 2},
         'description': 'Sacrifice and insight. A rarer find on the way up.'},
    13: {'name': 'Death',            'direction': DIRECTION_DESCEND,
         'effect': {'reward_ilvl': 3, 'enemy_hp_mult': 1.15},
         'description': 'Transformation. Great reward, hardened foes.'},
    14: {'name': 'Temperance',       'direction': DIRECTION_STAY,
         'effect': {'heal_pct': 1.0},
         'description': 'Moderation. Fully restored.'},
    15: {'name': 'The Devil',        'direction': DIRECTION_DESCEND,
         'effect': {'currency': 100, 'darkness_mult': 1.35},
         'description': 'Temptation. Gold now, shadow later.'},
    16: {'name': 'The Tower',        'direction': DIRECTION_DESCEND,
         'effect': {'reward_rarity': 'rare', 'darkness_mult': 1.4},
         'description': 'Upheaval. Catastrophic riches.'},
    17: {'name': 'The Star',         'direction': DIRECTION_ASCEND,
         'effect': {'heal_pct': 1.0, 'light_bonus': 2.0},
         'description': 'Hope renewed. Light and healing.'},
    18: {'name': 'The Moon',         'direction': DIRECTION_DESCEND,
         'effect': {'darkness_mult': 1.5, 'reward_ilvl': 3},
         'description': 'The deep unknown. Immense reward in the black.'},
    19: {'name': 'The Sun',          'direction': DIRECTION_ASCEND,
         'effect': {'reward_rarity': 'uncommon', 'heal_pct': 1.0},
         'description': 'Vitality. Radiant reward and full health.'},
    20: {'name': 'Judgement',        'direction': DIRECTION_ASCEND,
         'effect': {'currency': 80, 'heal_pct': 0.5},
         'description': 'Reckoning. Reward and renewal.'},
    21: {'name': 'The World',        'direction': DIRECTION_RETURN,
         'effect': {'currency': 120},
         'description': 'Completion. Leave with your spoils.'},
}


def draw_spread(rng=None) -> list:
    """Deal a 4-card spread.

    Guarantees:
      - The World (return) is always present, so leaving is never gated.
      - At least one descend card, so the run can always push deeper.
    Returns a list of 4 card dicts (arcana, name, img, direction, effect,
    description) in a shuffled order. depth/rewards/_rect are filled by the game.
    """
    rng = rng or random

    chosen = [RETURN_ARCANA]

    pool = [i for i in TAROT_CARDS if i != RETURN_ARCANA]
    others = rng.sample(pool, 3)
    if not any(TAROT_CARDS[i]['direction'] == DIRECTION_DESCEND for i in others):
        descend_pool = [i for i in pool
                        if TAROT_CARDS[i]['direction'] == DIRECTION_DESCEND]
        others[rng.randint(0, 2)] = rng.choice(descend_pool)

    chosen += others
    rng.shuffle(chosen)

    cards = []
    for arcana_id in chosen:
        info = TAROT_CARDS[arcana_id]
        cards.append({
            'arcana':      arcana_id,
            'name':        info['name'],
            'img':         _img(arcana_id),
            'direction':   info['direction'],
            'effect':      dict(info.get('effect') or {}),
            'description': info['description'],
            'depth':       None,
            'rewards':     [],
            '_rect':       None,
            '_flipped':    False,
        })
    return cards
