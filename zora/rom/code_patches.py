"""ZORA's 6502 patches: the CODE entries of features-behavior.md (B10).

The bytes come from zora/rom/code_patch_data.py, which scripts/asm_patches.py
generates from ZORA's ca65 sources in asm/ (asm/README.md). What a patch keeps
or moves of the original game is read from the player's ROM as it is written.
docs/rom-map.md records the free space and RAM each patch uses. The data
the patched code reads per seed is written here too.
"""
import hashlib
from collections.abc import Collection

from ..model.enums import Destination, Item
from ..model.game_world import GameWorld
from ..model.levels import Level
from ..model.overworld import POTION_SHOP_MIDDLE
from .base_rom import piece_bytes
from .code_patch_data import PATCHES, SYMBOLS
from .layout import CAVE_NOTHING_CODE
from .serialize.caves import CAVE_ITEM_CODE_MASK, WARES_PER_CAVE, cave_ware_tables

ROOMS_PER_BLOCK = 128
# FP-ENTR-02: level information +$23, the last byte of the palette transfer
# buffer, holds the exit-room count with bit 7 set (bit 7 still ends that
# buffer; PRG0 has $FF).
LEVEL_INFO_EXIT_ROOM_COUNT = 0x23
EXIT_ROOM_COUNT_FLAG = 0x80

# FP-HASH-01: the seed's code (or hash): four items shown on the file-select
# screen. The item IDs it may hold are the spec's 28 item-sprite values
# without 39: ZORA draws item IDs as room items are drawn, and PRG0's items
# run $00-$23. Each with the name the page shows.
SEED_CODE_NAMES: dict[int, str] = {
    0x00: "Bombs", 0x01: "Wooden Sword", 0x03: "Magical Sword", 0x04: "Bait", 0x05: "Recorder",
    0x06: "Blue Candle", 0x08: "Wooden Arrow", 0x0A: "Bow", 0x0B: "Magical Key", 0x0C: "Raft",
    0x0D: "Ladder", 0x0F: "Five Rupees", 0x10: "Wand", 0x11: "Book of Magic", 0x12: "Blue Ring",
    0x14: "Power Bracelet", 0x15: "Letter", 0x16: "Compass", 0x19: "Key", 0x1A: "Heart Container",
    0x1B: "Triforce", 0x1C: "Magical Shield", 0x1D: "Wooden Boomerang", 0x1F: "Blue Potion",
    0x21: "Clock", 0x22: "Heart", 0x23: "Fairy",
}
SEED_CODE_ITEMS = tuple(SEED_CODE_NAMES)
SEED_CODE_LENGTH = 4
SEED_CODE_ADDRESS = SYMBOLS["ZORA_B2_CodeIcons"]      # the asm label keeps its name


# FP-ENTR-01: the arrival code at level information +$3D (the cellar
# array's unused last entry; PRG0 $FF), and Link's overworld start Y, which
# the patch reads from its own byte so LevelInfo_StartY keeps PRG0's $8D.
LEVEL_INFO_ARRIVAL_CODE = 0x3D
ARRIVAL_OVERWORLD = 0
ARRIVAL_DUNGEON = 2
OVERWORLD_START_Y = SYMBOLS["ZORA_B5_OverworldStartY"]
ENTR_01 = "fp-entr-01"


# FP-BOOK-01, the patch of Book is an Atlas (B49); with B49 off (FL-OFF-05)
# it is left out and its sites keep PRG0's code.
BOOK_IS_AN_ATLAS = "fp-book-01"

# PI-CODE-01 (docs/design/progressive-items-plan.md; docs/progressive-patches.md):
# fp-prog-01 (bank 1: caves and shops) is written with Progressive Items or Shop
# Items in the Item Pool on, and fp-prog-02 (banks 5 and 4: room, coast and Armos
# items) with Progressive Items on. Its ResolveProgressive copies do not read the
# on/off byte, so leaving the patch out turns those upgrades off.
PROGRESSIVE_CAVES = "fp-prog-01"
PROGRESSIVE_ROOM_ITEMS = "fp-prog-02"
PROGRESSIVE_ITEMS_BYTE = SYMBOLS["ZORA_B1_ProgressiveItems"]
ONE_TIME_WARES = SYMBOLS["ZORA_B1_OneTimeWares"]
# The shops by the patch's shop number (ShopNumbers: object types $74, $77-$7A).
SHOPS_BY_NUMBER = (Destination.POTION_SHOP, Destination.SHOP_1, Destination.SHOP_2, Destination.SHOP_3,
                   Destination.SHOP_4)
# PI-CODE-04: the wares a shop sells again after each purchase, everything PRG0's shops sell
# as consumables; any other ware is sold once per shop (default-deny).
REBUYABLE_ITEMS = frozenset({Item.BOMBS, Item.BAIT, Item.MAGICAL_SHIELD, Item.KEY, Item.BLUE_POTION,
                             Item.RED_POTION, Item.SINGLE_HEART, Item.FAIRY})
# Shuffle Blue Potion's place, the potion shop's middle ware (empty in PRG0 and without the flag):
# sold once whatever it holds, its blue potion included (owner design, 2026-10-08).
ONE_TIME_POTION_SHOP_WARE = (SHOPS_BY_NUMBER.index(Destination.POTION_SHOP), POTION_SHOP_MIDDLE)


def left_out_patches(book_is_an_atlas: bool, progressive_items: bool, shop_items_in_pool: bool,
                     potion_shop_in_pool: bool = False) -> tuple[str, ...]:
    """The code patches a seed's settings leave out (FL-OFF-05, PI-CODE-01; fp-prog-01's buy-once
    rule also with Shuffle Blue Potion on)."""
    left_out = []
    if not book_is_an_atlas:
        left_out.append(BOOK_IS_AN_ATLAS)
    if not (progressive_items or shop_items_in_pool or potion_shop_in_pool):
        left_out.append(PROGRESSIVE_CAVES)
    if not progressive_items:
        left_out.append(PROGRESSIVE_ROOM_ITEMS)
    return tuple(left_out)


def one_time_wares(world: GameWorld, one_time_places: Collection[tuple[int, int]] = ()) -> bytes:
    """PI-CODE-04's ZORA_B1_OneTimeWares from the final shop stock: per ware position (0-2),
    bit 1 << shop number for each ware that holds an item and is not re-buyable or is the potion
    shop's middle ware (ONE_TIME_POTION_SHOP_WARE), and for each
    (shop number, position) of one_time_places (GameConfig.one_time_places)."""
    caves = {cave.destination: cave for cave in world.overworld.caves}
    items, _ = cave_ware_tables(caves)
    wares = bytearray(WARES_PER_CAVE)
    for shop_number, destination in enumerate(SHOPS_BY_NUMBER):
        start = (destination - Destination.WOOD_SWORD_CAVE) * WARES_PER_CAVE   # caves $10 + index
        for position, byte in enumerate(items[start:start + WARES_PER_CAVE]):
            item = byte & CAVE_ITEM_CODE_MASK
            sold_once = item not in REBUYABLE_ITEMS or (shop_number, position) == ONE_TIME_POTION_SHOP_WARE
            if item != CAVE_NOTHING_CODE and sold_once:
                wares[position] |= 1 << shop_number
    for shop_number, position in one_time_places:
        wares[position] |= 1 << shop_number
    return bytes(wares)


def code_patch_writes(world: GameWorld | None = None, left_out: Collection[str] = (),
                      progressive_items: bool = False,
                      one_time_places: Collection[tuple[int, int]] = ()) -> list[tuple[int, bytes]]:
    """Every patch's changed bytes as (file offset, bytes), in build order,
    with `world`'s per-seed data in place (without it, the placeholders).
    The patches named in left_out are not written."""
    data = seed_data(world, progressive_items, one_time_places) if world is not None else {}
    writes = []
    for name, pieces in PATCHES.items():
        if name in left_out:
            continue
        for offset, piece in pieces:
            run = bytearray(piece_bytes(piece))
            for address, value in data.items():
                if offset <= address < offset + len(run):
                    run[address - offset] = value
            writes.append((offset, bytes(run)))
    return writes


def seed_data(world: GameWorld, progressive_items: bool = False,
              one_time_places: Collection[tuple[int, int]] = ()) -> dict[int, int]:
    """The bytes inside the patches that a seed sets: file offset -> value. fp-prog-01's
    on/off byte is 1 with Progressive Items on (0 keeps only the buy-once rule, PI-CODE-01)."""
    data = {OVERWORLD_START_Y: world.overworld.start_position_y, PROGRESSIVE_ITEMS_BYTE: int(progressive_items)}
    data.update(enumerate(one_time_wares(world, one_time_places), start=ONE_TIME_WARES))
    return data


def overworld_start_y(rom: bytes) -> int | None:
    """FP-ENTR-01: the overworld start Y from a ROM carrying ZORA's patch,
    or None when it does not (PRG0, the corpus: LevelInfo_StartY holds it)."""
    data_byte = OVERWORLD_START_Y
    for offset, piece in PATCHES[ENTR_01]:
        after = piece_bytes(piece)
        run = bytearray(rom[offset:offset + len(after)])
        if offset <= data_byte < offset + len(after):
            run[data_byte - offset] = after[data_byte - offset]
        if run != after:
            return None
    return rom[data_byte]


def exit_room_count(world: GameWorld, level: Level) -> int:
    """FP-ENTR-02: how many rooms of the level's block, counting from room
    0, belong to no level or to this one. A dungeon move into the room with
    this number leaves the level."""
    count = 0
    while count < ROOMS_PER_BLOCK and level.block.owner_of(count) in (None, level):
        count += 1
    return count


def write_level_info_data(world: GameWorld, level: Level, info: bytearray) -> None:
    """The per-level bytes the patched code reads, into the dungeon's
    level-information block `info`."""
    info[LEVEL_INFO_EXIT_ROOM_COUNT] = exit_room_count(world, level) | EXIT_ROOM_COUNT_FLAG
    info[LEVEL_INFO_ARRIVAL_CODE] = ARRIVAL_DUNGEON


def write_overworld_level_info_data(info: bytearray) -> None:
    """The overworld's level-information byte the patched code reads."""
    info[LEVEL_INFO_ARRIVAL_CODE] = ARRIVAL_OVERWORLD


def stamp_seed_code(rom: bytearray) -> None:
    """FP-HASH-01: the seed's code, ZORA's function of the build: a SHA-256
    of the finished ROM (code bytes zeroed) picks each of the four items.
    Two builds of one seed and flags show the same code; any change to the
    generated ROM changes it. Player settings are applied after it and never
    change it (FP-SET-01)."""
    rom[SEED_CODE_ADDRESS:SEED_CODE_ADDRESS + SEED_CODE_LENGTH] = bytes(SEED_CODE_LENGTH)
    digest = hashlib.sha256(rom).digest()
    rom[SEED_CODE_ADDRESS:SEED_CODE_ADDRESS + SEED_CODE_LENGTH] = bytes(
        SEED_CODE_ITEMS[byte % len(SEED_CODE_ITEMS)] for byte in digest[:SEED_CODE_LENGTH]
    )


def seed_code(rom: bytes) -> tuple[str, ...]:
    """The seed's code as the four items' names, in screen order."""
    return tuple(SEED_CODE_NAMES[item] for item in rom[SEED_CODE_ADDRESS:SEED_CODE_ADDRESS + SEED_CODE_LENGTH])
