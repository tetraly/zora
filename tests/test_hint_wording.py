"""ZORA's hint wording (owner, 2026-10-09; zora/generate/steps/hint_text.py): the item-location
hints (HT-HINT-01's boss form, "THE <ITEM> <VERB> IN LEVEL-N.") and the level-location hints
("LEVEL-N LIES <PHRASE>.") with an opener when one more line fits.
  - every item (each name, each upgrade line, another player's item), level, region and opener
    renders within the box: at most three lines of 24, broken at word boundaries, with only
    characters the font has, and encodes;
  - the openers: from a copy of the hint step's stream (every other draw is unchanged), never
    repeated within a seed, at most one per hint; the same seed and flags give the same hints;
  - which hints appear and what they point to: a hint step with the openers removed draws exactly
    as before, and every reworded text is the item, level or region its record names."""
from __future__ import annotations

import copy
import re
import textwrap
from functools import cache

import pytest

from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.generate.steps import hint_text
from zora.generate.steps.hint_text import (
    FOREIGN_NAME,
    ITEM_VERBS,
    LINE_WIDTH,
    MAX_LINES,
    OPENERS,
    PROGRESSIVE_NAMES,
    REGION_PHRASES,
    SHOWN_CHARACTERS,
    UPGRADE_LINES,
    VANILLA_NAMES,
    ItemNames,
    encode_text,
    hint_lines,
    item_location_sentence,
    level_location_sentence,
    with_opener,
)
from zora.model.enums import Item
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom

LEVELS = range(1, 10)
ITEM_CODES = range(len(hint_text.ITEM_NAMES))
SEEDS = (1, 2, 3, 4, 5)
FOREIGN_CODE = 0x0F                         # how FINISH writes another player's item (five rupees)


def every_sentence() -> list[str]:
    """Every item-location and level-location sentence any seed can write."""
    sentences: set[str] = set()
    for code in ITEM_CODES:
        for names in (VANILLA_NAMES, PROGRESSIVE_NAMES, ItemNames(foreign_code=code)):
            sentences.update(item_location_sentence(code, level, names) for level in LEVELS)
    sentences.update(level_location_sentence(level, region) for level in LEVELS for region in REGION_PHRASES)
    return sorted(sentences)


def fits(lines: list[str]) -> bool:
    return (len(lines) <= MAX_LINES and all(len(line) <= LINE_WIDTH for line in lines)
            and set("".join(lines)) <= SHOWN_CHARACTERS)


# --- the words ------------------------------------------------------------------------------------

@pytest.mark.parametrize("opener", [None, *OPENERS])
def test_every_item_region_and_opener_combination_fits_the_box(opener: str | None) -> None:
    for sentence in every_sentence():
        lines = hint_lines(sentence) if opener is None else with_opener(opener, sentence)
        assert lines is not None, (opener, sentence)
        assert fits(lines), (opener, lines)
        assert " ".join(lines) == (sentence if opener is None else f"{opener} {sentence}")   # word breaks only
        assert encode_text(lines)


def test_the_item_sentences() -> None:
    assert item_location_sentence(Item.RAFT, 3) == "THE RAFT RESTS IN LEVEL-3."
    assert item_location_sentence(Item.MAGICAL_KEY, 8) == "THE MAGICAL KEY IS KEPT IN LEVEL-8."
    assert item_location_sentence(Item.SILVER_ARROWS, 9) == "THE SILVER ARROWS POINT IN LEVEL-9."
    assert item_location_sentence(Item.WOOD_ARROWS, 1) == "THE WOOD ARROWS AWAIT IN LEVEL-1."
    assert item_location_sentence(Item.WOOD_BOOMERANG, 7) == "THE WOOD BOOMERANG BECKONS IN LEVEL-7."
    assert item_location_sentence(Item.WOOD_SWORD, 2, PROGRESSIVE_NAMES) == "A SWORD UPGRADE SLUMBERS IN LEVEL-2."
    for item, expected in ((Item.SILVER_ARROWS, "AN ARROW UPGRADE AWAITS"),
                           (Item.RED_CANDLE, "A CANDLE UPGRADE FLICKERS"), (Item.BLUE_RING, "A RING UPGRADE RADIATES"),
                           (Item.MAGICAL_BOOMERANG, "A BOOMERANG UPGRADE BECKONS")):
        assert item_location_sentence(item, 4, PROGRESSIVE_NAMES) == f"{expected} IN LEVEL-4."
    assert item_location_sentence(FOREIGN_CODE, 5, ItemNames(foreign_code=FOREIGN_CODE)) == \
        f"{FOREIGN_NAME} AWAITS IN LEVEL-5."
    assert item_location_sentence(Item.BLUE_POTION, 6) == "THE BLUE POTION WAITS IN LEVEL-6."
    assert len(ITEM_VERBS) == 21 and set(hint_text.LINE_VERBS) == set(UPGRADE_LINES.values())


# The names a verb follows are ZORA's own (ITEM_NAMES); a plural name takes a plural verb.
PLURAL_NAMES = frozenset({Item.SILVER_ARROWS, Item.WOOD_ARROWS})
PLURAL_VERBS = frozenset({"POINT", "AWAIT"})


def test_each_verb_agrees_with_zoras_item_name() -> None:
    for item, verb in ITEM_VERBS.items():
        name = hint_text.ITEM_NAMES[item]
        assert item_location_sentence(item, 1) == f"THE {name} {verb} IN LEVEL-1."
        assert (item in PLURAL_NAMES) == (verb in PLURAL_VERBS) == name.endswith("S"), (name, verb)


def test_people_hints_name_the_region_by_its_phrase() -> None:
    """MEET <PERSON> <PHRASE>, and <PERSON> HAS <ITEM> <PHRASE> (or I HAVE), wrapped as before:
    every region with the longest names still fits the box."""
    from zora.generate.steps.hint_text import region_phrase
    for region in REGION_PHRASES:
        assert region_phrase(region) == REGION_PHRASES[region]
        for holder in ("I HAVE", "THE OLD WOMAN HAS", "THE MERCHANT HAS"):
            for item in ("THE MAGICAL BOOMERANG", FOREIGN_NAME, "A BOOMERANG UPGRADE"):
                place = region_phrase(region)
                lines = ([f"{holder} {item} {place}"] if len(f"{holder} {item} {place}") <= LINE_WIDTH
                         else [holder, f"{item} {place}"] if len(f"{item} {place}") <= LINE_WIDTH
                         else [holder, item, place])
                assert fits(lines), lines
        assert fits(["MEET THE OLD WOMAN", region_phrase(region)])


def test_the_level_sentences() -> None:
    assert [level_location_sentence(1, region) for region in REGION_PHRASES] == [
        "LEVEL-1 LIES HIGH IN DEATH MOUNTAIN.", "LEVEL-1 LIES BY THE GRAVEYARD.", "LEVEL-1 LIES IN THE DEAD WOODS.",
        "LEVEL-1 LIES NEAR START.", "LEVEL-1 LIES AROUND A LAKE.", "LEVEL-1 LIES ALONG A RIVER.",
        "LEVEL-1 LIES BY THE SHORE.", "LEVEL-1 LIES HIDDEN IN A FOREST.", "LEVEL-1 LIES UP IN THE LOST HILLS.",
        "LEVEL-1 LIES IN THE DRY DESERT."]
    assert set(REGION_PHRASES) == set(hint_text.REGION_TABLE)


def test_the_font_has_no_colon_so_no_opener_uses_one() -> None:
    assert ":" not in SHOWN_CHARACTERS and not any(":" in opener for opener in OPENERS)
    assert len(OPENERS) == len(set(OPENERS)) == 10


# --- seeds -------------------------------------------------------------------------------------

pytestmark_rom = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")
REWORDED = re.compile(r"(?:.* )?(?:THE .+|A .+ UPGRADE|AN .+ UPGRADE|ANOTHER PLAYER'S ITEM) .+ IN LEVEL-\d\.|"
                      r"(?:.* )?LEVEL-\d LIES .+\.")


def shown(text: str) -> str:
    return " ".join(line.strip("~ ") for line in text.split("|")).strip()


# CP-5 with B09 off, which Progressive Items refuses (PI-FLAG-03)
WITHOUT_CANDLES = "8hq4BeR1JXo7ygQD!vLBwTXdKSUJ3A"


@cache
def hints(seed: int, zora: str = "") -> tuple[str, ...]:
    flags = WITHOUT_CANDLES if zora else MVP_BASELINE_LEVEL_ENCODING_OFF
    rom = generate_rom(flags, seed, remember_repo_base_rom(), zora_flag_string=zora).rom
    return tuple(shown(quote.text) for quote in parse_rom(rom).quotes)


def opener_of(text: str) -> str | None:
    return next((opener for opener in OPENERS if text.startswith(opener + " ")), None)


@pytestmark_rom
@pytest.mark.parametrize("seed", SEEDS)
def test_openers_are_never_repeated_within_a_seed(seed: int) -> None:
    used = [opener for text in hints(seed) if (opener := opener_of(text)) is not None]
    assert used and len(used) == len(set(used)) <= len(OPENERS)
    assert all(REWORDED.fullmatch(text) for text in hints(seed) if opener_of(text) is not None)


@pytestmark_rom
def test_the_same_seed_and_flags_give_the_same_hints() -> None:
    first = hints(1)
    hints.cache_clear()
    assert hints(1) == first
    assert hints(2) != first


@pytestmark_rom
def test_the_openers_move_no_other_draw(monkeypatch: pytest.MonkeyPatch) -> None:
    """With the openers left out, every text is the same apart from its opener, and the hint step
    leaves the main stream where it did: which hints appear and what they point to are
    unchanged."""
    from zora.generate.pipeline import build, plan

    built = build(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 1), remember_repo_base_rom())
    state, assignment = built.result.item_shuffle_result, built.result.hint_assignment
    assert state is not None and assignment is not None

    def run(without_openers: bool) -> tuple[list[str], int]:
        from zora.generate.rng import Rng
        rng = Rng(12345)
        world = copy.deepcopy(built.world)
        if without_openers:
            monkeypatch.setattr(hint_text, "add_openers", lambda *_args: None)
        out = hint_text.generate_hint_text(world, state, assignment, rng)
        monkeypatch.undo()
        return [quote.text for quote in out.quotes], rng.below(1 << 30)

    with_texts, after = run(False)
    without_texts, after_without = run(True)
    assert after == after_without
    opened = 0
    for opened_text, plain_text in zip(with_texts, without_texts, strict=True):
        opener = opener_of(shown(opened_text))
        if opener is None:
            assert opened_text == plain_text
        else:
            opened += 1
            assert shown(opened_text) == f"{opener} {shown(plain_text)}"
    assert opened


# HT-HINT-01's people hints: MEET <PERSON> ..., and the white-sword cave item's holder
PEOPLE_HINT = re.compile(r"MEET (ME|THE (OLD MAN|OLD WOMAN|MERCHANT|MOBLIN|HUMAN)) |"
                         r"(I HAVE|THE (OLD MAN|OLD WOMAN|MERCHANT|MOBLIN|HUMAN) HAS) (THE|A|AN|ANOTHER) ")


@pytestmark_rom
@pytest.mark.parametrize("seed", SEEDS)
def test_people_hints_in_a_seed_use_the_phrases(seed: int) -> None:
    texts = [text for text in hints(seed) if PEOPLE_HINT.match(text) and opener_of(text) is None]
    assert texts
    assert not any(re.search(r"\bREGION \d", text) for text in texts), texts
    assert all(text.endswith(tuple(REGION_PHRASES.values())) for text in texts), texts


@pytestmark_rom
def test_a_progressive_seed_names_sword_upgrades_and_lines() -> None:
    texts = " ".join(hints(1, "2.O") + hints(2, "2.O") + hints(3, "2.O"))
    assert "UPGRADE" in texts and "HOLDS" not in texts
    assert not re.search(r"\bREGION \d", " ".join(text for text in hints(1) if "LEVEL-" in text))


def test_wrapping_never_splits_level_n() -> None:
    assert textwrap.wrap("X" * 20 + " LEVEL-3", LINE_WIDTH, break_on_hyphens=False)[-1] == "LEVEL-3"
    assert all("LEVEL-" not in line or re.search(r"LEVEL-\d", line)
               for sentence in every_sentence() for line in hint_lines(sentence))
