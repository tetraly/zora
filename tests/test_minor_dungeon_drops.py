"""Shuffle Minor Dungeon Drops (B17; post-shapes-b1.md PS-ITEM-14) on its Check strings: the levels'
bombs, five rupees and keys join the deal, so some reach a cave slot (with its high bits cleared,
PS-ITEM-06); no key ever reaches the white-sword cave (ZORA's rule, the spec's MAY); under Item Shuffle
None (C06 = 0) nothing moves; only the fifteen places are tracked."""
import pytest

from tests.needs import needs_base_rom
from zora.generate.pipeline import build, plan
from zora.model.enums import Item
from zora.model.rooms import ITEM_MASK
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
    assert result.caves["white_sword"] & ITEM_MASK != Item.KEY
    assert len(result.tracked) == TRACKED


# Archipelago scan seed 304003 (2026-11-21): B17 Random resolved on and the white-sword cave pinned Non-Heart; a key
# whose room's item byte has bit 5 set ($39) passed the six-bit key test and reached the cave
KEY_39_FLAGS, KEY_39_ZORA, KEY_39_SEED = "12J4Gr1vldMVz1uoNy4Oj2UdjXZdiF5nSZnDdr8me", "18.pKGlWRaU3QY", 3


def test_a_key_with_bit_5_set_never_reaches_the_white_sword_cave() -> None:
    result = build(plan(KEY_39_FLAGS, KEY_39_SEED, KEY_39_ZORA), remember_repo_base_rom()).result.item_shuffle_result
    assert result is not None
    assert result.caves["white_sword"] & ITEM_MASK != Item.KEY


def test_some_cave_slot_holds_a_minor_item() -> None:
    base = remember_repo_base_rom()
    results = [build(plan(B17_ON, seed), base).result.item_shuffle_result for seed in SEEDS]
    assert any(byte in MINOR for result in results if result is not None for byte in result.caves.values())


def test_under_item_shuffle_none_nothing_moves() -> None:
    base = remember_repo_base_rom()
    with_b17 = build(plan(B17_ON_ITEM_SHUFFLE_NONE, 1), base).result.item_shuffle_result
    assert with_b17 is not None
    assert not any(byte in MINOR for byte in with_b17.caves.values())


ARCHIPELAGO_FILLER = frozenset({"Bombs", "5 Rupees", "Key"})


@pytest.mark.parametrize("seed", SEEDS)
def test_an_archipelago_build_leaves_them_where_the_dungeon_build_put_them(seed: int) -> None:
    """In Archipelago (2026-11-23) ZORA's own deal is skipped: B17's places are the rooms and cellars the dungeon
    build left holding a minor item, each holding its own (the pool's filler and the filler spots match one for one),
    and no cave slot holds one; the single-player build of the same plan still deals them (the test above)."""
    from zora import archipelago as ap
    result = ap.build_from_strings(B17_ON, "", seed, remember_repo_base_rom())
    held = {place.name: name for place, name in zip(result.places, result.pool, strict=True)}
    assert {name for name, item in held.items() if item in ARCHIPELAGO_FILLER} == \
        {place.name for place in result.places if place.minor}
    shuffled = result.state.result.item_shuffle_result
    assert shuffled is not None
    assert not {slot for slot, item in shuffled.caves.items() if item & ITEM_MASK in MINOR}
