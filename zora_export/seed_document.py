"""The seed document: a finished seed in the visualizer's seed format, version 1.0
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
from dataclasses import fields
from typing import Any

from zora.flags import form as flag_form
from zora.flags import zora_flags
from zora.flags.codec import decode
from zora.flags.fields import OptionField, ThreeState
from zora.flags.form import ALL_FIELDS
from zora.flags.zora_form import FIELDS as ZORA_FIELDS
from zora.generate.pipeline import GenerationPlan, overworld_gates, resolve_question_marks
from zora.generate.steps.add_l4_sword import L4_SWORD_ITEM
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
from zora.model.item_names import ITEM_NAMES
from zora.model.levels import LEVEL_9, Level
from zora.model.overworld import DoorRepairCave, HintShop, ItemCave, OverworldItem, Shop, ShopItem, TakeAnyCave
from zora.model.rooms import Room
from zora.rom.code_patches import (
    SEED_CODE_NAMES,
    SHOPS_BY_NUMBER,
    one_time_wares,
    seed_code,
)
from zora.rom.parse.rom_file import parse_rom
from zora.version import PLAYER_NAME, ZORA_VERSION
from zora_export.nes_palette import NES_PALETTE

FORMAT = "z1r-seed"
FORMAT_VERSION = "1.0"
PRODUCER = PLAYER_NAME


class EncodedSeedRefused(ValueError):
    """The seed format's first rule: no seed document for a seed with level encoding on."""

    def __init__(self) -> None:
        super().__init__('no seed document or spoiler for a seed made with "Encode level data" on')


# --- items ---------------------------------------------------------------------------------

# No item: the model's NOTHING in a room, and the cave byte for an empty ware or overworld spot.
NO_ITEMS = frozenset({Item.NOTHING, Item.OVERWORLD_NO_ITEM})


def item_name(item: Item) -> str | None:
    """The format's name for an item; None for no item."""
    if item in NO_ITEMS:
        return None
    return ITEM_NAMES.get(item) or f"Unknown Item {int(item):02X}"


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
# The level's map colour: its wall colour (the third colour group's colour), one NES
# brightness step up so that a dark wall colour still shows on a map.
WALL_COLOUR_GROUP = 2
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


def level_colour(level: Level) -> str:
    colour = level.palette_colors()[WALL_COLOUR_GROUP]
    if colour < BRIGHTEST_ROW:
        colour += BRIGHTNESS_STEP
    return NES_PALETTE[colour].upper()


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


def room_item(room: Room) -> dict[str, Any] | None:
    """The room's item; `appears` (a ZORA extra) says when: "floor" at once, "foes" when the
    room's foes are beaten, "ganon" when Ganon is, or "never" (trigger 3 without Ganon)."""
    name = item_name(room.item)
    if name is None:
        return None
    if room.room_action == RoomAction.ALL_DEAD_ITEM:
        appears = "foes"
    elif room.room_action == RoomAction.LAST_BOSS:
        appears = "ganon" if room.enemy == Enemy.THE_BEAST else "never"
    else:
        appears = "floor"
    return {"name": name, "drop": room.room_action in DROP_ACTIONS, "appears": appears}


def level_staircases(level: Level) -> dict[int, dict[str, Any]]:
    """Each room's staircase: the item cellar it leads down to, or its end of a transport
    staircase (numbered in the level's staircase order), which names the other end."""
    stairs: dict[int, dict[str, Any]] = {}
    transports = 0
    for stair in level.staircase_rooms:
        if stair.room_type == RoomType.ITEM_STAIRCASE and stair.return_dest is not None:
            stairs[stair.return_dest] = {"kind": "item", "item": item_name(stair.item or Item.NOTHING)}
        elif stair.room_type == RoomType.TRANSPORT_STAIRCASE and None not in (stair.left_exit, stair.right_exit):
            transports += 1
            left, right = stair.left_exit, stair.right_exit
            assert left is not None and right is not None
            stairs[left] = {"kind": "transport", "number": transports, "to": right}
            stairs[right] = {"kind": "transport", "number": transports, "to": left}
    return stairs


def level_entry(level: Level, selling: frozenset[int]) -> dict[str, Any]:
    stairs = level_staircases(level)
    rooms = [{
        "number": room.room_num,
        "column": map_column(level, room.room_num),
        "row": room_grid.row(room.room_num) + 1,
        "type": display_name(room.room_type.name),
        "enemies": room_enemies(level, room, selling),
        "item": room_item(room),
        "staircase": stairs.get(room.room_num),
        "doors": {side: DOORS[getattr(room.walls, side)] for side in ("north", "east", "south", "west")},
    } for room in level.rooms]
    return {"number": level.level_num, "color": level_colour(level), "rooms": rooms}


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
    if destination in LEVELS:
        return f"Level {int(destination)}"
    return display_name(destination.name)


def short_name(destination: Destination) -> str:
    if destination in LEVELS:
        return f"L{int(destination)}"
    return SHORT_NAMES.get(destination, display_name(destination.name))


def overworld_entry(world: GameWorld) -> dict[str, Any]:
    screens = [{
        "number": screen.screen_num,
        "column": room_grid.column(screen.screen_num) + 1,
        "row": room_grid.row(screen.screen_num) + 1,
        "cave": {"name": place_name(screen.destination), "shortName": short_name(screen.destination)},
    } for screen in world.overworld.screens
        if screen.destination != Destination.NONE and screen.quest_visibility in FIRST_QUEST]
    spots = {cave.destination: cave.item for cave in world.overworld.caves if isinstance(cave, OverworldItem)}
    return {"screens": screens,
            "armos": item_name(spots.get(Destination.ARMOS_ITEM, Item.OVERWORLD_NO_ITEM)),
            "coast": item_name(spots.get(Destination.COAST_ITEM, Item.OVERWORLD_NO_ITEM))}


def sold_once(world: GameWorld, sells_once: bool) -> dict[tuple[Destination, int], bool]:
    """PI-CODE-04: the shop wares sold once, from the bytes the ROM holds (code_patches'
    one_time_wares of the finished stock); none when the patch is not in the ROM."""
    wares = one_time_wares(world) if sells_once else bytes(3)
    return {(destination, position): bool(byte & (1 << number))
            for number, destination in enumerate(SHOPS_BY_NUMBER) for position, byte in enumerate(wares)}


def cave_entries(world: GameWorld, sells_once: bool) -> list[dict[str, Any]]:
    """The caves that give or sell items, in the model's cave order."""
    once = sold_once(world, sells_once)
    caves: list[dict[str, Any]] = []
    for cave in world.overworld.caves:
        name = place_name(cave.destination)
        if isinstance(cave, ItemCave):
            items = [cave.maybe_extra_candle, cave.item]
            caves.append({"name": name, "kind": "item",
                          "wares": [{"item": item_name(item)} for item in items if item_name(item)]})
        elif isinstance(cave, TakeAnyCave):
            caves.append({"name": name, "kind": "take-any",
                          "wares": [{"item": item_name(item)} for item in cave.items if item_name(item)]})
        elif isinstance(cave, Shop):
            kind = "potion-shop" if cave.destination == Destination.POTION_SHOP else "shop"
            caves.append({"name": name, "kind": kind, "wares": [
                {"item": item_name(ware.item), "price": ware.price,
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
FIRST_PERSON = Enemy.OLD_MAN           # people are object types $4B-$52: their table index
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


def speakers(world: GameWorld) -> dict[int, list[str]]:
    """Who shows each text slot: the overworld caves' people, the hint shops' hints, and the
    dungeon people."""
    said: dict[int, list[str]] = {}
    for cave in world.overworld.caves:
        quote = getattr(cave, "quote_id", None)
        if quote is not None:
            said.setdefault(quote, []).append(place_name(cave.destination))
        if isinstance(cave, HintShop):
            for number, offer_slot in enumerate(hint_shop_slots(world, cave), start=1):
                said.setdefault(offer_slot, []).append(f"{place_name(cave.destination)}, hint {number}")
    for level in world.levels:
        for room in level.rooms:
            slot = person_slot(world, level, room)
            if slot is not None:
                said.setdefault(slot, []).append(f"Level {level.level_num}, room {room.room_num:02X}")
    return said


def shown_text(text: str) -> str:
    """A text as the player reads it: its lines joined, without the centring padding."""
    return " ".join(line.replace("~", " ").strip() for line in text.split("|") if line.strip("~ "))


def hint_entries(world: GameWorld) -> list[dict[str, Any]]:
    said = speakers(world)
    hints: list[dict[str, Any]] = []
    for slot, quote in enumerate(world.quotes):
        entry: dict[str, Any] = {"text": shown_text(quote.text)}
        if slot in said:
            entry["speaker"] = shorten("; ".join(said[slot]), SPEAKER_LENGTH)
        hints.append(entry)
    return hints


def shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit - 3] + "..."


# --- requirements and settings -------------------------------------------------------------

# The engine opens level 9 for all eight triforce pieces (InvTriforce $FF), the only C08
# value ZORA produces.
LEVEL_9_TRIFORCES = 8


def requirements(world: GameWorld) -> dict[str, int]:
    found: dict[str, int] = {"level9Triforces": LEVEL_9_TRIFORCES}
    for cave in world.overworld.caves:
        if isinstance(cave, ItemCave) and cave.destination == Destination.WHITE_SWORD_CAVE:
            found["whiteSwordHearts"] = cave.heart_requirement
        elif isinstance(cave, ItemCave) and cave.destination == Destination.MAGICAL_SWORD_CAVE:
            found["magicalSwordHearts"] = cave.heart_requirement
        elif isinstance(cave, DoorRepairCave):
            found["doorRepairCost"] = cave.cost
    return found


QUESTION_MARK = "?"


def setting_entries(chosen: GenerationPlan) -> list[dict[str, str]]:
    """Every Z1R field as the string chose it and as the seed resolved it (FL-DEP-04's own
    stream, the one generation used), then ZORA's own flags."""
    asked = decode(chosen.flag_string)
    resolved = zora_flags.without_extra_candles(
        chosen.zora, resolve_question_marks(asked, chosen.seed, chosen.flag_string), asked)
    # the owner's 2.0 dependencies may turn a "?" on B04 off (idempotent on the resolved ZORA flags)
    _, resolved = zora_flags.resolve_owner_dependencies(chosen.zora_resolved, chosen.zora, resolved, asked)
    entries = []
    for field in ALL_FIELDS:
        if isinstance(field, OptionField):
            value, final = asked.option(field), resolved.option(field)
            undecided = field.is_random(value)
        else:
            value, final = int(asked.toggle(field)), int(resolved.toggle(field))
            undecided = value == ThreeState.POSSIBLE
        entries.append({"id": field.id, "name": flag_form.field_label(field),
                        "chosen": QUESTION_MARK if undecided else flag_form.value_label(field, value),
                        "resolved": flag_form.value_label(field, final)})
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


def zora_entry_shown(flags: zora_flags.ZoraFlags, name: str) -> bool:
    if name == L4_SWORD_IN_LEVEL_2:
        return False
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
    return "follow the Z1R flags" if value is None else str(value)


# --- the document --------------------------------------------------------------------------

CODE_ITEMS = {name: Item(code) for code, name in SEED_CODE_NAMES.items()}


def seed_document(rom: bytes, chosen: GenerationPlan) -> dict[str, Any]:
    """The finished ROM `rom`, generated from `chosen`, as a seed document."""
    if chosen.encode_level_data:
        raise EncodedSeedRefused
    world = parse_rom(rom, chosen.config)
    sells_once = chosen.zora.progressive_items or chosen.zora.shop_items_in_pool or chosen.config.potion_shop_in_pool
    document = {
        "format": FORMAT,
        "formatVersion": FORMAT_VERSION,
        "producer": {"name": PRODUCER, "version": ZORA_VERSION},
        "seed": {"number": str(chosen.seed), "flags": chosen.flag_string, "zoraFlags": chosen.zora_flag_string,
                 "code": [item_name(CODE_ITEMS[name]) or name for name in seed_code(rom)]},
        "progressiveItems": chosen.zora.progressive_items,
        "levels": [level_entry(level, selling_levels(world))
                   for level in sorted(world.levels, key=lambda level: level.level_num)],
        "overworld": overworld_entry(world),
        "caves": cave_entries(world, sells_once),
        "hints": hint_entries(world),
        "requirements": requirements(world),
        "settings": setting_entries(chosen),
    }
    extras = zora_extras(world, chosen)
    if extras:
        document["zoraExtras"] = extras
    return document


# --- the owner's 2.0 flags (a ZORA extra; seed format 1.0 has no fields for them) ----------------

NEEDS_WORDS = {Item.RAFT: "the raft", Item.POWER_BRACELET: "the power bracelet", Item.LADDER: "the ladder",
               LOST_HILLS_HINT: "Hint Shop 1 (the Lost Hills' path)",
               DEAD_WOODS_HINT: "Hint Shop 2 (the Dead Woods' path)"}


def zora_extras(world: GameWorld, chosen: GenerationPlan) -> dict[str, Any]:
    """The owner's 2.0 flags' results: each randomized maze's sequence and the hint shop offer
    selling it, each overworld gate's screens and what they need, and Add L4 Sword's room
    (docs/design/l4-sword.md R10). Empty with none on."""
    gates = overworld_gates(chosen.zora_resolved)
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
