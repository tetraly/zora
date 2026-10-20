"""E11, ZORA's own acceptance rule (docs/deviations.md "The white-sword cave's hearts"): a pass whose
white-sword cave holds a tracked item the player needs, behind more hearts than can be reached
without it, is rejected.

Expanded Brackets on the 2nd Quest overworld (Expanded Dungeon Locations on), seed 30, from the
batch run on bbe10f0: its first accepted pass put the ladder in the white-sword cave, which asks
for 6 hearts. Without an item, Link reaches 3 starting hearts, the Armos heart container and one
take-any cave ($20); the coast's recorder needs the ladder and everything else needs one of the
two, so that ROM could not be beaten. VA-REJ-07's closure never counts hearts; the logic walk does
(docs/archipelago.md "The hearts")."""
import pytest

from tests.needs import needs_base_rom
from tests.test_assignment import identity
from tests.test_expanded_dungeon_locations import ON
from tests.test_expanded_dungeon_locations_second_quest import BRACKETS
from zora.generate import generation_pass
from zora.generate.logic import logic_model, sweep
from zora.generate.pipeline import Built, build, extra_options, plan
from zora.generate.steps.randomize_magical_sword import WHITE_SWORD_SLOT, white_sword_cave_hearts_met
from zora.model.enums import Destination, Item
from zora.model.overworld import ItemCave
from zora.rom.base_rom import remember_repo_base_rom

pytestmark = needs_base_rom

SEED = 30
HIGHEST_WHITE_SWORD_HEARTS = 6          # FP-SWORD-01's range, 4 to 6, with C20 and C21 at 0
# Without an item: 3 starting hearts and the Armos heart container; the one take-any cave reached
# ($20) adds none to the count (all but two), and at most 1 in the game: 5, short of 6 either way
HEARTS_COUNTED = 4


def built() -> Built:
    return build(plan(BRACKETS, SEED, ON), remember_repo_base_rom())


def built_without_e11(monkeypatch: pytest.MonkeyPatch) -> Built:
    """The seed as the spec accepts it: E11 passes every attempt."""
    monkeypatch.setattr(generation_pass, "white_sword_cave_hearts_met", lambda *args, **kwargs: True)
    return built()


def hearts_met(seed: Built, hearts_required: int) -> bool:
    world, result = seed.world, seed.result
    assert result.item_shuffle_result is not None and result.overworld is not None
    assert result.extra_pool_items is not None
    extras = extra_options(seed.plan)
    return white_sword_cave_hearts_met(world.levels, result.item_shuffle_result, result.extra_pool_items,
                                       world.overworld, result.overworld, hearts_required,
                                       extras.starting_heart_containers, extras.logic_rules)


def test_the_highest_count_is_judged_while_b10_draws_after_ship() -> None:
    """Change Sword Hearts (B10) on with Randomize Magical Sword off: the counts are drawn after the
    attempt ships, so E11 judges the range's highest, 6."""
    planned = plan(BRACKETS, SEED, ON)
    assert planned.steps.change_sword_hearts and not extra_options(planned).checks_magical_sword_hearts
    assert max(planned.alternatives.white_sword_hearts) == HIGHEST_WHITE_SWORD_HEARTS


def test_without_e11_the_ladder_waits_behind_hearts_no_player_reaches(monkeypatch: pytest.MonkeyPatch) -> None:
    seed = built_without_e11(monkeypatch)
    assert seed.result.item_shuffle_result is not None
    in_cave = [place.item for place in seed.result.item_shuffle_result.tracked if place.slot == WHITE_SWORD_SLOT]
    assert in_cave == [Item.LADDER]
    cave = seed.world.overworld.get_cave(Destination.WHITE_SWORD_CAVE, ItemCave)
    assert cave is not None and cave.heart_requirement == HIGHEST_WHITE_SWORD_HEARTS
    assert hearts_met(seed, HEARTS_COUNTED)
    assert not hearts_met(seed, HEARTS_COUNTED + 1)
    assert not hearts_met(seed, HIGHEST_WHITE_SWORD_HEARTS)  # E11 rejects it
    assert not sweep(logic_model(seed), identity(seed)).reaches_goal


def test_e11_rejects_that_pass_and_the_seed_is_beatable() -> None:
    seed = built()
    assert seed.result.acceptance_rejections["E11"] >= 1
    assert sweep(logic_model(seed), identity(seed)).reaches_goal
