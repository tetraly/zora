"""No person text's line ends on the pad tile (a player's report, 2026-10-29, fixed in aa19038).

Each line of a person text carries its line-break or end bits on its last tile, and the person text
drawer (Z_01.asm @WriteChar) skips the pad tile $25 before it reads them: a line ending on one runs
on past the box's right edge, and a text whose end bits fall on one never ends. (The ending's
thank-you text drawer, Z_02, skips it the same way; ZORA never writes that text.) The other texts
ZORA writes (the credits, the opening story, the boss-sound and level labels, the title and
statistics screens) have no line bits and are drawn by routines that never skip a tile.

Checked here on every writer of person text: the hint pool's quotes and hint_text.encode_text, the
toll texts, the level-9 refusal text under Specific Triforces with every level word, Swordlish's
text for every count; and (slow) on finished ROMs, every text the pointer table reaches and
Swordlish's, over every hint style, Specific Triforces, the Book and Swordlish, with each listed
level word and custom ones.

Every line encoder closes its line through text_encoding.closed_line (a last pad tile becomes a
space), so a line can no longer end on one whatever its characters: a character the font lacks
(written as the pad tile by the quote encoder), a "~", or a line with no shown character. Checked
on each encoder with such lines; and (slow) on finished ROMs of every Archipelago flag case
(tests/archipelago_cases.py, 94 varied settings), and on Archipelago's FINISH texts with another
player's item in every cave place."""
import itertools
from functools import cache

import pytest

from tests.archipelago_cases import FLAG_CASES as ARCHIPELAGO_CASES
from tests.needs import needs_base_rom
from tests.test_assignment import _built as archipelago_built
from tests.test_assignment import identity
from tests.test_foreign_hints import FINISH_SEEDS
from zora.flags import zora_flags
from zora.flags.codec import decode, encode
from zora.flags.fields import HintStyle, Level9Requirement, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import SWORDLISH_PIECES, Swordlish, ZoraFlags
from zora.generate.finish import FOREIGN
from zora.generate.pipeline import finish_world, generate_rom
from zora.generate.steps.hint_text import FOREIGN_NAME, POOL, _encode_line, encode_text
from zora.model.enums import Item, TollOption
from zora.model.level_9_gate import TRIFORCE_LEVELS
from zora.model.rooms import LifeOrMoneyToll
from zora.rom import swordlish
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.level_9_entrance import chosen_levels_text
from zora.rom.person_code import toll_text
from zora.rom.player_settings import (
    LEVEL_WORD_CHOICES,
    PlayerSettings,
    apply_player_settings,
    encoded_hint_lines,
    hint_pointer_count,
    hint_text_offset,
    text_body,
)
from zora.rom.serialize.features import encoded_refusal_text
from zora.rom.serialize.text import _encode_quote
from zora.rom.text_encoding import (
    BYTE_TO_CHAR,
    CHAR_TO_BYTE,
    LINE_END_TILE,
    QUOTE_CHAR_MASK,
    QUOTE_EMPTY,
    QUOTE_END_BITS,
    QUOTE_LINE1_BIT,
    QUOTE_LINE2_BIT,
    closed_line,
)

PAD_TILE = CHAR_TO_BYTE["~"]
WORDS = (*LEVEL_WORD_CHOICES, "X", "OH NO", "R2-D2", "A.B,C", "AB CDEF", "DUNGEON")


def ends_on_pad(text: bytes) -> bool:
    """Does a line of this encoded text end on the pad tile?"""
    return any(byte & QUOTE_END_BITS and byte & QUOTE_CHAR_MASK == PAD_TILE for byte in text)


def test_the_pool_quotes() -> None:
    for entry in POOL:
        assert not ends_on_pad(bytes(encode_text(list(entry.lines)))), entry


def test_the_toll_texts() -> None:
    for first, second in itertools.product((TollOption.LIFE, TollOption.MAX_BOMBS), TollOption):
        assert not ends_on_pad(toll_text(LifeOrMoneyToll(first, second, key_cost=2, money_cost=30))), (first, second)


@pytest.mark.parametrize("word", WORDS)
def test_the_refusal_texts(word: str) -> None:
    for count in range(1, len(TRIFORCE_LEVELS) + 1):
        for levels in itertools.combinations(TRIFORCE_LEVELS, count):
            text = encoded_refusal_text(chosen_levels_text(frozenset(levels), word))
            assert not ends_on_pad(text), (word, levels)


def test_the_swordlish_texts() -> None:
    for pieces in SWORDLISH_PIECES:
        assert not ends_on_pad(swordlish.encoded_text(pieces)), pieces


# Lines a line encoder must close: ending on a character the font lacks, on "~", with no shown
# character at all, and an ordinary one.
AWKWARD_LINES = ("WHERE IS IT;", "A ~", "~", ":::", "", "   ", "IT'S NOT HERE")


def test_closed_line() -> None:
    pad = CHAR_TO_BYTE["~"]
    assert closed_line([CHAR_TO_BYTE["A"], pad]) == [CHAR_TO_BYTE["A"], LINE_END_TILE]
    assert closed_line([pad, CHAR_TO_BYTE["A"]]) == [pad, CHAR_TO_BYTE["A"]]
    assert closed_line([]) == []


@pytest.mark.parametrize("center", [False, True])
def test_the_quote_encoder_closes_every_line(center: bool) -> None:
    """serialize.text._encode_quote: the Community and Helpful hints (centered), the vanilla text
    re-encoded (not centered), the refusal and Swordlish texts; the font's missing characters are
    written as pad tiles."""
    for lines in itertools.product(AWKWARD_LINES, repeat=3):
        text = _encode_quote("|".join(lines), center=center)
        assert not ends_on_pad(bytes(text)), lines


def line_marks(text: list[int]) -> list[int]:
    """The marks on each line's last tile, in order."""
    return [byte & QUOTE_END_BITS for byte in text if byte & QUOTE_END_BITS]


@pytest.mark.parametrize("center", [False, True])
@pytest.mark.parametrize("text", ["|ONE|TWO", "ONE||TWO", "ONE|TWO|", "|ONE||TWO|"])
def test_a_blank_line_takes_no_mark(text: str, center: bool) -> None:
    """A blank first, middle or last line is left out of the quote encoder's text: the lines it
    writes read as without it, each mark on its own line (line 1's, then the end's)."""
    blank = " " if center else ""                 # centered, a line of spaces is blank too
    for written in (text, text.replace("||", f"|{blank}|")):
        encoded = _encode_quote(written, center=center)
        assert encoded == _encode_quote("ONE|TWO", center=center), written
        assert line_marks(encoded) == [QUOTE_LINE1_BIT, QUOTE_END_BITS], written


@pytest.mark.parametrize("center", [False, True])
def test_three_lines_take_their_three_marks(center: bool) -> None:
    for text in ("ONE|TWO|THREE", "|ONE|TWO||THREE|"):
        assert line_marks(_encode_quote(text, center=center)) == [QUOTE_LINE1_BIT, QUOTE_LINE2_BIT, QUOTE_END_BITS]


@pytest.mark.parametrize("center", [False, True])
def test_a_text_of_blank_lines_is_the_empty_text(center: bool) -> None:
    """Never a text of no bytes, whose pointer would read the next text."""
    for text in ("", "|", "||"):
        assert _encode_quote(text, center=center) == [QUOTE_EMPTY]


def test_the_hint_line_encoders_close_every_line() -> None:
    """hint_text.encode_text (every generated hint style; it drops the missing characters, so a line
    of them is all padding) and player_settings.encoded_hint_lines (a rewrapped relabeled hint)."""
    for lines in itertools.product(AWKWARD_LINES, repeat=3):
        assert not ends_on_pad(bytes(encode_text(list(lines)))), lines
        assert _encode_line(":::")[-1] == LINE_END_TILE
    for lines in itertools.product(("~~~", "A~", "~A"), repeat=3):
        assert not ends_on_pad(encoded_hint_lines(list(lines))), lines


def flag_cases() -> dict[str, tuple[str, str]]:
    """(the flag string, the ZORA flag string) of each case."""
    base = decode(MVP_BASELINE_LEVEL_ENCODING_OFF)
    cases = {f"{style.name} specific {specific}": (encode(base.updated(options={
        "C03": style, **({"C08": Level9Requirement.SPECIFIC_PIECES} if specific else {})})), "")
             for style in HintStyle if style != HintStyle.RANDOM for specific in (False, True)}
    cases["book"] = (encode(base.updated(toggles={"B48": ThreeState.ON})), "")
    cases["swordlish"] = (MVP_BASELINE_LEVEL_ENCODING_OFF, zora_flags.encode(ZoraFlags(swordlish=Swordlish.ON)))
    return cases


@cache
def finished(case: str) -> bytes:
    flags, zora = flag_cases()[case]
    return generate_rom(flags, 1, remember_repo_base_rom(), zora_flag_string=zora).rom


def person_texts(rom: bytes) -> dict[str, bytes]:
    """Every text the person drawer can reach: each pointer slot's (the toll's and the refusal's
    included) and Swordlish's, which its hook addresses."""
    texts = {f"slot {slot}": text_body(rom, hint_text_offset(rom, slot)) for slot in range(hint_pointer_count(rom))}
    if swordlish.parsed_pieces(rom):
        texts["swordlish"] = text_body(rom, swordlish.TEXT)
    return texts


@needs_base_rom
@pytest.mark.slow
@pytest.mark.parametrize("case", list(flag_cases()))
def test_finished_roms(case: str) -> None:
    rom = finished(case)
    assert "swordlish" in person_texts(rom) or case != "swordlish"
    for word in WORDS:
        written = apply_player_settings(rom, PlayerSettings(level_word=word))
        bad = [name for name, text in person_texts(written).items() if ends_on_pad(text)]
        assert not bad, (case, word, bad)


@cache
def archipelago_case_rom(case: str) -> bytes:
    flags, zora = ARCHIPELAGO_CASES[case]
    return generate_rom(flags, 1, remember_repo_base_rom(), zora_flag_string=zora).rom


@needs_base_rom
@pytest.mark.slow
@pytest.mark.parametrize("case", list(ARCHIPELAGO_CASES))
def test_finished_roms_of_varied_settings(case: str) -> None:
    """Every person text of seed 1 under each of the 94 varied settings, with PRG0's word and a
    short custom one (relabeled lines padded at their ends)."""
    rom = archipelago_case_rom(case)
    for word in ("LEVEL", "X"):
        written = rom if word == "LEVEL" else apply_player_settings(rom, PlayerSettings(level_word=word))
        bad = [name for name, text in person_texts(written).items() if ends_on_pad(text)]
        assert not bad, (case, word, bad)


@needs_base_rom
@pytest.mark.slow
@pytest.mark.parametrize("case", ["baseline", "helpful hints", "every owner flag on", "pegasus boots"])
def test_archipelago_texts_naming_another_player_s_item(case: str) -> None:
    """Archipelago's FINISH with another player's item in every cave place: the texts as the ROM
    writer encodes them (the quotes centered, or the generated hint bytes) close every line."""
    named = 0
    for seed in FINISH_SEEDS:
        built = archipelago_built(case, seed)
        assignment = identity(built)
        received = []
        for place in built.places:
            if not place.is_dungeon:
                item = assignment[place.name]
                assert isinstance(item, Item)
                received.append(item)
                assignment[place.name] = FOREIGN
        world, _ = finish_world(built, assignment, received=received)
        texts = [bytes(_encode_quote(quote.text, center=True)) for quote in world.quotes]
        texts += list(world.hint_text_bytes or ())
        shown = [quote.text.replace("|", " ") for quote in world.quotes]
        shown += ["".join(BYTE_TO_CHAR.get(byte & QUOTE_CHAR_MASK, "") for byte in text)
                  for text in world.hint_text_bytes or ()]
        named += any(FOREIGN_NAME in " ".join(text.replace("~", " ").split()) for text in shown)
        assert not [text for text in texts if ends_on_pad(text)], (case, seed)
    assert named, case                      # the wording is in the texts checked
