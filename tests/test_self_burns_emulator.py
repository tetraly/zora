"""The statistics screen's self-burns counter (FP-STATS-01, asm/fp-stats-01/bank_00.s `SelfBurns`
and `CapSelfBurns`; the count itself is the INC in UpdateFire's damage call, bank 7, hook "self-burn")
in the emulator, slow.

Link's own flame is the object UpdateFire runs in slots $10 and $11: the candle's (WieldCandle) and
the wand's with the Book (HandleShotBlocked calls WieldCandle for the shot that hit a wall). When it
touches Link and he is not invincible, UpdateFire shoves him and harms him $80 (half a heart) through
Link_BeHarmed; the hook counts there. The cave fires (type $40) and the enemies' fireballs (type $55,
shot by ShootFireball) are other objects and never reach that code. The statue-room fireballs here
come from PersonFireballsEnabled, which the statues also take.

The hook is the same bytes in every statistics choice (MMC1, music, lozft2): the data test checks
them in each.
"""
import pytest

from tests.emulator import (
    INV_BOOK,
    ITEMS,
    OBJ_STATE,
    OBJ_TYPE,
    OBJ_X,
    OBJ_Y,
    SELECTED_ITEM_SLOT,
    Button,
    Emulator,
)
from tests.test_bait_in_pool import Console
from tests.test_stats_screen import (
    FLAGS,
    HEART_VALUES,
    ROMS,
    SELF_BURNS,
    SELF_BURNS_HIGH,
    STATS_BLOCK,
    playing,
)
from zora.rom import base_rom
from zora.rom.base_rom import original_bytes, piece_bytes
from zora.rom.player_settings_data import SETTINGS

pytestmark = pytest.mark.slow

HEART_PARTIAL = 0x670
FULL_HEARTS = 0xFF                     # HeartValues: 16 containers, all full
CANDLE, WAND = 4, 8                    # item slots (Items + slot)
CANDLE_SELECTION, WAND_SELECTION = 3, 7        # SelectedItemSlot values
FIRE_SLOTS = (0x10, 0x11)
STANDING_FIRE = 0x22                   # ObjState of a fire that stands (walking: $21)
WALK_FRAMES = 70                       # long enough to reach a fire 30 pixels away and be burned
HALF_HEART = 0x80                      # what UpdateFire harms Link
CAVE_SCREEN = 0x77                     # the first quest's sword cave, the old man and two fires
CAVE_FIRE_TYPE = 0x40
FIREBALL_TYPE = 0x55
LEVEL_1_START_ROOM = 0x73
PERSON_FIREBALLS_ENABLED = 0x4CC
SELF_BURNS_ADDRESS = STATS_BLOCK + SELF_BURNS
FLAGS_ADDRESS = STATS_BLOCK + FLAGS
DEAD = 0x11                            # the death mode


def burns(emu: Emulator) -> int:
    return emu[SELF_BURNS_ADDRESS]


def partial_heart(emu: Emulator) -> int:
    return emu[HEART_PARTIAL]


def fire_stands(emu: Emulator) -> bool:
    return any(emu[OBJ_STATE + slot] == STANDING_FIRE for slot in FIRE_SLOTS)


def face_up(emu: Emulator) -> None:
    emu.run(8, Button.UP)
    emu.run(5)


def walk_up_until_burned(emu: Emulator) -> None:
    """Hold Up toward the flame standing above Link until the count rises, then let go and wait out
    the shove."""
    before = burns(emu)
    emu.run_until(lambda: burns(emu) != before, limit=WALK_FRAMES, buttons=Button.UP)
    emu.run(30)


def after_the_flame_is_lit(name: str, item_slot: int, selection: int, *, book: bool = False) -> Emulator:
    emu = playing(name)
    emu[HEART_VALUES] = FULL_HEARTS
    emu[ITEMS + item_slot] = 1
    emu[INV_BOOK] = int(book)
    emu[SELECTED_ITEM_SLOT] = selection
    face_up(emu)
    emu.press(Button.B, after=0)
    emu.run_until(lambda: fire_stands(emu), limit=120)
    return emu


@pytest.mark.parametrize("name", ROMS)
def test_the_candles_flame_counts_one_hit(name: str) -> None:
    emu = after_the_flame_is_lit(name, CANDLE, CANDLE_SELECTION)
    assert burns(emu) == 0 and partial_heart(emu) == 0xFF
    walk_up_until_burned(emu)
    assert burns(emu) == 1
    assert partial_heart(emu) == 0xFF - HALF_HEART        # one half heart, whatever the frames in the flame
    emu.run(120)                                       # the flame burns out; Link stands clear
    assert burns(emu) == 1


@pytest.mark.parametrize("name", ROMS)
def test_the_wands_flame_with_the_book_counts_one_hit(name: str) -> None:
    emu = after_the_flame_is_lit(name, WAND, WAND_SELECTION, book=True)
    assert burns(emu) == 0
    walk_up_until_burned(emu)
    assert burns(emu) == 1
    emu.run(120)
    assert burns(emu) == 1


@pytest.mark.parametrize("name", ROMS)
def test_each_hit_counts_once_but_every_hit_counts(name: str) -> None:
    """Link is invincible for a few frames after a hit, so standing in the flame hurts him again
    when that ends: the count is hits, not frames."""
    emu = after_the_flame_is_lit(name, CANDLE, CANDLE_SELECTION)
    emu.run_until(lambda: burns(emu) == 1, limit=WALK_FRAMES, buttons=Button.UP)
    emu.run(2)
    assert burns(emu) == 1
    emu.run_until(lambda: burns(emu) == 2, limit=300, buttons=Button.UP)
    assert burns(emu) == 2


@pytest.mark.parametrize("name", ROMS)
def test_a_hit_that_kills_counts(name: str) -> None:
    emu = after_the_flame_is_lit(name, CANDLE, CANDLE_SELECTION)
    emu[HEART_VALUES] = 0x10                            # two containers, none full
    emu[HEART_PARTIAL] = 0x40                           # a quarter of a heart
    emu.run_until(lambda: burns(emu) == 1, limit=WALK_FRAMES, buttons=Button.UP)
    emu.run(5)
    assert burns(emu) == 1 and emu.mode == DEAD


@pytest.mark.parametrize("name", ROMS)
def test_touching_a_cave_fire_does_not_count(name: str) -> None:
    console = Console.__new__(Console)
    console.emu = emu = playing(name)
    emu[HEART_VALUES] = FULL_HEARTS
    console.enter_cave(CAVE_SCREEN)
    fires = [slot for slot in range(1, 12) if emu[OBJ_TYPE + slot] == CAVE_FIRE_TYPE]
    assert len(fires) == 2
    fire = fires[0]
    emu[OBJ_X], emu[OBJ_Y], emu[OBJ_STATE] = emu[OBJ_X + fire], emu[OBJ_Y + fire] + 22, 0
    emu.run(60, Button.UP)                              # into the fire, which stops him
    assert emu[OBJ_Y] - emu[OBJ_Y + fire] <= 16
    assert burns(emu) == 0 and partial_heart(emu) == 0xFF


@pytest.mark.parametrize("name", ROMS)
def test_an_enemy_fireball_does_not_count(name: str) -> None:
    console = Console.__new__(Console)
    console.emu = emu = playing(name)
    emu[HEART_VALUES] = FULL_HEARTS
    console.enter_room(1, LEVEL_1_START_ROOM)
    for slot in range(1, 12):
        emu[OBJ_TYPE + slot] = 0
    emu[PERSON_FIREBALLS_ENABLED] = 1                   # the statues shoot, as the cave fires do
    emu.run_until(lambda: partial_heart(emu) != 0xFF, limit=900)
    assert burns(emu) == 0


# --- the cap ------------------------------------------------------------------------------------

def test_the_count_stops_at_255() -> None:
    """The INC wraps 255 to 0; StatsTick runs CapSelfBurns while Link is invincible after the hit, sees
    the flag set (the count was 128 or more), finds a count below 128, and puts 255 back."""
    emu = after_the_flame_is_lit("prg0", CANDLE, CANDLE_SELECTION)
    emu[SELF_BURNS_ADDRESS] = 255
    emu[FLAGS_ADDRESS] |= SELF_BURNS_HIGH               # as an earlier hit's frames set it
    emu.run_until(lambda: partial_heart(emu) != 0xFF, limit=WALK_FRAMES, buttons=Button.UP)    # burned
    emu.run(3)
    assert burns(emu) == 255


def test_the_cap_check_runs_only_after_a_hit() -> None:
    """With the flag set and a count of 0, nothing is put back while Link is not invincible: the check
    is gated on his invincibility timer, which only a hit (or the Clock) holds."""
    emu = playing("prg0")
    emu[FLAGS_ADDRESS] |= SELF_BURNS_HIGH
    emu[SELF_BURNS_ADDRESS] = 0
    emu.run(120)
    assert burns(emu) == 0


def test_a_killing_hit_at_255_stays_at_255() -> None:
    emu = after_the_flame_is_lit("prg0", CANDLE, CANDLE_SELECTION)
    emu[SELF_BURNS_ADDRESS] = 255
    emu[FLAGS_ADDRESS] |= SELF_BURNS_HIGH
    emu[HEART_VALUES] = 0x10
    emu[HEART_PARTIAL] = 0x40
    emu.run_until(lambda: emu.mode == DEAD, limit=WALK_FRAMES, buttons=Button.UP)
    emu.run(10)
    assert burns(emu) == 255


def test_reaching_128_sets_the_mark() -> None:
    emu = after_the_flame_is_lit("prg0", CANDLE, CANDLE_SELECTION)
    emu[SELF_BURNS_ADDRESS] = 127
    assert not emu[FLAGS_ADDRESS] & SELF_BURNS_HIGH
    walk_up_until_burned(emu)
    assert burns(emu) == 128 and emu[FLAGS_ADDRESS] & SELF_BURNS_HIGH


@pytest.mark.parametrize("count", [0, 126, 127, 128])
def test_counts_below_the_cap_are_exact(count: int) -> None:
    emu = after_the_flame_is_lit("prg0", CANDLE, CANDLE_SELECTION)
    emu[SELF_BURNS_ADDRESS] = count
    emu.run(2)
    walk_up_until_burned(emu)
    assert burns(emu) == count + 1


# --- the other statistics choices -----------------------------------------------------------------

HOOK_OFFSET = 0x1F909
HOOK_BYTES = bytes.fromhex("860098aa20267e840da980850eee3f7f4c4f7bea")


def written_at_the_hook(choice: str) -> bytes | None:
    """The 20 bytes a choice leaves at the hook (the game's own where it holds them)."""
    base_rom.remember_repo_base_rom()
    covered = {}
    for offset, piece in SETTINGS["statistics_screen"][choice]:
        covered.update({offset + i: byte for i, byte in enumerate(piece_bytes(piece))})
    return bytes(covered[offset] for offset in range(HOOK_OFFSET, HOOK_OFFSET + len(HOOK_BYTES)))


@pytest.mark.parametrize("choice", ["on", "music", "lozft2"])
def test_every_statistics_choice_counts_in_the_same_place(choice: str) -> None:
    """The hook is bank 7's, the same 20 bytes in the MMC1 build, with randomized music and with
    lozft2: STX $00 / TYA / TAX / JSR BeginShove / STY $0D / LDA #$80 / STA $0E / INC SelfBurns
    ($7F3F) / JMP Link_BeHarmed / NOP, in place of the game's own 20."""
    assert written_at_the_hook(choice) == HOOK_BYTES
    assert HOOK_BYTES != original_bytes(HOOK_OFFSET, len(HOOK_BYTES))


def test_off_leaves_the_games_own_instructions() -> None:
    assert written_at_the_hook("off") == original_bytes(HOOK_OFFSET, len(HOOK_BYTES))
