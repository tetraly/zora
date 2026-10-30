"""The level word in the hints, in the emulator (FP-LEVEL-01; zora/rom/player_settings.py
end_padded_hint_line). A word shorter than LEVEL leaves a relabeled hint line spare tiles, padded
at its end. The person text drawer skips the padding tile before it reads the tile's line or end
bits, so a line ending on one ran on into the next line, past the box's right edge and round to
the next row's left edge ("KEEP-5 LIES HIGH IN DE" / "ATH MOUNTAIN.", a player's report,
2026-10-29), and a text whose end bits fell on one never ended, drawing the next text's tiles. The
padding now closes with a space, whose bits the drawer reads.

Seed 6 of the MVP baseline with the word KEEP: every person room of
levels 1-8 draws its text inside the box's 24 columns, the columns either side as with the
default word; with the old end padding (pad tiles only) at least one does not."""
from functools import cache

import pytest

import zora.rom.player_settings as player_settings
from tests.needs import needs_base_rom
from tests.test_assignment_emulator import Console
from tests.test_feature_patches import vanilla
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.model.levels import HINT_LEVELS
from zora.rom.parse.rom_file import parse_rom
from zora.rom.player_settings import TEXT_PAD_CHARACTER, PlayerSettings, apply_player_settings

pytestmark = [needs_base_rom, pytest.mark.slow]
SEED = 6                       # level 5's room $79: "KEEP-1 LIES UP IN THE" ends on padding
WORD = "KEEP"
TEXT_ROWS, ROW_TILES, TEXT_LINES = 0x21A0, 32, 3   # the nametable rows the text's lines are drawn in
TEXT_COLUMNS = range(4, 28)    # the box's 24 columns
TEXT_FRAMES = 400              # long enough for the longest text to finish


@cache
def finished() -> bytes:
    return generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, vanilla()).rom


def person_rooms() -> list[tuple[int, int]]:
    world = parse_rom(finished())
    return [(level.level_num, room.room_num) for level in world.levels if level.level_num in HINT_LEVELS
            for room in level.rooms if room.is_person_room]


def outside_the_box(data: bytes, level: int, room: int) -> list[bytes]:
    """Each text row's tiles left and right of the box's columns, once the text has run."""
    console = Console(data)
    console.enter_room(level, room)
    console.emu.run(TEXT_FRAMES)
    rows = console.emu.nametable(TEXT_ROWS, ROW_TILES * TEXT_LINES)
    return [bytes(tile for column, tile in enumerate(rows[ROW_TILES * line:ROW_TILES * (line + 1)])
                  if column not in TEXT_COLUMNS) for line in range(TEXT_LINES)]


def overflowing_rooms(data: bytes) -> list[tuple[int, int]]:
    return [(level, room) for level, room in person_rooms()
            if outside_the_box(data, level, room) != outside_the_box(finished(), level, room)]


def test_every_hint_stays_in_the_box() -> None:
    assert overflowing_rooms(apply_player_settings(finished(), PlayerSettings(level_word=WORD))) == []


def test_the_old_end_padding_overflows(monkeypatch: pytest.MonkeyPatch) -> None:
    """The old padding (pad tiles only), with the line encoders' own guard (text_encoding.closed_line,
    8bb9bb3, which would close such a line with a space too) also left out."""
    monkeypatch.setattr(player_settings, "end_padded_hint_line",
                        lambda line, length: line.ljust(length, TEXT_PAD_CHARACTER))
    monkeypatch.setattr(player_settings, "closed_line", lambda tiles: tiles)
    assert (5, 0x79) in overflowing_rooms(apply_player_settings(finished(), PlayerSettings(level_word=WORD)))
