"""The beta 9 export's in-play settings in the emulator, on the spec's Check strings (seed 1):

  - Killable Drop Items (B56; FP-KILL-01): a dropped rupee before Link's sword. Without B56 the sword
    fetches it; with B56 the swing destroys it (the world kill cycle advances, the room kill count
    does not, no rupee), and Link walking into one still takes it.
  - Hidden Numbers (B83; FP-NUM-01): the rupee, key and bomb counts show "X?", the key's with the
    Magical Key too, and the boss-sound label (FP-ROAR-01) still shows in level 9's boss-sound rooms
    (owner ruling: ZORA keeps it).
  - Rupees Affect Speed (B80; FP-RSPD-01): Link's quarter speed is $60 + rupees / 2, with Pegasus Boots
    (running keeps the faster speed) and under the Red Bubble Curse's slow speed (C19 = 2: $30 while
    cursed).
  - Prevent Clipping (B84; FP-CLIP-01): the room-to-room walk into level 9 ends at most a pixel from
    PRG0's end, and at most three with the rupee speed; walls stop Link where they do without it."""
from functools import cache

import pytest

from tests.emulator import CUR_LEVEL, GAME_MODE, GAME_SUBMODE, OBJ_TYPE, OBJ_X, OBJ_Y, ROOM_ID, Button, Emulator
from tests.test_beta8_patches import C19
from zora.flags import zora_flags
from zora.flags.codec import decode, encode
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import ZoraFlags
from zora.generate.pipeline import build, finish, plan
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora.rom.player_settings import DEFAULT_PLAYER_SETTINGS
from zora.rom.text_encoding import BYTE_TO_CHAR

pytestmark = pytest.mark.slow
CP5 = MVP_BASELINE_LEVEL_ENCODING_OFF
B56_ON = "1Ne1GBjkxlFBVfUfjWD8KCNkT9rUJ3A"
B83_ON = "2OtoMDzDUcPiuyIaUMyYrdLZaUfdEa9qUQUJ3A"
B80_ON, B80_SLOW = "5b4CUrbyqyQhfANcc3rTV0TsVe6grQ4jrUJ3A", "5b4CUrbyqyQhfANcc3rTV0TsVeLUxZ7!durnq"
B84_ON = "7BfP3fveBRa0Lb1hq1IPGWQblXUElwTPf!UJ3A"
BOOTS = zora_flags.encode(ZoraFlags(pegasus_boots=ThreeState.ON))
SEED = 1
# RAM (the pinned disassembly's labels)
OBJ_STATE, ITEM_LIFETIME, OBJ_UNINITIALIZED, OBJ_ATTR = 0xAC, 0x3A8, 0x492, 0x4BF
OBJ_HP, OBJ_INVINCIBILITY_MASK = 0x485, 0x4B2
ROOM_KILL_COUNT, WORLD_KILL_CYCLE = 0x34F, 0x52A
INV_SWORD, INV_RUPEES, INV_KEYS, INV_BOMBS, INV_MAGIC_KEY = 0x657, 0x66D, 0x66E, 0x658, 0x664
INV_BOOMERANG, INV_MAGIC_BOOMERANG, SELECTED_ITEM_SLOT, SWORD_BLOCKED = 0x674, 0x675, 0x656, 0x52E
LINK_QSPEED = 0x3BC
IS_UPDATING_MODE, LOAD_LEVEL_MODE, ENTER_ROOM_MODE, PLAY_MODE = 0x11, 0x02, 0x04, 0x05
DROPPED_ITEM, RUPEE, DROP_SLOT = 0x60, 0x18, 1
FRESH_DROP_FRAMES = 40             # FP-KILL-01 step 2: weapons test a drop once its lifetime is below $F0


@cache
def rom(flag_string: str, zora: str = "") -> bytes:
    base = remember_repo_base_rom()
    return finish(build(plan(flag_string, SEED, zora), base), base, player_settings=DEFAULT_PLAYER_SETTINGS)


def started(flag_string: str, zora: str = "") -> Emulator:
    emu = Emulator(rom(flag_string, zora))
    emu.new_game()
    return emu


# --- B56 ------------------------------------------------------------------------------------------

def drop_before_link(flag_string: str) -> Emulator:
    """A dropped rupee 18 pixels right of Link, facing it with the wooden sword, initialised by the
    game (B56's item initialisation included) and old enough for the weapon tests."""
    emu = started(flag_string)
    emu[INV_SWORD] = 1
    emu.run(8, Button.RIGHT)
    emu.run(10)
    emu[OBJ_TYPE + DROP_SLOT], emu[OBJ_UNINITIALIZED + DROP_SLOT], emu[OBJ_ATTR + DROP_SLOT] = DROPPED_ITEM, 0xFF, 0x81
    emu[OBJ_STATE + DROP_SLOT], emu[ITEM_LIFETIME + DROP_SLOT] = RUPEE, 0xFF
    emu[OBJ_X + DROP_SLOT], emu[OBJ_Y + DROP_SLOT] = emu[OBJ_X] + 18, emu[OBJ_Y]
    emu.run(FRESH_DROP_FRAMES)
    return emu


def swing(emu: Emulator) -> None:
    emu.run(10, Button.A)
    emu.run(50)


def test_without_b56_the_sword_fetches_a_drop() -> None:
    emu = drop_before_link(CP5)
    swing(emu)
    assert emu[OBJ_TYPE + DROP_SLOT] == 0 and emu[INV_RUPEES] == 1


def test_with_b56_the_sword_destroys_a_drop_without_counting_a_kill() -> None:
    emu = drop_before_link(B56_ON)
    assert (emu[OBJ_HP + DROP_SLOT], emu[OBJ_INVINCIBILITY_MASK + DROP_SLOT]) == (0, 0xC0)
    cycle = emu[WORLD_KILL_CYCLE]
    swing(emu)
    assert emu[INV_RUPEES] == 0
    assert (emu[OBJ_TYPE + DROP_SLOT], emu[OBJ_STATE + DROP_SLOT]) != (DROPPED_ITEM, RUPEE)
    assert emu[WORLD_KILL_CYCLE] == cycle + 1 and emu[ROOM_KILL_COUNT] == 0


def test_with_b56_link_still_takes_a_drop() -> None:
    emu = drop_before_link(B56_ON)
    emu.run(20, Button.RIGHT)
    assert emu[INV_RUPEES] == 1


# --- B83 ------------------------------------------------------------------------------------------

def text(tiles: bytes) -> str:
    return "".join(BYTE_TO_CHAR.get(tile, "~") for tile in tiles)


STATUS_BAR, STATUS_BAR_SIZE, ROW = 0x2000, 0x100, 32
COUNT_ROWS, COUNT_COLUMN = (3, 5, 6), 12          # rupees, keys, bombs: "X" and two digits
LABEL_ADDRESS, LABEL_TILES = 0x2076, 9


def counts(emu: Emulator) -> list[str]:
    bar = text(emu.nametable(STATUS_BAR, STATUS_BAR_SIZE))
    return [bar[row * ROW + COUNT_COLUMN:row * ROW + COUNT_COLUMN + 3] for row in COUNT_ROWS]


def in_a_boss_sound_room(flag_string: str) -> tuple[Emulator, str]:
    """Level 9 loaded with counts to show, then its first boss-sound room Link survives entering;
    the entrance's label."""
    rooms = [room.room_num for level in parse_rom(rom(flag_string)).levels if level.level_num == 9
             for room in level.rooms if room.boss_sound]
    for room in rooms:
        emu = started(flag_string)
        emu.run(30)
        emu[INV_RUPEES], emu[INV_KEYS], emu[INV_BOMBS] = 123, 5, 7
        emu[CUR_LEVEL], emu[GAME_MODE], emu[GAME_SUBMODE], emu[IS_UPDATING_MODE] = 9, LOAD_LEVEL_MODE, 0, 0
        emu.run(300)
        entrance = text(emu.nametable(LABEL_ADDRESS, LABEL_TILES))
        emu[ROOM_ID], emu[GAME_MODE], emu[GAME_SUBMODE], emu[IS_UPDATING_MODE] = room, ENTER_ROOM_MODE, 0, 0
        emu.run(200)
        if emu.mode == PLAY_MODE:
            return emu, entrance
    raise AssertionError("Link survives no boss-sound room of level 9")


@pytest.mark.parametrize(("flag_string", "shown"), [(CP5, ["123", "X5 ", "X7 "]), (B83_ON, ["X? "] * 3)])
def test_hidden_numbers_and_the_boss_sound_label(flag_string: str, shown: list[str]) -> None:
    emu, entrance = in_a_boss_sound_room(flag_string)
    assert counts(emu) == shown
    assert (entrance, text(emu.nametable(LABEL_ADDRESS, LABEL_TILES))) == (" -LIFE-  ", " -ROAR-  ")
    emu[INV_MAGIC_KEY] = 1
    emu.run(30)
    assert counts(emu)[1] == ("XA " if flag_string == CP5 else "X? ")


# --- B80 ------------------------------------------------------------------------------------------

def quarter_speed(flag_string: str, zora: str, rupees: int, running: bool = False, magical: bool = False,
                  cursed: bool = False) -> int:
    """Link's quarter speed after walking (or, with the boots on B, running) right for 40 frames."""
    emu = started(flag_string, zora)
    emu.run(20)
    emu[INV_RUPEES] = rupees
    if running:
        emu[INV_BOOMERANG], emu[SELECTED_ITEM_SLOT] = 1, 0
        emu[INV_MAGIC_BOOMERANG] = int(magical)
    emu[SWORD_BLOCKED] = int(cursed)
    emu.run(40, Button.LEFT | (Button.B if running else Button(0)))
    return emu[LINK_QSPEED]


CURSED = 0x30                                           # FP-BUBL-01


@pytest.mark.parametrize(("flag_string", "zora"), [(B80_ON, ""), (B80_ON, BOOTS), (B80_SLOW, ""), (B80_SLOW, BOOTS)],
                         ids=["alone", "boots", "slow speed", "slow speed and boots"])
@pytest.mark.parametrize("rupees", [0, 100, 254])
def test_rupee_speed_walking(flag_string: str, zora: str, rupees: int) -> None:
    assert quarter_speed(flag_string, zora, rupees) == 0x60 + rupees // 2
    if flag_string == B80_SLOW:
        assert quarter_speed(flag_string, zora, rupees, cursed=True) == CURSED


@pytest.mark.parametrize("flag_string", [B80_ON, B80_SLOW])
@pytest.mark.parametrize("magical", [False, True], ids=["L1 boots", "L2 boots"])
@pytest.mark.parametrize("rupees", [0, 254])
def test_running_keeps_the_faster_speed(flag_string: str, magical: bool, rupees: int) -> None:
    boots_speed = quarter_speed(CP5, BOOTS, rupees, running=True, magical=magical)
    assert boots_speed > 0x60
    assert quarter_speed(flag_string, BOOTS, rupees, running=True, magical=magical) == max(boots_speed,
                                                                                         0x60 + rupees // 2)


def test_without_b80_the_rupees_change_nothing() -> None:
    assert {quarter_speed(CP5, "", rupees) for rupees in (0, 254)} == {0x60}
    assert quarter_speed(C19[2], "", 254, cursed=True) == CURSED


# --- B84 ------------------------------------------------------------------------------------------

def walk_into_level_9(flag_string: str, rupees: int = 0) -> int:
    """Link's Y when play resumes after walking up out of level 9's first room."""
    emu = started(flag_string)
    emu.run(30)
    emu[INV_RUPEES] = rupees
    emu[CUR_LEVEL], emu[GAME_MODE], emu[GAME_SUBMODE], emu[IS_UPDATING_MODE] = 9, LOAD_LEVEL_MODE, 0, 0
    emu.run(300)
    left_play = False
    for _ in range(500):
        emu.run(1, Button.UP)
        left_play = left_play or emu.mode != PLAY_MODE
        if left_play and emu.mode == PLAY_MODE:
            return emu[OBJ_Y]
    raise AssertionError("Link never left the room")


def with_rupee_speed(flag_string: str) -> str:
    return encode(decode(flag_string).updated(toggles={"B80": ThreeState.ON}))


def test_prevent_clipping_ends_the_room_walk_near_prg0s_end() -> None:
    assert abs(walk_into_level_9(B84_ON) - walk_into_level_9(CP5)) <= 1
    assert abs(walk_into_level_9(with_rupee_speed(B84_ON), 254) - walk_into_level_9(with_rupee_speed(CP5), 254)) <= 3


@pytest.mark.parametrize("direction", [Button.LEFT, Button.RIGHT])
def test_prevent_clipping_stops_link_at_walls_where_prg0_does(direction: Button) -> None:
    ends = []
    for flag_string in (CP5, B84_ON):
        emu = started(flag_string)
        emu.run(20)
        emu.run(400, direction)
        ends.append((emu.mode, emu[OBJ_X], emu[OBJ_Y]))
    assert ends[0] == ends[1]
