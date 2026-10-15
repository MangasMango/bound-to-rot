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
Icon loader for the D2-style menu system.
Loads 16x16 pixel-art icons from assets/ui-icons/ on demand.
Uses nearest-neighbour filtering for crisp pixel scaling.

BLUEPRINT RULE: Every UI element that represents a concept MUST have an icon.
Text alone is forbidden for stat labels, item names, damage types,
equipment slots, currency, and screen actions.
"""
from __future__ import annotations

import os
import pyray as rl
from config import ASSETS

_ICON_DIR = os.path.join(ASSETS, 'ui-icons')

# Curated mapping: logical name → filename on disk
# Names with _s use the "Small" variant; names with _b use the "Big" variant.
ICON_MAP = {
    # ── Stats (unique per stat — no reuse) ──────────────────────────
    'str':         'RPG_Stat_Strength_Fist_Melee_Attack_Small.png',
    'dex':         'RPG_Stat_Dexterity_Agility_Boots_Movement_Speed_Small.png',
    'int':         'RPG_Stat_Intelligence_Intellect_Brain_Wisdom_Thinking_IQ_Small.png',
    'hp':          'RPG_Stat_HP_Health_Heart_Small.png',
    'mana':        'RPG_Stat_MP_Mana_Star_Small.png',
    'luck':        'RPG_Stat_Luck_Four_Leaf_Clover_Small.png',
    'accuracy':    'RPG_Stat_Accuracy_Ranged_Target_Arrow.png',
    'evasion':     'RPG_Skill_Dash_Dodge_Movement_Speed_Run_Sprint.png',
    'defense':     'RPG_Item_Stat_Shield_Defense_Armor.png',
    'penetration': 'RPG_Item_Stat_Broken_Shield_Armor_Penetration.png',
    'melee':       'RPG_Item_Weapon_Sword_Attack_Melee_Slashing_Damage.png',
    'move_speed':  'RPG_Stat_Dexterity_Agility_Boots_Movement_Speed.png',
    'attack_speed':  'Weather_Tornado_Cyclone_Whirlwind_Natural_Disaster.png',
    'cooldown_reduction': 'Software_Clock_Time_Wait_Chronometer_Timer_Countdown.png',
    'crit_chance':    'RPG_Skill_Strike_Attack_Sword_Slash_Cleave.png',
    'ability_crit':   'Controller_Buttons_View_Window_Cast.png',

    # ── DESCEND attributes ──────────────────────────────────────────
    'dexterity':   'RPG_Stat_Dexterity_Agility_Boots_Movement_Speed_Small.png',
    'endurance':   'RPG_Stat_Shield_Defense_Armor.png',
    'strength':    'RPG_Stat_Strength_Fist_Melee_Attack_Small.png',
    'cunning':     'RPG_Stat_Intelligence_Intellect_Brain_Wisdom_Thinking_IQ_Small.png',
    'essence':     'RPG_Stat_Luck_Four_Leaf_Clover_2_Small.png',
    'nerve':       'RPG_Stat_Accuracy_Ranged_Target_Arrow.png',
    'destiny':     'RPG_Stat_Luck_Four_Leaf_Clover_Small.png',

    # ── Damage types ────────────────────────────────────────────────
    'physical':  'Alchemy_Element_Earth.png',
    'fire':      'Alchemy_Element_Fire.png',
    'cold':      'Alchemy_Element_Water.png',
    'lightning': 'Alchemy_Element_Air.png',
    'magic':     'RPG_Spell_Skill_Magic_Arcane_Missiles_Multishot.png',
    'rot':       'Alchemy_Death_Omega.png',

    # ── Resistances (unique from damage types) ──────────────────────
    'fire_resist':     'Weather_Wildfire_Flame_Element_Hot_Burn.png',
    'cold_resist':     'Weather_Snowflake_Freeze_Cold_Snowstorm_Frozen_Frost_Element_Winter_Season.png',
    'lightning_resist':'Weather_Thunderstorm_Cloud_Lightning_Zap.png',
    'physical_resist': 'RPG_Stat_Shield_Defense_Armor.png',
    'magic_resist':    'RPG_Spell_Magic_Circle_Ritual_Pentagram.png',
    'rot_resist':      'Weather_Biohazard_Biological_Danger_Sign.png',
    'darkness_resist': 'Weather_Moon_Night_Crescent_Darkness_Mode_Twilight_Small.png',

    # ── Vessels ──────────────────────────────────────────────────────
    'warrior':  'Alchemy_Element_Earth.png',
    'fighter':  'Alchemy_Element_Fire.png',
    'pyrrhian': 'RPG_Stat_Luck_Four_Leaf_Clover_Small.png',
    'knight':   'RPG_Stat_Luck_Four_Leaf_Clover_Small.png',

    # ── Loot ────────────────────────────────────────────────────────
    'loot':   'RPG_Loot_Bag_Money_Coins_Purse.png',

    # ── Equipment slots ─────────────────────────────────────────────
    'helm':      'RPG_Item_Armor_Equipment_Slot_Head_Helmet.png',
    'chest':     'RPG_Item_Armor_Equipment_Slot_Chest_Breastplate_Body.png',
    'gloves':    'RPG_Item_Armor_Equipment_Slot_Hands_Gloves_Gauntlets.png',
    'boots':     'RPG_Item_Armor_Equipment_Slot_Feet_Boots_Legplates.png',
    'belt':      'RPG_Item_Accessory_Armor_Equipment_Slot_Waist_Belt.png',
    'ring':      'RPG_Item_Accessory_Trinket_Equipment_Slot_Finger_Ring_Jewelry.png',
    'amulet':    'RPG_Item_Accessory_Trinket_Equipment_Slot_Necklace_Amulet_Talisman_Jewelry.png',

    # ── Organ slots ─────────────────────────────────────────────────
    'lungs':     'Misc_Organ_Lungs_Breathing_Breath.png',
    'heart':     'RPG_Stat_HP_Health_Heart.png',
    'liver':     'Alchemy_Salt_Body.png',
    'intestine': 'Food_Fish_Bones_Trash.png',
    'kidney':    'Tools_Crafting_Bone_Skeleton_Remains_Small.png',
    'organ':     'Alchemy_Salt_Body.png',

    # ── Consumable items ────────────────────────────────────────────
    'potion':        'Alchemy_Potion_Vial_Bottle_Full.png',

    # ── UI controls ─────────────────────────────────────────────────
    'back':       'Arrows_Go_Back_Return_Previous.png',
    'settings':   'Software_Options_Settings_Cogwheel_Gear_Mechanics.png',
    'exit':       'Software_Exit_Quit_Doorway_Button.png',
    'delete':     'Software_Trashcan_Garbage_Bin_Rubbish_Delete_Erase_1.png',
    'refresh':    'Arrows_Reload_Refresh_Rotate_Clockwise.png',
    'search':     'Software_Magnifier_Zoom_Looking_Magnifying_Glass.png',
    'checkmark':  'Software_Checkbox_Checkmarked_Yes_Done_Todo.png',
    'cross':      'Alchemy_Cancel_Decline.png',
    'plus':       'Software_Signs_Maths_Plus_Addition_Bonus_Add_New.png',
    'minus':      'Software_Signs_Maths_Minus_Subtract_Drawback_Remove_Delete_Dash.png',
    'arrow_up':   'Arrows_Up_North.png',
    'arrow_down': 'Arrows_Down_South.png',
    'audio':      'Media_Audio_Sound_Volume_2.png',
    'graphics':   'Media_Camera_Photo_Shoot_1.png',
    'controls':   'Controller_Gamepad.png',
    'star':       'RPG_Magic_Sparkles_Enchantment.png',

    # ── World / gameplay ────────────────────────────────────────────
    'portal':       'RPG_Teleportation_Stone.png',
    'light':        'RPG_Item_Lantern_Lamp_Light.png',
    'darkness':     'Weather_Moon_Night_Crescent_Darkness_Mode_Twilight_Big.png',
    'skull':        'RPG_Skull_Death_Dead_Bones_Pirates.png',
    'player':       'RPG_Character_Humanoid.png',
    'help':         'Software_Warning_Sign_Circle_Question_Mark_Help.png',
    'multiplayer':  'Travel_Person_Player_Characters_People_Two_Coop_Multiplayer.png',
    'server':       'Software_Storage_Drives_Discs_Disks_Server_1.png',
    'key':          'Tools_Crafting_Key_Unlock_1.png',
    'shield':       'RPG_Crossed_Swords_Shield_Combat_Battle_War.png',
    'energy_shield':'RPG_Spell_Magic_Circle_Ritual_Pentagram.png',
    'crack':        'Warfare_Dynamite_Stick_Explosive.png',
    'cart':         'Warfare_Dynamite_TNT_Explosives_Crate_Bundle.png',
    'hidden':       'RPG_Skill_Explosive_Shot_Bomb_Arrow.png',
}

# Cache: name → Texture2D
_cache = {}


def _load_icon(name: str) -> rl.Texture2D | None:
    """Lazy-load a 16x16 icon, caching the result."""
    if name in _cache:
        return _cache[name]

    filename = ICON_MAP.get(name)
    if not filename:
        return None

    path = os.path.join(_ICON_DIR, filename)
    if not os.path.exists(path):
        return None

    img = rl.load_image(path)
    if img.width <= 0:
        return None

    tex = rl.load_texture_from_image(img)
    rl.unload_image(img)

    # Nearest-neighbour for crisp pixel-art upscaling
    rl.set_texture_filter(tex, rl.TEXTURE_FILTER_POINT)

    _cache[name] = tex
    return tex


_EQUIP_SLOT_TO_ICON = {
    'lungs':     'lungs',
    'heart':     'heart',
    'liver':     'liver',
    'intestine': 'intestine',
    'kidney':    'kidney',
}

def item_icon(idef: dict, item_id: str = None) -> str | None:
    """Return the UI icon name for an item definition, or None."""
    if not idef:
        return None
    slot = idef.get('equipSlot')
    if slot:
        mapped = _EQUIP_SLOT_TO_ICON.get(slot)
        if mapped:
            return mapped
    if idef.get('use'):
        return 'potion'
    if item_id and item_id in ICON_MAP:
        return item_id
    return None


def draw(name: str, x: int, y: int, size: int = 24, tint=None):
    """Draw an icon at (x, y) at a given pixel size. 24px = 1.5x scale."""
    tex = _load_icon(name)
    if not tex or tex.id <= 0:
        return

    rl.draw_texture_pro(
        tex,
        rl.Rectangle(0, 0, 16.0, 16.0),
        rl.Rectangle(float(x), float(y), float(size), float(size)),
        rl.Vector2(0, 0), 0.0,
        tint or rl.WHITE,
    )


def unload():
    """Release all cached icon textures."""
    for tex in _cache.values():
        if tex and tex.id > 0:
            rl.unload_texture(tex)
    _cache.clear()
