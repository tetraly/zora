"""The random hint pool (zora/generate/steps/hint_pool.txt): its wording, routing classes
and padding, where its quotes go (HT-TEXT-02), and where the 45 slot texts
go (HT-TEXT-03)."""
import itertools
import math

import pytest

from zora.rom.base_rom import BASE_ROM_PATH
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_world, plan
from zora.rom.parse.rom_file import parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom
from zora.rom.game_config import GameConfig, HintMode
from zora.rom.layout import (
    CONSTERNATION_HINT_SLOTS, EXT_HINT_DATA_ROM_END, EXT_HINT_DATA_ROM_START, EXTENDED_HINT_POINTERS,
    HINT_TEXT_SPILL_FILL, QUOTE_DATA_ADDRESS, REFUSAL_TEXT_ADDRESS, hint_text_regions, place_hint_texts,
)
from zora.model.overworld import Quote
from zora.generate.steps.change_sword_hearts import MAGICAL_SWORD_HEARTS, WHITE_SWORD_HEARTS
from zora.generate.rng import Rng
from zora.generate.steps.hint_text import (
    PLACEHOLDER_TEXT, POOL, POOL_CLASSES, POOL_FILE, SLOT_COUNT, UNSHOWN_SLOTS, PoolEntry, encode_text,
    place_pool, quote_problems, shown_class_slots,
)

BANK = EXT_HINT_DATA_ROM_END - EXT_HINT_DATA_ROM_START
HINT_TEXT_SPILL_START = QUOTE_DATA_ADDRESS + 2 * CONSTERNATION_HINT_SLOTS
SPILL = REFUSAL_TEXT_ADDRESS - HINT_TEXT_SPILL_START


HEART_REQUIREMENTS = list(itertools.product(WHITE_SWORD_HEARTS, MAGICAL_SWORD_HEARTS))
SHOWN_SLOTS = [slot for slot in range(SLOT_COUNT) if slot not in UNSHOWN_SLOTS]
# The one class with no strings of its own: its slots are served by the
# quotes of slot 8, slot 16 and slot 14 or 15 (owner ruling, review 37).
SERVED_BY_OTHERS = {"slot 8, 16 or 14/15": ("slot 8", "slot 16", "slot 14 or 15")}
# Classes padded beyond their minimum so that an informative candidate
# competing in their slot's draw shows at the spec's odds (owner ruling,
# 2026-10-03): slot 19's white-sword item hint (HT-TEXT-02).
ODDS_PADDED = {"slot 19"}


def test_pool_is_the_owners_routed_quotes_with_provenance() -> None:
    from importlib.resources import files
    text = files("zora.generate.steps").joinpath(POOL_FILE).read_text(encoding="utf-8")
    assert "owner-quotes-routed.tsv" in text and "afb5732" in text and "docs/ui-provenance.md" in text
    owner = [entry for entry in POOL if not entry.placeholder]
    assert len(owner) == 174
    assert sum(entry.reserved for entry in owner) == 12
    assert sum(entry.hearts is not None for entry in owner) == 27
    assert len({entry.lines for entry in POOL}) == len(POOL)
    for entry in POOL:
        assert quote_problems(list(entry.lines)) == [], entry


def test_placeholders_are_numbered_and_easy_to_find() -> None:
    placeholders = [entry for entry in POOL if entry.placeholder]
    assert [entry.lines for entry in placeholders] == [
        (f"{PLACEHOLDER_TEXT} {number}",) for number in range(1, len(placeholders) + 1)]
    assert not any(PLACEHOLDER_TEXT in "|".join(entry.lines) for entry in POOL if not entry.placeholder)


def _guaranteed(entries: list[PoolEntry], routing_class: str) -> int:
    """How many of a class's quotes can be drawn in every seed, whatever
    hearts FP-SWORD-01 asks for."""
    return min(sum(1 for entry in entries if entry.routing_class == routing_class and entry.slots(white, magical))
               for white, magical in HEART_REQUIREMENTS)


@pytest.mark.parametrize("routing_class", sorted(POOL_CLASSES))
def test_each_class_is_padded_to_exactly_its_shown_slots(routing_class: str) -> None:
    """A class can have to serve each of its shown slots in one seed, so it
    holds at least that many drawable quotes, and no placeholder more."""
    needed = len(shown_class_slots(routing_class))
    entries = list(POOL)
    if routing_class in SERVED_BY_OTHERS:
        assert _guaranteed(entries, routing_class) == 0
        for slot in shown_class_slots(routing_class):
            assert any(slot in shown_class_slots(other) for other in SERVED_BY_OTHERS[routing_class])
        return
    assert _guaranteed(entries, routing_class) >= needed
    padding = [entry for entry in entries if entry.routing_class == routing_class and entry.placeholder]
    if routing_class in ODDS_PADDED:
        return                          # padded for the hint's odds, tested below
    if padding:
        entries.remove(padding[-1])
        assert _guaranteed(entries, routing_class) == needed - 1


@pytest.mark.parametrize("white, magical", HEART_REQUIREMENTS)
def test_every_shown_slot_gets_candidates_and_no_quote_twice(white: int, magical: int) -> None:
    by_lines = {"|".join(entry.lines): entry for entry in POOL}
    for seed in range(40):
        candidates = place_pool(Rng(seed), white, magical)
        for slot in SHOWN_SLOTS:
            assert candidates[slot], (seed, slot)
        placed = ["|".join(lines) for slot in candidates for lines in candidates[slot]]
        assert len(placed) == len(set(placed))
        for slot, texts in candidates.items():
            for lines in texts:
                entry = by_lines["|".join(lines)]
                assert slot in entry.slots(white, magical)
                assert not entry.reserved
        # Owner rulings: slot 0 shows only its own quotes; slot 9's own
        # quotes show nowhere else.
        assert {by_lines["|".join(lines)].routing_class for lines in candidates[0]} == {"slot 0 (owner ruling)"}
        for slot in SHOWN_SLOTS:
            if slot != 9:
                assert all(by_lines["|".join(lines)].routing_class != "slot 9 (owner ruling)"
                           for lines in candidates[slot])


def test_heart_count_quotes_follow_the_requirement() -> None:
    candidates = place_pool(Rng(5), 4, 13)
    shown = {"|".join(lines) for texts in candidates.values() for lines in texts}
    for entry in POOL:
        if entry.hearts is not None:
            slot, count = entry.hearts
            assert ("|".join(entry.lines) in shown) == (slot == 19 and count == 4), entry


def test_quotes_that_cannot_be_shown_as_written_are_named() -> None:
    assert quote_problems(["INCLUDE: FULL HEALTH"]) == ["no tile for ':'"]
    assert quote_problems(["A & B"]) == ["no tile for '&'"]
    assert quote_problems(["A", "B", "C", "D"]) == ["4 lines (at most 3)"]
    assert quote_problems(["X" * 25])[0].endswith("is 25 characters (at most 24)")
    assert quote_problems([" ... WOOD?", "ZZZZZZZZ... "]) == []      # spaces are shown as written


def test_comma_and_double_quote_emit_their_tiles() -> None:
    """Owner ruling (2026-10-02), departing from HT-TEXT-01: ZORA's wording
    shows the comma ($28) and the double quote mark ($2D); the colon stays
    unshown."""
    assert quote_problems(["RED, RED, WINE"]) == []
    assert quote_problems(['"S WORDS"']) == []
    assert encode_text(['A,"']) == [0x25] * 10 + [0x0A, 0x28, 0x2D | 0xC0]
    assert encode_text(["A:B"]) == [0x25] * 11 + [0x0A, 0x0B | 0xC0]


def test_the_regions_of_each_pointer_count() -> None:
    """PI-HINT-01/02: the bank ends at $BE40 (file 0x7E50) whatever the mode; the overflow region
    starts after the mode's pointer table and ends at the refusal text. The plan's capacities:
    1,744 + 1,258 = 3,002 bytes for 38 pointers, 1,744 + 1,244 = 2,988 for 45."""
    assert EXT_HINT_DATA_ROM_END == 0x7E50 and BANK == 1744
    assert hint_text_regions(EXTENDED_HINT_POINTERS) == ((0x7780, 0x7E50), (0x405C, 0x4546))
    assert hint_text_regions(CONSTERNATION_HINT_SLOTS) == ((0x7780, 0x7E50), (0x406A, 0x4546))
    assert [sum(end - start for start, end in hint_text_regions(count))
            for count in (EXTENDED_HINT_POINTERS, CONSTERNATION_HINT_SLOTS)] == [3002, 2988]


def test_texts_fill_the_bank_then_the_overflow_region() -> None:
    slots = CONSTERNATION_HINT_SLOTS
    assert place_hint_texts([10, 20], slots) == [EXT_HINT_DATA_ROM_START, EXT_HINT_DATA_ROM_START + 10]
    offsets = place_hint_texts([BANK - 5, 10, 7], slots)
    assert offsets == [EXT_HINT_DATA_ROM_START, HINT_TEXT_SPILL_START, HINT_TEXT_SPILL_START + 10]
    assert place_hint_texts([BANK, SPILL], slots) == [EXT_HINT_DATA_ROM_START, HINT_TEXT_SPILL_START]
    with pytest.raises(ValueError, match="HT-TEXT-03"):
        place_hint_texts([BANK, SPILL, 1], slots)
    assert place_hint_texts([BANK, 1], EXTENDED_HINT_POINTERS)[1] == QUOTE_DATA_ADDRESS + 2 * EXTENDED_HINT_POINTERS


def test_spilled_texts_round_trip_and_stay_in_their_regions() -> None:
    """Forty-five copies of the longest quote that still fits the regions need more than the
    bank: the rest go to the overflow region, and the parser reads them back in slot order."""
    base = BASE_ROM_PATH.read_bytes()
    chosen = plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 1)
    world, _ = generate_world(chosen, base)
    capacity = sum(end - start for start, end in hint_text_regions(CONSTERNATION_HINT_SLOTS))
    body = max((bytes(encode_text(list(entry.lines))) for entry in POOL),
               key=lambda text: len(text) if len(text) * 45 <= capacity else 0)
    plain = serialize_to_rom(world, base, config=chosen.config)
    world.hint_text_bytes = (body,) * 45
    assert len(body) * 45 > BANK
    rom = serialize_to_rom(world, base, config=chosen.config)
    assert parse_rom(rom).hint_text_bytes == (body,) * 45
    in_bank = BANK // len(body)
    bank_end = EXT_HINT_DATA_ROM_START + in_bank * len(body)
    assert set(rom[bank_end:EXT_HINT_DATA_ROM_END]) == {HINT_TEXT_SPILL_FILL}
    assert rom[HINT_TEXT_SPILL_START:HINT_TEXT_SPILL_START + len(body)] == body
    # Nothing past the overflow region moves: the FP-TRIF-01 refusal text follows it.
    assert rom[REFUSAL_TEXT_ADDRESS:EXT_HINT_DATA_ROM_START] == plain[REFUSAL_TEXT_ADDRESS:EXT_HINT_DATA_ROM_START]
    # PI-HINT-01: fp-prog-01's bank-1 segment ($BE40) is never written by the texts.
    assert rom[EXT_HINT_DATA_ROM_END:EXT_HINT_DATA_ROM_END + 0x80] == base[EXT_HINT_DATA_ROM_END:EXT_HINT_DATA_ROM_END + 0x80]


def test_community_overflow_round_trips() -> None:
    """PI-HINT-02: COMMUNITY's 38 texts overflow into the old text area after its pointer
    table when they do not fit the bank, and the parser reads them back through the pointers."""
    base = BASE_ROM_PATH.read_bytes()
    world = parse_rom(base)
    longest = max((entry.lines for entry in POOL), key=lambda quote: len(encode_text(list(quote))))
    text = "|".join(longest)
    world.quotes = [Quote(quote_id=qid, text=text) for qid in range(EXTENDED_HINT_POINTERS)]
    config = GameConfig(hint_mode=HintMode.COMMUNITY)
    rom = serialize_to_rom(world, base, config=config)
    pointers = [rom[QUOTE_DATA_ADDRESS + 2 * qid] | rom[QUOTE_DATA_ADDRESS + 2 * qid + 1] << 8
                for qid in range(EXTENDED_HINT_POINTERS)]
    assert max(pointers) < 0xBE40 and min(pointers) < 0xB770          # some text spilled
    reread = parse_rom(rom, config)
    assert [quote.text.replace("~", "") for quote in reread.quotes] == [quote.text for quote in world.quotes]
    # (COMMUNITY's centring pads each line with "~", which a second serialization centres
    # again, so it is compared as text, not re-serialized byte for byte.)


def _spec_white_sword_hint_odds() -> float:
    """The chance that slot 19 draws the white-sword item candidate from the
    spec's pool (HT-TEXT-02): it competes with the 2 slot-19 strings, the
    "slot 1 or 19" strings that land there (10, each with chance 1/2) and the
    base-draw strings that land there (308 unrouted and 51 that keep the base
    draw, each with chance 1/44)."""
    def binomial(n: int, p: float) -> list[float]:
        return [math.comb(n, k) * p ** k * (1 - p) ** (n - k) for k in range(n + 1)]
    return sum(pair * base / (1 + 2 + paired + drawn)
               for paired, pair in enumerate(binomial(10, 1 / 2))
               for drawn, base in enumerate(binomial(308 + 51, 1 / 44)))


def test_slot_19_hint_shows_at_the_specs_odds() -> None:
    """Owner ruling (2026-10-03): slot 19's class is padded so the white-sword
    item hint shows about as often as with the spec's pool, about 1 time in
    15.5; one placeholder more or fewer would move it further away."""
    others = [len(place_pool(Rng(seed), white, magical)[19])
              for white, magical in HEART_REQUIREMENTS for seed in range(40)]

    def odds(extra: int) -> float:
        return sum(1 / (1 + count + extra) for count in others) / len(others)

    spec = _spec_white_sword_hint_odds()
    assert abs(odds(0) - spec) < min(abs(odds(-1) - spec), abs(odds(1) - spec))
