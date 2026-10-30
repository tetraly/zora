"""Archipelago's WorldTestBase on several of ZORA's option sets (each generates a whole ZORA world and
checks every location is reachable and the goal beatable), the item names Archipelago uses for some
of ZORA's items, and the color settings' values."""
import tempfile
import unittest
from pathlib import Path
from typing import Any, ClassVar

from Fill import distribute_items_restrictive

from . import ZoraTestBase
from ..names import BOMB_UPGRADE, BOOTS_UPGRADE, LINE_OF, LOCATION_NAME_TO_ID, ItemNaming, zora_names
from ..options import OPTION_CLASSES, SETTING_CLASSES
from ..zora.flags.zora_flags import Pacing
from ..zora.generate.acceptance_check import RING_LINE, SWORD_LINE, logic_walk_rules, rings_needed, swords_needed
from ..zora.generate.logic import RING, SWORD, CountTerm, ItemTerm, implies, triforce_event
from ..zora.generate.pipeline import extra_options
from ..zora.generate.places import CELLAR_SUFFIX, ROOM_SUFFIX
from ..zora.generate.steps.mixed_overworld_quest import SHOWN
from ..zora.model.enums import Item, RoomType

# Expanded Dungeon Locations' seeds run while the world offers it: held back again (owner, 2026-10-18)
# until an Expanded Brackets 2nd Quest seed's fix and its rescan, they come back on their own.
EXPANDED_OFFERED = "on" in OPTION_CLASSES["expanded_dungeon_locations"].options
skip_unless_expanded = unittest.skipUnless(EXPANDED_OFFERED, "Expanded Dungeon Locations is held back")
# Offense and Defense Item Pacing's seeds run once the world offers them (zora/archipelago.py HELD_BACK)
PACING_OFFERED = all("earlier" in OPTION_CLASSES[key].options for key in ("offense_pacing", "defense_pacing"))
skip_unless_pacing = unittest.skipUnless(PACING_OFFERED, "Offense and Defense Item Pacing are held back")


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
        rules_by_level += [(triforce_event(level), level, built.logic.events[triforce_event(level)])
                           for level in range(1, 9)]
        asked = 0
        for name, level, rule in rules_by_level:
            count = needed(pacing, level)
            if count:
                asked += 1
                for clause in rule:
                    test.assertTrue(implies(clause, CountTerm(line, count)), f"{name}: {line} {count}")
        test.assertTrue(asked, f"no level asks for a {line} count")
        test.assertLessEqual({Item(code) for code in items} - {Item.WOOD_SWORD}, built.logic.progression)


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

    def test_each_triforce_is_named_where_zora_put_it(self) -> None:
        assert_triforce_spots(self)

    def test_the_client_tables_carry_the_default_sound(self) -> None:
        """item_appears, Tune1Request $02 (owner decision, 2026-10-18)."""
        rules = self.multiworld.worlds[self.player].fill_slot_data()["client_tables"]["rules"]
        self.assertEqual(rules["arrivalSound"], 0x02)

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

    def test_the_white_sword_is_a_bomb_upgrade_when_it_stands_for_one(self) -> None:
        for progressive in (False, True):
            naming = ItemNaming(progressive=progressive, bomb_upgrade=True)
            self.assertEqual(naming.archipelago_name("White Sword"), BOMB_UPGRADE)
            self.assertIsNone(naming.line_of("White Sword"))
            self.assertEqual(zora_names([BOMB_UPGRADE], ["White Sword"], naming), ["White Sword"])
        self.assertEqual(ItemNaming().archipelago_name("White Sword"), "White Sword")


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
    options: ClassVar[dict[str, Any]] = {"expanded_dungeon_locations": "on"}

    def test_each_dungeon_needs_its_dealt_entrance(self) -> None:
        assert_dungeon_entrances(self)

    def test_each_triforce_is_named_where_zora_put_it(self) -> None:
        assert_triforce_spots(self)


@skip_unless_expanded
class TestExpandedBracketsSecondQuest(ZoraTestBase):
    """Expanded Brackets (Cave Shuffle: Dungeons Only) on the 2nd Quest overworld, with the shops'
    wares as locations: a shop moved off a dealt entrance keeps its locations' names."""
    options: ClassVar[dict[str, Any]] = {
        "expanded_dungeon_locations": "on", "overworld_quest": "second_quest", "cave_shuffle": "dungeons_only",
        "shop_items_in_pool": "on"}

    def test_each_dungeon_needs_its_dealt_entrance(self) -> None:
        assert_dungeon_entrances(self)

    def test_each_triforce_is_named_where_zora_put_it(self) -> None:
        assert_triforce_spots(self)


class TestTriforcesInStairways(ZoraTestBase):
    """Allow Triforces in Stairways (1e1e9f6): each Triforce takes one of its own level's item spots,
    a floor or a stairway, before Archipelago's fill, with Mixed + Shapes dungeons."""
    options: ClassVar[dict[str, Any]] = {"allow_triforces_in_stairways": "on", "dungeon_quest": "mixed_plus_shapes"}

    def test_each_triforce_is_named_where_zora_put_it(self) -> None:
        assert_triforce_spots(self)


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
