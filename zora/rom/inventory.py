"""The game's inventory in RAM, and giving an item the way the game takes one (aldonunez labels,
src/Variables.inc and Z_01.asm's TakeItem, at the pinned disassembly commit). Archipelago's
client gives the items other worlds send by writing RAM (zora/archipelago.py receive, docs/
archipelago.md "Interface"); this module says what to write, so the BizHawk client and a later
EverDrive bridge share one rule and no in-ROM code is needed.

It also names where the game records that a place's item was taken, for pickup_checks: a
world's room flags (bit $10, SetRoomFlagUWItemState) and fp-prog-01's ShopBoughtFlags.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..model.enums import Item
from .base_rom import original_bytes

ITEMS = 0x0657                       # Items: the inventory, one byte per slot
SWORD_SLOT = 0x00                    # InvSword
POTION_SLOT = 0x07
BOMB_SLOT = 0x01
HEART_VALUES_SLOT = 0x18             # HeartValues ($066F): containers - 1 (high nibble), hearts
WOOD_BOOMERANG_SLOT = 0x1D           # InvBoomerang ($0674)
MAX_BOMBS = 0x067C                   # MaxBombs
# The slots TakeItem treats as "complex" (maps, compasses, triforces): never Archipelago items.
COMPLEX_SLOTS = frozenset({0x10, 0x11, 0x1A, 0x1B})
RUPEE_SLOTS = frozenset({0x16, 0x1C})          # a rupee, five rupees: RupeesToAdd, not the inventory
HEART_SLOTS = frozenset({0x14, 0x19})          # a fairy, a heart: refills, not the inventory

# PRG0's ItemIdToSlot and ItemIdToDescriptor (Z_01.asm, bank 1), one byte per item code $00-$23,
# read from the player's ROM (base_rom.player_rom: archipelago.checked_rom, or any build, remembers
# it). A descriptor's high nibble is the item's class (0 unique, 1 an amount, 2 graded, 3 set to
# $FF), the low nibble its value.
ITEM_ID_TO_SLOT = 0x06B24            # file offsets
ITEM_ID_TO_DESCRIPTOR = 0x06B48
ITEM_CODES = 0x24


def item_slots() -> bytes:
    """ItemIdToSlot: each item code's inventory slot (an offset from ITEMS)."""
    return original_bytes(ITEM_ID_TO_SLOT, ITEM_CODES)


def item_descriptors() -> bytes:
    """ItemIdToDescriptor: each item code's class and value."""
    return original_bytes(ITEM_ID_TO_DESCRIPTOR, ITEM_CODES)


CLASS_MASK, VALUE_MASK = 0xF0, 0x0F
UNIQUE, AMOUNT, GRADED, FULL = 0x00, 0x10, 0x20, 0x30
FULL_VALUE = 0xFF
POTION_CAP, FOUR_POTION_CAP = 2, 4               # four_potion_inventory raises the cap
HEART_CONTAINER_STEP = 0x11                      # one container and one heart
MAX_HEART_VALUES = 0xF0                          # sixteen containers
ITEM_ID_LIMIT = 0x1F                             # every upgrade-line item is below it
MAGICAL_SWORD_LEVEL = 3                          # Add L4 Sword raises it to 4

# Archipelago's saved count of items the client has given (Phase 4c; docs/rom-map.md "RAM"):
# inside the Items block the game saves, checksums and clears for a new file ($0657-$067E), at a
# slot no item, label or literal reaches.
RECEIVED_COUNT = ITEMS + 0x24        # $067B

# Where the game records a taken item (pickup_checks).
WORLD_FLAGS = 0x067F                 # WorldFlags: the overworld's 128 room bytes
WORLD_FLAGS_SIZE = 0x80              # then levels 1-6's, then levels 7-9's (PRG0's LevelInfo_WorldFlagsAddr)
LEVELS_7_TO_9 = 7
ITEM_TAKEN = 0x10                    # SetRoomFlagUWItemState's bit (a room, a cellar, a cave's screen)
SHOP_BOUGHT_FLAGS = 0x0677           # fp-prog-01: one byte per ware position, bit 1 << shop number
COAST_SCREEN = 0x5F                  # where the game gives the coast item (PRG0)


def room_flags(level: int) -> int:
    """The first of a world's 128 room bytes: the overworld (level 0), levels 1-6 or levels 7-9."""
    if level == 0:
        return WORLD_FLAGS
    return WORLD_FLAGS + WORLD_FLAGS_SIZE * (1 if level < LEVELS_7_TO_9 else 2)


@dataclass(frozen=True)
class GiveRules:
    """The seed's flags that change how an item is taken: Progressive Items (fp-prog: the line's
    next level), Add L4 Sword (a sword at level 3 gives level 4) and Four Potion Inventory."""
    progressive_items: bool = False
    l4_sword: bool = False
    four_potions: bool = False


def next_level(code: int, ram: Mapping[int, int]) -> int:
    """fp-prog's ResolveProgressive: an upgrade-line item as its line's next level (at most the
    top); any other item unchanged. The boomerangs: the wooden one, then the magical one."""
    if code >= ITEM_ID_LIMIT:
        return code
    if code in (Item.WOOD_BOOMERANG, Item.MAGICAL_BOOMERANG):
        return Item.WOOD_BOOMERANG + ram[ITEMS + WOOD_BOOMERANG_SLOT]
    slots, descriptor = item_slots(), item_descriptors()[code]
    if descriptor & CLASS_MASK != GRADED:
        return code
    slot = slots[code]
    following = code - (descriptor & VALUE_MASK) + ram[ITEMS + slot] + 1
    return following if slots[following] == slot else following - 1


NO_RULES = GiveRules()


def give(item: Item, ram: Mapping[int, int], rules: GiveRules = NO_RULES) -> dict[int, int]:
    """The RAM writes (address -> value) that give `item` as TakeItem does, from `ram`, a snapshot
    holding at least the inventory ($0657-$067C); empty when the item changes nothing. Ring
    colours follow at the next palette load, not here (TakeItem also patches the palette)."""
    slots, descriptors = item_slots(), item_descriptors()
    if slots[item] == SWORD_SLOT and ram[ITEMS + SWORD_SLOT] > MAGICAL_SWORD_LEVEL:
        # Add L4 Sword's level 4 is the line's top. (The game's ResolveProgressive runs past it
        # to item $04, the bait; no fifth sword exists, so play never gets there.)
        return {}
    code = next_level(int(item), ram) if rules.progressive_items else int(item)
    slot, descriptor = slots[code], descriptors[code]
    if slot in COMPLEX_SLOTS | RUPEE_SLOTS | HEART_SLOTS:
        raise ValueError(f"{item.name}: not an item given through the inventory")
    address, value = ITEMS + slot, descriptor & VALUE_MASK
    current = ram[address]
    kind = descriptor & CLASS_MASK
    if kind == UNIQUE:
        new = value
    elif kind == GRADED:
        new = max(current, value)
        if rules.l4_sword and slot == SWORD_SLOT and current == value == MAGICAL_SWORD_LEVEL:
            new = MAGICAL_SWORD_LEVEL + 1                # Add L4 Sword's RaiseSwordToL4
    elif kind == AMOUNT and slot == HEART_VALUES_SLOT:
        new = current if current >= MAX_HEART_VALUES else current + HEART_CONTAINER_STEP
    elif kind == AMOUNT:
        new = min(current + value, FULL_VALUE)
        if slot == POTION_SLOT:
            new = min(new, FOUR_POTION_CAP if rules.four_potions else POTION_CAP)
        if slot == BOMB_SLOT:
            new = min(new, ram[MAX_BOMBS])
    else:
        new = FULL_VALUE
    return {address: new} if new != current else {}


# When a client may write RAM (receive): only in normal play, never during a transition (scrolling
# and caves are other modes), the item screen, a pause, an item being lifted, or text (a person's
# text halts Link, the state TryTakeRoomItem also refuses).
IS_UPDATING_MODE, GAME_MODE, GAME_SUBMODE = 0x11, 0x12, 0x13
PAUSED, MENU_STATE = 0xE0, 0xE1
LINK_STATE = 0xAC                        # ObjState, slot 0 (Link)
ITEM_LIFT_TIMER = 0x0506
PLAY_MODE = 0x05
HALTED_MASK, HALTED = 0xC0, 0x40
RECEIVE_STATE = (IS_UPDATING_MODE, GAME_MODE, GAME_SUBMODE, PAUSED, MENU_STATE, LINK_STATE, ITEM_LIFT_TIMER)


def may_receive(ram: Mapping[int, int]) -> bool:
    """Whether a client may write a received item now (`ram` holds RECEIVE_STATE's addresses)."""
    return (ram[GAME_MODE] == PLAY_MODE and ram[GAME_SUBMODE] == 0 and ram[IS_UPDATING_MODE] == 1
            and ram[PAUSED] == 0 and ram[MENU_STATE] == 0 and ram[ITEM_LIFT_TIMER] == 0
            and ram[LINK_STATE] & HALTED_MASK != HALTED)


# When the player has won (goal_reached; Z_04.asm's UpdateZelda, Z_07.asm's mode table): Link
# reaching Zelda puts her object (slot 1, type $37) in state 1 and halts him; $80 frames later
# UpdateZelda switches to mode $13 (UpdateMode13WinGame), the ending, which runs until the credits
# end and the file is saved.
ZELDA_SLOT = 1
ZELDA_TYPE = 0x034F + ZELDA_SLOT         # ObjType+1: $37 while Zelda is in her room
ZELDA_STATE = LINK_STATE + ZELDA_SLOT    # ObjState+1: 0 until Link reaches her
ZELDA = 0x37
WIN_GAME_MODE = 0x13
GOAL_STATE = (GAME_MODE, ZELDA_TYPE, ZELDA_STATE)


def goal_reached(ram: Mapping[int, int]) -> bool:
    """Whether Zelda is rescued (`ram` holds GOAL_STATE's addresses): Zelda's object in slot 1,
    and either play with her out of her waiting state or the ending's mode (her object stays
    through the ending, so a stray $13 alone, as in RAM at power-on, does not count)."""
    if ram[ZELDA_TYPE] != ZELDA:
        return False
    return ram[GAME_MODE] == WIN_GAME_MODE or (ram[GAME_MODE] == PLAY_MODE and ram[ZELDA_STATE] != 0)
