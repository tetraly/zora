"""Graphics theme in the emulator (Halloween Mode; zora/rom/graphics_theme.py): on the MVP baseline and
an Oops All Bosses seed, the PPU's pattern tables on the overworld and in each level 1-9, and in each
level's first boss room and Ganon's, as played. With the theme on they hold what the same seed holds
when generated from the working copy as a graphics hack (the art at every place the generation copied
a tile to), and differ from the theme off; PRG1 shows the same as PRG0."""
from functools import cache

import pytest

from tests.emulator import ROOM_ID, Emulator, Mode
from tests.test_graphics_theme import CASES, base
from zora.generate.pipeline import generate_rom
from zora.generate.steps.randomize_boss_groups import OLD_BOSS_GROUPS
from zora.model.enums import Enemy
from zora.rom.base_rom import BASE_ROM_PATH
from zora.rom.graphics_theme import GraphicsTheme, themed_player_rom
from zora.rom.parse.rom_file import parse_rom
from zora.rom.player_settings import PlayerSettings

pytestmark = [pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM"), pytest.mark.slow]

SEED = 3
CUR_LEVEL, IS_UPDATING_MODE, GAME_MODE, GAME_SUBMODE = 0x10, 0x11, 0x12, 0x13
ENTER_ROOM_MODE = 0x04
SETTLE_FRAMES = 60
H = GraphicsTheme.HALLOWEEN


def _start_mode(emu: Emulator, mode: int) -> None:
    emu[GAME_MODE] = mode
    emu[GAME_SUBMODE] = 0
    emu[IS_UPDATING_MODE] = 0


def _wait_for_play(emu: Emulator) -> None:
    emu.run_until(lambda: emu.mode == Mode.PLAY and emu[IS_UPDATING_MODE] == 1, limit=900)
    emu.run(SETTLE_FRAMES)


def boss_rooms(rom: bytes) -> list[tuple[int, int]]:
    """Each level's first boss room, and Ganon's."""
    rooms = []
    for level in parse_rom(rom).levels:
        bosses = [room for room in level.rooms if room.enemy in OLD_BOSS_GROUPS]
        ganon = [room for room in level.rooms if room.enemy is Enemy.THE_BEAST]
        rooms += [(level.level_num, room.room_num) for room in bosses[:1] + ganon[:1]]
    return rooms


def pattern_tables(rom: bytes, rooms: list[tuple[int, int]]) -> list[bytes]:
    """The PPU's pattern tables on the overworld, in each level's start room, and in each boss room."""
    emu = Emulator(rom)
    emu.new_game()
    emu.run(SETTLE_FRAMES)
    seen = [emu.pattern_tables()]
    for level in range(1, 10):
        emu[CUR_LEVEL] = level
        _start_mode(emu, Mode.LOAD_LEVEL)
        _wait_for_play(emu)
        seen.append(emu.pattern_tables())
        for room_level, room in rooms:
            if room_level == level:
                emu[ROOM_ID] = room
                _start_mode(emu, ENTER_ROOM_MODE)
                _wait_for_play(emu)
                seen.append(emu.pattern_tables())
    return seen


@cache
def rom(case: str, theme: GraphicsTheme, revision: str = "PRG0") -> bytes:
    flags, zora = CASES[case]
    return generate_rom(flags, SEED, base(revision), PlayerSettings(graphics_theme=theme), zora).rom


@pytest.mark.parametrize("case", ["baseline", "oops all bosses"])
def test_the_art_is_where_the_seed_put_each_tile(case: str) -> None:
    flags, zora = CASES[case]
    rooms = boss_rooms(rom(case, GraphicsTheme.OFF))
    assert len(rooms) >= 9
    on = pattern_tables(rom(case, H), rooms)
    as_hack = pattern_tables(generate_rom(flags, SEED, themed_player_rom(base(), H).canvas, PlayerSettings(),
                                          zora).rom, rooms)
    off = pattern_tables(rom(case, GraphicsTheme.OFF), rooms)
    assert on == as_hack
    assert all(themed != plain for themed, plain in zip(on, off, strict=True))


@pytest.mark.parametrize("case", ["baseline", "oops all bosses"])
def test_prg1_shows_the_same_as_prg0(case: str) -> None:
    rooms = boss_rooms(rom(case, GraphicsTheme.OFF))
    assert pattern_tables(rom(case, H, "PRG1"), rooms) == pattern_tables(rom(case, H), rooms)

