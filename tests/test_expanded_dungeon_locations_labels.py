"""Expanded Dungeon Locations' spot labels against generation, for every overworld quest.

A spot's label, 1Qn or 2Qn, is the level number the game shows at that screen in the original
quest: that quest's overworld with its own dungeons and every dungeon in place. It is not the door
code, which generation numbers levels by: with the second quest's dungeons the paired levels (2 and
3, 4 and 5, 7 and 8) show each other's numbers, so 2Q2 ($34) holds door code 3 and 2Q3 ($3C) code 2.
The deal and everything after it work by screen, never by a label's number."""
from functools import cache

import pytest

from tests.needs import needs_base_rom
from zora.flags import zora_flags
from zora.flags.codec import decode, encode
from zora.flags.fields import CaveShuffle, DungeonLayoutSource, OverworldQuest, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import build, plan
from zora.generate.steps.expanded_dungeon_locations import FIRST_QUEST, SECOND_QUEST, BaseQuest
from zora.generate.steps.mixed_overworld_quest import door_screen
from zora.model.game_world import GameWorld
from zora.rom.base_rom import remember_repo_base_rom

pytestmark = needs_base_rom

QUESTS = {1: (FIRST_QUEST, OverworldQuest.FIRST_QUEST, DungeonLayoutSource.FIRST_QUEST),
          2: (SECOND_QUEST, OverworldQuest.SECOND_QUEST, DungeonLayoutSource.SECOND_QUEST)}
# The second quest's labels whose shown number is not the door code: (label, screen, door code)
SECOND_QUEST_PAIRS = [("2Q2", 0x34, 3), ("2Q3", 0x3C, 2), ("2Q4", 0x1B, 5), ("2Q5", 0x45, 4),
                      ("2Q7", 0x6C, 8), ("2Q8", 0x19, 7)]


@cache
def original_quest(quest: int) -> GameWorld:
    """The quest's own overworld and dungeons, every dungeon on its own door (Cave Shuffle: Vanilla)."""
    _, overworld_quest, dungeon_quest = QUESTS[quest]
    flags = encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(
        options={"C01": overworld_quest, "C02": dungeon_quest, "C05": CaveShuffle.VANILLA}))
    built = plan(flags, 1, "")
    assert built.settings.option(zora_flags.CAVE_SHUFFLE) == CaveShuffle.VANILLA
    return build(built, remember_repo_base_rom()).world


def labelled_screens(base: BaseQuest, quest: int) -> dict[int, int]:
    """The quest's labels on this base's spots: shown level number -> screen."""
    return {int(name[2]): spot.screen for spot in base.spots for name in spot.label.split("/")
            if int(name[0]) == quest}


def shown_doors(world: GameWorld) -> dict[int, int | None]:
    """Each shown level number's door screen."""
    return {level.rom_level_num: door_screen(world.overworld, level.level_num) for level in world.levels}


@pytest.mark.parametrize("quest", QUESTS, ids=["1st Quest", "2nd Quest"])
def test_each_label_is_the_level_the_original_quest_shows_there(quest: int) -> None:
    base = QUESTS[quest][0]
    assert labelled_screens(base, quest) == shown_doors(original_quest(quest))


@pytest.mark.parametrize(("label", "screen", "door_code"), SECOND_QUEST_PAIRS)
def test_second_quest_labels_name_the_shown_number_not_the_door_code(label: str, screen: int,
                                                                     door_code: int) -> None:
    world = original_quest(2)
    assert next(spot.screen for spot in SECOND_QUEST.spots if label in spot.label.split("/")) == screen
    assert door_screen(world.overworld, door_code) == screen
    assert next(level.rom_level_num for level in world.levels if level.level_num == door_code) == int(label[2])


def test_both_bases_label_the_same_screens() -> None:
    assert [(spot.label, spot.screen) for spot in FIRST_QUEST.spots] == \
        [(spot.label, spot.screen) for spot in SECOND_QUEST.spots]


@pytest.mark.parametrize("overworld_quest", [OverworldQuest.MIXED_FIRST_QUEST_VARIANT,
                                             OverworldQuest.MIXED_SECOND_QUEST_VARIANT, OverworldQuest.RANDOM])
def test_no_other_overworld_quest_takes_the_deal(overworld_quest: OverworldQuest) -> None:
    """The mixed and random overworlds are refused, so no labels apply to them."""
    z1r = decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(
        options={"C01": overworld_quest, "C05": CaveShuffle.DUNGEON_DOORS_ONLY})
    flags = zora_flags.ZoraFlags(expanded_dungeon_locations=ThreeState.ON)
    assert any(zora_flags.OVERWORLD_QUEST.id in fields
               for _, fields in zora_flags.expanded_dungeon_locations_conflicts(flags, z1r))
