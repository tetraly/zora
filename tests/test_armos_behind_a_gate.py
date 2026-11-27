"""The Armos item is reached by walking onto its screen. Shuffle Armos (B13) can move it to screen $34, which
Extra Raft Blocks walls in behind the raft (overworld_gates.RAFT_ENCLOSED_SCREENS), so there the Armos item needs
the raft. The acceptance check once held the Armos item from the start wherever it stood: the 2.0.2 report
(seed 3425595242) put the raft under an Armos on $34, with level 6 behind the power bracelet and the bracelet in the
Letter Cave behind the raft, and the seed was accepted though it cannot be finished."""
from dataclasses import replace

import pytest

from tests.needs import needs_base_rom
from zora.flags import zora_flags
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.acceptance_check import AcceptanceCheck
from zora.generate.pipeline import Built, build, extra_options, generate_world, plan
from zora.generate.steps import overworld_gates as gates
from zora.generate.steps.item_shuffle_result import TrackedPlace
from zora.model.enums import Destination, Item
from zora.model.overworld import OverworldItem
from zora.rom.base_rom import remember_repo_base_rom

pytestmark = needs_base_rom

RAFT_BLOCKS = zora_flags.encode(zora_flags.ZoraFlags(extra_raft_blocks=ThreeState.ON))
NO_GATES = zora_flags.encode(zora_flags.ZoraFlags())
ARMOS_ON_THE_RAFT_ISLAND = 0x34
# The 2.0.2 report: Extra Raft Blocks and Extra Power Bracelet Blocks on, the raft under an Armos on $34
REPORTED = ("8hq4BeR1JXo898KtimW0fVhmo57q65", "23.95dBeC5Rw78Zj", 3425595242)


def check_with_armos_on(zora: str, screen: int) -> AcceptanceCheck:
    """A generated seed's acceptance check, its Armos item moved to `screen`."""
    seed: Built = build(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, zora), remember_repo_base_rom())
    state, caves = seed.result.item_shuffle_result, seed.result.overworld
    assert state is not None and caves is not None
    overworld = seed.world.overworld
    overworld.armos_screen_ids = [screen, *overworld.armos_screen_ids[1:]]
    return AcceptanceCheck(seed.world.levels, state, overworld, caves, extra_options(seed.plan).logic_rules)


def armos_slot(item: Item) -> TrackedPlace:
    return TrackedPlace(item, slot="armos")


def test_an_armos_on_the_raft_island_needs_the_raft() -> None:
    check = check_with_armos_on(RAFT_BLOCKS, ARMOS_ON_THE_RAFT_ISLAND)
    assert ARMOS_ON_THE_RAFT_ISLAND in gates.RAFT_ENCLOSED_SCREENS
    assert not check.collects(armos_slot(Item.BOOK), frozenset())
    assert check.collects(armos_slot(Item.BOOK), frozenset({Item.RAFT}))


def test_the_raft_under_an_armos_on_the_raft_island_is_never_accepted() -> None:
    check = check_with_armos_on(RAFT_BLOCKS, ARMOS_ON_THE_RAFT_ISLAND)
    raft_elsewhere = [place for place in check.item_shuffle_result.tracked if place.item == Item.RAFT]
    others = [place for place in check.item_shuffle_result.tracked if place.item != Item.RAFT and place.slot != "armos"]
    trapped = replace(check, item_shuffle_result=replace(check.item_shuffle_result,
                                                         tracked=[*others, armos_slot(Item.RAFT)]))
    assert raft_elsewhere
    assert Item.RAFT not in trapped.closure()[0]
    assert not trapped.collects_everything()


@pytest.mark.parametrize("zora", [NO_GATES, RAFT_BLOCKS])
def test_an_armos_on_an_open_screen_is_held_from_the_start(zora: str) -> None:
    check = check_with_armos_on(zora, 0x24)          # PRG0's Armos screen, never walled in
    assert check.collects(armos_slot(Item.BOOK), frozenset())
    assert Item.BOOK in check.closure()[0] or not any(place.slot == "armos" for place in
                                                       check.item_shuffle_result.tracked)


def test_the_reported_seed_never_hides_the_raft_under_its_own_block() -> None:
    flags, zora, seed = REPORTED
    world, _result = generate_world(plan(flags, seed, zora), remember_repo_base_rom())
    armos = world.overworld.get_cave(Destination.ARMOS_ITEM, OverworldItem)
    assert armos is not None
    assert not (world.overworld.armos_screen_ids[0] in gates.RAFT_ENCLOSED_SCREENS and armos.item == Item.RAFT)
