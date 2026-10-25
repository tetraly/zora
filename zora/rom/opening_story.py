"""ZORA's opening story and the story's closing note (beta 9, owner prompt 544 and its amendment).

The story's first page is one transfer record list, StoryTileAttrTransferBuf (bank 6, PRG0 file
0x1A40E, 1,131 bytes; InitDemoSubphaseTransferStoryTiles selects it): 32 rows of 32 tiles for
nametable $2000, then its 64 attribute bytes, written once while the screen is off. The page then
scrolls up as a whole (AnimateDemoPhase1Subphase0 only moves CurVScroll), so its attributes travel
with its tiles: a word is colored by the attribute bytes alone, during the scroll and after it.

Inside its frame PRG0's page has eleven lines of 24 tiles, at columns 4 to 27 of the odd rows 7 to
27; the even rows between them are blank but for its quotation marks ($F8, under "GANNON" and
"LINK"). Its paragraph's lines are justified to both edges, all but the paragraph's last, and its
closing two lines are centered. ZORA's eleven lines, the owner's text (2026-10-24), are laid out
the same way on the same rows. Each line is therefore alone in its half of an attribute row (a
16x16 block holds rows 2k and 2k+1), and a block is two columns wide. The text's color is color 1
of its palette (StoryPaletteTransferRecord): palette 0 white ($30), 1 blue ($21, PRG0's TRIFORCE),
2 red ($16, PRG0's title, GANNON and ZELDA), 3 green ($29, PRG0's LINK; also the frame's). ZORA
colors NINTENDO red, ZELDA RANDOMIZER green, ZORA blue and what level 9 asks to find red with those
palettes and changes none of them; every other block inside the frame is white, and the title row
and the frame keep PRG0's attributes.

Lines 10 and 11 state level 9's requirement, the Level9Gate the entrance check and its person's text
are written from (level_9_entry.refusal_text; the spoiler log reads the same world field), or the
level-4-sword entrance's four swords. A custom level word (FP-LEVEL-01, a player setting) is put in
on the finished ROM, as for the refusal text, with the red that follows it (level_word_in_story).

The note Link holds at the end of the item scroll (DemoStoryFinalSpriteTiles: 18 sprites of 8x16,
tiles $DC-$FF of DemoSpritePatterns, loaded at PPU $0700) is drawn art in a font 3 pixels wide:
"PLEASE / LOOK UP / THE MANUAL / FOR DETAILS.". Its third line becomes "ZORA.GG" on the tiles of
the ROM being written: O, R, A and the period copied from its fourth line, so a graphics pack's
note keeps its own letters, and Z and G, which its font lacks, drawn in its own ink and sheet
colors. A pack whose note does not hold those words keeps its note as drawn.
"""
import re

from ..model.level_9_gate import ALL_PIECES, GATE_ITEM_WORDS, GateKind, Level9Gate
from .text_encoding import CHAR_TO_BYTE

LINE_LENGTH = 24
DEFAULT_LEVEL_WORD = "LEVEL"            # player_settings.DEFAULT_LEVEL_WORD (FP-LEVEL-01)
LEVEL_9 = 9

# --- the page -------------------------------------------------------------------------------

STORY_RECORDS = 0x1A40E                 # StoryTileAttrTransferBuf (PRG0's layout)
RECORD_HEADER = 3                       # PPU address high, low, tile count
ROW_TILES = 32
RECORD_SIZE = RECORD_HEADER + ROW_TILES
FIRST_LINE_ROW = 7
LINES = 11
TEXT_COLUMN = 4                         # the lines' first column
INNER_COLUMNS = range(3, 29)            # inside the frame (columns 2 and 29)
INNER_ROWS = range(5, 29)               # below the title row (4), above the bottom border (29)
BLANK_TILE = CHAR_TO_BYTE[" "]
ATTRIBUTE_RECORDS = STORY_RECORDS + 30 * RECORD_SIZE      # $23C0 and $23E0, 32 bytes each
ATTRIBUTE_COLUMNS = 8
INNER_ATTRIBUTE_COLUMNS = range(1, 7)   # columns 4-27
WHITE, BLUE, RED, GREEN = 0, 1, 2, 3    # the palette each color is color 1 of

OPENING_LINES = (
    "MANY YEARS AGO, NINTENDO",
    "SENT LINK INTO HYRULE.",
    "THEN ZELDA RANDOMIZER",
    "TOTALLY CHANGED HYRULE,",
    "SHUFFLING ITEMS AND",
    "GENERATING NEW DUNGEON",
    "SHAPES FOR EVERY GAME.",
    "NOW ZORA EMBARKS ON AN",
    "EVEN MORE RANDOM QUEST.",
)
RESCUE_LINE = "TO RESCUE THE KIDNAPPED"
FIND = "GO FIND "
# Each colored phrase, its line (1-based) and its color; the requirement's is requirement_lines'
COLORED_WORDS = (("NINTENDO", 1, RED), ("ZELDA RANDOMIZER", 3, GREEN), ("ZORA", 8, BLUE))
REQUIREMENT_COLOR = RED

Span = tuple[int, str, int]             # line (1-based), phrase, palette


def plural(word: str) -> str:
    """The level word for several levels, as the refusal text makes it (chosen_levels_text)."""
    return word if word.endswith("S") else f"{word}S"


def requirement_lines(gate: Level9Gate, sword_entrance: bool = False,
                      word: str = DEFAULT_LEVEL_WORD) -> tuple[tuple[str, str], tuple[str, ...]]:
    """Lines 10 and 11, what level 9 asks for, and what there is to find in them (red, owner
    2026-10-24): nothing for an open level 9. PRG0's eight pieces read as the owner wrote them; no
    count, or no chosen level, is an open level 9."""
    if sword_entrance:
        return (f"{FIND}ALL FOUR SWORDS", RESCUE_LINE), ("ALL FOUR SWORDS",)
    if gate.kind is GateKind.ITEM:
        assert gate.item is not None
        item = GATE_ITEM_WORDS[gate.item]
        find = f"{FIND}{item}"
        return (find if len(find) <= LINE_LENGTH else find.removeprefix("GO "), RESCUE_LINE), (item,)
    if gate.kind is GateKind.LEVELS and gate.levels:
        numbers = " ".join(str(level) for level in sorted(gate.levels))
        levels = f"{word if len(gate.levels) == 1 else plural(word)} {numbers}"
        return (f"{FIND}THE TRIFORCE OF", levels), ("THE TRIFORCE OF", levels)
    if gate.kind is GateKind.OPEN or gate.pieces == 0:
        return (f"GO STRAIGHT TO {word} {LEVEL_9}", RESCUE_LINE), ()
    units = f"{gate.pieces} TRIFORCE {'UNIT' if gate.pieces == 1 else 'UNITS'}"
    assert 1 <= gate.pieces <= ALL_PIECES
    return (f"{FIND}{units}", RESCUE_LINE), (units,)


def justified(line: str) -> str:
    """A paragraph line spread to the full width with spaces between its words, as PRG0's are
    ("MANY  YEARS  AGO  PRINCE"): one more to each gap from the left."""
    words = line.split()
    gaps = len(words) - 1
    if gaps == 0:
        return line
    more, left = divmod(LINE_LENGTH - len(line), gaps)
    spaced = words[0]
    for gap, word in enumerate(words[1:]):
        spaced += " " * (1 + more + (gap < left)) + word
    return spaced


def centered(line: str) -> str:
    """A closing line, as PRG0's two are ("  GO FIND THE  8 UNITS")."""
    return " " * ((LINE_LENGTH - len(line)) // 2) + line


def story_lines(gate: Level9Gate, sword_entrance: bool = False, word: str = DEFAULT_LEVEL_WORD) -> tuple[str, ...]:
    """The page's eleven lines laid out as PRG0's: the paragraph justified to both edges but its
    last line, then the requirement's two lines centered."""
    *paragraph, last = OPENING_LINES
    requirement, _found = requirement_lines(gate, sword_entrance, word)
    lines = (*(justified(line) for line in paragraph), last, *(centered(line) for line in requirement))
    assert len(lines) == LINES and all(len(line) <= LINE_LENGTH for line in lines), lines
    return lines


def colored_spans(gate: Level9Gate, sword_entrance: bool = False, word: str = DEFAULT_LEVEL_WORD) -> list[Span]:
    """Every colored phrase: the fixed words, and the requirement's thing to find in red (each
    phrase on the first of lines 10 and 11 that holds it)."""
    lines = story_lines(gate, sword_entrance, word)
    requirement, found = requirement_lines(gate, sword_entrance, word)
    spans = [(line, phrase, palette) for phrase, line, palette in COLORED_WORDS]
    for phrase in found:
        line = next(index for index, text in enumerate(requirement, start=len(OPENING_LINES) + 1)
                    if phrase in text)
        spans.append((line, phrase, REQUIREMENT_COLOR))
    assert all(_place(lines[line - 1], phrase) for line, phrase, _palette in spans)
    return spans


def _place(text: str, phrase: str) -> range:
    """The columns of `phrase` in a laid-out line, its words as far apart as the layout put them."""
    found = re.search(r" +".join(re.escape(word) for word in phrase.split()), text)
    assert found is not None, (phrase, text)
    return range(found.start(), found.end())


def _row_offset(row: int) -> int:
    return STORY_RECORDS + row * RECORD_SIZE + RECORD_HEADER


def _line_row(line: int) -> int:
    """The tile row of a line, 1-based."""
    return FIRST_LINE_ROW + 2 * (line - 1)


def _encoded(line: str) -> bytes:
    return bytes(CHAR_TO_BYTE[char] for char in line.ljust(LINE_LENGTH))


def _line_writes(lines: tuple[str, ...], first_line: int) -> list[tuple[int, bytes]]:
    return [(_row_offset(_line_row(line)) + TEXT_COLUMN, _encoded(text))
            for line, text in enumerate(lines, start=first_line)]


def _attribute_offset(row: int, column: int) -> int:
    """Attribute row `row` of the 8 (tile rows 4*row to 4*row+3), column `column`."""
    return ATTRIBUTE_RECORDS + (row // 4) * RECORD_SIZE + RECORD_HEADER + (row % 4) * ATTRIBUTE_COLUMNS + column


def _block_palettes(lines: tuple[str, ...], spans: list[Span]) -> dict[tuple[int, int], int]:
    """Each colored phrase's 16x16 blocks (block row, block column) and palette; a block holds no
    letter of another word."""
    blocks = {}
    for line, phrase, palette in spans:
        text = lines[line - 1].ljust(LINE_LENGTH)
        columns = _place(text, phrase)
        for block in {(TEXT_COLUMN + index) // 2 for index in columns}:
            shared = range(max(2 * block - TEXT_COLUMN, 0), 2 * block - TEXT_COLUMN + 2)
            assert all(index in columns or text[index] == " " for index in shared), (phrase, text)
            blocks[_line_row(line) // 2, block] = palette
    return blocks


def _attribute_writes(rom: bytes | bytearray, lines: tuple[str, ...], spans: list[Span]) -> list[tuple[int, bytes]]:
    """Inside the frame, below the title row: white but for the colored phrases. The title row's
    quadrants (block row 2, the top of attribute row 1) keep the ROM's."""
    colored = _block_palettes(lines, spans)
    first_block_row = INNER_ROWS.start // 2 + 1           # 3: rows 6-7, line 1's
    writes = []
    for row in range(first_block_row // 2, INNER_ROWS.stop // 4):
        for column in INNER_ATTRIBUTE_COLUMNS:
            value = rom[_attribute_offset(row, column)]
            for quadrant in range(4):
                block_row, block_column = 2 * row + quadrant // 2, 2 * column + quadrant % 2
                if block_row < first_block_row:
                    continue
                shift = 2 * quadrant
                value = value & ~(0b11 << shift) | colored.get((block_row, block_column), WHITE) << shift
            writes.append((_attribute_offset(row, column), bytes([value])))
    return writes


def story_writes(rom: bytes | bytearray, gate: Level9Gate, sword_entrance: bool = False) -> list[tuple[int, bytes]]:
    """The page (every row inside the frame below the title: blank, then the lines), its colors,
    and the note's third line."""
    blank = bytes([BLANK_TILE] * len(INNER_COLUMNS))
    writes = [(_row_offset(row) + INNER_COLUMNS.start, blank) for row in INNER_ROWS]
    lines = story_lines(gate, sword_entrance)
    writes += _line_writes(lines, 1)
    writes += _attribute_writes(rom, lines, colored_spans(gate, sword_entrance))
    writes += note_writes(rom)
    return writes


def level_word_in_story(rom: bytearray, gate: Level9Gate, word: str) -> None:
    """FP-LEVEL-01 on the finished ROM: lines 10 and 11 with the player's level word, and their
    red, where they are ZORA's own text for `gate` with PRG0's word (an open level 9 or chosen
    levels name it)."""
    first_line = len(OPENING_LINES) + 1
    written = _line_writes(story_lines(gate)[first_line - 1:], first_line)
    if any(bytes(rom[offset:offset + len(data)]) != data for offset, data in written):
        return
    lines = story_lines(gate, word=word)
    for offset, data in [*_line_writes(lines[first_line - 1:], first_line),
                         *_attribute_writes(rom, lines, colored_spans(gate, word=word))]:
        rom[offset:offset + len(data)] = data


def story_text(rom: bytes | bytearray) -> tuple[str, ...]:
    """The page's eleven lines as a ROM holds them, trailing blanks dropped."""
    characters = {byte: char for char, byte in CHAR_TO_BYTE.items()}
    return tuple("".join(characters.get(tile, "?") for tile in rom[offset:offset + LINE_LENGTH]).rstrip()
                 for offset in (_row_offset(_line_row(line)) + TEXT_COLUMN for line in range(1, LINES + 1)))


# --- the note -------------------------------------------------------------------------------

DEMO_SPRITE_PATTERNS = 0x4DC4           # DemoSpritePatterns (PRG0's layout): tiles $70-$FF
FIRST_DEMO_TILE = 0x70
TILE_SIZE = 16
# DemoStoryFinalSpriteTiles' first three rows: the note, 8x16 sprites (the top tile of each pair)
NOTE_TILES = ((0xE0, 0xE2, 0xEC, 0xEE, 0xF8, 0xFA),
              (0xE4, 0xE6, 0xF0, 0xF2, 0xFC, 0xFE),
              (0xE8, 0xEA, 0xF4, 0xF6, 0xDC, 0xDE))
SPRITE_WIDTH, SPRITE_HEIGHT = 8, 16
SHEET_COLOR, INK_COLOR = 2, 0           # PRG0's sheet, and its text (transparent: the black behind)
SHEET_SAMPLE = (33, 0)                  # a pixel of bare sheet between the third and fourth lines
THIRD_LINE_ROWS = range(26, 33)         # "THE MANUAL", 7 pixels tall
THIRD_LINE_COLUMNS = range(3, 45)       # its width with a pixel either side; the curl is 45-47
NOTE_CENTER = 24
NOTE_LINE = "ZORA.GG"
# The note's letters, 7 rows, "#" the ink: those of "ZORA.GG" its own lines hold, and Z and G
GLYPHS = {
    "Z": ("###", "..#", "..#", ".#.", "#..", "#..", "###"),
    "O": ("###", "#.#", "#.#", "#.#", "#.#", "#.#", "###"),
    "R": ("###", "#.#", "#.#", "#.#", "##.", "#.#", "#.#"),
    "A": (".#.", "###", "#.#", "#.#", "###", "#.#", "#.#"),
    ".": (".", ".", ".", ".", ".", ".", "#"),
    "G": ("###", "#..", "#..", "#.#", "#.#", "#.#", "###"),
}
# Where the note's fourth line, "FOR DETAILS.", holds a letter (top left pixel): those are copied,
# so a graphics pack's note carries its own letters through; the note's font has no Z or G, which
# are drawn in the note's own ink and sheet colors.
NOTE_LETTERS = {"O": (37, 6), "R": (37, 10), "A": (37, 29), ".": (37, 45)}


def _pixel_place(y: int, x: int) -> tuple[int, int, int]:
    """The note pixel's file offset (of its tile's low plane row), and its bit."""
    tile = NOTE_TILES[y // SPRITE_HEIGHT][x // SPRITE_WIDTH] + (y % SPRITE_HEIGHT) // 8
    return DEMO_SPRITE_PATTERNS + (tile - FIRST_DEMO_TILE) * TILE_SIZE + y % 8, 7 - x % SPRITE_WIDTH, tile


def _pixel(rom: bytes | bytearray, y: int, x: int) -> int:
    low, bit, _tile = _pixel_place(y, x)
    return (rom[low] >> bit & 1) | (rom[low + 8] >> bit & 1) << 1


def _glyph_pixels(char: str, top: int, left: int) -> dict[tuple[int, int], bool]:
    """Each pixel of `char` placed at (top, left): True where it is ink."""
    return {(top + dy, left + dx): ink == "#" for dy, row in enumerate(GLYPHS[char]) for dx, ink in enumerate(row)}


def _letter_lefts(text: str) -> list[tuple[str, int]]:
    """Each letter of `text` and its left column, a pixel apart, centered on the note."""
    width = sum(len(GLYPHS[char][0]) for char in text) + len(text) - 1
    left, lefts = NOTE_CENTER - width // 2, []
    for char in text:
        lefts.append((char, left))
        left += len(GLYPHS[char][0]) + 1
    return lefts


def _ink(text: str) -> set[tuple[int, int]]:
    """The pixels of `text`'s ink on the third line."""
    return {place for char, left in _letter_lefts(text)
            for place, is_ink in _glyph_pixels(char, THIRD_LINE_ROWS.start, left).items() if is_ink}


def _note_colors(rom: bytes | bytearray) -> tuple[int, int] | None:
    """The note's sheet and ink colors, where its fourth line holds PRG0's letters in them (any
    graphics pack that keeps the note's words); None for a note drawn otherwise."""
    sheet = _pixel(rom, *SHEET_SAMPLE)
    ink = _pixel(rom, *NOTE_LETTERS["O"])
    if ink == sheet:
        return None
    held = all(_pixel(rom, y, x) == (ink if is_ink else sheet)
               for char, place in NOTE_LETTERS.items() for (y, x), is_ink in _glyph_pixels(char, *place).items())
    return (sheet, ink) if held else None


def note_writes(rom: bytes | bytearray) -> list[tuple[int, bytes]]:
    """The note's third line: its sheet over "THE MANUAL", then "ZORA.GG", each letter the note's
    fourth line holds copied from there and Z and G in its ink. A note whose fourth line is not
    PRG0's words, in whatever colors, is the player's own drawing and is left as it is."""
    colors = _note_colors(rom)
    if colors is None:
        return []
    sheet, ink = colors
    image = bytearray(rom)
    line = {(y, x): sheet for y in THIRD_LINE_ROWS for x in THIRD_LINE_COLUMNS}
    for char, left in _letter_lefts(NOTE_LINE):
        for (y, x), is_ink in _glyph_pixels(char, THIRD_LINE_ROWS.start, left).items():
            if char in NOTE_LETTERS:
                source_top, source_left = NOTE_LETTERS[char]
                line[(y, x)] = _pixel(rom, source_top + y - THIRD_LINE_ROWS.start, source_left + x - left)
            else:
                line[(y, x)] = ink if is_ink else sheet
    tiles = set()
    for (y, x), color in line.items():
        low, bit, tile = _pixel_place(y, x)
        for plane in range(2):
            mask = 1 << bit
            image[low + 8 * plane] = image[low + 8 * plane] & ~mask | (color >> plane & 1) * mask
        tiles.add(tile)
    offsets = sorted(DEMO_SPRITE_PATTERNS + (tile - FIRST_DEMO_TILE) * TILE_SIZE for tile in tiles)
    return [(offset, bytes(image[offset:offset + TILE_SIZE])) for offset in offsets]
