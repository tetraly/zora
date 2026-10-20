"""Expanded Dungeon Locations, phase 1: on the 1st Quest overworld, Expanded Brackets (Cave Shuffle:
Dungeons Only, step 1) and "Expanded + shuffle everything else" (All Caves, step 2)
(zora/generate/steps/expanded_dungeon_locations.py; owner and Bogie, 2026-10-18).

The deal (nine distinct spots, every dungeon one, its own stream, the start-room ban), every
unchosen-spot rule and the redraw, on hand-made deals; then finished seeds: each dungeon's door is
its spot's and shown, nothing else holds a level code, closed spots hold no cave, the recorder
entries and the Armos item's screen, the level-location hints name each spot's region, and the
logic reaches every place and event, under both modes; under All Caves the walk moves only the
other caves, never onto a closed spot, and the wooden-sword cave never takes a dungeon door. And the
flags: what the option is refused with and warned about, and its values held back from Archipelago."""
import copy
import json
import re
from collections import Counter
from functools import cache

import pytest

from tests.test_assignment import identity
from zora import archipelago
from zora.flags import zora_flags
from zora.flags.codec import decode, encode
from zora.flags.fields import CaveShuffle, OverworldQuest, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.logic import logic_model, sweep
from zora.generate.pipeline import Built, FlagsRefused, build, extra_options, finish, plan
from zora.generate.rng import Rng
from zora.generate.steps import expanded_dungeon_locations as edl
from zora.generate.steps.cave_entries import (
    EXPANDED_RECORDER_SCREENS,
    MIXED_RECORDER_SCREENS,
    RECORDER_ENTRY_OFF,
    RECORDER_SCREENS,
    Entry,
    recorder_screens,
)
from zora.generate.steps.expanded_dungeon_locations import SPOTS, SPOTS_BY_LABEL, ExpandedDeal, deal_entries
from zora.generate.steps.hint_text import REGION_PHRASES, region_of_screen
from zora.generate.steps.mixed_overworld_quest import (
    SCREEN_11_LAYOUT,
    SCREEN_60_LAYOUT,
    door_screen,
    is_second_quest_overworld,
)
from zora.generate.steps.shuffle_caves import CaveWalkParts, enrolled_entries, walk_destination_codes
from zora.model.enums import Destination, Enemy, Item, QuestVisibility
from zora.model.overworld import Overworld
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora_web.api import seed_report

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

FIELD = "expanded_dungeon_locations"
BRACKETS = encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(
    options={"C05": CaveShuffle.DUNGEON_DOORS_ONLY}, toggles={"B02": ThreeState.OFF, "B04": ThreeState.OFF}))
ON = zora_flags.encode(zora_flags.ZoraFlags(expanded_dungeon_locations=ThreeState.ON))
RANDOM = zora_flags.encode(zora_flags.ZoraFlags(expanded_dungeon_locations=ThreeState.POSSIBLE))
EVERYTHING_ELSE = encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(options={"C05": CaveShuffle.ALL_CAVES}))
# Dungeons Only with Shuffle Wood Sword Cave on: the coin (FL-DEP-02 rule 1) runs about half as All Caves
COIN = encode(decode(BRACKETS).updated(toggles={"B02": ThreeState.ON}))
SEEDS = range(6)
CASES = [(flags, seed) for flags in (BRACKETS, EVERYTHING_ELSE) for seed in SEEDS]
CASE_IDS = [f"{mode}-{seed}" for mode in ("brackets", "everything-else") for seed in SEEDS]
NO_START_ROOMS: dict[int, int] = {}
SHOWN = (QuestVisibility.BOTH_QUESTS, QuestVisibility.FIRST_QUEST)


@cache
def base() -> bytes:
    return remember_repo_base_rom()


@cache
def base_overworld() -> Overworld:
    return parse_rom(base()).overworld


@cache
def built(seed: int, flags: str = BRACKETS) -> Built:
    return build(plan(flags, seed, ON), base())


@cache
def finished(seed: int, flags: str = BRACKETS) -> bytes:
    return finish(built(seed, flags), base())


def deal_of(*labels: str) -> ExpandedDeal:
    """A hand-made deal: dungeons 1 to 9 on these spots, in order."""
    return ExpandedDeal({dungeon: SPOTS_BY_LABEL[label] for dungeon, label in enumerate(labels, start=1)})


def applied(deal: ExpandedDeal) -> Overworld:
    overworld = copy.deepcopy(base_overworld())
    edl.apply_deal(overworld, deal)
    return overworld


# --- the deal ------------------------------------------------------------------------------------

def test_the_pool_is_fifteen_spots_on_fifteen_screens() -> None:
    assert len(SPOTS) == 15 and len(edl.POOL_SCREENS) == 15
    assert {spot.label for spot in SPOTS} == {*(f"1Q{n}" for n in (3, 5, 6, 7, 8, 9)), "1Q1/2Q1", "1Q2/2Q3",
                                             "1Q4/2Q5", *(f"2Q{n}" for n in (2, 4, 6, 7, 8, 9))}


@pytest.mark.parametrize("key", range(40))
def test_the_deal_puts_each_dungeon_on_its_own_spot(key: int) -> None:
    deal = edl.deal_expanded_dungeon_locations(key, NO_START_ROOMS)
    assert sorted(deal.dungeons) == list(range(1, 10)) and len(deal.chosen) == 9
    assert deal == edl.deal_expanded_dungeon_locations(key, NO_START_ROOMS)       # its own stream only


def test_every_spot_is_chosen_about_as_often() -> None:
    """Uniform nine of 15: each spot in 60% of deals (the redraw moves six of them a little)."""
    counts = {spot.label: 0 for spot in SPOTS}
    deals = 3000
    for key in range(deals):
        for label in edl.deal_expanded_dungeon_locations(key, NO_START_ROOMS).chosen:
            counts[label] += 1
    assert all(0.55 < count / deals < 0.65 for count in counts.values()), counts


def test_the_start_room_ban_is_kept() -> None:
    """A dungeon never lands on its own start room's screen: with every dungeon's start room on
    1Q3's screen, no deal holds 1Q3, and a deal that chose it is drawn again."""
    banned = dict.fromkeys(range(1, 10), SPOTS_BY_LABEL["1Q3"].screen)
    for key in range(50):
        deal = edl.deal_expanded_dungeon_locations(key, banned)
        assert "1Q3" not in deal.chosen
    assert any(edl.deal_expanded_dungeon_locations(key, banned).ban_redraws for key in range(50))


def test_the_deal_comes_from_its_own_stream_keyed_by_both_strings() -> None:
    key = edl.expanded_dungeon_locations_seed(7, BRACKETS, ON)
    assert key != edl.expanded_dungeon_locations_seed(8, BRACKETS, ON)
    assert key != edl.expanded_dungeon_locations_seed(7, BRACKETS, RANDOM)
    assert plan(BRACKETS, 7, ON).generation_seed != key


# --- the unchosen spots --------------------------------------------------------------------------

ALL_FIRST_QUEST = ("1Q1/2Q1", "1Q2/2Q3", "1Q3", "1Q4/2Q5", "1Q5", "1Q6", "1Q7", "1Q8", "1Q9")
ALL_SECOND_QUEST_EXTRA = ("2Q2", "2Q4", "2Q6", "2Q7", "2Q8", "2Q9", "1Q1/2Q1", "1Q4/2Q5", "1Q8")


def test_the_vanilla_spots_change_nothing_but_the_recorder_entries() -> None:
    """The nine first-quest spots chosen in order: each keeps its own level, the second-quest
    secrets stay hidden with no code, 2Q2 keeps SHOP_4."""
    deal = deal_of(*ALL_FIRST_QUEST)
    assert edl.place_displaced_caves(deal, Rng(0)) and not deal.contents and not deal.closed_ponds
    overworld = applied(deal)
    for dungeon, label in enumerate(ALL_FIRST_QUEST, start=1):
        screen = overworld.screens[SPOTS_BY_LABEL[label].screen]
        kept = base_overworld().screens[SPOTS_BY_LABEL[label].screen]
        assert (screen.destination, screen.quest_visibility, screen.screen_code) == \
            (Destination(dungeon), kept.quest_visibility, kept.screen_code)
    for label in ("2Q4", "2Q6", "2Q7", "2Q8", "2Q9"):
        screen = overworld.screens[SPOTS_BY_LABEL[label].screen]
        assert (screen.destination, screen.quest_visibility) == (Destination.NONE, QuestVisibility.NEITHER_QUEST)
    assert overworld.screens[SPOTS_BY_LABEL["2Q2"].screen].destination == Destination.SHOP_4
    assert overworld.recorder_secret_screens[0] == 0x42
    assert all(entry == RECORDER_ENTRY_OFF for entry in overworld.recorder_secret_screens[1:])
    assert not overworld.recorder_reveals_listed_secrets_in_first_quest
    assert recorder_screens(overworld) == RECORDER_SCREENS and not is_second_quest_overworld(overworld)


def test_a_chosen_second_quest_secret_shows_in_the_first_quest() -> None:
    deal = deal_of(*ALL_SECOND_QUEST_EXTRA)
    assert edl.place_displaced_caves(deal, Rng(0))
    overworld = applied(deal)
    for dungeon, label in enumerate(ALL_SECOND_QUEST_EXTRA, start=1):
        screen = overworld.screens[SPOTS_BY_LABEL[label].screen]
        assert screen.destination == Destination(dungeon) and screen.quest_visibility in SHOWN
        assert door_screen(overworld, dungeon) == SPOTS_BY_LABEL[label].screen
    # 2Q6 chosen, 1Q7 not: only 2Q6's recorder entry, and the second quest's reveal in the first
    assert overworld.recorder_secret_screens[4] == 0x30 and overworld.recorder_reveals_listed_secrets_in_first_quest
    assert all(entry == RECORDER_ENTRY_OFF for index, entry in enumerate(overworld.recorder_secret_screens)
               if index != 4)
    assert recorder_screens(overworld) == EXPANDED_RECORDER_SCREENS
    assert not is_second_quest_overworld(overworld)        # though the first entry is off


def test_each_closed_spot_holds_no_cave() -> None:
    """Under ALL_SECOND_QUEST_EXTRA: 1Q5 shows the fountain (layout $7B, monster byte $2F), 1Q7 its
    lake with the entry off, 1Q9 is hidden; none holds a cave code."""
    deal = deal_of(*ALL_SECOND_QUEST_EXTRA)
    assert edl.place_displaced_caves(deal, Rng(0))
    overworld = applied(deal)
    fountain = overworld.screens[SPOTS_BY_LABEL["1Q5"].screen]
    assert (fountain.destination, fountain.screen_code, fountain.enemy_spec.enemy) == \
        (Destination.NONE, SCREEN_11_LAYOUT, Enemy(0x2F))
    assert overworld.screens[SPOTS_BY_LABEL["1Q7"].screen].destination == Destination.NONE
    assert overworld.recorder_secret_screens[0] == RECORDER_ENTRY_OFF
    hidden = overworld.screens[SPOTS_BY_LABEL["1Q9"].screen]
    assert (hidden.destination, hidden.quest_visibility) == (Destination.NONE, QuestVisibility.NEITHER_QUEST)


def test_the_displaced_shop_takes_a_vacated_open_cave_first() -> None:
    """2Q2 chosen, 1Q1 and 1Q4 free: SHOP_4 takes one of them; the other takes a cave the second
    quest shows at a first-quest level location; 1Q3 and 1Q6 show theirs."""
    deal = deal_of("2Q2", "1Q2/2Q3", "1Q5", "1Q7", "1Q8", "1Q9", "2Q4", "2Q6", "2Q7")
    assert edl.place_displaced_caves(deal, Rng(1))
    tier_1 = {SPOTS_BY_LABEL[label].screen for label in ("1Q1/2Q1", "1Q4/2Q5")}
    assert set(deal.contents) == tier_1 and Destination.SHOP_4 in deal.contents.values()
    other = next(cave for cave in deal.contents.values() if cave != Destination.SHOP_4)
    assert other in edl.FIRST_QUEST.opposite_quest_caves and not deal.dropped and not deal.closed_ponds
    overworld = applied(deal)
    assert overworld.screens[SPOTS_BY_LABEL["1Q3"].screen].destination == Destination.SHOP_2
    assert overworld.screens[SPOTS_BY_LABEL["1Q6"].screen].destination == Destination.MEDIUM_SECRET
    assert overworld.screens[SPOTS_BY_LABEL["2Q2"].screen].destination == Destination(1)


def test_tier_2_takes_a_cave_once_tier_1_is_full_and_a_borrowed_cave_is_dropped() -> None:
    """2Q2, 1Q3 and 1Q6 chosen, 1Q1 and 1Q4 chosen, 1Q2 free: SHOP_4 to 1Q2; SHOP_2 and
    MEDIUM_SECRET, with other entrances in the second quest only, are dropped."""
    deal = deal_of("2Q2", "1Q3", "1Q6", "1Q1/2Q1", "1Q4/2Q5", "1Q5", "1Q7", "1Q8", "1Q9")
    assert edl.place_displaced_caves(deal, Rng(0))
    assert deal.contents == {SPOTS_BY_LABEL["1Q2/2Q3"].screen: Destination.SHOP_4}
    assert deal.dropped == [Destination.SHOP_2, Destination.MEDIUM_SECRET]


def test_a_free_pond_cave_closes_as_the_second_quest_lake() -> None:
    deal = deal_of("1Q1/2Q1", "1Q4/2Q5", "1Q5", "1Q7", "1Q8", "1Q9", "2Q4", "2Q6", "2Q7")   # no carrier chosen
    assert edl.place_displaced_caves(deal, Rng(0))
    assert [spot.label for spot in deal.closed_ponds] == ["1Q2/2Q3"]
    pond = applied(deal).screens[SPOTS_BY_LABEL["1Q2/2Q3"].screen]
    assert (pond.destination, pond.screen_code) == (Destination.NONE, SCREEN_60_LAYOUT)


def test_shop_4_with_no_open_cave_takes_an_unchosen_carriers_place() -> None:
    """1Q1, 1Q2 and 1Q4 all chosen with 2Q2: SHOP_4 (no other first-quest entrance) replaces the
    borrowed cave of an unchosen 1Q3 or 1Q6, which is dropped (here 1Q6's; chosen 1Q3's SHOP_2,
    with no open cave left, is dropped too)."""
    deal = deal_of("2Q2", "1Q1/2Q1", "1Q2/2Q3", "1Q4/2Q5", "1Q3", "1Q5", "1Q7", "1Q8", "1Q9")
    assert edl.place_displaced_caves(deal, Rng(0))
    assert deal.contents == {SPOTS_BY_LABEL["1Q6"].screen: Destination.SHOP_4}
    assert deal.dropped == [Destination.MEDIUM_SECRET, Destination.SHOP_2]
    assert applied(deal).screens[SPOTS_BY_LABEL["1Q6"].screen].destination == Destination.SHOP_4


def test_shop_4_with_no_home_redraws_the_deal() -> None:
    deal = deal_of("2Q2", "1Q1/2Q1", "1Q2/2Q3", "1Q4/2Q5", "1Q3", "1Q6", "1Q7", "1Q8", "1Q9")
    assert not edl.place_displaced_caves(deal, Rng(0))
    redrawn = [key for key in range(2000) if edl.deal_expanded_dungeon_locations(key, NO_START_ROOMS).redraws]
    assert redrawn, "no deal of 2,000 was redrawn"
    for key in redrawn[:5]:
        deal = edl.deal_expanded_dungeon_locations(key, NO_START_ROOMS)
        assert Destination.SHOP_4 in deal.contents.values() or not deal.is_chosen(SPOTS_BY_LABEL["2Q2"])


# --- finished seeds ------------------------------------------------------------------------------

@pytest.mark.parametrize(("flags", "seed"), CASES, ids=CASE_IDS)
def test_each_dungeon_door_is_its_spot_and_nothing_else_holds_a_level(flags: str, seed: int) -> None:
    deal = built(seed, flags).result.expanded_deal
    assert deal is not None
    overworld = parse_rom(finished(seed, flags)).overworld
    caves = built(seed, flags).result.overworld
    assert caves is not None
    for dungeon, spot in deal.dungeons.items():
        assert door_screen(overworld, dungeon) == spot.screen
        assert caves.entry_door(dungeon) == spot.screen
    shown = [screen.screen_num for screen in overworld.screens
             if screen.destination.is_level and screen.quest_visibility in SHOWN]
    assert sorted(shown) == sorted(spot.screen for spot in deal.dungeons.values())
    for spot in SPOTS:
        if not deal.is_chosen(spot) and spot.kind in (edl.SpotKind.HIDDEN, edl.SpotKind.RECORDER_LAKE,
                                                       edl.SpotKind.FOUNTAIN):
            assert overworld.screens[spot.screen].destination == Destination.NONE, spot.label


@pytest.mark.parametrize(("flags", "seed"), CASES, ids=CASE_IDS)
def test_the_recorder_and_the_armos_item_follow_the_deal(flags: str, seed: int) -> None:
    deal = built(seed, flags).result.expanded_deal
    assert deal is not None
    overworld = parse_rom(finished(seed, flags)).overworld
    live = {SPOTS_BY_LABEL[label].screen for label in ("1Q7", "2Q6") if label in deal.chosen}
    assert {entry for entry in overworld.recorder_secret_screens if entry != RECORDER_ENTRY_OFF} == live
    assert overworld.recorder_reveals_listed_secrets_in_first_quest == ("2Q6" in deal.chosen)
    assert recorder_screens(overworld) != MIXED_RECORDER_SCREENS and not is_second_quest_overworld(overworld)
    caves = built(seed, flags).result.overworld
    assert caves is not None
    if "2Q2" in deal.chosen:
        assert caves.armos_screen != edl.ARMOS_SPOT_SCREEN


def test_the_armos_item_avoids_2q2_while_it_holds_a_dungeon() -> None:
    """Across seeds with 2Q2 chosen, the Armos item's screen is drawn from the other four."""
    with_2q2 = [seed for seed in range(40) if "2Q2" in built(seed).result.expanded_deal.chosen]   # type: ignore[union-attr]
    assert len(with_2q2) >= 10
    assert all(built(seed).result.overworld.armos_screen != edl.ARMOS_SPOT_SCREEN   # type: ignore[union-attr]
               for seed in with_2q2)


@pytest.mark.parametrize(("flags", "seed"), CASES, ids=CASE_IDS)
def test_level_location_hints_name_the_spots_region(flags: str, seed: int) -> None:
    deal = built(seed, flags).result.expanded_deal
    assert deal is not None
    texts = [hint["text"] for hint in json.loads(seed_report(finished(seed, flags), flags, seed, ON)["json"])["hints"]]
    for text in texts:
        found = re.search(r"LEVEL-(\d) LIES", text)
        if found:
            assert REGION_PHRASES[region_of_screen(deal.dungeons[int(found.group(1))].screen)] in text, text


@pytest.mark.parametrize(("flags", "seed"), CASES, ids=CASE_IDS)
def test_the_logic_reaches_every_place_and_event(flags: str, seed: int) -> None:
    """Each spot's need (the raft at 1Q4/2Q5, the recorder at 1Q7 and 2Q6, the ladder at 2Q8, the
    bracelet at 2Q4) is in the rules, and the seed's own items reach everything."""
    logic = logic_model(built(seed, flags))
    swept = sweep(logic, identity(built(seed, flags)))
    assert swept.reaches_goal
    assert set(logic.places) == swept.places and set(logic.events) == swept.events


def test_a_door_on_a_gated_spot_needs_its_item() -> None:
    rules = extra_options(built(0).plan).logic_rules
    assert Item.RECORDER in rules.needs(SPOTS_BY_LABEL["2Q6"].screen)
    assert Item.RECORDER in rules.needs(SPOTS_BY_LABEL["1Q7"].screen)
    assert Item.RECORDER not in rules.needs(SPOTS_BY_LABEL["1Q2/2Q3"].screen)        # not the eleven-screen set
    assert Item.RAFT in rules.needs(SPOTS_BY_LABEL["1Q4/2Q5"].screen)
    assert Item.LADDER in rules.needs(SPOTS_BY_LABEL["2Q8"].screen)
    assert Item.POWER_BRACELET in rules.needs(SPOTS_BY_LABEL["2Q4"].screen)


@pytest.mark.slow
@pytest.mark.parametrize("flags", [BRACKETS, EVERYTHING_ELSE, COIN], ids=["brackets", "everything-else", "coin"])
@pytest.mark.parametrize("seed", range(6, 46))
def test_more_seeds_reach_every_place_and_event(flags: str, seed: int) -> None:
    test_each_dungeon_door_is_its_spot_and_nothing_else_holds_a_level(flags, seed)
    test_the_logic_reaches_every_place_and_event(flags, seed)


# --- "Expanded + shuffle everything else" (step 2) ------------------------------------------------

# Start rooms off the pool's screens, so the start-room ban never refuses a pair in the walk tests
START_ROOMS_OFF_THE_POOL = dict.fromkeys(range(1, 10), 127)
# Chosen spots that stand on OW-APP-A3 screens (the wooden-sword cave's partners): 1Q1, 1Q2, 1Q5, 1Q6, 1Q3
ON_SWORD_SCREENS = ("1Q1/2Q1", "1Q2/2Q3", "1Q5", "1Q6", "1Q3", "2Q4", "2Q6", "2Q7", "2Q8")


def walked(sword_partner_caves_only: bool, key: int) -> tuple[list[Entry], list[Entry]]:
    """A deal's cave list before and after the non-dungeon walk (with the spec's or ZORA's wooden-sword partners)."""
    deal = deal_of(*ON_SWORD_SCREENS)
    assert edl.place_displaced_caves(deal, Rng(0))
    overworld = applied(deal)
    before = deal_entries(overworld, enrolled_entries(overworld))
    after = copy.deepcopy(before)
    walk_destination_codes(after, START_ROOMS_OFF_THE_POOL, Rng(key), parts=CaveWalkParts(dungeon_doors=False),
                           sword_partner_caves_only=sword_partner_caves_only)
    return before, after


@pytest.mark.parametrize("key", range(30))
def test_the_walk_moves_only_the_other_caves(key: int) -> None:
    """The dungeon doors stay where the deal put them, every other code is kept (only moved), and
    no closed spot is in the list."""
    before, after = walked(True, key)
    doors = [(entry.screen, entry.code) for entry in before if entry.code in range(1, 10)]
    assert [(entry.screen, entry.code) for entry in after if entry.code in range(1, 10)] == doors and len(doors) == 9
    assert Counter(entry.code for entry in after) == Counter(entry.code for entry in before)
    closed = {SPOTS_BY_LABEL[label].screen for label in ("1Q7", "1Q8", "1Q9", "2Q9")}     # the deal's closed spots
    assert not closed & {entry.screen for entry in after}


def test_the_wood_sword_cave_never_takes_a_dungeon_door() -> None:
    """The spec's wooden-sword partner may be a dungeon door on an OW-APP-A3 screen (which would take
    a dungeon off the pool); ZORA's never is."""
    moved = [key for key in range(200)
             if [e.code for e in walked(False, key)[1] if e.code in range(1, 10)]
             != [e.code for e in walked(False, key)[0] if e.code in range(1, 10)]]
    assert moved, "the spec's partner never took a door in 200 walks"
    for key in moved[:20]:
        before, after = walked(True, key)
        assert [e for e in after if e.code in range(1, 10)] == [e for e in before if e.code in range(1, 10)]


def test_everything_else_moves_the_other_caves() -> None:
    """Across seeds under All Caves, the other caves leave their first-quest screens (the wood sword
    cave among them), while each dungeon stays on its dealt spot (the finished-seed tests)."""
    moved: Counter[int] = Counter()
    for seed in SEEDS:
        overworld = parse_rom(finished(seed, EVERYTHING_ELSE)).overworld
        moved.update(screen.screen_num for screen, kept in zip(overworld.screens, base_overworld().screens, strict=True)
                     if screen.screen_num not in edl.POOL_SCREENS and screen.destination != kept.destination)
    assert len(moved) > 20


def test_all_caves_and_the_coin_are_accepted() -> None:
    """All Caves gives "Expanded + shuffle everything else"; Dungeons Only with Shuffle Wood Sword
    Cave on is accepted with a warning, and its coin runs some seeds as All Caves."""
    assert zora_flags.validate(zora_flags.decode(ON), decode(EVERYTHING_ELSE)) == []
    assert zora_flags.validate(zora_flags.decode(ON), decode(COIN)) == []
    assert zora_flags.warnings(zora_flags.decode(ON), decode(COIN))
    assert not zora_flags.warnings(zora_flags.decode(ON), decode(BRACKETS))
    resolved = {plan(COIN, seed, ON).alternatives.cave_shuffle for seed in range(16)}
    assert resolved == {CaveShuffle.DUNGEON_DOORS_ONLY, CaveShuffle.ALL_CAVES}


# --- the flags -----------------------------------------------------------------------------------

def test_off_by_default_and_random_resolves_per_seed() -> None:
    assert plan(BRACKETS, 0).zora_resolved.expanded_dungeon_locations is ThreeState.OFF
    sides = {plan(BRACKETS, seed, RANDOM).zora_resolved.is_on(FIELD) for seed in range(16)}
    assert sides == {True, False}


@pytest.mark.parametrize(("change", "reason"), [
    ({"options": {"C01": OverworldQuest.MIXED_FIRST_QUEST_VARIANT}}, "needs Overworld Quest: 1st Quest or 2nd Quest"),
    ({"options": {"C01": OverworldQuest.MIXED_SECOND_QUEST_VARIANT}}, "needs Overworld Quest: 1st Quest or 2nd Quest"),
    ({"options": {"C01": OverworldQuest.RANDOM}}, "needs Overworld Quest: 1st Quest or 2nd Quest"),
    ({"options": {"C05": CaveShuffle.VANILLA}}, "needs Cave Shuffle: Dungeons Only"),
    ({"options": {"C05": CaveShuffle.NON_DUNGEON_CAVES_ONLY}}, "needs Cave Shuffle: Dungeons Only"),
    ({"options": {"C05": CaveShuffle.RANDOM}}, "needs Cave Shuffle: Dungeons Only"),
], ids=["mixed", "mixed-second", "random-quest", "vanilla", "non-dungeons", "random-caves"])
@pytest.mark.parametrize("zora", [ON, RANDOM], ids=["on", "random"])
def test_what_it_is_refused_with(change: dict, reason: str, zora: str) -> None:
    flags = encode(decode(BRACKETS).updated(**change))
    with pytest.raises(FlagsRefused, match=re.escape(reason)):
        plan(flags, 0, zora)
    names = {name for _message, fields in zora_flags.conflicts(zora_flags.decode(zora), decode(flags))
             for name in fields}
    assert FIELD in names


def test_offered_by_archipelago() -> None:
    """Released in 2fd34b5, held in 1e585a8 for the 2nd Quest Brackets seed 30, released again once
    acceptance E11 (64109a8) fixed it and its rescan passed (archipelago.HELD_BACK's comment)."""
    assert FIELD not in archipelago.HELD_BACK
    offered = next(spec for spec in archipelago.option_fields() if spec.id == FIELD)
    assert offered.values == tuple(int(state) for state in ThreeState)
