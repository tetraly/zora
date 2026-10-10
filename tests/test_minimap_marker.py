"""The map's position marker (docs/reports/minimap-marker.md): PRG0 draws Link's marker on the
status bar's map (UpdatePositionMarker, bank 1) and on the item screen's dungeon map (bank 5) as
sprite tile $3E with attributes 0, and the tile's 3x3 dot is colour 1 of sprite palette 0: the
tunic colour, which the rings and FP-SET-02's tunic setting change. A black tunic makes the marker
black, and the dungeon map's background is black, so the marker disappears there (beta tester's
report).

The fix (owner ruling, option d): with a colour from MARKER_HIDING_COLOURS in any of the three
tunic slots, the dot is drawn in colour 2, Link's skin; otherwise the marker stays PRG0's. The
page shows a note from the same set (metadata.markerHidingColours)."""
import json
import re
from functools import cache
from pathlib import Path

import pytest

from tests.test_feature_patches import vanilla
from zora.flags import form as flag_form
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.rom.player_settings import (
    BLACKER_THAN_BLACK,
    DEFAULT_PLAYER_SETTINGS,
    MARKER_HIDING_COLOURS,
    PAGE_TUNIC_SLOTS,
    PALETTE_SIZE,
    TUNIC_SLOTS,
    PlayerSettings,
    apply_player_settings,
    written_offsets,
)

MARKER_TILE = 0x3E
# CommonSpritePatterns (bank 2, copied to CHR RAM's sprite table at power-on): tile $3E's 16
# bytes, the low plane then the high plane.
MARKER_PATTERN = 0x846F
TILE_BYTES = 16
PLANE_BYTES = 8
# The operand of each `LDA #$00` that sets the marker's attributes: UpdatePositionMarker's
# player path (status bar map) and the item screen's dungeon map (Sprites+82).
STATUS_BAR_MARKER_ATTRIBUTE = 0x6A99
ITEM_SCREEN_MARKER_ATTRIBUTE = 0x140DF
LINKS_PALETTE = 0x00
TUNIC_COLOUR_INDEX = 1
DOT_ROWS, DOT_COLUMNS = 3, 3

SKIN_COLOUR_INDEX = 2
STATUS_BAR_MARKER_SPRITE = 84          # Sprites+84: Y, tile, attributes, X (sprite 21)
BLACK_TUNIC = 0x0F


def pixel_indexes(pattern: bytes) -> list[list[int]]:
    """An 8x8 tile's colour indexes, row by row."""
    low, high = pattern[:PLANE_BYTES], pattern[PLANE_BYTES:]
    return [[(low[row] >> (7 - column) & 1) | (high[row] >> (7 - column) & 1) << 1 for column in range(8)]
            for row in range(8)]


def dot(rom: bytes) -> set[int]:
    """The colour indexes of the marker's drawn pixels."""
    pixels = pixel_indexes(rom[MARKER_PATTERN:MARKER_PATTERN + TILE_BYTES])
    drawn = {(row, column) for row in range(8) for column in range(8) if pixels[row][column]}
    assert drawn == {(row, column) for row in range(DOT_ROWS) for column in range(DOT_COLUMNS)}
    return {pixels[row][column] for row, column in drawn}


@cache
def zora_rom() -> bytes:
    return generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, vanilla()).rom


@pytest.mark.parametrize("which", ["PRG0", "ZORA"])
def test_the_marker_is_a_dot_in_the_tunic_colour(which: str) -> None:
    rom = vanilla() if which == "PRG0" else zora_rom()
    assert dot(rom) == {TUNIC_COLOUR_INDEX}
    assert rom[STATUS_BAR_MARKER_ATTRIBUTE] == rom[ITEM_SCREEN_MARKER_ATTRIBUTE] == LINKS_PALETTE
    # Each attribute operand follows `LDA #$3E / STA Sprites+...`: the marker tile's store.
    assert rom[STATUS_BAR_MARKER_ATTRIBUTE - 5] == rom[ITEM_SCREEN_MARKER_ATTRIBUTE - 5] == MARKER_TILE


def test_a_black_tunic_marker_shows_on_the_dungeon_map() -> None:
    """Level 1 without its map: the status bar map is black around the marker. PRG0's overworld
    (Emulator.walk_into_level_1 needs its screens) with FP-SET-02's tunic setting written."""
    from tests.emulator import Emulator
    emu = Emulator(apply_player_settings(vanilla(), PlayerSettings(tunic_colours=(BLACK_TUNIC, 0x32, 0x16))))
    emu.new_game()
    emu.walk_into_level_1()
    y, tile, attributes, x = emu.sprites()[STATUS_BAR_MARKER_SPRITE:STATUS_BAR_MARKER_SPRITE + 4]
    assert (tile, attributes) == (MARKER_TILE, LINKS_PALETTE)
    marker, beside = emu.last_frame[y + 1, x], emu.last_frame[y + 1, x + DOT_COLUMNS]
    assert not (marker == beside).all()


# --- The fix: a hiding colour in any slot draws the dot in Link's skin colour --------------------

def with_tunic(slot: int, colour: int) -> tuple[int, int, int]:
    tunics = list(DEFAULT_PLAYER_SETTINGS.tunic_colours)
    tunics[slot] = colour
    return tunics[0], tunics[1], tunics[2]


def changed_offsets(before: bytes, after: bytes) -> set[int]:
    return {offset for offset, (old, new) in enumerate(zip(before, after, strict=True)) if old != new}


def test_a_hiding_colour_from_the_generator_draws_the_skin_marker() -> None:
    rom = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, vanilla(),
                       player_settings=PlayerSettings(tunic_colours=with_tunic(0, BLACK_TUNIC))).rom
    assert dot(rom) == {SKIN_COLOUR_INDEX}
    assert changed_offsets(zora_rom(), rom) <= written_offsets("tunic_colours")


@pytest.mark.parametrize("slot", range(TUNIC_SLOTS))
@pytest.mark.parametrize("colour", sorted(MARKER_HIDING_COLOURS))
def test_a_hiding_colour_in_any_slot_draws_the_skin_marker(slot: int, colour: int) -> None:
    rom = apply_player_settings(zora_rom(), PlayerSettings(tunic_colours=with_tunic(slot, colour)))
    assert dot(rom) == {SKIN_COLOUR_INDEX}
    assert changed_offsets(zora_rom(), rom) <= written_offsets("tunic_colours")


ORDINARY_COLOURS = [colour for colour in range(PALETTE_SIZE)
                    if colour not in MARKER_HIDING_COLOURS and colour != BLACKER_THAN_BLACK]


@pytest.mark.parametrize("slot", range(TUNIC_SLOTS))
def test_ordinary_colours_keep_prg0s_marker(slot: int) -> None:
    """Every other colour, in each slot: only the tunic bytes change; the marker stays PRG0's."""
    marker_bytes = set(range(MARKER_PATTERN, MARKER_PATTERN + TILE_BYTES))
    for colour in ORDINARY_COLOURS:
        rom = apply_player_settings(zora_rom(), PlayerSettings(tunic_colours=with_tunic(slot, colour)))
        assert not changed_offsets(zora_rom(), rom) & marker_bytes, f"${colour:02X}"
        assert dot(rom) == {TUNIC_COLOUR_INDEX}


def test_default_settings_leave_the_output_byte_identical() -> None:
    assert apply_player_settings(zora_rom(), DEFAULT_PLAYER_SETTINGS) == zora_rom()


# --- The set: the report's rule, and the page's copy ---------------------------------------------

PAGE_SCRIPT = Path(__file__).resolve().parent.parent / "web" / "zora-web.js"
# The map backgrounds the marker sits on: black (levels, item screen), grey $00 (overworld), room
# blue $12 (a level's shown rooms). A colour under HIDING_DISTANCE (CIE76) from one of them hides
# the marker, and one under FAINT_ON_BLACK from black is too faint there (a 3x3 dot on a TV).
BLACK = 0x0F
MAP_BACKGROUNDS = (BLACK, 0x00, 0x12)
HIDING_DISTANCE = 25
FAINT_ON_BLACK = 30


def page_palette() -> list[tuple[int, int, int]]:
    table = PAGE_SCRIPT.read_text().split("const NES_PALETTE = [")[1].split("];")[0]
    return [(int(code[0:2], 16), int(code[2:4], 16), int(code[4:6], 16))
            for code in re.findall(r'"#([0-9a-f]{6})"', table)]


def lab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    """sRGB (D65) to CIE L*a*b*."""
    def linear(channel: int) -> float:
        value = channel / 255
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    r, g, b = (linear(channel) for channel in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    return 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))


def colour_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return float(sum((p - q) ** 2 for p, q in zip(lab(a), lab(b), strict=True)) ** 0.5)


def test_the_set_is_the_reports_rule() -> None:
    """The 16 colours of docs/reports/minimap-marker.md, in the page's palette (the same RGB
    values the emulator shows)."""
    palette = page_palette()

    def hides(colour: int) -> bool:
        nearest = min(colour_distance(palette[colour], palette[back]) for back in MAP_BACKGROUNDS)
        return nearest < HIDING_DISTANCE or colour_distance(palette[colour], palette[BLACK]) < FAINT_ON_BLACK

    hiding = {colour for colour in range(PALETTE_SIZE) if colour != BLACKER_THAN_BLACK and hides(colour)}
    assert hiding == MARKER_HIDING_COLOURS and len(hiding) == 16


def test_the_page_takes_the_set_from_the_metadata() -> None:
    """The page's note reads metadata.markerHidingColours (no list of its own), and its tunic
    slots are player_settings_from_page's."""
    metadata = json.loads(json.dumps(flag_form.metadata()))
    assert metadata["markerHidingColours"] == sorted(MARKER_HIDING_COLOURS)
    page = PAGE_SCRIPT.read_text()
    assert "metadata.markerHidingColours.includes(" in page
    slots = re.search(r"const TUNIC_SLOTS = \[([^\]]*)\]", page)
    assert slots and tuple(json.loads(f"[{slots.group(1)}]")) == PAGE_TUNIC_SLOTS
