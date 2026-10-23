"""The beta 9 export's item pins (post-shapes-b1.md PS-ITEM-12, flags-behavior.md FL-DEP-01 rule 5 and
FL-DEP-04), on the spec's Check strings:

  - Level 9 Item 1 and 2 (C26, C27) at the Bow, the Ladder, the Power Bracelet, the Raft and the
    Recorder, and at the Wand under Swords at Swordless or Random, are refused with Allow Important
    Items in 9 (B25) off; with B25 on the item lies in level 9, and with B25 at Random it resolves on.
    For C27 the rule is ZORA's (owner ruling, 2026-10-22).
  - Coast Item at Non-Heart (C12 = 16): ZORA always gives the coast a non-heart item (owner ruling,
    2026-10-22; the spec's walk leaves it its heart container in about 9 seeds in 23 under C06 = 3)."""
from functools import cache

import pytest

from tests.needs import needs_base_rom
from zora.flags.codec import decode, encode
from zora.flags.dependencies import check_dependencies
from zora.flags.fields import PinnedItem, ThreeState, WoodenSwordState
from zora.generate.pipeline import Built, FlagsRefused, build, plan
from zora.generate.rng import Rng
from zora.generate.steps.shuffle_items import _non_heart_from_earlier
from zora.model.enums import Destination, Item
from zora.model.game_world import GameWorld
from zora.model.overworld import OverworldItem
from zora.rom.base_rom import remember_repo_base_rom

pytestmark = needs_base_rom
# The Checks' strings: CP-5 with the pin, B25 off, then the same with B25 on
C26_BOW, C27_BOW = "8hq4BeR1JXo89BJ6Gp8qsK!0oiwJ3A", "8hq4BeR1JXo89BK5VQ2GO7gOAiNJ3A"
C26_BOW_B25, C27_BOW_B25 = "8hq4BeR1orW6eezw2jGmw5eR!HwJ3A", "8hq4BeR1orW6ee!vHKACRtKpMHNJ3A"
WITH_B25 = {
    (26, Item.BOW): C26_BOW_B25, (26, Item.LADDER): "8hq4BeR1orW6eezyEHs7riylbgDz3A",
    (26, Item.POWER_BRACELET): "8hq4BeR1orW6ee!0Vdl9FexjWFfz3A", (26, Item.RAFT): "8hq4BeR1orW6ee!1bQ2piycNpRpJ3A",
    (26, Item.RECORDER): "8hq4BeR1orW6ee!2hCLVBHH27dye3A", (27, Item.BOW): C27_BOW_B25,
    (27, Item.LADDER): "8hq4BeR1orW6ef0bxd1A3Mn2X!Ie3A", (27, Item.POWER_BRACELET): "8hq4BeR1orW6ef1eSZobz5SNpZBe3A",
    (27, Item.RAFT): "8hq4BeR1orW6ef1!IDk5HKgUvQ9J3A", (27, Item.RECORDER): "8hq4BeR1orW6ef2L7sfZaZuc0H6z3A",
    (26, Item.WAND): "8hq4BeR1orW6ee!73KXC2WvfLPdGxq", (27, Item.WAND): "8hq4BeR1orW6ef3jTTNUoXo3Ni1wxq",  # C07 = 3
}
WAND_SWORDS_NORMAL = ("8hq4BeR1JXo89BJIHQPFzmGE9qYz3A", "8hq4BeR1JXo89BNuhZFYkn8dC7ye3A")      # B25 off, C07 = 0
COAST_NON_HEART = {"C06 = 3": "8hq4BeR1JXo89BJ2!TFpTP0Gzf1QcV", "C06 = 1": "8hq4BeR1JXo89BJ2!TFpTP0Gzf142H",
                   "C06 = 2": "8hq4BeR1JXo89BJ2!TFpTP0Gzf1FKO"}
RULE_5 = "FL-DEP-01 rule 5"


@cache
def built(flag_string: str, seed: int) -> Built:
    return build(plan(flag_string, seed), remember_repo_base_rom())


def level_9_items(world: GameWorld) -> set[Item | None]:
    level_9 = next(level for level in world.levels if level.level_num == 9)
    return {room.item for room in level_9.rooms} | {cellar.item for cellar in level_9.staircase_rooms}


def rules(flag_string: str) -> list[str]:
    return [refusal.rule for refusal in check_dependencies(decode(flag_string))]


@pytest.mark.parametrize("flag_string", [C26_BOW, C27_BOW])
def test_a_long_item_pin_with_b25_off_is_refused(flag_string: str) -> None:
    assert rules(flag_string) == [RULE_5]
    with pytest.raises(FlagsRefused, match=RULE_5):
        plan(flag_string, 1)


@pytest.mark.parametrize("flag_string", [*WITH_B25.values(), *WAND_SWORDS_NORMAL])
def test_with_b25_on_or_the_swords_kept_nothing_is_refused(flag_string: str) -> None:
    assert rules(flag_string) == []


@pytest.mark.parametrize("pin", ["C26", "C27"])
@pytest.mark.parametrize("item", [PinnedItem.BOW, PinnedItem.LADDER, PinnedItem.POWER_BRACELET, PinnedItem.RAFT,
                                  PinnedItem.RECORDER])
def test_every_long_item_is_refused_with_b25_off(pin: str, item: PinnedItem) -> None:
    assert rules(encode(decode(C26_BOW).updated(options={"C26": 0, pin: item}))) == [RULE_5]


@pytest.mark.parametrize("swords", [WoodenSwordState.SWORDLESS, WoodenSwordState.RANDOM])
def test_the_wand_needs_b25_under_swordless_and_random(swords: WoodenSwordState) -> None:
    flag_string = encode(decode(WAND_SWORDS_NORMAL[0]).updated(options={"C07": swords}))
    assert rules(flag_string) == [RULE_5]


@pytest.mark.parametrize(("pin", "item"), list(WITH_B25))
def test_the_pinned_item_lies_in_level_9(pin: int, item: Item) -> None:
    assert item in level_9_items(built(WITH_B25[pin, item], 1).world)


def test_b25_at_random_resolves_on_beside_a_long_item_pin() -> None:
    flag_string = encode(decode(C26_BOW).updated(toggles={"B25": ThreeState.POSSIBLE}))
    assert all(plan(flag_string, seed).settings.is_on("B25") for seed in range(1, 21))
    for seed in (1, 2):
        assert Item.BOW in level_9_items(built(flag_string, seed).world)


def test_b25_at_random_beside_a_wand_pin_follows_the_swords() -> None:
    """Under Swords Random a pinned Wand needs B25 only when the swords resolve to Swordless (FL-DEP-04's
    first rule then turns a possible B25 on)."""
    flag_string = encode(decode(WAND_SWORDS_NORMAL[0]).updated(options={"C07": WoodenSwordState.RANDOM},
                                                              toggles={"B25": ThreeState.POSSIBLE}))
    resolved = [plan(flag_string, seed).settings for seed in range(1, 41)]
    swordless = [settings for settings in resolved if settings.option("C07") == WoodenSwordState.SWORDLESS]
    assert swordless and all(settings.is_on("B25") for settings in swordless)
    assert {settings.is_on("B25") for settings in resolved if settings not in swordless} == {False, True}


def coast_item(world: GameWorld) -> Item:
    coast = world.overworld.get_cave(Destination.COAST_ITEM, OverworldItem)
    assert coast is not None
    return coast.item


@pytest.mark.parametrize("seed", range(1, 11))
@pytest.mark.parametrize("item_shuffle", list(COAST_NON_HEART))
def test_the_coast_at_non_heart_never_keeps_a_heart_container(item_shuffle: str, seed: int) -> None:
    assert coast_item(built(COAST_NON_HEART[item_shuffle], seed).world) != Item.HEART_CONTAINER


class _OneDraw(Rng):
    """An rng whose every draw is the given index."""

    def __init__(self, index: int) -> None:
        super().__init__(0)
        self.index = index

    def below(self, bound: int) -> int:
        assert self.index < bound
        return self.index


def test_the_non_heart_place_takes_an_earlier_non_heart_item() -> None:
    """Positions 0 to 2 dealt, position 3 standing on the Non-Heart place with only heart containers
    left: it exchanges destinations with a drawn earlier position whose item is no heart container and
    whose place is neither pinned nor Non-Heart (here positions 0 and 2, drawn second)."""
    heart = Item.HEART_CONTAINER
    pool_items: list[int] = [Item.BOW, heart, Item.RAFT, heart, heart]
    destination = [4, 1, 2, 0, 3]                 # position 3 is to go to place 0, the Non-Heart one
    _non_heart_from_earlier(destination, pool_items, 3, forced={}, non_heart={0}, rng=_OneDraw(1))
    assert destination == [4, 1, 0, 2, 3]
