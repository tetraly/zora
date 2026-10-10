"""Hints naming a place that holds another player's item (Archipelago, External mode; owner
decisions 2026-10-08, docs/archipelago.md): the text names it "another player's item", never
"five rupees" (what the ROM shows there) and never which item it is. Each hinted place gets
another player's item in turn: the white-sword cave (its requirement text and the person-name
text naming its item), the coast (the ladder requirement), the magical-sword cave (its own text),
and the silver arrows' place (the level-9 trio's silver-arrow or arrow-upgrade text). ZORA mode's
names are unaffected (verify.sh, the 32-ROM matrix)."""
from dataclasses import replace

import pytest

from tests.archipelago_cases import FLAG_CASES
from tests.test_assignment import _built, identity
from zora.generate.finish import FOREIGN, FOREIGN_ITEM, rebuild_tracking, with_tracking
from zora.generate.pipeline import Built, finish_world
from zora.generate.steps.hint_text import (
    FOREIGN_NAME,
    HOLDER_SLOT,
    PROGRESSIVE_NAMES,
    SLOT_COUNT,
    VANILLA_NAMES,
    ItemNames,
    Requirement,
    level9_trio_texts,
    magical_sword_cave_text,
    quote_problems,
    requirement_candidates,
    requirement_text,
    write_person_name_texts,
)
from zora.model.enums import Item
from zora.model.game_world import GameWorld
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora.rom.text_encoding import CHAR_TO_BYTE

FOREIGN_WORDS = "ANOTHER PLAYER'S ITEM"
RUPEES_WORDS = "RUPEES"
APOSTROPHE_TILE = 0x2A
SEEDS = (1, 2, 3)


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("vanilla ROM missing")
    return remember_repo_base_rom()


def foreign_names(built: Built) -> ItemNames:
    names = PROGRESSIVE_NAMES if built.plan.zora.progressive_items else VANILLA_NAMES
    return replace(names, foreign_code=FOREIGN_ITEM)


def _says_foreign(lines: list[str]) -> bool:
    text = " ".join(lines)
    assert not quote_problems(lines), lines
    assert RUPEES_WORDS not in text, lines
    return FOREIGN_WORDS in text


def _with_foreign(built: Built, name: str) -> tuple[GameWorld, list[Item]]:
    """The world with another player's item in the named place, and the item it displaced
    (which this player then receives)."""
    assignment = identity(built)
    displaced = assignment[name]
    assert isinstance(displaced, Item)
    assignment[name] = FOREIGN
    world, finished = finish_world(built, assignment, received=[displaced])
    assert finished.sanity is not None and finished.sanity.granted is None
    return world, [displaced]


def _requirement(world: GameWorld, built: Built, white_sword_cave: bool) -> list[str]:
    """The requirement text naming the white-sword cave's item, or the coast's (the ladder's)."""
    candidates = requirement_candidates(world, [])
    if white_sword_cave:
        candidate = next((c for c in candidates if c.white_sword_cave), None)
        if candidate is None:                      # the cave's screen needs no means
            pytest.skip("this seed's white-sword cave has no requirement text")
    else:
        candidate = next(c for c in candidates if c.form == "ladder")
    return requirement_text(candidate, foreign_names(built))


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_the_white_sword_cave(base: bytes, case: str, seed: int) -> None:
    built = _built(case, seed)
    world, _ = _with_foreign(built, "White Sword Cave")
    slots: list[list[str] | None] = [None] * SLOT_COUNT
    write_person_name_texts(world, slots, foreign_names(built))
    holder = slots[HOLDER_SLOT]
    assert holder is not None and _says_foreign(holder) and FOREIGN_NAME in holder, holder
    candidates = requirement_candidates(world, [])
    for candidate in (c for c in candidates if c.white_sword_cave):
        assert _says_foreign(requirement_text(candidate, foreign_names(built)))


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_the_coast(base: bytes, case: str, seed: int) -> None:
    built = _built(case, seed)
    world, _ = _with_foreign(built, "Coast")
    assert _says_foreign(_requirement(world, built, white_sword_cave=False))


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("case", ["magical sword and letter", "every ZORA flag on"])
def test_the_magical_sword_cave(base: bytes, case: str, seed: int) -> None:
    built = _built(case, seed)
    world, _ = _with_foreign(built, "Magical Sword Cave")
    lines = magical_sword_cave_text(world, foreign_names(built))
    assert _says_foreign(lines) and lines[-1] == FOREIGN_NAME, lines


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_the_silver_arrows_place(base: bytes, case: str, seed: int) -> None:
    """The trio's silver-arrow (or arrow-upgrade) text points at a level-9 place holding the item
    only while this world holds it: another player's item there is never named."""
    built = _built(case, seed)
    name = next(name for name, item in identity(built).items() if item == Item.SILVER_ARROWS)
    world, _ = _with_foreign(built, name)
    assert built.result.item_shuffle_result is not None
    state = with_tracking(built.result.item_shuffle_result, rebuild_tracking(world, built), world, built.places)
    silver_text = level9_trio_texts(world, state, foreign_names(built))[0]
    assert not quote_problems(silver_text) and RUPEES_WORDS not in " ".join(silver_text)
    assert "ELSEWHERE" in " ".join(silver_text), silver_text


@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_finished_hint_text_never_says_rupees_for_another_players_item(base: bytes, case: str) -> None:
    """Through FINISH: another player's item in every cave place; the shipped quotes pass the text
    checks, name no five rupees, and say "another player" where they name one of those places."""
    said = 0
    for seed in SEEDS:
        built = _built(case, seed)
        assignment = identity(built)
        received = []
        for place in built.places:
            if not place.is_dungeon:
                item = assignment[place.name]
                assert isinstance(item, Item)
                received.append(item)
                assignment[place.name] = FOREIGN
        world, _ = finish_world(built, assignment, received=received)
        texts = [quote.text.replace("|", " ") for quote in world.quotes]
        assert not any("FIVE RUPEES" in text for text in texts)
        said += any(FOREIGN_WORDS in text for text in texts)
    assert said > 0


def test_the_wording_fits_the_text_box() -> None:
    """The wording's characters all have tiles (the apostrophe is the font's $2A), and each
    requirement text naming it keeps the wording whole on one line."""
    assert FOREIGN_NAME == "ANOTHER PLAYER'S ITEM"
    assert not quote_problems([FOREIGN_NAME]) and CHAR_TO_BYTE["'"] == APOSTROPHE_TILE
    names = replace(VANILLA_NAMES, foreign_code=FOREIGN_ITEM)
    for form in ("raft", "recorder", "bracelet", "ladder"):
        for white_sword_cave in (False, True):
            lines = requirement_text(Requirement(form, FOREIGN_ITEM, white_sword_cave=white_sword_cave), names)
            assert _says_foreign(lines) and FOREIGN_NAME in lines, lines


def test_the_apostrophe_is_vanillas_own(base: bytes) -> None:
    """Vanilla's person text shows the apostrophe tile ("IT'S DANGEROUS TO GO ALONE!")."""
    assert any("'" in quote.text for quote in parse_rom(base).quotes)


def test_zora_mode_names_are_unchanged() -> None:
    """Without foreign_code (ZORA mode) the five-rupee code is named as ever."""
    assert VANILLA_NAMES.foreign_code is None and PROGRESSIVE_NAMES.foreign_code is None
    assert VANILLA_NAMES.phrase(FOREIGN_ITEM) == "THE FIVE RUPEES"
