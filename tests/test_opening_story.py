"""ZORA's opening story and the story's closing note (zora/rom/opening_story.py; owner prompt 544
and its amendment):

- the page holds the owner's eleven lines, laid out as PRG0's (the paragraph justified to both
  edges but its last line, the closing two lines centered); lines 10 and 11 state level 9's requirement,
  the gate its person's text names (every Level 9 Entry value, C08 = 0 to 12, and the
  level-4-sword entrance), in 24 columns, with the level word;
- NINTENDO is red, ZELDA RANDOMIZER green, ZORA blue and the thing to find red; the title row,
  the frame and the palettes keep PRG0's;
- the note's third line is ZORA.GG, and only the note's tiles change; its O, R, A and period are
  the note's own and Z and G are in its own colors, so a graphics pack's note carries through, and
  a note drawn otherwise is left alone;
- none of it is z1rr-coop's or another patch's."""
from functools import cache
from itertools import combinations

import pytest

from tests.needs import needs_base_rom
from tests.test_coop_reserved import hits
from zora.flags import zora_flags
from zora.flags.codec import decode, encode
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import Built, build, finish, plan
from zora.generate.steps.feature_data import LEVEL_9_SWORD_REFUSAL_TEXT
from zora.generate.steps.level_9_entry import COUNT_WORDS, refusal_text
from zora.model.level_9_gate import (
    EIGHT_PIECES,
    GATE_ITEM_WORDS,
    GATE_ITEMS,
    OPEN_GATE,
    TRIFORCE_LEVELS,
    GateKind,
    Level9Gate,
    item_gate,
    levels_gate,
    pieces_gate,
)
from zora.rom import opening_story as story
from zora.rom.base_rom import PRG1_ROM_PATH, remember_repo_base_rom
from zora.rom.player_settings import LEVEL_WORD_CHOICES, LEVEL_WORD_MAX_LENGTH, PlayerSettings, apply_player_settings
from zora.rom.revision import moved_to_prg0_layout

LEVEL_WORDS = (*LEVEL_WORD_CHOICES, "DUNGEON", "MAZES", "AB CDEF", "X" * LEVEL_WORD_MAX_LENGTH)
C08_VALUES = range(13)
SPECIFIC_TRIFORCES, OPEN_LEVEL_9 = 10, 8
ASNB = zora_flags.encode(zora_flags.ZoraFlags(progressive_items=True, add_l4_sword=ThreeState.ON,
                                              l4_sword_in_level_2=True, level_9_entrance_sword=True))


def flags(c08: int) -> str:
    return encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(options={"C08": c08}))


def every_gate() -> list[Level9Gate]:
    gates = [pieces_gate(pieces) for pieces in range(9)] + [OPEN_GATE]
    gates += [levels_gate(frozenset(chosen)) for count in range(9) for chosen in combinations(TRIFORCE_LEVELS, count)]
    return gates + [item_gate(item) for item in GATE_ITEMS]


def named_requirement(gate: Level9Gate) -> str:
    """What both texts must name: the count, the levels, the item, or nothing (an open level 9)."""
    if gate.kind is GateKind.ITEM:
        assert gate.item is not None
        return GATE_ITEM_WORDS[gate.item]
    if gate.kind is GateKind.LEVELS and gate.levels:
        return " ".join(str(level) for level in sorted(gate.levels))
    return "" if gate.kind is GateKind.OPEN or gate.pieces == 0 else str(gate.pieces)


def check_agrees_with_the_gate_text(lines: tuple[str, ...], gate: Level9Gate, gate_text: str) -> None:
    told = named_requirement(gate)
    said = " ".join(line.strip() for line in lines[9:11])
    if not told:
        assert lines[9].strip().startswith("GO STRAIGHT TO ") and lines[9].endswith(" 9"), said
        return
    assert told in said, (said, gate_text)
    if gate.kind is GateKind.PIECES:
        assert f"YOU NEED {COUNT_WORDS[gate.pieces]}" in gate_text
    else:
        assert told in gate_text.replace("\n", " "), gate_text


def test_the_lines_are_the_owners_laid_out_as_prg0s() -> None:
    assert story.story_lines(EIGHT_PIECES) == (
        "MANY YEARS AGO, NINTENDO", "SENT  LINK  INTO HYRULE.", "THEN   ZELDA  RANDOMIZER", "TOTALLY  CHANGED HYRULE,",
        "SHUFFLING    ITEMS   AND", "GENERATING  NEW  DUNGEON", "SHAPES  FOR  EVERY GAME.", "NOW  ZORA  EMBARKS ON AN",
        "EVEN MORE RANDOM QUEST.", "GO FIND 8 TRIFORCE UNITS", "TO RESCUE THE KIDNAPPED")
    assert [" ".join(line.split()) for line in story.story_lines(EIGHT_PIECES)[:9]] == list(story.OPENING_LINES)
    assert story.story_lines(OPEN_GATE)[9:] == (" GO STRAIGHT TO LEVEL 9", "TO RESCUE THE KIDNAPPED")
    assert story.story_lines(item_gate(GATE_ITEMS[6]))[9] == "    GO FIND THE RAFT"


def test_every_gate_and_word_fits_and_agrees_with_the_gate_text() -> None:
    for gate in every_gate():
        for word in LEVEL_WORDS:
            lines = story.story_lines(gate, word=word)
            assert len(lines) == story.LINES and all(len(line) <= story.LINE_LENGTH for line in lines), lines
            check_agrees_with_the_gate_text(lines, gate, refusal_text(gate))
            if gate.kind is GateKind.OPEN or (gate.kind is GateKind.LEVELS and gate.levels):
                assert word in " ".join(lines[9:11])
            red = [phrase for _line, phrase, palette in story.colored_spans(gate, word=word)
                   if palette == story.REQUIREMENT_COLOR and phrase != "NINTENDO"]
            told = named_requirement(gate)
            assert bool(red) == bool(told) and told in " ".join(red), (gate, red)
    assert story.requirement_lines(EIGHT_PIECES, sword_entrance=True) == (
        ("GO FIND ALL FOUR SWORDS", "TO RESCUE THE KIDNAPPED"), ("ALL FOUR SWORDS",))
    assert story.requirement_lines(pieces_gate(1))[1] == ("1 TRIFORCE UNIT",)
    assert story.requirement_lines(OPEN_GATE) == (("GO STRAIGHT TO LEVEL 9", "TO RESCUE THE KIDNAPPED"), ())
    assert story.requirement_lines(levels_gate(frozenset({2, 6, 8}))) == (
        ("GO FIND THE TRIFORCE OF", "LEVELS 2 6 8"), ("THE TRIFORCE OF", "LEVELS 2 6 8"))


@cache
def built(c08: int, zora_flags_string: str = "") -> Built:
    return build(plan(flags(c08), 1, zora_flags_string), remember_repo_base_rom())


@cache
def finished(c08: int, zora_flags_string: str = "") -> bytes:
    return finish(built(c08, zora_flags_string), remember_repo_base_rom())


@needs_base_rom
@pytest.mark.parametrize("c08", C08_VALUES)
def test_each_level_9_entry_value_tells_its_gate(c08: int) -> None:
    """The finished ROM's page names the gate the entrance checks and its person's text names."""
    world = built(c08).world
    shown = story.story_text(finished(c08))
    assert shown == story.story_lines(world.level_9_gate)
    assert all(len(line) <= story.LINE_LENGTH for line in shown)
    check_agrees_with_the_gate_text(shown, world.level_9_gate, world.level9_refusal_text)


@needs_base_rom
def test_the_level_4_sword_entrance_tells_four_swords() -> None:
    assert built(0, ASNB).world.level9_refusal_text == LEVEL_9_SWORD_REFUSAL_TEXT
    assert story.story_text(finished(0, ASNB))[9].strip() == "GO FIND ALL FOUR SWORDS"


@needs_base_rom
@pytest.mark.parametrize("word", ["DUNGEON", "MAZES"])
def test_a_level_word_is_put_in(word: str) -> None:
    opened = story.story_text(apply_player_settings(finished(OPEN_LEVEL_9), PlayerSettings(level_word=word)))
    assert opened[9] == story.centered(f"GO STRAIGHT TO {word} 9")
    gate = built(SPECIFIC_TRIFORCES).world.level_9_gate
    relabeled_levels = apply_player_settings(finished(SPECIFIC_TRIFORCES), PlayerSettings(level_word=word))
    assert story.story_text(relabeled_levels) == story.story_lines(gate, word=word)
    # the red follows the word's line
    lines = story.story_lines(gate, word=word)
    expected = story._attribute_writes(relabeled_levels, lines, story.colored_spans(gate, word=word))
    assert all(relabeled_levels[offset:offset + len(data)] == data for offset, data in expected)
    counted = finished(3)
    relabeled = apply_player_settings(counted, PlayerSettings(level_word=word))
    assert story.story_text(relabeled) == story.story_text(counted)


@needs_base_rom
def test_prg1_takes_the_same_story() -> None:
    if not PRG1_ROM_PATH.exists():
        pytest.skip(f"{PRG1_ROM_PATH.name} is not beside the PRG0 base")
    base = PRG1_ROM_PATH.read_bytes()
    rom = finish(build(plan(flags(OPEN_LEVEL_9), 1), base), base)
    image = moved_to_prg0_layout(apply_player_settings(rom, PlayerSettings(level_word="PALACE")))
    assert story.story_text(image) == story.story_lines(OPEN_GATE, word="PALACE")
    assert story.note_writes(image) == story.note_writes(moved_to_prg0_layout(rom))


def attributes(rom: bytes, row: int, column: int) -> list[int]:
    """The four palettes of an attribute byte: top left, top right, bottom left, bottom right."""
    value = rom[story._attribute_offset(row, column)]
    return [value >> shift & 0b11 for shift in (0, 2, 4, 6)]


@needs_base_rom
def test_the_words_are_colored_and_nothing_else_changes() -> None:
    base, rom = remember_repo_base_rom(), finished(0)
    # NINTENDO on row 7, ZELDA RANDOMIZER on row 11 (columns 8-24), ZORA on row 21 (5-8, its A
    # beside a space), 8 TRIFORCE UNITS on row 25 (9-24)
    colored = {(1, 5): [0, 0, 2, 2], (1, 6): [0, 0, 2, 2],
               (2, 2): [0, 0, 0, 3], (2, 3): [0, 0, 3, 3], (2, 4): [0, 0, 3, 3], (2, 5): [0, 0, 3, 3],
               (2, 6): [0, 0, 3, 3], (5, 2): [1, 1, 0, 0], (5, 3): [1, 0, 0, 0],
               (6, 3): [2, 2, 0, 0], (6, 4): [2, 2, 0, 0], (6, 5): [2, 2, 0, 0], (6, 6): [2, 2, 0, 0]}
    for row in range(1, 7):
        for column in story.INNER_ATTRIBUTE_COLUMNS:
            palettes = attributes(rom, row, column)
            if row == 1:                                        # the title row keeps PRG0's
                assert palettes[:2] == attributes(base, row, column)[:2]
                palettes = [0, 0, *palettes[2:]]
            assert palettes == colored.get((row, column), [0, 0, 0, 0]), (row, column)
    for row in range(8):
        for column in (0, 7):                                   # the frame
            assert attributes(rom, row, column) == attributes(base, row, column)
    assert all(attributes(rom, 7, column) == attributes(base, 7, column) for column in range(8))
    frame = [story._row_offset(row) + column for row in range(30) for column in range(story.ROW_TILES)
             if row not in story.INNER_ROWS or column not in story.INNER_COLUMNS]
    assert all(rom[offset] == base[offset] for offset in frame)


@needs_base_rom
def test_the_note_says_zora_gg_and_only_its_tiles_change() -> None:
    base, rom = remember_repo_base_rom(), finished(0)
    note = {offset + i for offset, data in story.note_writes(base) for i in range(len(data))}
    patterns = range(story.DEMO_SPRITE_PATTERNS, story.DEMO_SPRITE_PATTERNS + 0x90 * story.TILE_SIZE)
    assert {offset for offset in patterns if rom[offset] != base[offset]} <= note
    assert note <= set(range(story.DEMO_SPRITE_PATTERNS + (0xDC - story.FIRST_DEMO_TILE) * story.TILE_SIZE,
                             patterns.stop))
    for y in story.THIRD_LINE_ROWS:
        for x in story.THIRD_LINE_COLUMNS:
            low, bit, _tile = story._pixel_place(y, x)
            color = (rom[low] >> bit & 1) | (rom[low + 8] >> bit & 1) << 1
            assert color == (story.INK_COLOR if (y, x) in story._ink(story.NOTE_LINE) else story.SHEET_COLOR)


@needs_base_rom
def test_the_note_follows_the_players_graphics() -> None:
    """Each pixel of the note's tiles inverted (2 bits each): the third line is the same, inverted;
    the fourth line's letters with another shape (a note drawn otherwise) leave the note alone."""
    base = remember_repo_base_rom()
    inverted = bytearray(base)
    start = story.DEMO_SPRITE_PATTERNS + (0xDC - story.FIRST_DEMO_TILE) * story.TILE_SIZE
    end = story.DEMO_SPRITE_PATTERNS + 0x90 * story.TILE_SIZE
    inverted[start:end] = bytes(value ^ 0xFF for value in base[start:end])
    assert story.note_writes(base)
    assert [(offset, bytes(value ^ 0xFF for value in data)) for offset, data in story.note_writes(base)] \
        == story.note_writes(inverted)
    redrawn = bytearray(base)
    low, bit, _tile = story._pixel_place(*story.NOTE_LETTERS["R"])
    redrawn[low + 8] ^= 1 << bit                                # the R's top left: sheet, not ink
    assert story.note_writes(redrawn) == []


@needs_base_rom
def test_no_story_byte_is_z1rr_coops() -> None:
    writes = story.story_writes(remember_repo_base_rom(), EIGHT_PIECES)
    assert not hits({offset + i for offset, data in writes for i in range(len(data))})
