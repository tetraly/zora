"""Level items' digits on a Music: Random ROM (2.0.2; found by players on consoles, then in emulators too). lozft moves
29 bytes of IsrNmi from 0x1E4D1 into bank 6, and those bytes hold the digit's hook (asm/flags2/ap-items,
JSR TransferTileBufAndDigit). Copied from the player's ROM, they went back to the game's JSR TransferCurTileBuf:
the digit's sprite was drawn, but its glyph was never written, so no Triforce piece, map or compass showed its
number. lozft now moves the finished ROM's bytes (zora/rom/music/lozft.py moved_piece_bytes).

The seed is the one reported: single player, Add Triforces and Add Maps/Compasses to the Item Pool on, the Item
Counter on, on PRG0 and PRG1."""
from functools import cache

import numpy as np
import pytest

from tests.emulator import Emulator
from tests.needs import needs_base_rom, needs_encoder
from tests.test_assignment_emulator import Console
from tests.test_cave_takes_emulator import _base, _music_assets
from tests.test_level_items_emulator import DIGIT_FRAMES, shown_digits
from zora.generate import pipeline
from zora.generate.places import Place, PlaceKind
from zora.generate.solo_assignment import solo_assignment
from zora.model.enums import Item
from zora.model.level_items import level_of
from zora.rom.base_rom import Original, as_player_rom, player_rom_of, using_player_rom
from zora.rom.music.lozft import with_lozft_from_source
from zora.rom.music.lozft_patch_data import PATCHES
from zora.rom.player_settings import Music, PlayerSettings
from zora.rom.revision import in_prg0_layout

SEED = 3790294229101682353
Z1R_FLAGS = "oIbnPfPb01Hll3CyNpAHO63H9tZw5aOkkiU8a"
ZORA_FLAGS = "23.9UTKssCWMDGkC"
ROOMS = 3                                   # level-item rooms checked
DIGIT_HOOK = 0x1E4D1                        # IsrNmi's JSR TransferCurTileBuf, the ap-items hook
REVISIONS = {"prg0": "PRG0", "prg1": "PRG1"}


@cache
def finished(revision: str) -> tuple[bytes, bytes, tuple[Place, ...]]:
    """The reported seed's ROM made for Music: Random (before lozft), the player's ROM, and the first ROOMS
    floor places that hold a level item."""
    base = _base(revision)
    with using_player_rom(as_player_rom(base)):
        built = pipeline.build(pipeline.plan(Z1R_FLAGS, SEED, ZORA_FLAGS), base)
    assignment = solo_assignment(built)
    places = tuple(place for place in built.places if place.kind is PlaceKind.ROOM
                   and isinstance(item := assignment[place.name], Item) and level_of(item) is not None)[:ROOMS]
    assert len(places) == ROOMS
    rom = pipeline.generate_rom(Z1R_FLAGS, SEED, base, PlayerSettings(music=Music.RANDOM_STANDARD),
                                zora_flag_string=ZORA_FLAGS).rom
    return rom, base, places


def digits(rom: bytes, place: Place) -> list[int]:
    assert place.level is not None and place.room_num is not None
    console = Console(rom)
    console.enter_room(place.level, place.room_num)
    console.clear_monsters()
    console.emu.run(DIGIT_FRAMES)
    return shown_digits(console, rom)


@needs_base_rom
@needs_encoder                              # the reported seed encodes its levels
@pytest.mark.parametrize("revision", REVISIONS)
def test_the_digits_show_on_a_music_rom(revision: str) -> None:
    """Each room's digit with the seed's songs is the one the same ROM without lozft shows."""
    from zora.rom.music.randomize import randomize_music
    rom, base, places = finished(revision)
    music = randomize_music(rom, base, _music_assets(), SEED).rom
    for place in places:
        expected = digits(rom, place)
        assert len(expected) == 1 and expected[0] in range(1, 10), (place.name, expected)
        assert digits(music, place) == expected, place.name


@needs_base_rom
@needs_encoder                              # the reported seed encodes its levels
@pytest.mark.parametrize("revision", REVISIONS)
def test_no_moved_piece_drops_a_zora_change(revision: str) -> None:
    """Every piece of the game's code lozft moves lands as the finished ROM holds it, the digit's hook among them."""
    rom, base, _ = finished(revision)
    out = with_lozft_from_source(rom, base)
    player = player_rom_of(base)
    original, rom = player.layout, in_prg0_layout(rom, player.revision)    # where the sources are
    changed = []
    for target, piece in PATCHES[REVISIONS[revision]]:
        if not isinstance(piece, Original):
            continue
        source = rom[piece.source:piece.source + piece.length]
        assert out[target:target + piece.length] == source, f"{piece.source:#07x} moved to {target:#07x}"
        if source != original[piece.source:piece.source + piece.length]:
            changed.append(piece.source)
    assert DIGIT_HOOK in changed            # the finished ROM's change there is what this guards


DYNAMIC_TILE_BUFFER = 0x302                 # DynTileBuf: the game's transfer records, ended by a byte >= $80
DIGIT_PAIR_DIGIT, DIGIT_PENDING = 0x370, 0x376
RECORD_COUNT, RECORD_REPEAT, END_MARK = 0x3F, 0x40, 0x80
STATUS_BAR_UPDATE_BYTES = 30                # the game's every-other-frame status bar update sends 34
FORCED_DIGIT = 4
SPILL_FRAMES = 2


def dynamic_buffer_bytes(emu: Emulator) -> int:
    """The bytes the next frame update's dynamic transfer writes."""
    at, total = DYNAMIC_TILE_BUFFER, 0
    while emu[at] < END_MARK:
        flags = emu[at + 2]
        count = flags & RECORD_COUNT or RECORD_COUNT + 1
        total += count
        at += 4 if flags & RECORD_REPEAT else 3 + count
    return total


@needs_base_rom
@needs_encoder                              # the reported seed encodes its levels
@pytest.mark.parametrize("music", ["game", "random"])          # the game's music (no lozft), Music: Random
@pytest.mark.parametrize("revision", REVISIONS)
def test_a_digit_glyph_never_spills_past_the_vertical_blank(revision: str, music: str) -> None:
    """2.0.2's test build (reported by players: the screen and the status bar garbled as a level item dropped or a
    room with one was entered). A digit glyph written in the same frame update as the game's status bar update
    pushed the game's transfer past the vertical blank: its last bytes and the video address reset landed while
    the screen was drawn. A glyph waiting on such a frame now waits for a shorter one, so the frames are those of
    the same console with no glyph waiting (the glyph's tile is not on screen)."""
    from zora.rom.music.randomize import randomize_music
    rom, base, places = finished(revision)
    if music == "random":
        rom = randomize_music(rom, base, _music_assets(), SEED).rom
    place = places[0]
    assert place.level is not None and place.room_num is not None
    console = Console(rom)
    console.enter_room(place.level, place.room_num)
    emu = console.emu
    emu.run_until(lambda: dynamic_buffer_bytes(emu) >= STATUS_BAR_UPDATE_BYTES and emu[DIGIT_PENDING] == 0, limit=60)
    state = emu.save()
    frames = {}
    for glyph in (False, True):
        emu.load(state)
        if glyph:                               # pair 0 takes a digit: its glyph waits for the frame update
            emu[DIGIT_PAIR_DIGIT] = FORCED_DIGIT
            emu[DIGIT_PENDING] = 1
        shown = []
        for _ in range(SPILL_FRAMES):
            emu.run(1)
            shown.append(emu.last_frame.copy())
        frames[glyph] = shown
    for frame, (plain, with_glyph) in enumerate(zip(frames[False], frames[True], strict=True)):
        differing = int((plain != with_glyph).any(axis=2).sum())
        assert differing == 0, f"frame {frame + 1}: {differing} pixels differ"
