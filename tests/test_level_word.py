"""The level label's word (FP-LEVEL-01, a player setting; zora/rom/player_settings.py).

PRG0 shows "LEVEL-" in one place (ZORA's location hints also name levels so; their part is
tests/test_level_word_hints.py): `LevelNumberTransferBuf`, an 11-byte PPU transfer record in
bank 6's data block (copied to RAM $67F0 at power-on), drawn at the top of the status bar
(nametable row 2, from column 2) when a level loads; InitMode3_Sub7 stores the level's number in
its seventh tile. The item screen scrolls over the play area, not the status bar, so the label
shows there too. The record holds 7 tiles; FP-LEVEL-02 (asm/fp-level-02/) draws an 8-tile label
from its own record for a 7-character label text, so words of up to 6 characters keep the dash
("CASTLE-1") and 7-character words drop it ("DUNGEON1"); shorter labels keep PRG0's record and
code.

The emulator tests run PRG0 (and PRG1) with the setting written (Emulator.walk_into_level_1 needs
the original overworld); ZORA's output holds PRG0's record, number store and FP-LEVEL-02's site
apart from FP-LEVEL-01's dash tile, which the setting writes too, so the results hold for ZORA's
ROMs."""
import json
import re
import shutil
import subprocess
from functools import cache
from pathlib import Path

import numpy as np
import pytest

from tests.test_feature_patches import vanilla
from zora.flags import form as flag_form
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.rom.base_rom import PRG1_ROM_PATH
from zora.rom.layout import (
    FP_LEVEL_DASH_TILE,
    LEVEL_LABEL_RECORD,
    LEVEL_LABEL_RECORD_SIZE,
    LEVEL_NAME_DASH_OFFSET,
    LEVEL_NAME_DASH_TILE,
)
from zora.rom.player_settings import (
    DEFAULT_LEVEL_WORD,
    LEVEL_NUMBER_STORE_OPERAND,
    LEVEL_RECORD,
    LEVEL_RECORD_SIZE,
    LEVEL_WORD_CHARACTERS,
    LEVEL_WORD_CHOICES,
    LEVEL_WORD_DASH_MAX_LENGTH,
    LEVEL_WORD_MAX_LENGTH,
    PlayerSettingError,
    PlayerSettings,
    apply_player_settings,
    level_label,
    level_label_is_long,
    level_word_problem,
    normalized_level_word,
    player_settings_from_page,
    written_offsets,
)
from zora.rom.player_settings_data import SETTINGS
from zora.rom.text_encoding import BYTE_TO_CHAR, CHAR_TO_BYTE

REPO = Path(__file__).resolve().parent.parent
PAGE_SCRIPT = REPO / "web" / "zora-web.js"
LABEL_ROW = 0x2040                     # status bar row 2
LABEL_COLUMN = 2
ROW_TILES = 32
BLANK = " "
PRG0_DASH_TILE = 0x62                  # the record's dash before FP-LEVEL-01 (these tests run on PRG0)
# The label's pixels on screen: row 2's 8 scanlines, columns 2-9 (the longest label, 8 tiles).
LABEL_PIXELS = (slice(16, 24), slice(16, 80))
# Words the default run renders: the default, the shortest, a 5-character word (the longest short
# label), 6- and 7-character words (FP-LEVEL-02), the font's punctuation; the slow run renders
# every listed word.
QUICK_WORDS = ("LEVEL", "DEN", "TOWER", "PALACE", "DUNGEON", "A.B-C?")
# FP-LEVEL-02's site: the hook (InitMode3_Sub7's number store and selector cue) and the slot.
LEVEL_LABEL_HOOK = range(0x1703F, 0x17046)
LEVEL_LABEL_SLOT = range(0x17CD0, 0x17D00)
CUSTOM_CASES = {
    "level": "LEVEL", " Lair ": "LAIR", "x": "X", "R2-D2": "R2-D2", "OH, NO": "OH, NO", "dungeon": "DUNGEON",
    "": None, "   ": None, "DUNGEONS": None, "A~B": None, "ÄRA": None, "A_B": None, "A/B": None,
}


@cache
def zora_rom() -> bytes:
    return generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, vanilla()).rom


def test_every_listed_word_fits() -> None:
    """No listed word is dropped: each is at most 7 characters of the font."""
    assert len(set(LEVEL_WORD_CHOICES)) == len(LEVEL_WORD_CHOICES) == 28
    assert LEVEL_WORD_CHOICES[0] == DEFAULT_LEVEL_WORD
    for word in LEVEL_WORD_CHOICES:
        assert level_word_problem(word) is None, word


def test_prg0_and_zora_hold_the_record_the_setting_rewrites() -> None:
    """One copy of the label in the ROM: PRG0's record, which ZORA keeps apart from the dash."""
    original, rom = vanilla(), zora_rom()
    assert original.count(bytes.fromhex("150e1f0e15")) == 1
    # PRG0's record, read from the base ROM: PPU $2042 and 7 tiles, "LEVEL", the status bar's
    # dash, the number's tile (0 until the game writes it) and the end mark.
    record = original[LEVEL_RECORD:LEVEL_RECORD + LEVEL_RECORD_SIZE]
    assert record[:3] == bytes.fromhex("2042 07") and record[-2:] == bytes.fromhex("00 ff")
    assert "".join(BYTE_TO_CHAR[tile] for tile in record[3:-3]) == "LEVEL" and record[-3] == LEVEL_NAME_DASH_TILE
    assert original[LEVEL_NUMBER_STORE_OPERAND - 1:LEVEL_NUMBER_STORE_OPERAND + 2] == bytes.fromhex("8d2568")
    for offset in (*range(LEVEL_RECORD, LEVEL_RECORD + LEVEL_RECORD_SIZE), LEVEL_NUMBER_STORE_OPERAND):
        expected = FP_LEVEL_DASH_TILE if offset == LEVEL_NAME_DASH_OFFSET else original[offset]
        assert rom[offset] == expected, hex(offset)


def test_the_default_word_leaves_the_output_byte_identical() -> None:
    assert apply_player_settings(zora_rom(), PlayerSettings()) == zora_rom()
    assert apply_player_settings(zora_rom(), PlayerSettings(level_word=DEFAULT_LEVEL_WORD)) == zora_rom()


@pytest.mark.parametrize("word", LEVEL_WORD_CHOICES[1:])
def test_another_word_changes_only_its_bytes(word: str) -> None:
    rom = apply_player_settings(zora_rom(), PlayerSettings(level_word=word))
    changed = {offset for offset, (a, b) in enumerate(zip(zora_rom(), rom, strict=True)) if a != b}
    assert changed and changed <= written_offsets("level_word")


def test_long_labels_are_6_and_7_character_words() -> None:
    """FP-LEVEL-02 is written for a 7-character label text: a 6-character word and its dash, or a
    7-character word. Every word keeps the dash up to 6 characters."""
    assert (LEVEL_WORD_MAX_LENGTH, LEVEL_WORD_DASH_MAX_LENGTH) == (7, 6)
    assert [level_label(word) for word in ("LEVEL", "CASTLE", "DUNGEON")] == ["LEVEL-1", "CASTLE-1", "DUNGEON1"]
    for word in ("X", "DEN", "LAIR", "LEVEL", "TOWER", "CASTLE", "PALACE", "DUNGEON", "ABCDEFG"):
        assert level_label_is_long(word) == (len(word) >= 6), word


def site_bytes(rom: bytes | bytearray) -> bytes:
    return bytes(rom[offset] for offset in (*LEVEL_LABEL_HOOK, *LEVEL_LABEL_SLOT))


@pytest.mark.parametrize("word", ["LEVEL", "DEN", "TOWER", "R2-D2"])
def test_a_short_label_leaves_fp_level_02s_site(word: str) -> None:
    """A label of up to 7 tiles keeps PRG0's code at the hook and the slot's free space, as ZORA's
    output and PRG0 hold them."""
    rom = bytearray(apply_player_settings(zora_rom(), PlayerSettings(level_word=word)))
    rom[LEVEL_NUMBER_STORE_OPERAND] = zora_rom()[LEVEL_NUMBER_STORE_OPERAND]     # the short label's own write
    assert site_bytes(rom) == site_bytes(zora_rom()) == site_bytes(vanilla())
    assert all(rom[offset] == 0xFF for offset in LEVEL_LABEL_SLOT)


@pytest.mark.parametrize("word", ["CASTLE", "DUNGEON"])
def test_a_long_label_writes_fp_level_02_and_its_record(word: str) -> None:
    """The patch's bytes at the hook and the routine, the word's record in the slot, and PRG0's
    record and number store as ZORA's output holds them."""
    rom = apply_player_settings(zora_rom(), PlayerSettings(level_word=word))
    pieces = dict(SETTINGS["level_label"]["long"])
    jump, routine = pieces[LEVEL_LABEL_HOOK.start], pieces[LEVEL_LABEL_RECORD + LEVEL_LABEL_RECORD_SIZE]
    assert isinstance(jump, bytes) and isinstance(routine, bytes)
    assert rom[LEVEL_LABEL_HOOK.start:LEVEL_LABEL_HOOK.stop] == jump
    tiles = [*(CHAR_TO_BYTE[char] for char in word), *([FP_LEVEL_DASH_TILE] if len(word) == 6 else []), 0x00]
    record = bytes([0x20, 0x42, len(tiles), *tiles, 0xFF]).ljust(LEVEL_LABEL_RECORD_SIZE, b"\xff")
    assert rom[LEVEL_LABEL_RECORD:LEVEL_LABEL_RECORD + LEVEL_LABEL_RECORD_SIZE] == record
    routine_start = LEVEL_LABEL_RECORD + LEVEL_LABEL_RECORD_SIZE
    assert rom[routine_start:routine_start + len(routine)] == routine
    assert rom[LEVEL_RECORD:LEVEL_RECORD + LEVEL_RECORD_SIZE] == zora_rom()[LEVEL_RECORD:LEVEL_RECORD + LEVEL_RECORD_SIZE]


@pytest.mark.parametrize(("typed", "word"), list(CUSTOM_CASES.items()))
def test_custom_words(typed: str, word: str | None) -> None:
    """The page's text box and the command line: capitals, no outer spaces, at most 7 of the
    font's characters."""
    normalized = normalized_level_word(typed)
    assert (level_word_problem(normalized) is None) == (word is not None)
    if word is None:
        with pytest.raises(PlayerSettingError):
            player_settings_from_page({"levelWord": typed})
    else:
        assert player_settings_from_page({"levelWord": typed}).level_word == word


def test_settings_refuse_an_unnormalized_word() -> None:
    for word in ("lair", " LAIR", "LAIR "):
        with pytest.raises(PlayerSettingError):
            PlayerSettings(level_word=word)


# --- the page shares the rule ---------------------------------------------------------------------

def page_function(name: str) -> str:
    """A top-level function's source from web/zora-web.js."""
    match = re.search(rf"^function {name}\(.*?^}}\n", PAGE_SCRIPT.read_text(), re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group(0)


def test_the_page_gets_the_rule_from_the_metadata() -> None:
    metadata = json.loads(json.dumps(flag_form.metadata()))["levelWord"]
    assert metadata == {"default": DEFAULT_LEVEL_WORD, "choices": list(LEVEL_WORD_CHOICES),
                        "maxLength": LEVEL_WORD_MAX_LENGTH, "dashMaxLength": 6, "characters": LEVEL_WORD_CHARACTERS}
    page = PAGE_SCRIPT.read_text()
    assert "const rule = metadata.levelWord;" in page
    assert f'settings.levelWord = "{DEFAULT_LEVEL_WORD}";' in page


def test_the_pages_check_agrees_with_pythons() -> None:
    """The page's normalizing, checking and label functions, run in Node on the custom cases
    and every listed word, give Python's answers."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    rule = json.loads(json.dumps(flag_form.metadata()))["levelWord"]
    cases = [*CUSTOM_CASES, *LEVEL_WORD_CHOICES, "ABCDEF", "ABCDEFG", "AB CD"]
    script = "\n".join([page_function("normalizedLevelWord"), page_function("levelWordProblem"),
                        page_function("levelLabel"),
                        f"const rule = {json.dumps(rule)};",
                        f"const cases = {json.dumps(cases)};",
                        ("console.log(JSON.stringify(cases.map((typed) => { const word = normalizedLevelWord(typed);"
                         " const problem = levelWordProblem(word, rule);"
                         " return [word, problem, problem ? null : levelLabel(word, rule)]; })));")])
    answers = json.loads(subprocess.run([node, "-e", script], capture_output=True, text=True, check=True).stdout)
    expected = []
    for typed in cases:
        word = normalized_level_word(typed)
        problem = level_word_problem(word)
        expected.append([word, problem, None if problem else level_label(word)])
    assert answers == expected


# --- in the emulator ------------------------------------------------------------------------------

def prg1() -> bytes:
    if not PRG1_ROM_PATH.exists():
        pytest.skip(f"{PRG1_ROM_PATH.name} is not beside the PRG0 base")
    return PRG1_ROM_PATH.read_bytes()


def label_in_level_1(word: str, revision: str = "prg0") -> tuple[str, np.ndarray]:
    """Status bar row 2 as text, and the label's pixels, in level 1 with `word` written on the
    original game (PRG0, or PRG1: apply_player_settings writes it in PRG0's layout and moves it)."""
    from tests.emulator import Emulator
    base = vanilla() if revision == "prg0" else prg1()
    emu = Emulator(apply_player_settings(base, PlayerSettings(level_word=word)))
    emu.new_game()
    emu.walk_into_level_1()
    row = emu.nametable(LABEL_ROW, ROW_TILES)
    text = "".join("-" if tile == PRG0_DASH_TILE else BYTE_TO_CHAR.get(tile, "?") for tile in row)
    return text, emu.last_frame[LABEL_PIXELS].copy()


def expected_row(word: str) -> str:
    label = level_label(word)
    return (BLANK * LABEL_COLUMN + label).ljust(ROW_TILES)


@cache
def glyph_pixels() -> dict[str, np.ndarray]:
    """Each character's 8x8 pixels on the status bar, from labels of known words."""
    glyphs: dict[str, np.ndarray] = {}
    for word in ("ABCDE", "FGHIJ", "KLMNO", "PQRST", "UVWXY", "Z0123", "45678", "9,!'&", '."?-'):
        _, pixels = label_in_level_1(word)
        for index, char in enumerate(level_label(word)):
            glyphs.setdefault(char, pixels[:, 8 * index:8 * index + 8])
    return glyphs


def check_word(word: str, revision: str = "prg0") -> None:
    row, pixels = label_in_level_1(word, revision)
    assert row == expected_row(word), (word, row)
    if word == DEFAULT_LEVEL_WORD:
        return     # the default writes nothing: PRG0's record with ZORA's dash
    for index, char in enumerate(level_label(word)):
        assert (pixels[:, 8 * index:8 * index + 8] == glyph_pixels()[char]).all(), (word, char)


@pytest.mark.parametrize("word", QUICK_WORDS)
def test_the_label_shows_the_word(word: str) -> None:
    check_word(word)


@pytest.mark.parametrize("word", ["LEVEL", "TOWER", "CASTLE", "DUNGEON"])
def test_the_label_shows_the_word_on_prg1(word: str) -> None:
    check_word(word, "prg1")


@pytest.mark.parametrize("word", ["CASTLE", "DUNGEON"])
def test_a_long_label_stays_through_the_item_screen(word: str) -> None:
    """The item screen scrolls over the play area: the 8-tile label is still there after it
    opens and closes."""
    from tests.emulator import Button, Emulator
    emu = Emulator(apply_player_settings(vanilla(), PlayerSettings(level_word=word)))
    emu.new_game()
    emu.walk_into_level_1()
    before = emu.nametable(LABEL_ROW, ROW_TILES)
    emu.press(Button.START, after=120)
    emu.press(Button.START, after=120)
    assert emu.nametable(LABEL_ROW, ROW_TILES) == before
    assert emu.last_frame[LABEL_PIXELS].tolist() == label_in_level_1(word)[1].tolist()


@pytest.mark.slow
@pytest.mark.parametrize("word", [word for word in LEVEL_WORD_CHOICES if word not in QUICK_WORDS])
def test_every_listed_word_shows(word: str) -> None:
    check_word(word)


def test_the_glyphs_are_the_fonts_and_distinct() -> None:
    """Every character of the rule has its own glyph (no blank or repeated tile), so the pixel
    checks above tell characters apart."""
    glyphs = glyph_pixels()
    assert set(glyphs) == set(LEVEL_WORD_CHARACTERS) - {BLANK}
    seen = [pixels.tobytes() for pixels in glyphs.values()]
    assert len(set(seen)) == len(seen)
