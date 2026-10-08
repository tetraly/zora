"""The B10 CODE patches in the emulator (features-behavior.md; asm/).

Each test runs PRG0 with ZORA's code patches applied and, where the effect
is a change from PRG0, the same script on PRG0 as the control."""
import dataclasses
import os
from functools import cache
from pathlib import Path

import pytest

from tests.emulator import (
    INV_BOMBS, INV_BOOMERANG, INV_RECORDER, PAUSED, SELECTED_ITEM_SLOT,
    LAST_BOSS_DEFEATED, OBJ_STATE, OBJ_TYPE, ROOM_ITEM_SLOT,
    ITEMS, OBJ_DIR, OBJ_Y,
    INV_BOOK, INV_MAP, STATUS_BAR_MAP_TRIGGER, STATUS_BAR_ROWS, INV_KEYS, LEVEL_1_MOUTH_X, LEVEL_1_TRIFORCE, LEVEL_INFO,
    CUR_LEVEL, CUR_OPENED_DOORS, CUR_PPU_CONTROL, OBJ_TIMER, OBJ_X, QUEST_NUMBERS, ROOM_ID,
    SHUTTER_TRIGGER, TRIFORCE_FANFARE_ACTIVE, TRIGGERED_DOOR_CMD, TRIGGERED_DOOR_DIR, Button, Direction,
    Emulator, Mode,
)
from zora.rom.code_patches import (
    SEED_CODE_LENGTH, SEED_CODE_ITEMS, SEED_CODE_ADDRESS, EXIT_ROOM_COUNT_FLAG, LEVEL_INFO_EXIT_ROOM_COUNT,
    code_patch_writes, exit_room_count,
)
from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.model.enums import BossSound, Item, ItemPosition, RoomAction, WallType
from zora.rom.game_config import GameConfig, HintMode
from zora.rom.parse.rom_file import parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom
from zora.rom.text_encoding import CHAR_TO_BYTE
from zora.generate.rng import Rng
from zora.generate.generation_pass import generate_shapes
from zora.generate.shapes.options import ShapeOptions

ALL_DOORS_OPEN = 0x0F
OPEN_DOOR_CMD = 0x06


def tiles(text: str, dash: int = CHAR_TO_BYTE["-"]) -> bytes:
    """`text` as name and label tiles; "-" as `dash` (PRG0's labels use tile $62 for it)."""
    return bytes(dash if letter == "-" else CHAR_TO_BYTE[letter] for letter in text)


ZELDA_NAME = tiles("ZELDA")
FIRST_QUEST, SECOND_QUEST = 0, 1


@cache
def vanilla() -> bytes:
    env = os.environ.get("ZORA_VANILLA_ROM")
    cand = Path(env) if env else BASE_ROM_PATH
    if not cand.exists():
        pytest.skip("vanilla ROM missing")
    return verify_base_rom(cand).read_bytes()


@cache
def patched() -> bytes:
    """PRG0 with every code patch."""
    rom = bytearray(vanilla())
    for offset, data in code_patch_writes():
        rom[offset:offset + len(data)] = data
    return bytes(rom)


# --- FP-LOCK-01 ---------------------------------------------------------------

def _register_zelda(rom: bytes) -> Emulator:
    emu = Emulator(rom)
    emu.boot_to_file_select()
    emu.register_file(ZELDA_NAME)
    return emu


def test_lock_zelda_name_keeps_the_first_quest() -> None:
    """FP-LOCK-01 (b): the name ZELDA no longer selects the second quest."""
    assert _register_zelda(vanilla())[QUEST_NUMBERS] == SECOND_QUEST      # control
    assert _register_zelda(patched())[QUEST_NUMBERS] == FIRST_QUEST


def test_lock_saved_second_quest_loads_as_first() -> None:
    """FP-LOCK-01 (a): a save file holding the second quest (made by PRG0)
    is read into the slot as the first quest."""
    saved = _register_zelda(vanilla()).save()
    for rom, quest in ((vanilla(), SECOND_QUEST), (patched(), FIRST_QUEST)):
        emu = Emulator(rom)
        emu.load(saved)
        emu.reset()
        emu.boot_to_file_select()
        assert emu.mode == Mode.FILE_SELECT
        assert emu[QUEST_NUMBERS] == quest


# --- FP-FIX-05 ---------------------------------------------------------------

def _shutter_trigger_by_frame(rom: bytes) -> list[tuple[int, int]]:
    """In level 1's start room, every door counted open, the shutter
    trigger set while an open-door command is pending: (trigger, command)
    for the next 12 frames."""
    emu = Emulator(rom)
    emu.new_game()
    emu.walk_into_level_1()
    emu[CUR_OPENED_DOORS] = ALL_DOORS_OPEN
    emu[SHUTTER_TRIGGER] = 1
    emu[TRIGGERED_DOOR_DIR] = Direction.UP
    emu[TRIGGERED_DOOR_CMD] = OPEN_DOOR_CMD
    frames = []
    for _ in range(12):
        emu.run(1)
        frames.append((emu[SHUTTER_TRIGGER], emu[TRIGGERED_DOOR_CMD]))
    return frames


def test_shutters_wait_while_a_door_command_is_pending() -> None:
    """FP-FIX-05: PRG0 clears the trigger at once (no unopened shutter);
    the patch keeps it while the command runs and clears it after."""
    prg0 = _shutter_trigger_by_frame(vanilla())
    zora = _shutter_trigger_by_frame(patched())
    assert all(trigger == 0 for trigger, _ in prg0)
    pending = [trigger for trigger, command in zora if command]
    after = [trigger for trigger, command in zora if not command]
    assert pending and all(pending) and after[-1] == 0


# --- FP-FIX-06 ---------------------------------------------------------------

MOUNTAIN_MAZE_SCREEN = 0x1B


def _whirlwind_trip_end(features_b10: bool) -> int:
    """Level 1's whirlwind origin set to the mountain maze screen; play the
    recorder holding level 1's triforce and return the screen the trip
    ends on."""
    world = parse_rom(vanilla())
    world.overworld.recorder_warp_destinations[0] = MOUNTAIN_MAZE_SCREEN
    emu = Emulator(serialize_to_rom(world, vanilla(), config=GameConfig(features_b10=features_b10)))
    emu.new_game()
    emu.play_recorder(LEVEL_1_TRIFORCE)
    return emu[ROOM_ID]


def test_whirlwind_is_not_held_by_the_maze() -> None:
    """FP-FIX-06: PRG0's maze check keeps the trip on the maze screen; with
    the patch it ends on the screen to its right, the level's entrance."""
    assert _whirlwind_trip_end(features_b10=False) == MOUNTAIN_MAZE_SCREEN
    assert _whirlwind_trip_end(features_b10=True) == MOUNTAIN_MAZE_SCREEN + 1


# --- FP-FIX-03 ---------------------------------------------------------------

VRAM_INCREMENT_32 = 0x04             # PPUCTRL bit 2
ENTERING_MODES = (Mode.PLAY, Mode.ENTER)


def _level_1_patterns(rom: bytes, increment_left_set: bool) -> bytes:
    """Whirlwind to level 1, walk in through its mouth and return the
    pattern tables once Link stands in the start room. With
    `increment_left_set`, the PPUCTRL shadow keeps the +32 increment bit on
    every frame until the level load starts, as a vertical tile-buffer
    record would leave it."""
    emu = Emulator(rom)
    emu.new_game()
    emu.play_recorder(LEVEL_1_TRIFORCE)
    emu.run_until(lambda: emu[OBJ_X] <= LEVEL_1_MOUTH_X, buttons=Button.LEFT)
    while not (emu.mode == Mode.PLAY and emu[CUR_LEVEL] == 1):
        if increment_left_set and emu.mode in ENTERING_MODES:
            emu[CUR_PPU_CONTROL] |= VRAM_INCREMENT_32
        emu.run(1, Button.UP)
        assert emu.frames < 5000
    return emu.pattern_tables()


def test_level_patterns_load_with_a_plus_1_increment() -> None:
    """FP-FIX-03: with the +32 increment left set, PRG0 loads level 1's
    patterns scrambled; the patch loads them as a normal entry does."""
    normal = _level_1_patterns(vanilla(), increment_left_set=False)
    assert _level_1_patterns(vanilla(), increment_left_set=True) != normal      # control
    assert _level_1_patterns(patched(), increment_left_set=True) == normal


# --- FP-FIX-02 ---------------------------------------------------------------

FANFARE_FRAMES = 0x40
FANFARE_HALT_FRAMES = 0xC0           # TakePowerTriforce halts Link this long


def _door_redraw_during_fanfare(rom: bytes, fanfare: bool) -> tuple[bytes, bytes]:
    """Level 1's start room: open the north door (an open-door command),
    with or without the Triforce of Power fanfare running; return the
    nametables before and 20 frames after."""
    emu = Emulator(rom)
    emu.new_game()
    emu.walk_into_level_1()
    before = emu.ciram()
    if fanfare:
        emu[TRIFORCE_FANFARE_ACTIVE] = 1
        emu[OBJ_TIMER] = FANFARE_FRAMES
    emu[TRIGGERED_DOOR_DIR] = Direction.UP
    emu[TRIGGERED_DOOR_CMD] = OPEN_DOOR_CMD
    emu.run(20)
    return before, emu.ciram()


def test_fanfare_flash_keeps_a_pending_screen_update() -> None:
    """FP-FIX-02: during the fanfare PRG0 discards the door's tile update
    (the flash's palette selection wins); the patch draws it, as without
    the fanfare. The spec's likely effect is confirmed."""
    before, opened = _door_redraw_during_fanfare(vanilla(), fanfare=False)
    assert before != opened
    prg0_before, prg0_after = _door_redraw_during_fanfare(vanilla(), fanfare=True)
    assert prg0_after == prg0_before                                      # control
    # Within the patched ROM (its status-bar label differs from PRG0's, FP-ROAR-01).
    _, patched_opened = _door_redraw_during_fanfare(patched(), fanfare=False)
    assert _door_redraw_during_fanfare(patched(), fanfare=True)[1] == patched_opened


# --- FP-ENTR-02 ---------------------------------------------------------------

LEVEL_1_START_ROOM = 0x73
ROOM_NORTH_OF_START = 0x63
LEVEL_1_ENTRANCE_SCREEN = 0x37


def _walk_out_of_start_room(rom: bytes, direction: Button, exit_room: int | None) -> tuple[int, int]:
    """Level 1's start room, holding a key: set the level's exit-room
    count to `exit_room` (as level information would) and walk through the
    door in `direction`; return (CurLevel, RoomId) once Link can move."""
    emu = Emulator(rom)
    emu.new_game()
    emu.walk_into_level_1()
    assert emu[ROOM_ID] == LEVEL_1_START_ROOM
    emu[INV_KEYS] = 1                       # the north door is locked
    if exit_room is not None:
        emu[LEVEL_INFO + LEVEL_INFO_EXIT_ROOM_COUNT] = exit_room | EXIT_ROOM_COUNT_FLAG
    emu.run_until(lambda: emu.mode != Mode.PLAY, buttons=direction, limit=400)
    emu.run_until(lambda: emu.mode == Mode.PLAY, limit=400)
    return emu[CUR_LEVEL], emu[ROOM_ID]


def test_moving_into_the_exit_room_leaves_the_level() -> None:
    """FP-ENTR-02: with the count naming the room north of the start
    room, walking north leaves level 1 exactly as walking out of its south
    edge does; PRG0 enters the room."""
    south_exit = _walk_out_of_start_room(vanilla(), Button.DOWN, None)
    assert south_exit == (0, LEVEL_1_ENTRANCE_SCREEN)
    assert _walk_out_of_start_room(vanilla(), Button.UP, ROOM_NORTH_OF_START) == (1, ROOM_NORTH_OF_START)
    assert _walk_out_of_start_room(patched(), Button.UP, ROOM_NORTH_OF_START) == south_exit
    assert _walk_out_of_start_room(patched(), Button.UP, None) == (1, ROOM_NORTH_OF_START)


def test_exit_room_counts_on_prg0() -> None:
    """FP-ENTR-02's count on PRG0's quest-1 levels: the leading rooms of
    the block, from room 0, that belong to no level or to this one."""
    world = parse_rom(vanilla())
    counts = {level.level_num: exit_room_count(world, level) for level in world.levels}
    for level in world.levels:
        count = counts[level.level_num]
        assert all(level.block.owner_of(n) in (None, level) for n in range(count))
        assert count == 128 or level.block.owner_of(count) not in (None, level)


# --- FP-BOOK-01 ---------------------------------------------------------------

LEVEL_1_MAP = 0x01                   # InvMap bit
ITEM_SPOT_ON_LINKS_PATH = ItemPosition(2)   # level 1's third item spot, above the entrance


def _status_bar_in_level_1(rom: bytes, book: bool, level_map: bool) -> bytes:
    """The status bar after walking into level 1 holding the Book of Magic
    and/or level 1's map."""
    emu = Emulator(rom)
    emu.new_game()
    emu[INV_BOOK] = int(book)
    emu[INV_MAP] = LEVEL_1_MAP if level_map else 0
    emu.walk_into_level_1()
    return emu.nametable(*STATUS_BAR_ROWS)


def test_book_counts_as_the_level_map() -> None:
    """FP-BOOK-01: inside a level, the Book shows the map as the level's
    map does; PRG0 shows none."""
    no_map = _status_bar_in_level_1(vanilla(), book=False, level_map=False)
    with_map = _status_bar_in_level_1(vanilla(), book=False, level_map=True)
    assert no_map != with_map
    assert _status_bar_in_level_1(vanilla(), book=True, level_map=False) == no_map      # control
    # Within the patched ROM (its status-bar label differs from PRG0's, FP-ROAR-01).
    patched_map = _status_bar_in_level_1(patched(), book=False, level_map=True)
    assert _status_bar_in_level_1(patched(), book=True, level_map=False) == patched_map
    assert _status_bar_in_level_1(patched(), book=False, level_map=False) != patched_map


def _take_book_in_level_1(features_b10: bool) -> tuple[bool, bool]:
    """The Book lies in level 1's start room, on Link's way north; walk
    up until he holds it. Return whether the map redraw was requested, and
    whether the status bar changed."""
    world = parse_rom(vanilla())
    start_room = next(level for level in world.levels if level.level_num == 1).block.room(LEVEL_1_START_ROOM)
    start_room.item = Item.BOOK
    start_room.item_position = ITEM_SPOT_ON_LINKS_PATH
    emu = Emulator(serialize_to_rom(world, vanilla(), config=GameConfig(features_b10=features_b10)))
    emu.new_game()
    emu.walk_into_level_1()
    before = emu.nametable(*STATUS_BAR_ROWS)
    requested = False
    while not emu[INV_BOOK]:
        emu.run(1, Button.UP)
        requested |= emu[STATUS_BAR_MAP_TRIGGER] != 0
        assert emu.frames < 5000
    emu.run(10)
    return requested, emu.nametable(*STATUS_BAR_ROWS) != before


def test_taking_the_book_draws_the_map() -> None:
    """FP-BOOK-01: taking the Book requests the status-bar map redraw, and
    the map appears at once."""
    assert _take_book_in_level_1(features_b10=False) == (False, False)       # control
    assert _take_book_in_level_1(features_b10=True) == (True, True)


# --- FP-HASH-01 ---------------------------------------------------------------

# The seed code's left sprites: OAM records 24-27 (offsets $60-$6C), at the
# heading row's Y.
SEED_CODE_RECORDS = range(24, 28)
SEED_CODE_SPRITE_Y = 0x27
OAM_RECORD = 4
CODE_HEADING = (0x20A8, bytes([0x0C, 0x18, 0x0D, 0x0E]))    # "CODE" at PPU row 5, column 8


def _finished(seed: int) -> bytes:
    world = parse_rom(vanilla())
    generate_shapes(world, Rng(seed), ShapeOptions())
    return serialize_to_rom(world, vanilla(), config=GameConfig(features_b10=True))


def _file_select_code(rom: bytes) -> tuple[bytes, bytes]:
    """The seed code's OAM records and the heading's first tiles, once a file
    is registered."""
    emu = Emulator(rom)
    emu.boot_to_file_select()
    emu.register_file()
    sprites = emu.sprites()
    code = b"".join(sprites[OAM_RECORD * record:OAM_RECORD * (record + 1)] for record in SEED_CODE_RECORDS)
    heading_address, heading = CODE_HEADING
    return code, emu.nametable(heading_address, len(heading))


def test_file_select_shows_the_seed_code() -> None:
    """FP-HASH-01: the seed's code, four items on the heading row after the label;
    the code's bytes lie in the spec's set and follow the build."""
    first, second = _finished(11), _finished(12)
    for rom in (first, second):
        assert all(item in SEED_CODE_ITEMS for item in rom[SEED_CODE_ADDRESS:SEED_CODE_ADDRESS + SEED_CODE_LENGTH])
    assert first[SEED_CODE_ADDRESS:SEED_CODE_ADDRESS + SEED_CODE_LENGTH] != second[SEED_CODE_ADDRESS:SEED_CODE_ADDRESS + SEED_CODE_LENGTH]
    assert _finished(11) == first                                         # same build, same code

    code, heading = _file_select_code(first)
    assert heading == CODE_HEADING[1]
    assert all(code[OAM_RECORD * i] == SEED_CODE_SPRITE_Y for i in range(len(SEED_CODE_RECORDS)))
    assert _file_select_code(second)[0] != code
    prg0_code, _ = _file_select_code(vanilla())
    assert all(prg0_code[OAM_RECORD * i] != SEED_CODE_SPRITE_Y for i in range(len(SEED_CODE_RECORDS)))


# --- FP-ENTR-01 ---------------------------------------------------------------

SWORD = 1                            # Items+0, the sword
SWORD_SLOTS = range(13, 15)          # object slots the sword thrust uses
START_X = 0x78
OVERWORLD_START = (START_X, 0x8D)
DUNGEON_WALKED_IN = (START_X, 0xCD)   # placed at $DD, walks in
FACING_NONE = 0


def _sword_thrusts(emu: Emulator) -> bool:
    """Press A; does a sword object appear within 20 frames?"""
    emu.run(2, Button.A)
    thrust = False
    for _ in range(20):
        emu.run(1)
        thrust |= any(emu[OBJ_STATE + slot] for slot in SWORD_SLOTS)
    return thrust


def _overworld_start(features_b10: bool) -> tuple[tuple[int, int, int], bool, bool]:
    """PRG0's world serialized: Link's (X, Y, direction) at the start,
    whether the sword works at once, and whether it works after one move."""
    rom = serialize_to_rom(parse_rom(vanilla()), vanilla(), config=GameConfig(features_b10=features_b10))
    emu = Emulator(rom)
    emu.new_game()
    emu[ITEMS] = SWORD
    emu.run(5)
    placed = (emu[OBJ_X], emu[OBJ_Y], emu[OBJ_DIR])
    start = emu.save()
    at_once = _sword_thrusts(emu)
    emu.load(start)
    emu.run(8, Button.RIGHT)
    return placed, at_once, _sword_thrusts(emu)


def test_overworld_start_faces_no_direction() -> None:
    """FP-ENTR-01, code 0: X $78, the start Y, direction $00. Found in
    play: until Link first moves, the sword (and the B item) do nothing;
    then both work. PRG0 starts him facing up, armed."""
    assert _overworld_start(features_b10=False) == ((*OVERWORLD_START, Direction.UP), True, True)
    assert _overworld_start(features_b10=True) == ((*OVERWORLD_START, FACING_NONE), False, True)


def test_overworld_start_y_moves_out_of_level_information() -> None:
    """FP-ENTR-01 with OW-START-01: a seed's start Y is read from the
    patch's byte; LevelInfo_StartY keeps PRG0's $8D; Link starts there."""
    for seed in range(40):
        world = parse_rom(vanilla())
        generate_shapes(world, Rng(seed), ShapeOptions())
        if world.overworld.start_position_y != OVERWORLD_START[1]:
            break
    rom = serialize_to_rom(world, vanilla(), config=GameConfig(features_b10=True))
    assert parse_rom(rom).overworld.start_position_y == world.overworld.start_position_y
    emu = Emulator(rom)
    emu.new_game()
    assert (emu[ROOM_ID], emu[OBJ_X], emu[OBJ_Y]) == (
        world.overworld.start_screen, START_X, world.overworld.start_position_y)


def _dungeon_arrival(features_b10: bool) -> tuple[int, int, int]:
    rom = serialize_to_rom(parse_rom(vanilla()), vanilla(), config=GameConfig(features_b10=features_b10))
    emu = Emulator(rom)
    emu.new_game()
    emu.play_recorder(LEVEL_1_TRIFORCE)
    emu.run_until(lambda: emu[OBJ_X] <= LEVEL_1_MOUTH_X, buttons=Button.LEFT)
    emu.run_until(lambda: emu.mode == Mode.PLAY and emu[CUR_LEVEL] == 1, buttons=Button.UP, limit=1000)
    return emu[OBJ_X], emu[OBJ_Y], emu[OBJ_DIR]


def test_dungeon_arrival_matches_prg0() -> None:
    """FP-ENTR-01, code 2: X $78, Y $DD, facing up, as PRG0; Link then
    walks in to Y $CD before he can move."""
    prg0 = _dungeon_arrival(features_b10=False)
    assert prg0 == (*DUNGEON_WALKED_IN, Direction.UP)
    assert _dungeon_arrival(features_b10=True) == prg0


# --- FP-FIX-04 ---------------------------------------------------------------

EAST_DOOR = 0x01                     # CurOpenedDoors bit


def _power_triforce_pickup(features_b10: bool) -> dict[str, int]:
    """Level 1's start room with a last-boss secret trigger, a shutter on
    its east side and the Triforce of Power on Link's way north, activated
    as Ganon's death activates it. Walk up and take it; return the frames
    (from the start of the walk) of the pickup and of the shutter opening,
    and LastBossDefeated and ObjType slot 0 right after the pickup."""
    world = parse_rom(vanilla())
    room = next(level for level in world.levels if level.level_num == 1).block.room(LEVEL_1_START_ROOM)
    room.item = Item.TRIFORCE_OF_POWER
    room.item_position = ITEM_SPOT_ON_LINKS_PATH
    room.room_action = RoomAction.LAST_BOSS
    room.walls = dataclasses.replace(room.walls, east=WallType.SHUTTER_DOOR)
    emu = Emulator(serialize_to_rom(world, vanilla(), config=GameConfig(features_b10=features_b10)))
    emu.new_game()
    emu.walk_into_level_1()
    emu[OBJ_STATE + ROOM_ITEM_SLOT] = 0      # Ganon_ActivateRoomItem
    result: dict[str, int] = {}
    for frame in range(400):
        emu.run(1, Button(0) if "taken" in result else Button.UP)
        if "taken" not in result and emu[TRIFORCE_FANFARE_ACTIVE]:
            result.update(taken=frame, last_boss=emu[LAST_BOSS_DEFEATED], obj_type_0=emu[OBJ_TYPE])
        if "opened" not in result and emu[CUR_OPENED_DOORS] & EAST_DOOR:
            result["opened"] = frame
    return result


def test_power_triforce_pickup_opens_the_last_boss_shutters() -> None:
    """FP-FIX-04: PRG0 opens the shutter after the $C0-frame fanfare;
    the patch sets LastBossDefeated to 2 and ObjType slot 0 at the pickup
    and opens it during the fanfare. The spec's likely effect is confirmed."""
    prg0 = _power_triforce_pickup(features_b10=False)
    zora = _power_triforce_pickup(features_b10=True)
    assert prg0["taken"] == zora["taken"]
    assert (prg0["last_boss"], prg0["obj_type_0"]) == (0, 0)
    assert (zora["last_boss"], zora["obj_type_0"]) == (2, 1)
    assert prg0["opened"] - prg0["taken"] > FANFARE_HALT_FRAMES
    assert zora["opened"] - zora["taken"] < FANFARE_HALT_FRAMES // 8


# --- FP-ROAR-01 ---------------------------------------------------------------

ROOM_LABEL = 0x2076, 9                                   # PPU address, tiles
LABEL_DASH_TILE = 0x62
PRG0_LABEL = tiles(" -LIFE-  ", dash=LABEL_DASH_TILE)
USUAL_LABEL = tiles(" -LIFE-  ")
BOSS_SOUND_LABEL = tiles("BOSS NEAR")                  # ZORA's own
LABEL_PIXELS = (slice(0, 40), slice(160, 256))           # the label's corner of the frame


def _room_labels(features_b10: bool) -> tuple[bytes, bytes, bytes, bytes]:
    """Level 1's start room given a boss sound: the label on the
    overworld, in that room and in the room north of it, and the label's
    pixels on the overworld."""
    world = parse_rom(vanilla())
    room = next(level for level in world.levels if level.level_num == 1).block.room(LEVEL_1_START_ROOM)
    room.boss_sound = BossSound.ROAR_AQUAMENTUS_GLEEOK_GANON
    emu = Emulator(serialize_to_rom(world, vanilla(), config=GameConfig(features_b10=features_b10)))
    emu.new_game()
    emu.run(10)
    overworld = emu.nametable(*ROOM_LABEL)
    pixels = emu.last_frame[LABEL_PIXELS].tobytes()
    emu.walk_into_level_1()
    sound_room = emu.nametable(*ROOM_LABEL)
    emu[INV_KEYS] = 1                       # the north door is locked
    emu.run_until(lambda: emu[ROOM_ID] == ROOM_NORTH_OF_START, buttons=Button.UP, limit=600)
    emu.run_until(lambda: emu.mode == Mode.PLAY, limit=400)
    emu.run(4)
    return overworld, sound_room, emu.nametable(*ROOM_LABEL), pixels


def test_boss_sound_room_changes_the_label() -> None:
    """FP-ROAR-01: the usual label everywhere (dashes $2F, drawn
    pixel-identical to PRG0's $62), ZORA's second label in a boss-sound
    room until the next room's check."""
    prg0 = _room_labels(features_b10=False)
    zora = _room_labels(features_b10=True)
    assert prg0[:3] == (PRG0_LABEL, PRG0_LABEL, PRG0_LABEL)
    assert zora[:3] == (USUAL_LABEL, BOSS_SOUND_LABEL, USUAL_LABEL)
    assert zora[3] == prg0[3]


# --- FP-HOT-01 ----------------------------------------------------------------

HOT_KEY_MODE = ITEMS + 0x23          # the saved mode byte ZORA chose (docs/rom-map.md)
HOT_KEY_LABEL = 0x2984, 9            # the item screen heading's place
INVENTORY_HEADING = tiles("INVENTORY")
CYCLING_LABEL = tiles("ITEMS    ")                    # ZORA's own
PAUSING_LABEL = tiles("PAUSE    ")                    # ZORA's own
BOOMERANG_SLOT, BOMB_SLOT, RECORDER_SLOT = 0, 1, 5


def _armed_start(features_b10: bool) -> Emulator:
    """A new file on PRG0's world, holding the boomerang, bombs and the
    recorder, facing up."""
    rom = serialize_to_rom(parse_rom(vanilla()), vanilla(), config=GameConfig(features_b10=features_b10))
    emu = Emulator(rom)
    emu.new_game()
    emu.run(8, Button.UP)
    emu[INV_BOOMERANG] = 1
    emu[INV_BOMBS] = 4
    emu[INV_RECORDER] = 1
    emu.run(5)
    return emu


def _select_presses(emu: Emulator, count: int) -> list[tuple[int, int]]:
    """(SelectedItemSlot, Paused) after each Select press."""
    states = []
    for _ in range(count):
        emu.press(Button.SELECT, after=6)
        states.append((emu[SELECTED_ITEM_SLOT], emu[PAUSED]))
    return states


def test_select_cycles_the_b_item_in_a_new_file() -> None:
    """FP-HOT-01, mode 0 (a new file): Select selects the next occupied
    B slot and does not pause; PRG0 pauses and unpauses."""
    prg0 = _armed_start(features_b10=False)
    assert _select_presses(prg0, 2) == [(BOOMERANG_SLOT, 1), (BOOMERANG_SLOT, 0)]
    zora = _armed_start(features_b10=True)
    assert zora[HOT_KEY_MODE] == 0
    assert _select_presses(zora, 3) == [(BOMB_SLOT, 0), (RECORDER_SLOT, 0), (BOOMERANG_SLOT, 0)]


def test_item_screen_toggles_the_mode_and_its_label() -> None:
    """FP-HOT-01: the item screen shows the mode's label in place of the
    heading (its other four tiles blank); Select there toggles the mode
    and redraws the label; back in play, Select pauses as in PRG0."""
    prg0 = _armed_start(features_b10=False)
    prg0.open_item_screen()
    assert prg0.nametable(*HOT_KEY_LABEL) == INVENTORY_HEADING             # control
    zora = _armed_start(features_b10=True)
    zora.open_item_screen()
    assert zora.nametable(*HOT_KEY_LABEL) == CYCLING_LABEL
    zora.press(Button.SELECT, after=10)
    assert (zora[HOT_KEY_MODE], zora.nametable(*HOT_KEY_LABEL)) == (1, PAUSING_LABEL)
    zora.close_item_screen()
    assert _select_presses(zora, 2) == [(BOOMERANG_SLOT, 1), (BOOMERANG_SLOT, 0)]


def test_hot_key_mode_is_saved_with_the_file() -> None:
    """FP-HOT-01: the mode is saved with the file and restored when the
    file is chosen (the spec's unobserved point, observed)."""
    emu = _armed_start(features_b10=True)
    emu.open_item_screen()
    emu.press(Button.SELECT, after=10)
    emu.save_and_reload()
    assert emu[HOT_KEY_MODE] == 1
    emu.run(8, Button.UP)
    assert _select_presses(emu, 1)[0][1] == 1                               # Select pauses


# --- a finished ROM ---------------------------------------------------------------

def test_finished_rom_starts_on_its_start_screen() -> None:
    """A ZORA seed with the code patches boots, registers a file and
    starts Link on the seed's start screen (OW-START-01)."""
    world = parse_rom(vanilla())
    generate_shapes(world, Rng(7), ShapeOptions())
    rom = serialize_to_rom(world, vanilla(),
                           config=GameConfig(hint_mode=HintMode.CONSTERNATION, features_b10=True))
    emu = Emulator(rom)
    emu.new_game()
    assert emu.mode == Mode.PLAY and emu[ROOM_ID] == world.overworld.start_screen
