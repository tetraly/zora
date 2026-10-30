"""Level 9's Triforce gate room is the walks' cell in every quest (zora/generate/late_gate/walk.py
level9_entry_room; a deviation from VA-WALK-08's fixed second-quest cell $64, docs/deviations.md).

Archipelago scan seed 100967 (Dungeon Quest: Mixed + Shapes, C02 = 4; with Move Start Rooms, B26):
level 9 is second-quest, its start room at $73 and its gate person in $63. With the walks' cell at
$64, $63's shutters counted closed, so level 9 could not be entered, in ZORA's walk and
Archipelago's logic alike. The game opens the shutters of whatever room holds the person
(InitUnderworldPersonC), which the emulator tests check: on that seed's ROM (Level 9 Entry: Open
Level 9, C08, so with no pieces) and on a CP-5 seed with 2nd Quest and Move Start Rooms whose gate
room also moved to $63 (the eight pieces)."""
from functools import cache

import pytest

from tests.emulator import CUR_OPENED_DOORS, INV_TRIFORCE, OBJ_TYPE, ROOM_ID, SHUTTER_TRIGGER
from tests.test_asnb_emulator import ALL_TRIFORCE_PIECES, GATE_FRAMES, LEVEL_9_ENTRANCE_PERSON, MONSTER_SLOTS
from tests.test_progressive_emulator import ENTER_ROOM_MODE, SWORD, Game
from zora.archipelago import build_from_strings
from zora.generate.acceptance_check import AcceptanceCheck
from zora.generate.late_gate.walk import level9_entry_room
from zora.generate.logic import FALSE
from zora.generate.pipeline import generate_rom, shipped_logic_rules
from zora.model.enums import Item
from zora.model.levels import GANON_LIST, L9_ENTRY_PERSON, LEVEL_9, Level
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

# Archipelago scan seed 100967: its two flag strings and the generation seed (100967 mod 1000)
SEED_100967 = ("3Ddc0upY5NKsNtiDRNOhXfpfvA2vN0k4hMMqCG4E", "13.7wKVIwlL", 967)
# CP-5 with Dungeon Quest: 2nd Quest (C02 = 1) and Move Start Rooms on (B26), seed 1: level 9's start
# room moved to $73, so its gate room to $63; Level 9 Entry as CP-5 has it (the eight pieces)
SECOND_QUEST_MOVED = ("8hq4BeR2oTx3ebLWKBddefzLRrUJ2v", "", 1)
GATE_ROOM, ENTRANCE = 0x63, 0x73
PRG0_SECOND_QUEST_GATE_ROOM = 0x64
TOP_SWORD_LEVEL = 3


def _gate_rooms(level: Level) -> list[int]:
    return [number for number in level.room_nums if level.block.room(number).enemy == L9_ENTRY_PERSON]


def test_seed_100967_level_9_can_be_entered() -> None:
    flags, zora_flags, seed = SEED_100967
    built = build_from_strings(flags, zora_flags, seed, remember_repo_base_rom())
    world = built.state.world
    level = next(level for level in world.levels if level.level_num == LEVEL_9)
    assert level.is_second_quest and level.entrance_room == ENTRANCE
    assert _gate_rooms(level) == [GATE_ROOM] == [level9_entry_room(level)] != [PRG0_SECOND_QUEST_GATE_ROOM]
    # Archipelago's logic: every place and event reachable (the Triforce of Power and Zelda were not)
    assert not [name for name, rule in (*built.logic.places.items(), *built.logic.events.items()) if rule == FALSE]
    # ZORA's own walk of the same world: past $63's shutters to Ganon with every item
    result = built.state.result
    assert result.item_shuffle_result is not None and result.overworld is not None
    check = AcceptanceCheck(world.levels, result.item_shuffle_result, world.overworld, result.overworld,
                            shipped_logic_rules(built.state.plan, world))
    ganon = next(room.room_num for room in level.rooms if room.enemy == GANON_LIST)
    assert check.can_reach_room(LEVEL_9, ganon, frozenset(int(item) for item in Item))
    assert check.collects_everything() and check.reaches_ganon_before_shutters_open()


@cache
def rom_for(case: tuple[str, str, int]) -> bytes:
    flags, zora_flags, seed = case
    return generate_rom(flags, seed, remember_repo_base_rom(), zora_flag_string=zora_flags).rom


def enter_the_gate_room(case: tuple[str, str, int], triforce: int) -> tuple[bool, bool, bool]:
    """Stand in $63 with these pieces and the top sword: whether the person is still there, whether
    the shutters were triggered and whether the room's doors opened."""
    game = Game(rom_for(case))
    SWORD.set_level(game.emu, TOP_SWORD_LEVEL)
    game.emu[INV_TRIFORCE] = triforce
    game.enter_level(LEVEL_9)
    game.emu[ROOM_ID] = GATE_ROOM
    game.start_mode(ENTER_ROOM_MODE)
    triggered = False
    for _ in range(GATE_FRAMES):
        game.emu.run(1)
        triggered |= bool(game.emu[SHUTTER_TRIGGER])
    present = any(game.emu[OBJ_TYPE + slot] == LEVEL_9_ENTRANCE_PERSON for slot in MONSTER_SLOTS)
    return present, triggered, bool(game.emu[CUR_OPENED_DOORS])


def test_seed_100967s_gate_room_opens_without_pieces() -> None:
    """Open Level 9 (C08): the person opens $63's shutters whatever the pieces."""
    assert enter_the_gate_room(SEED_100967, 0) == (False, True, True)


def test_a_moved_second_quest_gate_room_opens_with_the_pieces() -> None:
    assert enter_the_gate_room(SECOND_QUEST_MOVED, ALL_TRIFORCE_PIECES) == (False, True, True)
    assert enter_the_gate_room(SECOND_QUEST_MOVED, 0) == (True, False, False)


def test_the_moved_second_quest_case_is_what_it_says() -> None:
    flags, zora_flags, seed = SECOND_QUEST_MOVED
    world = build_from_strings(flags, zora_flags, seed, remember_repo_base_rom()).state.world
    level = next(level for level in world.levels if level.level_num == LEVEL_9)
    assert level.is_second_quest and level.entrance_room == ENTRANCE
    assert _gate_rooms(level) == [GATE_ROOM] == [level9_entry_room(level)]
