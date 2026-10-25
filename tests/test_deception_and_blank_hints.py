"""Hint Type Deception, Blank and Random (C03 = 3, 5, 6; hints-behavior.md HT-HINT-06, HT-HINT-07,
HT-HINT-05's Random bullet), on finished ROMs from the spec's own Check strings:

  - Deception: helpful hints' selectors (white-sword cave $66, HT-SEL-02's hint-shop offers); every
    slot with a helpful text shows it (slots 0, 3, 6, 7 and 35 included); level-location entries
    name the door's region about half the time or more, and not always; the requirement texts hold
    no inside-dungeon form; B19's exchange starts at slot 19.
  - Blank: 45 empty texts from 0x7780 (ZORA's empty text, a space with the end mark: the spec's lone
    $FF draws a stray mark in the text box, docs/deviations.md), each slot pointing at its own but
    slots 27 and 34 and B19's
    exchanged ones; PRG0's white-sword cave selector, hint-shop selectors and prices; no first-eight
    dungeon selector $4C.
  - Random resolves to each of the six styles."""
from functools import cache

import pytest

from tests.needs import needs_base_rom
from zora.flags.codec import decode, encode
from zora.flags.fields import ThreeState
from zora.generate.finish import FOREIGN
from zora.generate.pipeline import Built, build, finish, finish_world, plan
from zora.generate.steps.hint_text import (
    HINT_SHOP_OFFER_SELECTORS,
    HOLDER_SLOT,
    LEVEL_LOCATION_SLOTS,
    MEET_SLOT,
    SHOW_SLOT,
    WHITE_SWORD_SELECTOR,
    _door_screen,
    level_shown_as,
    region_of_screen,
    region_phrase,
)
from zora.generate.steps.shuffle_dungeon_text import NORMAL_SHUFFLED_SLOTS
from zora.model.game_world import GameWorld
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.layout import QUOTE_DATA_ADDRESS
from zora.rom.parse.rom_file import parse_rom
from zora.rom.text_encoding import QUOTE_EMPTY

pytestmark = needs_base_rom
DECEPTION, BLANK, RANDOM = ("8hq4BeR1JXo89BJ2!TFpTP02u8UJ1u", "8hq4BeR1JXo89BJ2!TFpTP02u8UJ4R",
                            "8hq4BeR1JXo89BJ2!TFpTP02u8UJ5i")
BLANK_NO_EXCHANGE = encode(decode(BLANK).updated(toggles={"B19": ThreeState.OFF}))
DECEPTION_NO_EXCHANGE = encode(decode(DECEPTION).updated(toggles={"B19": ThreeState.OFF}))
BLANK_TEXTS, SLOTS, EMPTY = 0x7780, 45, QUOTE_EMPTY
TOLL_SLOT, REFUSAL_SLOT = 27, 34
DUNGEON_SELECTORS = 8
REPLACED_SELECTOR = 0x4C
EXT_HINT_CPU_BASE, EXT_BANK1_ROM_START = 0xB770, 0x7780


@cache
def built(flag_string: str, seed: int) -> Built:
    return build(plan(flag_string, seed), remember_repo_base_rom())


@cache
def rom(flag_string: str, seed: int) -> bytes:
    return finish(built(flag_string, seed), remember_repo_base_rom())


@cache
def world(flag_string: str, seed: int) -> GameWorld:
    return parse_rom(rom(flag_string, seed))


def pointers(data: bytes) -> list[int]:
    return [data[QUOTE_DATA_ADDRESS + 2 * slot] | data[QUOTE_DATA_ADDRESS + 2 * slot + 1] << 8 for slot in range(SLOTS)]


def text(shipped: GameWorld, slot: int) -> str:
    """A slot's text as one line: the centring pads and line breaks as spaces."""
    return " ".join((shipped.quotes[slot].text or "").replace("~", " ").replace("|", " ").split())


@pytest.mark.parametrize("seed", (1, 2, 3))
def test_deception_keeps_helpful_hints_selectors_and_shows_every_helpful_text(seed: int) -> None:
    shipped = world(DECEPTION, seed)
    assert shipped.white_sword_text_selector == WHITE_SWORD_SELECTOR
    assert tuple(shipped.hint_shop_offer_selectors or ()) == HINT_SHOP_OFFER_SELECTORS
    # ZORA's slot 0 shows its own quotes (owner ruling); the other four always show their helpful text
    assert text(shipped, SHOW_SLOT).startswith("SHOW") and text(shipped, MEET_SLOT).startswith("MEET")
    assert " HAS" in text(shipped, HOLDER_SLOT) or "I HAVE" in text(shipped, HOLDER_SLOT)


def test_deception_misstates_some_level_regions_and_states_some_true() -> None:
    true = false = 0
    for seed in range(1, 7):
        shipped = world(DECEPTION_NO_EXCHANGE, seed)
        for player_level, slot in enumerate(LEVEL_LOCATION_SLOTS, start=1):
            screen = _door_screen(shipped, level_shown_as(shipped.levels, player_level).level_num)
            assert screen is not None
            truth = region_phrase(region_of_screen(screen))
            if f"LEVEL-{player_level} " not in text(shipped, slot):
                continue                           # moved (HT-HINT-02's relocations) or a pool quote
            if text(shipped, slot).endswith(f"{truth}."):
                true += 1
            else:
                false += 1
    # each entry is true with chance one-half plus one-half times its region's share of the 128
    # screens (about 0.55 here); 48 or so entries leave room for noise
    assert true and false and 0.35 <= true / (true + false) <= 0.85


@pytest.mark.parametrize("seed", (1, 2))
def test_deception_names_no_inside_dungeon_requirement(seed: int) -> None:
    assert not any("INSIDE" in (quote.text or "") for quote in world(DECEPTION, seed).quotes)


@pytest.mark.parametrize("flag_string", [BLANK, BLANK_NO_EXCHANGE])
@pytest.mark.parametrize("seed", (1, 2))
def test_blank_hints(flag_string: str, seed: int) -> None:
    data, base = rom(flag_string, seed), parse_rom(remember_repo_base_rom())
    assert data[BLANK_TEXTS:BLANK_TEXTS + SLOTS] == bytes([EMPTY]) * SLOTS
    own = [EXT_HINT_CPU_BASE + slot for slot in range(SLOTS)]
    exchanged = set(NORMAL_SHUFFLED_SLOTS) if flag_string == BLANK else set()
    differ = {slot for slot, pointer in enumerate(pointers(data)) if pointer != own[slot]}
    assert differ <= {TOLL_SLOT, REFUSAL_SLOT} | exchanged
    assert REFUSAL_SLOT in differ
    shipped = world(flag_string, seed)
    assert shipped.white_sword_text_selector == base.white_sword_text_selector
    assert shipped.hint_shop_offer_selectors == base.hint_shop_offer_selectors
    for family in (shipped.underworld_text_selectors_a, shipped.underworld_text_selectors_b):
        assert family is not None and REPLACED_SELECTOR not in family[:DUNGEON_SELECTORS]


def test_random_hint_style_resolves_to_each_style() -> None:
    assert {plan(RANDOM, seed).settings.option("C03") for seed in range(60)} == set(range(6))


@pytest.mark.parametrize("seed", (1, 2))
def test_random_hint_style_generates(seed: int) -> None:
    assert world(RANDOM, seed).levels


@pytest.mark.parametrize("seed", range(1, 7))
def test_deception_with_every_tracked_item_in_another_world(seed: int) -> None:
    """An Archipelago world whose places all hold other players' items tracks nothing
    (finish.rebuild_tracking), so the white-sword cave's deceiving item has no pool entries to draw
    from: it is the cave's own item then (ZORA4 of the batch run's exported YAMLs crashed on
    rng.below(0)). Over these seeds the item's coin comes up heads on some."""
    every_place_foreign = {place.name: FOREIGN for place in built(DECEPTION, seed).places}
    _world, finished = finish_world(built(DECEPTION, seed), every_place_foreign, check=False)
    assert finished.tracking.tracked == []
