"""The acceptance check's figures (acceptance.md), E1's selection traces included."""

import statistics
from collections.abc import Callable

from zora.measure.checkpoints.overworld import _entry_door
from zora.measure.checkpoints.summaries import LEVELS_7_9, Summary
from zora.model.enums import Destination, Item, RoomType
from zora.model.game_world import GameWorld
from zora.model.overworld import ItemCave
from zora.model.rooms import Room, StaircaseRoom

# --- B6: the acceptance check (acceptance.md) ------------------------------------

SPEC_B6 = "acceptance.md @ 1f19c6e"
LONG_ITEMS = (Item.RECORDER, Item.BOW, Item.RAFT, Item.LADDER, Item.POWER_BRACELET)   # VA-REJ-08


def long_items_outside_level9(gw: GameWorld) -> bool:
    """VA-REJ-08's consequence: none of the five long items in a level-9
    item place (its rooms and item cellars)."""
    level9 = gw.levels[8]
    rooms = [r.item for r in level9.rooms]
    cellars = [c.item for c in gw.blocks[LEVELS_7_9].cells
               if isinstance(c, StaircaseRoom) and c.room_type == RoomType.ITEM_STAIRCASE
               and c.return_dest in level9.room_nums]
    return not any(item in LONG_ITEMS for item in rooms + cellars)


# --- E1's selection traces (acceptance.md VA-REJ-07/08/17) ------------------------

SPEC_E1 = "acceptance.md @ 6520ff7"
FAMILY_VALUE_FLAG = 0x80             # VA-REJ-17: the layout byte's bit 7 as value bit 7
RECORDER_LIST = frozenset({0x38, 0x39})
BOW_LIST = frozenset({0x33, 0x34})
SWORD_LIST = frozenset({0x82, 0x83, 0x84, 0x85, 0x87, 0x88, 0x16, 0xB0, 0xB8})
# (item, list) pairs the VA-REJ-17 Check names, by list
RECORDER_LIST_ITEMS = (Item.RECORDER, Item.POWER_BRACELET, Item.RAFT, Item.BOW)
BOW_LIST_ITEMS = (Item.BOW, Item.SILVER_ARROWS, Item.RECORDER, Item.RAFT)
SWORD_LIST_ITEMS = (Item.WAND, Item.BOW, Item.RAFT)
LADDER_LAYOUTS = frozenset({11, 18, 19, 20, 22, 24, 25})   # VA-REJ-07 (iv)
CAVE_SLOT = 0                        # "level" of an item in a special-cave slot


def family_value(room: Room) -> int:
    """VA-REJ-17's monster value: low six bits, plus $80 for the layout bit 7."""
    return room.monster_list | (FAMILY_VALUE_FLAG if room.has_monster_bit else 0)


def _level_rooms_of(gw: GameWorld) -> list[Room]:
    return [room for level in gw.levels for room in level.rooms]


def items_in_list_rooms(items: tuple[Item, ...], values: frozenset[int]
                        ) -> Callable[[GameWorld], dict[str, tuple[int, int]]]:
    """Per ROM, for each item: (level rooms holding it on the list, level
    rooms holding it)."""
    def per_rom(gw: GameWorld) -> dict[str, tuple[int, int]]:
        rooms = _level_rooms_of(gw)
        return {item.name.lower(): (sum(r.item == item and family_value(r) in values for r in rooms),
                                    sum(r.item == item for r in rooms))
                for item in items}
    return per_rom


def _ratios_text(values: list[dict[str, tuple[int, int]]]) -> str:
    return " ".join(f"{sum(v[k][0] for v in values)}/{sum(v[k][1] for v in values)}"
                    for k in values[0])


RATIOS = Summary(_ratios_text, lambda ratios: {k: (float(h), float(n)) for k, (h, n) in ratios.items()})


def item_places(gw: GameWorld) -> dict[Item, list[int]]:
    """Each item's places: the level number of each level room or item
    cellar holding it, CAVE_SLOT for the three special-cave slots."""
    places: dict[Item, list[int]] = {}
    for level in gw.levels:
        for room in level.rooms:
            places.setdefault(room.item, []).append(level.level_num)
    for block in gw.blocks:
        for cell in block.cells:
            if isinstance(cell, StaircaseRoom) and cell.room_type == RoomType.ITEM_STAIRCASE \
                    and cell.item is not None:
                # room numbers repeat across the two blocks: the owner is in this block
                owner = block.owner_of(cell.return_dest) if cell.return_dest is not None else None
                if owner is not None:
                    places.setdefault(cell.item, []).append(owner.level_num)
    for slot in _cave_slots(gw).values():
        places.setdefault(slot, []).append(CAVE_SLOT)
    return places


def _cave_slots(gw: GameWorld) -> dict[str, Item]:
    from zora.model.overworld import OverworldItem
    ow = gw.overworld
    armos = ow.get_cave(Destination.ARMOS_ITEM, OverworldItem)
    coast = ow.get_cave(Destination.COAST_ITEM, OverworldItem)
    white = ow.get_cave(Destination.WHITE_SWORD_CAVE, ItemCave)
    return {name: Item(slot.item & 0x3F) for name, slot in
            (("armos", armos), ("white_sword", white), ("coast", coast)) if slot is not None}


PLACE_KEYS = (1, 2, 3, 4, 5, 6, 7, 8, 9, CAVE_SLOT)


def long_item_level(item: Item) -> Callable[[GameWorld], int | None]:
    """The level (CAVE_SLOT for a cave slot) of the item's first place."""
    def per_rom(gw: GameWorld) -> int | None:
        found = item_places(gw).get(item)
        return found[0] if found else None
    return per_rom


def long_item_split(gw: GameWorld) -> dict[str, int]:
    """The five long items' places: levels 1-6, levels 7-8, cave slots."""
    places = item_places(gw)
    where = [places.get(item, [None])[0] for item in LONG_ITEMS]
    return {"levels 1-6": sum(w is not None and 1 <= w <= 6 for w in where),
            "levels 7-8": sum(w in (7, 8) for w in where),
            "cave slots": sum(w == CAVE_SLOT for w in where)}


SPLIT_SUMMARY = Summary(
    lambda values: " / ".join(f"{statistics.mean(v[k] for v in values):.3f}" for k in values[0]),
    lambda split: {k: float(n) for k, n in split.items()}
)

TRACKED_TYPES = (Item.WHITE_SWORD, Item.RECORDER, Item.RED_CANDLE, Item.SILVER_ARROWS, Item.BOW,
                 Item.MAGICAL_KEY, Item.RAFT, Item.LADDER, Item.WAND, Item.BOOK, Item.RED_RING,
                 Item.POWER_BRACELET, Item.WOOD_BOOMERANG, Item.MAGICAL_BOOMERANG)
# (the fifteenth tracked type, the heart container, is not placeable on a
# finished ROM: every heart place holds the same byte)


def tracked_in_level9(gw: GameWorld) -> int:
    """How many of the fourteen identifiable tracked types lie in level 9."""
    places = item_places(gw)
    return sum(9 in places.get(item, []) for item in TRACKED_TYPES)


def self_locks(gw: GameWorld) -> dict[str, bool]:
    """Placements E1 can never accept: a long item in a level whose entry
    door needs it; the ladder in the coast slot; the white-sword cave's own
    screen need in that cave; the ladder in a ladder-layout room."""
    from zora.generate.steps.cave_entries import (
        BRACELET_SCREENS,
        LADDER_SCREENS,
        RAFT_SCREENS,
        RECORDER_SCREENS,
    )
    needs = ((RAFT_SCREENS, Item.RAFT), (RECORDER_SCREENS, Item.RECORDER),
             (LADDER_SCREENS, Item.LADDER), (BRACELET_SCREENS, Item.POWER_BRACELET))
    screens = [int(s.destination) for s in gw.overworld.screens]
    places = item_places(gw)
    entrance = False
    for screen_set, item in needs:
        for level in places.get(item, []):
            if level != CAVE_SLOT and _entry_door(gw, level) in screen_set:
                entrance = True
    slots = _cave_slots(gw)
    ws_screens = [s for s, d in enumerate(screens) if d == Destination.WHITE_SWORD_CAVE]
    ws_own = bool(ws_screens) and any(
        ws_screens[0] in screen_set and slots.get("white_sword") == item for screen_set, item in needs
    )
    ladder_room = any(r.item == Item.LADDER and int(r.room_type) & 0x3F in LADDER_LAYOUTS
                      for r in _level_rooms_of(gw))
    return {"entrance": entrance, "coast ladder": slots.get("coast") == Item.LADDER,
            "white-sword own need": ws_own, "ladder room": ladder_room}


def e1_replay(gw: GameWorld) -> bool:
    """VA-REJ-07's closure (zora/generate/acceptance_check.py) run on the finished
    ROM: the fourteen identifiable tracked types where the ROM holds them
    (the heart container is left out), the entry doors from the overworld.
    Every corpus final was accepted when it was made, so the corpus column tests
    that ZORA's check is not stricter than the corpus's; the ZORA column
    must be all accepted by construction."""
    from zora.generate.acceptance_check import AcceptanceCheck
    from zora.generate.steps.cave_entries import FIXED_DUNGEON_DOORS, CaveShuffle, Entry
    from zora.generate.steps.item_shuffle_result import ItemShuffleResult, TrackedPlace
    places = item_places(gw)
    slot_of = {item: name for name, item in _cave_slots(gw).items()}
    tracked = []
    for item in TRACKED_TYPES:
        if item in slot_of:
            tracked.append(TrackedPlace(int(item), slot=slot_of[item]))
        elif places.get(item):
            tracked.append(TrackedPlace(int(item), level=places[item][0]))
        else:
            return False
    movable = (Destination.WHITE_SWORD_CAVE, *(Destination(d) for d in range(1, 10)))
    entries = [Entry(screen, s.destination, 0) for screen, s in enumerate(gw.overworld.screens)
               if s.destination in movable and FIXED_DUNGEON_DOORS.get(int(s.destination)) != screen]
    caves = CaveShuffle(entries, armos_screen=gw.overworld.armos_screen_ids[0])
    return AcceptanceCheck(gw.levels, ItemShuffleResult(tracked=tracked), gw.overworld, caves) \
        .collects_everything()
