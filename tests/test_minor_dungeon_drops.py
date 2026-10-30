"""Shuffle Minor Dungeon Drops (B17; post-shapes-b1.md PS-ITEM-14) on its Check strings: the levels'
bombs, five rupees and keys join the deal, so some reach a cave slot (with its high bits cleared,
PS-ITEM-06); no key ever reaches the white-sword cave (ZORA's rule, the spec's MAY); under Item Shuffle
None (C06 = 0) nothing moves; only the fifteen places are tracked."""
import pytest

from tests.needs import needs_base_rom
from zora.generate.pipeline import build, plan
from zora.model.enums import Item
from zora.rom.base_rom import remember_repo_base_rom

pytestmark = needs_base_rom

B17_ON = "8hq4BeR1JY64WVOsObF4MXVt3QUJ3A"
B17_ON_ITEM_SHUFFLE_NONE = "8hq4BeR1JY64WVOsObF4MXVt3QTmBq"
MINOR = frozenset({Item.BOMBS, Item.FIVE_RUPEES, Item.KEY})
TRACKED = 15
SEEDS = range(1, 7)


@pytest.mark.parametrize("seed", SEEDS)
def test_minor_items_reach_cave_slots_but_no_key_the_white_sword_cave(seed: int) -> None:
    result = build(plan(B17_ON, seed), remember_repo_base_rom()).result.item_shuffle_result
    assert result is not None
    assert result.caves["white_sword"] != Item.KEY
    assert len(result.tracked) == TRACKED


def test_some_cave_slot_holds_a_minor_item() -> None:
    base = remember_repo_base_rom()
    results = [build(plan(B17_ON, seed), base).result.item_shuffle_result for seed in SEEDS]
    assert any(byte in MINOR for result in results if result is not None for byte in result.caves.values())


def test_under_item_shuffle_none_nothing_moves() -> None:
    base = remember_repo_base_rom()
    with_b17 = build(plan(B17_ON_ITEM_SHUFFLE_NONE, 1), base).result.item_shuffle_result
    assert with_b17 is not None
    assert not any(byte in MINOR for byte in with_b17.caves.values())
