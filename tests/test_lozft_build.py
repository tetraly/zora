"""lozft built from its pinned source (scripts/lozft_build.py; docs/music.md "lozft from source").

Without Node, the lozft clone or js65 in the music folder, the build tests skip; the data tests
always run: zora/rom/music/lozft_patch_data.py holds no byte of the original game, never copies
from the player's tiles, and gives the same bytes on a ROM whose tiles are scrambled.
"""
import importlib.util
import random
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest

from tests.needs import needs_base_rom
from zora.rom import base_rom
from zora.rom.base_rom import Original
from zora.rom.music.lozft_patch_data import PATCHES
from zora.rom.revision import GRAPHICS_BLOCKS, NES_HEADER_SIZE, Revision

REPO = Path(__file__).resolve().parent.parent
BATTERY_BYTE = 6                 # the iNES header's flags 6: mapper 4 ($40), with the battery bit $42
MMC3_WITH_BATTERY = 0x42
PRG_BANKS_BYTE, LOZFT_BANKS = 4, 16


def build_script() -> ModuleType:
    """scripts/lozft_build.py, loaded by path (it is not part of the type-checked scripts)."""
    path = REPO / "scripts" / "lozft_build.py"
    if not path.exists():
        pytest.skip("needs scripts/lozft_build.py")
    spec = importlib.util.spec_from_file_location("lozft_build", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def tile_offsets() -> set[int]:
    return {NES_HEADER_SIZE + offset + index for _name, offset, length in GRAPHICS_BLOCKS for index in range(length)}


def can_build() -> bool:
    from scripts.music_assets import music_folder
    return shutil.which("node") is not None and (music_folder() / "lozft" / ".git").exists() \
        and (music_folder() / "js65" / "package-lock.json").exists()


needs_build = pytest.mark.skipif(not can_build(), reason="needs Node, music/lozft and music/js65")


def test_copies_never_read_tiles() -> None:
    tiles = tile_offsets()
    for revision, patch in PATCHES.items():
        for offset, piece in patch:
            if isinstance(piece, Original):
                assert not tiles & set(range(piece.source, piece.source + piece.length)), (revision, hex(offset))


@needs_base_rom
def test_no_original_game_bytes_in_the_literals() -> None:
    script = build_script()
    releases = [script.release(Revision.PRG0), script.release(Revision.PRG1)]
    for patch in PATCHES.values():
        assert script.scan_hits(list(patch), releases) == []


@needs_base_rom
@pytest.mark.parametrize("revision", [Revision.PRG0, Revision.PRG1])
def test_scrambled_tiles_give_the_same_bytes(revision: Revision) -> None:
    script = build_script()
    game = script.release(revision)
    scrambled = bytearray(game)
    rng = random.Random(revision.value)
    for offset in tile_offsets():
        scrambled[offset] = rng.randrange(256)

    def written(data: bytes) -> list[bytes]:
        with base_rom.using_player_rom(base_rom.player_rom_of(data)):
            return [base_rom.piece_bytes(piece) for _offset, piece in PATCHES[revision.value]]

    assert written(bytes(scrambled)) == written(game)


@needs_build
@needs_base_rom
def test_quantams_source_builds_his_patch() -> None:
    """lozft as Quantam published it, built here, is exactly what his own lozft.bps makes."""
    script = build_script()
    source = script.export_source(script.UPSTREAM_COMMIT, script.SCRATCH / "test-upstream")
    assert script.upstream_check(source) == []


@needs_build
@needs_base_rom
def test_the_pin_is_quantams_build_by_default() -> None:
    """The pinned commit, built without ZORA's defines, is its own committed lozft.bps byte for byte:
    each of ZORA's changes is an option."""
    script = build_script()
    source = script.export_source(script.LOZFT_COMMIT, script.SCRATCH / "test-fork")
    assert script.upstream_check(source) == []


@needs_build
@needs_base_rom
def test_the_data_is_the_build() -> None:
    """zora/rom/music/lozft_patch_data.py is what the pinned source builds today."""
    script = build_script()
    source = script.export_source(script.LOZFT_COMMIT, script.SCRATCH / "source")
    claims = script.zora_claims()
    builds = [script.build(revision, source, claims) for revision in (Revision.PRG0, Revision.PRG1)]
    assert script.data_text(builds) == script.DATA_FILE.read_text()


MUSIC_STATE = 0x0153             # lozft's MusicState (its FT_RAM at $0150, lozft.dbg): 2 while a FamiTracker song plays
PLAYING_FT = 2
OVERWORLD_FRAMES = 600


@needs_base_rom
@pytest.mark.parametrize("revision", [Revision.PRG0, Revision.PRG1])
def test_a_music_rom_from_source_plays(revision: Revision) -> None:
    """A seed with Music: Random through lozft built from source (randomize_music(from_source=True)):
    the 256 KB MMC3 ROM with the battery bit, the statistics screen called once a frame, every cave
    kind's take and a FamiTracker song on the overworld, in the emulator, without a crash."""
    from tests.test_bait_in_pool import CAVE_ITEM_IDS, ITEM_INACTIVE, Console
    from tests.test_cave_takes_emulator import CAVES, ITEMS, SEED, SETTLE_FRAMES, _music_assets
    from tests.test_progressive_emulator import INV_LETTER, LETTER_DELIVERED
    from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
    from zora.generate.pipeline import generate_rom
    from zora.rom.music.randomize import randomize_music
    from zora.rom.parse.rom_file import parse_rom
    from zora.rom.player_settings import Music, PlayerSettings
    script = build_script()
    base = script.release(revision)
    base_rom.remember_repo_base_rom()
    rom = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, base, PlayerSettings(music=Music.RANDOM_STANDARD)).rom
    world = parse_rom(rom)
    screens = {destination: next(screen.screen_num for screen in world.overworld.screens
                                 if screen.destination == destination) for destination in CAVES}
    music = randomize_music(rom, base, _music_assets(), SEED, from_source=True).rom
    assert music[PRG_BANKS_BYTE] == LOZFT_BANKS and music[BATTERY_BYTE] == MMC3_WITH_BATTERY
    console = Console(music)
    console.emu.run(OVERWORLD_FRAMES)
    assert not console.emu.nes.has_crashed
    assert console.emu[MUSIC_STATE] == PLAYING_FT
    for destination in CAVES:
        for item in ITEMS:
            console = Console(music)
            console.emu[INV_LETTER] = LETTER_DELIVERED           # the potion shop opens
            console.enter_cave(screens[destination])
            position = next(position for position in range(3)
                            if console.emu[CAVE_ITEM_IDS + position] != ITEM_INACTIVE)
            console.emu[CAVE_ITEM_IDS + position] = item
            console.take_ware(position)
            console.emu.run(SETTLE_FRAMES)
            assert not console.emu.nes.has_crashed, (destination, item)


# SetItemValue's JMP once moved: to the Book's routine (B49 on), to the store (B49 off)
SET_ITEM_JUMP_TARGETS = {1: 0xFFC3, 0: 0xFFCB}


@needs_base_rom
@pytest.mark.parametrize(("state", "b49", "item"), [
    ("WOODEN_SWORD_ONLY", 1, "WHITE_SWORD"), ("WOODEN_SWORD_ONLY", 1, "BOOK"), ("WOODEN_SWORD_ONLY", 0, "WHITE_SWORD"),
    ("NORMAL", 1, "BOOK")])
def test_book_is_an_atlas_and_the_bomb_upgrade_on_a_music_rom_from_source(state: str, b49: int, item: str) -> None:
    """lozft's bank switch overlaps ZORA's code at $FFC0-$FFD2, which with_lozft_from_source moves to
    $FFC3-$FFD5 (lozft.moved_set_item_routines): SetItemValue's JMP is re-pointed, and in play item $02
    is still a bomb upgrade in either store layout and the Book still sets its status-bar map trigger."""
    from tests.emulator import ITEMS, OBJ_X, OBJ_Y, ROOM_ITEM_SLOT
    from tests.test_assignment_emulator import Console, floor_room, with_items
    from tests.test_cave_takes_emulator import _music_assets
    from tests.test_sword_states import (
        BOOK_MAP_FLAG,
        BOOK_SLOT,
        INV_BOMBS,
        INV_SWORD,
        MAX_BOMBS,
        PRG0_MAX_BOMBS,
        TAKE_FRAMES,
        _built,
        flags,
    )
    from zora.flags.fields import WoodenSwordState
    from zora.generate.pipeline import finish
    from zora.model.enums import Item
    from zora.rom.music.lozft import SET_ITEM_ROUTINES, SET_ITEM_ROUTINES_SHIFT
    from zora.rom.music.randomize import randomize_music
    from zora.rom.player_settings import Music, PlayerSettings
    from zora.rom.sword_states import SET_ITEM_VALUE_STORE
    base = base_rom.remember_repo_base_rom()
    built = _built(flags(WoodenSwordState[state], B49=b49), 1)
    place = floor_room(built)
    rom = finish(built, base, with_items(built, {place.name: Item[item]}),
                 player_settings=PlayerSettings(music=Music.RANDOM_STANDARD))
    music = randomize_music(rom, base, _music_assets(), 1, from_source=True).rom
    target = SET_ITEM_JUMP_TARGETS[b49]
    assert music[SET_ITEM_VALUE_STORE:SET_ITEM_VALUE_STORE + 3] == bytes([0x4C, target & 0xFF, target >> 8])
    game_fixed, lozft_fixed = NES_HEADER_SIZE + 7 * 0x4000 - 0xC000, NES_HEADER_SIZE + 15 * 0x4000 - 0xC000
    moved = SET_ITEM_ROUTINES.start + SET_ITEM_ROUTINES_SHIFT
    assert music[lozft_fixed + moved:lozft_fixed + moved + len(SET_ITEM_ROUTINES)] == \
        rom[game_fixed + SET_ITEM_ROUTINES.start:game_fixed + SET_ITEM_ROUTINES.stop]
    console = Console(music)
    assert place.level is not None and place.room_num is not None
    console.enter_room(place.level, place.room_num)
    console.clear_monsters()
    emu = console.emu
    emu[OBJ_X], emu[OBJ_Y] = emu[OBJ_X + ROOM_ITEM_SLOT], emu[OBJ_Y + ROOM_ITEM_SLOT]
    triggered = False
    for _ in range(TAKE_FRAMES):
        emu.run(1)
        triggered |= emu[BOOK_MAP_FLAG] != 0
    assert not emu.nes.has_crashed
    if item == "BOOK":
        assert triggered and emu[ITEMS + BOOK_SLOT] == 1
    else:
        assert (emu[INV_SWORD], emu[MAX_BOMBS], emu[INV_BOMBS]) == (0, PRG0_MAX_BOMBS + 2, PRG0_MAX_BOMBS + 2)


def test_the_areas_song_numbers_are_lozfts() -> None:
    """The importer's song number per area (AREA_SONGS) is the number lozft.ftcfg gives the song of
    that name (MUSIC_LAYOUT, read from the build), so a change of lozft's numbering is caught here."""
    from zora.rom.music.importer import AREA_SONGS
    from zora.rom.music.library import DUNGEON, ENDING, LAST_DUNGEON, OVERWORLD, TITLE
    from zora.rom.music.lozft_patch_data import MUSIC_LAYOUT
    names = {OVERWORLD: ("Overworld",), ENDING: ("Ending",), LAST_DUNGEON: ("Dungeon9",),
             DUNGEON: tuple(f"Dungeon{level}" for level in range(1, 9)), TITLE: ("Title",)}
    songs = MUSIC_LAYOUT["songs"]
    assert AREA_SONGS == {area: tuple(songs[name] for name in area_names) for area, area_names in names.items()}


STATS_BLOCK = range(0x7F00, 0x7F40)         # the statistics screen's block (asm/fp-stats-01)
STATS_CLOCK = range(0x7F02, 0x7F1A)         # TotalSeconds, SubFrame, TenthPhase and AreaSeconds
STATS_INPUTS_SEED = 7
CART_RAM = list(range(0x6000, 0x6C90))      # below the code bank 1 copies to RAM
MUSIC_RAM = set(range(0x00, 0x10)) | set(range(0x66, 0x70)) | set(range(0x100, 0x200)) | \
    set(range(0x5F0, 0x5F6)) | set(range(0x600, 0x620)) | {0x4F, 0xE4}     # scratch, sound engines, lozft
PAUSE_FRAMES = 300


def _stats_inputs(frames: int) -> list[int]:
    import random

    from tests.emulator import Button
    rng = random.Random(STATS_INPUTS_SEED)
    pads = [Button.UP, Button.DOWN, Button.LEFT, Button.RIGHT, Button(0)]
    out: list[int] = []
    while len(out) < frames:
        pad = int(rng.choice(pads))
        out += [pad | (int(Button.A) if rng.random() < 0.15 else 0)] * rng.randrange(8, 31)
    return out[:frames]


@needs_base_rom
@pytest.mark.parametrize("revision", [Revision.PRG0, Revision.PRG1])
def test_the_statistics_count_on_lozft2_as_on_mmc1(revision: Revision) -> None:
    """The statistics screen counts frames on a lozft2 ROM (its "lozft2" choice: StatsTick at the end
    of DriveAudio, which lozft calls once a frame) as on today's ROM (StatsTick at IsrNmi's JSR
    DriveAudio). From one game state, copied from the MMC1 ROM into the lozft2 one, the same input
    for each frame the game runs: after every such frame the clock is the same, lag frames or not,
    and the whole block too, on the overworld, in level 9's busiest room (where lozft2 lags less)
    and through a pause."""
    from tests.emulator import FRAME_COUNTER, Button, Emulator
    from tests.test_bait_in_pool import Console
    from tests.test_cave_takes_emulator import SEED, _music_assets
    from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
    from zora.generate.pipeline import generate_rom
    from zora.rom.music.randomize import randomize_music
    from zora.rom.player_settings import Music, PlayerSettings
    script = build_script()
    base = script.release(revision)
    base_rom.remember_repo_base_rom()
    mmc1 = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, base, PlayerSettings()).rom
    music = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, base, PlayerSettings(music=Music.RANDOM_STANDARD)).rom
    lozft2 = randomize_music(music, base, _music_assets(), SEED, from_source=True).rom
    compared = [address for address in range(0x800) if address not in MUSIC_RAM] + CART_RAM + list(STATS_BLOCK)

    def game_frame(emu: Emulator, buttons: int) -> None:
        before = emu[FRAME_COUNTER]
        emu.nes.controller = buttons
        while emu[FRAME_COUNTER] == before:
            emu.nes.step(1)

    for name, level, room, frames in (("overworld", 0, None, 1200), ("level 9 $63", 9, 0x63, 600),
                                      ("paused", 0, None, PAUSE_FRAMES)):
        consoles = [Console(mmc1), Console(lozft2)]
        for console in consoles:
            if room is not None:
                console.enter_room(level, room)
        for address in compared:
            consoles[1].emu[address] = consoles[0].emu[address]
        start = [bytes(console.emu[address] for address in STATS_BLOCK) for console in consoles]
        inputs = _stats_inputs(frames)
        if name == "paused":
            inputs = [int(Button.START)] * 2 + [0] * (frames - 4) + [int(Button.START)] * 2
        for index, buttons in enumerate(inputs):
            blocks = []
            for console in consoles:
                game_frame(console.emu, buttons)
                blocks.append(bytes(console.emu[address] for address in STATS_BLOCK))
            clock = slice(STATS_CLOCK.start - STATS_BLOCK.start, STATS_CLOCK.stop - STATS_BLOCK.start)
            assert blocks[0][clock] == blocks[1][clock], (revision, name, index)
        assert all(block[clock] != first[clock] for block, first in zip(blocks, start, strict=True)), name
        if name != "level 9 $63":            # where lag differs, play may part (the replay report)
            assert blocks[0] == blocks[1], (revision, name)
