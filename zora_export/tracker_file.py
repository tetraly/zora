"""The ZoraTracker save file of a seed made with a spoiler log level (rulings of 2026-11-06; the format and what
each level holds: docs/reports/tracker-file-format.md sections 2, 3 and 10.7, with the rulings recorded in 10.8).

Written from the seed document and its `spoiler` block, like the text log, so the two say the same. Every level
writes the whole skeleton the tracker requires, with the overworld (each entrance's kind, shops by their wares),
the item boxes (the major items of each level and of the six overworld item places) and each level's map. The
levels differ only in the dungeon maps (10.7): Basic has rooms, walls and passages, the entrance arrow and the
transport staircase pairs; Medium adds item cellars and the major floor items; Full adds Ganon's and Zelda's
rooms, the persons, the named layouts, door colors, monsters and the minor floor items.

The tracker skips a box or tile over its limit without a word and turns an unknown name into "unmarked", so
the writer checks the limits itself (ExportProblem) and lists what the file can't hold in its Notes.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from zora.model.item_names import PEGASUS_BOOTS_NAMES
from zora.version import player_version

from .leveled_log import FULL, LEVEL_NAMES, LEVEL_OWN_ITEMS, SCREEN_COLUMNS, level_facts, spoiler_level
from .spoiler_log import L4_SWORD_LABEL, MAJOR_ITEMS

TRACKER_VERSION = "2.2.0"          # ZoraTracker's GlobalAssemblyInfo.fs version the format was read from
# ZoraTracker's own format number (new in its build b20; ZTracker ignores it): kept with Version 2.2.0, so a later
# ZoraTracker knows the format without its version warning (owner ruling 2026-11-06; tracker-load-tests.md)
SAVE_FORMAT_VERSION = 1
# ZTracker compares Version with its own and always warns on a ZORA file, then loads it on "Attempt Load"
ZTRACKER_WARNING = ('ZTracker shows a version warning when it opens this file; click "Attempt Load" and the file '
                    "opens.")
MAP_SIZE = 8
MAP_TILES = 128
NO_MARK = (-1, -1, 0)
# A ZORA item by the document's name, as the tracker's box id (section 3.2). Ids 15 and up are ZoraTracker's:
# ZTracker drops them.
ITEM_IDS = {
    "Book": 0, "Boomerang": 1, "Bow": 2, "Power Bracelet": 3, "Ladder": 4, "Magical Boomerang": 5,
    "Magical Key": 6, "Raft": 7, "Recorder": 8, "Red Candle": 9, "Red Ring": 10, "Silver Arrow": 11, "Wand": 12,
    "White Sword": 13, "Heart Container": 14, "Blue Potion": 15, "Red Potion": 16, "Letter": 17,
    "Wood Sword": 19, "Magical Sword": 20, L4_SWORD_LABEL: 21, "Blue Ring": 22, "Wooden Arrow": 23,
    "Blue Candle": 24, "Shield": 25, "Bait": 26, "Key": 27, "Triforce": 29,
}
ZTRACKER_LAST_ID = 14
HEART_CONTAINER, TRIFORCE = 14, 29
# How often the tracker takes one id across all boxes; every other id once (section 2.3)
ID_LIMITS = {HEART_CONTAINER: 9, TRIFORCE: 9}
# Boxes per level with numbers shown: level 1 (level 4 with second-quest dungeons) and level 8 hold three
SHARED_THIRD_BOX = {False: 1, True: 4}
THREE_BOX_LEVELS = (8,)
TWO_BOXES, THREE_BOXES = 2, 3
LEVEL_9 = 9
# Overworld tiles (section 3.1): the marker of each entrance kind
LEVEL_MARKERS = range(9)
ANY_ROAD_MARKERS = (9, 10, 11, 12)
CAVE_MARKERS = {
    "Magical Sword Cave": 13, "White Sword Cave": 14, "Wood Sword Cave": 15, "Large Secret": 25,
    "Medium Secret": 26, "Small Secret": 27, "Door Repair": 28, "Money Making Game": 29, "Letter Cave": 30,
    "Hint Shop 1": 32, "Hint Shop 2": 32, "Take Any": 33, "Potion Shop": 34,
}
# A shop is marked by its first ware of these eight kinds (marker 16 + kind - 1), the next two in `extra`
SHOP_WARE_KINDS = {"Wooden Arrow": 1, "Bombs": 2, "Book": 3, "Blue Candle": 4, "Blue Ring": 5, "Bait": 6, "Key": 7,
                   "Shield": 8}
FIRST_SHOP_MARKER = 16
WARE_BASE = 9
# Tile limits (ZoraTracker's overworldTiles): first quest's, then second quest's where they differ
TILE_LIMITS = {13: (2, 2), 14: (2, 2), 15: (2, 2), 25: (3, 1), 26: (7, 7), 27: (4, 6), 28: (9, 10), 29: (5, 6),
               33: (4, 4), 34: (7, 9), 32: (99, 99)}
OVERWORLD_QUESTS = {"1st Quest": 0, "2nd Quest": 1, "Mixed Quest - 1st": 2, "Mixed Quest - 2nd": 3}
SECOND_QUEST_MAP = 1
DUNGEON_SUMMARY_TAB = 9

# Dungeon maps (10.7)
OFF_THE_MAP = "RoomType_OffTheMap"
ENTRANCE_TYPES = {"north": "RoomType_StartEnterFromN", "south": "RoomType_StartEnterFromS",
                  "east": "RoomType_StartEnterFromE", "west": "RoomType_StartEnterFromW"}
MAX_TRANSPORT_PAIRS = 8
NAMED_LAYOUTS = {0x16: "Chevy", 0x19: "DoubleMoat", 0x18: "TopMoat", 0x13: "RightMoat", 0x14: "CircleMoat",
                 0x12: "Tee", 0x0B: "LavaMoat", 0x0E: "VChute", 0x0F: "HChute", 0x20: "Turnstile"}
ELDERS = frozenset({"ELDER", "ELDER_2", "ELDER_3", "ELDER_4", "ELDER_5", "ELDER_6"})
PERSON_TYPES = {"MUGGER": "LifeOrMoney", "HUNGRY_GORIYA": "HungryGoriyaMeatBlock"}
MONSTERS = {
    "AQUAMENTUS": "Aquamentus", "SINGLE_DODONGO": "Dodongo", "TRIPLE_DODONGO": "Dodongo", "BLUE_GOHMA": "Bow",
    "RED_GOHMA": "Bow", "MANHANDLA": "Manhandla", "GLEEOK_1": "Gleeok", "GLEEOK_2": "Gleeok", "GLEEOK_3": "Gleeok",
    "GLEEOK_4": "Gleeok", "SINGLE_DIGDOGGER": "Digdogger", "TRIPLE_DIGDOGGER": "Digdogger", "MOLDORM": "Moldorm",
    "PATRA_1": "Patra", "PATRA_2": "Patra", "BLUE_LANMOLA": "BlueLanmola", "RUPEE_BOSS": "RupeeBoss",
    "BLUE_BUBBLE": "BlueBubble", "RED_BUBBLE": "RedBubble", "THREE_PAIRS_OF_TRAPS": "Traps", "CORNER_TRAPS": "Traps",
    "VIRE": "Vire", "ZOL": "Zol", "POLS_VOICE": "PolsVoice", "RED_TEKTITE": "RedTektite", "RED_GORIYA": "RedGoriya",
    "ROPE": "Rope", "STALFOS": "Stalfos", "WALLMASTER": "Wallmaster", "LIKE_LIKE": "Likelike", "GIBDO": "Gibdo",
    "RED_LYNEL": "RedLynel", "BLUE_MOBLIN": "BlueMoblin", "BLUE_WIZZROBE": "BlueWizzrobe",
    "BLUE_DARKNUT": "BlueDarknut", "GEL_1": "Gel", "GEL_2": "Gel", "BLUE_KEESE": "Keese", "RED_KEESE": "Keese",
    "DARK_KEESE": "Keese",
}
MAJOR_DROPS = {"Heart Container": "Heart", "Triforce": "Triforce"}
MINOR_DROPS = {"Key": "Key", "Bombs": "BombPack", "5 Rupees": "FiveRupee", "Map": "Map", "Compass": "Compass"}
WALL, PASSAGE, LOCKED, SHUTTER = 1, 2, 3, 4
SIDES = ("north", "east", "south", "west")
MEDIUM = 2


class ExportProblem(AssertionError):
    """A seed the tracker file can't describe as the format's rules ask (10.7): more than eight transport pairs
    in a level, a room outside the 8 by 8 map, or an entrance room that is also a stairway."""


def tracker_file_name(document: dict[str, Any]) -> str:
    return f"zora-{document['producer']['version']}-seed-{document['seed']['number']}-tracker.json"


def setting(document: dict[str, Any], field_id: str) -> str:
    """A Z1R setting as this seed resolved it (after any rule that changed it)."""
    entry = next(entry for entry in document["settings"] if entry.get("id") == field_id)
    return str(entry.get("final", entry["resolved"]))


def box(item_id: int = -1) -> dict[str, int]:
    return {"CellCurrent": item_id, "PlayerHas": 0}


class Writer:
    """One document's tracker file, with what it couldn't hold."""

    def __init__(self, document: dict[str, Any]) -> None:
        self.document = document
        self.level = spoiler_level(document)
        self.facts = level_facts(document)
        self.lost: list[str] = []
        self.used: Counter[int] = Counter()

    def item_id(self, name: str | None, place: str) -> int:
        """NAME's box id, counted against the tracker's limits; -1 (and a note) when the tracker has no such
        item or has used it up."""
        if not name:
            return -1
        item_id = ITEM_IDS.get(name)
        if item_id is None:
            self.lost.append(f"{place}: {name} (no tracker item)")
            return -1
        if self.used[item_id] >= ID_LIMITS.get(item_id, 1):
            self.lost.append(f"{place}: {name} (over the tracker's limit)")
            return -1
        self.used[item_id] += 1
        return item_id

    # --- the overworld ---------------------------------------------------------------------------------

    def overworld(self) -> dict[str, Any]:
        quest = OVERWORLD_QUESTS.get(setting(self.document, "C01"), 0)
        limit_index = int(quest == SECOND_QUEST_MAP)
        tiles = [NO_MARK] * MAP_TILES
        roads = iter(ANY_ROAD_MARKERS)
        counts: Counter[int] = Counter()
        caves = {cave["name"]: cave for cave in self.document["caves"]}
        for screen in sorted(self.document["overworld"]["screens"], key=lambda screen: screen["number"]):
            cave = screen["cave"]
            marker, extra = self.tile(cave, caves, roads)
            if marker is None:
                continue
            if counts[marker] >= TILE_LIMITS.get(marker, (MAP_TILES, MAP_TILES))[limit_index]:
                self.lost.append(f"screen ${screen['number']:02X}: {cave['name']} (over the tracker's tile limit)")
                continue
            counts[marker] += 1
            tiles[screen["number"]] = (marker, extra, 0)
        start_row, start_column = divmod(self.document["spoiler"]["startScreen"], SCREEN_COLUMNS)
        return {"Quest": quest, "MirrorOverworld": False, "StartIconX": start_column, "StartIconY": start_row,
                "CustomWaypointX": -1, "CustomWaypointY": -1, "Map": [value for tile in tiles for value in tile]}

    def tile(self, cave: dict[str, Any], caves: dict[str, dict[str, Any]], roads: Any) -> tuple[int | None, int]:
        name = cave["name"]
        if "shownName" in cave:
            return LEVEL_MARKERS[int(cave["shownName"].removeprefix("Level ")) - 1], 0
        if name == "Any Road":
            marker = next(roads, None)
            if marker is None:
                self.lost.append("a fifth Any Road (the tracker numbers four)")
            return marker, 0
        if name.startswith("Shop "):
            kinds = [SHOP_WARE_KINDS[ware["item"]] for ware in caves[name]["wares"] if ware["item"] in SHOP_WARE_KINDS]
            if not kinds:
                self.lost.append(f"{name}: no ware of the tracker's eight shop kinds")
                return None, 0
            rest = [*kinds[1:3], 0, 0]
            return FIRST_SHOP_MARKER + kinds[0] - 1, rest[0] + WARE_BASE * rest[1]
        if name in CAVE_MARKERS:
            return CAVE_MARKERS[name], 0
        return None, 0           # the Lost Hills and Dead Woods hints: no tracker tile

    # --- the items -----------------------------------------------------------------------------------

    def cave_item(self, caves: dict[str, dict[str, Any]], name: str) -> dict[str, int]:
        """An overworld item place's box: the cave's own item (its last ware; an extra candle comes first)."""
        wares = caves.get(name, {}).get("wares", [])
        return box(self.item_id(wares[-1]["item"], name) if wares else -1)

    def level_items(self, level: dict[str, Any]) -> list[str]:
        """The major items a level's boxes hold, in room order (its triforce piece, and Ganon's Triforce of
        Power, are the dungeon's own)."""
        l4 = self.document.get("zoraExtras", {}).get("l4Sword")
        items = []
        for room in sorted(level["rooms"], key=lambda room: (room["row"], room["column"])):
            if l4 and (level["number"], room["number"]) == (l4["level"], l4["room"]):
                items.append(L4_SWORD_LABEL)
            elif room["item"] and room["item"]["name"] in MAJOR_ITEMS - LEVEL_OWN_ITEMS:
                items.append(room["item"]["name"])
            stair = room["staircase"]
            if stair and stair["kind"] == "item" and stair["item"] in MAJOR_ITEMS:
                items.append(stair["item"])
        return items

    def dungeons(self, second_quest: bool, hidden: bool) -> list[dict[str, Any]]:
        dungeons = []
        for level in sorted(self.document["levels"], key=lambda level: level["shownNumber"]):
            shown = level["shownNumber"]
            three = (shown in THREE_BOX_LEVELS or shown == SHARED_THIRD_BOX[second_quest]
                     or (hidden and shown != LEVEL_9))
            count = THREE_BOXES if three else TWO_BOXES
            items = self.level_items(level)
            place = f"Level {shown}"
            for extra in items[count:]:
                self.lost.append(f"{place}: {extra} (the tracker has {count} boxes for the level)")
            boxes = [box(self.item_id(name, place)) for name in items[:count]]
            boxes += [box() for _ in range(count - len(boxes))]
            label = "?" if hidden or shown == LEVEL_9 else str(shown)
            dungeons.append({"Triforce": False, "Color": 0, "LabelChar": label, "PlayerHasMap": False,
                             "Boxes": boxes, "ExtraBox": box()})
        return dungeons

    def items(self) -> dict[str, Any]:
        second_quest = all(entry["quest"] == 2 for entry in self.facts.values())
        hidden = setting(self.document, "B24") == "On"
        caves = {cave["name"]: cave for cave in self.document["caves"]}
        overworld = self.document["overworld"]
        return {
            "HiddenDungeonNumbers": hidden, "SecondQuestDungeons": second_quest,
            "WhiteSwordBox": self.cave_item(caves, "White Sword Cave"),
            "LadderBox": box(self.item_id(overworld["coast"], "Coast")),
            "ArmosBox": box(self.item_id(overworld["armos"], "Armos statue")),
            "MagicalSwordBox": self.cave_item(caves, "Magical Sword Cave"),
            "LetterBox": self.cave_item(caves, "Letter Cave"),
            "WoodSwordBox": self.cave_item(caves, "Wood Sword Cave"),
            "ShuffledWoodSwordTiles": "", "HintShopColors": "", "CustomLevelName": "",
            "Level2StairBoxEnabled": False, "Level2StairBox": box(), "Level9FloorBoxEnabled": False,
            "Dungeons": self.dungeons(second_quest, hidden),
        }

    # --- the dungeon maps (10.7) ---------------------------------------------------------------------

    def room_type(self, room: dict[str, Any], facts: dict[str, Any], entrance: dict[str, Any]) -> str:
        stair = room["staircase"]
        if room["number"] == entrance["entranceRoom"]:
            if stair is not None:
                raise ExportProblem(f"level {entrance['number']}: the entrance room ${room['number']:02X} "
                                    "has a stairway")
            return ENTRANCE_TYPES[entrance["entranceSide"]]
        if stair and stair["kind"] == "transport":
            if stair["number"] > MAX_TRANSPORT_PAIRS:
                raise ExportProblem(f"level {entrance['number']}: more than {MAX_TRANSPORT_PAIRS} transport pairs")
            return f"RoomType_Transport{stair['number']}"
        if stair and stair["kind"] == "item" and self.level >= MEDIUM:
            return "RoomType_ItemBasement"
        if self.level >= FULL:
            monster = facts["monster"]
            if monster == "THE_BEAST":
                return "RoomType_Gannon"
            if monster == "THE_KIDNAPPED":
                return "RoomType_Zelda"
            if monster == "BOMB_UPGRADER":
                return "RoomType_OldManHint" if facts["talksOnly"] else "RoomType_BombUpgrade"
            if monster in ELDERS:
                return "RoomType_OldManHint"
            if monster in PERSON_TYPES:
                return f"RoomType_{PERSON_TYPES[monster]}"
            if facts["layout"] in NAMED_LAYOUTS:
                return f"RoomType_{NAMED_LAYOUTS[facts['layout']]}"
        return "RoomType_NonDescript"

    def floor_drop(self, level: dict[str, Any], room: dict[str, Any]) -> str:
        l4 = self.document.get("zoraExtras", {}).get("l4Sword")
        if self.level >= MEDIUM and l4 and (level["number"], room["number"]) == (l4["level"], l4["room"]):
            return "FloorDropDetail_OtherKeyItem"
        item = room["item"]
        if self.level < MEDIUM or item is None or item.get("appears") == "never":
            return "FloorDropDetail_Unmarked"
        name = item["name"]
        if name in MAJOR_DROPS:
            return f"FloorDropDetail_{MAJOR_DROPS[name]}"
        if name in MAJOR_ITEMS:
            return "FloorDropDetail_OtherKeyItem"
        if self.level >= FULL and name in MINOR_DROPS:
            return f"FloorDropDetail_{MINOR_DROPS[name]}"
        return "FloorDropDetail_Unmarked"

    def edge(self, first: dict[str, Any] | None, second: dict[str, Any] | None, side: str, back: str,
             adjacent: bool) -> int:
        """10.7 rule 3: an edge touching no room is a wall; between two rooms a passage if either side lets
        a player through, and at Full a shutter before a locked door before an open passage."""
        if first is None or second is None or not adjacent:
            return WALL
        doors = (first["doors"][side], second["doors"][back])
        if all(door == "solid" for door in doors):
            return WALL
        if self.level >= FULL:
            if "shutter" in doors:
                return SHUTTER
            if "locked" in doors:
                return LOCKED
        return PASSAGE

    def dungeon_map(self, level: dict[str, Any]) -> dict[str, Any]:
        entrance = self.facts[level["number"]]
        room_facts = {room["number"]: room for room in entrance["rooms"]}
        grid: dict[tuple[int, int], dict[str, Any]] = {}
        for room in level["rooms"]:
            column, row = room["column"] - 1, room["row"] - 1
            if not (0 <= column < MAP_SIZE and 0 <= row < MAP_SIZE):
                raise ExportProblem(f"level {level['shownNumber']}: room ${room['number']:02X} is off the 8 by 8 map")
            grid[column, row] = room
        states: list[list[dict[str, Any]]] = []
        for row in range(MAP_SIZE):
            states.append([])
            for column in range(MAP_SIZE):
                room = grid.get((column, row))
                monster = "MonsterDetail_Unmarked"
                if room is None:
                    room_type, drop = OFF_THE_MAP, "FloorDropDetail_Unmarked"
                else:
                    facts = room_facts[room["number"]]
                    room_type = self.room_type(room, facts, entrance)
                    drop = self.floor_drop(level, room)
                    if self.level >= FULL and facts["monster"] in MONSTERS:
                        monster = f"MonsterDetail_{MONSTERS[facts['monster']]}"
                states[row].append({"IsCompleted": False, "RoomType": room_type, "MonsterDetail": monster,
                                    "FloorDropDetail": drop, "FloorDropShouldAppearBright": True})

        def across(column: int, row: int) -> int:
            first, second = grid.get((column, row)), grid.get((column + 1, row))
            adjacent = bool(first and second and second["number"] == first["number"] + 1)
            return self.edge(first, second, "east", "west", adjacent)

        def down(column: int, row: int) -> int:
            first, second = grid.get((column, row)), grid.get((column, row + 1))
            adjacent = bool(first and second and second["number"] == first["number"] + SCREEN_COLUMNS)
            return self.edge(first, second, "south", "north", adjacent)

        return {
            "HorizontalDoors": [[across(column, row) for column in range(MAP_SIZE - 1)] for row in range(MAP_SIZE)],
            "VerticalDoors": [[down(column, row) for column in range(MAP_SIZE)] for row in range(MAP_SIZE - 1)],
            "RoomIsCircled": [[False] * MAP_SIZE for _ in range(MAP_SIZE)],
            "RoomStates": states,
            "VanillaMapOverlay": 0,
        }

    # --- the file ------------------------------------------------------------------------------------

    def write(self) -> dict[str, Any]:
        document = self.document
        overworld = self.overworld()
        items = self.items()
        maps = [self.dungeon_map(level)
                for level in sorted(document["levels"], key=lambda level: level["shownNumber"])]
        version = player_version(document["producer"]["version"])
        notes = [f"ZORA {version}, seed {document['seed']['number']}, spoiler log {LEVEL_NAMES[self.level]}."]
        if self.lost:
            notes.append("Not in this file: " + "; ".join(self.lost) + ".")
        no_blocker = {"Kind": "Blocker_Nothing", "AppliesTo": [False] * 6}
        return {
            "Version": TRACKER_VERSION,
            "SaveFormatVersion": SAVE_FORMAT_VERSION,
            "TimeInSeconds": 0,
            "Overworld": overworld,
            "Items": items,
            "PlayerProgressAndTakeAnyHearts": {
                "TakeAnyHearts": [0, 0, 0, 0], **dict.fromkeys((
                    "PlayerHasBoomBook", "PlayerHasWoodSword", "PlayerHasWoodArrow", "PlayerHasBlueRing",
                    "PlayerHasBlueCandle", "PlayerHasMagicalSword", "PlayerHasDefeatedGanon",
                    "PlayerHasRescuedZelda", "PlayerHasBombs"), False)},
            "StartingItemsAndExtras": {
                "HDNStartingTriforcePieces": [False] * 8, **dict.fromkeys((
                    "PlayerHasWhiteSword", "PlayerHasMagicalSword", "PlayerHasSilverArrow", "PlayerHasBow",
                    "PlayerHasWand", "PlayerHasRedCandle", "PlayerHasBoomerang", "PlayerHasMagicBoomerang",
                    "PlayerHasRedRing", "PlayerHasPowerBracelet", "PlayerHasLadder", "PlayerHasRaft",
                    "PlayerHasRecorder", "PlayerHasAnyKey", "PlayerHasBook", "PlayerHasMeat", "PlayerHasLetter"),
                    False),
                "MaxHeartsDifferential": 0},
            "Blockers": [[dict(no_blocker) for _ in range(3)] for _ in range(8)],
            "Hints": {"LocationHints": [0] * 11, **dict.fromkeys((
                "NoFeatOfStrengthHint", "SailNotHint", "SailToHint", "PlayMelodyHint", "StepOverWaterHint",
                "FireArrowsHint"), False)},
            "Notes": " ".join(notes),
            "CurrentRecorderDestinationIndex": 0,
            "RecorderToNewDungeons": False,
            "RecorderToUnbeatenDungeons": False,
            "IsBoomstickSeed": True,           # the book/shield box means the Book: ZORA places the Book
            "IsAtlasSeed": setting(document, "B49") == "On",
            "IsWSMSReplacedByBUSeed": False,
            "DungeonTabSelected": DUNGEON_SUMMARY_TAB,
            "DungeonMaps": maps,
            "DrawingLayerIcons": [],
            "AlternativeOverworldMapFilename": "",
            "ShouldInitiallyHideOverworldMap": False,
            "Seed": document["seed"]["number"],
            "Flags": document["seed"]["flags"],
            "OverworldSpotsRemainingOverTime": [],
            "Timeline": [],
        }


def tracker_file(document: dict[str, Any]) -> dict[str, Any]:
    """The ZoraTracker save of a seed made with a log level: the document must carry the `spoiler` block."""
    return Writer(document).write()


# The overworld boxes as the note names them: each place's words after "the items"
OVERWORLD_BOXES = {"WoodSwordBox": "Wood Sword", "WhiteSwordBox": "White Sword", "MagicalSwordBox": "Magical Sword",
                   "LetterBox": "Letter", "LadderBox": "at the coast", "ArmosBox": "under the Armos statue",
                   "Level2StairBox": "down level 2's stairway"}
CAVE_BOXES = ("WoodSwordBox", "WhiteSwordBox", "MagicalSwordBox", "LetterBox")


def listed(words: list[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def ztracker_misses(tracker: dict[str, Any]) -> tuple[int, list[str]]:
    """The boxes holding an item numbered 15 or up, which ZTracker drops: how many, and where, grouped as the note
    says them ("in the Wood Sword and Magical Sword caves", "at the coast", "in levels 3 and 9")."""
    items = tracker["Items"]
    def dropped(entry: dict[str, int]) -> bool:
        return bool(entry["CellCurrent"] > ZTRACKER_LAST_ID)
    caves = [OVERWORLD_BOXES[name] for name in CAVE_BOXES if dropped(items[name])]
    places = [f"in the {listed(caves)} cave{'s' if len(caves) > 1 else ''}"] if caves else []
    places += [words for name, words in OVERWORLD_BOXES.items() if name not in CAVE_BOXES and dropped(items[name])]
    levels = [str(number) for number, dungeon in enumerate(items["Dungeons"], 1)
              if any(dropped(entry) for entry in (*dungeon["Boxes"], dungeon["ExtraBox"]))]
    if levels:
        places.append(f"in level{'s' if len(levels) > 1 else ''} {listed(levels)}")
    count = sum(dropped(items[name]) for name in OVERWORLD_BOXES)
    count += sum(dropped(entry) for dungeon in items["Dungeons"] for entry in (*dungeon["Boxes"], dungeon["ExtraBox"]))
    return count, places


def ztracker_note(tracker: dict[str, Any]) -> str:
    """What the page says after the file is saved about ZTracker (owner rulings, 2026-11-06): what it will miss
    for this seed, when it misses anything, and always its version warning and how to get past it."""
    count, places = ztracker_misses(tracker)
    if not count:
        return ZTRACKER_WARNING
    return (f"ZTracker won't show the item{'s' if count > 1 else ''} {listed(places)}; open this file in "
            f"ZoraTracker to see everything. {ZTRACKER_WARNING}")


# Pegasus Boots' names, kept out of ITEM_IDS on purpose: the tracker has no boots
assert not set(PEGASUS_BOOTS_NAMES.values()) & set(ITEM_IDS)
