"""Item places (Archipelago Phase 2; docs/archipelago.md): where a finished world holds an item of
ZORA's major pool, so that another filler (Archipelago) can put its own item in each place.

Places are read from the finished world, after every generation step has moved items (the late
gate's re-deal, the room exchange, VA-REJ-20, the map move, the ZORA extras' exchanges), so they
are where items really are. A place is any of these that holds a major-pool item:
  - a level room's item, or an item cellar's item (ROOM, CELLAR);
  - the Armos and coast items, the white-sword cave, and with their ZORA flags on the
    magical-sword and letter caves (CAVE);
  - with Shop Items in the Item Pool on, the shop wares that joined the pool (SHOP_WARE);
  - with Shuffle Blue Potion on, the potion shop's middle ware (POTION_SHOP; empty in PRG0, the
    left blue potion stays a re-buyable ware and is never a place).

The major pool (owner decision 1, 2026-10-08) is the item shuffle's (PS-ITEM): the twelve
progression items, the three special-cave items and heart containers, plus each ZORA extra's
items while its flag is on (Add L4 Sword = Level 2's sword upgrade, item $01, among them). Small
items, maps, compasses, triforces and Add L4 Sword = Level 9's fixed sword are never places.

Never a place, even holding a pool item (R2): a room on the last-boss trigger (the rule
move_last_boss_room_items applies, is_last_boss_room), and Ganon's and Zelda's rooms.

Each place carries what the filler must respect (R2): `forbids`, items it must never hold, and
`requires`, conditions local to the place (the sword caves' hearts). Reachability is not here:
it comes from ZORA's own walk code (dungeon_walk, the late gate's walk, acceptance_check), which
Phase 3 calls on the built world; each place names where that walk finds it (`level` and
`room_num`, or the overworld `screens`).
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum

from ..model.enums import Destination, Enemy, Item, QuestVisibility, RoomType
from ..model.game_world import GameWorld
from ..model.levels import Level
from ..model.overworld import POTION_SHOP_MIDDLE, ItemCave, OverworldItem, Shop
from ..model.rooms import Room, StaircaseRoom
from .extra_options import ExtraOptions
from .steps.move_last_boss_room_items import is_last_boss_room
from .steps.shop_items_in_pool import JOINED_SHOP_ITEMS
from .steps.shuffle_items import POOL_ORDER
from .steps.shuffle_shop_items import SHOPS


class PlaceKind(Enum):
    ROOM = "room"                    # a level room's item: on the floor, or dropped (trigger 7)
    CELLAR = "cellar"                # an item cellar's item
    CAVE = "cave"                    # an overworld item or a one-item cave
    SHOP_WARE = "shop ware"          # a ware of shops 1-4 joined by Shop Items in the Item Pool
    POTION_SHOP = "potion shop"      # the potion shop's middle ware, Shuffle Blue Potion's place


@dataclass(frozen=True)
class HeartsRequired:
    """A sword cave's condition on whatever item it holds: at least `hearts` heart containers,
    as BUILD set it (change_sword_hearts)."""
    hearts: int


@dataclass(frozen=True)
class Place:
    """One place an item can go. Dungeon places name `level` and `room_num` (for a cellar its
    own cell, where the walk finds it, and `stair_room`, the room its stairs are in); overworld
    places name `destination`, `position` (a shop ware's index) and `screens`, the overworld
    screens whose entrance leads there (the Armos item: the formation's screen; the coast: none,
    the game gives it at a fixed spot)."""
    kind: PlaceKind
    name: str
    level: int | None = None
    room_num: int | None = None
    stair_room: int | None = None
    destination: Destination | None = None
    position: int | None = None
    screens: tuple[int, ...] = ()
    forbids: frozenset[Item] = frozenset()
    requires: tuple[HeartsRequired, ...] = ()

    @property
    def is_dungeon(self) -> bool:
        return self.kind in (PlaceKind.ROOM, PlaceKind.CELLAR)

    @property
    def is_shop(self) -> bool:
        return self.kind in (PlaceKind.SHOP_WARE, PlaceKind.POTION_SHOP)


# --- the major pool --------------------------------------------------------------------------

# The special-cave items the item shuffle pools with the progression items (PRG0's Armos, white
# sword and coast items).
SPECIAL_CAVE_ITEMS = frozenset({Item.POWER_BRACELET, Item.WHITE_SWORD, Item.HEART_CONTAINER})
BASE_POOL = frozenset(Item(code) for code in POOL_ORDER) | SPECIAL_CAVE_ITEMS


def major_pool(extras: ExtraOptions) -> frozenset[Item]:
    """The item codes of the major pool under these ZORA flags."""
    items = set(BASE_POOL)
    if extras.randomize_magical_sword:
        items.add(Item.MAGICAL_SWORD)
    if extras.randomize_letter:
        items.add(Item.LETTER)
    if extras.shop_items_in_pool:
        items.update(JOINED_SHOP_ITEMS)
    if extras.shuffle_blue_potion:
        items.add(Item.BLUE_POTION)
    if extras.l4_sword_in_level_2:
        items.add(Item.WOOD_SWORD)       # ASNB's level-2 sword upgrade (steps/level_2_sword.py)
    return frozenset(items)


# --- restrictions (R2) -----------------------------------------------------------------------

# With ZORA's remap on, $0E reads as "no item" in a dungeon room or cellar; it only belongs in
# Ganon's room, which is never a place.
DUNGEON_FORBIDS = frozenset({Item.TRIFORCE_OF_POWER})
# A joined shop ware may sell any pool item, heart containers included: ZORA's own seeds do, and
# SI-PRICE-01 prices them (20-40). The spec's "no heart containers in shops" is not applied, since
# it would refuse ZORA's own placement (docs/archipelago.md, "Restrictions").
SHOP_FORBIDS: frozenset[Item] = frozenset()
# The potion shop opens only for a player who shows the letter (Shuffle Blue Potion).
POTION_SHOP_FORBIDS = SHOP_FORBIDS | {Item.LETTER}
# Ganon and Zelda (add_l4_sword's EXCLUDED_MONSTERS): their rooms are never places.
FINAL_ROOM_ENEMIES = frozenset({Enemy.THE_BEAST, Enemy.THE_KIDNAPPED})


def is_never_a_place(room: Room) -> bool:
    """R2: a room whose item is never collected in play by design: on the last-boss trigger
    (VA-REJ-20's rule), or Ganon's or Zelda's room."""
    return is_last_boss_room(room) or room.enemy in FINAL_ROOM_ENEMIES


# --- names -----------------------------------------------------------------------------------

LEVELS = range(1, 10)
ROOM_NUMBERS = range(128)
WARE_NAMES = ("Left", "Middle", "Right")
CAVE_NAMES: dict[Destination, str] = {
    Destination.ARMOS_ITEM: "Armos",
    Destination.COAST_ITEM: "Coast",
    Destination.WHITE_SWORD_CAVE: "White Sword Cave",
    Destination.MAGICAL_SWORD_CAVE: "Magical Sword Cave",
    Destination.LETTER_CAVE: "Letter Cave",
}
SHOP_NAMES: dict[Destination, str] = {
    **{shop: f"Shop {number}" for number, shop in enumerate(SHOPS, start=1)},
    Destination.POTION_SHOP: "Potion Shop",
}


def room_name(level: int, room_num: int) -> str:
    return f"Level {level} Room {room_num:02X}"


def cellar_name(level: int, stair_room: int) -> str:
    """An item cellar, by the room its stairs are in."""
    return f"{room_name(level, stair_room)} Cellar"


def ware_name(shop: Destination, position: int) -> str:
    return f"{SHOP_NAMES[shop]} {WARE_NAMES[position]}"


def all_place_names() -> list[str]:
    """Every name any seed can produce, for Archipelago's fixed location IDs, in a fixed order:
    levels 1-9 x rooms $00-$7F x {room, cellar}, then the caves and the shop wares."""
    names = [name for level in LEVELS for room_num in ROOM_NUMBERS
             for name in (room_name(level, room_num), cellar_name(level, room_num))]
    names += list(CAVE_NAMES.values())
    names += [ware_name(shop, position) for shop in SHOP_NAMES for position in range(len(WARE_NAMES))]
    return names


# --- enumeration -----------------------------------------------------------------------------

def _level(world: GameWorld, level_num: int) -> Level:
    return next(level for level in world.levels if level.level_num == level_num)


def _item_cellars(level: Level) -> Iterator[StaircaseRoom]:
    """The level's item cellars holding an item: those returning to one of its rooms (as
    dungeon_walk.item_cellar reads ownership)."""
    for stair in level.block.staircases:
        if (stair.room_type == RoomType.ITEM_STAIRCASE and stair.item is not None
                and stair.return_dest in level.room_nums):
            yield stair


def _dungeon_places(world: GameWorld, pool: frozenset[Item]) -> list[Place]:
    """Rooms and item cellars holding a pool item, block by block, in room-number order."""
    found: list[tuple[int, int, Place]] = []
    for level in world.levels:
        block_index = next(index for index, block in enumerate(world.blocks) if block is level.block)
        found.extend((block_index, room.room_num, Place(
            PlaceKind.ROOM, room_name(level.level_num, room.room_num), level=level.level_num,
            room_num=room.room_num, forbids=DUNGEON_FORBIDS))
            for room in level.rooms if room.item in pool and not is_never_a_place(room))
        for cellar in _item_cellars(level):
            if cellar.item in pool:
                assert cellar.return_dest is not None
                found.append((block_index, cellar.room_num, Place(
                    PlaceKind.CELLAR, cellar_name(level.level_num, cellar.return_dest), level=level.level_num,
                    room_num=cellar.room_num, stair_room=cellar.return_dest, forbids=DUNGEON_FORBIDS)))
    return [place for _block, _room, place in sorted(found, key=lambda entry: entry[:2])]


def _screens(world: GameWorld, destination: Destination) -> tuple[int, ...]:
    """The first-quest overworld screens whose entrance leads to `destination`."""
    return tuple(screen.screen_num for screen in world.overworld.screens
                 if screen.destination == destination
                 and screen.quest_visibility in (QuestVisibility.BOTH_QUESTS, QuestVisibility.FIRST_QUEST))


def _cave_destinations(extras: ExtraOptions) -> list[Destination]:
    """The cave places under these ZORA flags, in Destination order."""
    caves = [Destination.WHITE_SWORD_CAVE, Destination.ARMOS_ITEM, Destination.COAST_ITEM]
    if extras.randomize_magical_sword:
        caves.append(Destination.MAGICAL_SWORD_CAVE)
    if extras.randomize_letter:
        caves.append(Destination.LETTER_CAVE)
    return sorted(caves)


def _cave_place(world: GameWorld, destination: Destination) -> Place:
    overworld = world.overworld
    if destination == Destination.ARMOS_ITEM:
        screens: tuple[int, ...] = (overworld.armos_screen_ids[0],)
    elif destination == Destination.COAST_ITEM:
        screens = ()
    else:
        screens = _screens(world, destination)
    requires: tuple[HeartsRequired, ...] = ()
    if destination in (Destination.WHITE_SWORD_CAVE, Destination.MAGICAL_SWORD_CAVE):
        cave = overworld.get_cave(destination, ItemCave)
        assert cave is not None, destination
        requires = (HeartsRequired(cave.heart_requirement),)
    return Place(PlaceKind.CAVE, CAVE_NAMES[destination], destination=destination, screens=screens,
                 requires=requires)


def _ware_places(world: GameWorld, extras: ExtraOptions, pool: frozenset[Item]) -> list[Place]:
    """The joined shop wares: a ware of shops 1-4 holding a pool item (each joined item was sold
    by exactly one ware, which keeps a pool item after every exchange), then the potion shop's
    middle ware."""
    places = []
    if extras.shop_items_in_pool:
        for shop in SHOPS:
            cave = world.overworld.get_cave(shop, Shop)
            assert cave is not None, shop
            places += [Place(PlaceKind.SHOP_WARE, ware_name(shop, position), destination=shop, position=position,
                             screens=_screens(world, shop), forbids=SHOP_FORBIDS)
                       for position, ware in enumerate(cave.items) if ware.item in pool]
    if extras.shuffle_blue_potion:
        places.append(Place(PlaceKind.POTION_SHOP, ware_name(Destination.POTION_SHOP, POTION_SHOP_MIDDLE),
                            destination=Destination.POTION_SHOP, position=POTION_SHOP_MIDDLE,
                            screens=_screens(world, Destination.POTION_SHOP), forbids=POTION_SHOP_FORBIDS))
    return places


def all_item_places(world: GameWorld, extras: ExtraOptions) -> list[Place]:
    """Every place of the finished world holding a major-pool item, in a fixed order: the
    dungeon places (block, then room number), then the caves and the shop wares in Destination
    order. The same world and flags give the same list; so does the world parsed back from the
    finished ZORA-mode ROM."""
    pool = major_pool(extras)
    caves = [_cave_place(world, destination) for destination in _cave_destinations(extras)]
    overworld = sorted(caves + _ware_places(world, extras, pool),
                       key=lambda place: (place.destination, place.position or 0))
    return _dungeon_places(world, pool) + overworld


# --- reading and writing ---------------------------------------------------------------------

def _room(world: GameWorld, place: Place) -> Room:
    assert place.level is not None and place.room_num is not None
    return _level(world, place.level).block.room(place.room_num)


def _cellar(world: GameWorld, place: Place) -> StaircaseRoom:
    assert place.level is not None
    return next(stair for stair in _level(world, place.level).block.staircases if stair.room_num == place.room_num)


def _ware(world: GameWorld, place: Place) -> Shop:
    assert place.destination is not None and place.position is not None
    shop = world.overworld.get_cave(place.destination, Shop)
    assert shop is not None, place.name
    return shop


def _cave(world: GameWorld, place: Place) -> OverworldItem | ItemCave:
    assert place.destination is not None
    cave: OverworldItem | ItemCave | None
    if place.destination in (Destination.ARMOS_ITEM, Destination.COAST_ITEM):
        cave = world.overworld.get_cave(place.destination, OverworldItem)
    else:
        cave = world.overworld.get_cave(place.destination, ItemCave)
    assert cave is not None, place.name
    return cave


def read_item(world: GameWorld, place: Place) -> Item:
    """The item the place holds."""
    if place.kind == PlaceKind.ROOM:
        return _room(world, place).item
    if place.kind == PlaceKind.CELLAR:
        item = _cellar(world, place).item
        assert item is not None, place.name
        return item
    if place.is_shop:
        assert place.position is not None
        return _ware(world, place).ware(place.position).item
    return _cave(world, place).item


def write_item(world: GameWorld, place: Place, item: Item) -> None:
    """Put `item` in the place, changing the item code only: a room keeps its boss sound, its
    darkness, its trigger and its item position; a cave or shop keeps its own flags (written from
    its kind) and a ware its price."""
    if place.kind == PlaceKind.ROOM:
        _room(world, place).item = item
    elif place.kind == PlaceKind.CELLAR:
        _cellar(world, place).item = item
    elif place.is_shop:
        assert place.position is not None
        _ware(world, place).ware(place.position).item = item
    else:
        _cave(world, place).item = item
