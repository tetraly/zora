"""Progressive Items and Shop Items in the Item Pool on the generation side
(docs/design/progressive-items-plan.md sections 7 and 9): the hints name upgrade lines, the
flags off keep today's texts, and generated seeds hold the joins, the patches and the logic.
The flags, the patches, the logic rules and the joins have their own tests
(tests/test_zora_flags.py, tests/test_asm_patches.py, tests/test_acceptance.py,
tests/test_zora_extras.py)."""
from functools import cache

import pytest

from zora.flags.codec import decode, encode
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_world, plan
from zora.generate.steps.hint_text import (
    ITEM_NAMES, LINE_WIDTH, PROGRESSIVE_NAMES, UPGRADE_LINES, VANILLA_NAMES, Form, Requirement, item_name,
    requirement_text,
)
from zora.generate.steps.item_shuffle_result import shop_of_slot
from zora.model.enums import Item
from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")

WITHOUT_EXTRA_CANDLES = encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(toggles={"B09": ThreeState.OFF}))
PROGRESSIVE, SHOP_POOL, BOTH = "2.O", "2.m", "2.19"


@cache
def generated(zora: str, seed: int) -> tuple:
    flags = MVP_BASELINE_LEVEL_ENCODING_OFF if zora == SHOP_POOL else WITHOUT_EXTRA_CANDLES
    return generate_world(plan(flags, seed, zora), verify_base_rom().read_bytes())


# --- PI-TEXT-01 ------------------------------------------------------------------------------

def test_the_vanilla_names_are_todays() -> None:
    for code in range(len(ITEM_NAMES)):
        assert VANILLA_NAMES.label(code) == item_name(code)
        assert VANILLA_NAMES.phrase(code) == f"THE {item_name(code)}"
    candidate = Requirement(Form.BOSS, Item.MAGICAL_BOOMERANG, 8)
    assert requirement_text(candidate) == ["THE LURKING MANHANDLA", "HOLDS THE MAGICAL BOOMERANG"]


def test_progressive_names_name_each_line() -> None:
    assert PROGRESSIVE_NAMES.phrase(Item.WHITE_SWORD) == "A SWORD UPGRADE"
    assert PROGRESSIVE_NAMES.phrase(Item.RED_CANDLE) == "A CANDLE UPGRADE"
    assert PROGRESSIVE_NAMES.phrase(Item.SILVER_ARROWS) == "AN ARROW UPGRADE"
    assert PROGRESSIVE_NAMES.phrase(Item.BLUE_RING) == "A RING UPGRADE"
    assert PROGRESSIVE_NAMES.phrase(Item.MAGICAL_BOOMERANG) == "A BOOMERANG UPGRADE"
    assert PROGRESSIVE_NAMES.label(Item.WOOD_SWORD) == "SWORD UPGRADE"
    assert PROGRESSIVE_NAMES.phrase(Item.BOOK) == "THE BOOK"          # not an upgrade line
    assert len(UPGRADE_LINES) == 11


@pytest.mark.parametrize("item", sorted(UPGRADE_LINES))
@pytest.mark.parametrize("form", [Form.BOSS, Form.RAFT])
def test_progressive_requirement_texts_fit(item: int, form: str) -> None:
    for level in range(1, 9):
        lines = requirement_text(Requirement(form, item, level), PROGRESSIVE_NAMES)
        assert 1 <= len(lines) <= 3 and all(len(line) <= LINE_WIDTH for line in lines)
        assert "UPGRADE" in " ".join(lines) and item_name(item) not in " ".join(lines)


@pytest.mark.parametrize("zora", [PROGRESSIVE, "2.b"])          # 2.b: with the magical sword, cap 12
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_generated_hints_name_lines_not_items(zora: str, seed: int) -> None:
    """With Progressive Items on, no hint text names an upgrade-line item, apart from the
    white-sword cave's own name and the owner's quotes in slot 0 (the wood sword cave)."""
    world, _ = generated(zora, seed)
    for slot, quote in enumerate(world.quotes):
        if slot == 0:
            continue
        text = quote.text.replace("~", "").replace("|", " ").replace("WHITE SWORD CAVE", "")
        assert not any(item_name(code) in text for code in UPGRADE_LINES), (slot, text)


def test_with_the_flag_off_the_silver_arrow_text_is_todays() -> None:
    world, _ = generated(SHOP_POOL, 1)
    assert not any("UPGRADE" in quote.text for quote in world.quotes if "BOMB UPGRADE" not in quote.text)


# --- generated seeds ---------------------------------------------------------------------------

@pytest.mark.parametrize("seed", [1, 2, 3])
def test_shop_items_in_the_pool_track_the_arrows_and_the_candle(seed: int) -> None:
    """PI-LOGIC-06: the joined arrows and candle are tracked wherever they went; the ring is
    not; a tracked shop ware names a shop."""
    _, result = generated(SHOP_POOL, seed)
    tracked = {place.item for place in result.item_shuffle_result.tracked}
    assert {Item.WOOD_ARROWS, Item.BLUE_CANDLE} <= tracked and Item.BLUE_RING not in tracked
    assert result.extra_pool_items.shop_items == [Item.WOOD_ARROWS, Item.BLUE_CANDLE, Item.BLUE_RING]
    for place in result.item_shuffle_result.tracked:
        if place.slot is not None and place.slot.startswith("shop"):
            assert shop_of_slot(place.slot) is not None
