"""Expanded Dungeon Locations, phase 2: on the 2nd Quest overworld (Overworld Quest: 2nd Quest, C01 =
1), Expanded Brackets (Dungeons Only) and "Expanded + shuffle everything else" (All Caves), phase 1's
rules mirrored (zora/generate/steps/expanded_dungeon_locations.py, SECOND_QUEST; owner, 2026-10-18).

The spots and their 2nd Quest kinds; every unchosen-spot rule on hand-made deals over the 2nd Quest
overworld: chosen first-quest entrances shown (1Q8, 1Q9, 1Q5's doorway, 1Q7's recorder entry),
unchosen ones closed with no cave, the pond (1Q2/2Q3) as 2Q3's recorder lake, the displaced caves
(own SHOP_2 and MEDIUM_SECRET, then borrowed SHOP_4) into 1Q1/2Q1 and 1Q4/2Q5 or dropped, a leftover
open cave taking SHOP_4, and the owner's redraw when two are left over. Then finished seeds of both
modes: each door its spot's, the recorder entries, the Armos item, the hints, the seed document, and
the logic reaching every place and event. And the flags: accepted, still held back from Archipelago."""
import copy
import json
import re
from collections import Counter
from functools import cache

import pytest

from tests.test_assignment import identity
from tests.test_expanded_dungeon_locations import ON, base, base_overworld
from zora import archipelago
from zora.flags import zora_flags
from zora.flags.codec import decode, encode
from zora.flags.fields import CaveShuffle, OverworldQuest, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.logic import logic_model, sweep
from zora.generate.pipeline import Built, build, extra_options, finish, plan
from zora.generate.rng import Rng
from zora.generate.steps import expanded_dungeon_locations as edl
from zora.generate.steps.cave_entries import MIXED_RECORDER_SCREENS, RECORDER_ENTRY_OFF, recorder_screens
from zora.generate.steps.expanded_dungeon_locations import SECOND_QUEST, ExpandedDeal, SpotKind
from zora.generate.steps.hint_text import REGION_PHRASES, region_of_screen
from zora.generate.steps.mixed_overworld_quest import (
    SCREEN_11_LAYOUT,
    SCREEN_60_LAYOUT,
    door_screen,
    is_second_quest_overworld,
    prepare_second_quest_screen_11,
    second_quest_overworld,
    show_second_quest_overworld,
)
from zora.model.enums import Destination, Item, QuestVisibility
from zora.model.overworld import Overworld
from zora.rom.base_rom import BASE_ROM_PATH
from zora.rom.parse.rom_file import parse_rom
from zora_export.seed_document import overworld_entry
from zora_web.api import seed_report

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

SECOND = {"C01": OverworldQuest.SECOND_QUEST}
BRACKETS = encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(
    options={**SECOND, "C05": CaveShuffle.DUNGEON_DOORS_ONLY}, toggles={"B02": ThreeState.OFF, "B04": ThreeState.OFF}))
EVERYTHING_ELSE = encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(
    options={**SECOND, "C05": CaveShuffle.ALL_CAVES}))
SEEDS = range(6)
# Dungeons Only with Shuffle Wood Sword Cave on: the coin (FL-DEP-02 rule 1) runs about half as All Caves
COIN = encode(decode(BRACKETS).updated(toggles={"B02": ThreeState.ON}))
CASES = [(flags, seed) for flags in (BRACKETS, EVERYTHING_ELSE) for seed in SEEDS]
CASE_IDS = [f"{mode}-{seed}" for mode in ("brackets", "everything-else") for seed in SEEDS]
NO_START_ROOMS: dict[int, int] = {}
SHOWN = (QuestVisibility.BOTH_QUESTS, QuestVisibility.FIRST_QUEST)
SPOT = SECOND_QUEST.by_label
POOL_RECORDER_ENTRIES = {spot.recorder_entry: spot.screen for spot in SECOND_QUEST.spots
                         if spot.recorder_entry is not None}


@cache
def built(seed: int, flags: str = BRACKETS) -> Built:
    return build(plan(flags, seed, ON), base())


@cache
def finished(seed: int, flags: str = BRACKETS) -> bytes:
    return finish(built(seed, flags), base())


@cache
def second_quest_recorder_list() -> tuple[int, ...]:
    """The 2nd Quest overworld's own recorder list (OW-QST-04): entry 0 off, the other ten live."""
    overworld = copy.deepcopy(base_overworld())
    second_quest_overworld(overworld)
    return tuple(overworld.recorder_secret_screens)


def deal_of(*labels: str) -> ExpandedDeal:
    """A hand-made deal over the 2nd Quest overworld: dungeons 1 to 9 on these spots, in order."""
    return ExpandedDeal({dungeon: SPOT[label] for dungeon, label in enumerate(labels, start=1)}, SECOND_QUEST)


def applied(deal: ExpandedDeal) -> Overworld:
    """The deal on the 2nd Quest overworld as the generation pass stages it."""
    overworld = copy.deepcopy(base_overworld())
    prepare_second_quest_screen_11(overworld)
    show_second_quest_overworld(overworld)
    edl.apply_deal(overworld, deal, base_overworld())
    return overworld


def placed(*labels: str) -> ExpandedDeal:
    deal = deal_of(*labels)
    assert edl.place_displaced_caves(deal, Rng(0))
    return deal


# --- the spots -----------------------------------------------------------------------------------

def test_the_spots_mirror_the_first_quests() -> None:
    """The same 15 spots; under a 2nd Quest overworld 1Q2/2Q3 is 2Q3's recorder lake (entry 6), 1Q8
    and 1Q9 are the secrets the base quest hides, and only 1Q1/2Q1 and 1Q4/2Q5 can be vacated."""
    assert [(spot.label, spot.screen) for spot in SECOND_QUEST.spots] == [(spot.label, spot.screen) for spot in edl.SPOTS]
    assert (SPOT["1Q2/2Q3"].kind, SPOT["1Q2/2Q3"].recorder_entry) == (SpotKind.RECORDER_LAKE, 6)
    assert {spot.label for spot in SECOND_QUEST.spots if spot.other_quest_secret} == {"1Q8", "1Q9"}
    assert SECOND_QUEST.vacated_tiers == (("1Q1/2Q1", "1Q4/2Q5"), ())
    assert SECOND_QUEST.carriers == ("1Q3", "1Q6", "2Q2") and SECOND_QUEST.opposite_quest_caves == (Destination.SHOP_4,)


def test_the_caves_on_pool_spots_are_the_second_quests_shops_and_secret() -> None:
    """On the 2nd Quest overworld the non-dungeon caves on pool spots are SHOP_2 at 1Q3 and
    MEDIUM_SECRET at 1Q6, each with other entrances; SHOP_4 (1Q's at 2Q2) has its own on $0F."""
    overworld = copy.deepcopy(base_overworld())
    second_quest_overworld(overworld)
    on_pool = {spot.label: overworld.screens[spot.screen].destination for spot in SECOND_QUEST.spots
               if not overworld.screens[spot.screen].destination.is_level
               and overworld.screens[spot.screen].destination != Destination.NONE}
    assert on_pool == {"1Q3": Destination.SHOP_2, "1Q6": Destination.MEDIUM_SECRET}
    for cave in (Destination.SHOP_2, Destination.MEDIUM_SECRET, Destination.SHOP_4):
        entrances = [screen.screen_num for screen in overworld.screens
                     if screen.destination == cave and screen.quest_visibility in SHOWN
                     and screen.screen_num not in edl.POOL_SCREENS]
        assert entrances, cave
    assert not SECOND_QUEST.sole_entrance_caves


# --- the unchosen spots --------------------------------------------------------------------------

ALL_SECOND_QUEST = ("1Q1/2Q1", "2Q2", "1Q2/2Q3", "2Q4", "1Q4/2Q5", "2Q6", "2Q7", "2Q8", "2Q9")
FIRST_QUEST_ENTRANCES = ("1Q5", "1Q7", "1Q8", "1Q9", "1Q3", "1Q6", "1Q1/2Q1", "2Q4", "2Q8")


def test_the_vanilla_spots_change_nothing_but_the_codes() -> None:
    """The nine second-quest spots chosen: each keeps its look and holds its dealt code; 1Q3 and 1Q6
    keep their shops; 2Q2's borrowed SHOP_4, with no open cave free, is dropped (it keeps $0F); the
    first-quest secrets stay hidden and 1Q5 and 1Q7 hold no leftover code."""
    deal = placed(*ALL_SECOND_QUEST)
    assert not deal.contents and deal.dropped == [Destination.SHOP_4]
    overworld = applied(deal)
    staged = copy.deepcopy(base_overworld())
    prepare_second_quest_screen_11(staged)
    second_quest_overworld(staged)
    for dungeon, label in enumerate(ALL_SECOND_QUEST, start=1):
        screen, kept = overworld.screens[SPOT[label].screen], staged.screens[SPOT[label].screen]
        assert (screen.destination, screen.quest_visibility, screen.screen_code) == \
            (Destination(dungeon), kept.quest_visibility, kept.screen_code)
        assert door_screen(overworld, dungeon) == SPOT[label].screen
    assert overworld.screens[SPOT["1Q3"].screen].destination == Destination.SHOP_2
    assert overworld.screens[SPOT["1Q6"].screen].destination == Destination.MEDIUM_SECRET
    for label in ("1Q5", "1Q7", "1Q8", "1Q9"):
        assert overworld.screens[SPOT[label].screen].destination == Destination.NONE, label
    assert overworld.recorder_secret_screens == list(second_quest_recorder_list())   # entry 0 off, as 2nd Quest
    assert overworld.recorder_reveals_listed_secrets_in_first_quest
    assert recorder_screens(overworld) == MIXED_RECORDER_SCREENS and is_second_quest_overworld(overworld)


def test_chosen_first_quest_entrances_show_on_the_second_quest_overworld() -> None:
    """1Q8's bush and 1Q9's bomb wall get quest field 0; 1Q5 keeps its first-quest doorway (layout
    $0A and its monsters, no fountain); 1Q7's recorder entry 0 is live; each is its dungeon's door."""
    deal = placed(*FIRST_QUEST_ENTRANCES)
    overworld = applied(deal)
    for dungeon, label in enumerate(FIRST_QUEST_ENTRANCES, start=1):
        screen = overworld.screens[SPOT[label].screen]
        assert screen.destination == Destination(dungeon) and screen.quest_visibility in SHOWN, label
        assert door_screen(overworld, dungeon) == SPOT[label].screen, label
    for label in ("1Q8", "1Q9"):
        assert overworld.screens[SPOT[label].screen].quest_visibility is QuestVisibility.BOTH_QUESTS
    doorway, first = overworld.screens[SPOT["1Q5"].screen], base_overworld().screens[SPOT["1Q5"].screen]
    assert (doorway.screen_code, doorway.enemy_spec, doorway.enemy_quantity) == \
        (first.screen_code, first.enemy_spec, first.enemy_quantity)
    assert doorway.screen_code != SCREEN_11_LAYOUT
    assert overworld.recorder_secret_screens[0] == SPOT["1Q7"].screen
    # 2Q3 unchosen: the pond entry off with the first, so the world does not read as 2nd Quest
    assert overworld.recorder_secret_screens[6] == RECORDER_ENTRY_OFF and not is_second_quest_overworld(overworld)


def test_a_chosen_1q5_is_a_door_while_the_world_reads_as_second_quest() -> None:
    """1Q5 and 2Q3 chosen, 1Q7 not: entry 0 off and the pond entry live (2nd Quest's mark), yet
    1Q5's screen, showing its doorway, is its dungeon's door (second_quest_leftovers)."""
    labels = ("1Q5", "1Q2/2Q3", "1Q4/2Q5", "1Q8", "1Q9", "2Q4", "2Q6", "2Q7", "2Q8")
    overworld = applied(placed(*labels))
    assert is_second_quest_overworld(overworld)
    assert door_screen(overworld, 1) == SPOT["1Q5"].screen and door_screen(overworld, 2) == SPOT["1Q2/2Q3"].screen


def test_each_closed_spot_holds_no_cave() -> None:
    """Under FIRST_QUEST_ENTRANCES: 2Q3's pond keeps its lake ($7B) with entry 6 off; 2Q2 shows the
    borrowed SHOP_4; 2Q6, 2Q7 and 2Q9 are hidden with no code, 2Q6's entry off; the second quest's
    other recorder secrets stay live."""
    overworld = applied(placed(*FIRST_QUEST_ENTRANCES))
    pond = overworld.screens[SPOT["1Q2/2Q3"].screen]
    assert (pond.destination, pond.screen_code) == (Destination.NONE, SCREEN_60_LAYOUT)
    assert overworld.screens[SPOT["2Q2"].screen].destination == Destination.SHOP_4
    for label in ("2Q6", "2Q7", "2Q9"):
        hidden = overworld.screens[SPOT[label].screen]
        assert (hidden.destination, hidden.quest_visibility) == (Destination.NONE, QuestVisibility.NEITHER_QUEST)
    entries = overworld.recorder_secret_screens
    assert entries[4] == entries[6] == RECORDER_ENTRY_OFF
    assert [screen for entry, screen in enumerate(entries) if entry not in POOL_RECORDER_ENTRIES] == \
        [screen for entry, screen in enumerate(second_quest_recorder_list()) if entry not in POOL_RECORDER_ENTRIES]


def test_an_unchosen_1q5_shows_the_fountain_and_1q7_its_lake() -> None:
    overworld = applied(placed(*ALL_SECOND_QUEST))
    fountain = overworld.screens[SPOT["1Q5"].screen]
    assert (fountain.destination, fountain.screen_code) == (Destination.NONE, SCREEN_11_LAYOUT)
    assert overworld.screens[SPOT["1Q7"].screen].destination == Destination.NONE
    assert overworld.recorder_secret_screens[0] == RECORDER_ENTRY_OFF


def test_own_caves_move_first_then_the_borrowed_one_is_dropped() -> None:
    """1Q3, 1Q6 and 2Q2 chosen, 1Q1/2Q1 and 1Q4/2Q5 free: the own SHOP_2 and MEDIUM_SECRET take
    them; the borrowed SHOP_4, last, finds none and is dropped (no redraw: it keeps $0F)."""
    deal = placed("1Q3", "1Q6", "2Q2", "1Q2/2Q3", "1Q5", "1Q7", "1Q8", "1Q9", "2Q4")
    tier_1 = {SPOT[label].screen for label in SECOND_QUEST.vacated_tiers[0]}
    assert set(deal.contents) == tier_1
    assert sorted(deal.contents.values()) == sorted([Destination.SHOP_2, Destination.MEDIUM_SECRET])
    assert deal.dropped == [Destination.SHOP_4] and not deal.closed_ponds


def test_displaced_caves_with_no_open_cave_are_dropped_never_redrawn() -> None:
    deal = placed("1Q1/2Q1", "1Q4/2Q5", "1Q3", "1Q6", "2Q2", "1Q5", "1Q7", "1Q8", "1Q9")
    assert not deal.contents
    assert deal.dropped == [Destination.SHOP_2, Destination.MEDIUM_SECRET, Destination.SHOP_4]
    assert not any(edl.deal_expanded_dungeon_locations(key, NO_START_ROOMS, SECOND_QUEST).redraws
                   for key in range(2000))


def test_a_leftover_open_cave_takes_shop_4() -> None:
    """1Q4/2Q5 chosen, 1Q1/2Q1 free and no carrier chosen: SHOP_4, the cave the first quest shows at
    a second-quest level location (2Q2's), one more entrance to it; 2Q2 shows it too."""
    deal = placed("1Q4/2Q5", "1Q2/2Q3", "1Q5", "1Q7", "1Q8", "1Q9", "2Q4", "2Q6", "2Q7")
    assert deal.contents == {SPOT["1Q1/2Q1"].screen: Destination.SHOP_4}
    overworld = applied(deal)
    assert overworld.screens[SPOT["1Q1/2Q1"].screen].destination == Destination.SHOP_4
    assert overworld.screens[SPOT["2Q2"].screen].destination == Destination.SHOP_4


def test_two_leftover_open_caves_redraw_the_deal() -> None:
    """Owner ruling, 2026-10-18: both open caves free with nothing displaced (1Q3, 1Q6 and 2Q2
    unchosen) leaves two caves for one SHOP_4, and the deal is drawn again."""
    deal = deal_of("1Q2/2Q3", "1Q5", "1Q7", "1Q8", "1Q9", "2Q4", "2Q6", "2Q7", "2Q8")
    assert not edl.place_displaced_caves(deal, Rng(0)) and deal.too_many_leftovers
    deals = [edl.deal_expanded_dungeon_locations(key, NO_START_ROOMS, SECOND_QUEST) for key in range(6000)]
    assert any(deal.leftover_redraws for deal in deals), "no deal of 6,000 was redrawn for its leftovers"
    for deal in deals:
        assert any(label in deal.chosen for label in ("1Q1/2Q1", "1Q4/2Q5", *SECOND_QUEST.carriers))
    assert not any(edl.deal_expanded_dungeon_locations(key, NO_START_ROOMS).leftover_redraws for key in range(2000))


def test_every_spot_is_chosen_about_as_often() -> None:
    counts: Counter[str] = Counter()
    deals = 3000
    for key in range(deals):
        counts.update(edl.deal_expanded_dungeon_locations(key, NO_START_ROOMS, SECOND_QUEST).chosen)
    assert set(counts) == set(SPOT) and all(0.55 < count / deals < 0.65 for count in counts.values()), counts


# --- finished seeds ------------------------------------------------------------------------------

def deal_in(seed: int, flags: str) -> ExpandedDeal:
    deal = built(seed, flags).result.expanded_deal
    assert deal is not None and deal.base == SECOND_QUEST      # by value: a shared build may be unpickled
    return deal


@pytest.mark.parametrize(("flags", "seed"), CASES, ids=CASE_IDS)
def test_each_dungeon_door_is_its_spot_and_nothing_else_holds_a_level(flags: str, seed: int) -> None:
    deal = deal_in(seed, flags)
    overworld = parse_rom(finished(seed, flags)).overworld
    caves = built(seed, flags).result.overworld
    assert caves is not None
    for dungeon, spot in deal.dungeons.items():
        assert door_screen(overworld, dungeon) == spot.screen
        assert caves.entry_door(dungeon) == spot.screen
    shown = [screen.screen_num for screen in overworld.screens
             if screen.destination.is_level and screen.quest_visibility in SHOWN]
    assert sorted(shown) == sorted(spot.screen for spot in deal.dungeons.values())
    for spot in SECOND_QUEST.spots:
        if not deal.is_chosen(spot) and spot.kind in (SpotKind.HIDDEN, SpotKind.RECORDER_LAKE, SpotKind.FOUNTAIN):
            assert overworld.screens[spot.screen].destination == Destination.NONE, spot.label


@pytest.mark.parametrize(("flags", "seed"), CASES, ids=CASE_IDS)
def test_the_recorder_and_the_armos_item_follow_the_deal(flags: str, seed: int) -> None:
    """Each pool recorder entry is live only while its spot is chosen; the second quest's other
    recorder secrets stay; the first quest reveals them (branch $D0); the recorder set is the
    eleven; the Armos item avoids 2Q2 while it holds a dungeon."""
    deal = deal_in(seed, flags)
    overworld = parse_rom(finished(seed, flags)).overworld
    for entry, screen in enumerate(overworld.recorder_secret_screens):
        if entry in POOL_RECORDER_ENTRIES:
            chosen = any(spot.recorder_entry == entry for spot in deal.dungeons.values())
            assert screen == (POOL_RECORDER_ENTRIES[entry] if chosen else RECORDER_ENTRY_OFF), entry
        else:
            assert screen == second_quest_recorder_list()[entry], entry
    assert overworld.recorder_reveals_listed_secrets_in_first_quest
    assert recorder_screens(overworld) == MIXED_RECORDER_SCREENS
    caves = built(seed, flags).result.overworld
    assert caves is not None
    if "2Q2" in deal.chosen:
        assert caves.armos_screen != edl.ARMOS_SPOT_SCREEN


@pytest.mark.parametrize(("flags", "seed"), CASES, ids=CASE_IDS)
def test_level_location_hints_name_the_spots_region(flags: str, seed: int) -> None:
    deal = deal_in(seed, flags)
    texts = [hint["text"] for hint in json.loads(seed_report(finished(seed, flags), flags, seed, ON)["json"])["hints"]]
    for text in texts:
        found = re.search(r"LEVEL-(\d) LIES", text)
        if found:
            assert REGION_PHRASES[region_of_screen(deal.dungeons[int(found.group(1))].screen)] in text, text


@pytest.mark.parametrize(("flags", "seed"), CASES, ids=CASE_IDS)
def test_the_seed_document_lists_each_dungeon_at_its_spot(flags: str, seed: int) -> None:
    deal = deal_in(seed, flags)
    screens = overworld_entry(parse_rom(finished(seed, flags)))["screens"]
    levels = {screen["number"]: screen["cave"] for screen in screens if "shownName" in screen["cave"]}
    assert sorted(levels) == sorted(spot.screen for spot in deal.dungeons.values())


@pytest.mark.parametrize(("flags", "seed"), CASES, ids=CASE_IDS)
def test_the_logic_reaches_every_place_and_event(flags: str, seed: int) -> None:
    logic = logic_model(built(seed, flags))
    swept = sweep(logic, identity(built(seed, flags)))
    assert swept.reaches_goal
    assert set(logic.places) == swept.places and set(logic.events) == swept.events


def test_a_door_on_a_gated_spot_needs_its_item() -> None:
    """The recorder at 1Q7, 2Q3's pond and 2Q6 (the eleven-screen set), the raft at 1Q4/2Q5, the
    ladder at 2Q8, the bracelet at 2Q4."""
    rules = extra_options(built(0).plan).logic_rules
    for label in ("1Q7", "1Q2/2Q3", "2Q6"):
        assert Item.RECORDER in rules.needs(SPOT[label].screen), label
    assert Item.RAFT in rules.needs(SPOT["1Q4/2Q5"].screen)
    assert Item.LADDER in rules.needs(SPOT["2Q8"].screen)
    assert Item.POWER_BRACELET in rules.needs(SPOT["2Q4"].screen)


def test_everything_else_moves_the_other_caves() -> None:
    """Under All Caves the other caves leave their 2nd Quest screens, the dungeons staying on their spots."""
    staged = copy.deepcopy(base_overworld())
    second_quest_overworld(staged)
    moved: Counter[int] = Counter()
    for seed in SEEDS:
        overworld = parse_rom(finished(seed, EVERYTHING_ELSE)).overworld
        moved.update(screen.screen_num for screen, kept in zip(overworld.screens, staged.screens, strict=True)
                     if screen.screen_num not in edl.POOL_SCREENS and screen.destination != kept.destination)
    assert len(moved) > 20


@pytest.mark.slow
@pytest.mark.parametrize("flags", [BRACKETS, EVERYTHING_ELSE], ids=["brackets", "everything-else"])
@pytest.mark.parametrize("seed", range(6, 46))
def test_more_seeds_reach_every_place_and_event(flags: str, seed: int) -> None:
    test_each_dungeon_door_is_its_spot_and_nothing_else_holds_a_level(flags, seed)
    test_the_logic_reaches_every_place_and_event(flags, seed)


# --- the flags -----------------------------------------------------------------------------------

@pytest.mark.parametrize("flags", [BRACKETS, EVERYTHING_ELSE], ids=["brackets", "everything-else"])
def test_the_second_quest_overworld_is_accepted(flags: str) -> None:
    assert zora_flags.validate(zora_flags.decode(ON), decode(flags)) == []
    assert plan(flags, 0, ON).zora_resolved.is_on("expanded_dungeon_locations")


def test_the_coin_is_accepted_with_the_warning() -> None:
    assert zora_flags.validate(zora_flags.decode(ON), decode(COIN)) == []
    assert zora_flags.warnings(zora_flags.decode(ON), decode(COIN))
    resolved = {plan(COIN, seed, ON).alternatives.cave_shuffle for seed in range(16)}
    assert resolved == {CaveShuffle.DUNGEON_DOORS_ONLY, CaveShuffle.ALL_CAVES}


def test_offered_by_archipelago() -> None:
    """Released in 2fd34b5, held in 1e585a8 for the 2nd Quest Brackets seed 30, released again once
    acceptance E11 (64109a8) fixed it and its rescan passed (archipelago.HELD_BACK's comment)."""
    assert "expanded_dungeon_locations" not in archipelago.HELD_BACK
    offered = next(spec for spec in archipelago.option_fields() if spec.id == "expanded_dungeon_locations")
    assert offered.values == tuple(int(state) for state in ThreeState)
