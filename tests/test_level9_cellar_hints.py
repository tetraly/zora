"""The level-9 old man's texts for an item in a level-9 item cellar (HT-HINT-01's silver-arrow
text, PI-TEXT-01's arrow-upgrade text): a cellar's item is shown by the quadrant of the room its
stairs are in, never as "UNKNOWN". The seeds are pinned on Hint Type: Helpful (C03 = 1) with
Item Shuffle within each dungeon, the flags of the report that found it."""
from __future__ import annotations

from dataclasses import replace
from functools import cache

import pytest

from tests.needs import needs_encoder
from zora.flags import codec
from zora.generate.pipeline import Built, build, plan
from zora.generate.steps.hint_text import (
    LEVEL9_TRIO_SLOTS,
    PROGRESSIVE_NAMES,
    VANILLA_NAMES,
    _quadrant,
    level9_trio_texts,
)
from zora.model.enums import Item, RoomType
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom

FLAGS = "143oNtDD4PAvB!U8nSk4yS8L09lgT10vRVe7sx"
ZORA_FLAGS = "10.J2EkcYg"
PROGRESSIVE_ZORA_FLAGS = "10.J2EkcZ3"       # the same, with Progressive Items on
SILVER_SLOT = LEVEL9_TRIO_SLOTS[0]          # the silver-arrow text is always kept, in slot 35
ARROW_LINE = {Item.WOOD_ARROWS, Item.SILVER_ARROWS}
DECEPTION = 3                               # Hint Type: Deception (C03 = 3)
pytestmark = needs_encoder                   # the report's flags encode levels (private module)


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("needs the base ROM")
    return remember_repo_base_rom()


@cache
def _built(zora_flags: str, seed: int, hint_type: int | None = None) -> Built:
    flags = FLAGS
    if hint_type is not None:
        settings = codec.decode(FLAGS)
        flags = codec.encode(replace(settings, options={**settings.options, "C03": hint_type}))
    return build(plan(flags, seed, zora_flags), remember_repo_base_rom())


def _cellar_stair_rooms(built: Built, items: set[Item]) -> list[int]:
    """The rooms whose stairs lead down to a level-9 item cellar holding one of the items."""
    level9 = built.world.levels[8]
    return [stair.return_dest for stair in level9.block.staircases
            if stair.room_type == RoomType.ITEM_STAIRCASE and stair.item in items
            and stair.return_dest is not None and stair.return_dest in level9.room_nums]


def _in_a_room(built: Built, items: set[Item]) -> bool:
    return any(room.item in items for room in built.world.levels[8].rooms)


# (seed, the stair room's quadrant): 10 replaces the report's 3268821545 (silver in cellar $4F under room
# $77), whose level 9 the bomb-dropper rule (5be7d86) has since drawn again
@pytest.mark.parametrize(("seed", "quadrant"), [(10, "SOUTH-WEST"), (0, "NORTH-EAST")])
def test_silver_arrows_in_a_level_9_cellar(base: bytes, seed: int, quadrant: str) -> None:
    built = _built(ZORA_FLAGS, seed)
    stair_rooms = _cellar_stair_rooms(built, {Item.SILVER_ARROWS})
    assert len(stair_rooms) == 1 and not _in_a_room(built, {Item.SILVER_ARROWS}), "re-pin the seed"
    assert _quadrant(built.world, stair_rooms[0]) == quadrant
    assert built.result.item_shuffle_result is not None
    text = level9_trio_texts(built.world, built.result.item_shuffle_result, VANILLA_NAMES)[0]
    assert text == ["SILVER ARROWS ARE", f"IN THE {quadrant}"]
    assert built.world.quotes[SILVER_SLOT].text == "|".join(text)       # the finished world's slot


@pytest.mark.parametrize(("seed", "quadrant"), [(4, "SOUTH-EAST")])
def test_an_arrow_upgrade_in_a_level_9_cellar(base: bytes, seed: int, quadrant: str) -> None:
    built = _built(PROGRESSIVE_ZORA_FLAGS, seed)
    stair_rooms = _cellar_stair_rooms(built, ARROW_LINE)
    assert stair_rooms and not _in_a_room(built, ARROW_LINE), "re-pin the seed"
    assert _quadrant(built.world, stair_rooms[0]) == quadrant
    assert built.result.item_shuffle_result is not None
    text = level9_trio_texts(built.world, built.result.item_shuffle_result, PROGRESSIVE_NAMES)[0]
    assert " ".join(text) == f"AN ARROW UPGRADE IS IN THE {quadrant}"
    assert built.world.quotes[SILVER_SLOT].text == "|".join(text)


# Seed 83: silver in cellar $48 under room $28, and its hint shows the true quadrant; before the fix
# a cellar's quadrant was always drawn at random under Deception, and here read SOUTH-WEST.
@pytest.mark.parametrize(("seed", "quadrant"), [(83, "NORTH-EAST")])
def test_deception_tells_the_truth_about_a_level_9_cellar(base: bytes, seed: int, quadrant: str) -> None:
    built = _built(ZORA_FLAGS, seed, DECEPTION)
    stair_rooms = _cellar_stair_rooms(built, {Item.SILVER_ARROWS})
    assert len(stair_rooms) == 1 and not _in_a_room(built, {Item.SILVER_ARROWS}), "re-pin the seed"
    assert _quadrant(built.world, stair_rooms[0]) == quadrant
    assert built.world.quotes[SILVER_SLOT].text == f"SILVER ARROWS ARE|IN THE {quadrant}"
