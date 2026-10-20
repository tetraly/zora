"""Player settings (features-behavior.md FP-SET-01 to FP-SET-04, FP-HOT-01,
FP-RESET-01, FP-BEEP-01, FP-FIX-02; flags-behavior.md FL-SUP-05; FP-STATS-01).

A player setting is not part of the flag string and never changes generation,
the seed, the seed's code (FP-HASH-01) or the level encoding (FP-TOURNEY-01).
apply_player_settings writes them into a FINISHED ROM: after level encoding
and after the seed's code is stamped, outside both. Each setting has one
function, called from apply_player_settings; at the defaults a finished ZORA
ROM is unchanged (the statistics screen, FP-STATS-01, is off by default until
it is better tested; on writes only its own bytes).

Select swap, the death-warp mapping, reduce flashing, music off and the
statistics screen (asm/fp-stats-01/) use the patches assembled by asm/settings/ (docs/player-settings-patches.md);
player_settings_data.py is a verbatim copy of its output, which
tests/test_player_settings_wiring.py keeps equal. Select swap's off choice is
not assembled there: it is PRG0's own code at FP-HOT-01's four sites.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .base_rom import Piece, original_bytes, piece_bytes, piece_length
from .code_patch_data import PATCHES, SYMBOLS
from .layout import (
    CONSTERNATION_HINT_SLOTS,
    EXT_BANK1_ROM_START,
    EXT_HINT_CPU_BASE,
    FP_LEVEL_DASH_TILE,
    LEVEL_INFO_ADDRESS,
    LEVEL_INFO_SIZE,
    LEVEL_LABEL_RECORD,
    LEVEL_LABEL_RECORD_SIZE,
    LEVEL_NAME_OFFSET,
    LOW_HEALTH_BEEP_OPERAND_ADDRESS,
    NUM_QUOTES,
    QUOTE_DATA_ADDRESS,
    TITLE_ROW_LENGTH,
    TITLE_SEED_LABEL,
    TITLE_SEED_ROW_ADDRESS,
    hint_text_regions,
)
from .player_settings_data import SETTINGS
from .revision import Revision, back_to_revision, layout_of, moved_to_prg0_layout, prg1_offset
from .text_encoding import (
    BYTE_TO_CHAR,
    CHAR_TO_BYTE,
    QUOTE_BLANK,
    QUOTE_CHAR_MASK,
    QUOTE_END_BITS,
    QUOTE_LINE1_BIT,
    QUOTE_LINE2_BIT,
)

# NES palette values (FP-SET-02): six bits, and $0D ("blacker than black",
# never used by PRG0, can upset a TV's picture sync) is refused.
PALETTE_SIZE = 0x40
BLACKER_THAN_BLACK = 0x0D

# FP-SET-02: the tunic color of each ring state, in both copies PRG0 reads:
# the file-select copy (LinkColors) and the pickup copy (LinkColors_CommonCode,
# whose first entry is never read; the slot's value is written there too).
TUNIC_FILE_SELECT_COPY = 0xA297
TUNIC_PICKUP_COPY = 0x6BA5
TUNIC_SLOTS = 3                      # no ring, blue ring, red ring
# The map's position marker (docs/reports/minimap-marker.md): sprite tile $3E, whose 3x3 dot is
# color 1 of Link's palette, the tunic color. These tunic colors hide it on a map background
# (black in the levels, gray $00 on the overworld, room blue $12; CIE76 color distance under 25),
# or are too faint on black (under 30). With any of them in any slot, the dot is drawn in color 2, Link's skin ($27;
# $37 in level 3), which no ring or setting changes. The page shows a note from this same set
# (zora.flags.form.metadata).
MARKER_HIDING_COLORS = frozenset({
    0x0E, 0x0F, 0x1D, 0x1E, 0x1F, 0x2E, 0x2F, 0x3E, 0x3F,      # black
    0x00, 0x2D, 0x0C,                                           # on gray $00
    0x12, 0x13,                                                 # on room blue
    0x07, 0x08,                                                 # faint on black
})
# Tile $3E in CommonSpritePatterns (bank 2): its low plane, then its high plane 8 bytes on; the
# dot is the top three rows. Color 2 is low bit clear, high bit set in the dot's three columns.
MARKER_DOT_LOW_PLANE = 0x846F
MARKER_DOT_HIGH_PLANE = MARKER_DOT_LOW_PLANE + 8
MARKER_DOT_ROWS = 3
MARKER_DOT_COLUMNS_BITS = 0xE0
SKIN_DOT_LOW_PLANE = bytes(MARKER_DOT_ROWS)
SKIN_DOT_HIGH_PLANE = bytes([MARKER_DOT_COLUMNS_BITS] * MARKER_DOT_ROWS)
# FP-SET-03: the heart color, byte 8 of each of the ten level informations'
# palette records (the overworld's is k = 0).
HEART_COLOR_OFFSET = 8
LEVEL_INFORMATIONS = 10
# FP-BEEP-01: the operand ORed into Tune0Request ($40 requests the tone).
BEEP_REMOVED, BEEP_KEPT = 0x00, 0x40
# FP-HOT-01's patch: select swap off restores PRG0 at every site of it that
# runs (its slot in bank 2, the item screen's call and heading pointer, and
# the play mode's Select test). Its bank-5 and bank-7 slots stay, unreachable.
HOT_KEY_PATCH = "fp-hot-01"
SELECT_SWAP_OFF_SITES = (0x0B010, 0x140E5, 0x1A040, 0x1EC46)


# FP-LEVEL-01: the level label's word ("LEVEL-1" on a level's status bar, its only place in the
# game). LevelNumberTransferBuf is one 11-byte PPU transfer record in bank 6's data block, which
# power-on copies to RAM $67F0: the address ($2042, row 2 column 2), the tile count, the tiles,
# $FF. InitMode3_Sub7 stores the level's number at its offset 9 (the seventh tile), and the next
# table follows the record, so it holds at most 7 tiles. A shorter label keeps it left-aligned:
# the record gets fewer tiles and the number store's operand moves with them (docs/rom-map.md
# "Other fixed-address writes"). FP-LEVEL-02 (asm/fp-level-02/) gives the label 8 tiles: a word
# of up to 6 characters keeps the dash ("CASTLE-1") and a 7-character word drops it
# ("DUNGEON1"). Its patch is written only for a label text of 7 characters (the word and the
# dash), which the 7-tile record cannot hold; every shorter label keeps PRG0's record and code.
DEFAULT_LEVEL_WORD = "LEVEL"
LEVEL_WORD_CHOICES = (
    "LEVEL", "BOARD", "ABODE", "LAIR", "SECTOR", "AREA", "PALACE", "VAULT", "CRYPT", "TOMB", "KEEP",
    "MAZE", "TOWER", "TEMPLE", "SHRINE", "CASTLE", "FORT", "HALL", "DEN", "NEST", "HOLD", "STAGE",
    "WORLD", "ZONE", "FLOOR", "RUIN", "PIT", "CAVE",
)
LEVEL_WORD_MAX_LENGTH = 7
LEVEL_WORD_DASH_MAX_LENGTH = 6
SHORT_LABEL_TEXT_MAX_LENGTH = 6           # PRG0's record: the label text and the number in 7 tiles
# The font's characters (zora/rom/text_encoding.py) apart from "~", the text boxes' padding tile,
# which shows as a blank.
TEXT_PAD_CHARACTER = "~"
LEVEL_WORD_CHARACTERS = "".join(char for char in CHAR_TO_BYTE if char != TEXT_PAD_CHARACTER)
LEVEL_RECORD_HEADER = 3                                   # PPU address high, low, tile count
LEVEL_RECORD = LEVEL_NAME_OFFSET - LEVEL_RECORD_HEADER    # file 0x19D14
LEVEL_RECORD_SIZE = 11
LEVEL_RECORD_PPU_ADDRESS = (0x20, 0x42)
LEVEL_RECORD_RAM = 0x681C                                 # where power-on copies the record
LEVEL_NUMBER_PLACEHOLDER = 0x00                           # PRG0's; InitMode3_Sub7 overwrites it
TRANSFER_END = 0xFF
# The hints name levels the same way ("THE RAFT RESTS IN LEVEL-3.", "LEVEL-3 LIES BY THE COAST."),
# and hint text is written at generation, before the player settings. The setting rewrites each
# hint line holding a label in place: the label replaced, the line centered again on the box's
# width, then padded at its end with the blank padding tile to its old length, so every text
# keeps its length and place and the pointers stay. A label is at most one character longer than
# "LEVEL-3" ("CASTLE-3", "DUNGEON3"; FP-LEVEL-02), which takes a centering pad tile. A line
# without one (its text 23 or 24 characters) has its text wrapped again in the text's length, or,
# with no tile to spare there, at its own new length in the regions' free space, its pointer
# moved with it. PRG0's own texts and the community pool never say "LEVEL-".
HINT_LEVEL_LABEL = re.compile(r"(?<![A-Z0-9])LEVEL-([1-9])(?![0-9])")
HINT_LINE_WIDTH = 24                      # hint_text.LINE_WIDTH: hint lines are centered on it
HINT_MAX_LINES = 3                        # hint_text.MAX_LINES: the text box's lines
POINTER_BANK_BIT = 0x80                   # a pointer's high byte in bank 1 ($8000-$BFFF)
# InitMode3_Sub7's `STA LevelNumberTransferBuf+9` (8D 25 68 at 0x1703F): its operand's low byte.
LEVEL_NUMBER_STORE_OPERAND = 0x17040


# FP-ROAR-01's boss-sound label, " -ROAR-  " in -LIFE-'s place while a dungeon room's boss sound
# plays: its four letters are a player setting (testers' request). The word, a listed or custom
# one of exactly four of the font's characters, or Random: a listed word drawn from the seed
# number alone, on a stream of its own (a hash of the number), so the same seed shows the same
# word and nothing else moves. Player settings apply to the finished ROM, so Random reads the
# number from the title screen's seed row (FP-TITLE-01).
DEFAULT_BOSS_SOUND_WORD = "ROAR"
RANDOM_BOSS_SOUND_WORD = "RANDOM"
BOSS_SOUND_WORDS = (
    "RAWR", "MEOW", "WOOF", "AWOO", "OINK", "WEEF", "HONK", "AAAA", "GOAL", "OHAI", "WAAH", "HOWL",
    "HISS", "PURR", "BARK", "HOOT", "BAAA", "GRRR", "BONK", "EEEK", "OOPS", "YAAY",
)
BOSS_SOUND_WORD_LENGTH = 4
BOSS_SOUND_WORD_CHARACTERS = LEVEL_WORD_CHARACTERS          # the same font
BOSS_SOUND_WORD_ADDRESS = SYMBOLS["ZORA_B5_BossSoundWord"]  # fp-roar-01's second label record
BOSS_SOUND_WORD_STREAM = b"zora boss-sound word:"


class PlayerSettingError(ValueError):
    """A player setting outside its choices."""


class SelectSwap(Enum):
    """FP-HOT-01."""
    OFF = "off"                  # PRG0: Select pauses
    SWAP_ONLY = "swap_only"
    TOGGLE = "toggle"


class LowHealthBeep(Enum):
    """FP-BEEP-01."""
    REMOVED = "removed"
    KEPT = "kept"                # PRG0


class DeathWarp(Enum):
    """FP-RESET-01: the combination that ends the game from the item screen."""
    CONTROLLER2_UP_A = "controller2_up_a"          # PRG0
    CONTROLLER1_UP_A = "controller1_up_a"
    CONTROLLER1_UP_SELECT = "controller1_up_select"


class Music(Enum):
    """FP-SET-04."""
    ON = "on"
    OFF = "off"


@dataclass(frozen=True)
class PlayerSettings:
    """The seven settings the MVP offers (FL-SUP-05), the level label's word (FP-LEVEL-01) and
    the boss-sound label's word (FP-ROAR-01), and testers' requests, at their defaults. The
    statistics screen (FP-STATS-01) is no longer a setting: every ROM has it (write_player_settings)."""
    select_swap: SelectSwap = SelectSwap.TOGGLE
    low_health_beep: LowHealthBeep = LowHealthBeep.REMOVED
    death_warp: DeathWarp = DeathWarp.CONTROLLER1_UP_A
    reduce_flashing: bool = False
    # green tunic (no ring), blue ring, red ring: PRG0's
    tunic_colors: tuple[int, int, int] = (0x29, 0x32, 0x16)
    heart_color: int = 0x16                        # PRG0's
    music: Music = Music.ON
    level_word: str = DEFAULT_LEVEL_WORD            # FP-LEVEL-01
    boss_sound_word: str = DEFAULT_BOSS_SOUND_WORD  # FP-ROAR-01's label: a word or RANDOM

    def __post_init__(self) -> None:
        check_level_word(self.level_word)
        check_boss_sound_word(self.boss_sound_word)
        if len(self.tunic_colors) != TUNIC_SLOTS:
            raise PlayerSettingError(f"tunic colors: three values, not {len(self.tunic_colors)}")
        for name, value in (("green tunic", self.tunic_colors[0]), ("blue ring", self.tunic_colors[1]),
                            ("red ring", self.tunic_colors[2]), ("heart color", self.heart_color)):
            check_palette_value(name, value)


def check_palette_value(name: str, value: int) -> None:
    """FP-SET-02 and FP-SET-03: $00-$3F, except $0D."""
    if not isinstance(value, int) or not 0 <= value < PALETTE_SIZE:
        raise PlayerSettingError(f"{name}: {value!r} is not an NES palette value ($00-$3F)")
    if value == BLACKER_THAN_BLACK:
        raise PlayerSettingError(f"{name}: $0D is not allowed (blacker than black)")


def normalized_level_word(text: str) -> str:
    """The word as the player typed it, in the label's form: capitals, no outer spaces."""
    return text.strip().upper()


def level_word_problem(word: str) -> str | None:
    """Why `word` (normalized) cannot be the level label's word, or None. The page applies the
    same rule (web/zora-web.js levelWordProblem, from metadata.levelWord)."""
    if not word:
        return "type a word"
    if len(word) > LEVEL_WORD_MAX_LENGTH:
        return f"at most {LEVEL_WORD_MAX_LENGTH} characters"
    unknown = sorted({char for char in word if char not in LEVEL_WORD_CHARACTERS})
    if unknown:
        return f"the game's font has no {' '.join(unknown)}"
    return None


def check_level_word(word: object) -> None:
    if not isinstance(word, str) or word != normalized_level_word(word):
        raise PlayerSettingError(f"level word: {word!r} is not in capitals without outer spaces")
    if (problem := level_word_problem(word)) is not None:
        raise PlayerSettingError(f"level word {word!r}: {problem}")


def boss_sound_word_problem(word: str) -> str | None:
    """Why `word` (normalized) cannot be the boss-sound label's word, or None. RANDOM is the
    Random choice. The page applies the same rule (web/zora-web.js bossSoundWordProblem)."""
    if word == RANDOM_BOSS_SOUND_WORD:
        return None
    if len(word) != BOSS_SOUND_WORD_LENGTH:
        return f"exactly {BOSS_SOUND_WORD_LENGTH} characters"
    unknown = sorted({char for char in word if char not in BOSS_SOUND_WORD_CHARACTERS})
    if unknown:
        return f"the game's font has no {' '.join(unknown)}"
    return None


def normalized_boss_sound_word(text: str) -> str:
    """The word as the player typed it: capitals, no outer spaces (a space inside counts)."""
    return text.strip().upper()


def check_boss_sound_word(word: object) -> None:
    if not isinstance(word, str) or word != normalized_boss_sound_word(word):
        raise PlayerSettingError(f"boss-sound word: {word!r} is not in capitals without outer spaces")
    if (problem := boss_sound_word_problem(word)) is not None:
        raise PlayerSettingError(f"boss-sound word {word!r}: {problem}")


def random_boss_sound_word(seed: int) -> str:
    """Random's word for a seed number: a listed word, by a hash of the number alone."""
    digest = hashlib.sha256(BOSS_SOUND_WORD_STREAM + str(seed).encode()).digest()
    return BOSS_SOUND_WORDS[int.from_bytes(digest[:8], "big") % len(BOSS_SOUND_WORDS)]


def title_seed_number(rom: bytes | bytearray) -> int:
    """The seed number the title screen shows (FP-TITLE-01: SEED, then the number right-aligned).
    The row is 24 tiles and shows at most 19 digits, a 20-digit seed's first 19 (since 2026-10-17;
    before, its 20 digits touched the label: SEED14089154938208861744, which this still reads). So
    Random's word for a seed of 10^19 or more is the shown number's. Read in PRG0's layout (a ROM
    made from PRG1 has the row 139 bytes on; revision.layout_of)."""
    seed_row = TITLE_SEED_ROW_ADDRESS
    if layout_of(bytes(rom[:TITLE_SEED_ROW_ADDRESS + TITLE_ROW_LENGTH + 0x100])) is Revision.PRG1:
        seed_row = prg1_offset(TITLE_SEED_ROW_ADDRESS)
    row = "".join(BYTE_TO_CHAR.get(tile, "?") for tile in rom[seed_row:
                                                                 seed_row + TITLE_ROW_LENGTH])
    label, number = row[:len(TITLE_SEED_LABEL)], row[len(TITLE_SEED_LABEL):].strip()
    if label != TITLE_SEED_LABEL or not number.isdigit():
        raise PlayerSettingError("Random boss-sound word: this ROM's title screen shows no seed number")
    return int(number)


def level_label(word: str) -> str:
    """How the status bar shows level 1's label with this word."""
    return f"{word}{'-' if len(word) <= LEVEL_WORD_DASH_MAX_LENGTH else ''}1"


def level_label_is_long(word: str) -> bool:
    """FP-LEVEL-02: does the label text (the word, and the dash for a word of up to 6
    characters) take 7 tiles, so the number makes 8 and PRG0's record cannot hold it?"""
    return len(level_label(word)) - 1 > SHORT_LABEL_TEXT_MAX_LENGTH


# The spec's defaults: what a finished ROM gets when the player chooses nothing.
DEFAULT_PLAYER_SETTINGS = PlayerSettings()


def apply_player_settings(rom: bytes, settings: PlayerSettings, coop: bool = False) -> bytes:
    """A finished ROM with the player settings written; nothing else changes. A ROM made from
    PRG1 is written in PRG0's layout and moved back (revision.layout_of). coop: as in
    write_player_settings."""
    if layout_of(rom) is Revision.PRG1:
        image = moved_to_prg0_layout(rom)
        return back_to_revision(rom, Revision.PRG1, image, write_player_settings(image, settings, coop))
    return write_player_settings(rom, settings, coop)


def write_player_settings(rom: bytes, settings: PlayerSettings, coop: bool = False) -> bytes:
    """apply_player_settings on an image in PRG0's layout (the final steps' image), with the
    statistics screen, which every ROM has (owner, 2026-10-17; it was a setting, off by default,
    up to 2.0 beta 6).

    coop: the hook for the future co-op mode, which nothing sets yet. z1rr-coop's patch uses the
    statistics screen's SRAM page ($7F00-$7FFF; docs/rom-map.md "Reserved for z1rr-coop"), so a
    co-op ROM leaves the screen out (statistics_screen with on=False: the ROM without it)."""
    out = bytearray(rom)
    select_swap(out, settings.select_swap)
    low_health_beep(out, settings.low_health_beep)
    death_warp(out, settings.death_warp)
    reduce_flashing(out, settings.reduce_flashing)
    tunic_colors(out, settings.tunic_colors)
    heart_color(out, settings.heart_color)
    music(out, settings.music)
    level_word(out, settings.level_word)
    boss_sound_word(out, settings.boss_sound_word)
    statistics_screen(out, on=not coop)
    return bytes(out)


def _write(rom: bytearray, runs: tuple[tuple[int, Piece], ...]) -> None:
    for offset, piece in runs:
        run = piece_bytes(piece)
        rom[offset:offset + len(run)] = run


def _hot_key_extent(site: int) -> int:
    """How many bytes FP-HOT-01 writes from `site` on, without a gap."""
    lengths = {offset: piece_length(piece) for offset, piece in PATCHES[HOT_KEY_PATCH]}
    end = site
    while end in lengths:
        end += lengths[end]
    return end - site


def select_swap_off_runs() -> tuple[tuple[int, bytes], ...]:
    """PRG0's bytes at FP-HOT-01's running sites, read from the player's ROM."""
    return tuple((site, original_bytes(site, _hot_key_extent(site))) for site in SELECT_SWAP_OFF_SITES)


def select_swap(rom: bytearray, choice: SelectSwap) -> None:
    """FP-HOT-01: off (PRG0), swap-only or toggle."""
    if choice is SelectSwap.OFF:
        _write(rom, select_swap_off_runs())
    else:
        _write(rom, SETTINGS["select_swap"][choice.value])


def low_health_beep(rom: bytearray, choice: LowHealthBeep) -> None:
    """FP-BEEP-01: the tone request's operand."""
    rom[LOW_HEALTH_BEEP_OPERAND_ADDRESS] = BEEP_REMOVED if choice is LowHealthBeep.REMOVED else BEEP_KEPT


def death_warp(rom: bytearray, choice: DeathWarp) -> None:
    """FP-RESET-01: the death-warp combination."""
    _write(rom, SETTINGS["death_warp"][choice.value])


def reduce_flashing(rom: bytearray, on: bool) -> None:
    """FP-FIX-02's reduce-flashing setting: the four flashes."""
    _write(rom, SETTINGS["reduce_flashing"]["on" if on else "off"])


def tunic_colors(rom: bytearray, colors: tuple[int, int, int]) -> None:
    """FP-SET-02: each slot's value in both copies; with a color that hides the map marker in
    any slot, the marker in Link's skin color (owner ruling, docs/reports/minimap-marker.md)."""
    for copy in (TUNIC_FILE_SELECT_COPY, TUNIC_PICKUP_COPY):
        rom[copy:copy + len(colors)] = bytes(colors)
    if hides_the_map_marker(colors):
        rom[MARKER_DOT_LOW_PLANE:MARKER_DOT_LOW_PLANE + MARKER_DOT_ROWS] = SKIN_DOT_LOW_PLANE
        rom[MARKER_DOT_HIGH_PLANE:MARKER_DOT_HIGH_PLANE + MARKER_DOT_ROWS] = SKIN_DOT_HIGH_PLANE


def hides_the_map_marker(colors: tuple[int, int, int]) -> bool:
    """Whether any ring state's tunic color would hide the marker drawn in it."""
    return any(color in MARKER_HIDING_COLORS for color in colors)


def heart_color(rom: bytearray, color: int) -> None:
    """FP-SET-03: all ten level informations' heart color."""
    for level_information in range(LEVEL_INFORMATIONS):
        rom[LEVEL_INFO_ADDRESS + level_information * LEVEL_INFO_SIZE + HEART_COLOR_OFFSET] = color


def music(rom: bytearray, choice: Music) -> None:
    """FP-SET-04: on, or the three area songs never start."""
    _write(rom, SETTINGS["music"][choice.value])


def level_word(rom: bytearray, word: str) -> None:
    """FP-LEVEL-01: the label's word. FP-LEVEL-02's choice comes first: the 8-tile patch for a
    long label, else PRG0's code and free space (what ZORA's output holds; it restores the number
    store's operand, so the short record's operand is written after it). The default then writes
    nothing more (PRG0's word, and the dash generation wrote); another word rewrites the hints'
    level labels and its record: FP-LEVEL-02's, or PRG0's record and the number store's operand."""
    long = level_label_is_long(word)
    _write(rom, SETTINGS["level_label"]["long" if long else "short"])
    if word == DEFAULT_LEVEL_WORD:
        return
    level_word_in_hints(rom, word)
    tiles = [CHAR_TO_BYTE[char] for char in word]
    if len(word) <= LEVEL_WORD_DASH_MAX_LENGTH:
        tiles.append(FP_LEVEL_DASH_TILE)
    tiles.append(LEVEL_NUMBER_PLACEHOLDER)
    record = bytes([*LEVEL_RECORD_PPU_ADDRESS, len(tiles), *tiles, TRANSFER_END])
    if long:
        # The patch's routine stores the number itself; 0x17040 is now its JMP's operand.
        rom[LEVEL_LABEL_RECORD:LEVEL_LABEL_RECORD + LEVEL_LABEL_RECORD_SIZE] = record.ljust(
            LEVEL_LABEL_RECORD_SIZE, bytes([TRANSFER_END]))
        return
    rom[LEVEL_RECORD:LEVEL_RECORD + LEVEL_RECORD_SIZE] = record.ljust(LEVEL_RECORD_SIZE, bytes([TRANSFER_END]))
    number_offset = LEVEL_RECORD_HEADER + len(tiles) - 1
    rom[LEVEL_NUMBER_STORE_OPERAND] = (LEVEL_RECORD_RAM + number_offset) & 0xFF


def boss_sound_word(rom: bytearray, word: str) -> None:
    """FP-ROAR-01's label word: ROAR, fp-roar-01's own, writes nothing; Random draws a listed word
    for the title screen's seed number."""
    if word == RANDOM_BOSS_SOUND_WORD:
        word = random_boss_sound_word(title_seed_number(rom))
    if word == DEFAULT_BOSS_SOUND_WORD:
        return
    rom[BOSS_SOUND_WORD_ADDRESS:BOSS_SOUND_WORD_ADDRESS + BOSS_SOUND_WORD_LENGTH] = bytes(
        CHAR_TO_BYTE[char] for char in word)


def statistics_screen(rom: bytearray, on: bool) -> None:
    """FP-STATS-01: the end-of-game statistics screen (asm/fp-stats-01/). Off writes the bytes the
    ROM has without it (free space and the game's own instructions)."""
    _write(rom, SETTINGS["statistics_screen"]["on" if on else "off"])


def relabel_hint_line(line: str, word: str, dash: bool = True) -> str | None:
    """One hint line (its characters, centering pad included) with each level label in `word`'s
    form (dash False: without the dash), centered again and padded at its end to the line's old
    length; None when it no longer fits that length."""
    original = line.lstrip(TEXT_PAD_CHARACTER)
    text = HINT_LEVEL_LABEL.sub(lambda label: hint_label(word, label.group(1), dash), original)
    if text == original:
        return line
    if len(text) > len(line):
        return None
    pad = min((HINT_LINE_WIDTH - len(text)) // 2, len(line) - len(text))
    return (TEXT_PAD_CHARACTER * pad + text).ljust(len(line), TEXT_PAD_CHARACTER)


def hint_label(word: str, number: str, dash: bool = True) -> str:
    """A level's label in a hint: as the status bar shows it, or (dash False) without the dash."""
    return f"{word}{'-' if dash and len(word) <= LEVEL_WORD_DASH_MAX_LENGTH else ''}{number}"


def rewrapped_hint_lines(lines: list[str], word: str, length: int | None) -> list[str] | None:
    """A hint whose relabeled line no longer fits its own length (an 8-character label in a line
    of 23 or 24 characters, FP-LEVEL-02): its words with the word's labels wrapped again on the
    box's width. With `length`, into at most as many lines, each centered as far as that length
    allows and the spare length padding the lines' ends, the lines adding up to `length`; None when
    the words need more lines or more room. Without it, into at most the box's lines, centered."""
    words = [HINT_LEVEL_LABEL.sub(lambda label: hint_label(word, label.group(1)), text_word)
             for text_word in " ".join(line.strip(TEXT_PAD_CHARACTER) for line in lines).split(" ")]
    texts = [""]
    for text_word in words:                 # a label is one word, even when `word` holds a space
        joined = f"{texts[-1]} {text_word}" if texts[-1] else text_word
        if len(joined) <= HINT_LINE_WIDTH:
            texts[-1] = joined
        else:
            texts.append(text_word)
    most_lines = len(lines) if length is not None else HINT_MAX_LINES
    if len(texts) > most_lines or any(len(text) > HINT_LINE_WIDTH for text in texts):
        return None
    if length is None:
        return [TEXT_PAD_CHARACTER * ((HINT_LINE_WIDTH - len(text)) // 2) + text for text in texts]
    spare = length - sum(len(text) for text in texts)
    if spare < 0:
        return None
    rewrapped = []
    for text in texts:
        pad = min((HINT_LINE_WIDTH - len(text)) // 2, spare)
        spare -= pad
        rewrapped.append(TEXT_PAD_CHARACTER * pad + text)
    for index, line in enumerate(rewrapped):
        extra = min(HINT_LINE_WIDTH - len(line), spare)
        spare -= extra
        rewrapped[index] = line + TEXT_PAD_CHARACTER * extra
    return rewrapped if spare == 0 else None


def relabel_hint_text(body: bytes, word: str) -> bytes:
    """An encoded hint text (lines whose last byte carries the line or end bits) with its level
    labels in `word`'s form. Each line is relabeled in place, keeping its bits on its last byte.
    When a line has no room for a longer label (FP-LEVEL-02's 8 characters), the whole text is
    wrapped again in its own length (rewrapped_hint_lines); failing that (about 1 template in 20
    has no spare tile), at the length its centered lines take, longer than `body`: the caller
    moves it (level_word_in_hints)."""
    spans: list[tuple[int, int]] = []
    start = 0
    for end, byte in enumerate(body):
        if not byte & QUOTE_END_BITS:
            continue
        spans.append((start, end + 1))
        if byte & QUOTE_END_BITS == QUOTE_END_BITS:
            break
        start = end + 1
    lines = ["".join(BYTE_TO_CHAR.get(tile & QUOTE_CHAR_MASK, "?") for tile in body[first:last])
             for first, last in spans]
    relabeled = [relabel_hint_line(line, word) for line in lines]
    if None in relabeled:
        rewrapped = rewrapped_hint_lines(lines, word, len(body)) or rewrapped_hint_lines(lines, word, None)
        assert rewrapped is not None, (lines, word)
        return encoded_hint_lines(rewrapped)
    out = bytearray(body)
    for (first, last), line, new in zip(spans, lines, relabeled, strict=True):
        if new is not None and new != line:
            out[first:last] = bytes(CHAR_TO_BYTE[char] for char in new)
            out[last - 1] |= body[last - 1] & QUOTE_END_BITS
    return bytes(out)


def encoded_hint_lines(lines: list[str]) -> bytes:
    """Lines as an encoded hint text (hint_text.encode_text's bits: line 1's end, line 2's end,
    the text's end)."""
    out = bytearray()
    for index, line in enumerate(lines):
        out += bytes(CHAR_TO_BYTE[char] for char in line)
        last = index == len(lines) - 1
        out[-1] |= QUOTE_END_BITS if last else QUOTE_LINE1_BIT if index == 0 else QUOTE_LINE2_BIT
    return bytes(out)


def hint_pointer_count(rom: bytes | bytearray) -> int:
    """45 pointers with Consternation's hint text (their high bytes all in bank 1), else PRG0's 38."""
    extra = range(NUM_QUOTES, CONSTERNATION_HINT_SLOTS)
    return CONSTERNATION_HINT_SLOTS if all(rom[QUOTE_DATA_ADDRESS + 2 * slot + 1] & POINTER_BANK_BIT
                                           for slot in extra) else NUM_QUOTES


def hint_text_offset(rom: bytes | bytearray, slot: int) -> int:
    pointer = rom[QUOTE_DATA_ADDRESS + 2 * slot] | rom[QUOTE_DATA_ADDRESS + 2 * slot + 1] << 8
    return EXT_BANK1_ROM_START + pointer - EXT_HINT_CPU_BASE


def hint_text_offsets(rom: bytes | bytearray) -> list[int]:
    """The file offsets of the person and hint texts the pointer table addresses inside the hint
    text regions (hint_pointer_count's pointers)."""
    count = hint_pointer_count(rom)
    regions = hint_text_regions(count)
    return sorted({offset for slot in range(count) if any(start <= (offset := hint_text_offset(rom, slot)) < end
                                                          for start, end in regions)})


def text_body(rom: bytes | bytearray, offset: int) -> bytes:
    """The encoded text at `offset`, through its end byte (or the blank sentinel)."""
    end = offset
    while rom[end] != QUOTE_BLANK and rom[end] & QUOTE_END_BITS != QUOTE_END_BITS:
        end += 1
    return bytes(rom[offset:end + 1])


def level_word_in_hints(rom: bytearray, word: str) -> None:
    """The hints' level labels in `word`'s form, each text rewritten in place; a text that grew
    (relabel_hint_text) goes to the hint text regions' free space after every text, and each
    pointer to it follows (the regions hold about 3,000 bytes, the texts under 2,000)."""
    count = hint_pointer_count(rom)
    offsets = hint_text_offsets(rom)
    bodies = {offset: text_body(rom, offset) for offset in offsets}
    free = [(max([start, *(offset + len(bodies[offset]) for offset in offsets if start <= offset < end)]), end)
            for start, end in hint_text_regions(count)]
    moved: dict[int, int] = {}
    for offset, body in bodies.items():
        relabeled = relabel_hint_text(body, word)
        if len(relabeled) == len(body):
            rom[offset:offset + len(body)] = relabeled
            continue
        region = next(index for index, (start, end) in enumerate(free) if start + len(relabeled) <= end)
        start, end = free[region]
        rom[start:start + len(relabeled)] = relabeled
        moved[offset] = start
        free[region] = (start + len(relabeled), end)
    for slot in range(count):
        if (new := moved.get(hint_text_offset(rom, slot))) is not None:
            pointer = new - EXT_BANK1_ROM_START + EXT_HINT_CPU_BASE
            rom[QUOTE_DATA_ADDRESS + 2 * slot:QUOTE_DATA_ADDRESS + 2 * slot + 2] = pointer.to_bytes(2, "little")


def written_offsets(settings_field: str) -> set[int]:
    """Every file offset a setting's function may write, whatever its choice."""
    if settings_field == "select_swap":
        runs = [*select_swap_off_runs(), *(run for runs in SETTINGS["select_swap"].values() for run in runs)]
    elif settings_field == "low_health_beep":
        return {LOW_HEALTH_BEEP_OPERAND_ADDRESS}
    elif settings_field == "tunic_colors":
        return ({copy + slot for copy in (TUNIC_FILE_SELECT_COPY, TUNIC_PICKUP_COPY) for slot in range(TUNIC_SLOTS)}
                | {plane + row for plane in (MARKER_DOT_LOW_PLANE, MARKER_DOT_HIGH_PLANE)
                   for row in range(MARKER_DOT_ROWS)})
    elif settings_field == "boss_sound_word":
        return set(range(BOSS_SOUND_WORD_ADDRESS, BOSS_SOUND_WORD_ADDRESS + BOSS_SOUND_WORD_LENGTH))
    elif settings_field == "level_word":
        hint_regions = {offset for count in (NUM_QUOTES, CONSTERNATION_HINT_SLOTS)
                        for start, end in hint_text_regions(count) for offset in range(start, end)}
        label_runs = [run for runs in SETTINGS["level_label"].values() for run in runs]
        pointers = range(QUOTE_DATA_ADDRESS, QUOTE_DATA_ADDRESS + 2 * CONSTERNATION_HINT_SLOTS)
        return {*range(LEVEL_RECORD, LEVEL_RECORD + LEVEL_RECORD_SIZE), LEVEL_NUMBER_STORE_OPERAND, *hint_regions,
                *pointers,
                *range(LEVEL_LABEL_RECORD, LEVEL_LABEL_RECORD + LEVEL_LABEL_RECORD_SIZE),
                *(offset + i for offset, run in label_runs for i in range(piece_length(run)))}
    elif settings_field == "heart_color":
        return {LEVEL_INFO_ADDRESS + k * LEVEL_INFO_SIZE + HEART_COLOR_OFFSET for k in range(LEVEL_INFORMATIONS)}
    else:
        runs = [run for runs in SETTINGS[settings_field].values() for run in runs]
    return {offset + i for offset, run in runs for i in range(piece_length(run))}


SETTING_CHOICES: dict[str, type[Enum]] = {"select_swap": SelectSwap, "low_health_beep": LowHealthBeep,
                                          "death_warp": DeathWarp, "music": Music}
SWITCH_WORDS = {"off": False, "on": True}
# Settings that are gone, by their command-line, YAML and page names: still accepted, with any value,
# and ignored, so what named them before still reads (the statistics screen, always on since
# 2026-10-17).
RETIRED_SETTINGS = frozenset({"statistics_screen"})
RETIRED_PAGE_SETTINGS = frozenset({"statisticsScreen"})


def parse_player_settings(pairs: list[str]) -> PlayerSettings:
    """Command-line settings, each `name=value` with PlayerSettings' field names: a choice by
    its value (music=off), reduce_flashing=on, heart_color=0x21, tunic_colors=0x29,0x32,0x16,
    level_word=PALACE (any case), boss_sound_word=MEOW or boss_sound_word=random. A retired
    setting (RETIRED_SETTINGS) is ignored, whatever its value."""
    chosen: dict[str, object] = {}
    for pair in pairs:
        name, _, text = pair.partition("=")
        try:
            if name in RETIRED_SETTINGS:
                continue
            if name in SETTING_CHOICES:
                chosen[name] = SETTING_CHOICES[name](text)
            elif name == "reduce_flashing":
                chosen[name] = SWITCH_WORDS[text]
            elif name == "heart_color":
                chosen[name] = int(text, 0)
            elif name == "tunic_colors":
                chosen[name] = tuple(int(value, 0) for value in text.split(","))
            elif name == "level_word":
                chosen[name] = normalized_level_word(text)
            elif name == "boss_sound_word":
                chosen[name] = normalized_boss_sound_word(text)
            else:
                raise PlayerSettingError(f"unknown player setting {name!r}")
        except (KeyError, ValueError) as exc:
            if isinstance(exc, PlayerSettingError):
                raise
            raise PlayerSettingError(f"{pair!r}: not a choice of {name}") from exc
    return PlayerSettings(**chosen)  # type: ignore[arg-type]


# The page's Cosmetic tab (web/zora-web.js PLAYER_CHOICES and PLAYER_COLORS): its keys and
# choice values, as PlayerSettings fields. The page's names are also Archipelago's (a recipe's
# playerSettings, zora/archipelago.py).
PAGE_CHOICES: dict[str, tuple[str, dict[str, Any]]] = {
    "selectButton": ("select_swap", {"off": SelectSwap.OFF, "swap": SelectSwap.SWAP_ONLY,
                                     "toggle": SelectSwap.TOGGLE}),
    "lowHealthBeep": ("low_health_beep", {"removed": LowHealthBeep.REMOVED, "kept": LowHealthBeep.KEPT}),
    "deathWarp": ("death_warp", {"p2-up-a": DeathWarp.CONTROLLER2_UP_A, "p1-up-a": DeathWarp.CONTROLLER1_UP_A,
                                 "p1-up-select": DeathWarp.CONTROLLER1_UP_SELECT}),
    "reduceFlashing": ("reduce_flashing", {"off": False, "on": True}),
    "music": ("music", {"on": Music.ON, "off": Music.OFF}),
}
PAGE_TUNIC_SLOTS = ("greenTunic", "blueRingTunic", "redRingTunic")
PAGE_HEART_SLOT = "heart"
PAGE_LEVEL_WORD = "levelWord"
PAGE_BOSS_SOUND_WORD = "bossSoundWord"


def player_settings_from_page(values: Mapping[str, Any]) -> PlayerSettings:
    """The page's playerSettings object as PlayerSettings. A key it leaves out
    takes the default; an unknown choice or a color that is not an NES palette
    value (or is $0D) is refused with PlayerSettingError, never replaced. Other keys,
    RETIRED_PAGE_SETTINGS among them, are not read."""
    defaults = PlayerSettings()
    chosen: dict[str, Any] = {}
    for key, (field, choices) in PAGE_CHOICES.items():
        if key in values:
            if not isinstance(values[key], str) or values[key] not in choices:
                raise PlayerSettingError(f"{key}: unknown choice {values[key]!r}")
            chosen[field] = choices[values[key]]
    tunics = tuple(values.get(slot, default)
                   for slot, default in zip(PAGE_TUNIC_SLOTS, defaults.tunic_colors, strict=True))
    if PAGE_LEVEL_WORD in values:
        if not isinstance(values[PAGE_LEVEL_WORD], str):
            raise PlayerSettingError(f"{PAGE_LEVEL_WORD}: {values[PAGE_LEVEL_WORD]!r} is not text")
        chosen["level_word"] = normalized_level_word(values[PAGE_LEVEL_WORD])
    if PAGE_BOSS_SOUND_WORD in values:
        if not isinstance(values[PAGE_BOSS_SOUND_WORD], str):
            raise PlayerSettingError(f"{PAGE_BOSS_SOUND_WORD}: {values[PAGE_BOSS_SOUND_WORD]!r} is not text")
        chosen["boss_sound_word"] = normalized_boss_sound_word(values[PAGE_BOSS_SOUND_WORD])
    return PlayerSettings(tunic_colors=tunics, heart_color=values.get(PAGE_HEART_SLOT, defaults.heart_color),
                          **chosen)
