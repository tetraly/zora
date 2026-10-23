"""No level-N hints inside level N (owner request, beta 7; docs/deviations.md): a person inside a
level never tells where that same level is. A dungeon person room that, after B19's pointer
exchange, would show where its own level is ("LEVEL-7 LIES AROUND A LAKE.") trades text pointers
with another dungeon person room, so the text is still shown, in another level; a pool quote takes
its place only when no room can trade (none in 300 seeds, with Hint Type Normal or Helpful).

Which slot a room shows is read here from the shipped world as the game reads it: the room's hint
id picks an entry of its level's family table (B for a helpful level), the entry's selector is
twice the slot, and the slot's pointer gives the text (world.quotes, by slot as displayed)."""
import re

import pytest

from tests.needs import needs_base_rom
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate import ship
from zora.generate.pipeline import Built, build, plan
from zora.generate.steps.hint_text import (
    FAMILY_ENTRIES,
    FIRST_PERSON_CODE,
    LEVEL_LOCATION_SLOTS,
    SELECTOR_TO_SLOT,
    SLOT_COUNT,
    HintTextResult,
    _text_addresses,
    encode_text,
    keep_level_hints_out_of_their_levels,
)
from zora.model.overworld import Quote
from zora.rom.base_rom import remember_repo_base_rom

pytestmark = needs_base_rom

SEEDS = range(10)
# Seed 6: a level 7 person would say where level 7 is, and no other (beta 8's output; seed 0 now has
# two, levels 4 and 7, which the rule moves through three slots)
SEED_WITH_ONE = 6
LEVEL_3_SLOT = LEVEL_LOCATION_SLOTS[2]


def built(seed: int) -> Built:
    return build(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, seed), remember_repo_base_rom())


def built_without_the_rule(monkeypatch: pytest.MonkeyPatch, seed: int) -> Built:
    monkeypatch.setattr(ship, "keep_level_hints_out_of_their_levels", lambda hint_text: hint_text)
    return built(seed)


def texts_inside_levels(seed: Built) -> list[tuple[int, str]]:
    """Each listed person room's player level and the text it shows."""
    world, assignment = seed.world, seed.result.hint_assignment
    assert assignment is not None
    assert world.underworld_text_selectors_a is not None and world.underworld_text_selectors_b is not None
    shown = []
    for level_num, hint_id in assignment.hint_ids:
        entry = hint_id - FIRST_PERSON_CODE
        if entry >= FAMILY_ENTRIES:
            continue
        family = (world.underworld_text_selectors_b if level_num in assignment.helpful
                  else world.underworld_text_selectors_a)
        level = next(level for level in world.levels if level.level_num == level_num)
        shown.append((level.rom_level_num, world.quotes[family[entry] // SELECTOR_TO_SLOT].text))
    return shown


def says_where_its_own_level_is(level: int, text: str) -> bool:
    return re.search(rf"LEVEL-{level}\|? ?LIES", text) is not None


@pytest.mark.parametrize("seed", SEEDS)
def test_no_person_tells_where_its_own_level_is(seed: int) -> None:
    shown = texts_inside_levels(built(seed))
    assert shown
    assert not [(level, text) for level, text in shown if says_where_its_own_level_is(level, text)]


def test_without_the_rule_one_seed_tells_level_7_where_it_is(monkeypatch: pytest.MonkeyPatch) -> None:
    shown = texts_inside_levels(built_without_the_rule(monkeypatch, SEED_WITH_ONE))
    assert [level for level, text in shown if says_where_its_own_level_is(level, text)] == [7]


def test_two_rooms_trade_their_texts(monkeypatch: pytest.MonkeyPatch) -> None:
    """The level 7 text moves to another room, whose text moves to level 7: the same texts are
    shown, two of them in each other's place, and nothing else changes."""
    with_rule = built(SEED_WITH_ONE).world.quotes
    without_rule = built_without_the_rule(monkeypatch, SEED_WITH_ONE).world.quotes
    changed = [slot for slot, (new, old) in enumerate(zip(with_rule, without_rule, strict=True))
               if new.text != old.text]
    assert len(changed) == 2
    first, second = changed
    assert (with_rule[first].text, with_rule[second].text) == (without_rule[second].text, without_rule[first].text)


def test_a_slot_no_room_can_trade_with_shows_its_pool_quote() -> None:
    """The last resort: one room, in level 3, showing where level 3 is."""
    text_bytes = tuple(bytes(encode_text([f"TEXT {slot}"])) for slot in range(SLOT_COUNT))
    pointers = tuple(_text_addresses(text_bytes))
    hint_text = HintTextResult(
        quotes=[Quote(quote_id=slot, text=f"TEXT {slot}") for slot in range(SLOT_COUNT)], pointers=pointers,
        text_bytes=text_bytes, white_sword_selector=0, hint_shop_offer_selectors=(), underworld_selectors_a=b"",
        underworld_selectors_b=b"", hint_shop_prices=(), overlay_flags=(True,) * SLOT_COUNT,
        level_location_slots={LEVEL_3_SLOT: 3}, level_text_alternatives={LEVEL_3_SLOT: ["A POOL QUOTE"]},
        room_slots=((3, LEVEL_3_SLOT),))
    kept = keep_level_hints_out_of_their_levels(hint_text)
    assert kept.quotes[LEVEL_3_SLOT].text == "A POOL QUOTE" and not kept.overlay_flags[LEVEL_3_SLOT]
    assert kept.pointers == tuple(_text_addresses(kept.text_bytes))
    assert [quote.text for quote in kept.quotes if quote.text != "A POOL QUOTE"] == [
        f"TEXT {slot}" for slot in range(SLOT_COUNT) if slot != LEVEL_3_SLOT]
