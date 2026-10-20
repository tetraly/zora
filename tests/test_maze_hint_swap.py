"""The Dead Woods' path outside the forest (owner, 2026-10-15; docs/deviations.md, docs/zora-extras.md):
with Randomize Dead Woods on and the non-dungeon caves left in place (Cave Shuffle: Vanilla or
Dungeons Only, after "?" and FL-DEP-02 rule 1's coin, and an overworld quest that is not mixed), the
hint shop selling the Dead Woods' path stands on $70, past the Dead Woods; the two maze hint shops
then exchange screens (shuffle_caves.sell_dead_woods_path_outside_the_forest), so every hint and
every place stays reachable."""
from copy import deepcopy
from functools import cache

import pytest

from zora import archipelago
from zora.flags import zora_flags
from zora.flags.codec import decode, encode
from zora.flags.fields import CAVE_SHUFFLE, OVERWORLD_QUEST, CaveShuffle, OverworldQuest, ThreeState
from zora.flags.zora_flags import ZoraFlags
from zora.generate.logic import FALSE, sweep
from zora.generate.pipeline import plan
from zora.generate.places import read_item
from zora.generate.steps import overworld_gates as gates
from zora.generate.steps.mixed_overworld_quest import second_quest_entries
from zora.generate.steps.shuffle_caves import (
    CaveWalkParts,
    cave_walk_parts,
    enrolled_entries,
    sell_dead_woods_path_outside_the_forest,
)
from zora.model.enums import Destination
from zora.model.overworld import Overworld
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora_measure.checkpoints.cave_shuffle import VANILLA_CAVES_FLAGS

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

# Where the two shops stand with the non-dungeon caves in place (PRG0's, and the second quest's)
LOST_HILLS_SHOP_HOME, DEAD_WOODS_SHOP_HOME = 0x1A, 0x70
MAZES = {
    "Dead Woods": zora_flags.encode(ZoraFlags(randomize_dead_woods=ThreeState.ON)),
    "both mazes": zora_flags.encode(ZoraFlags(randomize_lost_hills=ThreeState.ON,
                                              randomize_dead_woods=ThreeState.ON)),
    "Lost Hills": zora_flags.encode(ZoraFlags(randomize_lost_hills=ThreeState.ON)),
}
MIXED_QUESTS = (OverworldQuest.MIXED_FIRST_QUEST_VARIANT, OverworldQuest.MIXED_SECOND_QUEST_VARIANT)


def flags(quest: OverworldQuest, caves: CaveShuffle) -> str:
    return encode(decode(VANILLA_CAVES_FLAGS).updated(options={OVERWORLD_QUEST: quest, CAVE_SHUFFLE: caves}))


@cache
def overworld() -> Overworld:
    return parse_rom(remember_repo_base_rom()).overworld


def shop_screens(entries: list) -> tuple[int, int]:
    return (next(entry.screen for entry in entries if entry.code == gates.LOST_HILLS_HINT_SHOP),
            next(entry.screen for entry in entries if entry.code == gates.DEAD_WOODS_HINT_SHOP))


@pytest.mark.parametrize("quest", ["first", "second"])
@pytest.mark.parametrize("dead_woods", [False, True])
@pytest.mark.parametrize("lost_hills", [False, True])
@pytest.mark.parametrize("parts", [CaveWalkParts(False, False), CaveWalkParts(True, False),
                                   CaveWalkParts(False, True), CaveWalkParts(True, True)],
                         ids=["vanilla", "dungeons only", "non-dungeons only", "all caves"])
def test_the_shops_exchange_exactly_with_dead_woods_and_no_non_dungeon_part(
        quest: str, dead_woods: bool, lost_hills: bool, parts: CaveWalkParts) -> None:
    """Both quests' lists hold the shops on $1A and $70; they exchange exactly when Randomize Dead
    Woods is on and the walk has no non-dungeon part, whatever Randomize Lost Hills says."""
    world = deepcopy(overworld())
    entries = enrolled_entries(world) if quest == "first" else second_quest_entries(world)
    assert shop_screens(entries) == (LOST_HILLS_SHOP_HOME, DEAD_WOODS_SHOP_HOME)
    before = [(entry.screen, entry.code, entry.inner_palette) for entry in entries]
    sell_dead_woods_path_outside_the_forest(entries, gates.OverworldGates(lost_hills=lost_hills,
                                                                          dead_woods=dead_woods), parts)
    exchanged = dead_woods and not parts.non_dungeon_caves
    expected = (DEAD_WOODS_SHOP_HOME, LOST_HILLS_SHOP_HOME) if exchanged else (LOST_HILLS_SHOP_HOME,
                                                                               DEAD_WOODS_SHOP_HOME)
    assert shop_screens(entries) == expected
    # only the two codes change; every screen keeps its palette bits
    changed = [(screen, code) for (screen, code, palette), entry in zip(before, entries, strict=True)
               if (entry.code, entry.inner_palette) != (code, palette)]
    assert len(changed) == (2 if exchanged else 0)
    assert all(entry.inner_palette == palette for (_, _, palette), entry in zip(before, entries, strict=True))


def test_the_shops_new_screens_are_outside_the_mazes_they_sell() -> None:
    """After the exchange: the Dead Woods' path on $1A, which no gate holds (both mazes and the ladder's
    west half); the Lost Hills' path on $70, past the Dead Woods only, so no loop."""
    both = gates.OverworldGates(lost_hills=True, dead_woods=True, raft_blocks=True, bracelet_blocks=True)
    assert LOST_HILLS_SHOP_HOME not in both.gated_screens()
    assert DEAD_WOODS_SHOP_HOME in gates.DEAD_WOODS_GATED
    assert DEAD_WOODS_SHOP_HOME not in gates.LOST_HILLS_GATED | gates.DEAD_WOODS_WEST


def built(flag_string: str, zora: str, seed: int) -> archipelago.BuildResult:
    return archipelago.build_from_strings(flag_string, zora, seed, remember_repo_base_rom())


def shops_in_place(flag_string: str, zora: str, seed: int) -> bool:
    """The resolved Cave Shuffle and overworld quest leave the non-dungeon caves in place."""
    alternatives = plan(flag_string, seed, zora).alternatives
    return not cave_walk_parts(alternatives.cave_shuffle, alternatives.mix_overworld_quest
                               or alternatives.mix_overworld_quest_second_variant).non_dungeon_caves


def everything_reachable(result: archipelago.BuildResult) -> None:
    """No FALSE rule, and with every pool item received every place and event is reached (the
    check Archipelago's generation makes)."""
    logic = result.logic
    assert [name for name, rule in logic.events.items() if rule == FALSE] == []
    assert [name for name, rule in logic.places.items() if rule == FALSE] == []
    swept = sweep(logic, {}, [read_item(result.state.world, place) for place in result.state.places])
    assert swept.places == set(logic.places)
    assert swept.events == set(logic.events)


@pytest.mark.parametrize("maze", list(MAZES))
@pytest.mark.parametrize("quest", [OverworldQuest.FIRST_QUEST, OverworldQuest.SECOND_QUEST])
def test_a_seed_with_the_caves_in_place(maze: str, quest: OverworldQuest) -> None:
    """The first such seed under Cave Shuffle: Vanilla: the shops stand where the rule puts them,
    and every hint, place and event is reachable."""
    flag_string, zora = flags(quest, CaveShuffle.VANILLA), MAZES[maze]
    seed = next(seed for seed in range(40) if shops_in_place(flag_string, zora, seed))
    result = built(flag_string, zora, seed)
    doors = {code: [screen.screen_num for screen in result.state.world.overworld.screens
                    if screen.destination == code]
             for code in (gates.LOST_HILLS_HINT_SHOP, gates.DEAD_WOODS_HINT_SHOP)}
    exchanged = maze != "Lost Hills"
    assert doors[Destination.HINT_SHOP_2] == [LOST_HILLS_SHOP_HOME if exchanged else DEAD_WOODS_SHOP_HOME]
    assert doors[Destination.HINT_SHOP_1] == [DEAD_WOODS_SHOP_HOME if exchanged else LOST_HILLS_SHOP_HOME]
    everything_reachable(result)


@pytest.mark.slow
@pytest.mark.parametrize("caves", [CaveShuffle.VANILLA, CaveShuffle.DUNGEON_DOORS_ONLY, CaveShuffle.RANDOM])
@pytest.mark.parametrize("quest", [OverworldQuest.FIRST_QUEST, OverworldQuest.SECOND_QUEST, *MIXED_QUESTS])
def test_every_hint_and_place_reachable_over_40_seeds(caves: CaveShuffle, quest: OverworldQuest) -> None:
    """The cases Archipelago's generation failed on (Randomize Dead Woods with Cave Shuffle 0, 1 or
    Random: 10 to 19 of 40 seeds left the Dead Woods' hint unreachable), both mazes on, seeds 0-39."""
    flag_string = flags(quest, caves)
    for seed in range(40):
        everything_reachable(built(flag_string, MAZES["both mazes"], seed))
