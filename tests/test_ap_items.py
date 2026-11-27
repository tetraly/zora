"""Archipelago items piece 4 (docs/design/archipelago-items.md): a room's item is six bits, table E
bits 4-0 and table F bit 3 as bit 5, in the model, the parser and the serializer; every kind of place
holding an extended code reads back. The emulator side is tests/test_ap_items_emulator.py."""
from dataclasses import replace
from functools import cache

import pytest

from tests.needs import needs_base_rom
from tests.test_assignment import identity
from tests.test_assignment_emulator import CASE, SEED, _built, places_of_each_kind
from zora.generate.pipeline import Built, finish_world, written_world
from zora.generate.places import Place, read_item, write_item
from zora.model.enums import Destination, Item, RoomType
from zora.model.levels import LevelBlock
from zora.model.rooms import ITEM_MASK, TRIGGER_ITEM_HIGH_BIT, ItemInfo, Room, StaircaseRoom
from zora.rom.base_rom import as_player_rom, remember_repo_base_rom, using_player_rom
from zora.rom.layout import DUNGEON_NOTHING_CODE, LEVEL_TABLE_SIZE
from zora.rom.owner_patches import ARCHIPELAGO_PATCHES
from zora.rom.parse.levels import _parse_block
from zora.rom.parse.rom_file import parse_rom
from zora.rom.serialize.levels import encode_level_block
from zora.rom.serialize.rom_file import serialize_to_rom

ITEM_TABLE, TRIGGER_TABLE = 4, 5        # LevelBlockAttrsE and F among a block's six tables
SIX_BIT_CODES = (Item.RED_POTION, Item.FAIRY, Item.COMPASS_1, Item.TRIFORCE_7)
FIVE_BIT_CODES = (Item.BOMBS, Item.KEY, Item.BLUE_POTION)
TEST_CODE = Item.COMPASS_1
OVERWORLD_PLACES = (Destination.ARMOS_ITEM, Destination.COAST_ITEM)


def _room(block: LevelBlock) -> Room:
    return next(cell for cell in block.cells if isinstance(cell, Room))


def _item_cellar(block: LevelBlock) -> StaircaseRoom:
    return next(cell for cell in block.cells
                if isinstance(cell, StaircaseRoom) and cell.room_type == RoomType.ITEM_STAIRCASE)


@needs_base_rom
@pytest.mark.parametrize("item", SIX_BIT_CODES + FIVE_BIT_CODES, ids=lambda item: item.name)
def test_a_room_and_a_cellar_keep_six_bits(item: Item) -> None:
    """A room's and an item cellar's item round-trips through the block encoder and parser; table F
    bit 3 is set exactly for codes $20 and up, and nothing else in E or F moves."""
    world = parse_rom(remember_repo_base_rom())
    block = world.blocks[0]
    room, cellar = _room(block), _item_cellar(block)
    before = encode_level_block(block, DUNGEON_NOTHING_CODE)
    room.item_info = replace(room.item_info, item=item)
    cellar.item = item
    encoded = encode_level_block(block, DUNGEON_NOTHING_CODE)
    high = TRIGGER_ITEM_HIGH_BIT if item.value & 0x20 else 0
    for cell in (room.room_num, cellar.room_num):
        e, f = (ITEM_TABLE * LEVEL_TABLE_SIZE + cell, TRIGGER_TABLE * LEVEL_TABLE_SIZE + cell)
        assert encoded[e] & ITEM_MASK == item.value & ITEM_MASK
        assert encoded[e] & ~ITEM_MASK == before[e] & ~ITEM_MASK        # boss sound and darkness
        assert encoded[f] == before[f] | high                           # trigger and item position
    parsed = _parse_block(encoded, {}, DUNGEON_NOTHING_CODE)         # mixed groups name no room's item
    assert parsed.room(room.room_num).item == item
    parsed_cellar = parsed.staircase(cellar.room_num)
    assert parsed_cellar.item == item and parsed_cellar.t5_raw == cellar.t5_raw


@needs_base_rom
def test_no_room_of_either_quest_has_a_sixth_bit() -> None:
    """Table F bit 3 is clear in every dungeon room of PRG0, so every room parses as before."""
    world = parse_rom(remember_repo_base_rom())
    for block in (*world.blocks, *world.blocks_2q):
        for cell in block.cells:
            item = cell.item
            assert item is None or item == Item.NOTHING or item.value < 0x20, (cell.room_num, item)


def test_a_six_bit_item_has_no_single_item_byte() -> None:
    """A pass that moves table E's byte whole would drop bit 5: such a move refuses."""
    info = ItemInfo(TEST_CODE)
    assert info.item_code == TEST_CODE.value
    with pytest.raises(ValueError, match="six-bit"):
        _ = info.item_byte
    assert ItemInfo(Item.BLUE_POTION).item_byte == Item.BLUE_POTION.value


@needs_base_rom
def test_the_serializer_refuses_3f_in_a_room() -> None:
    world = parse_rom(remember_repo_base_rom())
    room = _room(world.blocks[0])
    room.item_info = replace(room.item_info, item=Item.OVERWORLD_NO_ITEM)
    with pytest.raises(ValueError, match="cannot be a room's item"):
        encode_level_block(world.blocks[0], DUNGEON_NOTHING_CODE)


def test_archipelago_roms_carry_the_patch() -> None:
    assert "ap-items" in ARCHIPELAGO_PATCHES


@cache
def every_kind(base: bytes, item: Item) -> tuple[bytes, dict[str, Place], Built]:
    """An Archipelago game's ROM (CASE, finished with its own items) with `item` written by FINISH's
    serializer into one place of each kind: a room floor, a room drop, an item cellar, the white sword
    cave, a shop ware, the Armos item and the coast item. Extended codes are not assignable before
    pieces 5 and 6, so the item is written into the finished world, as apply_assignment would."""
    built = _built(CASE, SEED) if base == remember_repo_base_rom() else _built_on(base)
    places = places_of_each_kind(built)
    for destination in OVERWORLD_PLACES:
        places[destination.name] = next(place for place in built.places if place.destination == destination)
    with using_player_rom(as_player_rom(base)):
        world, finished = finish_world(built, identity(built))
    for place in places.values():
        write_item(world, place, item)
    config = replace(finished.config, archipelago_rom=True, seed_number=None)
    return serialize_to_rom(written_world(world, config), base, config=config), places, built


@cache
def _built_on(base: bytes) -> Built:
    from tests.archipelago_cases import FLAG_CASES
    from zora.generate.pipeline import build, plan
    flag_string, zora_flag_string = FLAG_CASES[CASE]
    return build(plan(flag_string, SEED, zora_flag_string), base)


@needs_base_rom
def test_every_kind_of_place_reads_back_the_test_code() -> None:
    base = remember_repo_base_rom()
    rom, places, _ = every_kind(base, TEST_CODE)
    parsed = parse_rom(rom)
    for kind, place in places.items():
        assert read_item(parsed, place) == TEST_CODE, (kind, place.name)


@needs_base_rom
def test_compass_chime_reads_six_bits_in_an_archipelago_rom() -> None:
    """Compass Chime's room item read becomes JSR ReadRoomItem6 / AND #$3F where ap-items is written,
    and stays the game's five-bit read elsewhere."""
    from zora.rom.flags2_patch_data import PATCHES
    from zora.rom.owner_patches import (
        FIVE_BIT_ROOM_ITEM_READ,
        owner_patch_writes,
        read_room_item_6_address,
    )
    remember_repo_base_rom()
    address = read_room_item_6_address()
    six_bit_read = bytes([0x20, address & 0xFF, address >> 8, 0x29, 0x3F])
    chime = {offset for offset, piece in PATCHES["compass-chime"]
             if isinstance(piece, bytes) and FIVE_BIT_ROOM_ITEM_READ in piece}
    assert len(chime) == 1

    def chime_piece(archipelago_rom: bool) -> bytes:
        return next(data for offset, data in owner_patch_writes(["compass_chime"], archipelago_rom=archipelago_rom)
                    if offset in chime)

    assert six_bit_read in chime_piece(True) and FIVE_BIT_ROOM_ITEM_READ not in chime_piece(True)
    assert FIVE_BIT_ROOM_ITEM_READ in chime_piece(False) and six_bit_read not in chime_piece(False)
