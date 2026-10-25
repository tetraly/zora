"""The seed document: a finished seed in the visualizer's seed format, version 1.1
(docs/seed-format/seed-format.schema.json, copied from the z1r-visualizer repo; its
docs/seed-format.md explains every field).

It describes the FINISHED ROM: the dungeons, caves, shops and texts come from the data
layer's parse of the ROM's bytes (parse_rom with the seed's GameConfig), never from the
generator's working state. The plan adds only what the ROM cannot say: the seed number, the
flag strings, each setting as chosen and as resolved (FL-DEP-04's separate "?" stream, so
reading it again draws nothing from the generation's stream), and who says each text.

Never for an encoded seed (the format's first rule): a plan with "Encode level data" on is
refused with EncodedSeedRefused.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, fields
from enum import IntEnum
from itertools import pairwise
from typing import Any

from zora.flags import form as flag_form
from zora.flags import zora_flags
from zora.flags.codec import decode
from zora.flags.dependencies import (
    meet_cave_prerequisite,
    meet_monster_prerequisite,
    meet_room_prerequisite,
    with_the_toll_beside_merchants,
    without_both_boss_health_rules,
)
from zora.flags.fields import OptionField, Settings, ThreeState, ToggleField
from zora.flags.form import ALL_FIELDS
from zora.flags.zora_form import FIELDS as ZORA_FIELDS
from zora.generate.late_gate.gatekeeper import GATEKEEPER_LEVELS
from zora.generate.pipeline import (
    GenerationPlan,
    cave_prerequisite_rng,
    monster_prerequisite_rng,
    overworld_gates,
    resolve_question_marks,
    room_prerequisite_rng,
)
from zora.generate.steps.add_l4_sword import L4_SWORD_ITEM
from zora.generate.steps.mixed_overworld_quest import second_quest_leftovers
from zora.generate.steps.overworld_gates import DEAD_WOODS_HINT, LOST_HILLS_HINT
from zora.generate.steps.randomize_mazes import DEAD_WOODS, LOST_HILLS
from zora.model import room_grid
from zora.model.enums import (
    Destination,
    Enemy,
    Item,
    QuestVisibility,
    RoomAction,
    RoomType,
    UnderworldPersonInit,
    WallType,
)
from zora.model.game_world import GameWorld
from zora.model.item_names import ITEM_NAMES, item_names
from zora.model.level_9_gate import GateKind, Level9Gate
from zora.model.levels import LEVEL_9, Level
from zora.model.overworld import DoorRepairCave, HintShop, ItemCave, OverworldItem, Shop, ShopItem, TakeAnyCave
from zora.model.rooms import Room
from zora.rom import item_sprites
from zora.rom.code_patches import (
    SHOPS_BY_NUMBER,
    one_time_wares,
    seed_code_values,
)
from zora.rom.parse.rom_file import parse_rom
from zora.rom.revision import finished_in_prg0_layout
from zora.rom.uphill_battle import QUESTION_MARK_TILE
from zora.version import PLAYER_NAME, ZORA_VERSION
from zora_export.nes_palette import NES_PALETTE

FORMAT = "z1r-seed"
FORMAT_VERSION = "1.1"
PRODUCER = PLAYER_NAME


class EncodedSeedRefused(ValueError):
    """The seed format's first rule: no seed document for a seed with level encoding on."""

    def __init__(self) -> None:
        super().__init__('no seed document or spoiler for a seed made with "Encode level data" on')


# --- items ---------------------------------------------------------------------------------

# No item: the model's NOTHING in a room, and the cave byte for an empty ware or overworld spot.
NO_ITEMS = frozenset({Item.NOTHING, Item.OVERWORLD_NO_ITEM})


def item_name(item: Item, names: Mapping[Item, str] = ITEM_NAMES) -> str | None:
    """The format's name for an item (in `names`: item_names(), the boots' with Pegasus Boots
    on); None for no item."""
    if item in NO_ITEMS:
        return None
    return names.get(item) or f"Unknown Item {int(item):02X}"


# --- dungeons -------------------------------------------------------------------------------

DOORS = {
    WallType.OPEN_DOOR: "open", WallType.SOLID_WALL: "solid", WallType.WALK_THROUGH_WALL_1: "walk-through",
    WallType.WALK_THROUGH_WALL_2: "walk-through", WallType.BOMB_HOLE: "bombable",
    WallType.LOCKED_DOOR_1: "locked", WallType.LOCKED_DOOR_2: "locked", WallType.SHUTTER_DOOR: "shutter",
}
# The level map shows the middle 8 of the 16 columns of the level's map bitmap; a room's
# bitmap column is its grid column shifted by the level's map start (SH-MAP-01,
# zora/generate/shapes/minimap.py).
MAP_COLUMNS_HIDDEN_LEFT = 4
MAP_COLUMN_MASK = 0x0F
# The level's map color: its wall color (the third color group's color), one NES
# brightness step up so that a dark wall color still shows on a map.
WALL_COLOR_GROUP = 2
BRIGHTNESS_STEP = 0x10
BRIGHTEST_ROW = 0x30
# Monsters without the level's group size: bosses, people and other single objects.
SINGLE_ENEMIES = frozenset({
    Enemy.THREE_PAIRS_OF_TRAPS, Enemy.CORNER_TRAPS, Enemy.FALLING_ROCKS, Enemy.FALLING_ROCK,
    Enemy.DIGDOGGER_SPAWN, Enemy.PATRA_SPAWN, Enemy.FLYING_GLEEOK_HEAD,
})
# A room's item is not on the floor when the room loads: the engine hides it for trigger 7
# (all dead), which brings it out when the foes are beaten, and for trigger 3 (last boss),
# where only Ganon's death code brings it out (aldonunez CheckUnderworldSecrets,
# Ganon_ActivateRoomItem; Room.item_hidden_at_load).
DROP_ACTIONS = frozenset({RoomAction.ALL_DEAD_ITEM, RoomAction.LAST_BOSS})
SHORT_WORDS = frozenset({"NSU"})


def display_name(enum_name: str) -> str:
    """An enum member's name in words: GLEEOK_ROOM -> "Gleeok Room", LAYOUT_0x2A -> "Layout $2A"."""
    if match := re.fullmatch(r"([A-Z_]+?)_0x([0-9A-F]{2})", enum_name):
        return f"{display_name(match.group(1))} ${match.group(2)}"
    return " ".join(word if word in SHORT_WORDS else word.capitalize() for word in enum_name.split("_"))


def map_column(level: Level, room_number: int) -> int:
    return ((room_grid.column(room_number) + level.map_start) & MAP_COLUMN_MASK) - MAP_COLUMNS_HIDDEN_LEFT + 1


def level_color(level: Level) -> str:
    color = level.palette_colors()[WALL_COLOR_GROUP]
    if color < BRIGHTEST_ROW:
        color += BRIGHTNESS_STEP
    return NES_PALETTE[color].upper()


# Without PS-BOMB-03's patch the engine's own test applies: persons outside levels 3, 4, 6,
# 8 and 9 take the selling path (aldonunez UpdateUnderworldPerson_Full).
VANILLA_SELLING_LEVELS = (1, 2, 5, 7)
TALKING_BOMB_UPGRADER = "Bomb Upgrader (Talks Only)"


def selling_levels(world: GameWorld) -> frozenset[int]:
    """The levels whose persons take the selling path (PS-BOMB-03's two patched levels)."""
    return frozenset(world.bomb_upgrade_levels or VANILLA_SELLING_LEVELS)


def room_enemies(level: Level, room: Room, selling: frozenset[int]) -> dict[str, Any] | None:
    """The room's monster. A bomb-upgrade person sells only in a selling level; elsewhere (a
    hint room whose code the helpful counter set to $0F, PS-HINT-05) it only talks."""
    enemy = room.enemy
    if enemy == Enemy.NOTHING:
        return None
    talks_only = enemy == Enemy.BOMB_UPGRADER and level.level_num not in selling
    entry: dict[str, Any] = {"name": TALKING_BOMB_UPGRADER if talks_only else display_name(enemy.name)}
    if not (enemy.is_boss or enemy.is_unkillable() or room.is_person or enemy in SINGLE_ENEMIES):
        entry["count"] = level.enemy_quantity(room)
    return entry


def room_item(room: Room, names: Mapping[Item, str] = ITEM_NAMES) -> dict[str, Any] | None:
    """The room's item; `appears` (a ZORA extra) says when: "floor" at once, "foes" when the
    room's foes are beaten, "ganon" when Ganon is, or "never" (trigger 3 without Ganon)."""
    name = item_name(room.item, names)
    if name is None:
        return None
    if room.room_action == RoomAction.ALL_DEAD_ITEM:
        appears = "foes"
    elif room.room_action == RoomAction.LAST_BOSS:
        appears = "ganon" if room.enemy == Enemy.THE_BEAST else "never"
    else:
        appears = "floor"
    return {"name": name, "drop": room.room_action in DROP_ACTIONS, "appears": appears}


def level_staircases(level: Level, names: Mapping[Item, str] = ITEM_NAMES) -> dict[int, dict[str, Any]]:
    """Each room's staircase: the item cellar it leads down to, or its end of a transport
    staircase (numbered in the level's staircase order), which names the other end."""
    stairs: dict[int, dict[str, Any]] = {}
    transports = 0
    for stair in level.staircase_rooms:
        if stair.room_type == RoomType.ITEM_STAIRCASE and stair.return_dest is not None:
            stairs[stair.return_dest] = {"kind": "item", "item": item_name(stair.item or Item.NOTHING, names)}
        elif stair.room_type == RoomType.TRANSPORT_STAIRCASE and None not in (stair.left_exit, stair.right_exit):
            transports += 1
            left, right = stair.left_exit, stair.right_exit
            assert left is not None and right is not None
            stairs[left] = {"kind": "transport", "number": transports, "to": right}
            stairs[right] = {"kind": "transport", "number": transports, "to": left}
    return stairs


def level_entry(level: Level, selling: frozenset[int], names: Mapping[Item, str] = ITEM_NAMES,
                has_gatekeepers: bool = False) -> dict[str, Any]:
    stairs = level_staircases(level, names)
    rooms = [{
        "number": room.room_num,
        "column": map_column(level, room.room_num),
        "row": room_grid.row(room.room_num) + 1,
        "type": display_name(room.room_type.name),
        "enemies": room_enemies(level, room, selling),
        "item": room_item(room, names),
        "staircase": stairs.get(room.room_num),
        "doors": {side: DOORS[getattr(room.walls, side)] for side in ("north", "east", "south", "west")},
    } for room in level.rooms]
    entry = {"number": level.level_num, "shownNumber": shown_number(level), "color": level_color(level),
             "rooms": rooms}
    if has_gatekeepers and level.level_num in GATEKEEPER_LEVELS:
        # Gatekeeper Bosses: the ROM's boss room (LevelInfo_BossRoomId) is the gatekeeper; only when set
        entry["gatekeeper"] = level.boss_room
    return entry


def seed_code_entry(rom: bytes, names: Mapping[Item, str]) -> list[str | None]:
    """The seed code as the file-select screen shows it: the four items' names, or under Item
    Sprites other than normal (C15, FP-SPRITE-01) its four characters, as one entry."""
    text = item_sprites.code_text(finished_in_prg0_layout(rom))
    return [text] if text is not None else [item_name(Item(value), names) for value in seed_code_values(rom)]


def shown_number(level: Level) -> int:
    """The number the level's label shows; under Hide Dungeon Numbers (B24, FP-LEVEL-02), whose
    label shows a question mark, the number it stands for (its data number)."""
    return level.level_num if level.rom_level_num == QUESTION_MARK_TILE else level.rom_level_num


# --- the overworld and its caves ----------------------------------------------------------

SHORT_NAMES = {
    Destination.WOOD_SWORD_CAVE: "Wood", Destination.TAKE_ANY: "Take", Destination.WHITE_SWORD_CAVE: "White",
    Destination.MAGICAL_SWORD_CAVE: "Magical", Destination.ANY_ROAD: "Road", Destination.LOST_HILLS_HINT: "Hills",
    Destination.MONEY_MAKING_GAME: "Game", Destination.DOOR_REPAIR: "Repair", Destination.LETTER_CAVE: "Letter",
    Destination.DEAD_WOODS_HINT: "Woods", Destination.POTION_SHOP: "Potion", Destination.HINT_SHOP_1: "Hint 1",
    Destination.HINT_SHOP_2: "Hint 2", Destination.SHOP_1: "Shop 1", Destination.SHOP_2: "Shop 2",
    Destination.SHOP_3: "Shop 3", Destination.SHOP_4: "Shop 4", Destination.MEDIUM_SECRET: "Medium",
    Destination.LARGE_SECRET: "Large", Destination.SMALL_SECRET: "Small",
}
LEVELS = range(Destination.LEVEL_1, Destination.LEVEL_9 + 1)
# The first quest's screens: those of both quests and those of the first only.
FIRST_QUEST = frozenset({QuestVisibility.BOTH_QUESTS, QuestVisibility.FIRST_QUEST})


def place_name(destination: Destination) -> str:
    """A place's name; a dungeon door by its data number (the door code, `Level.level_num`)."""
    if destination in LEVELS:
        return level_name(int(destination))
    return display_name(destination.name)


def short_name(destination: Destination) -> str:
    if destination in LEVELS:
        return f"L{int(destination)}"
    return SHORT_NAMES.get(destination, display_name(destination.name))


# Level numbering (owner ruling 2026-10-11): `number`, the screens' level-door names and the
# hints' `speaker` keep the data number (the door code, `Level.level_num`), which the visualizer
# reads; beside each, a `shown...` field holds the number the status bar shows on entry
# (`Level.rom_level_num`). The two differ only for a second-quest set's paired levels (2 and 3,
# 4 and 5, 7 and 8).
def level_name(number: int) -> str:
    return f"Level {number}"


def shown_numbers(world: GameWorld) -> dict[int, int]:
    """Each level's shown number by its data number."""
    return {level.level_num: shown_number(level) for level in world.levels}


def level_door(destination: Destination, shown: dict[int, int]) -> dict[str, str]:
    """A screen's cave entry; a level door's also names the level by its shown number."""
    entry = {"name": place_name(destination), "shortName": short_name(destination)}
    if destination in LEVELS:
        number = shown[int(destination)]
        entry |= {"shownName": level_name(number), "shownShortName": f"L{number}"}
    return entry


def overworld_entry(world: GameWorld, names: Mapping[Item, str] = ITEM_NAMES) -> dict[str, Any]:
    # 2nd Quest's leftover dungeon codes on 11 and 66 are shown but cannot be entered (OW-QST-05;
    # the recorder reveals neither): not entrances
    leftovers = second_quest_leftovers(world.overworld)
    shown = shown_numbers(world)
    screens = [{
        "number": screen.screen_num,
        "column": room_grid.column(screen.screen_num) + 1,
        "row": room_grid.row(screen.screen_num) + 1,
        "cave": level_door(screen.destination, shown),
    } for screen in world.overworld.screens
        if screen.destination != Destination.NONE and screen.quest_visibility in FIRST_QUEST
        and screen.screen_num not in leftovers]
    spots = {cave.destination: cave.item for cave in world.overworld.caves if isinstance(cave, OverworldItem)}
    return {"screens": screens,
            "armos": item_name(spots.get(Destination.ARMOS_ITEM, Item.OVERWORLD_NO_ITEM), names),
            "coast": item_name(spots.get(Destination.COAST_ITEM, Item.OVERWORLD_NO_ITEM), names)}


def sold_once(world: GameWorld, sells_once: bool, bait_in_pool: bool = False) -> dict[tuple[Destination, int], bool]:
    """PI-CODE-04: the shop wares sold once, from the bytes the ROM holds (code_patches'
    one_time_wares of the finished stock, Shop Items in the Item Pool's bait included); none when
    the patch is not in the ROM."""
    wares = one_time_wares(world, bait_in_pool=bait_in_pool) if sells_once else bytes(3)
    return {(destination, position): bool(byte & (1 << number))
            for number, destination in enumerate(SHOPS_BY_NUMBER) for position, byte in enumerate(wares)}


def cave_entries(world: GameWorld, sells_once: bool, bait_in_pool: bool = False,
                 names: Mapping[Item, str] = ITEM_NAMES) -> list[dict[str, Any]]:
    """The caves that give or sell items, in the model's cave order."""
    once = sold_once(world, sells_once, bait_in_pool)
    caves: list[dict[str, Any]] = []
    for cave in world.overworld.caves:
        name = place_name(cave.destination)
        if isinstance(cave, ItemCave):
            items = [cave.maybe_extra_candle, cave.item]
            caves.append({"name": name, "kind": "item",
                          "wares": [{"item": item_name(item, names)} for item in items if item_name(item)]})
        elif isinstance(cave, TakeAnyCave):
            caves.append({"name": name, "kind": "take-any",
                          "wares": [{"item": item_name(item, names)} for item in cave.items if item_name(item)]})
        elif isinstance(cave, Shop):
            kind = "potion-shop" if cave.destination == Destination.POTION_SHOP else "shop"
            caves.append({"name": name, "kind": kind, "wares": [
                {"item": item_name(ware.item, names), "price": ware.price,
                 "sellsOnce": once.get((cave.destination, position), False)}
                for position, ware in shop_wares(cave) if item_name(ware.item)]})
    return caves


def shop_wares(shop: Shop) -> list[tuple[int, ShopItem]]:
    """A shop's wares with their positions (0-2) in the ware table: the potion shop's two sit
    at 0 and 2, with Shuffle Blue Potion's middle ware at 1 (Shop.middle)."""
    if shop.destination != Destination.POTION_SHOP:
        return list(enumerate(shop.items))
    left, right = shop.items
    return [(0, left), *([(1, shop.middle)] if shop.middle is not None else []), (2, right)]


# --- texts and who says them --------------------------------------------------------------

# A text selector is twice the text's slot (the person-text pointer table is two bytes a text).
SELECTOR_TO_SLOT = 2
FIRST_PERSON = Enemy.ELDER             # people are object types $4B-$52: their table index
# Level 9's persons read a fixed table (aldonunez UnderworldPersonTextSelectorsC), which ZORA
# leaves as PRG0 has it.
LEVEL_9_SELECTORS = (0x44, 0x46, 0x48, 0x4A)
HUNGRY_GORIYA_SELECTOR = 0x24
TOLL_SELECTOR = 0x36                   # life-or-money people (aldonunez InitUnderworldPersonLifeOrMoney)
SPEAKER_LENGTH = 100


def person_slot(world: GameWorld, level: Level, room: Room) -> int | None:
    """The text slot a dungeon person shows: the hungry goriya and the life-or-money people
    have fixed texts; the others read selector table A or B by the level's person init
    (GameWorld.person_inits), or table C in level 9, at their object type less $4B."""
    enemy = room.enemy
    if enemy == Enemy.HUNGRY_GORIYA:
        return HUNGRY_GORIYA_SELECTOR // SELECTOR_TO_SLOT
    if enemy == Enemy.MUGGER:
        return TOLL_SELECTOR // SELECTOR_TO_SLOT
    if not room.is_person:
        return None
    index = enemy - FIRST_PERSON
    if level.level_num == 9:
        table: bytes | tuple[int, ...] = LEVEL_9_SELECTORS
    elif world.person_inits[level.level_num - 1] == UnderworldPersonInit.B:
        table = world.underworld_text_selectors_b or b""
    else:
        table = world.underworld_text_selectors_a or b""
    return table[index] // SELECTOR_TO_SLOT if 0 <= index < len(table) else None


# The hint shops' offers, in HintCaveTextSelectors0's order: Hint Shop 1's three, then Hint Shop 2's.
HINT_SHOP_OFFER_COUNT = 3
HINT_SHOP_OFFERS = {Destination.HINT_SHOP_1: range(0, 3), Destination.HINT_SHOP_2: range(3, 6)}


def hint_shop_slots(world: GameWorld, shop: HintShop) -> list[int]:
    """The text slot each of a hint shop's offers shows: its whole selector over two. (The parsed
    HintShopItem.quote_id keeps only the selector's low six bits, which misreads the generated
    hint style's selectors of $40 and up, HT-SEL-02.)"""
    selectors = world.hint_shop_offer_selectors
    if selectors is None or shop.destination not in HINT_SHOP_OFFERS:
        return [hint.quote_id for hint in shop.hints]
    return [selectors[offer] // SELECTOR_TO_SLOT for offer in HINT_SHOP_OFFERS[shop.destination]]


@dataclass(frozen=True)
class Speaker:
    """Who shows a text: `name` names a dungeon person's level by its data number, `shown_name`
    by its shown number (the same for the caves' people and the hint shops)."""
    name: str
    shown_name: str
    in_level: bool = False


def speakers(world: GameWorld) -> dict[int, list[Speaker]]:
    """Who shows each text slot: the overworld caves' people, the hint shops' hints, and the
    dungeon people."""
    said: dict[int, list[Speaker]] = {}
    for cave in world.overworld.caves:
        quote = getattr(cave, "quote_id", None)
        if quote is not None:
            name = place_name(cave.destination)
            said.setdefault(quote, []).append(Speaker(name, name))
        if isinstance(cave, HintShop):
            for number, offer_slot in enumerate(hint_shop_slots(world, cave), start=1):
                name = f"{place_name(cave.destination)}, hint {number}"
                said.setdefault(offer_slot, []).append(Speaker(name, name))
    for level in world.levels:
        for room in level.rooms:
            slot = person_slot(world, level, room)
            if slot is not None:
                room_text = f", room {room.room_num:02X}"
                said.setdefault(slot, []).append(Speaker(level_name(level.level_num) + room_text,
                                                         level_name(shown_number(level)) + room_text, in_level=True))
    return said


def shown_text(text: str) -> str:
    """A text as the player reads it: its lines joined, without the centering padding."""
    return " ".join(line.replace("~", " ").strip() for line in text.split("|") if line.strip("~ "))


def hint_entries(world: GameWorld) -> list[dict[str, Any]]:
    said = speakers(world)
    hints: list[dict[str, Any]] = []
    for slot, quote in enumerate(world.quotes):
        entry: dict[str, Any] = {"text": shown_text(quote.text)}
        if slot in said:
            entry["speaker"] = shorten("; ".join(speaker.name for speaker in said[slot]), SPEAKER_LENGTH)
            if any(speaker.in_level for speaker in said[slot]):
                entry["shownSpeaker"] = shorten("; ".join(speaker.shown_name for speaker in said[slot]),
                                                SPEAKER_LENGTH)
        hints.append(entry)
    return hints


def shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit - 3] + "..."


# --- requirements and settings -------------------------------------------------------------

# FP-TRIF-06's items as the entrance tests them: any sword, either candle, either arrow
GATE_ITEM_NAMES = {Item.WOOD_SWORD: "Sword", Item.BLUE_CANDLE: "Candle", Item.WOOD_ARROWS: "Arrow"}


def level_9_requirements(gate: Level9Gate) -> dict[str, Any]:
    """What level 9's entrance asks for (C08; FP-TRIF-01 to FP-TRIF-06), as the ROM's check holds
    it: the pieces needed (0 when open or an item), the chosen levels, or the item."""
    found: dict[str, Any] = {"level9Triforces": gate.pieces}
    if gate.kind is GateKind.LEVELS:
        found["level9Levels"] = sorted(gate.levels)
    if gate.kind is GateKind.ITEM:
        assert gate.item is not None
        found["level9Item"] = GATE_ITEM_NAMES.get(gate.item, ITEM_NAMES[gate.item])
    return found


def requirements(world: GameWorld) -> dict[str, Any]:
    found = level_9_requirements(world.level_9_gate)
    for cave in world.overworld.caves:
        if isinstance(cave, ItemCave) and cave.destination == Destination.WHITE_SWORD_CAVE:
            found["whiteSwordHearts"] = cave.heart_requirement
        elif isinstance(cave, ItemCave) and cave.destination == Destination.MAGICAL_SWORD_CAVE:
            found["magicalSwordHearts"] = cave.heart_requirement
        elif isinstance(cave, DoorRepairCave):
            found["doorRepairCost"] = cave.cost
    return found


QUESTION_MARK = "?"


# The rules that can change a value after the "?" values are drawn, in the order plan() applies
# them. A setting's changedBy names one: the name the spoiler log shows, then after ", " the spec
# rule, which the log leaves out.
ZORA_RULES = "a ZORA Extras rule"
BOSS_HEALTH_RULE = "Ganon HP 0 rule, FL-DEP-01 rule 3"
MERCHANT_RULE = "merchant toll rule, FL-DEP-04"
CAVE_RULE = "cave shuffle coin, FL-DEP-02 rule 1"
ROOM_RULE = "room shuffle coin, FL-DEP-02 rule 2"
MONSTER_RULE = "monster shuffle coin, FL-DEP-02 rule 3"


def resolution_stages(chosen: GenerationPlan) -> list[tuple[str, Settings]]:
    """The Z1R settings as the seed's "?" values resolved them (FL-DEP-04's own stream, the one
    generation used), then after each later rule that can change a value, as plan() applies them:
    FL-DEP-01 rule 3 (B41 and B46 never both on), FL-DEP-04's B22 and B23 rule, the
    ZORA Extras' rules (the owner's 2.0 dependencies), FL-DEP-02
    rule 1's coin (OW-CAVE-10), rule 2's (beta 8) and rule 3's (the 2026-10-22 export). The last is
    what the seed was generated with."""
    asked = decode(chosen.flag_string)
    resolved = resolve_question_marks(asked, chosen.seed, chosen.flag_string)
    stages = [("", resolved)]
    stages.append((BOSS_HEALTH_RULE, without_both_boss_health_rules(asked, stages[-1][1])))
    stages.append((MERCHANT_RULE, with_the_toll_beside_merchants(asked, stages[-1][1])))
    _, owner = zora_flags.resolve_owner_dependencies(chosen.zora_resolved, chosen.zora, stages[-1][1], asked)
    stages.append((ZORA_RULES, owner))
    stages.append((CAVE_RULE, meet_cave_prerequisite(owner, cave_prerequisite_rng(chosen.seed, chosen.flag_string))))
    stages.append((ROOM_RULE, meet_room_prerequisite(stages[-1][1], room_prerequisite_rng(chosen.seed,
                                                                                         chosen.flag_string))))
    stages.append((MONSTER_RULE, meet_monster_prerequisite(
        stages[-1][1], monster_prerequisite_rng(chosen.seed, chosen.flag_string))))
    return stages


def _field_value(settings: Settings, field: OptionField | ToggleField) -> int:
    return settings.option(field) if isinstance(field, OptionField) else int(settings.toggle(field))


def setting_entries(chosen: GenerationPlan) -> list[dict[str, str]]:
    """Every Z1R field as the string chose it and as the seed's "?" resolved it, and, where a later
    rule changed it (resolution_stages), its final value and the last rule that did; then ZORA's
    own flags."""
    asked = decode(chosen.flag_string)
    stages = resolution_stages(chosen)
    resolved = stages[0][1]
    entries = []
    for field in ALL_FIELDS:
        value = _field_value(asked, field)
        undecided = field.is_random(value) if isinstance(field, OptionField) else value == ThreeState.POSSIBLE
        entry = {"id": field.id, "name": flag_form.field_label(field),
                 "chosen": QUESTION_MARK if undecided else flag_form.value_label(field, value),
                 "resolved": flag_form.value_label(field, _field_value(resolved, field))}
        changed_by = ""
        for (_rule, before), (next_rule, after) in pairwise(stages):
            if _field_value(before, field) != _field_value(after, field):
                changed_by = next_rule
        final = _field_value(stages[-1][1], field)
        if final != _field_value(resolved, field):
            entry["final"] = flag_form.value_label(field, final)
            entry["changedBy"] = changed_by
        entries.append(entry)
    labels = {field["name"]: field["label"] for field in ZORA_FIELDS}
    entries.extend({"id": "ZORA", "name": labels.get(zora_field.name, zora_field.name),
                    "chosen": zora_entry_text(chosen.zora, zora_field.name),
                    "resolved": zora_entry_text(chosen.zora_resolved, zora_field.name)}
                   for zora_field in fields(chosen.zora) if zora_entry_shown(chosen.zora, zora_field.name))
    return entries


# ASNB's version-4 fields (docs/design/asnb.md section 1): the level-2 field is shown in Add L4
# Sword's entry (Off / Level 2 / Level 9); Level 9 Entrance only when set, so a seed without
# them keeps its document.
L4_SWORD_IN_LEVEL_2 = "l4_sword_in_level_2"
LEVEL_9_ENTRANCE = "level_9_entrance_sword"
L4_SWORD_TEXT = {zora_flags.L4Sword.LEVEL_2: "level 2", zora_flags.L4Sword.LEVEL_9: "level 9"}


# Oops All Enemies and Oops All Bosses (version 5) and Gatekeeper Bosses (version 12): shown only when
# set, by their value's name, so a seed without them keeps its document too.
OOPS_ALL_FIELDS = tuple(zora_flags.ENUM_FIELDS)


LISTED_WHEN_SET = frozenset((*zora_flags.ZORA_1_0_FIELDS, *zora_flags.PEGASUS_BOOTS_FIELDS,
                            *zora_flags.EXPANDED_DUNGEON_LOCATIONS_FIELDS,
                            *zora_flags.HIGHLIGHT_NO_DROP_ROOMS_FIELDS,
                            *zora_flags.DO_NOT_SEGMENT_DUNGEONS_FIELDS))


def zora_entry_shown(flags: zora_flags.ZoraFlags, name: str) -> bool:
    if name == L4_SWORD_IN_LEVEL_2:
        return False
    if name in OOPS_ALL_FIELDS or name in LISTED_WHEN_SET:
        # listed only when set, so the documents of seeds without them stay as they were
        return bool(getattr(flags, name))
    return name != LEVEL_9_ENTRANCE or flags.level_9_entrance_sword


def zora_entry_text(flags: zora_flags.ZoraFlags, name: str) -> str:
    """A ZORA field's value as the settings list shows it, Add L4 Sword's place and Level 9
    Entrance by name."""
    if name == "add_l4_sword" and flags.add_l4_sword is ThreeState.ON:
        return L4_SWORD_TEXT[flags.l4_sword]
    if name == LEVEL_9_ENTRANCE:
        return "level 4 sword" if flags.level_9_entrance_sword else "triforce pieces"
    return zora_value_text(getattr(flags, name))


def zora_value_text(value: bool | int | ThreeState | None) -> str:
    """A ZORA field's value as the settings list shows it."""
    if isinstance(value, ThreeState):
        return QUESTION_MARK if value is ThreeState.POSSIBLE else ("on" if value is ThreeState.ON else "off")
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, IntEnum):
        return value.name.lower().replace("_", " ")
    return "follow the Z1R flags" if value is None else str(value)


# --- the document --------------------------------------------------------------------------



def seed_document(rom: bytes, chosen: GenerationPlan) -> dict[str, Any]:
    """The finished ROM `rom`, generated from `chosen`, as a seed document."""
    if chosen.encode_level_data:
        raise EncodedSeedRefused
    world = parse_rom(rom, chosen.config)
    sells_once = chosen.zora.progressive_items or chosen.zora.shop_items_in_pool or chosen.config.potion_shop_in_pool
    # Pegasus Boots: the boomerangs' items are the boots, the seed code's $1D icon too (as the game draws it)
    names = item_names(chosen.zora_resolved.is_on("pegasus_boots"))
    document = {
        "format": FORMAT,
        "formatVersion": FORMAT_VERSION,
        "producer": {"name": PRODUCER, "version": ZORA_VERSION},
        "seed": {"number": str(chosen.seed), "flags": chosen.flag_string, "zoraFlags": chosen.zora_flag_string,
                 "code": seed_code_entry(rom, names)},
        "progressiveItems": chosen.zora.progressive_items,
        "levels": [level_entry(level, selling_levels(world), names, bool(chosen.zora_resolved.gatekeeper_bosses))
                   for level in sorted(world.levels, key=lambda level: level.level_num)],
        "overworld": overworld_entry(world, names),
        "caves": cave_entries(world, sells_once, chosen.config.bait_in_pool, names),
        "hints": hint_entries(world),
        "requirements": requirements(world),
        "settings": setting_entries(chosen),
    }
    if chosen.notices:
        document["notices"] = list(chosen.notices)
    extras = zora_extras(world, chosen)
    if extras:
        document["zoraExtras"] = extras
    return document


# --- the owner's 2.0 flags (a ZORA extra; seed format 1.1 has no fields for them) ----------------

NEEDS_WORDS = {Item.RAFT: "the raft", Item.POWER_BRACELET: "the power bracelet", Item.LADDER: "the ladder",
               LOST_HILLS_HINT: "Hint Shop 1 (the Lost Hills' path)",
               DEAD_WOODS_HINT: "Hint Shop 2 (the Dead Woods' path)"}


def zora_extras(world: GameWorld, chosen: GenerationPlan) -> dict[str, Any]:
    """The owner's 2.0 flags' results: each randomized maze's sequence and the hint shop offer
    selling it, each overworld gate's screens and what they need, and Add L4 Sword's room
    (docs/design/l4-sword.md R10). Empty with none on."""
    gates = overworld_gates(chosen.zora_resolved, chosen.settings)
    extras: dict[str, Any] = {}
    mazes = []
    for on, maze, sequence in ((gates.lost_hills, LOST_HILLS, world.overworld.lost_hills_directions),
                               (gates.dead_woods, DEAD_WOODS, world.overworld.dead_woods_directions)):
        if on:
            shop, offer = divmod(maze.hint_shop_offer, HINT_SHOP_OFFER_COUNT)
            mazes.append({"name": maze.name, "sequence": [maze.words[step].lower() for step in sequence],
                          "hintShop": f"Hint Shop {shop + 1}", "hint": offer + 1})
    if mazes:
        extras["mazes"] = mazes
    if gates.any:
        extras["gates"] = [{"screens": sorted(screens), "needs": NEEDS_WORDS[need]}
                           for screens, need in gates.screen_needs()]
    if chosen.zora_resolved.l4_sword is zora_flags.L4Sword.LEVEL_9:      # Level 2's is a pool item
        level9 = next(level for level in world.levels if level.level_num == LEVEL_9)
        room = next(room for room in level9.rooms if room.item == L4_SWORD_ITEM)
        extras["l4Sword"] = {"level": LEVEL_9, "room": room.room_num}
    return extras


def seed_document_for(rom: bytes, flag_string: str, seed: int, zora_flag_string: str = "") -> dict[str, Any]:
    """The page's way in: the plan again from the strings the ROM was made from (planning
    draws nothing from the generation's stream), then the document."""
    from zora.generate.pipeline import plan
    return seed_document(rom, plan(flag_string, seed, zora_flag_string))
