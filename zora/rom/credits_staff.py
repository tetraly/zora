"""The ending credits' Randomizer Staff box (FP-CREDITS-01, owner, beta 9): ZORA's names from
zora/rom/credits_staff.txt, in a box like the original staff box, right after it.

PRG0's credits (Z_02 DrawCredits): as the ending scrolls, one tile row is drawn every 8 pixels.
CreditsRow counts them (rows 30 and 31 of each 32 never come: a nametable has 30). Twelve VRAM
pages of 8 rows (6 in pages 3, 7 and 11) say by a bit mask which rows hold text, and each such
row takes the next of 23 text records (length, first column, tiles; 32 columns, the box's inside
is columns 4-27): the staff box (lines 0-11, rows 1-46, its brick walls drawn on rows 1 and 46
and at columns 3 and 28 of the rows between), then the first quest's closing lines (12-15,
rows 55-70) or the second quest's (16-22, rows 71-89, the file's name and deaths on line 17).
An attribute byte per four rows colors them: palette 1 red, 2 blue, 3 green, 0 the walls and
the box's name. The scroll stops at screen 2 + $78 (first quest) or screen 3 (second).

fp-credits-01 has DrawCredits read ZORA's tables, which this module writes for each ROM: the
original's rows, lines and colors up to its box's bottom wall, then ZORA_INSERTED_ROWS rows for
the new box, then the original's after them, 64 rows (two nametables) later, so they keep their
place on screen and their colors; the scroll runs two screens longer. The original's text and
tables are read from the player's ROM; FP-LOCK-02's records for lines 12-14 come from the world.
"""
from dataclasses import dataclass
from importlib.resources import files

from .base_rom import original_bytes
from .code_patch_data import SYMBOLS
from .layout import CREDITS_POINTERS_HI_ADDRESS, CREDITS_POINTERS_LO_ADDRESS
from .text_encoding import CHAR_TO_BYTE

STAFF_FILE = "credits_staff.txt"
COMMENT = "#"
TITLE_TAG = "[title]"
WHITE, RED, BLUE, GREEN = 0, 1, 2, 3          # the credits' palettes (StoryPalette is the story's)
COLOR_TAGS = {"[white]": WHITE, "[red]": RED, "[blue]": BLUE, "[green]": GREEN}
LEFT, CENTER = "left", "center"
ALIGN_TAGS = {"[left]": LEFT, "[center]": CENTER}
BOX_WIDTH = 24                                # columns 4-27, inside the walls
BOX_FIRST_COLUMN = 4
LEFT_COLUMN = 5                               # the original's lines start here ("EXECUTIVE", "SOUND")
CREDITS_DOT = 0x63                            # the credits' dot ("PRODUCER... H.YAMAUCHI")
CHARACTERS = {**{char: CHAR_TO_BYTE[char] for char in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ ,!'&\"?-"},
              ".": CREDITS_DOT}

# PRG0's credits (file offsets in PRG0's layout; the bank-2 CPU address is the offset - $10)
BANK_2_CPU = -0x10
PAGE_MASKS = 0x0AC32                          # CreditsPagesTextMasks, 12 bytes
PAGE_ROWS = (8, 8, 8, 6)                      # a nametable's four pages
ORIGINAL_LINES = 23
ATTRIBUTES = 0x0AE0A                          # CreditsAttrs, 24 bytes
ORIGINAL_ATTRIBUTE_ROWS = 24
ORIGINAL_BOX = (1, 0x2E)                      # its top and bottom wall rows
FIRST_QUEST_END, SECOND_QUEST_SKIP, NAME_LINE = 0x10, (0x0C, 0x10), 0x11
LOCKED_LINES = range(12, 16)                  # FP-LOCK-02's records (GameWorld.credits_pointers)
ROWS_PER_NAMETABLE = 32                       # CreditsRow's count, 30 drawn
DRAWN_ROWS = 30

# The new box
INSERT_AT = ORIGINAL_BOX[1] + 1               # the first CreditsRow after the original box
INSERTED_ROWS = 2 * ROWS_PER_NAMETABLE        # fp-credits-01's two more screens
GAP = 8                                       # empty rows before the box, as before PRG0's next line
BOX_FRAME_ROWS = 4                            # the walls, and an empty row inside each
# Where each quest's scroll stops (fp-credits-01's CreditsLastScreenList, PRG0's $78 and $00), in
# pixels, and the row drawn two nametables before the one that would come next: it still shows,
# not drawn over, at the bottom of the stopped screen (PRG0 shows its box's side walls there). The
# new box keeps text off those rows (seen in the emulator).
SCREEN_PIXELS, ROW_PIXELS = 240, 8
STOPS = (4 * SCREEN_PIXELS + 0x78, 5 * SCREEN_PIXELS)
LEFTOVER_ROWS = tuple(stop // ROW_PIXELS - (2 * 30 + 1) for stop in STOPS)
LAST_BOX = 0xFF

# fp-credits-01's tables
TEXT_ROWS = SYMBOLS["ZORA_B2_CreditsTextRows"]
LINES_LO, LINES_HI = SYMBOLS["ZORA_B2_CreditsLinesLo"], SYMBOLS["ZORA_B2_CreditsLinesHi"]
LINE_COUNT = SYMBOLS["ZORA_B2_CreditsLineCount"]
QUEST_END = SYMBOLS["ZORA_B2_CreditsFirstQuestEnd"]
QUEST_SKIP = SYMBOLS["ZORA_B2_CreditsSecondQuestSkip"]
NAME_LINE_INDEX = SYMBOLS["ZORA_B2_CreditsNameLine"]
BOXES = SYMBOLS["ZORA_B2_CreditsBoxes"]
NEW_ATTRIBUTES = SYMBOLS["ZORA_B2_CreditsAttributes"]
RECORDS = SYMBOLS["ZORA_B2_CreditsRecords"]
TEXT_ROW_BYTES, MAX_LINES, MAX_BOXES, ATTRIBUTE_ROWS, RECORDS_SIZE = 32, 64, 3, 64, 1024


class CreditsError(ValueError):
    """credits_staff.txt cannot be shown: a line too long, an unknown character or tag, too many rows."""


@dataclass(frozen=True)
class StaffRow:
    text: str                                 # "" for an empty row
    color: int = WHITE
    align: str = CENTER


@dataclass(frozen=True)
class Staff:
    title: str
    rows: tuple[StaffRow, ...]


def parse_staff(text: str) -> Staff:
    """credits_staff.txt's title and rows; refuses what the credits cannot show."""
    title, color, align, rows = "", WHITE, LEFT, []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if line.startswith(COMMENT):
            continue
        if line.startswith(TITLE_TAG):
            title = line.removeprefix(TITLE_TAG).strip()
            check_line(f" {title} ", number)
        elif line.lower() in COLOR_TAGS:
            color = COLOR_TAGS[line.lower()]
        elif line.lower() in ALIGN_TAGS:
            align = ALIGN_TAGS[line.lower()]
        elif line.startswith("["):
            raise CreditsError(f"{STAFF_FILE} line {number}: unknown tag {line!r} "
                               f"(use {', '.join([*COLOR_TAGS, *ALIGN_TAGS])})")
        else:
            check_line(line, number)
            if align == LEFT and len(line) > BOX_WIDTH - (LEFT_COLUMN - BOX_FIRST_COLUMN):
                raise CreditsError(f"{STAFF_FILE} line {number}: {line!r} is {len(line)} columns; from the left "
                                   f"edge at most {BOX_WIDTH - (LEFT_COLUMN - BOX_FIRST_COLUMN)} fit, or center it")
            rows.append(StaffRow(line, color if line else WHITE, align))
    if not title:
        raise CreditsError(f"{STAFF_FILE}: no {TITLE_TAG} line")
    while rows and not rows[-1].text:
        rows.pop()
    fitting = DRAWN_ROWS * INSERTED_ROWS // ROWS_PER_NAMETABLE - BOX_FRAME_ROWS
    if len(rows) > fitting:
        raise CreditsError(f"{STAFF_FILE}: {len(rows)} rows, and the box holds {fitting}")
    return Staff(title, tuple(rows))


def check_line(line: str, number: int) -> None:
    if len(line) > BOX_WIDTH:
        raise CreditsError(f"{STAFF_FILE} line {number}: {line!r} is {len(line)} columns, at most {BOX_WIDTH}")
    unknown = sorted(set(line) - set(CHARACTERS))
    if unknown:
        raise CreditsError(f"{STAFF_FILE} line {number}: {line!r}: the credits' font has no {''.join(unknown)!r}")


def load_staff() -> Staff:
    # This package by its own name (zora/ may be copied in under another, perhaps from a zip).
    return parse_staff(files(__package__).joinpath(STAFF_FILE).read_text(encoding="utf-8"))


def record(text: str, align: str = CENTER) -> bytes:
    """A credits text record: length, first column, tiles; centered in the box, or from the
    original's left edge (LEFT_COLUMN)."""
    column = LEFT_COLUMN if align == LEFT else BOX_FIRST_COLUMN + (BOX_WIDTH - len(text)) // 2
    return bytes([len(text), column, *(CHARACTERS[char] for char in text)])


def credits_row(drawn: int) -> int:
    """The CreditsRow of the `drawn`-th row drawn (rows 30 and 31 of each 32 never come)."""
    return drawn // DRAWN_ROWS * ROWS_PER_NAMETABLE + drawn % DRAWN_ROWS


def drawn_index(row: int) -> int:
    return row // ROWS_PER_NAMETABLE * DRAWN_ROWS + row % ROWS_PER_NAMETABLE


def original_text_rows(masks: bytes) -> list[int]:
    """The CreditsRows PRG0's page masks give text, in order (lines 0 to 22)."""
    rows, row = [], 0
    for page, mask in enumerate(masks):
        for line in range(PAGE_ROWS[page % len(PAGE_ROWS)]):
            if mask << line & 0x80:
                rows.append(row)
            row += 1
        if page % len(PAGE_ROWS) == len(PAGE_ROWS) - 1:
            row += ROWS_PER_NAMETABLE - DRAWN_ROWS
    return rows


def _attribute(top: int, bottom: int) -> int:
    return top | top << 2 | bottom << 4 | bottom << 6


def _half_palette(placed: "CreditsLayout", row: int) -> int:
    """The palette of the 16x16 blocks of rows `row` and `row` + 1 of the new box: its lines'."""
    colors = {line.color for line in (placed.staff_rows.get(row), placed.staff_rows.get(row + 1))
              if line is not None and line.text}
    if len(colors) > 1:
        raise CreditsError(f"{STAFF_FILE}: credits rows {row} and {row + 1} share their colors; "
                           "put an empty row between two colors")
    return colors.pop() if colors else WHITE


@dataclass(frozen=True)
class CreditsLayout:
    staff_rows: dict[int, StaffRow]           # CreditsRow -> the new box's row (its title's included)
    box: tuple[int, int]                      # its walls' rows


def placed_at(staff: Staff, gap: int) -> CreditsLayout:
    """The new box `gap` empty rows after the original box: its top wall with the title, an
    empty row, the file's rows, an empty row and its bottom wall."""
    first = drawn_index(INSERT_AT) + gap
    top = credits_row(first)
    rows = {top: StaffRow(f" {staff.title} ")}
    for offset, row in enumerate(staff.rows, start=2):
        rows[credits_row(first + offset)] = row
    return CreditsLayout(rows, (top, credits_row(first + len(staff.rows) + BOX_FRAME_ROWS - 1)))


def layout(staff: Staff) -> CreditsLayout:
    """The box at the gap closest to GAP (the smaller first) that fits and keeps text off the
    stopped screens' leftover rows."""
    room = DRAWN_ROWS * INSERTED_ROWS // ROWS_PER_NAMETABLE - len(staff.rows) - BOX_FRAME_ROWS
    leftover = {credits_row(row) for row in LEFTOVER_ROWS}
    for gap in sorted(range(room + 1), key=lambda gap: (abs(gap - GAP), gap)):
        placed = placed_at(staff, gap)
        if not leftover & {row for row, line in placed.staff_rows.items() if line.text}:
            return placed
    raise CreditsError(f"{STAFF_FILE}: no place for the box keeps text off the stopped screen's last row; "
                       "add or remove an empty row")


def credits_writes(pointers_12_to_15: tuple[int, ...] | None = None,
                   staff: Staff | None = None) -> list[tuple[int, bytes]]:
    """fp-credits-01's tables for the player's ROM (in PRG0's layout): every row's text bit, the
    lines in row order with the new box's records, the quests' line numbers, the boxes and the
    attributes. pointers_12_to_15: FP-LOCK-02's records (GameWorld.credits_pointers), else PRG0's."""
    staff = staff or load_staff()
    placed = layout(staff)
    masks = original_bytes(PAGE_MASKS, len(PAGE_ROWS) * 3)
    low, high = (original_bytes(table, ORIGINAL_LINES) for table in (CREDITS_POINTERS_LO_ADDRESS,
                                                                     CREDITS_POINTERS_HI_ADDRESS))
    pointers = [low[line] | high[line] << 8 for line in range(ORIGINAL_LINES)]
    if pointers_12_to_15 is not None:
        pointers[LOCKED_LINES.start:LOCKED_LINES.stop] = pointers_12_to_15
    old_attributes = original_bytes(ATTRIBUTES, ORIGINAL_ATTRIBUTE_ROWS)

    def moved(row: int) -> int:
        return row if row < INSERT_AT else row + INSERTED_ROWS

    original_rows = original_text_rows(masks)
    before = [line for line, row in enumerate(original_rows) if row < INSERT_AT]
    text_rows = sorted([moved(row) for row in original_rows] + [row for row, line in placed.staff_rows.items()
                                                                  if line.text])
    records, addresses = bytearray(), []
    for row in sorted(placed.staff_rows):
        if placed.staff_rows[row].text:
            addresses.append(RECORDS + len(records) + BANK_2_CPU)
            line = placed.staff_rows[row]
            records += record(line.text, line.align)
    added = len(addresses)
    lines = [*(pointers[line] for line in before), *addresses, *pointers[len(before):]]
    if len(lines) > MAX_LINES or len(records) > RECORDS_SIZE:
        raise CreditsError(f"{STAFF_FILE}: {len(lines)} credits lines and {len(records)} bytes of text, at most "
                           f"{MAX_LINES} and {RECORDS_SIZE}")

    bits = bytearray(TEXT_ROW_BYTES)
    for row in text_rows:
        bits[row // 8] |= 0x80 >> row % 8

    attributes = bytearray(ATTRIBUTE_ROWS)
    first_new, last_new = INSERT_AT // 4 + 1, (INSERT_AT + INSERTED_ROWS - 1) // 4
    for index in range(ATTRIBUTE_ROWS):
        if index < first_new:
            attributes[index] = old_attributes[index]
        elif index <= last_new:
            attributes[index] = _attribute(*(_half_palette(placed, row) for row in (4 * index, 4 * index + 2)))
        elif index - INSERTED_ROWS // 4 < ORIGINAL_ATTRIBUTE_ROWS:
            attributes[index] = old_attributes[index - INSERTED_ROWS // 4]

    boxes = bytes([*ORIGINAL_BOX, *placed.box, LAST_BOX])
    assert len(before) == LOCKED_LINES.start, before                  # the box's twelve lines
    return [
        (TEXT_ROWS, bytes(bits)),
        (LINES_LO, bytes(address & 0xFF for address in lines)),
        (LINES_HI, bytes(address >> 8 for address in lines)),
        (LINE_COUNT, bytes([len(lines)])),
        (QUEST_END, bytes([FIRST_QUEST_END + added])),
        (QUEST_SKIP, bytes([SECOND_QUEST_SKIP[0] + added, SECOND_QUEST_SKIP[1] + added])),
        (NAME_LINE_INDEX, bytes([NAME_LINE + added])),
        (BOXES, boxes),
        (NEW_ATTRIBUTES, bytes(attributes)),
        (RECORDS, bytes(records)),
    ]
