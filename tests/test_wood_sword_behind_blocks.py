"""Allow OW Blocks of Wood Sword (B03; overworld-behavior.md OW-CAVE-07): the wooden-sword cave may
land behind an item gate the free item opens. The Check over 1,000 seeds: `python3
scripts/compare_corpus.py --set b03` (no corpus: ZORA beside the figures the spec reports)."""
import copy
from functools import cache

import pytest

from zora.flags import zora_flags
from zora.flags.codec import decode, encode
from zora.flags.fields import WOOD_SWORD_CAVE_BEHIND_BLOCKS, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.support import Support, support
from zora.generate.pipeline import build, plan
from zora.generate.steps.cave_entries import BURNABLE_SCREENS, MIXED_RECORDER_SCREENS, RAFT_SCREENS
from zora.generate.steps.overworld_gates import RAFT_ENCLOSED_SCREENS, OverworldGates
from zora.generate.steps.wood_sword_behind_blocks import (
    BRACELET_SCREENS_WITH_32_33,
    armos_reached_from_start,
    free_item,
    wood_sword_extra_screens,
)
from zora.model.enums import Destination, Item
from zora.model.game_world import GameWorld
from zora.model.overworld import OverworldItem
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora_measure.checkpoints.overworld_quests import WOOD_SWORD_BLOCKS_FLAGS, wood_sword_widened

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")


@cache
def _base() -> bytes:
    return remember_repo_base_rom()


@cache
def _prg0() -> GameWorld:
    return parse_rom(_base())


def test_the_string_is_cp5_with_b03_on_and_supported() -> None:
    settings = decode(WOOD_SWORD_BLOCKS_FLAGS)
    assert settings.toggle(WOOD_SWORD_CAVE_BEHIND_BLOCKS) is ThreeState.ON
    off = settings.updated(toggles={WOOD_SWORD_CAVE_BEHIND_BLOCKS.id: ThreeState.OFF})
    assert encode(off) == MVP_BASELINE_LEVEL_ENCODING_OFF
    for state in ThreeState:
        judged = support(off.updated(toggles={WOOD_SWORD_CAVE_BEHIND_BLOCKS.id: state}))
        assert judged[WOOD_SWORD_CAVE_BEHIND_BLOCKS.id] is Support.SUPPORTED, state


@pytest.mark.parametrize("armos, coast, expected", [
    (Item.RECORDER, Item.HEART_CONTAINER, Item.RECORDER),
    (Item.LADDER, Item.RAFT, Item.RAFT),               # the Armos ladder: the coast item instead
    (Item.LADDER, Item.HEART_CONTAINER, None),
    (Item.BLUE_CANDLE, Item.HEART_CONTAINER, None),    # a blue candle as the free item does not count
    (Item.WHITE_SWORD, Item.POWER_BRACELET, None),     # the coast counts only behind an Armos ladder
])
def test_the_free_item(armos: Item, coast: Item, expected: Item | None) -> None:
    assert free_item(int(armos), int(coast)) == expected


@pytest.mark.parametrize("free, screens", [
    (Item.POWER_BRACELET, BRACELET_SCREENS_WITH_32_33), (Item.RAFT, RAFT_SCREENS),
    (Item.RED_CANDLE, BURNABLE_SCREENS), (Item.RECORDER, frozenset({66})), (Item.WHITE_SWORD, frozenset()),
])
def test_each_free_item_adds_its_set(free: Item, screens: frozenset[int]) -> None:
    assert wood_sword_extra_screens(_prg0().overworld, int(free), int(Item.HEART_CONTAINER)) == screens


def test_the_recorder_set_follows_the_quest() -> None:
    """Under every overworld quest but the first, the recorder adds the eleven screens."""
    overworld = copy.deepcopy(_prg0().overworld)
    overworld.recorder_reveals_listed_secrets_in_first_quest = True
    assert wood_sword_extra_screens(overworld, int(Item.RECORDER), 0) == MIXED_RECORDER_SCREENS


@pytest.mark.parametrize("armos, coast, starting, expected", [
    (Item.RAFT, Item.HEART_CONTAINER, frozenset(), None),
    (Item.POWER_BRACELET, Item.HEART_CONTAINER, frozenset(), None),
    (Item.RECORDER, Item.HEART_CONTAINER, frozenset(), None),
    (Item.LADDER, Item.RAFT, frozenset(), None),                       # the Armos ladder out of reach too
    (Item.POWER_BRACELET, Item.RAFT, frozenset({Item.LADDER}), Item.RAFT),   # the started ladder: the coast
])
def test_a_walled_in_armos_gives_no_free_item(armos: Item, coast: Item, starting: frozenset[Item],
                                              expected: Item | None) -> None:
    """The 2.0.2 follow-up to 4ab25424: an Armos on a screen a gate walls in (Extra Raft Blocks and $34) is not
    reached from the start, so its item is not free; the coast item still is when the start holds the ladder."""
    assert free_item(int(armos), int(coast), starting, armos_reached=False) == expected
    assert wood_sword_extra_screens(_prg0().overworld, int(armos), int(coast), starting,
                                    armos_reached=False) == (RAFT_SCREENS if expected == Item.RAFT else frozenset())


RAFT_BLOCKS = OverworldGates(raft_blocks=True)


@pytest.mark.parametrize("gates, screen, starting, reached", [
    (RAFT_BLOCKS, 0x34, frozenset(), False),
    (RAFT_BLOCKS, 0x34, frozenset({Item.RAFT}), True),               # Start Raft (B57)
    (RAFT_BLOCKS, 0x24, frozenset(), True),                          # PRG0's Armos screen, never walled in
    (OverworldGates(), 0x34, frozenset(), True),                     # $34 is open without Extra Raft Blocks
])
def test_the_armos_is_reached_from_the_start(gates: OverworldGates, screen: int, starting: frozenset[Item],
                                             reached: bool) -> None:
    assert armos_reached_from_start(screen, gates, starting) is reached


# Shuffle Wood Sword Cave (B02), B03, Shuffle Armos (B13) and the Power Bracelet pinned at the Armos (C11 = 8), with
# Extra Raft Blocks: seeds 6 and 22 once put the Armos on $34 and the wooden-sword cave behind a bracelet boulder
# ($21, $49), so Link started without a sword and the bracelet needed the raft first (scan of 2026-11-27).
BRACELET_AT_THE_ARMOS = encode(decode(WOOD_SWORD_BLOCKS_FLAGS).updated(
    options={"C11": 8}, toggles={"B02": ThreeState.ON, "B03": ThreeState.ON, "B13": ThreeState.ON}))
EXTRA_RAFT_BLOCKS = zora_flags.encode(zora_flags.ZoraFlags(extra_raft_blocks=ThreeState.ON))


@pytest.mark.parametrize("seed", [6, 22])
def test_the_sword_cave_never_waits_on_a_walled_in_armos(seed: int) -> None:
    built = build(plan(BRACELET_AT_THE_ARMOS, seed, EXTRA_RAFT_BLOCKS), _base())
    overworld, caves = built.world.overworld, built.result.overworld
    assert caves is not None
    armos = overworld.get_cave(Destination.ARMOS_ITEM, OverworldItem)
    assert armos is not None and armos.item == Item.POWER_BRACELET
    sword = {entry.screen for entry in caves.entries if entry.code == Destination.WOOD_SWORD_CAVE}
    if overworld.armos_screen_ids[0] in RAFT_ENCLOSED_SCREENS:
        assert not sword & wood_sword_extra_screens(overworld, int(armos.item), 0), (
            f"Armos on ${overworld.armos_screen_ids[0]:02X}, wooden-sword cave on {sorted(sword)}")


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_finished_roms(seed: int) -> None:
    built = build(plan(WOOD_SWORD_BLOCKS_FLAGS, seed), _base())
    assert wood_sword_widened(built.world)["on the widened set"]
