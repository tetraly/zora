"""Replace Book Fire with Explosion (B47; features-behavior.md FP-BOOK-02) and the coast pin (C12;
PS-ITEM-12), on finished ROMs from the spec's own Check strings. ZORA's B47 is the blast alone (owner,
2026-10-22; docs/deviations.md): no OW-SHOP-07 or PS-ITEM-13, nor FL-DEP-01 rule 4.

  - the blast's bytes are written (at ZORA's places, docs/deviations.md), and PRG0's without B47;
  - the same flags with B47 off deal the same items, stock the same shops and track the same items,
    with and without the shop shuffle, under C06 = 0 and with a level-9 pin naming the Book;
  - B47 "?" comes out both ways, beside a Book pin too;
  - the coast cave slot holds the pinned item (C12 = 12, the Red Ring; and 1 to 4, 6 to 15)."""
from functools import cache

import pytest

from tests.needs import needs_base_rom
from zora.flags.codec import decode, encode
from zora.flags.fields import PinnedItem, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import Built, build, finish, plan
from zora.generate.steps.shuffle_items import FORCED_ITEM_OPTIONS
from zora.model.enums import Destination, Item
from zora.model.game_world import GameWorld
from zora.model.overworld import OverworldItem, Shop
from zora.model.rooms import ITEM_MASK
from zora.rom import uphill_battle as patches
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom

pytestmark = needs_base_rom
B47_ON = "8i4nJHyUO4csR3bl54eJRdRTLQUJ3A"
B47_POSSIBLE = "8iKVQwUxScRbiwuSAh1oPrstniUJ3A"
B47_NO_SHOP_SHUFFLE = "8i4nJHyUO4csNEyXBA5hEpGwDiUJ3A"
B47_NO_DEAL = "8i4nJHyUO4csR3bl54eJRdRTLQTmBq"           # C06 = 0
B47_LEVEL_9_BOOK_PIN = "8i4nJHyUO4csR3bmArwzux67ecde3A"  # C26 = 1
COAST_RED_RING = "8hq4BeR1JXo89BJ2!TFpTP0DSme8zA"
COAST_RED_RING_ITEM_ONLY = "8hq4BeR1JXo89BJ2!TFpTP0DSmdnOx"
SHOPS = (Destination.SHOP_1, Destination.SHOP_2, Destination.SHOP_3, Destination.SHOP_4)
SPECIAL_SLOTS = (Destination.ARMOS_ITEM, Destination.COAST_ITEM)


@cache
def built(flag_string: str, seed: int) -> Built:
    return build(plan(flag_string, seed), remember_repo_base_rom())


@cache
def rom(flag_string: str, seed: int) -> bytes:
    return finish(built(flag_string, seed), remember_repo_base_rom())


@cache
def world(flag_string: str, seed: int) -> GameWorld:
    return parse_rom(rom(flag_string, seed))


def level_items(shipped: GameWorld) -> list[int]:
    return [room.item_info.item_byte & ITEM_MASK for level in shipped.levels
            for room in (level.block.room(number) for number in level.room_nums)]


def slot_item(shipped: GameWorld, destination: Destination) -> Item | None:
    slot = shipped.overworld.get_cave(destination, OverworldItem)
    return None if slot is None else slot.item


def tracked_items(flag_string: str, seed: int) -> set[int]:
    shuffled = built(flag_string, seed).result.item_shuffle_result
    assert shuffled is not None
    return {place.item & ITEM_MASK for place in shuffled.tracked}


def wares(shipped: GameWorld) -> list[list[tuple[Item, int]]]:
    return [[(ware.item, ware.price) for ware in shop.items]
            for shop in (shipped.overworld.get_cave(destination, Shop) for destination in SHOPS) if shop is not None]


@pytest.mark.parametrize("seed", (1, 2, 3))
def test_the_blast(seed: int) -> None:
    finished = rom(B47_ON, seed)
    writes = patches.book_explosion_writes()
    assert [finished[offset:offset + len(data)] for offset, data in writes] == [data for _offset, data in writes]


def without_b47(flag_string: str) -> str:
    return encode(decode(flag_string).updated(toggles={"B47": ThreeState.OFF}))


@pytest.mark.parametrize("flag_string", [B47_ON, B47_NO_SHOP_SHUFFLE, B47_NO_DEAL, B47_LEVEL_9_BOOK_PIN])
@pytest.mark.parametrize("seed", (1, 2))
def test_items_and_shops_as_without_b47(flag_string: str, seed: int) -> None:
    """The owner's B47 (2026-10-22): the Book stays in the pool and the shops keep the magic shield."""
    shipped, control = world(flag_string, seed), world(without_b47(flag_string), seed)
    assert level_items(shipped) == level_items(control)
    assert [slot_item(shipped, slot) for slot in SPECIAL_SLOTS] == [slot_item(control, slot) for slot in SPECIAL_SLOTS]
    assert wares(shipped) == wares(control)
    assert all(item != Item.BOOK for items in wares(shipped) for item, _price in items)
    assert tracked_items(flag_string, seed) == tracked_items(without_b47(flag_string), seed)


def test_a_level_9_book_pin_finds_the_book() -> None:
    assert Item.BOOK in tracked_items(B47_LEVEL_9_BOOK_PIN, 1)


def test_without_b47_nothing_changes() -> None:
    finished = rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1)
    base = remember_repo_base_rom()
    assert all(finished[offset:offset + len(data)] == base[offset:offset + len(data)]
               for offset, data in patches.book_explosion_writes())


def test_b47_random_both_ways_beside_a_book_pin_too() -> None:
    assert {plan(B47_POSSIBLE, seed).settings.is_on("B47") for seed in range(16)} == {True, False}
    beside_pin = encode(decode(B47_POSSIBLE).updated(options={"C11": PinnedItem.BOOK_OF_MAGIC}))
    assert {plan(beside_pin, seed).settings.is_on("B47") for seed in range(16)} == {True, False}


@pytest.mark.parametrize("flag_string", [COAST_RED_RING, COAST_RED_RING_ITEM_ONLY])
@pytest.mark.parametrize("seed", (1, 2))
def test_the_coast_pin(flag_string: str, seed: int) -> None:
    assert slot_item(world(flag_string, seed), Destination.COAST_ITEM) == Item.RED_RING


@pytest.mark.parametrize("pin", [1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 13, 14, 15])
def test_every_coast_pin(pin: int) -> None:
    flag_string = encode(decode(COAST_RED_RING).updated(options={"C12": pin}))
    assert slot_item(world(flag_string, 1), Destination.COAST_ITEM) == FORCED_ITEM_OPTIONS[pin]
