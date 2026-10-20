"""ZORA's 6502 patches: the CODE entries of features-behavior.md (B10).

The bytes come from zora/rom/code_patch_data.py, which scripts/asm_patches.py
generates from ZORA's ca65 sources in asm/ (asm/README.md). What a patch keeps
or moves of the original game is read from the player's ROM as it is written.
docs/rom-map.md records the free space and RAM each patch uses. The data
the patched code reads per seed is written here too.
"""
import hashlib
from collections.abc import Collection
from dataclasses import replace

from ..model.canonical import canonical_bytes
from ..model.enums import Destination, Item
from ..model.game_world import GameWorld
from ..model.overworld import POTION_SHOP_MIDDLE
from ..model.sprites import SpriteData
from .base_rom import piece_bytes, piece_length
from .code_patch_data import PATCHES, SYMBOLS
from .game_config import GameConfig
from .layout import CAVE_NOTHING_CODE
from .revision import Revision
from .serialize.caves import CAVE_ITEM_CODE_MASK, WARES_PER_CAVE, cave_ware_tables

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
SEED_CODE_DOMAIN = b"ZORA seed code\x00"             # what the hash is of, before the model


# FP-ENTR-01: the arrival code at level information +$3D (the cellar
# array's unused last entry; PRG0 $FF; the codes are model.levels.ARRIVAL_*),
# and Link's overworld start Y, which the patch reads from its own byte so
# LevelInfo_StartY keeps PRG0's $8D.
LEVEL_INFO_ARRIVAL_CODE = 0x3D
OVERWORLD_START_Y = SYMBOLS["ZORA_B5_OverworldStartY"]
ENTR_01 = "fp-entr-01"
# FP-ENTR-01's codes 1, 3 and 4 (B26, PS-START-03): written only when a start room moved, so a
# ROM without B26 keeps fp-entr-01's bytes.
ENTR_01_SIDES = "fp-entr-01-sides"
# The codes only fp-entr-01-sides places Link by (from above, the left, the right)
SIDE_ARRIVAL_CODES = frozenset({1, 3, 4})


# FP-BOOK-01, the patch of Book is an Atlas (B49); with B49 off (FL-OFF-05)
# it is left out and its sites keep PRG0's code.
BOOK_IS_AN_ATLAS = "fp-book-01"
# HT-BOOK-01, the patch of Book to Understand NPCs (B48): written only with B48 on.
BOOK_TO_UNDERSTAND_NPCS = "ht-book-01"

# PI-CODE-01 (docs/design/progressive-items-plan.md; docs/progressive-patches.md):
# fp-prog-01 (bank 1: caves and shops) is written with Progressive Items or Shop
# Items in the Item Pool on, and fp-prog-02 (banks 5 and 4: room, coast and Armos
# items) with Progressive Items on. Its ResolveProgressive copies do not read the
# on/off byte, so leaving the patch out turns those upgrades off.
PROGRESSIVE_CAVES = "fp-prog-01"
PROGRESSIVE_ROOM_ITEMS = "fp-prog-02"
PROGRESSIVE_ITEMS_BYTE = SYMBOLS["ZORA_B1_ProgressiveItems"]
# fp-start-02 (FP-START-02/03): a new file and the second quest take their Items block from a
# 40-byte table (ZORA_B2_StartItems; the patch's own copy is PRG0's start, FP-START-01). Inert
# by default: written only with start_items on, with the seed's table at START_ITEMS_TABLE.
START_ITEMS = "fp-start-02"
START_ITEMS_TABLE = SYMBOLS["ZORA_B2_StartItems"]
START_ITEMS_SIZE = 40
# PRG0's start as the table holds it (FP-START-01): 3 hearts and containers ($22) at HeartValues
# (offset $18), a full HeartPartial ($19), 8 MaxBombs ($25), every other byte 0.
PRG0_START_ITEMS = bytes(0x18) + bytes([0x22, 0xFF]) + bytes(0x0B) + bytes([0x08]) + bytes(2)
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
                     potion_shop_in_pool: bool = False, start_items: bool = False,
                     start_rooms_moved: bool = False, book_to_understand_npcs: bool = False) -> tuple[str, ...]:
    """The code patches a seed's settings leave out (FL-OFF-05, PI-CODE-01; fp-prog-01's buy-once
    rule also with Shuffle Blue Potion on; fp-start-02 unless a seed
    starts with other items than PRG0's, FP-START-02; fp-entr-01-sides unless the start-room swap
    ran, PS-START; ht-book-01 unless B48 is on, HT-BOOK-01)."""
    left_out = []
    if not book_is_an_atlas:
        left_out.append(BOOK_IS_AN_ATLAS)
    if not (progressive_items or shop_items_in_pool or potion_shop_in_pool):
        left_out.append(PROGRESSIVE_CAVES)
    if not progressive_items:
        left_out.append(PROGRESSIVE_ROOM_ITEMS)
    if not start_items:
        left_out.append(START_ITEMS)
    if not start_rooms_moved:
        left_out.append(ENTR_01_SIDES)
    if not book_to_understand_npcs:
        left_out.append(BOOK_TO_UNDERSTAND_NPCS)
    return tuple(left_out)


def start_items_writes(table: bytes) -> list[tuple[int, bytes]]:
    """fp-start-02 with `table` as the seed's starting Items block: (file offset, bytes)."""
    if len(table) != START_ITEMS_SIZE:
        raise ValueError(f"a starting table is {START_ITEMS_SIZE} bytes, not {len(table)}")
    return [*((offset, piece_bytes(piece)) for offset, piece in PATCHES[START_ITEMS]), (START_ITEMS_TABLE, table)]


def one_time_wares(world: GameWorld, one_time_places: Collection[tuple[int, int]] = (),
                   bait_in_pool: bool = False) -> bytes:
    """PI-CODE-04's ZORA_B1_OneTimeWares from the final shop stock: per ware position (0-2),
    bit 1 << shop number for each ware that holds an item and is not re-buyable or is the potion
    shop's middle ware (ONE_TIME_POTION_SHOP_WARE), and for each
    (shop number, position) of one_time_places (GameConfig.one_time_places). With Shop Items in
    the Item Pool's bait (bait_in_pool) every bait a shop sells is one of the pool's items, and so
    is a blue potion that shops 1-4 sell (Shuffle Blue Potion's, in a joined ware), so each is sold
    once, as Archipelago's ware places are."""
    pool_only = {Item.BAIT, Item.BLUE_POTION} if bait_in_pool else set()
    caves = {cave.destination: cave for cave in world.overworld.caves}
    items, _ = cave_ware_tables(caves)
    wares = bytearray(WARES_PER_CAVE)
    for shop_number, destination in enumerate(SHOPS_BY_NUMBER):
        start = (destination - Destination.WOOD_SWORD_CAVE) * WARES_PER_CAVE   # caves $10 + index
        rebuyable = REBUYABLE_ITEMS - pool_only if destination != Destination.POTION_SHOP else REBUYABLE_ITEMS
        for position, byte in enumerate(items[start:start + WARES_PER_CAVE]):
            item = byte & CAVE_ITEM_CODE_MASK
            sold_once = item not in rebuyable or (shop_number, position) == ONE_TIME_POTION_SHOP_WARE
            if item != CAVE_NOTHING_CODE and sold_once:
                wares[position] |= 1 << shop_number
    for shop_number, position in one_time_places:
        wares[position] |= 1 << shop_number
    return bytes(wares)


def code_patch_writes(world: GameWorld | None = None, left_out: Collection[str] = (),
                      progressive_items: bool = False,
                      one_time_places: Collection[tuple[int, int]] = (),
                      bait_in_pool: bool = False) -> list[tuple[int, bytes]]:
    """Every patch's changed bytes as (file offset, bytes), in build order,
    with `world`'s per-seed data in place (without it, the placeholders).
    The patches named in left_out are not written."""
    data = seed_data(world, progressive_items, one_time_places, bait_in_pool) if world is not None else {}
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
              one_time_places: Collection[tuple[int, int]] = (), bait_in_pool: bool = False) -> dict[int, int]:
    """The bytes inside the patches that a seed sets: file offset -> value. fp-prog-01's
    on/off byte is 1 with Progressive Items on (0 keeps only the buy-once rule, PI-CODE-01);
    with start items or start pieces, fp-start-02's table is the seed's (FP-START-03), as the
    serializer writes it."""
    from .start_items import start_table  # start_items reads this module's constants
    data = {OVERWORLD_START_Y: world.overworld.start_position_y, PROGRESSIVE_ITEMS_BYTE: int(progressive_items)}
    data.update(enumerate(one_time_wares(world, one_time_places, bait_in_pool), start=ONE_TIME_WARES))
    if world.uses_start_table:
        data.update(enumerate(start_table(world.start_items, world.new_file_heart_containers,
                                          world.new_file_full_hearts, world.start_triforce_pieces),
                              start=START_ITEMS_TABLE))
    return data


def overworld_start_y(rom: bytes) -> int | None:
    """FP-ENTR-01: the overworld start Y from a ROM carrying ZORA's patch,
    or None when it does not (PRG0, the corpus: LevelInfo_StartY holds it). The bytes
    fp-entr-01-sides writes over fp-entr-01 (B26's re-pointed jump) are not compared: a ROM
    whose start rooms moved carries both."""
    data_byte = OVERWORLD_START_Y
    overlaid = {offset + i for offset, piece in PATCHES[ENTR_01_SIDES] for i in range(piece_length(piece))}
    for offset, piece in PATCHES[ENTR_01]:
        after = piece_bytes(piece)
        if any(rom[address] != after[address - offset] for address in range(offset, offset + len(after))
               if address != data_byte and address not in overlaid):
            return None
    return rom[data_byte]


def seed_code_items(world: GameWorld, config: GameConfig) -> bytes:
    """FP-HASH-01: the seed's code, a function of the generated game alone (owner ruling, beta 5):
    a SHA-256 of ZORA's model of the seed, written out in its fixed form (model/canonical.py),
    and of the game configuration, picks each of the four items. The model leaves out the tile
    patterns (the player's graphics) and the configuration its release and graphics fields, and
    the player settings are never in either, so one seed and its flags show the same code on PRG0
    and PRG1, with any graphics and any player settings. Any change to the game changes it,
    Archipelago's slot identity (each slot's code differs) and the level encoding included."""
    game = replace(config, revision=Revision.PRG0, modified_graphics=False, seed_number=None)
    digest = hashlib.sha256(SEED_CODE_DOMAIN + canonical_bytes(world, left_out=(SpriteData,))
                            + canonical_bytes(game)).digest()
    return bytes(SEED_CODE_ITEMS[byte % len(SEED_CODE_ITEMS)] for byte in digest[:SEED_CODE_LENGTH])


# The statistics screen's seed number (asm/fp-stats-01/bank_02.s StatsSeedDigits, bank 2 $B780, free
# space outside every patch, so the player settings never rewrite it): 20 tiles, the first 10
# digits after "SEED " on row 1 and the rest under them on row 2, blank-padded. $FF (a ROM without
# a seed number written) shows no seed row.
STATS_SEED_DIGITS = 0x0B790
SEED_DIGITS_PER_ROW = 10
SEED_DIGIT_ROWS = 2
SEED_DIGITS_LENGTH = SEED_DIGITS_PER_ROW * SEED_DIGIT_ROWS
BLANK_TILE = 0x24                                       # digits are tiles 0-9


def seed_digit_tiles(seed: int) -> bytes:
    """The seed number as StatsSeedDigits holds it (at most 20 digits: seeds are below 2^64)."""
    digits = str(seed)
    assert len(digits) <= SEED_DIGITS_LENGTH, seed
    return bytes(int(digit) for digit in digits).ljust(SEED_DIGITS_LENGTH, bytes([BLANK_TILE]))


def stamp_seed_number(rom: bytearray, seed: int) -> None:
    rom[STATS_SEED_DIGITS:STATS_SEED_DIGITS + SEED_DIGITS_LENGTH] = seed_digit_tiles(seed)


def stamp_seed_code(rom: bytearray, world: GameWorld, config: GameConfig) -> None:
    """Write the seed's code (seed_code_items) into its four bytes."""
    rom[SEED_CODE_ADDRESS:SEED_CODE_ADDRESS + SEED_CODE_LENGTH] = seed_code_items(world, config)


# Pegasus Boots (asm/flags2/pegasus-boots' icon-offsets hook; owner decision 2026-10-18): item slot $1D
# draws Anim_ItemFrameTiles[$25], the boot, so the code's $1D icon is the boot and is named as the game
# draws it. The code's value stays $1D.
BOOMERANG_CODE = 0x1D
BOOTS_CODE_NAME = "Pegasus Boots"
BOOMERANG_FRAME_OFFSET = 0x07154        # Anim_ItemFrameOffsets[$1D], bank 1 (no PRG1 move)
BOOT_FRAME_ENTRY = 0x25


def draws_boots(rom: bytes) -> bool:
    """The finished ROM draws item slot $1D as the boot (Pegasus Boots is on)."""
    return rom[BOOMERANG_FRAME_OFFSET] == BOOT_FRAME_ENTRY


def seed_code_values(rom: bytes) -> bytes:
    """The seed's code as the four item values, in screen order."""
    return rom[SEED_CODE_ADDRESS:SEED_CODE_ADDRESS + SEED_CODE_LENGTH]


def seed_code(rom: bytes) -> tuple[str, ...]:
    """The seed's code as the four items' names, in screen order, as the game draws them."""
    boots = draws_boots(rom)
    return tuple(BOOTS_CODE_NAME if boots and item == BOOMERANG_CODE else SEED_CODE_NAMES[item]
                 for item in seed_code_values(rom))
