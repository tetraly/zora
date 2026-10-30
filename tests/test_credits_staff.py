"""The ending credits' Randomizer Staff box (FP-CREDITS-01; zora/rom/credits_staff.py, its names
in zora/rom/credits_staff.txt, the code asm/fp-credits-01):

- the file's every line fits the box and its font, and the build refuses what does not;
- the tables keep PRG0's rows, lines and colors before the box and move the rest two nametables
  down; FP-LOCK-02's records stay lines 12 to 15;
- in the emulator, the credits draw PRG0's staff box, then the new box line by line, then PRG0's
  closing lines (the first quest's ©, the second quest's from YOU ARE GREAT), on PRG0 and PRG1,
  and the scroll stops on the original closing screen with no text on its last row;
- none of its bytes is z1rr-coop's or another patch's."""
from functools import cache

import pytest

from tests.emulator import GAME_MODE, GAME_SUBMODE, Emulator
from tests.needs import needs_base_rom
from tests.test_coop_reserved import hits
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.rom import credits_staff as credits
from zora.rom.base_rom import PRG1_ROM_PATH, remember_repo_base_rom
from zora.rom.code_patch_data import PATCHES
from zora.rom.layout import CREDITS_POINTERS_HI_ADDRESS, CREDITS_POINTERS_LO_ADDRESS, CREDITS_RECORD_CPU_ADDRESSES
from zora.rom.player_settings import PlayerSettings
from zora.rom.text_encoding import BYTE_TO_CHAR

WIN_MODE, IS_UPDATING_MODE, LAST_WIN_SUBMODE = 0x13, 0x11, 4
CUR_SAVE_SLOT, QUEST_NUMBERS = 0x16, 0x62D
DYN_TILE_BUF, ROW_RECORD = 0x302, 32
CREDITS_ROW = 0x50A
ENDING_FRAMES = 4000
FIRST_QUEST, SECOND_QUEST = 0, 1
TILE_CHARACTERS = {**BYTE_TO_CHAR, credits.CREDITS_DOT: "."}
WALL = 0xFA
LOCKED = (*CREDITS_RECORD_CPU_ADDRESSES, 0xAD72)          # FP-LOCK-02's lines 12-15 (copyright kept)


# --- the file ---------------------------------------------------------------------------------------

def test_the_file_fits_the_box() -> None:
    staff = credits.load_staff()
    assert staff.title == "RANDOMIZER STAFF"
    texts = [row.text for row in staff.rows]
    assert texts[:2] == ["DESIGN AND", "PROGRAMMING... TETRALY"] and texts[-1] == "FCOUGHLIN"
    for name in ("THEREALQUANTAM", "IRENEPUNMASTER", "ZEROMEANING", "GROMFALLOON", "CUSTOMSHIELD", "GRANDPASZABO",
                 "HECCINHAYLEY", "ISUMATT", "PDXREX", "THEGOBONE", "BOGIESMALLS", "METALMACHINE", "CLAUDE OPUS 5.5",
                 "THE ZORA COMMUNITY", "ALDONUNEZ"):
        assert any(text.endswith(name) for text in texts), name
    assert all(len(text) <= credits.BOX_WIDTH for text in texts)


@pytest.mark.parametrize(("text", "message"), [
    ("[title] X\n" + "A" * 25, "is 25 columns"),
    ("[title] X\n" + "A" * 24, "from the left edge at most 23 fit"),
    ("[title] X\nA#B", "has no '#'"),
    ("[title] X\n[purple]\nA", "unknown tag"),
    ("A", "no \\[title\\]"),
    ("[title] X\n" + "A\n" * 57, "57 rows, and the box holds 56"),
])
def test_the_build_refuses_what_the_credits_cannot_show(text: str, message: str) -> None:
    with pytest.raises(credits.CreditsError, match=message):
        credits.parse_staff(text)


def test_lines_start_at_the_originals_left_edge_or_center() -> None:
    staff = credits.load_staff()
    left = [row for row in staff.rows if row.align == credits.LEFT and row.text]
    assert [row.text for row in left[:3]] == ["DESIGN AND", "PROGRAMMING... TETRALY", "MUSIC DESIGN"]
    assert all(credits.record(row.text, row.align)[1] == credits.LEFT_COLUMN for row in left)
    centered = [row for row in staff.rows if row.align == credits.CENTER and row.text]
    assert [row.text for row in centered][-1] == "FCOUGHLIN"
    assert credits.record("FCOUGHLIN", credits.CENTER)[1] == credits.BOX_FIRST_COLUMN + (24 - 9) // 2
    blurb = staff.rows[[row.text for row in staff.rows].index("BUILDS ON THE DESIGN"):]
    assert {row.color for row in blurb if row.text} == {credits.WHITE}


@needs_base_rom
def test_two_colors_need_an_empty_row_between() -> None:
    remember_repo_base_rom()
    staff = credits.parse_staff("[title] X\n[blue]\nA\n[red]\nB\n[blue]\nC")      # one pair shares a block
    with pytest.raises(credits.CreditsError, match="empty row between two colors"):
        credits.credits_writes(staff=staff)


# --- the tables -------------------------------------------------------------------------------------

def written(writes: list[tuple[int, bytes]], offset: int) -> bytes:
    return next(data for address, data in writes if address == offset)


@needs_base_rom
def test_the_tables_keep_prg0s_credits_around_the_box() -> None:
    base = remember_repo_base_rom()
    writes = credits.credits_writes(LOCKED)
    staff_lines = [row for row in credits.layout(credits.load_staff()).staff_rows.values() if row.text]
    added = len(staff_lines)
    low, high = written(writes, credits.LINES_LO), written(writes, credits.LINES_HI)
    lines = [lo | hi << 8 for lo, hi in zip(low, high, strict=True)]
    prg0 = [base[CREDITS_POINTERS_LO_ADDRESS + line] | base[CREDITS_POINTERS_HI_ADDRESS + line] << 8
            for line in range(credits.ORIGINAL_LINES)]
    assert lines[:12] == prg0[:12] and lines[12 + added:] == [*LOCKED, *prg0[16:]]
    assert written(writes, credits.LINE_COUNT)[0] == credits.ORIGINAL_LINES + added
    assert written(writes, credits.NAME_LINE_INDEX)[0] == 0x11 + added
    rows = credits.original_text_rows(base[credits.PAGE_MASKS:credits.PAGE_MASKS + 12])
    bits = written(writes, credits.TEXT_ROWS)

    def has_text(row: int) -> bool:
        return bool(bits[row // 8] & 0x80 >> row % 8)

    assert all(has_text(row if row < credits.INSERT_AT else row + credits.INSERTED_ROWS) for row in rows)
    old = base[credits.ATTRIBUTES:credits.ATTRIBUTES + credits.ORIGINAL_ATTRIBUTE_ROWS]
    new = written(writes, credits.NEW_ATTRIBUTES)
    assert new[:12] == old[:12] and new[28:40] == old[12:]
    placed = credits.layout(credits.load_staff())
    assert credits.INSERT_AT < placed.box[0] < placed.box[1] < credits.INSERT_AT + credits.INSERTED_ROWS
    assert not {credits.credits_row(row) for row in credits.LEFTOVER_ROWS} & {
        row for row, line in placed.staff_rows.items() if line.text}


def test_no_byte_is_z1rr_coops() -> None:
    offsets = {offset + i for offset, piece in PATCHES["fp-credits-01"] for i in range(len(piece)
                                                                                         if isinstance(piece, bytes)
                                                                                         else piece.length)}
    assert not hits(offsets)


# --- the emulator -----------------------------------------------------------------------------------

@cache
def finished(base_name: str) -> bytes:
    base = PRG1_ROM_PATH.read_bytes() if base_name == "prg1" else remember_repo_base_rom()
    return generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, base, PlayerSettings()).rom


def text(tiles: bytes) -> str:
    return "".join(TILE_CHARACTERS.get(tile, " ") for tile in tiles if tile != WALL).strip()


@cache
def drawn_rows(base_name: str, quest: int) -> tuple[str, ...]:
    """The ending's credits as drawn: each new row's text in order (DrawCredits' transfer
    record), up to the last win submode."""
    emu = Emulator(finished(base_name))
    emu.new_game()
    emu.run(10)
    emu[QUEST_NUMBERS + emu[CUR_SAVE_SLOT]] = quest
    emu[GAME_MODE], emu[IS_UPDATING_MODE], emu[GAME_SUBMODE] = WIN_MODE, 1, 0
    rows, row = [], emu[CREDITS_ROW]
    for _ in range(ENDING_FRAMES):
        emu.run(1)
        if emu[CREDITS_ROW] != row:
            row = emu[CREDITS_ROW]
            shown = text(bytes(emu[DYN_TILE_BUF + 3 + i] for i in range(ROW_RECORD)))
            if shown:
                rows.append(shown)
        if emu[GAME_SUBMODE] == LAST_WIN_SUBMODE:
            break
    assert emu[GAME_SUBMODE] == LAST_WIN_SUBMODE
    return tuple(rows)


@needs_base_rom
@pytest.mark.parametrize("base_name", ["prg0", "prg1"])
@pytest.mark.parametrize("quest", [FIRST_QUEST, SECOND_QUEST])
def test_the_credits_draw_the_box_between_prg0s(base_name: str, quest: int) -> None:
    if base_name == "prg1" and not PRG1_ROM_PATH.exists():
        pytest.skip(f"{PRG1_ROM_PATH.name} is not beside the PRG0 base")
    rows = drawn_rows(base_name, quest)
    staff = credits.load_staff()
    box = [staff.title, *(" ".join(row.text.split()) for row in staff.rows if row.text)]
    start = rows.index("STAFF")
    shown = [" ".join(row.split()) for row in rows]
    title = shown.index(staff.title)
    assert shown[title:title + len(box)] == box
    original = shown[start:title]
    assert original[1:3] == ["EXECUTIVE", "PRODUCER... H.YAMAUCHI"] and original[-1] == "COMPOSER...... KONCHAN"
    after = shown[title + len(box):]
    if quest == FIRST_QUEST:
        assert after[-1].endswith("1986 NINTENDO") and len(after) == 1      # FP-LOCK-02 blanks lines 12-14
    else:
        assert after[0] == "YOU ARE GREAT." and after[-2:] == ['"THE LEGEND OF ZELDA 1"', after[-1]]
