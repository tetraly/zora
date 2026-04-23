"""
AssumedFill randomizer for Zelda 1.

Places all major items into the game world using the assumed fill algorithm,
which guarantees a beatable seed by construction.

The algorithm:
  1. Collect item pool and location pool from the game world.
  2. Pre-place any forced/constrained items.
  3. While items remain in the pool:
     a. Assume the player has ALL remaining unplaced items.
     b. Find all empty locations reachable under that assumption.
     c. Pick a random item and a random valid location for it.
     d. Place the item, remove from pool.
  4. Run is_seed_valid() as a final sanity check.
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass

logger = logging.getLogger(__name__)

from zora.data_model import (
    Destination,
    EntranceType,
    GameWorld,
    Item,
    ItemCave,
    OverworldItem,
    RoomAction,
    Shop,
    ShopType,
    TakeAnyCave,
)
from zora.game_config import GameConfig
from zora.game_validator import (
    CaveLocation,
    DungeonLocation,
    GameValidator,
    Location,
)
from zora.inventory import Inventory
from zora.rng import Rng

# ---------------------------------------------------------------------------
# Major item pool
# ---------------------------------------------------------------------------

MAJOR_ITEMS: list[Item] = [
    Item.WOOD_SWORD,
    Item.WHITE_SWORD,
    Item.MAGICAL_SWORD,
    Item.LETTER,
    Item.BAIT,
    Item.RECORDER,
    Item.BLUE_CANDLE,
    Item.RED_CANDLE,
    Item.WOOD_ARROWS,
    Item.SILVER_ARROWS,
    Item.BOW,
    Item.MAGICAL_KEY,
    Item.RAFT,
    Item.LADDER,
    Item.WAND,
    Item.BOOK,
    Item.BLUE_RING,
    Item.RED_RING,
    Item.POWER_BRACELET,
    Item.WOOD_BOOMERANG,
    Item.MAGICAL_BOOMERANG,
]

# Items whose value > 0x1F — only valid in cave/shop locations (dungeon rooms
# use a 5-bit field). Currently none of MAJOR_ITEMS exceed 0x1F, but heart
# containers (0x1A) are fine in dungeons.
_SHOP_ONLY_ITEMS: set[Item] = {
    item for item in Item if item.value > 0x1F
}

_SWORD_OR_WAND = {Item.WOOD_SWORD, Item.WHITE_SWORD, Item.MAGICAL_SWORD, Item.WAND}
# Items that are progressive base versions — buying multiples would give free upgrades
_PROGRESSIVE_BASE_ITEMS = {Item.WOOD_SWORD, Item.BLUE_RING, Item.WOOD_ARROWS, Item.BLUE_CANDLE}
_ARROW_ITEMS = {Item.WOOD_ARROWS, Item.SILVER_ARROWS}
_RING_ITEMS = {Item.BLUE_RING, Item.RED_RING}
_L9_IMPORTANT_ITEMS = {Item.BOW, Item.LADDER, Item.POWER_BRACELET, Item.RAFT, Item.RECORDER}

_DESTINATION_TO_SHOP_TYPE = {
    Destination.SHOP_1:      ShopType.SHOP_A,
    Destination.SHOP_2:      ShopType.SHOP_B,
    Destination.SHOP_3:      ShopType.SHOP_C,
    Destination.SHOP_4:      ShopType.SHOP_D,
    Destination.POTION_SHOP: ShopType.SHOP_E,
}

_SHOP_DESTINATIONS = frozenset(_DESTINATION_TO_SHOP_TYPE.keys())


# ---------------------------------------------------------------------------
# Constraint system
# ---------------------------------------------------------------------------

@dataclass
class Constraints:
    """Placement constraints for assumed fill."""

    # Structural constraints (always enforced)
    heart_containers_forbidden_from_shops: bool = True
    ladder_forbidden_from_coast: bool = True
    letter_forbidden_from_potion_shop: bool = True
    shop_only_items_forbidden_from_dungeons: bool = True
    progressive_items_forbidden_from_shops: bool = False
    guarantee_starting_sword_or_wand: bool = True
    important_items_forbidden_from_l9: bool = True

    # Forced placements (pre-placement pass)
    force_heart_container_to_armos: bool = False
    force_heart_container_to_coast: bool = False
    force_ring_to_level_nine: bool = False
    force_arrow_to_level_nine: bool = False

    # Forced item enum fields (None = not forced)
    forced_white_sword_item: Item | None = None
    forced_armos_item: Item | None = None
    forced_coast_item: Item | None = None

    @classmethod
    def from_config(cls, config: GameConfig) -> "Constraints":
        return cls(
            progressive_items_forbidden_from_shops=config.progressive_items,
            guarantee_starting_sword_or_wand=True,
            important_items_forbidden_from_l9=not config.allow_important_in_l9,
            force_heart_container_to_armos=(
                config.forced_armos_item == Item.HEART_CONTAINER
            ),
            force_heart_container_to_coast=(
                config.forced_coast_item == Item.HEART_CONTAINER
            ),
            force_ring_to_level_nine=config.force_rr_to_l9,
            force_arrow_to_level_nine=config.force_sa_to_l9,
            forced_white_sword_item=config.forced_white_sword_item,
            forced_armos_item=config.forced_armos_item,
            forced_coast_item=config.forced_coast_item,
        )


def is_item_valid_for_location(
    item: Item,
    location: Location,
    constraints: Constraints,
) -> bool:
    """Return True if placing item at location satisfies all constraints."""
    is_shop = isinstance(location, CaveLocation) and location.destination in _SHOP_DESTINATIONS
    is_dungeon = isinstance(location, DungeonLocation)

    if constraints.heart_containers_forbidden_from_shops:
        if item == Item.HEART_CONTAINER and is_shop:
            return False

    if constraints.ladder_forbidden_from_coast:
        if item == Item.LADDER and isinstance(location, CaveLocation):
            if location.destination == Destination.COAST_ITEM:
                return False

    if constraints.letter_forbidden_from_potion_shop:
        if item == Item.LETTER and isinstance(location, CaveLocation):
            if location.destination == Destination.POTION_SHOP:
                return False

    if constraints.shop_only_items_forbidden_from_dungeons:
        if is_dungeon and item in _SHOP_ONLY_ITEMS:
            return False

    if constraints.progressive_items_forbidden_from_shops:
        if is_shop and item in _PROGRESSIVE_BASE_ITEMS:
            return False

    if constraints.important_items_forbidden_from_l9:
        if isinstance(location, DungeonLocation) and location.level_num == 9:
            if item in _L9_IMPORTANT_ITEMS:
                return False

    return True


# ---------------------------------------------------------------------------
# Constraint validation (pre-flight check)
# ---------------------------------------------------------------------------

def _validate_constraints(
    item_pool: list[Item],
    location_pool: list[Location],
    constraints: Constraints,
) -> None:
    """Raise ValueError if constraints are provably unsatisfiable."""
    armos_loc = CaveLocation(Destination.ARMOS_ITEM, 0)
    coast_loc = CaveLocation(Destination.COAST_ITEM, 0)
    level_9_locs = [loc for loc in location_pool
                    if isinstance(loc, DungeonLocation) and loc.level_num == 9]

    if constraints.force_heart_container_to_armos:
        if Item.HEART_CONTAINER not in item_pool:
            raise ValueError("force_heart_container_to_armos: no heart containers in pool")
        if armos_loc not in location_pool:
            raise ValueError("force_heart_container_to_armos: armos location not in pool "
                             "(enable shuffle_armos_item)")

    if constraints.force_heart_container_to_coast:
        if Item.HEART_CONTAINER not in item_pool:
            raise ValueError("force_heart_container_to_coast: no heart containers in pool")
        if coast_loc not in location_pool:
            raise ValueError("force_heart_container_to_coast: coast location not in pool "
                             "(enable shuffle_coast_item)")

    if constraints.force_arrow_to_level_nine:
        arrows = [i for i in item_pool if i in _ARROW_ITEMS]
        if not arrows:
            raise ValueError("force_arrow_to_level_nine: no arrow items in pool")
        if not level_9_locs:
            raise ValueError("force_arrow_to_level_nine: no level 9 locations in pool")

    if constraints.force_ring_to_level_nine:
        rings = [i for i in item_pool if i in _RING_ITEMS]
        if not rings:
            raise ValueError("force_ring_to_level_nine: no ring items in pool")
        if not level_9_locs:
            raise ValueError("force_ring_to_level_nine: no level 9 locations in pool")


# ---------------------------------------------------------------------------
# Location and item pool collection
# ---------------------------------------------------------------------------

# TODO: shuffle_dungeon_hearts=True combined with heart-gated sword caves
# (white sword requires 5 hearts, magical sword requires 12) is a known hard
# constraint. When hearts are shuffled throughout the dungeon pool, the assumed
# fill can leave the sword caves unreachable if hearts land behind progression
# gates. Fixing this requires either: (a) pre-placing enough hearts in early
# accessible dungeons to satisfy the cave requirements, or (b) treating the
# sword caves' heart requirements as placement constraints in the MRV scoring.
# This is deferred to a follow-up. Default flags (shuffle_dungeon_hearts=False)
# are fully supported and produce valid seeds reliably.

def _is_major_item(item: Item) -> bool:
    return item in MAJOR_ITEMS


def collect_item_locations(game_world: GameWorld, config: GameConfig) -> list[Location]:
    """Collect all locations eligible for item placement based on flags."""
    locations: list[Location] = []

    # Dungeon locations: rooms and staircase rooms that hold a major item
    # (or heart container if shuffled). Triforces and compasses/maps are
    # handled by dungeon_item_shuffler.py — not included here.
    for level in game_world.levels:
        for room in level.rooms:
            if _is_major_item(room.item):
                locations.append(DungeonLocation(level.level_num, room.room_num))
            elif config.shuffle_dungeon_hearts and room.item == Item.HEART_CONTAINER:
                locations.append(DungeonLocation(level.level_num, room.room_num))
        for sr in level.staircase_rooms:
            if sr.item is not None and _is_major_item(sr.item):
                locations.append(DungeonLocation(level.level_num, sr.room_num))
            elif sr.item is not None and config.shuffle_dungeon_hearts and sr.item == Item.HEART_CONTAINER:
                locations.append(DungeonLocation(level.level_num, sr.room_num))

    # Cave locations
    ow = game_world.overworld
    cave_by_dest = {c.destination: c for c in ow.caves}
    if config.shuffle_wood_sword:
        locations.append(CaveLocation(Destination.WOOD_SWORD_CAVE, 0))
    if config.shuffle_white_sword:
        locations.append(CaveLocation(Destination.WHITE_SWORD_CAVE, 0))
    if config.shuffle_magical_sword:
        locations.append(CaveLocation(Destination.MAGICAL_SWORD_CAVE, 0))
    if config.shuffle_letter:
        locations.append(CaveLocation(Destination.LETTER_CAVE, 0))
    if config.shuffle_armos_item:
        locations.append(CaveLocation(Destination.ARMOS_ITEM, 0))
    if config.shuffle_coast_item:
        locations.append(CaveLocation(Destination.COAST_ITEM, 0))

    # shuffle_take_any_items hardcoded False for MVP
    # TODO: wire to flags_generated.py in future phase

    major_shops = [
        (ShopType.SHOP_A, Destination.SHOP_1),
        (ShopType.SHOP_B, Destination.SHOP_2),
        (ShopType.SHOP_C, Destination.SHOP_3),
        (ShopType.SHOP_D, Destination.SHOP_4),
    ]
    if config.shuffle_major_shop_items:
        for shop_type, dest in major_shops:
            c = cave_by_dest.get(dest)
            if c is not None:
                assert isinstance(c, Shop)
                for i, shop_item in enumerate(c.items):
                    if _is_major_item(shop_item.item):
                        locations.append(CaveLocation(dest, i))
    if config.shuffle_blue_potion:
        c = cave_by_dest.get(Destination.POTION_SHOP)
        if c is not None:
            assert isinstance(c, Shop)
            for i, shop_item in enumerate(c.items):
                if _is_major_item(shop_item.item):
                    locations.append(CaveLocation(Destination.POTION_SHOP, i))

    return locations


def _collect_item_pool(game_world: GameWorld, config: GameConfig) -> list[Item]:
    """Collect all major items currently placed in the eligible locations."""
    pool: list[Item] = []

    for level in game_world.levels:
        for room in level.rooms:
            if _is_major_item(room.item):
                pool.append(room.item)
            elif config.shuffle_dungeon_hearts and room.item == Item.HEART_CONTAINER:
                pool.append(room.item)
        for sr in level.staircase_rooms:
            if sr.item is not None and _is_major_item(sr.item):
                pool.append(sr.item)
            elif sr.item is not None and config.shuffle_dungeon_hearts and sr.item == Item.HEART_CONTAINER:
                pool.append(sr.item)

    ow = game_world.overworld
    cave_by_dest = {c.destination: c for c in ow.caves}

    def _get_item_cave_item(dest: Destination) -> Item | None:
        c = cave_by_dest.get(dest)
        if c is not None and isinstance(c, ItemCave):
            return c.item
        return None

    def _get_overworld_item(dest: Destination) -> Item | None:
        c = cave_by_dest.get(dest)
        if c is not None and isinstance(c, OverworldItem):
            return c.item
        return None

    if config.shuffle_wood_sword:
        item = _get_item_cave_item(Destination.WOOD_SWORD_CAVE)
        if item is not None and _is_major_item(item):
            pool.append(item)
    if config.shuffle_white_sword:
        item = _get_item_cave_item(Destination.WHITE_SWORD_CAVE)
        if item is not None and _is_major_item(item):
            pool.append(item)
    if config.shuffle_magical_sword:
        item = _get_item_cave_item(Destination.MAGICAL_SWORD_CAVE)
        if item is not None and _is_major_item(item):
            pool.append(item)
    if config.shuffle_letter:
        item = _get_item_cave_item(Destination.LETTER_CAVE)
        if item is not None and _is_major_item(item):
            pool.append(item)
    if config.shuffle_armos_item:
        item = _get_overworld_item(Destination.ARMOS_ITEM)
        if item is not None and (_is_major_item(item) or item == Item.HEART_CONTAINER):
            pool.append(item)
    if config.shuffle_coast_item:
        item = _get_overworld_item(Destination.COAST_ITEM)
        if item is not None and (_is_major_item(item) or item == Item.HEART_CONTAINER):
            pool.append(item)

    if config.shuffle_major_shop_items:
        for dest in [Destination.SHOP_1, Destination.SHOP_2, Destination.SHOP_3, Destination.SHOP_4]:
            c = cave_by_dest.get(dest)
            if c is not None and isinstance(c, Shop):
                for shop_item in c.items:
                    if _is_major_item(shop_item.item):
                        pool.append(shop_item.item)
    if config.shuffle_blue_potion:
        c = cave_by_dest.get(Destination.POTION_SHOP)
        if c is not None and isinstance(c, Shop):
            for shop_item in c.items:
                if _is_major_item(shop_item.item):
                    pool.append(shop_item.item)

    if config.progressive_items:
        pool = [_progressive_downgrade(item) for item in pool]

    return pool


# Progressive item downgrade map: higher-tier items become their base version
# so that multiple copies of the base item end up in the pool.
_PROGRESSIVE_DOWNGRADE: dict[Item, Item] = {
    Item.WHITE_SWORD:    Item.WOOD_SWORD,
    Item.MAGICAL_SWORD:  Item.WOOD_SWORD,
    Item.RED_RING:       Item.BLUE_RING,
    Item.SILVER_ARROWS:  Item.WOOD_ARROWS,
    Item.RED_CANDLE:     Item.BLUE_CANDLE,
}


def _progressive_downgrade(item: Item) -> Item:
    return _PROGRESSIVE_DOWNGRADE.get(item, item)


# Higher-tier items that must never appear in a shuffled location on a
# progressive seed — the pool transformation should have replaced them all.
_PROGRESSIVE_FORBIDDEN = frozenset(_PROGRESSIVE_DOWNGRADE.keys())

# Maximum occurrences of each base item across all shuffled locations.
_PROGRESSIVE_MAX_COUNTS: dict[Item, int] = {
    Item.WOOD_SWORD:  3,   # wood + white + magical
    Item.BLUE_RING:   2,   # blue + red
    Item.WOOD_ARROWS: 2,   # wood + silver
    Item.BLUE_CANDLE: 2,   # blue + red
}


def _check_progressive_placement_invariants(
    game_world: GameWorld,
    location_pool: list[Location],
    config: GameConfig,
) -> bool:
    """Return False if any shuffled location contains a forbidden or over-counted item.

    Only the locations that were part of the fill (location_pool) are checked —
    non-shuffled caves may still hold their vanilla higher-tier items.
    """
    from collections import Counter

    placed: list[Item] = []
    for loc in location_pool:
        if isinstance(loc, DungeonLocation):
            level = game_world.levels[loc.level_num - 1]
            for room in level.rooms:
                if room.room_num == loc.room_num:
                    placed.append(room.item)
                    break
            else:
                for sr in level.staircase_rooms:
                    if sr.room_num == loc.room_num:
                        if sr.item is not None:
                            placed.append(sr.item)
                        break
        else:
            items = _get_cave_items_for_location(game_world, loc)
            placed.extend(items)

    for item in placed:
        if item in _PROGRESSIVE_FORBIDDEN:
            return False

    max_counts = dict(_PROGRESSIVE_MAX_COUNTS)
    if config.add_l4_sword:
        max_counts[Item.WOOD_SWORD] = 4  # wood + white + magical + L4

    counts = Counter(placed)
    for item, max_count in max_counts.items():
        if counts[item] > max_count:
            return False

    return True


def _get_cave_items_for_location(game_world: GameWorld, loc: CaveLocation) -> list[Item]:
    """Return the item(s) at a CaveLocation in the current game world state."""
    ow = game_world.overworld
    cave_by_dest = {c.destination: c for c in ow.caves}
    c = cave_by_dest.get(loc.destination)
    if c is None:
        return []
    match loc.destination:
        case (Destination.WOOD_SWORD_CAVE | Destination.WHITE_SWORD_CAVE
              | Destination.MAGICAL_SWORD_CAVE | Destination.LETTER_CAVE):
            assert isinstance(c, ItemCave)
            return [c.item]
        case Destination.ARMOS_ITEM | Destination.COAST_ITEM:
            assert isinstance(c, OverworldItem)
            return [c.item]
        case _:
            if loc.destination in _SHOP_DESTINATIONS:
                assert isinstance(c, Shop)
                return [c.items[loc.position].item]
            return []


# ---------------------------------------------------------------------------
# Item placement into GameWorld
# ---------------------------------------------------------------------------

def _place_item(game_world: GameWorld, item: Item, location: Location) -> None:
    """Write an item placement into the GameWorld (mutates in place)."""
    if isinstance(location, DungeonLocation):
        level = game_world.levels[location.level_num - 1]
        for room in level.rooms:
            if room.room_num == location.room_num:
                room.item = item
                return
        for sr in level.staircase_rooms:
            if sr.room_num == location.room_num:
                sr.item = item
                return
        raise ValueError(f"Room {location.room_num:#04x} not found in level {location.level_num}")

    # CaveLocation
    ow = game_world.overworld
    dest = location.destination
    cave_by_dest = {c.destination: c for c in ow.caves}
    c = cave_by_dest[dest]
    match dest:
        case (Destination.WOOD_SWORD_CAVE | Destination.WHITE_SWORD_CAVE
              | Destination.MAGICAL_SWORD_CAVE | Destination.LETTER_CAVE):
            assert isinstance(c, ItemCave)
            c.item = item
        case Destination.ARMOS_ITEM | Destination.COAST_ITEM:
            assert isinstance(c, OverworldItem)
            c.item = item
        case Destination.TAKE_ANY:
            assert isinstance(c, TakeAnyCave)
            c.items[location.position] = item
        case _:
            assert isinstance(c, Shop)
            c.items[location.position].item = item


def _clear_location(game_world: GameWorld, location: Location) -> None:
    """set a location to Item.NOTHING (used before assumed fill begins)."""
    _place_item(game_world, Item.NOTHING, location)


def compute_self_blocking_locations(
    game_world: GameWorld,
    location_pool: list[Location],
) -> dict[Item, set[Location]]:
    """Return a map of item → locations where placing that item makes it unreachable.

    A dungeon room with action KILLING_ENEMIES_OPENS_SHUTTERS_AND_DROPS_ITEM is
    self-blocking for any item that is uniquely required to kill its enemy:

    - GOHMA rooms require BOW (arrows alone don't help — the other arrow type
      can substitute, so only BOW itself is self-blocking here).
    - DIGDOGGER rooms require RECORDER.
    """
    forbidden: dict[Item, set[Location]] = defaultdict(set)

    for level in game_world.levels:
        for room in level.rooms:
            loc = DungeonLocation(level.level_num, room.room_num)
            if loc not in location_pool:
                continue
            if room.room_action != RoomAction.KILLING_ENEMIES_OPENS_SHUTTERS_AND_DROPS_ITEM:
                continue
            enemy = room.enemy_spec.enemy
            if enemy.is_gohma():
                forbidden[Item.BOW].add(loc)
            elif enemy.is_digdogger():
                forbidden[Item.RECORDER].add(loc)

    return forbidden


# ---------------------------------------------------------------------------
# Pre-placement pass
# ---------------------------------------------------------------------------

def _force_place(
    game_world: GameWorld,
    item: Item,
    location: Location,
    item_pool: list[Item],
    location_pool: list[Location],
) -> None:
    """Place item at location and remove both from their pools."""
    _place_item(game_world, item, location)
    item_pool.remove(item)
    if location in location_pool:
        location_pool.remove(location)


def _find_open_sword_cave(
    game_world: GameWorld,
    location_pool: list[Location],
) -> CaveLocation | None:
    """Find a sword cave (WOOD_SWORD_CAVE or LETTER_CAVE) behind an OPEN screen."""
    open_dests: set[Destination] = set()
    for screen in game_world.overworld.screens:
        if screen.entrance_type == EntranceType.OPEN:
            open_dests.add(screen.destination)

    candidates = [
        CaveLocation(Destination.WOOD_SWORD_CAVE, 0),
        CaveLocation(Destination.LETTER_CAVE, 0),
    ]
    for loc in candidates:
        if loc in location_pool and loc.destination in open_dests:
            return loc
    return None


def _pre_place_forced_items(
    game_world: GameWorld,
    item_pool: list[Item],
    location_pool: list[Location],
    constraints: Constraints,
    rng: Rng,
) -> bool:
    """Place forced items, mutating item_pool and location_pool in place.

    Returns False if the layout makes a valid seed impossible (e.g. no sword
    cave is behind an OPEN screen), signaling the caller to skip the fill.
    """
    level_9_locs = [loc for loc in location_pool
                    if isinstance(loc, DungeonLocation) and loc.level_num == 9]

    if constraints.guarantee_starting_sword_or_wand:
        sword_cave_in_pool = any(
            loc for loc in location_pool
            if isinstance(loc, CaveLocation)
            and loc.destination in (Destination.WOOD_SWORD_CAVE, Destination.LETTER_CAVE)
        )
        if sword_cave_in_pool:
            sword_loc = _find_open_sword_cave(game_world, location_pool)
            if sword_loc is None:
                logger.info("  pre-place: no sword cave behind OPEN screen — skipping fill")
                return False
            swords_and_wands = [i for i in item_pool if i in _SWORD_OR_WAND]
            if swords_and_wands:
                item = rng.choice(swords_and_wands)
                _force_place(game_world, item, sword_loc, item_pool, location_pool)

    if constraints.force_heart_container_to_armos:
        loc = CaveLocation(Destination.ARMOS_ITEM, 0)
        _force_place(game_world, Item.HEART_CONTAINER, loc, item_pool, location_pool)

    if constraints.force_heart_container_to_coast:
        loc = CaveLocation(Destination.COAST_ITEM, 0)
        _force_place(game_world, Item.HEART_CONTAINER, loc, item_pool, location_pool)
        # Rebuild level_9_locs since location_pool may have changed
        level_9_locs = [loc for loc in location_pool
                        if isinstance(loc, DungeonLocation) and loc.level_num == 9]

    if constraints.force_arrow_to_level_nine:
        level_9_locs = [loc for loc in location_pool
                        if isinstance(loc, DungeonLocation) and loc.level_num == 9]
        arrows = [i for i in item_pool if i in _ARROW_ITEMS]
        if arrows and level_9_locs:
            dloc = rng.choice(level_9_locs)
            item = rng.choice(arrows)
            _force_place(game_world, item, dloc, item_pool, location_pool)

    if constraints.force_ring_to_level_nine:
        level_9_locs = [loc for loc in location_pool
                        if isinstance(loc, DungeonLocation) and loc.level_num == 9]
        rings = [i for i in item_pool if i in _RING_ITEMS]
        if rings and level_9_locs:
            dloc = rng.choice(level_9_locs)
            item = rng.choice(rings)
            _force_place(game_world, item, dloc, item_pool, location_pool)

    # Item enum forced placements (white_sword_item, armos_item, coast_item)
    # force_heart_container cases are already handled above; skip here to avoid double-placing.
    forced_locations = [
        (constraints.forced_white_sword_item, CaveLocation(Destination.WHITE_SWORD_CAVE, 0)),
        (constraints.forced_armos_item,       CaveLocation(Destination.ARMOS_ITEM, 0)),
        (constraints.forced_coast_item,       CaveLocation(Destination.COAST_ITEM, 0)),
    ]
    for forced_item, loc in forced_locations:
        if forced_item is None or forced_item == Item.HEART_CONTAINER:
            continue  # None = random, heart_container already handled above
        if loc in location_pool and forced_item in item_pool:
            _force_place(game_world, forced_item, loc, item_pool, location_pool)

    return True


# ---------------------------------------------------------------------------
# Assumed fill
# ---------------------------------------------------------------------------

def _apply_progressive_upgrades(inv: Inventory, item_list: list[Item]) -> None:
    """Add progressive upgrade items to an assumed inventory.

    The assumed inventory is built with set.add() which deduplicates base items.
    This function counts base item occurrences in the original list and adds the
    corresponding upgrade items that would result from collecting them in sequence.
    """
    if not inv.progressive_items:
        return
    _UPGRADE_CHAINS: list[tuple[Item, list[Item]]] = [
        (Item.WOOD_SWORD, [Item.WHITE_SWORD, Item.MAGICAL_SWORD]),
        (Item.BLUE_RING, [Item.RED_RING]),
        (Item.WOOD_ARROWS, [Item.SILVER_ARROWS]),
        (Item.BLUE_CANDLE, [Item.RED_CANDLE]),
    ]
    for base, upgrades in _UPGRADE_CHAINS:
        count = item_list.count(base)
        for upgrade in upgrades[:count - 1]:
            inv.items.add(upgrade)


def assumed_fill(game_world: GameWorld, config: GameConfig, rng: Rng) -> bool:
    """Place all major items using assumed fill. Mutates game_world in place.

    Returns True if a valid seed was generated, False if placement was
    impossible (rare with assumed fill; indicates over-constrained input).
    """
    constraints = Constraints.from_config(config)
    validator = GameValidator(game_world, config.avoid_required_hard_combat,
                              progressive_items=config.progressive_items)

    # Progressive items + magical sword cave not shuffled: overwrite the cave
    # with a WOOD_SWORD so the player finds a sword upgrade there instead of
    # an unreachable magical sword (matching the old ZORA behavior).
    if config.progressive_items and not config.shuffle_magical_sword:
        cave_by_dest = {c.destination: c for c in game_world.overworld.caves}
        c = cave_by_dest.get(Destination.MAGICAL_SWORD_CAVE)
        if c is not None and isinstance(c, ItemCave):
            c.item = Item.WOOD_SWORD

    # Collect pools from the current game world state
    item_pool = _collect_item_pool(game_world, config)
    location_pool = collect_item_locations(game_world, config)
    all_shuffled_locations = list(location_pool)  # snapshot before pool is mutated

    assert len(item_pool) == len(location_pool), (
        f"Pool size mismatch: {len(item_pool)} items vs {len(location_pool)} locations"
    )

    # Validate constraints before mutating anything
    _validate_constraints(item_pool, location_pool, constraints)

    # Clear all shuffled locations so the validator sees empty slots
    for loc in location_pool:
        _clear_location(game_world, loc)

    # Pre-place forced items (returns False if layout is impossible)
    if not _pre_place_forced_items(game_world, item_pool, location_pool, constraints, rng):
        return False

    # Compute self-blocking constraints: rooms where an item can't go because
    # collecting it from that room requires the item itself to be in inventory.
    self_blocking = compute_self_blocking_locations(game_world, location_pool)

    # Track which locations from location_pool have been filled.
    # Pre-placed locations were removed from location_pool by _pre_place_forced_items
    # but are already filled — seed them into the set so the final assert counts them.
    filled: set[Location] = set(all_shuffled_locations) - set(location_pool)

    # Assumed fill loop
    rng.shuffle(item_pool)

    # Cache reachable_without results across outer iterations.
    # A cache entry is valid as long as the item pool hasn't changed (i.e. no
    # placement has occurred). The cache is cleared immediately after each
    # _place_item call so stale entries never survive into the next iteration.
    _reachable_without_cache: dict[tuple[Item, ...], set[Location]] = {}
    fill_start = time.monotonic()
    items_placed = 0
    traversal_count = 0

    while item_pool:
        iter_start = time.monotonic()

        # Build assumed inventory: everything still unplaced
        assumed = Inventory(progressive_items=config.progressive_items)
        for item in item_pool:
            assumed.items.add(item)
        _apply_progressive_upgrades(assumed, item_pool)
        # Triforces are tracked by level, not as generic items.  Credit one
        # assumed level per unplaced triforce so the validator can open L9.
        assumed_triforce_count = item_pool.count(Item.TRIFORCE)
        for lvl in range(1, assumed_triforce_count + 1):
            if lvl not in assumed.levels_with_triforce_obtained:
                assumed.levels_with_triforce_obtained.append(lvl)

        # Find all reachable empty locations under assumed inventory
        reachable = validator.get_reachable_locations(assumed_inventory=assumed)
        traversal_count += 1
        reachable_set = set(reachable)

        empty_reachable = [
            loc for loc in location_pool
            if loc not in filled and loc in reachable_set
        ]

        if not empty_reachable:
            unfilled = [loc for loc in location_pool if loc not in filled]
            logger.info(
                "  assumed_fill STUCK: no empty reachable locations. "
                "%d items unplaced, %d unfilled locations, %d reachable",
                len(item_pool), len(unfilled), len(reachable),
            )
            logger.info("    Unplaced items: %s", [i.name for i in item_pool])
            unreachable_unfilled = [
                loc for loc in unfilled if loc not in reachable_set
            ]
            logger.info("    Unfilled unreachable locations (%d):",
                        len(unreachable_unfilled))
            for loc in unreachable_unfilled:
                if isinstance(loc, DungeonLocation):
                    level = game_world.levels[loc.level_num - 1]
                    room = next(
                        (r for r in level.rooms if r.room_num == loc.room_num),
                        None,
                    )
                    visited = (loc.level_num, loc.room_num) in validator.visited_rooms
                    dirs = validator.room_entry_directions.get(
                        (loc.level_num, loc.room_num), set())
                    if room:
                        logger.info(
                            "      L%d R%s: %s item=%s visited=%s dirs=%s",
                            loc.level_num, f"{loc.room_num:#04x}",
                            room.room_type.name, room.item.name,
                            visited, [d.name for d in dirs],
                        )
                    else:
                        logger.info(
                            "      L%d R%s: (room not in cache) visited=%s dirs=%s",
                            loc.level_num, f"{loc.room_num:#04x}",
                            visited, [d.name for d in dirs],
                        )
                elif isinstance(loc, CaveLocation):
                    logger.info("      Cave %s slot %d",
                                loc.destination.name, loc.position)
            return False

        # Score each item by how many valid locations it has (without itself assumed).
        # Sort ascending (most constrained first) so items with few options are
        # placed before items that can go almost anywhere. Ties are broken randomly
        # by pre-shuffling before the stable sort.
        #
        # Cache reachable_without results by the remaining pool's sorted tuple —
        # using a tuple (not frozenset) to preserve duplicate counts correctly.
        # Items of the same type (e.g. multiple HEART_CONTAINERs) produce the
        # same remaining multiset when removed, so they share one traversal.
        candidates = list(item_pool)
        rng.shuffle(candidates)

        cache_misses = 0
        item_valid_locs: list[tuple[Item, list[Location]]] = []
        for item in candidates:
            remaining_for_check = list(item_pool)
            remaining_for_check.remove(item)
            cache_key = tuple(sorted(remaining_for_check, key=lambda i: i.value))

            if cache_key not in _reachable_without_cache:
                assumed_without = Inventory(progressive_items=config.progressive_items)
                for other in remaining_for_check:
                    assumed_without.items.add(other)
                _apply_progressive_upgrades(assumed_without, remaining_for_check)
                without_triforce_count = remaining_for_check.count(Item.TRIFORCE)
                for lvl in range(1, without_triforce_count + 1):
                    if lvl not in assumed_without.levels_with_triforce_obtained:
                        assumed_without.levels_with_triforce_obtained.append(lvl)
                rw = validator.get_reachable_locations(assumed_inventory=assumed_without)
                _reachable_without_cache[cache_key] = set(rw)
                cache_misses += 1
                traversal_count += 1

            reachable_without_set = _reachable_without_cache[cache_key]

            valid_locs = [
                loc for loc in empty_reachable
                if loc in reachable_without_set
                and is_item_valid_for_location(item, loc, constraints)
                and loc not in self_blocking.get(item, set())
            ]
            item_valid_locs.append((item, valid_locs))

        # Place the most-constrained item (fewest valid locations, >0)
        item_valid_locs.sort(key=lambda x: len(x[1]) if x[1] else float("inf"))

        placed = False
        for item, valid_locs in item_valid_locs:
            if not valid_locs:
                continue
            loc = rng.choice(valid_locs)
            _place_item(game_world, item, loc)
            _reachable_without_cache.clear()
            item_pool.remove(item)
            filled.add(loc)
            placed = True
            items_placed += 1
            iter_elapsed = time.monotonic() - iter_start
            if iter_elapsed > 0.5:
                logger.info(
                    "  assumed_fill iter %d: placed %s, %.2fs "
                    "(%d candidates, %d cache misses, %d total traversals)",
                    items_placed, item.name, iter_elapsed,
                    len(candidates), cache_misses, traversal_count,
                )
            break

        if not placed:
            logger.info(
                "  assumed_fill PLACEMENT FAIL: no valid location for any item. "
                "%d items placed, %d remaining, %.2fs, %d traversals",
                items_placed, len(item_pool),
                time.monotonic() - fill_start, traversal_count,
            )
            logger.info("    Unplaced items: %s", [i.name for i in item_pool])
            logger.info("    Empty reachable locations (%d):", len(empty_reachable))
            for loc in empty_reachable[:10]:
                if isinstance(loc, DungeonLocation):
                    level = game_world.levels[loc.level_num - 1]
                    room = next(
                        (r for r in level.rooms if r.room_num == loc.room_num),
                        None,
                    )
                    if room:
                        logger.info("      L%d R%s: %s item=%s",
                                    loc.level_num, f"{loc.room_num:#04x}",
                                    room.room_type.name, room.item.name)
                elif isinstance(loc, CaveLocation):
                    logger.info("      Cave %s slot %d",
                                loc.destination.name, loc.position)
            return False

    fill_elapsed = time.monotonic() - fill_start
    logger.info(
        "  assumed_fill complete: %d items in %.2fs, %d traversals",
        items_placed, fill_elapsed, traversal_count,
    )

    # All items placed — verify nothing was left behind
    assert len(item_pool) == 0, f"item_pool not empty after fill: {[i.name for i in item_pool]}"
    unfilled = [loc for loc in all_shuffled_locations if loc not in filled]
    assert len(unfilled) == 0, (
        "unfilled locations after fill: "
        + ", ".join(
            f"L{loc.level_num} R{loc.room_num:#04x}" if isinstance(loc, DungeonLocation)
            else f"{loc.destination.name} pos={loc.position}"
            for loc in unfilled
        )
    )

    # Progressive placement invariant: no higher-tier items in shuffled locations,
    # no base item appearing more times than its chain length.
    if config.progressive_items:
        if not _check_progressive_placement_invariants(game_world, all_shuffled_locations, config):
            return False

    # Final sanity check
    return validator.is_seed_valid()


# ---------------------------------------------------------------------------
# Helper: collect all placed items (for test comparison)
# ---------------------------------------------------------------------------

def _snapshot_locations(game_world: GameWorld, config: GameConfig) -> dict[Location, Item]:
    """Capture the current item at every major-item location."""
    snapshot: dict[Location, Item] = {}
    for loc in collect_item_locations(game_world, config):
        if isinstance(loc, DungeonLocation):
            level = game_world.levels[loc.level_num - 1]
            for room in level.rooms:
                if room.room_num == loc.room_num:
                    snapshot[loc] = room.item
                    break
            else:
                for sr in level.staircase_rooms:
                    if sr.room_num == loc.room_num:
                        snapshot[loc] = sr.item if sr.item is not None else Item.NOTHING
                        break
        else:
            ow = game_world.overworld
            cave_by_dest = {c.destination: c for c in ow.caves}
            c = cave_by_dest[loc.destination]
            match loc.destination:
                case (Destination.WOOD_SWORD_CAVE | Destination.WHITE_SWORD_CAVE
                      | Destination.MAGICAL_SWORD_CAVE | Destination.LETTER_CAVE):
                    assert isinstance(c, ItemCave)
                    snapshot[loc] = c.item
                case Destination.ARMOS_ITEM | Destination.COAST_ITEM:
                    assert isinstance(c, OverworldItem)
                    snapshot[loc] = c.item
                case Destination.TAKE_ANY:
                    assert isinstance(c, TakeAnyCave)
                    snapshot[loc] = c.items[loc.position]
                case _:
                    assert isinstance(c, Shop)
                    snapshot[loc] = c.items[loc.position].item
    return snapshot


def _restore_locations(game_world: GameWorld, snapshot: dict[Location, Item]) -> None:
    """Restore item placements from a snapshot."""
    for loc, item in snapshot.items():
        _place_item(game_world, item, loc)


def randomize_items(game_world: GameWorld, config: GameConfig, rng: Rng) -> None:
    max_attempts = 3
    for attempt in range(max_attempts):
        snapshot = _snapshot_locations(game_world, config)
        success = assumed_fill(game_world, config, rng)
        if success:
            return
        if attempt < max_attempts - 1:
            _restore_locations(game_world, snapshot)
    raise RuntimeError("Randomizer could not produce a valid seed")


def collect_all_placed_items(game_world: GameWorld) -> list[Item]:
    """Return all items currently placed in dungeon rooms and cave locations."""
    items: list[Item] = []
    for level in game_world.levels:
        for room in level.rooms:
            items.append(room.item)
    ow = game_world.overworld
    cave_by_dest = {c.destination: c for c in ow.caves}
    for dest in [Destination.WOOD_SWORD_CAVE, Destination.WHITE_SWORD_CAVE,
                 Destination.MAGICAL_SWORD_CAVE, Destination.LETTER_CAVE]:
        c = cave_by_dest.get(dest)
        if c is not None and isinstance(c, ItemCave):
            items.append(c.item)
    for dest in [Destination.ARMOS_ITEM, Destination.COAST_ITEM]:
        c = cave_by_dest.get(dest)
        if c is not None and isinstance(c, OverworldItem):
            items.append(c.item)
    return items
