"""The ZORA 2.0 flag patches of asm/flags2/ (docs/design/zora-flags-2.0.md) in the emulator.

The patches are not wired into the serializer. The control ROM is ZORA's output for the MVP
baseline (level encoding off, seed 1); each test ROM is that output with one patch written
over it by asm/flags2/build.py. Every test runs the same steps on both and checks the patch's
effect against the control. Link is moved and rooms entered as in
tests/test_progressive_emulator.py (its Game: the leave-cave, enter-cave, level-load and
enter-room modes), with monsters frozen by the clock where they would get in the way.

Not observed here: the raft and bracelet screen edits (their effect is reaching places with
the raft or the bracelet, which the generator's logic will decide), a fourth sword's stab
(PRG0's code, unchanged) and its palette (owner: kept as it is), drinking from four potions,
and the Lost Hills and Dead Woods edits around the mazes (the walks below cross the maze
screens themselves)."""
import importlib.util
from functools import cache
from itertools import product
from pathlib import Path
from types import ModuleType

import pytest

from tests.emulator import (
    FACE_FRAMES,
    INV_RECORDER,
    ITEMS,
    OBJ_TYPE,
    OBJ_X,
    OBJ_Y,
    RECORDER_SLOT,
    ROOM_ID,
    SELECTED_ITEM_SLOT,
    Button,
    Emulator,
    Mode,
)
from tests.test_progressive_emulator import (
    BLUE_POTION,
    ENTER_ROOM_MODE,
    INV_BOOMERANG,
    INV_LETTER,
    INV_MAGIC_BOOMERANG,
    INV_RUPEES,
    IS_UPDATING_MODE,
    LETTER_DELIVERED,
    POTION,
    RED_POTION,
    COAST_SCREEN,
    Game,
    cave_type,
    finished,
)
from tests.test_progressive_emulator import build as progressive_build
from tests.test_feature_patches import vanilla
from zora.flags.codec import decode, encode
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.model.enums import Destination, Enemy, Side, WallType
from zora.rom.parse.rom_file import parse_rom

REPO = Path(__file__).resolve().parent.parent


def _module(name: str, path: Path) -> ModuleType:
    if not path.exists():
        # asm/ is left out of some trees: what needs it skips there.
        pytest.skip(f"{path.relative_to(REPO)} is not in this tree", allow_module_level=True)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = _module("flags2_build", REPO / "asm" / "flags2" / "build.py")
PATCHES = build.load_data().PATCHES

# CPU RAM and work RAM (the pinned disassembly's src/Variables.inc)
FLUTE_TIMER = 0x3C
WORLD_IS_FILLING_HEARTS = 0x63
OBJ_HP = 0x485
USED_FLUTE = 0x51B
MAZE_STEP = 0x52F
INV_CLOCK = 0x66C
HEART_VALUES = 0x66F                 # high nibble: heart containers - 1; low: full hearts - 1
HEART_PARTIAL = 0x670
INV_MAGIC_SHIELD = 0x676
MONSTER_SLOTS = range(1, 12)

FULL_HEARTS = 0xFF                   # 16 heart containers, all full
NO_ITEM_WARE = 0x3F


def control() -> bytes:
    return bytes(finished())


@cache
def patched(name: str) -> bytes:
    return bytes(build.apply_patches(control(), [name], PATCHES))


def both(name: str) -> dict[str, bytes]:
    return {"control": control(), "patched": patched(name)}


def monster_types(emu: Emulator) -> list[int]:
    return [emu[OBJ_TYPE + slot] for slot in MONSTER_SLOTS]


@cache
def rooms_holding(enemy: Enemy) -> list[tuple[int, int]]:
    """(level, room) of each dungeon room of the control ROM whose monster is `enemy`."""
    world = parse_rom(control())
    return [(level.level_num, room.room_num) for level in world.levels for room in level.rooms
            if room.enemy == enemy]


def enter_room(game: Game, level: int, room: int) -> None:
    """Load `level` and enter `room` (the enter-room mode), monsters and all."""
    game.enter_level(level)
    game.emu[ROOM_ID] = room
    game.start_mode(ENTER_ROOM_MODE)
    game.wait_for_play()
    game.emu.run(30)


def play_recorder(emu: Emulator) -> None:
    """Play the recorder where Link stands and run until its tune has ended."""
    emu[INV_RECORDER] = 1
    emu[SELECTED_ITEM_SLOT] = RECORDER_SLOT
    emu.run(FACE_FRAMES, Button.UP)
    emu.run(5)
    emu.press(Button.B)
    emu.run_until(lambda: emu[FLUTE_TIMER] == 0, limit=400)


# --- 2: Add L4 Sword ----------------------------------------------------------------------

STRUCK_HP = 0xF0                     # the struck monster's HP before the hit
BOOMERANG_SLOT = 0                   # SelectedItemSlot of the boomerangs


def hp_after_hit(rom: bytes, weapon: Button, sword: int = 3, magical_boomerang: bool = False) -> int:
    """In a Stalfos room, frozen by the clock and with full hearts (so the sword shoots), hold
    the first monster above Link at STRUCK_HP, attack upward with `weapon` (A: the sword, B:
    the boomerang) and return the monster's lowest HP over the next second."""
    game = Game(rom)
    enter_room(game, *rooms_holding(Enemy.STALFOS)[0])
    emu = game.emu
    emu[INV_CLOCK] = 1
    emu[HEART_VALUES], emu[HEART_PARTIAL] = FULL_HEARTS, 0xFF
    emu[ITEMS] = sword
    emu[INV_BOOMERANG], emu[INV_MAGIC_BOOMERANG] = 1, int(magical_boomerang)
    emu[SELECTED_ITEM_SLOT] = BOOMERANG_SLOT
    slot = next(slot for slot in MONSTER_SLOTS if emu[OBJ_TYPE + slot])
    emu.run(10, Button.UP)
    x, target_y = emu[OBJ_X] & 0xF8, 0x5D
    emu[OBJ_X] = x
    emu[OBJ_HP + slot] = STRUCK_HP
    emu.run(2, Button.UP)
    emu.run(4)
    emu.press(weapon, after=0)
    lowest = STRUCK_HP
    for _ in range(60):
        emu[OBJ_X + slot], emu[OBJ_Y + slot] = x, target_y
        emu.run(1)
        lowest = min(lowest, emu[OBJ_HP + slot])
    return lowest


@pytest.mark.parametrize(("sword", "control_damage", "patched_damage"), [
    (1, 0x10, 0x10),                 # the wooden sword: as in PRG0
    (3, 0x40, 0x40),                 # the magical sword: as in PRG0
    (4, 0x10, 0x40),                 # a fourth sword: the wooden sword's damage in PRG0
])
def test_a_fourth_swords_beam_does_the_magical_swords_damage(sword: int, control_damage: int,
                                                               patched_damage: int) -> None:
    for name, rom in both("l4-sword-beam").items():
        damage = STRUCK_HP - hp_after_hit(rom, Button.A, sword=sword)
        assert damage == (patched_damage if name == "patched" else control_damage), (name, sword)


# --- 11: Magical Boomerang Does 1 HP Damage ------------------------------------------------

@pytest.mark.parametrize("magical", [False, True])
def test_the_magical_boomerang_does_one_hp_of_damage(magical: bool) -> None:
    """The magical boomerang takes $10 (the wooden sword's damage) off a monster it stuns; the
    wooden boomerang, and either in PRG0, takes none."""
    for name, rom in both("magic-boomerang-damage").items():
        damage = STRUCK_HP - hp_after_hit(rom, Button.B, magical_boomerang=magical)
        assert damage == (0x10 if name == "patched" and magical else 0), (name, magical)


# --- 5: Speed Up Dungeon Transitions ---------------------------------------------------------

# Where Link starts, next to a door, and the button that walks him through it.
DOOR_APPROACH = {Side.NORTH: ((0x78, 0x45), Button.UP), Side.EAST: ((0xC8, 0x8D), Button.RIGHT)}


@cache
def room_with_open_door(side: Side) -> tuple[int, int]:
    """A level-1 room of the control ROM with an open door on `side` into another room."""
    world = parse_rom(control())
    level = next(level for level in world.levels if level.level_num == 1)
    numbers = {room.room_num for room in level.rooms}
    step = {Side.NORTH: -0x10, Side.EAST: 1}[side]
    return 1, next(room.room_num for room in level.rooms
                   if room.walls[side] == WallType.OPEN_DOOR and room.room_num + step in numbers)


def scroll_through_door(rom: bytes, side: Side) -> tuple[int, int, bytes]:
    """Walk through the door; return the room reached, the frames from leaving play until play
    resumes there, and the nametable RAM once it has settled."""
    game = Game(rom)
    enter_room(game, *room_with_open_door(side))
    emu = game.emu
    emu[INV_CLOCK] = 1
    (emu[OBJ_X], emu[OBJ_Y]), button = DOOR_APPROACH[side]
    emu.run_until(lambda: emu.mode != Mode.PLAY, buttons=button, limit=600)
    start = emu.frames
    emu.run_until(lambda: emu.mode == Mode.PLAY, limit=600)
    taken = emu.frames - start
    emu.run(40)
    return emu[ROOM_ID], taken, emu.ciram()


@pytest.mark.parametrize("side", [Side.NORTH, Side.EAST])
def test_dungeon_rooms_scroll_faster(side: Side) -> None:
    """A vertical and a horizontal room change take fewer frames (the overworld's timings), and
    end in the same room with the same nametables as in the control."""
    room, control_frames, control_tiles = scroll_through_door(control(), side)
    patched_room, patched_frames, patched_tiles = scroll_through_door(patched("fast-dungeon-scroll"), side)
    assert patched_room == room
    assert patched_frames < control_frames * 3 // 4, (patched_frames, control_frames)
    assert patched_tiles == control_tiles


# --- 6: Speed Up Heart Fill ----------------------------------------------------------------------

def fill_hearts(rom: bytes) -> tuple[int, int, int, bool]:
    """From 1 heart of 8, start a heart fill (as a fairy or a potion does); return the frames
    it takes, the heart values and partial heart at the end, and whether the hearts ever
    exceeded the containers."""
    emu = Emulator(rom)
    emu.new_game()
    emu[HEART_VALUES], emu[HEART_PARTIAL] = 0x70, 0x00
    emu[WORLD_IS_FILLING_HEARTS] = 1
    frames, exceeded = 0, False
    while emu[WORLD_IS_FILLING_HEARTS]:
        emu.run(1)
        frames += 1
        assert frames < 2000
        exceeded |= (emu[HEART_VALUES] & 0x0F) > emu[HEART_VALUES] >> 4
    return frames, emu[HEART_VALUES], emu[HEART_PARTIAL], exceeded


def test_hearts_fill_four_times_as_fast_and_stop_at_full() -> None:
    control_frames, *control_end = fill_hearts(control())
    patched_frames, *patched_end = fill_hearts(patched("fast-heart-fill"))
    assert control_end == patched_end == [0x77, 0xFF, False]       # 8 of 8, the last heart full
    assert 3.5 < control_frames / patched_frames < 4.5, (control_frames, patched_frames)


# --- 7: Recorder Kills Dungeon Pols Voice --------------------------------------------------------

def test_the_recorder_kills_every_pols_voice_in_the_room() -> None:
    """In a Pols Voice room, the Pols Voices are all gone once the recorder's tune ends; in the
    control they all stay."""
    for name, rom in both("recorder-pols-voice").items():
        game = Game(rom)
        enter_room(game, *rooms_holding(Enemy.POLS_VOICE)[0])
        before = monster_types(game.emu)
        assert before.count(Enemy.POLS_VOICE) >= 2
        play_recorder(game.emu)
        game.emu.run(60)
        after = monster_types(game.emu)
        assert after.count(Enemy.POLS_VOICE) == (0 if name == "patched" else before.count(Enemy.POLS_VOICE)), name


def test_the_recorder_only_counts_in_its_own_room() -> None:
    """Played in another room of the level, the recorder leaves the Pols Voices of the next room
    alive: the game clears UsedFlute when a room is entered."""
    game = Game(patched("recorder-pols-voice"))
    level, room = rooms_holding(Enemy.POLS_VOICE)[0]
    game.enter_level(level)
    play_recorder(game.emu)
    assert game.emu[USED_FLUTE]
    game.emu[ROOM_ID] = room
    game.start_mode(ENTER_ROOM_MODE)
    game.wait_for_play()
    game.emu.run(90)
    assert game.emu[USED_FLUTE] == 0
    assert monster_types(game.emu).count(Enemy.POLS_VOICE) >= 2


def test_the_recorder_on_the_overworld_is_unchanged() -> None:
    """On the overworld the recorder summons the whirlwind and sets Link down where the control
    does."""
    landed = {}
    for name, rom in both("recorder-pols-voice").items():
        emu = Emulator(rom)
        emu.new_game()
        emu.play_recorder(0x01)
        landed[name] = (emu[ROOM_ID], emu[OBJ_X], emu[OBJ_Y])
    assert landed["patched"] == landed["control"]


# --- 8: Four Potion Inventory, 9: Auto Show Letter ------------------------------------------------

@cache
def potion_shop_rom(rom: bytes) -> bytes:
    for position, item in enumerate((BLUE_POTION, RED_POTION, NO_ITEM_WARE)):
        rom = progressive_build.with_ware(rom, cave_type(Destination.POTION_SHOP), position, item, 1)
    return bytes(rom)


def potions_after_buying(rom: bytes, held: int, item: int) -> int:
    game = Game(potion_shop_rom(rom))
    game.emu[POTION] = held
    game.emu[INV_LETTER] = LETTER_DELIVERED
    game.enter_cave(Destination.POTION_SHOP)
    game.take_ware(0 if item == BLUE_POTION else 1)
    return game.emu[POTION]


@pytest.mark.parametrize(("held", "control_after", "patched_after"), [
    (1, 2, 2), (2, 2, 3), (3, 2, 4), (4, 2, 4),
])
def test_blue_potions_stack_up_to_four(held: int, control_after: int, patched_after: int) -> None:
    """Buying a blue potion adds one, capped at 4 (PRG0: 2)."""
    for name, rom in both("four-potions").items():
        expected = patched_after if name == "patched" else control_after
        assert potions_after_buying(rom, held, BLUE_POTION) == expected, (name, held)


@pytest.mark.parametrize("letter", [0, 1])
def test_the_potion_shop_takes_a_held_letter_at_once(letter: int) -> None:
    """Walking into the potion shop holding the letter (1) shows it at once (2) without
    selecting it; without the letter nothing changes; in the control the letter waits for B."""
    for name, rom in both("auto-show-letter").items():
        game = Game(potion_shop_rom(rom))
        game.emu[INV_LETTER] = letter
        game.enter_cave(Destination.POTION_SHOP)
        game.emu.run(120)
        shown = letter == 1 and name == "patched"
        assert game.emu[INV_LETTER] == (LETTER_DELIVERED if shown else letter), (name, letter)


# --- 10: Like-Like Eats Rupees ------------------------------------------------------------------

def test_a_like_like_eats_rupees_not_the_shield() -> None:
    """Held by a Like-Like past its $60 frames, Link keeps the magical shield and loses rupees
    (one a frame while held); in the control he loses the shield and keeps the rupees."""
    for name, rom in both("like-like-rupees").items():
        game = Game(rom)
        enter_room(game, *rooms_holding(Enemy.LIKE_LIKE)[0])
        emu = game.emu
        emu[INV_MAGIC_SHIELD], emu[INV_RUPEES] = 1, 50
        slot = next(slot for slot in MONSTER_SLOTS if emu[OBJ_TYPE + slot] == Enemy.LIKE_LIKE)
        for frame in range(420):
            emu[HEART_VALUES] = FULL_HEARTS
            if frame < 20:
                emu[OBJ_X], emu[OBJ_Y] = emu[OBJ_X + slot], emu[OBJ_Y + slot]
            emu.run(1)
        if name == "patched":
            assert (emu[INV_MAGIC_SHIELD], emu[INV_RUPEES]) == (1, 0)
        else:
            assert (emu[INV_MAGIC_SHIELD], emu[INV_RUPEES]) == (0, 50)


# --- 12-13: Randomize Lost Hills / Randomize Dead Woods ---------------------------------------------

UP, DOWN, LEFT, RIGHT = Button.UP, Button.DOWN, Button.LEFT, Button.RIGHT
MAZE_DIRECTIONS = {Button.UP: 0x08, Button.DOWN: 0x04, Button.LEFT: 0x02, Button.RIGHT: 0x01}


class Maze:
    """A maze screen, where its sequence's four direction bytes are, the directions of steps
    1-3 and the fixed step 4 (the document's sequence rules), where Link starts each step
    (next to the edge he leaves by; the maze screen's own squares are PRG0's), and the screen
    the last step leads to."""

    def __init__(self, screen: int, directions: int, steps: tuple[Button, ...], last: Button,
                 starts: dict[Button, tuple[int, int]], beyond: int) -> None:
        self.screen, self.directions, self.steps, self.last = screen, directions, steps, last
        self.starts, self.beyond = starts, beyond

    def sequences(self) -> list[tuple[Button, ...]]:
        return [(*steps, self.last) for steps in product(self.steps, repeat=3)]


MAZES = {
    # The mountain maze (MountainMazeDirs, 0x6DAB): steps from up, down, right; last up, to $0B.
    "lost-hills": Maze(0x1B, 0x6DAB, (UP, DOWN, RIGHT), UP,
                       {UP: (0x70, 0x5D), DOWN: (0x70, 0xBD), RIGHT: (0xD0, 0x8D)}, 0x0B),
    # The forest maze (ForestMazeDirs, 0x6DA7): steps from north, west, south; last south, to $71.
    "dead-woods": Maze(0x61, 0x6DA7, (UP, LEFT, DOWN), DOWN,
                       {UP: (0xA0, 0x8D), LEFT: (0xA0, 0x8D), DOWN: (0xA0, 0x8D)}, 0x71),
}


def on_maze_screen(name: str, sequence: tuple[Button, ...]) -> Emulator:
    """A new game standing on the maze screen, with `sequence` written as the maze's direction
    bytes. Each walk boots its own ROM: CheckMazes reads the bytes from bank 1's copy in work
    RAM, made at boot, so a state saved under other bytes would keep those."""
    maze = MAZES[name]
    rom = bytearray(patched(name))
    rom[maze.directions:maze.directions + 4] = bytes(MAZE_DIRECTIONS[step] for step in sequence)
    game = Game(bytes(rom))
    game.go_to_screen(maze.screen)
    return game.emu


def take_step(emu: Emulator, maze: Maze, step: Button) -> int:
    """Walk off the maze screen by `step`'s edge; return the screen Link comes in on."""
    emu[INV_CLOCK] = 1
    emu[HEART_VALUES] = FULL_HEARTS
    emu[OBJ_X], emu[OBJ_Y] = maze.starts[step]
    emu.run_until(lambda: emu.mode != Mode.PLAY, buttons=step, limit=300)
    emu.run_until(lambda: emu.mode == Mode.PLAY and emu[IS_UPDATING_MODE] == 1, limit=600)
    emu.run(5)
    return emu[ROOM_ID]


def walk(name: str, sequence: tuple[Button, ...]) -> list[int]:
    """Take the sequence's four steps from the maze screen; return the screen after each."""
    emu = on_maze_screen(name, sequence)
    return [take_step(emu, MAZES[name], step) for step in sequence]


@pytest.mark.slow                    # 27 emulator walks; test_a_wrong_step_starts_the_maze_over runs by default
@pytest.mark.parametrize("first", [0, 1, 2])
@pytest.mark.parametrize("name", list(MAZES))
def test_every_maze_sequence_can_be_walked(name: str, first: int) -> None:
    """Each of the 27 sequences the document allows (split by the first step, for parallel
    runs): the first three steps bring Link back to the maze screen and the fourth takes him
    to the screen beyond it."""
    maze = MAZES[name]
    for sequence in maze.sequences():
        if sequence[0] == maze.steps[first]:
            assert walk(name, sequence) == [maze.screen] * 3 + [maze.beyond], (name, sequence)


def test_a_wrong_step_starts_the_maze_over() -> None:
    """A step outside the sequence resets the maze (MazeStep 0) and repeats the screen, as in
    PRG0."""
    maze = MAZES["lost-hills"]
    sequence = (DOWN, DOWN, DOWN, UP)
    emu = on_maze_screen("lost-hills", sequence)
    assert take_step(emu, maze, DOWN) == maze.screen and emu[MAZE_STEP] == 1
    assert take_step(emu, maze, UP) == maze.screen and emu[MAZE_STEP] == 0


# --- 2: Add L4 Sword, the take (docs/design/l4-sword.md T1-T5) -----------------------------------

PROGRESSIVE_ITEMS = "2.O"            # a ZORA flag string with Progressive Items on
WOODEN_SWORD_ITEM, MAGICAL_SWORD_ITEM, BOMBS_ITEM, FOOD_ITEM = 0x01, 0x03, 0x00, 0x04


@cache
def progressive_control() -> bytes:
    """ZORA's output with Progressive Items on (Extra Candles off: Progressive Items refuses
    it), which the flag needs: a sword room item shows at Link's next level."""
    flags = encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(toggles={"B09": ThreeState.OFF}))
    return bytes(generate_rom(flags, 1, vanilla(), zora_flag_string=PROGRESSIVE_ITEMS).rom)


@cache
def l4_roms() -> dict[str, bytes]:
    """The control and the control with both Add L4 Sword patches, as the serializer will
    write them (R17)."""
    control_rom = progressive_control()
    return {"control": control_rom,
            "patched": bytes(build.apply_patches(control_rom, ["l4-sword-beam", "l4-sword-take"], PATCHES))}


def sword_after_room_item(rom: bytes, sword: int, item: int) -> tuple[int, int]:
    """Stand in level 9's entrance room with `item` as its room item and `sword` held; return
    the item shown and the sword level after taking it."""
    game = Game(rom)
    game.emu[ITEMS] = sword
    game.enter_level(9)
    game.reload_room_with_item(item)
    shown = game.room_item()[0]
    game.take_room_item()
    return shown, game.emu[ITEMS]


@pytest.mark.parametrize(("sword", "item", "control_after", "patched_after"), [
    (3, WOODEN_SWORD_ITEM, 3, 4),    # T1: the level-4 sword, shown as the magical sword
    (0, WOODEN_SWORD_ITEM, 1, 1),    # T2: taken early, the next sword
    (1, WOODEN_SWORD_ITEM, 2, 2),
    (2, WOODEN_SWORD_ITEM, 3, 3),
    (0, BOMBS_ITEM, 0, 0),           # T3: bombs leave the sword alone
    (3, FOOD_ITEM, 3, 3),            # another item at level 3
])
def test_a_room_sword_taken_at_level_3_gives_level_4(sword: int, item: int, control_after: int,
                                                       patched_after: int) -> None:
    for name, rom in l4_roms().items():
        shown, after = sword_after_room_item(rom, sword, item)
        assert after == (patched_after if name == "patched" else control_after), (name, sword, item)
        if item == WOODEN_SWORD_ITEM and sword == 3:
            assert shown == MAGICAL_SWORD_ITEM, name


def test_the_coast_item_is_taken_as_before() -> None:
    """T4: the overworld's room-item take (the coast item) gives what it gives in the control,
    also at sword level 3: the hook leaves the overworld alone."""
    results = {}
    for name, rom in l4_roms().items():
        game = Game(progressive_build.with_coast_item(rom, WOODEN_SWORD_ITEM))
        game.emu[ITEMS] = 3
        game.go_to_screen(COAST_SCREEN)
        shown = game.room_item()[0]
        game.take_room_item()
        results[name] = (shown, game.emu[ITEMS], game.emu[ROOM_ID])
    assert results["patched"] == results["control"] == (MAGICAL_SWORD_ITEM, 3, COAST_SCREEN)


def test_level_4_survives_the_menus_and_a_save() -> None:
    """T5: with sword level 4 the item screen opens and closes, and the level is kept through a
    save, the console's reset and reloading the file. (The beam at level 4:
    test_a_fourth_swords_beam_does_the_magical_swords_damage.)"""
    game = Game(l4_roms()["patched"])
    game.emu[ITEMS] = 4
    game.emu.run(30)
    game.emu.open_item_screen()
    game.emu.close_item_screen()
    assert game.emu.mode == Mode.PLAY and game.emu[ITEMS] == 4
    game.emu.open_item_screen()
    game.emu.save_and_reload()
    assert game.emu[ITEMS] == 4
