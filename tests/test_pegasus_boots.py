"""Pegasus Boots (ZORA string version 7; the owner's spec "Pegasus Boots for ZORA - Implementation
Spec", 2026-10-17; asm/flags2/pegasus-boots/): the flag, its refusals, its names, and the spec's
emulator cases, control against patched.

The control ROM is ZORA's output for the MVP baseline (level encoding off, seed 1); the patched ROM
is that output with pegasus-boots written over it (tests/test_flags2_emulator.py's both()). The
movement cases stand Link grid-aligned at (X $20, Y $6D) on the start screen, a clear run of more
than 80 pixels to the right, facing right; distances allow one 8-pixel step of tolerance (the spec's
figures assume position fraction 0). On PRG1 the pair is ZORA's own output on the PRG1 base, with
and without the flag. Not observed here (the owner's manual pass): doorways and shutters at speed,
the ladder and raft, Armos and gravestones, Like-Likes and Wallmasters, whirlwinds and the recorder,
diagonal input at intersections, edge transitions in every direction."""
from functools import cache
from pathlib import Path

import pytest

from tests.emulator import ITEMS, OBJ_X, OBJ_Y, ROOM_ID, SELECTED_ITEM_SLOT, Button, Emulator, Mode
from tests.test_feature_patches import vanilla
from tests.test_flags2_emulator import both, control, enter_room, rooms_holding
from tests.test_progressive_emulator import ENTER_ROOM_MODE, INV_BOOMERANG, INV_MAGIC_BOOMERANG, Game
from zora.flags import zora_flags
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import PEGASUS_BOOTS_CONFLICT, ZoraFlags
from zora.generate.pipeline import FlagsRefused, generate_rom, plan
from zora.generate.steps.hint_text import ItemNames, item_location_sentence
from zora.model.enums import Enemy, Item, Side, WallType
from zora.model.item_names import ITEM_NAMES, item_names
from zora.rom import flags2_patch_data
from zora.rom.base_rom import PRG1_ROM_PATH, piece_length
from zora.rom.code_patches import SEED_CODE_ADDRESS, SEED_CODE_LENGTH, draws_boots, seed_code, seed_code_values
from zora.rom.owner_patches import PATCHES_BY_FLAG, owner_patch_writes
from zora.rom.parse.rom_file import parse_rom
from zora.rom.revision import (
    PEGASUS_BOOTS_SPEED_CALL,
    Revision,
    back_to_revision,
    moved_to_prg0_layout,
    prg1_offset,
)

REPO = Path(__file__).resolve().parent.parent
FIELD = "pegasus_boots"
BOOTS = zora_flags.encode(ZoraFlags(pegasus_boots=ThreeState.ON))
WITH_DAMAGE = zora_flags.encode(ZoraFlags(pegasus_boots=ThreeState.ON, magical_boomerang_damage=ThreeState.ON))
SEED = 1

# RAM (the pinned disassembly's src/Variables.inc)
OBJ_DIR = 0x98
OBJ_STATE = 0xAC
OBJ_TIMER = 0x28
OBJ_GRID_OFFSET = 0x394
OBJ_QSPEED = 0x3BC
OBJ_INPUT_DIR = 0x3F8
BOOTS_CHARGE = 0x38F                 # ObjMovingLimit+15, the player boomerang's slot
EFFECT_REQUEST = 0x603               # SongRequest+3
BOOMERANG_EFFECT = 0x02
INV_BOMBS = 0x658
PLAY_AREA_TILES = 0x6530             # the overworld's tile map in work RAM
PLAY_AREA_SIZE = 0x2C0
STAIRS_TILE = 0x74
GROUND_TILE = 0x26                   # the start screen's most common tile, walkable
BAIT_SLOT = 0x0F
BAIT_STATE = 0x80                    # WieldFood's
BOMBS_SLOT = 1

WALK_SPEED, STAIRS_SPEED, L1_SPEED, L2_SPEED = 0x60, 0x30, 0x79, 0xA5
L1_CHARGE_FRAMES = 0x20
START_X, START_Y = 0x20, 0x6D
STEP = 8                             # Link's grid: one step of tolerance
B_RIGHT = Button.B | Button.RIGHT

# The boots' code (asm/flags2/pegasus-boots): WieldBoomerang's old body, and BootsSpeed's address
BOOTS_ROUTINES, BOOTS_ROUTINES_LENGTH = 0x14E48, 57
BOOTS_SPEED_PRG0 = 0x8E3E
BANK_5_SHIFT = 10                    # PRG1 moves this code 10 bytes on (revision.PRG1_MOVES)
JSR, NOP = 0x20, 0xEA

# The status bar's B-item sprite (left half) and the item tiles
B_ITEM_Y, B_ITEM_X = 31, 128
BOOT_TILE, BOOMERANG_TILE = 0x1C, 0x36
LINK_PALETTE, BLUE_PALETTE, L1_BOOTS_PALETTE = 0, 1, 2      # sprite palette rows
GORIYA_BOOMERANG_TILES = {0x36, 0x38, 0x3A, 0x3C}
# The blank priority sprites of every dungeon room (BlankPrioritySpriteTemplates)
MASK_SPRITES = range(16)
MASK_TILE = 0x51                     # background table, tiles $50/$51
PATTERN_TILE_SIZE = 16
BACKGROUND_TABLE = 0x1000

# Dungeon doors: where Link stands to walk through each side's door, and the button that does it
DOOR_APPROACH = {Side.NORTH: ((0x78, 0x45), Button.UP), Side.EAST: ((0xC8, 0x8D), Button.RIGHT),
                 Side.SOUTH: ((0x78, 0xBD), Button.DOWN), Side.WEST: ((0x28, 0x8D), Button.LEFT)}
NEXT_ROOM_STEP = {Side.NORTH: -0x10, Side.EAST: 1, Side.SOUTH: 0x10, Side.WEST: -1}
CUR_OPENED_DOORS = 0xEE              # a bit per opened door: DoorBits
DOOR_BITS = {Side.EAST: 0x01, Side.WEST: 0x02, Side.SOUTH: 0x04, Side.NORTH: 0x08}
# The loaded level's wall bytes, three bits a side (LevelBlockAttrsA: N and S; B: W and E)
WALL_FIELDS = {Side.NORTH: (0x687E, 5), Side.SOUTH: (0x687E, 2), Side.WEST: (0x68FE, 5), Side.EAST: (0x68FE, 2)}
WALL_BITS = 0x07
INV_CLOCK = 0x66C


def standing(rom: bytes, l1: int, l2: int, slot: int = 0, x: int = START_X, bombs: int = 0) -> Emulator:
    """A new game with the boots (or boomerangs) and bombs given and `slot` on B, Link grid-aligned
    at (x, START_Y) facing right."""
    emu = Emulator(rom)
    emu.new_game()
    emu.run(30)
    emu[INV_BOMBS] = bombs
    emu[INV_BOOMERANG], emu[INV_MAGIC_BOOMERANG], emu[SELECTED_ITEM_SLOT] = l1, l2, slot
    emu[OBJ_X], emu[OBJ_Y], emu[OBJ_GRID_OFFSET] = x, START_Y, 0
    emu.run(1, Button.RIGHT)
    emu.run(10)
    return emu


def moved(emu: Emulator, frames: int, buttons: Button) -> int:
    start = emu[OBJ_X]
    emu.run(frames, buttons)
    return emu[OBJ_X] - start


def near(distance: int, expected: int) -> bool:
    return abs(distance - expected) <= STEP


def fill_play_area(emu: Emulator, tile: int) -> None:
    for offset in range(PLAY_AREA_SIZE):
        emu[PLAY_AREA_TILES + offset] = tile


def b_item_sprite(emu: Emulator) -> tuple[int, int]:
    """The status bar's B-item sprite: its tile and palette."""
    oam = emu.sprites()
    entry = next(index for index in range(0, 256, 4) if (oam[index], oam[index + 3]) == (B_ITEM_Y, B_ITEM_X))
    return oam[entry + 1], oam[entry + 2] & 0x03


@cache
def prg1_pair() -> dict[str, bytes]:
    """ZORA's output on the PRG1 base, and that output with pegasus-boots written as generation
    writes it on PRG1 (revision.back_to_revision from PRG0's layout), so both hold one world."""
    if not PRG1_ROM_PATH.exists():
        pytest.skip(f"{PRG1_ROM_PATH.name} is not beside the PRG0 base")
    control = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, PRG1_ROM_PATH.read_bytes()).rom
    before = moved_to_prg0_layout(control)
    after = bytearray(before)
    for offset, data in owner_patch_writes([FIELD]):
        after[offset:offset + len(data)] = data
    return {"control": control, "patched": back_to_revision(control, Revision.PRG1, before, bytes(after))}


def pairs() -> list[str]:
    return ["PRG0", "PRG1"]


def pair(release: str) -> dict[str, bytes]:
    return both("pegasus-boots") if release == "PRG0" else prg1_pair()


# --- the flag ---------------------------------------------------------------------------------

def test_the_flag_is_version_7s_first_field_and_off_by_default() -> None:
    assert FIELD in zora_flags.PEGASUS_BOOTS_FIELDS and FIELD in zora_flags.PRODUCED_OWNER_FIELDS
    field = next(field for field in zora_flags.FIELDS if field.name == FIELD)
    assert (field.version, field.slots) == (7, zora_flags.THREE_STATE_SLOTS)
    assert zora_flags.decode("").pegasus_boots is ThreeState.OFF
    assert zora_flags.decode(BOOTS).pegasus_boots is ThreeState.ON and BOOTS.startswith("7.")
    assert PATCHES_BY_FLAG[FIELD] == ("pegasus-boots",)


def test_magical_boomerang_damage_is_refused_with_the_boots() -> None:
    with pytest.raises(FlagsRefused, match="Pegasus Boots cannot be used with Magical Boomerang"):
        plan(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, WITH_DAMAGE)
    flags = zora_flags.decode(WITH_DAMAGE)
    assert zora_flags.conflicts(flags, plan(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED).settings) == [
        (PEGASUS_BOOTS_CONFLICT, ("pegasus_boots", "magical_boomerang_damage"))]


@pytest.mark.parametrize(("boots", "damage", "dropped"), [
    (ThreeState.POSSIBLE, ThreeState.ON, "pegasus_boots"),
    (ThreeState.ON, ThreeState.POSSIBLE, "magical_boomerang_damage"),
    (ThreeState.POSSIBLE, ThreeState.POSSIBLE, "magical_boomerang_damage"),
])
def test_a_question_mark_into_the_conflict_resolves_off(boots: ThreeState, damage: ThreeState, dropped: str) -> None:
    asked = ZoraFlags(pegasus_boots=boots, magical_boomerang_damage=damage)
    both_on = ZoraFlags(pegasus_boots=ThreeState.ON, magical_boomerang_damage=ThreeState.ON)
    settings = plan(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED).settings
    resolved, _ = zora_flags.resolve_owner_dependencies(both_on, asked, settings, settings)
    assert getattr(resolved, dropped) is ThreeState.OFF
    assert sum(resolved.is_on(name) for name in ("pegasus_boots", "magical_boomerang_damage")) == 1


def test_the_default_output_keeps_prg0s_bytes_at_every_boots_site() -> None:
    control = both("pegasus-boots")["control"]
    original = vanilla()
    for offset, piece in flags2_patch_data.PATCHES["pegasus-boots"]:
        length = piece_length(piece)
        assert control[offset:offset + length] == original[offset:offset + length], hex(offset)


# --- names ------------------------------------------------------------------------------------

def test_the_boots_names() -> None:
    names = item_names(pegasus_boots=True)
    assert (names[Item.WOOD_BOOMERANG], names[Item.MAGICAL_BOOMERANG]) == ("Pegasus Boots", "Magical Boots")
    assert item_names() is ITEM_NAMES and ITEM_NAMES[Item.WOOD_BOOMERANG] == "Boomerang"
    boots = ItemNames(pegasus_boots=True)
    assert item_location_sentence(Item.WOOD_BOOMERANG, 3, boots) == "THE PEGASUS BOOTS WAIT IN LEVEL-3."
    assert item_location_sentence(Item.MAGICAL_BOOMERANG, 9, boots) == "THE MAGICAL BOOTS RACE IN LEVEL-9."
    assert boots.phrase(Item.MAGICAL_BOOMERANG) == "THE MAGICAL BOOTS"
    assert boots.label(Item.WOOD_BOOMERANG) == "PEGASUS BOOTS"
    assert ItemNames(progressive_items=True, pegasus_boots=True).phrase(Item.MAGICAL_BOOMERANG) == "A BOOTS UPGRADE"
    assert ItemNames().phrase(Item.MAGICAL_BOOMERANG) == "THE MAGICAL BOOMERANG"


def test_a_boots_seeds_document_and_log_name_the_boots() -> None:
    """Seed format 1.1 (z1r-visualizer aa1790c) names the boots: the document passes the 1.1 schema
    (ZORA's copy) with "Pegasus Boots" and "Magical Boots" in its item fields, and the spoiler log
    shows the boots. (tetraly/zora#9's workaround, the boomerangs' names, is undone.)"""
    import json

    from zora_export.seed_document import FORMAT_VERSION, seed_document_for
    from zora_export.spoiler_log import spoiler_log
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((REPO / "docs/seed-format/seed-format.schema.json").read_text())
    assert {"Pegasus Boots", "Magical Boots"} <= set(schema["$defs"]["itemName"]["anyOf"][0]["enum"])
    rom = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 3, vanilla(), zora_flag_string=BOOTS).rom
    document = seed_document_for(rom, MVP_BASELINE_LEVEL_ENCODING_OFF, 3, BOOTS)
    assert document["formatVersion"] == FORMAT_VERSION == "1.1"
    assert not list(jsonschema.Draft202012Validator(schema).iter_errors(document))
    text = repr(document)
    assert "'Pegasus Boots'" in text and "'Magical Boots'" in text
    assert "'Boomerang'" not in text and "'Magical Boomerang'" not in text
    item_lines = [line for line in spoiler_log(document).splitlines() if " ..." not in line]   # not the flags
    assert any("Pegasus Boots" in line for line in item_lines)
    assert not any("Boomerang" in line for line in item_lines)


# --- the spec's emulator cases ----------------------------------------------------------------

@pytest.mark.parametrize("release", pairs())
def test_1_l2_runs_at_once_and_4_release_walks(release: str) -> None:
    for name, rom in pair(release).items():
        emu = standing(rom, 1, 1)
        run = moved(emu, 24, B_RIGHT)
        if name == "patched":
            assert near(run, 55) and emu[OBJ_QSPEED] == L2_SPEED, (release, run)
        else:
            assert run < 33, (release, run)            # the boomerang throw pauses Link
        walk = moved(emu, 24, Button.RIGHT)
        assert near(walk, 32) and emu[OBJ_QSPEED] == WALK_SPEED, (release, name, walk)


@pytest.mark.parametrize("release", pairs())
def test_2_l1_winds_up_then_runs_and_3_whooshes_at_takeoff(release: str) -> None:
    """L1 stands still for 31 frames after a B press, at PRG0's speed with no input direction
    (never speed 0: the 2026-10-19 door freeze), then runs on the 32nd with one whoosh. The
    spec's whoosh every 8 frames became one at takeoff, to fit the routine's 57 bytes."""
    emu = standing(pair(release)["patched"], 1, 0)
    start, whooshes = emu[OBJ_X], []
    for frame in range(L1_CHARGE_FRAMES):
        emu.run(1, B_RIGHT)
        if emu[EFFECT_REQUEST] & BOOMERANG_EFFECT:
            whooshes.append(frame)
        if frame < L1_CHARGE_FRAMES - 1:
            assert (emu[OBJ_X], emu[OBJ_QSPEED], emu[OBJ_INPUT_DIR]) == (start, WALK_SPEED, 0), frame
    assert emu[OBJ_X] > start and emu[OBJ_QSPEED] == L1_SPEED and emu[BOOTS_CHARGE] == 0
    assert whooshes == [L1_CHARGE_FRAMES - 1]
    run = moved(emu, 24, B_RIGHT)
    assert near(run, 42) and emu[OBJ_QSPEED] == L1_SPEED, run


def test_5_a_b_press_restarts_the_wind_up() -> None:
    emu = standing(both("pegasus-boots")["patched"], 1, 0)
    emu.run(L1_CHARGE_FRAMES, B_RIGHT)
    emu.run(5)
    emu.run(1, Button.B)
    emu.run(2)
    assert emu[BOOTS_CHARGE] == L1_CHARGE_FRAMES
    assert moved(emu, L1_CHARGE_FRAMES - 1, B_RIGHT) == 0


@cache
def door_room(wall: WallType, side: Side) -> tuple[int, int]:
    """(level, room) of the first dungeon room of the control ROM with `wall` on `side`, into
    another room of its level."""
    for level in parse_rom(control()).levels:
        numbers = {room.room_num for room in level.rooms}
        for room in level.rooms:
            if room.walls[side] == wall and room.room_num + NEXT_ROOM_STEP[side] in numbers:
                return level.level_num, room.room_num
    raise AssertionError(f"no {wall.name} on the {side.name} side")


def l1_through_door(rom: bytes, wall: WallType, side: Side) -> tuple[int, list[int]]:
    """Walk through the door with L1 on B, pressing B as the walk through it begins: room entry
    calls InitLinkSpeed during the wind-up. Return the room play resumes in (within 600 frames)
    and Link's QSpeed on each frame between. ZORA writes no walk-through walls: those are an
    open door's wall rewritten in the loaded level. Shutters and bombable walls are opened in
    CurOpenedDoors."""
    level, room = door_room(WallType.OPEN_DOOR if wall in WALK_THROUGH else wall, side)
    game = Game(rom)
    game.enter_level(level)
    emu = game.emu
    if wall in WALK_THROUGH:
        address, shift = WALL_FIELDS[side]
        emu[address + room] = emu[address + room] & ~(WALL_BITS << shift) | wall << shift
    emu[ROOM_ID] = room
    game.start_mode(ENTER_ROOM_MODE)
    game.wait_for_play()
    emu.run(30)
    emu[INV_CLOCK] = 1                                              # the monsters stand still
    emu[CUR_OPENED_DOORS] |= DOOR_BITS[side]
    emu[INV_BOOMERANG], emu[INV_MAGIC_BOOMERANG], emu[SELECTED_ITEM_SLOT] = 1, 0, 0
    (emu[OBJ_X], emu[OBJ_Y]), button = DOOR_APPROACH[side]
    emu.run_until(lambda: emu.mode != Mode.PLAY, buttons=button, limit=300)
    speeds = []
    for _ in range(600):
        emu.run(1, button | Button.B)
        speeds.append(emu[OBJ_QSPEED])
        if emu.mode == Mode.PLAY:
            break
    return (emu[ROOM_ID] if emu.mode == Mode.PLAY else -1), speeds


WALK_THROUGH = (WallType.WALK_THROUGH_WALL_1, WallType.WALK_THROUGH_WALL_2)
DOOR_CASES = [(WallType.OPEN_DOOR, side) for side in Side] + [
    (WallType.LOCKED_DOOR_1, Side.NORTH), (WallType.SHUTTER_DOOR, Side.EAST),
    (WallType.BOMB_HOLE, Side.SOUTH), (WallType.WALK_THROUGH_WALL_1, Side.WEST),
    (WallType.WALK_THROUGH_WALL_2, Side.NORTH)]


@pytest.mark.parametrize("wall, side", DOOR_CASES, ids=lambda case: case.name)
def test_l1_wind_up_through_a_door_never_freezes(wall: WallType, side: Side) -> None:
    """The 2026-10-19 freeze: InitLinkSpeed's call on room entry during the L1 wind-up set speed
    0, and the walk through the door or doorway, which moves Link at that speed until he reaches
    the grid, never ended. Every door kind reaches the next room's play at a speed never 0."""
    level, room = door_room(WallType.OPEN_DOOR if wall in WALK_THROUGH else wall, side)
    reached, speeds = l1_through_door(both("pegasus-boots")["patched"], wall, side)
    assert reached == room + NEXT_ROOM_STEP[side], (level, hex(room), reached)
    assert 0 not in speeds and WALK_SPEED in speeds


def test_6_boots_not_on_b_and_7_no_b_items_walk() -> None:
    for name, rom in both("pegasus-boots").items():
        emu = standing(rom, 1, 1, slot=BOMBS_SLOT, bombs=8)
        assert moved(emu, 24, B_RIGHT) < 33 and emu[OBJ_QSPEED] == WALK_SPEED, name   # a bomb, never a run
        emu = standing(rom, 0, 0)
        assert near(moved(emu, 24, B_RIGHT), 32) and emu[SELECTED_ITEM_SLOT] == 0, name


def test_8_stairs_keep_their_slow_speed() -> None:
    """On the overworld's stair tiles both walk at $30: the control walking, the boots running."""
    for name, rom in both("pegasus-boots").items():
        emu = standing(rom, 1, 1)
        fill_play_area(emu, STAIRS_TILE)
        emu.run(8, Button.UP | (Button.B if name == "patched" else Button(0)))
        assert emu[OBJ_QSPEED] == STAIRS_SPEED, name


def test_9_the_run_carries_across_a_scroll() -> None:
    emu = standing(both("pegasus-boots")["patched"], 1, 1, x=0x60)
    fill_play_area(emu, GROUND_TILE)
    room = emu[ROOM_ID]
    emu.run_until(lambda: emu.mode != Mode.PLAY, buttons=B_RIGHT, limit=300)
    emu.run_until(lambda: emu.mode == Mode.PLAY, buttons=B_RIGHT, limit=300)
    emu.run(4, B_RIGHT)
    assert emu[ROOM_ID] == room + 1 and emu[OBJ_QSPEED] == L2_SPEED


def test_10_the_sword_stops_the_run_for_its_swing() -> None:
    emu = standing(both("pegasus-boots")["patched"], 1, 1)
    emu[ITEMS] = 1
    emu.run(10, B_RIGHT)
    emu.press(Button.A, after=0)
    swing = moved(emu, 8, B_RIGHT)
    assert swing == 0 and emu[OBJ_STATE]                        # the swing holds Link
    emu.run(10, B_RIGHT)
    assert moved(emu, 12, B_RIGHT) > 20 and emu[OBJ_QSPEED] == L2_SPEED


def test_11_bait_survives_the_boots() -> None:
    for name, rom in both("pegasus-boots").items():
        emu = standing(rom, 1, 1)
        emu[OBJ_STATE + BAIT_SLOT], emu[OBJ_TIMER + BAIT_SLOT] = BAIT_STATE, 0xFF
        emu.run(1, Button.B)
        emu.run(2)
        replaced = emu[OBJ_STATE + BAIT_SLOT] != BAIT_STATE
        assert replaced == (name == "control"), name           # PRG0 throws the boomerang over it


@pytest.mark.parametrize("release", pairs())
def test_12_the_icon(release: str) -> None:
    """The boot in the B box: L1 in the red palette (the designer's art, 2026-10-19), L2 in the
    blue one; the control's boomerangs in Link's and the blue one."""
    for name, rom in pair(release).items():
        for l2, palette in ((0, L1_BOOTS_PALETTE if name == "patched" else LINK_PALETTE), (1, BLUE_PALETTE)):
            emu = standing(rom, 1, l2)
            emu.run(5)
            assert b_item_sprite(emu) == ((BOOT_TILE if name == "patched" else BOOMERANG_TILE), palette), (name, l2)


def goriya_boomerangs(rom: bytes, magical: bool) -> set[tuple[int, int]]:
    """The flying boomerang sprites (tile, palette) seen in a red Goriyas' room over 600 frames."""
    game = Game(rom)
    enter_room(game, *rooms_holding(Enemy.RED_GORIYA)[0])
    emu = game.emu
    emu[INV_MAGIC_BOOMERANG] = int(magical)
    seen: set[tuple[int, int]] = set()
    for _ in range(600):
        emu.run(1)
        emu[0x66F] = 0xFF                                       # full hearts: Link lives
        oam = emu.sprites()
        seen |= {(oam[index + 1], oam[index + 2] & 0x03) for index in range(0, 256, 4)
                 if oam[index + 1] in GORIYA_BOOMERANG_TILES and B_ITEM_Y < oam[index] < 0xEF}
    return seen


def test_13_goriya_boomerangs_keep_their_look() -> None:
    """The flying boomerang's tiles, spin and spark as in PRG0, and its palette whether or not
    the L2 boots are owned (PRG0 turns every boomerang blue with the magical boomerang)."""
    control, patched = both("pegasus-boots").values()
    plain = goriya_boomerangs(control, False)
    assert {tile for tile, _ in plain} == GORIYA_BOOMERANG_TILES
    assert goriya_boomerangs(patched, False) == plain == goriya_boomerangs(patched, True)
    assert goriya_boomerangs(control, True) != plain


def attract_tiles(rom: bytes) -> bytes:
    """The nametables once the attract mode shows its item list."""
    emu = Emulator(rom)
    emu.run(2800)
    return emu.ciram()


def text(word: str) -> bytes:
    return bytes(0x24 if character == " " else ord(character) - 55 for character in word)


def test_14_the_attract_mode_lists_the_boots() -> None:
    control, patched = both("pegasus-boots").values()
    shown, vanilla = attract_tiles(patched), attract_tiles(control)
    assert text("BOOMERANG") in vanilla and text("BOOMERANG") not in shown
    assert text("  BOOTS  ") in shown and text("MAGICAL") in shown


def test_dungeon_priority_sprites_draw_a_blank_tile_not_the_boot() -> None:
    """The spec's open "pink splotch": PRG0's blank priority sprites at X 0 drew tiles $1C/$1D,
    the boot. They draw the background table's $50/$51, blank in every level."""
    for name, rom in both("pegasus-boots").items():
        for level in range(1, 10):
            game = Game(rom)
            game.enter_level(level)
            game.emu.run(30)
            oam = game.emu.sprites()
            tiles = {oam[4 * sprite + 1] for sprite in MASK_SPRITES}
            assert tiles == ({MASK_TILE} if name == "patched" else {BOOT_TILE}), (name, level)
            patterns = game.emu.pattern_tables()
            pair_start = BACKGROUND_TABLE + (MASK_TILE & ~1) * PATTERN_TILE_SIZE
            assert not any(patterns[pair_start:pair_start + 2 * PATTERN_TILE_SIZE]), level


def test_prg1s_output_calls_bootsspeed_where_prg1_moved_it() -> None:
    """InitLinkSpeed's JSR points at BootsSpeed's PRG1 address ($8E3E + 10), and BootsPressB
    sits at its moved offset (revision.MOVED_POINTERS, PRG1_MOVES)."""
    if not PRG1_ROM_PATH.exists():
        pytest.skip(f"{PRG1_ROM_PATH.name} is not beside the PRG0 base")
    prg0 = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, vanilla(), zora_flag_string=BOOTS).rom
    prg1 = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, PRG1_ROM_PATH.read_bytes(), zora_flag_string=BOOTS).rom
    call = slice(PEGASUS_BOOTS_SPEED_CALL - 1, PEGASUS_BOOTS_SPEED_CALL + 3)       # JSR BootsSpeed / NOP
    assert prg0[call] == bytes([JSR, *BOOTS_SPEED_PRG0.to_bytes(2, "little"), NOP])
    assert prg1[call] == bytes([JSR, *(BOOTS_SPEED_PRG0 + BANK_5_SHIFT).to_bytes(2, "little"), NOP])
    routines = slice(BOOTS_ROUTINES, BOOTS_ROUTINES + BOOTS_ROUTINES_LENGTH)
    moved = slice(prg1_offset(BOOTS_ROUTINES), prg1_offset(BOOTS_ROUTINES) + BOOTS_ROUTINES_LENGTH)
    assert prg1[moved] == prg0[routines]


def test_the_seed_code_names_its_boomerang_icon_as_the_game_draws_it() -> None:
    """Owner decision 2026-10-18: in a boots seed the code's $1D icon draws the boot, so the page, the
    bug report and the seed document name it Pegasus Boots; its value stays $1D, and other seeds keep
    "Wooden Boomerang"."""
    for name, rom in both("pegasus-boots").items():
        code = bytearray(rom)
        code[SEED_CODE_ADDRESS:SEED_CODE_ADDRESS + SEED_CODE_LENGTH] = bytes([0x1D, 0x00, 0x1D, 0x23])
        expected = "Pegasus Boots" if name == "patched" else "Wooden Boomerang"
        assert seed_code(bytes(code)) == (expected, "Bombs", expected, "Fairy"), name
        assert draws_boots(bytes(code)) == (name == "patched")
    for flags in ("", BOOTS):
        for seed in range(1, 40):
            rom = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, seed, vanilla(), zora_flag_string=flags).rom
            if 0x1D in seed_code_values(rom):
                break
        else:
            pytest.fail("no seed with the boomerang icon in its code")
        from zora_export.seed_document import seed_document_for
        named = seed_document_for(rom, MVP_BASELINE_LEVEL_ENCODING_OFF, seed, flags)["seed"]["code"]
        assert ("Pegasus Boots" in named) == bool(flags) and ("Boomerang" in named) != bool(flags), (flags, named)
        assert ("Pegasus Boots" in seed_code(rom)) == bool(flags)



def test_the_give_rules_report_the_boots() -> None:
    """Archipelago (owner decision 2026-10-18): give_rules carries pegasus_boots, which the world
    reads to name the boomerangs' items Pegasus Boots and Magical Boots (Boots Upgrade with
    Progressive Items); the give itself is the boomerangs' slots, unchanged, and the client tables
    carry it (an optional field) so they read back the same."""
    from zora import archipelago
    from zora.rom.base_rom import remember_repo_base_rom
    with_boots = archipelago.build_from_strings(MVP_BASELINE_LEVEL_ENCODING_OFF, BOOTS, 1, remember_repo_base_rom())
    without = archipelago.build_from_strings(MVP_BASELINE_LEVEL_ENCODING_OFF, "", 1, remember_repo_base_rom())
    assert archipelago.give_rules(with_boots).pegasus_boots and not archipelago.give_rules(without).pegasus_boots
    data = archipelago.client_tables_to_json(with_boots)
    assert archipelago.client_tables_from_json(data).rules == archipelago.give_rules(with_boots)
    plain = {**data, "rules": {key: value for key, value in data["rules"].items() if key != "pegasusBoots"}}
    assert not archipelago.client_tables_from_json(plain).rules.pegasus_boots
    ram = dict.fromkeys(range(0x0657, 0x0680), 0)
    for item in ("Boomerang", "Magical Boomerang"):
        assert archipelago.receive(item, ram, archipelago.give_rules(with_boots)) == \
            archipelago.receive(item, ram, archipelago.give_rules(without))
