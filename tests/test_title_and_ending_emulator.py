"""The title screen's story and treasure list, and the ending to the credits, in the emulator (2.0.2's test build:
both crashed with Add Triforces or Add Maps/Compasses to the Item Pool on, found in testing).

With either switch, per-level mode (asm/flags2/ap-items, docs/design/archipelago-items.md piece 6) drew the generic
compass, map and Triforce ($16, $17, $1B) far, and a far draw returns with bank 1 mapped. Bank 2 draws those codes
on the title screen (its treasure list, about the keys) and in the ending (the Triforce over Link and over Zelda),
and went on running bank 1's bytes: the title froze, the ending crashed. IsFarCode now draws them as the game does
in those two modes (from 907f2286 to the fix).

Each build: from power-on, the title runs its story and its treasure list to the last row, and back to the title;
then from Zelda's room, Link reaches her and the ending runs through the credits to its last screen. The console
never jams, and its frame counter never stops."""
from collections.abc import Callable
from functools import cache

import pytest

from tests.emulator import CUR_LEVEL, GAME_MODE, GAME_SUBMODE, OBJ_X, OBJ_Y, ROOM_ID, Emulator, Mode
from tests.needs import needs_base_rom
from tests.test_cave_takes_emulator import _base
from zora import archipelago
from zora.flags.fields import ThreeState
from zora.flags.zora_flags import LevelItemShuffle, ZoraFlags, encode
from zora.generate import pipeline
from zora.model.enums import Enemy
from zora.rom import inventory
from zora.rom.parse.rom_file import parse_rom

pytestmark = needs_base_rom

SEED = 1
FRAME_COUNTER = 0x15
IS_UPDATING_MODE = 0x11
LINK_INVINCIBILITY_TIMER = 0x4F0
INVINCIBLE = 0xFF
STILL_FRAMES = 120                      # a frame counter standing this long: the console has hung
# The title's phases (BeginEndVars.inc): the story and treasure list are phase 1, its rows DemoItemRow
DEMO_PHASE = 0x42C
DEMO_ITEM_ROW = 0x42F
STORY_PHASE = 1
LAST_ITEM_ROW = 22
TITLE_LIMIT = 6000                      # the first cycle ends near frame 4,830
# The ending (mode $13): submode 3 scrolls the credits (about 2,160 frames), submode 4 is the last screen. The
# rescue runs submodes 0-4 once before them, its submode 3 some 80 frames: the credits are the long one.
WIN_GAME_MODE = 0x13
CREDITS_SUBMODE = 3
LAST_SUBMODE = 4
CREDITS_FRAMES = 1000
ENDING_LIMIT = 6000                     # the last screen comes near frame 3,660
ZELDA_X, ZELDA_Y = 0x78, 0x95           # UpdateZelda: X $70-$80 and Y $95 reach her

BOTH = ZoraFlags(triforce_shuffle=LevelItemShuffle.ANYWHERE, map_compass_shuffle=LevelItemShuffle.ANYWHERE)
CASES = {
    "single player, Add Triforces": ZoraFlags(triforce_shuffle=LevelItemShuffle.ANYWHERE),
    "single player, Add Maps/Compasses": ZoraFlags(map_compass_shuffle=LevelItemShuffle.ANYWHERE),
    "single player, defaults": ZoraFlags(),
}


@cache
def single_player(name: str) -> bytes:
    return pipeline.generate_rom(archipelago.DEFAULT_FLAGS, SEED, _base("prg0"), zora_flag_string=encode(CASES[name])).rom


@cache
def archipelago_rom(revision: str) -> bytes:
    """Both switches on, BUILD's own placement as the multiworld's."""
    base = _base(revision)
    result = archipelago.build_from_strings(archipelago.DEFAULT_FLAGS, encode(BOTH), SEED, base)
    fill = {place.name: item for place, item in zip(result.places, result.pool, strict=True)}
    return archipelago.finish(result, fill)


BUILDS: dict[str, Callable[[], bytes]] = {
    **{name: (lambda name=name: single_player(name)) for name in CASES},     # type: ignore[misc]
    "Archipelago, both, PRG0": lambda: archipelago_rom("prg0"),
    "Archipelago, both, PRG1": lambda: archipelago_rom("prg1"),
}


def run_until(emu: Emulator, done: Callable[[], bool], limit: int, invincible: bool = False) -> None:
    """Frame by frame until `done`; never a jammed console or a frame counter standing still."""
    still = 0
    for frame in range(limit):
        if invincible:
            emu[LINK_INVINCIBILITY_TIMER] = INVINCIBLE
        before = emu[FRAME_COUNTER]
        emu.run(1)
        assert not emu.nes.has_crashed, f"the console jammed at frame {frame}, mode ${emu[GAME_MODE]:02X}"
        still = still + 1 if emu[FRAME_COUNTER] == before else 0
        assert still < STILL_FRAMES, f"the console hung at frame {frame - still}, mode ${emu[GAME_MODE]:02X}"
        if done():
            return
    raise AssertionError(f"not reached in {limit} frames")


@pytest.mark.parametrize("build", BUILDS)
def test_the_title_runs_its_treasure_list_to_the_end(build: str) -> None:
    emu = Emulator(BUILDS[build]())
    seen = {"last row": False}

    def back_to_the_title() -> bool:
        seen["last row"] |= emu[DEMO_PHASE] == STORY_PHASE and emu[DEMO_ITEM_ROW] == LAST_ITEM_ROW
        return seen["last row"] and emu[DEMO_PHASE] != STORY_PHASE
    run_until(emu, back_to_the_title, TITLE_LIMIT)
    assert emu.mode == Mode.TITLE


@pytest.mark.parametrize("build", BUILDS)
def test_the_ending_runs_through_the_credits(build: str) -> None:
    rom = BUILDS[build]()
    level9 = next(level for level in parse_rom(rom).levels if level.level_num == 9)
    zelda = next(room.room_num for room in level9.rooms if room.enemy == Enemy.THE_KIDNAPPED)
    emu = Emulator(rom)
    emu.new_game()
    emu[inventory.ITEMS + inventory.HEART_VALUES_SLOT] = INVINCIBLE
    in_play = lambda: emu.mode == Mode.PLAY and emu[IS_UPDATING_MODE] == 1  # noqa: E731
    emu[CUR_LEVEL] = 9
    emu[GAME_MODE], emu[GAME_SUBMODE], emu[IS_UPDATING_MODE] = Mode.LOAD_LEVEL, 0, 0
    run_until(emu, in_play, 900, invincible=True)
    emu[ROOM_ID] = zelda
    emu[GAME_MODE], emu[GAME_SUBMODE], emu[IS_UPDATING_MODE] = 0x04, 0, 0
    run_until(emu, in_play, 900, invincible=True)
    emu.run(30)
    emu[OBJ_X], emu[OBJ_Y] = ZELDA_X, ZELDA_Y
    credits = {"frames": 0}

    def last_screen() -> bool:
        in_ending = emu.mode == WIN_GAME_MODE
        credits["frames"] += in_ending and emu[GAME_SUBMODE] == CREDITS_SUBMODE
        return credits["frames"] >= CREDITS_FRAMES and in_ending and emu[GAME_SUBMODE] == LAST_SUBMODE
    run_until(emu, last_screen, ENDING_LIMIT, invincible=True)
