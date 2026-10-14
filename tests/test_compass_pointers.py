"""Every level's compass points at its Triforce room (Zelda's in level 9).

The compass reads the level's Triforce-room record (level information +$30, LevelInfo_TriforceRoomId
when loaded). Beta 4 kept PRG0's record in a level from a vanilla set (dungeon_quest.vanilla_set):
the passes move the triforce (the late gate's re-deal, VA-REJ-03 step 1, re-points the record, A16),
so every level but 9 under 1st Quest (C02 = 0) and 2nd Quest (C02 = 1), and a first- or
second-quest set under Mixed + Shapes (C02 = 4), pointed at PRG0's Triforce rooms. A player
reported it on seed 2535214729 (beta 4: levels 1-6 first quest, 7-9 second quest; every compass but
level 9's wrong).

The Triforce room is read from the written ROM, not the model: the room whose item byte's low five
bits are the triforce ($1B), or in level 9 the room whose monster list is $37; with Encode level data
on, from the decoded level data (level_encoding.decode_level_data), which is what the game loads.
A triforce in an item cellar is pointed at through the cellar's room (derive_triforce_room_ptr).
"""
from dataclasses import dataclass
from functools import cache

import pytest

from tests.test_coop_reserved import z1r_with
from zora.flags.codec import decode, encode
from zora.flags.fields import ENCODE_LEVEL_DATA, DungeonLayoutSource, ThreeState
from zora.generate.pipeline import Built, build, finish, plan
from zora.model.enums import Enemy, Item
from zora.model.levels import LEVEL_9, Level
from zora.rom import level_encoding
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.layout import (
    LEVEL_1_6_DATA_ADDRESS,
    LEVEL_7_9_DATA_ADDRESS,
    LEVEL_INFO_ADDRESS,
    LEVEL_INFO_SIZE,
    LEVEL_TABLE_SIZE,
    ROOM_BLOCK_ADDRESSES_Q1,
    ROOM_BLOCK_HIGH_BYTES,
)
from zora.rom.serialize.levels import derive_triforce_room_ptr

TRIFORCE_RECORD = 0x30                    # LevelInfo_TriforceRoomId's offset in a level's information
ITEM_TABLE, MONSTER_TABLE, LAYOUT_TABLE = 4, 2, 3     # LevelBlockAttrsE, C and D
ITEM_CODE_MASK, MONSTER_LIST_MASK, MIXED_LIST_BIT = 0x1F, 0x3F, 0x80
ROOM_BLOCK_SIZE = 0x300
# The plain ROM's room-block address for each high byte in LevelBlockAddrsQ1 ($87 $8A $8D $90)
BLOCK_ADDRESSES = dict(zip(ROOM_BLOCK_HIGH_BYTES, (LEVEL_1_6_DATA_ADDRESS, LEVEL_7_9_DATA_ADDRESS,
                                                   LEVEL_1_6_DATA_ADDRESS + 2 * ROOM_BLOCK_SIZE,
                                                   LEVEL_7_9_DATA_ADDRESS + 2 * ROOM_BLOCK_SIZE), strict=True))

FIRST_QUEST = z1r_with(options={"C02": DungeonLayoutSource.FIRST_QUEST})
SECOND_QUEST = z1r_with(options={"C02": DungeonLayoutSource.SECOND_QUEST})
MIXED_WITH_SHAPES = z1r_with(options={"C02": DungeonLayoutSource.MIXED_WITH_SHAPES})
# Mixed + Shapes seeds covering a second-quest set of levels 1-6, of levels 7-9, and none (a
# first-quest set with a shapes set), plain and encoded (tests/test_level_encoding_fold.py)
QUEST_CASES = [(FIRST_QUEST, 1), (SECOND_QUEST, 1), (SECOND_QUEST, 2)]
CASES = [*QUEST_CASES, *((MIXED_WITH_SHAPES, seed) for seed in (1, 2, 5))]
ENCODED_CASES = [*QUEST_CASES, *((MIXED_WITH_SHAPES, seed) for seed in (1, 2, 7))]
# The player's seed (beta 4); its flag string isn't known, so the regression case is Mixed + Shapes on
# the test baseline, which draws the same sets: levels 1-6 first quest, levels 7-9 second quest
PLAYER_SEED = 2535214729
ENCODED_ONLY = pytest.mark.skipif(not level_encoding.is_available(), reason="level encoding is not installed")


def encoded(flags: str) -> str:
    return encode(decode(flags).updated(toggles={ENCODE_LEVEL_DATA.id: ThreeState.ON}))


@dataclass(frozen=True)
class Finished:
    built: Built
    rom: bytes
    blocks: dict[int, bytes]          # the room block each high byte names, as the game loads it


@cache
def finished(flags: str, seed: int) -> Finished:
    chosen = plan(flags, seed)
    base = remember_repo_base_rom()
    built = build(chosen, base)
    rom = finish(built, base)
    if chosen.config.level_encoding is None:
        blocks = {high: rom[address:address + ROOM_BLOCK_SIZE] for high, address in BLOCK_ADDRESSES.items()}
    else:
        plain = level_encoding.decode_level_data(rom, chosen.config.level_encoding)
        first_block = LEVEL_1_6_DATA_ADDRESS - level_encoding.LEVEL_DATA_START
        blocks = {high: plain[first_block + index * ROOM_BLOCK_SIZE:][:ROOM_BLOCK_SIZE]
                  for index, high in enumerate(ROOM_BLOCK_HIGH_BYTES[:2])}
    return Finished(built, rom, blocks)


def compass(rom: bytes, level: Level) -> int:
    return rom[LEVEL_INFO_ADDRESS + level.level_num * LEVEL_INFO_SIZE + TRIFORCE_RECORD]


def triforce_room(case: Finished, level: Level) -> int:
    """The room the compass must name, from the room block the level's pointer names."""
    block = case.blocks[case.rom[ROOM_BLOCK_ADDRESSES_Q1 + 2 * level.level_num + 1]]

    def table(index: int, room: int) -> int:
        return block[index * LEVEL_TABLE_SIZE + room]

    if level.level_num == LEVEL_9:
        rooms = [room for room in level.room_nums
                 if table(MONSTER_TABLE, room) & MONSTER_LIST_MASK == Enemy.THE_KIDNAPPED
                 and not table(LAYOUT_TABLE, room) & MIXED_LIST_BIT]
    else:
        rooms = [room for room in level.room_nums if table(ITEM_TABLE, room) & ITEM_CODE_MASK == Item.TRIFORCE]
    if not rooms:                     # in an item cellar: its room
        return derive_triforce_room_ptr(level)
    assert len(rooms) == 1, f"level {level.level_num}: triforce rooms {rooms}"
    return rooms[0]


def check_compasses(flags: str, seed: int) -> list[int]:
    """Every compass on its Triforce room; returns the levels from a vanilla set."""
    case = finished(flags, seed)
    wrong = {level.level_num: (f"${compass(case.rom, level):02X}", f"${triforce_room(case, level):02X}")
             for level in case.built.world.levels if compass(case.rom, level) != triforce_room(case, level)}
    assert not wrong, f"compass, Triforce room by level: {wrong}"
    return [level.level_num for level in case.built.world.levels if level.is_second_quest]


@pytest.mark.parametrize(("flags", "seed"), CASES)
def test_every_compass_points_at_the_triforce_room(flags: str, seed: int) -> None:
    check_compasses(flags, seed)


@ENCODED_ONLY
@pytest.mark.parametrize(("flags", "seed"), ENCODED_CASES)
def test_every_compass_points_at_the_triforce_room_encoded(flags: str, seed: int) -> None:
    check_compasses(encoded(flags), seed)


def test_the_players_seed() -> None:
    """Regression (beta 4): levels 1-6 first quest and 7-9 second quest, the triforce moved off
    PRG0's room in the vanilla levels, every compass on the moved room."""
    assert check_compasses(MIXED_WITH_SHAPES, PLAYER_SEED) == [7, 8, 9]
    world = finished(MIXED_WITH_SHAPES, PLAYER_SEED).built.world
    prg0 = finished_prg0_records()
    moved = [level.level_num for level in world.levels[:8]
             if derive_triforce_room_ptr(level) != prg0[level.is_second_quest][level.level_num - 1]]
    assert moved, "no triforce moved: the case would not catch beta 4's bug"


@cache
def finished_prg0_records() -> dict[bool, list[int]]:
    """PRG0's Triforce-room records by quest (False: first, True: second), levels 1-9."""
    from zora.rom.parse.rom_file import parse_rom
    world = parse_rom(remember_repo_base_rom())
    return {False: [derive_triforce_room_ptr(level) for level in world.levels],
            True: [derive_triforce_room_ptr(level) for level in world.levels_2q]}


# --- in the game: an encoded second-quest level ------------------------------------------------

LEVEL_LOAD_FRAMES, SETTLE_FRAMES = 900, 40
LEVEL_BLOCK_ATTRS_E = 0x6A7E           # the loaded (decoded) block's LevelBlockAttrsE in WRAM
MAP_LEVELS = (1, 8)                    # one level of each set


@ENCODED_ONLY
@pytest.mark.parametrize("level_num", MAP_LEVELS)
def test_the_game_loads_the_compass_on_the_triforce_room(level_num: int) -> None:
    """2nd Quest (C02 = 1), encoded: the game loads the level (decoding its block into work RAM);
    the Triforce-room record it loaded names the room whose decoded item is the triforce, and that
    room is the one the model put the triforce in."""
    from tests.emulator import CUR_LEVEL, GAME_MODE, GAME_SUBMODE, LEVEL_INFO, Emulator, Mode
    case = finished(encoded(SECOND_QUEST), 1)
    level = case.built.world.levels[level_num - 1]
    assert level.is_second_quest
    emu = Emulator(case.rom)
    emu.new_game()
    emu[CUR_LEVEL] = level_num
    emu[GAME_MODE] = Mode.LOAD_LEVEL
    emu[GAME_SUBMODE] = 0
    emu.run_until(lambda: emu.mode == Mode.PLAY and emu[CUR_LEVEL] == level_num, limit=LEVEL_LOAD_FRAMES)
    emu.run(SETTLE_FRAMES)
    record = emu[LEVEL_INFO + TRIFORCE_RECORD]
    assert emu[LEVEL_BLOCK_ATTRS_E + record] & ITEM_CODE_MASK == Item.TRIFORCE
    assert record == derive_triforce_room_ptr(level) == triforce_room(case, level)
