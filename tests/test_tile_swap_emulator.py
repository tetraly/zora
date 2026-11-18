"""Change Hidden OW Tiles' tile swap (zora/rom/hidden_tiles.py step 4) in the emulator, on a ROM with Randomize
Boss Groups (B40), Change Hidden OW Tiles (B89), Pegasus Boots and the Item Counter on: the secret squares and
the common boss block share background tiles $30-$3F, and $50-$5F hold what every mode needs.

  - Each level load sends the right tiles to $30-$3F: the squares on the overworld, the ROM's own $30-$3F (the
    boss tiles) in a level, after a new file, a level and back, another level, a cave and out, a save, reset and
    Continue; and $50-$5F stay as the ROM has them ($50/$51 blank for Pegasus Boots' priority sprites, so no
    mark shows at a dungeon room's top-left corner, the counter's chest and slash at $52/$53). The same on PRG1
    and with Music: Random.
  - The squares are drawn from $30-$3F and are solid: on every overworld screen with a rock wall or tree secret
    that Link can walk up into, he stops short of it; with the solid test's old range ($50-$5F) he walks into it.
"""
from functools import cache

import pytest

from tests.emulator import CUR_LEVEL, GAME_MODE, GAME_SUBMODE, OBJ_X, OBJ_Y, ROOM_ID, Button, Emulator, Mode
from tests.needs import needs_base_rom
from tests.test_progressive_emulator import IS_UPDATING_MODE, LEAVE_CAVE_MODE, Game
from zora.flags import codec, zora_flags
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import ZoraFlags
from zora.generate.pipeline import generate_rom
from zora.generate.steps.change_secret_spots import BOMBABLE_ROCK_WALL, BURNABLE_TREE, OPEN_SQUARES
from zora.rom import hidden_tiles
from zora.rom.base_rom import PRG1_ROM_PATH, remember_repo_base_rom
from zora.rom.item_counter import CHEST, CHEST_TILE, SLASH, SLASH_TILE, tile_bytes
from zora.rom.layout import BOSS_SET_EXPANSION_SPRITES_ADDRESS
from zora.rom.parse.rom_file import parse_rom
from zora.rom.vanilla_overworld.layouts import read_overworld_layouts

pytestmark = needs_base_rom
SEED = 7
ZORA = zora_flags.encode(ZoraFlags(pegasus_boots=ThreeState.ON, item_counter=ThreeState.ON))
TILE_BYTES = 16
BACKGROUND_TABLE = 0x1000
SQUARE_TILES = hidden_tiles.SQUARE_TILES
BLANK_PAIR = range(0x50, 0x52)                  # Pegasus Boots' priority sprites
ENTER_CAVE_MODE = 0x0B
DEATH_MODE = 0x11
CAVE_FRAMES = 200
SETTLE_FRAMES = 20
# A walk into a secret square: squares are 16 pixels, the play area starts at Y $40
SQUARE = 16
PLAY_AREA_TOP = 0x40
LAYOUT_ROWS = 11
WALK_FRAMES = 40
SOLID_SECRETS = frozenset({BOMBABLE_ROCK_WALL, BURNABLE_TREE})


def flag_string() -> str:
    settings = codec.decode(MVP_BASELINE_LEVEL_ENCODING_OFF)
    return codec.encode(settings.updated(toggles={"B40": ThreeState.ON, "B89": ThreeState.ON}))


def base(release: str) -> bytes:
    remember_repo_base_rom()
    if release == "prg1":
        if not PRG1_ROM_PATH.exists():
            pytest.skip(f"needs {PRG1_ROM_PATH.name}")
        return PRG1_ROM_PATH.read_bytes()
    return remember_repo_base_rom()


@cache
def rom(release: str) -> bytes:
    return generate_rom(flag_string(), SEED, base(release), zora_flag_string=ZORA).rom


@cache
def music_rom(release: str) -> bytes:
    from tests.test_cave_takes_emulator import _music_assets
    from zora.rom.music.randomize import randomize_music
    from zora.rom.player_settings import Music, PlayerSettings
    assets = _music_assets()
    finished = generate_rom(flag_string(), SEED, base(release), PlayerSettings(music=Music.RANDOM_STANDARD),
                            zora_flag_string=ZORA).rom
    return randomize_music(finished, base(release), assets, SEED).rom


def background(emu: Emulator, tiles: range) -> bytes:
    start = BACKGROUND_TABLE + tiles.start * TILE_BYTES
    return emu.pattern_tables()[start:start + len(tiles) * TILE_BYTES]


def start_mode(emu: Emulator, mode: int) -> None:
    emu[GAME_MODE], emu[GAME_SUBMODE], emu[IS_UPDATING_MODE] = mode, 0, 0


def wait_for_play(emu: Emulator) -> None:
    emu.run_until(lambda: emu.mode == Mode.PLAY and emu[IS_UPDATING_MODE] == 1, limit=1500)
    emu.run(SETTLE_FRAMES)


def load_level(emu: Emulator, level: int) -> None:
    emu[CUR_LEVEL] = level
    start_mode(emu, Mode.LOAD_LEVEL)
    wait_for_play(emu)


def boss_tiles(finished: bytes) -> bytes:
    start = BOSS_SET_EXPANSION_SPRITES_ADDRESS
    return finished[start:start + hidden_tiles.BOSS_TILES_SIZE]


def assert_transitions(finished: bytes) -> None:
    squares, bosses = hidden_tiles.marked_tile_bytes(), boss_tiles(finished)
    assert squares != bosses and any(bosses)
    seen = []

    def look(when: str, emu: Emulator) -> None:
        want = squares if emu[CUR_LEVEL] == 0 else bosses
        assert background(emu, SQUARE_TILES) == want, when
        assert background(emu, BLANK_PAIR) == bytes(len(BLANK_PAIR) * TILE_BYTES), when
        counter = background(emu, range(CHEST_TILE, SLASH_TILE + 1))
        assert counter == tile_bytes(CHEST) + tile_bytes(SLASH), when
        seen.append(when)

    emu = Emulator(finished)
    emu.new_game()
    emu.run(SETTLE_FRAMES)
    look("a new file, on the overworld", emu)
    load_level(emu, 1)
    look("level 1", emu)
    load_level(emu, 0)
    look("back on the overworld", emu)
    load_level(emu, 4)
    look("level 4", emu)
    start_mode(emu, DEATH_MODE)
    emu.run_until(lambda: emu.mode != DEATH_MODE, limit=2000)
    for _ in range(3):
        if emu.mode == Mode.PLAY:
            break
        emu.press(Button.START, after=30)
        emu.run(60)
    wait_for_play(emu)
    look("Continue after a death in level 4", emu)
    load_level(emu, 0)
    start_mode(emu, ENTER_CAVE_MODE)
    emu.run(CAVE_FRAMES)
    start_mode(emu, LEAVE_CAVE_MODE)
    wait_for_play(emu)
    look("out of a cave", emu)
    emu.open_item_screen()
    emu.save_and_reload()
    emu.run(SETTLE_FRAMES)
    look("save, reset and Continue", emu)
    assert len(seen) == 7


@pytest.mark.parametrize("release", ("prg0", "prg1"))
def test_each_level_load_swaps_in_the_right_tiles(release: str) -> None:
    assert_transitions(rom(release))


@pytest.mark.slow
@pytest.mark.parametrize("release", ("prg0", "prg1"))
def test_with_music_random_the_same(release: str) -> None:
    assert_transitions(music_rom(release))


def up_walks(finished: bytes) -> list[tuple[int, int, int]]:
    """(screen, column, row) of each rock wall or tree secret with an open square below it, Link's way up into
    it (the gravestone and the rock are pushed: Link moves them, as in PRG0)."""
    layouts = read_overworld_layouts(finished, b"")
    walks = []
    for screen in parse_rom(finished).overworld.screens:
        columns = layouts.layouts[screen.screen_code]
        for column, code in enumerate(columns):
            for row, square in enumerate(layouts.squares[code]):
                if square in SOLID_SECRETS and row + 1 < LAYOUT_ROWS \
                        and layouts.squares[code][row + 1] in OPEN_SQUARES:
                    walks.append((screen.screen_num, column, row))
    return walks


def walk_up(finished: bytes, screen: int, column: int, row: int) -> int:
    """Link's Y after walking up from the square below (screen, column, row)'s."""
    game = Game(finished)
    game.go_to_screen(screen)
    emu = game.emu
    emu[OBJ_X], emu[OBJ_Y] = column * SQUARE, PLAY_AREA_TOP + (row + 1) * SQUARE
    emu.run(2)
    emu.run(WALK_FRAMES, Button.UP)
    assert emu[ROOM_ID] == screen
    return emu[OBJ_Y]


@pytest.mark.slow
def test_the_squares_are_solid() -> None:
    finished = rom("prg0")
    test = hidden_tiles.SOLID_ROUTINE + hidden_tiles.SOLID_ROUTINE_CODE.index(bytes.fromhex("c9309004c940"))
    old_range = bytearray(finished)
    old_range[test + 1], old_range[test + 5] = 0x50, 0x60
    walks = up_walks(finished)
    assert walks
    entered = 0
    for screen, column, row in walks:
        top = PLAY_AREA_TOP + row * SQUARE             # Link stops a few pixels below it (his feet collide)
        assert walk_up(finished, screen, column, row) > top, hex(screen)
        entered += walk_up(bytes(old_range), screen, column, row) < top
    assert entered
