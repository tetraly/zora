"""Archipelago's WorldTestBase on several of ZORA's option sets (each generates a whole ZORA world and
checks every location is reachable and the goal beatable), the item names Archipelago uses for some
of ZORA's items, and the color settings' values."""
import tempfile
import unittest
from pathlib import Path
from typing import Any, ClassVar

from BaseClasses import ItemClassification
from Fill import distribute_items_restrictive

from .. import ZoraItem
from ..classes import FILLER_ITEMS, ONE_COPY_ITEMS, PROGRESSION_ITEMS, pool_classes, progression_copies, terms
from ..names import (
    BOMB_UPGRADE,
    BOOTS_UPGRADE,
    ITEM_NAME_TO_ID,
    LINE_OF,
    LOCATION_NAME_TO_ID,
    ItemNaming,
    kept_home,
    zora_names,
)
from ..options import OPTION_CLASSES, SETTING_CLASSES
from ..rules import term_holds
from ..zora.flags.zora_flags import Pacing
from ..zora.generate.acceptance_check import RING_LINE, SWORD_LINE, logic_walk_rules, rings_needed, swords_needed
from ..zora.generate.logic import (
    CANDLE,
    LEVEL9_ENTRY_EVENT,
    RING,
    SWORD,
    TRUE,
    CountTerm,
    EventTerm,
    ItemTerm,
    Line,
    LogicModel,
    implies,
    triforce_event,
)
from ..zora.generate.pipeline import extra_options
from ..zora.generate.places import CELLAR_SUFFIX, ROOM_SUFFIX, SELLER_SUFFIX, is_never_a_place
from ..zora.generate.steps.mixed_overworld_quest import SHOWN
from ..zora.model.enums import Item, RoomType
from . import ZoraTestBase

# Expanded Dungeon Locations' seeds run while the world offers it: held back again (owner, 2026-10-18)
# until an Expanded Brackets 2nd Quest seed's fix and its rescan, they come back on their own.
EXPANDED_OFFERED = "on" in OPTION_CLASSES["expanded_dungeon_locations"].options
skip_unless_expanded = unittest.skipUnless(EXPANDED_OFFERED, "Expanded Dungeon Locations is held back")
# Offense and Defense Item Pacing's seeds run once the world offers them (zora/archipelago.py HELD_BACK)
PACING_OFFERED = all("earlier" in OPTION_CLASSES[key].options for key in ("offense_pacing", "defense_pacing"))
skip_unless_pacing = unittest.skipUnless(PACING_OFFERED, "Offense and Defense Item Pacing are held back")
# Bomb Upgrades in the Item Pool's seeds run once the world offers it (held back until its logic scan; piece 8)
BOMB_UPGRADES_OFFERED = "on" in OPTION_CLASSES["bomb_upgrades_in_pool"].options
skip_unless_bomb_upgrades = unittest.skipUnless(BOMB_UPGRADES_OFFERED, "Bomb Upgrades in the Item Pool is held back")


def assert_dungeon_entrances(test: ZoraTestBase) -> None:
    """Every location in a dungeon needs what its entrance's screen needs, wherever the dungeon was
    dealt (Expanded Dungeon Locations: the raft at $45, the recorder at $42 and 2Q6, the ladder at
    2Q8, the bracelet at 2Q4), and every location name has its ID. A clause with another kind of
    term (a count or an event) may meet a need another way, so only all-item clauses are checked."""
    built = test.multiworld.worlds[test.player].built
    rules = logic_walk_rules(extra_options(built.state.plan).logic_rules)
    names = [place.name for place in built.places]
    test.assertEqual(len(names), len(set(names)))
    test.assertFalse([name for name in names if name not in LOCATION_NAME_TO_ID])
    for place in built.state.places:
        if place.level is None:
            continue
        needs = rules.needs(built.state.result.overworld.entry_door(place.level))
        for clause in built.logic.places[place.name]:
            if all(isinstance(term, ItemTerm) for term in clause):
                test.assertLessEqual(needs, {term.item for term in clause}, place.name)


def assert_triforce_spots(test: ZoraTestBase) -> None:
    """BuildResult.triforces: one spot per level 1-8, in level order, named as a location (by the
    level's shown number), never one of Archipelago's places, and holding that level's Triforce in
    the built world, as a room's own item (Floor) or in a cellar whose stairs are in the room
    (Stairway). The event's rule follows the spot (AcceptanceCheck.completes reads the world);
    WorldTestBase checks every event is reached."""
    built = test.multiworld.worlds[test.player].built
    levels = {level.level_num: level for level in built.state.world.levels}
    places = {place.name for place in built.places}
    test.assertEqual([event for event, _place in built.triforces], [triforce_event(level) for level in range(1, 9)])
    for level_num, (event, place) in enumerate(built.triforces, start=1):
        test.assertIn(event, built.logic.events)
        test.assertIn(place, LOCATION_NAME_TO_ID)
        test.assertNotIn(place, places)
        level = levels[level_num]
        words = place.split()                           # Level 3 Room 2F Stairway
        test.assertEqual(int(words[1]), level.rom_level_num, place)
        room_num = int(words[3], 16)
        if words[4] == ROOM_SUFFIX:
            test.assertEqual(level.block.room(room_num).item, Item.TRIFORCE, place)
        else:
            test.assertEqual(words[4], CELLAR_SUFFIX, place)
            test.assertIn(Item.TRIFORCE, {stair.item for stair in level.block.staircases
                                          if stair.room_type == RoomType.ITEM_STAIRCASE
                                          and stair.return_dest == room_num}, place)


PIECE_NAMES = frozenset(f"Level {level} Triforce" for level in range(1, 9))
MAP_NAMES = frozenset(f"Level {level} Map" for level in range(1, 10))
COMPASS_NAMES = frozenset(f"Level {level} Compass" for level in range(1, 10))


def assert_level_items_pooled(test: ZoraTestBase, pieces: bool, maps: bool, compasses: bool) -> None:
    """Triforce Shuffle and Map & Compass Shuffle at Anywhere (docs/design/archipelago-items.md piece 6): each
    pooled level item is in the pool once, by its level's shown number, and no generic code is; every piece is
    progression (classes.py, 2026-11-23), and ZORA places none of them; maps and compasses are useful. WorldTestBase
    checks every location is reached and the goal beaten with the items anywhere."""
    world = test.multiworld.worlds[test.player]
    names = [item.name for item in test.multiworld.itempool if item.player == test.player]
    # A level item ZORA left in a room that is never a place (Zelda's room, as level 9's map in some seeds) stays
    # there, out of the pool, as in a single-player game
    kept = {f"Level {level.rom_level_num} {room.item.name.title()}" for level in world.built.state.world.levels
            for room in level.rooms if is_never_a_place(room) and room.item in (Item.TRIFORCE, Item.MAP, Item.COMPASS)}
    for wanted, kinds in ((pieces, PIECE_NAMES), (maps, MAP_NAMES), (compasses, COMPASS_NAMES)):
        pooled = sorted(name for name in names if name in kinds)
        test.assertEqual(pooled, sorted(kinds - kept) if wanted else [])
    test.assertFalse({"Triforce", "Map", "Compass"} & set(names))
    if pieces:
        test.assertEqual(list(world.built.triforces), [])
        for name in PIECE_NAMES - kept:
            test.assertEqual(world.classification(name), ItemClassification.progression, name)
    else:
        assert_triforce_spots(test)
    for name in (MAP_NAMES - kept if maps else set()) | (COMPASS_NAMES - kept if compasses else set()):
        test.assertEqual(world.classification(name), ItemClassification.useful, name)
    assert_classes(test)


def assert_pacing(test: ZoraTestBase) -> None:
    """Offense and Defense Item Pacing: every clause of a level's locations and Triforce asks for the
    swords and rings ZORA's acceptance check asks for there (swords_needed, rings_needed: 1 or 2 of
    the Sword or Ring line), and the items those lines count are progression."""
    built = test.multiworld.worlds[test.player].built
    rules = extra_options(built.state.plan).logic_rules
    for line, pacing, needed, items in ((SWORD, rules.offense_pacing, swords_needed, SWORD_LINE),
                                        (RING, rules.defense_pacing, rings_needed, RING_LINE)):
        if pacing is Pacing.OFF:
            continue
        rules_by_level = [(place.name, place.level, built.logic.places[place.name])
                          for place in built.state.places if place.level is not None]
        # the Triforce events, with Triforce Shuffle Off or Between levels (Anywhere: their rooms are places, above)
        rules_by_level += [(triforce_event(level), level, built.logic.events[triforce_event(level)])
                           for level in range(1, 9) if triforce_event(level) in built.logic.events]
        asked = 0
        for name, level, rule in rules_by_level:
            count = needed(pacing, level)
            if count:
                asked += 1
                for clause in rule:
                    test.assertTrue(implies(clause, CountTerm(line, count)), f"{name}: {line} {count}")
        test.assertTrue(asked, f"no level asks for a {line} count")
        test.assertLessEqual({Item(code) for code in items} - {Item.WOOD_SWORD}, built.logic.progression)
    assert_classes(test)


def assert_classes(test: ZoraTestBase) -> None:
    """The item classes (classes.py, 2026-11-23): every copy of an always-progression item is progression, as is at
    least one sword, candle and ring copy; a copy that isn't is filler if it is Bombs, 5 Rupees or a Key, else
    useful. And every item, count and heart term of the seed's logic holds in the state of every progression copy
    (and the events they reach), as Archipelago counts it: a useful copy of the same name is never counted."""
    world = test.multiworld.worlds[test.player]
    naming = world.naming
    items = [item for item in test.multiworld.itempool if item.player == test.player]
    always = {naming.archipelago_name(name) for name in PROGRESSION_ITEMS}
    for item in items:
        if item.name in always:
            test.assertTrue(item.advancement, item.name)
        elif not item.advancement:
            test.assertEqual(item.classification, ItemClassification.filler if item.name in FILLER_ITEMS
                             else ItemClassification.useful, item.name)
    names = {item.name for item in items}
    for name in {naming.archipelago_name(name) for name in ONE_COPY_ITEMS} & names:
        test.assertTrue(any(item.advancement for item in items if item.name == name), name)
    state = test.multiworld.get_all_state(False)
    model = world.built.logic
    for term in set(terms(model)):
        if not isinstance(term, EventTerm):
            test.assertTrue(term_holds(term, state, test.player, model, naming), term)


class TestDefaults(ZoraTestBase):
    def test_take_any_hearts_are_caves_the_first_quest_shows(self) -> None:
        """The logic's take-any heart events are only the Take Any caves a first-quest overworld
        shows (ZORA's 2180d32: the second quest's never open)."""
        built = self.multiworld.worlds[self.player].built
        shown = {screen.screen_num for screen in built.state.world.overworld.screens
                 if screen.quest_visibility in SHOWN}
        events = built.logic.take_any_events
        self.assertTrue(events)
        for event in events:                                # "Take Any 1E Heart"
            self.assertIn(int(event.split()[2], 16), shown, event)

    def test_the_level_items_are_items_by_default(self) -> None:
        """Triforce Shuffle and Map & Compass Shuffle default to Anywhere in Archipelago (owner, 2026-11-25)."""
        assert_level_items_pooled(self, pieces=True, maps=True, compasses=True)

    def test_the_client_tables_carry_the_default_sound(self) -> None:
        """item_appears, Tune1Request $02 (owner decision, 2026-10-18)."""
        rules = self.multiworld.worlds[self.player].fill_slot_data()["client_tables"]["rules"]
        self.assertEqual(rules["arrivalSound"], 0x02)

    def test_the_classes_are_fixed(self) -> None:
        """classes.py (2026-11-23): Bombs, 5 Rupees and Key are filler; the blue potion and the other items useful;
        the listed items progression, whatever the seed's logic names."""
        world = self.multiworld.worlds[self.player]
        for name in FILLER_ITEMS:
            self.assertEqual(world.classification(name), ItemClassification.filler, name)
        for name in ("Blue Potion", "Red Potion", "Wand", "Book", "Magical Key", "Shield", "Bait", BOMB_UPGRADE,
                     "Boomerang", "Magical Boomerang", "Level 3 Map", "Level 3 Compass"):
            self.assertEqual(world.classification(name), ItemClassification.useful, name)
        for name in (*PROGRESSION_ITEMS, *ONE_COPY_ITEMS):
            self.assertEqual(world.classification(name), ItemClassification.progression, name)
        self.assertNotIn("Key", world.options.local_items.value)             # no key in this pool
        assert_classes(self)

    def test_no_item_is_renamed_without_progressive_items(self) -> None:
        names = {item.name for item in self.multiworld.itempool if item.player == self.player}
        self.assertIn("Raft", names)
        self.assertFalse(names & {"Sword Upgrade", "Candle Upgrade", "Arrow Upgrade", "Ring Upgrade",
                                  "Boomerang Upgrade", BOMB_UPGRADE})


class TestArrivalSound(ZoraTestBase):
    """The slot data's client tables carry the player's Sound when an item arrives."""
    options: ClassVar[dict[str, Any]] = {"item_arrival_sound": "none"}

    def test_the_client_tables_carry_the_chosen_sound(self) -> None:
        rules = self.multiworld.worlds[self.player].fill_slot_data()["client_tables"]["rules"]
        self.assertEqual(rules["arrivalSound"], 0)


class TestRetiredLookSetting(ZoraTestBase):
    """A YAML from 2.0.1 that still sets "Other players' items look like" (retired by piece 5 of
    docs/design/archipelago-items.md) generates: the world keeps it as a hidden option and ignores it."""
    options: ClassVar[dict[str, Any]] = {"foreign_item_look": "logo"}

    def test_the_option_is_hidden_and_offers_no_setting(self) -> None:
        self.assertNotIn("foreign_item_look", SETTING_CLASSES)
        option = self.multiworld.worlds[self.player].options.foreign_item_look
        self.assertEqual(option.visibility, 0)


class TestProgressiveItemNames(ZoraTestBase):
    """With Progressive Items on, upgrade-line items are named by their line, and the seed is still
    filled and beatable (the rules count the upgrades)."""
    options: ClassVar[dict[str, Any]] = {"progressive_items": "on", "extra_candles": "off"}

    def test_line_items_are_named_by_their_line(self) -> None:
        names = [item.name for item in self.multiworld.itempool if item.player == self.player]
        self.assertFalse(set(names) & set(LINE_OF), names)
        self.assertIn("Sword Upgrade", names)
        world = self.multiworld.worlds[self.player]
        self.assertEqual(len(names), len(world.pool))
        assert_classes(self)


class TestProgressiveCopiesTakeTheirOwnClass(ZoraTestBase):
    """Progressive Items with the shops' items in the pool: two Candle Upgrades and two Ring Upgrades, one copy of each
    progression and the other useful unless the logic counts both; both Arrow Upgrades progression."""
    options: ClassVar[dict[str, Any]] = {"progressive_items": "on", "shop_items_in_pool": "on"}

    def test_each_copy_has_its_class(self) -> None:
        items = [item for item in self.multiworld.itempool if item.player == self.player]
        copies = self.multiworld.worlds[self.player].progression_copies
        for name in ("Candle Upgrade", "Ring Upgrade"):
            classes = [item.classification for item in items if item.name == name]
            self.assertEqual(len(classes), 2, name)
            self.assertEqual(classes.count(ItemClassification.progression), max(1, copies[name]), name)
        arrows = [item for item in items if item.name == "Arrow Upgrade"]
        self.assertEqual(len(arrows), 2)
        self.assertTrue(all(item.advancement for item in arrows))
        assert_classes(self)


class TestMinorDropsFillerSpots(ZoraTestBase):
    """Shuffle Minor Dungeon Drops (B17) On: a minor place takes only filler, any world's; every other place takes
    anything but this world's own Bombs, 5 Rupees and Keys, so after the fill no place the Item Counter counts
    holds this world's filler (wolf2k's seed: level 8's counted rooms held keys and bombs)."""
    options: ClassVar[dict[str, Any]] = {"shuffle_minor_dungeon_drops": "on"}

    def test_the_filler_stays_where_the_dungeon_build_put_it(self) -> None:
        """ZORA's own B17 deal is skipped in Archipelago (2026-11-23): every Bomb, 5 Rupees and Key is a minor
        place's own item, so the pool's filler and the filler spots match one for one; the keys stay in this world,
        and the White Sword Cave never takes a key."""
        world = self.multiworld.worlds[self.player]
        built = world.built
        own = {place.name: name for place, name in zip(built.places, built.pool, strict=True)}
        self.assertEqual({name for name, item in own.items() if item in FILLER_ITEMS},
                         {place.name for place in built.places if place.minor})
        self.assertIn("Key", world.options.local_items.value)
        cave = next(place for place in built.places if place.name == "White Sword Cave")
        self.assertIn("Key", cave.forbids)
        rule = self.multiworld.get_location("White Sword Cave", self.player).item_rule
        self.assertFalse(rule(ZoraItem("Key", ItemClassification.filler, ITEM_NAME_TO_ID["Key"], self.player)))

    def test_the_item_rules(self) -> None:
        world = self.multiworld.worlds[self.player]
        minor = [place.name for place in world.places if place.minor]
        self.assertTrue(minor)

        def item(name: str, classification: ItemClassification, player: int) -> ZoraItem:
            return ZoraItem(name, classification, ITEM_NAME_TO_ID[name], player)

        other = self.player + 1
        for place in world.places:
            rule = self.multiworld.get_location(place.name, self.player).item_rule
            accepts = {(name, player): rule(item(name, classification, player))
                       for name, classification in (("Bombs", ItemClassification.filler),
                                                    ("Key", ItemClassification.filler),
                                                    ("5 Rupees", ItemClassification.filler),
                                                    ("Wand", ItemClassification.useful),
                                                    ("Raft", ItemClassification.progression))
                       for player in (self.player, other)}
            filler = {(name, player) for name in FILLER_ITEMS for player in (self.player, other)}
            if place.minor:
                self.assertEqual({key for key, accepted in accepts.items() if accepted}, filler, place.name)
            elif place.compass_spot:
                # the room a level's compass marks takes no world's filler (per-level mode, Archipelago's default)
                self.assertEqual({key for key, accepted in accepts.items() if not accepted}, filler, place.name)
            else:
                self.assertEqual({key for key, accepted in accepts.items() if not accepted},
                                 {(name, self.player) for name in FILLER_ITEMS}, place.name)

    def test_no_counted_place_holds_this_world_s_filler(self) -> None:
        world = self.multiworld.worlds[self.player]
        distribute_items_restrictive(self.multiworld)      # WorldTestBase stops before the fill
        for place in world.places:
            placed = self.multiworld.get_location(place.name, self.player).item
            assert placed is not None
            if place.minor:
                self.assertFalse(placed.advancement or placed.useful, place.name)
            else:
                self.assertFalse(placed.player == self.player and placed.name in FILLER_ITEMS, place.name)
        self.assertTrue(self.multiworld.can_beat_game(self.multiworld.state))
        assert_classes(self)


def candle_model(*terms_: CountTerm | ItemTerm, starting: int = 0) -> LogicModel:
    lines = {CANDLE: Line(frozenset({Item.BLUE_CANDLE, Item.RED_CANDLE})),
             SWORD: Line(frozenset({Item.WHITE_SWORD, Item.MAGICAL_SWORD}), starting=1)}
    return LogicModel(places={"A": frozenset({frozenset(terms_)})}, events={}, goal=TRUE, progression=frozenset(),
                      starting_hearts=3, lines=lines)


class TestProgressionCopies(unittest.TestCase):
    """classes.progression_copies: the fixed classes, raised to what the logic counts."""

    def test_one_candle_unless_the_logic_counts_two(self) -> None:
        pool = ["Red Candle", "Blue Candle"]
        for naming, name in ((ItemNaming(), "Blue Candle"), (ItemNaming(progressive=True), "Candle Upgrade")):
            one = progression_copies(pool, candle_model(CountTerm(CANDLE, 1)), naming)
            self.assertEqual(sum(one[candle] for candle in ("Blue Candle", "Red Candle", "Candle Upgrade")), 1)
            self.assertEqual(one[name], 1)
            two = progression_copies(pool, candle_model(CountTerm(CANDLE, 2)), naming)
            self.assertEqual(sum(two[candle] for candle in ("Blue Candle", "Red Candle", "Candle Upgrade")), 2)

    def test_an_item_term_on_a_line_s_item(self) -> None:
        """Without Progressive Items the red candle itself; with them, its grade (the sword line counts the
        wooden-sword cave's sword as its start: the magical sword is two Sword Upgrades)."""
        red = progression_copies(["Red Candle", "Blue Candle"], candle_model(ItemTerm(Item.RED_CANDLE)), ItemNaming())
        self.assertEqual((red["Blue Candle"], red["Red Candle"]), (1, 1))
        pool = ["White Sword", "Magical Sword", "Wood Sword"]
        swords = progression_copies(pool, candle_model(ItemTerm(Item.MAGICAL_SWORD)), ItemNaming(progressive=True))
        self.assertEqual(swords["Sword Upgrade"], 2)
        self.assertEqual(progression_copies(pool, candle_model(), ItemNaming(progressive=True))["Sword Upgrade"], 1)

    def test_never_more_copies_than_the_pool_holds(self) -> None:
        copies = progression_copies(["Bombs", "Key", "5 Rupees", "Blue Potion"], candle_model(CountTerm(CANDLE, 2)),
                                    ItemNaming())
        self.assertEqual(copies, {})

    def test_a_name_s_first_copies_are_its_progression_copies(self) -> None:
        names = ["Candle Upgrade", "Bombs", "Candle Upgrade", "Blue Potion"]
        self.assertEqual(pool_classes(names, progression_copies(["Blue Candle", "Red Candle"], candle_model(),
                                                                ItemNaming(progressive=True))),
                         [ItemClassification.progression, ItemClassification.filler, ItemClassification.useful,
                          ItemClassification.useful])


class TestMagicalSwordHeartsAbove12(ZoraTestBase):
    """A YAML asking the magical-sword cave for 13 or 14 hearts (owner rule, 2026-11-23: never more than 12 in
    Archipelago): read as 12 with a warning, never refused, and the seed generates; the option offers no more."""
    options: ClassVar[dict[str, Any]] = {"change_sword_hearts": "on", "magical_sword_hearts_min": "hearts_14",
                                         "magical_sword_hearts_max": "hearts_14",
                                         "magical_sword_hearts_highest": "at_most_14_hearts"}

    def test_read_as_12(self) -> None:
        options = self.multiworld.worlds[self.player].options
        self.assertEqual(options.magical_sword_hearts_min.current_key, "hearts_12")
        self.assertEqual(options.magical_sword_hearts_max.current_key, "hearts_12")
        self.assertEqual(options.magical_sword_hearts_highest.current_key, "at_most_12_hearts")
        for key in ("magical_sword_hearts_min", "magical_sword_hearts_max"):
            self.assertNotIn("hearts_14", OPTION_CLASSES[key].options)
        with self.assertLogs(level="WARNING") as logged:
            OPTION_CLASSES["magical_sword_hearts_max"].from_any("hearts_13")
        self.assertIn("never asks for more than 12 hearts", logged.output[0])


class TestKeptHome(unittest.TestCase):
    def test_a_pool_s_keys_stay_in_its_world(self) -> None:
        self.assertEqual(kept_home(["Raft", "Key", "Bombs", "Key"]), {"Key"})
        self.assertEqual(kept_home(["Raft", "5 Rupees"]), frozenset())


class TestItemNaming(unittest.TestCase):
    def test_upgrades_become_the_pool_s_own_codes_in_turn(self) -> None:
        naming = ItemNaming(progressive=True)
        pool = ["White Sword", "Raft", "Wood Sword", "Red Candle"]
        self.assertEqual(zora_names(["Sword Upgrade", "Candle Upgrade", "Raft", "Sword Upgrade"], pool, naming),
                         ["White Sword", "Red Candle", "Raft", "Wood Sword"])

    def test_an_upgrade_beyond_the_pool_is_its_line_s_lowest_code(self) -> None:
        naming = ItemNaming(progressive=True)
        self.assertEqual(zora_names(["Sword Upgrade", "Ring Upgrade"], ["Magical Sword"], naming),
                         ["Magical Sword", "Blue Ring"])

    def test_a_bomb_upgrade_is_its_own_item(self) -> None:
        """Bomb Upgrade (ID 106) is piece 8's code $37, never the White Sword (that naming retired 2026-11-21)."""
        for naming in (ItemNaming(), ItemNaming(progressive=True), ItemNaming(pegasus_boots=True)):
            self.assertEqual(naming.archipelago_name(BOMB_UPGRADE), BOMB_UPGRADE)
            self.assertNotEqual(naming.archipelago_name("White Sword"), BOMB_UPGRADE)
            self.assertEqual(zora_names([BOMB_UPGRADE], [BOMB_UPGRADE], naming), [BOMB_UPGRADE])
            self.assertEqual(zora_names([BOMB_UPGRADE], [], naming), [BOMB_UPGRADE])


class TestLevel4SwordEntrance(ZoraTestBase):
    options: ClassVar[dict[str, Any]] = {
        "progressive_items": "on", "extra_candles": "off", "add_l4_sword": "level_2",
        "level_9_entrance_sword": "level_4_sword"}


class TestMixedShapesDungeons(ZoraTestBase):
    options: ClassVar[dict[str, Any]] = {
        "dungeon_quest": "mixed_plus_shapes", "shuffle_dungeon_start_room": "on",
        "remove_most_open_stairs": "on", "book_to_understand_old_men": "on"}


class TestSecondQuestCosmetics(ZoraTestBase):
    options: ClassVar[dict[str, Any]] = {
        "dungeon_quest": "second_quest", "green_tunic": 0x2A, "level_word": "lair",
        "boss_sound_word": "random_word", "start_inventory": {"Raft": 1, "Bombs": 2}}


@skip_unless_expanded
class TestExpandedDungeonLocations(ZoraTestBase):
    """The nine dungeons dealt onto 9 of 15 entrances, every other cave shuffled (Cave Shuffle: All
    Caves): each dungeon's locations need its dealt entrance's items."""
    options: ClassVar[dict[str, Any]] = {"expanded_dungeon_locations": "on", "triforce_shuffle": "off"}

    def test_each_dungeon_needs_its_dealt_entrance(self) -> None:
        assert_dungeon_entrances(self)

    def test_each_triforce_is_named_where_zora_put_it(self) -> None:
        assert_triforce_spots(self)


@skip_unless_expanded
class TestExpandedBracketsSecondQuest(ZoraTestBase):
    """Expanded Brackets (Cave Shuffle: Dungeons Only) on the 2nd Quest overworld, with the shops'
    wares as locations: a shop moved off a dealt entrance keeps its locations' names."""
    options: ClassVar[dict[str, Any]] = {
        "triforce_shuffle": "off",
        "expanded_dungeon_locations": "on", "overworld_quest": "second_quest", "cave_shuffle": "dungeons_only",
        "shop_items_in_pool": "on"}

    def test_each_dungeon_needs_its_dealt_entrance(self) -> None:
        assert_dungeon_entrances(self)

    def test_each_triforce_is_named_where_zora_put_it(self) -> None:
        assert_triforce_spots(self)


class TestTriforcesInStairways(ZoraTestBase):
    """Allow Triforces in Stairways (1e1e9f6): each Triforce takes one of its own level's item spots,
    a floor or a stairway, before Archipelago's fill, with Mixed + Shapes dungeons."""
    options: ClassVar[dict[str, Any]] = {"allow_triforces_in_stairways": "on", "dungeon_quest": "mixed_plus_shapes",
                                         "triforce_shuffle": "off"}

    def test_each_triforce_is_named_where_zora_put_it(self) -> None:
        assert_triforce_spots(self)


class TestLevelItemsOff(ZoraTestBase):
    options: ClassVar[dict[str, Any]] = {"triforce_shuffle": "off", "map_compass_shuffle": "off"}

    def test_each_triforce_is_named_where_zora_put_it(self) -> None:
        assert_level_items_pooled(self, pieces=False, maps=False, compasses=False)


class TestLevelItemsBetweenLevels(ZoraTestBase):
    """Between levels: the pieces stay events at Off's spots, nothing joins the pool, and with Level 9 Entry: Specific
    Triforces level 9 asks for the events of the levels the chosen levels' pieces were drawn into."""
    options: ClassVar[dict[str, Any]] = {"triforce_shuffle": "between_levels", "map_compass_shuffle": "between_levels",
                                         "level_9_entry": "specific_triforces"}

    def test_the_pieces_stay_events(self) -> None:
        assert_level_items_pooled(self, pieces=False, maps=False, compasses=False)

    def test_level_9_asks_for_the_drawn_levels(self) -> None:
        built = self.multiworld.worlds[self.player].built
        rules = extra_options(built.state.plan).logic_rules
        gate = built.state.world.level_9_gate
        events = {term.name for clause in built.logic.events[LEVEL9_ENTRY_EVENT] for term in clause
                  if isinstance(term, EventTerm)}
        if gate.levels:
            self.assertEqual(events, {triforce_event(rules.triforce_codes.index(level) + 1) for level in gate.levels})


class TestRenamedLevelItemKeys(ZoraTestBase):
    """2.0.2's test release's keys still load: add_triforces_to_pool off is Triforce Shuffle: Off, and
    add_maps_compasses_to_pool on is Map & Compass Shuffle: Anywhere."""
    options: ClassVar[dict[str, Any]] = {"add_triforces_to_pool": "off", "add_maps_compasses_to_pool": "on"}

    def test_the_old_keys_are_read(self) -> None:
        assert_level_items_pooled(self, pieces=False, maps=True, compasses=True)


class TestTriforcesInPool(ZoraTestBase):
    options: ClassVar[dict[str, Any]] = {"triforce_shuffle": "anywhere", "map_compass_shuffle": "off"}

    def test_the_pieces_are_items(self) -> None:
        assert_level_items_pooled(self, pieces=True, maps=False, compasses=False)


class TestMapsCompassesInPool(ZoraTestBase):
    options: ClassVar[dict[str, Any]] = {"map_compass_shuffle": "anywhere", "triforce_shuffle": "off"}

    def test_the_maps_and_compasses_are_items(self) -> None:
        assert_level_items_pooled(self, pieces=False, maps=True, compasses=True)


class TestLevelItemsInPoolSpecificTriforces(ZoraTestBase):
    """Both switches, Level 9 Entry: Specific Triforces and Remove Maps: no map in the pool, and level 9
    asks for the chosen levels' pieces wherever they were filled."""
    options: ClassVar[dict[str, Any]] = {"triforce_shuffle": "anywhere", "map_compass_shuffle": "anywhere",
                                         "level_9_entry": "specific_triforces", "remove_maps": "on"}

    def test_the_pieces_and_compasses_are_items(self) -> None:
        assert_level_items_pooled(self, pieces=True, maps=False, compasses=True)


class TestCompassSpotsTakeNoFiller(ZoraTestBase):
    """Per-level mode (owner, 2026-11-25): the room or item cellar each level's compass marks (Place.compass_spot,
    the piece's original spot) takes no world's filler, so the compass always points at a real item; with Shuffle
    Minor Dungeon Drops on, this world's Bombs, 5 Rupees and Keys are in the pool."""
    options: ClassVar[dict[str, Any]] = {"triforce_shuffle": "anywhere", "shuffle_minor_dungeon_drops": "on"}

    def test_the_item_rules(self) -> None:
        world = self.multiworld.worlds[self.player]
        spots = [place for place in world.places if place.compass_spot]
        self.assertTrue(spots)
        other = self.player + 1
        for place in spots:
            rule = self.multiworld.get_location(place.name, self.player).item_rule
            for player in (self.player, other):
                for name in FILLER_ITEMS:
                    self.assertFalse(rule(ZoraItem(name, ItemClassification.filler, ITEM_NAME_TO_ID[name], player)),
                                     (place.name, name, player))
                for name, classification in (("Wand", ItemClassification.useful),
                                             ("Raft", ItemClassification.progression)):
                    self.assertTrue(rule(ZoraItem(name, classification, ITEM_NAME_TO_ID[name], player)),
                                    (place.name, name, player))

    def test_no_compass_spot_holds_filler_after_the_fill(self) -> None:
        world = self.multiworld.worlds[self.player]
        distribute_items_restrictive(self.multiworld)      # WorldTestBase stops before the fill
        for place in world.places:
            if place.compass_spot:
                placed = self.multiworld.get_location(place.name, self.player).item
                assert placed is not None
                self.assertTrue(placed.advancement or placed.useful, place.name)
        self.assertTrue(self.multiworld.can_beat_game(self.multiworld.state))


@skip_unless_bomb_upgrades
class TestBombUpgradesInPool(ZoraTestBase):
    """Bomb Upgrades in the Item Pool (docs/design/archipelago-items.md piece 8): each selling bomb upgrader's room is
    a location, "Level N Room XX Bomb Upgrade", and the pool holds a Bomb Upgrade (ID 106) for each; WorldTestBase
    checks every location is reached and the goal beaten with the items anywhere."""
    options: ClassVar[dict[str, Any]] = {"bomb_upgrades_in_pool": "on"}

    def test_each_seller_is_a_location_and_its_upgrade_an_item(self) -> None:
        world = self.multiworld.worlds[self.player]
        sellers = [place.name for place in world.places if place.name.endswith(SELLER_SUFFIX)]
        self.assertEqual(len(sellers), 2)
        for name in sellers:
            self.assertIn(name, LOCATION_NAME_TO_ID)
            self.multiworld.get_location(name, self.player)
        names = [item.name for item in self.multiworld.itempool if item.player == self.player]
        self.assertEqual(names.count(BOMB_UPGRADE), 2)
        self.assertNotEqual(world.classification(BOMB_UPGRADE), ItemClassification.filler)


class TestBetaValue(ZoraTestBase):
    """A beta value (zora/archipelago.py HELD_BACK: not through ZORA's logic scan for multiworld; offered since
    2026-11-21, with a warning): a YAML that names one generates. WorldTestBase checks every location is reached
    and the goal beaten."""
    options: ClassVar[dict[str, Any]] = {"universal_drops_v2": "on", "add_extra_bosses": "on"}

    def test_the_values_are_beta_values(self) -> None:
        for key in self.options:
            option = getattr(self.multiworld.worlds[self.player].options, key)
            self.assertIn(option.value, option.beta_values)


class TestRandomNeverDrawsABetaValue(unittest.TestCase):
    """Archipelago's own random picks among the values that passed the scan, never a beta value."""

    def test_random(self) -> None:
        for option_class in OPTION_CLASSES.values():
            if option_class.beta_values:
                drawn = {option_class.from_text("random").value for _ in range(200)}
                self.assertFalse(drawn & set(option_class.beta_values), option_class.display_name)
                # named, a beta value reads as itself
                key = next(name for name, value in option_class.options.items() if value in option_class.beta_values)
                self.assertEqual(option_class.from_text(key).value, option_class.options[key])


class TestOldYamlStillLoads(ZoraTestBase):
    """A YAML from before 2026-11-21 that names the settings off in Archipelago for good, and Universal Drops
    v2.0 (then never offered) off, generates: the first are hidden options, the last an ordinary one."""
    options: ClassVar[dict[str, Any]] = {"shuffle_wood_sword": "off", "disable_custom_music": "off",
                                         "item_shuffle_no_vanilla": "off", "detailed_spoiler_log": "off",
                                         "print_quest_info": "on", "universal_drops_v2": "off"}

    def test_the_kept_off_settings_are_hidden(self) -> None:
        for key in ("shuffle_wood_sword", "disable_custom_music", "item_shuffle_no_vanilla", "detailed_spoiler_log",
                    "print_quest_info"):
            self.assertNotIn(key, OPTION_CLASSES)
            self.assertEqual(getattr(self.multiworld.worlds[self.player].options, key).visibility, 0)


class TestNoBombUpgradesByDefault(ZoraTestBase):
    def test_no_seller_is_a_location(self) -> None:
        world = self.multiworld.worlds[self.player]
        self.assertFalse([place.name for place in world.places if place.name.endswith(SELLER_SUFFIX)])
        self.assertNotIn(BOMB_UPGRADE, {item.name for item in self.multiworld.itempool if item.player == self.player})


@skip_unless_pacing
class TestOffensePacing(ZoraTestBase):
    """Offense Item Pacing, Earlier: levels 1 to 4 ask for one sword, 5 to 9 for two (the wooden
    sword is one); a sword in a sword cave counts once its cave's hearts are met, as its location asks."""
    options: ClassVar[dict[str, Any]] = {"offense_pacing": "earlier"}

    def test_each_level_asks_for_its_swords(self) -> None:
        assert_pacing(self)


@skip_unless_pacing
class TestDefensePacing(ZoraTestBase):
    """Defense Item Pacing, Normal (Earlier's generation often runs past 30 s): levels 7 to 9 ask for
    one ring; the blue ring's shop ware counts once a door of its shop is reached."""
    options: ClassVar[dict[str, Any]] = {"defense_pacing": "normal"}

    def test_each_level_asks_for_its_rings(self) -> None:
        assert_pacing(self)


@skip_unless_pacing
class TestBothPacingsProgressive(ZoraTestBase):
    """Both pacings under Progressive Items and Shop Items in the Item Pool: the counts read Sword
    Upgrade and Ring Upgrade, and no shop ware counts for a line."""
    options: ClassVar[dict[str, Any]] = {"offense_pacing": "later", "defense_pacing": "later",
                                         "progressive_items": "on", "shop_items_in_pool": "on"}

    def test_each_level_asks_for_its_swords_and_rings(self) -> None:
        assert_pacing(self)


class TestSevenLetterLevelWord(ZoraTestBase):
    """A typed level word of 7 characters, ZORA's longest (d579ad5: DUNGEON1, no dash), reaches
    ZORA's finish and recipe; the world takes ZORA's rule, so an 8th character is refused."""
    options: ClassVar[dict[str, Any]] = {"level_word": "dungeon"}

    def test_the_word_reaches_the_patch(self) -> None:
        world = self.multiworld.worlds[self.player]
        self.assertIn("DUNGEON", world.settings_values.values())
        distribute_items_restrictive(self.multiworld)      # WorldTestBase stops before the fill
        with tempfile.TemporaryDirectory() as out:
            world.generate_output(out)
            self.assertTrue(list(Path(out).glob("*.apzora")))

    def test_an_eighth_character_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            SETTING_CLASSES["level_word"].from_any("dungeons")


class TestColorSettings(unittest.TestCase):
    def test_color_options_take_palette_numbers(self) -> None:
        """Each color setting's option values are the NES palette numbers themselves, so an
        unquoted 0x29 in a YAML (the number 41) is palette value 41, never a list position."""
        from ..options import SETTING_CLASSES
        for key in ("green_tunic", "blue_ring_tunic", "red_ring_tunic", "hearts"):
            option = SETTING_CLASSES[key]
            self.assertEqual(sorted(option.options.values())[:3], [0, 1, 2], key)
            self.assertNotIn(0x0D, option.options.values(), key)
            self.assertEqual(option.from_any(0x29).value, 0x29, key)
            self.assertEqual(option.from_any("0x2a").value, 0x2A, key)

    def test_a_removed_playable_character_reads_as_the_original_link(self) -> None:
        """A YAML naming a people set beta 11 offered (removed 2026-11-02) still loads: the original Link."""
        from ..options import SETTING_CLASSES, setting_value
        option = SETTING_CLASSES["playable_character"]
        for key in ("merchant", "old_man", "old_woman", "zelda"):
            self.assertNotIn(key, option.name_lookup.values(), key)       # not listed, so random never picks it
            self.assertEqual(setting_value(option.from_any(key)), "link", key)

    def test_the_boomerangs_line_is_the_boots_upgrade_with_pegasus_boots(self) -> None:
        naming = ItemNaming(progressive=True, pegasus_boots=True)
        for name in ("Boomerang", "Magical Boomerang"):
            self.assertEqual(naming.archipelago_name(name), BOOTS_UPGRADE)
        self.assertEqual(naming.line_of("Magical Boomerang"), (BOOTS_UPGRADE, 2))
        self.assertEqual(naming.members(BOOTS_UPGRADE), {"Boomerang", "Magical Boomerang"})
        self.assertEqual(zora_names([BOOTS_UPGRADE, BOOTS_UPGRADE], ["Magical Boomerang"], naming),
                         ["Magical Boomerang", "Boomerang"])
        self.assertEqual(ItemNaming(progressive=True).archipelago_name("Boomerang"), "Boomerang Upgrade")

    def test_without_progressive_items_the_boots_are_named_one_by_one(self) -> None:
        naming = ItemNaming(pegasus_boots=True)
        self.assertEqual(naming.archipelago_name("Boomerang"), "Pegasus Boots")
        self.assertEqual(naming.archipelago_name("Magical Boomerang"), "Magical Boots")
        self.assertIsNone(naming.line_of("Magical Boomerang"))
        self.assertEqual(zora_names(["Magical Boots", "Pegasus Boots"], ["Boomerang", "Magical Boomerang"], naming),
                         ["Magical Boomerang", "Boomerang"])
        self.assertEqual(ItemNaming().archipelago_name("Boomerang"), "Boomerang")

    def test_the_naming_reads_zora_s_give_rules(self) -> None:
        """ItemNaming.of reads GiveRules' own fields (168d20c added pegasus_boots), so a renamed
        field fails here, not silently in a seed."""
        from ..zora.rom.inventory import GiveRules
        self.assertEqual(ItemNaming.of(GiveRules(progressive_items=True, pegasus_boots=True)),
                         ItemNaming(progressive=True, pegasus_boots=True))
        self.assertEqual(ItemNaming.of(GiveRules()), ItemNaming())


class TestForeignClass(unittest.TestCase):
    """Another player's item is classed from its Archipelago classification (piece 1 of
    docs/design/archipelago-items.md): progression wins, then useful; anything else, traps
    included, is filler."""

    def test_the_classification_mapping(self) -> None:
        from BaseClasses import ItemClassification as C

        from .. import foreign_value
        from ..zora.archipelago import ItemClass
        cases = {C.progression: ItemClass.PROGRESSION, C.progression | C.useful: ItemClass.PROGRESSION,
                 C.progression_skip_balancing: ItemClass.PROGRESSION, C.useful: ItemClass.USEFUL,
                 C.useful | C.trap: ItemClass.USEFUL, C.filler: ItemClass.FILLER, C.trap: ItemClass.FILLER,
                 C.skip_balancing: ItemClass.FILLER}
        for classification, item_class in cases.items():
            self.assertEqual(foreign_value(classification).item_class, item_class, classification)


class TestDeathLinkOff(ZoraTestBase):
    """DeathLink is Archipelago's own option, off by default; slot data tells the client."""

    def test_slot_data_says_off(self) -> None:
        self.assertIs(self.multiworld.worlds[self.player].fill_slot_data()["death_link"], False)


class TestDeathLinkOn(ZoraTestBase):
    options: ClassVar[dict[str, Any]] = {"death_link": True}

    def test_slot_data_says_on_and_the_rom_settings_do_not_carry_it(self) -> None:
        from ..options import player_settings
        self.assertIs(self.multiworld.worlds[self.player].fill_slot_data()["death_link"], True)
        self.assertNotIn("death_link", player_settings(self.multiworld.worlds[self.player].options))
