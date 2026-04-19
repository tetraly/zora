"""
Validator tests: verify the GameValidator correctly identifies beatable and
unbeatable seeds using the vanilla ROM as a baseline.
"""
from pathlib import Path
from typing import cast

from zora.data_model import (
    Destination,
    Direction,
    Enemy,
    EnemySpec,
    GameWorld,
    Item,
    ItemCave,
    ItemPosition,
    Room,
    RoomAction,
    RoomType,
    WallSet,
    WallType,
)
from zora.game_validator import DungeonLocation, GameValidator, Location
from zora.inventory import Inventory
from zora.parser import load_bin_files, parse_game_world

TEST_DATA = Path(__file__).parent.parent / "rom_data"


def _make_validator(game_world: GameWorld | None = None, avoid_required_hard_combat: bool = False) -> GameValidator:
    if game_world is None:
        bins = load_bin_files(TEST_DATA)
        game_world = parse_game_world(bins)
    return GameValidator(game_world, avoid_required_hard_combat)


def test_vanilla_rom_is_valid():
    """Vanilla ROM must pass validation."""
    assert _make_validator().is_seed_valid()


def test_missing_wood_sword_is_invalid():
    """Removing the wood sword from its cave makes the seed invalid (no starting sword)."""
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    cave_by_dest = {c.destination: c for c in gw.overworld.caves}
    wood_sword = cave_by_dest[Destination.WOOD_SWORD_CAVE]
    assert isinstance(wood_sword, ItemCave)
    wood_sword.item = Item.NOTHING
    assert not _make_validator(gw).is_seed_valid()


def test_missing_recorder_is_invalid():
    """Recorder is required to warp to level 7. Removing it makes the seed invalid."""
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    # Find and clear the recorder from whichever dungeon room holds it
    for level in gw.levels:
        for room in level.rooms:
            if room.item == Item.RECORDER:
                room.item = Item.NOTHING
    for level in gw.levels:
        for sr in level.staircase_rooms:
            if sr.item == Item.RECORDER:
                sr.item = Item.NOTHING
    assert not _make_validator(gw).is_seed_valid()


def test_get_reachable_locations_vanilla():
    """Vanilla ROM should reach all 9 dungeon levels."""
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    v = GameValidator(gw, False)
    locations = v.get_reachable_locations()
    level_nums = {loc.level_num for loc in locations if isinstance(loc, DungeonLocation)}
    assert level_nums == {1, 2, 3, 4, 5, 6, 7, 8, 9}


def test_get_reachable_locations_with_full_assumed_inventory():
    """With a full assumed inventory, all levels should be reachable."""
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    v = GameValidator(gw, False)

    assumed = Inventory()
    for item in [Item.RECORDER, Item.RAFT, Item.LADDER, Item.POWER_BRACELET,
                 Item.WOOD_SWORD, Item.RED_CANDLE, Item.BOW, Item.SILVER_ARROWS,
                 Item.BOOK, Item.BAIT, Item.LETTER]:
        assumed.items.add(item)

    locations = v.get_reachable_locations(assumed_inventory=assumed)
    level_nums = {loc.level_num for loc in locations if isinstance(loc, DungeonLocation)}
    assert level_nums == {1, 2, 3, 4, 5, 6, 7, 8, 9}


def _make_blue_wizzrobe_room() -> Room:
    """Build a minimal room with a blue wizzrobe enemy."""
    walls = WallSet(WallType.OPEN_DOOR, WallType.OPEN_DOOR, WallType.OPEN_DOOR, WallType.OPEN_DOOR)
    return Room(
        room_num=0x10,
        room_type=RoomType.PLAIN_ROOM,
        walls=walls,
        enemy_spec=EnemySpec(Enemy.BLUE_WIZZROBE),
        enemy_quantity=3,
        item=Item.NOTHING,
        item_position=ItemPosition.POSITION_A,
        room_action=RoomAction.KILLING_ENEMIES_OPENS_SHUTTERS_AND_DROPS_ITEM,
        is_dark=False,
        boss_cry_1=False,
        boss_cry_2=False,
        movable_block=False,
        palette_0=0,
        palette_1=0,
    )


def test_avoid_hard_combat_blocks_wizzrobe_without_equipment():
    """With avoid_required_hard_combat ON, blue wizzrobe room requires ring + white sword."""
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    v = GameValidator(gw, avoid_required_hard_combat=True)
    room = _make_blue_wizzrobe_room()

    # With only wood sword and no ring: cannot defeat
    v.inventory.items.add(Item.WOOD_SWORD)
    assert not v._can_defeat_enemies(room)

    # With white sword but no ring: still cannot defeat
    v.inventory.items.add(Item.WHITE_SWORD)
    assert not v._can_defeat_enemies(room)

    # With white sword and blue ring: can defeat
    v.inventory.items.add(Item.BLUE_RING)
    assert v._can_defeat_enemies(room)


def test_avoid_hard_combat_off_allows_wizzrobe_with_sword():
    """With avoid_required_hard_combat OFF, blue wizzrobe room only requires a sword."""
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    v = GameValidator(gw, avoid_required_hard_combat=False)
    room = _make_blue_wizzrobe_room()

    # Wood sword alone is sufficient when flag is off
    v.inventory.items.add(Item.WOOD_SWORD)
    assert v._can_defeat_enemies(room)


# ---------------------------------------------------------------------------
# Progressive inventory upgrade chain tests
# ---------------------------------------------------------------------------

def test_progressive_inventory_sword_chain():
    """Two WOOD_SWORDs → WHITE_SWORD; three → MAGICAL_SWORD."""
    inv = Inventory(progressive_items=True)
    inv.add_item(Item.WOOD_SWORD)
    assert Item.WOOD_SWORD in inv.items
    assert Item.WHITE_SWORD not in inv.items

    inv.add_item(Item.WOOD_SWORD)
    assert Item.WHITE_SWORD in inv.items
    assert Item.MAGICAL_SWORD not in inv.items

    inv.add_item(Item.WOOD_SWORD)
    assert Item.MAGICAL_SWORD in inv.items


def test_progressive_inventory_ring_chain():
    """Two BLUE_RINGs → RED_RING."""
    inv = Inventory(progressive_items=True)
    inv.add_item(Item.BLUE_RING)
    assert Item.RED_RING not in inv.items

    inv.add_item(Item.BLUE_RING)
    assert Item.RED_RING in inv.items


def test_progressive_inventory_arrow_chain():
    """Two WOOD_ARROWS → SILVER_ARROWS."""
    inv = Inventory(progressive_items=True)
    inv.add_item(Item.WOOD_ARROWS)
    assert Item.SILVER_ARROWS not in inv.items

    inv.add_item(Item.WOOD_ARROWS)
    assert Item.SILVER_ARROWS in inv.items


def test_progressive_inventory_candle_chain():
    """Two BLUE_CANDLEs → RED_CANDLE."""
    inv = Inventory(progressive_items=True)
    inv.add_item(Item.BLUE_CANDLE)
    assert Item.RED_CANDLE not in inv.items

    inv.add_item(Item.BLUE_CANDLE)
    assert Item.RED_CANDLE in inv.items


def test_non_progressive_inventory_no_upgrades():
    """Without progressive_items, duplicate items do not trigger upgrade chains."""
    inv = Inventory(progressive_items=False)
    inv.add_item(Item.WOOD_SWORD)
    inv.add_item(Item.WOOD_SWORD)
    assert Item.WHITE_SWORD not in inv.items
    assert Item.MAGICAL_SWORD not in inv.items

    inv2 = Inventory(progressive_items=False)
    inv2.add_item(Item.BLUE_RING)
    inv2.add_item(Item.BLUE_RING)
    assert Item.RED_RING not in inv2.items


# ---------------------------------------------------------------------------
# Progressive placement invariant tests
# ---------------------------------------------------------------------------

from zora.game_config import GameConfig  # noqa: E402
from zora.item_randomizer import _check_progressive_placement_invariants  # noqa: E402

_DEFAULT_CONFIG = GameConfig()


def test_progressive_placement_rejects_higher_tier_items():
    """Invariant check must fail if a shuffled location holds a higher-tier item."""
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    room = gw.levels[0].rooms[0]
    room.item = Item.WHITE_SWORD
    loc = DungeonLocation(level_num=1, room_num=room.room_num)
    assert not _check_progressive_placement_invariants(gw, [loc], _DEFAULT_CONFIG), \
        "WHITE_SWORD in shuffled location should fail invariant"

    bins2 = load_bin_files(TEST_DATA)
    gw2 = parse_game_world(bins2)
    room2 = gw2.levels[0].rooms[0]
    room2.item = Item.RED_RING
    loc2 = DungeonLocation(level_num=1, room_num=room2.room_num)
    assert not _check_progressive_placement_invariants(gw2, [loc2], _DEFAULT_CONFIG), \
        "RED_RING in shuffled location should fail invariant"


def test_progressive_placement_rejects_too_many_base_items():
    """Invariant check must fail if a base item appears more times than its chain length."""
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    # Place WOOD_SWORD in 4 dungeon rooms (max is 3)
    locs = []
    for i in range(4):
        room = gw.levels[0].rooms[i]
        room.item = Item.WOOD_SWORD
        locs.append(DungeonLocation(level_num=1, room_num=room.room_num))
    assert not _check_progressive_placement_invariants(gw, cast(list[Location], locs), _DEFAULT_CONFIG), \
        "4x WOOD_SWORD in shuffled locations should exceed max-count invariant"


def test_progressive_placement_passes_for_valid_pool():
    """Invariant check must pass when shuffled locations hold only valid base items."""
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    rooms = gw.levels[0].rooms
    rooms[0].item = Item.WOOD_SWORD
    rooms[1].item = Item.WOOD_SWORD
    rooms[2].item = Item.WOOD_SWORD
    rooms[3].item = Item.BLUE_RING
    rooms[4].item = Item.BLUE_RING
    locs = [DungeonLocation(level_num=1, room_num=rooms[i].room_num) for i in range(5)]
    assert _check_progressive_placement_invariants(gw, cast(list[Location], locs), _DEFAULT_CONFIG), \
        "3x WOOD_SWORD + 2x BLUE_RING should pass invariant"


def test_shutter_door_blocked_by_push_block_without_movable_block():
    """Shutter doors with PUSHING_BLOCK_OPENS_SHUTTERS but no movable block are impassable."""
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    v = _make_validator(gw)
    v.inventory.items.add(Item.WOOD_SWORD)

    walls = WallSet(WallType.OPEN_DOOR, WallType.SHUTTER_DOOR, WallType.OPEN_DOOR, WallType.OPEN_DOOR)
    room = Room(
        room_num=0x10,
        room_type=RoomType.PLAIN_ROOM,
        walls=walls,
        enemy_spec=EnemySpec(Enemy.RED_DARKNUT),
        enemy_quantity=3,
        item=Item.NOTHING,
        item_position=ItemPosition.POSITION_A,
        room_action=RoomAction.PUSHING_BLOCK_OPENS_SHUTTERS,
        is_dark=False,
        boss_cry_1=False,
        boss_cry_2=False,
        movable_block=False,
        palette_0=0,
        palette_1=0,
    )
    assert not v._can_move(Direction.WEST, Direction.EAST, 1, 0x10, room)


def test_shutter_door_blocked_by_old_man_with_kill_action():
    """Shutter doors with an unkillable NPC and a kill-based room action are impassable."""
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    v = _make_validator(gw)
    v.inventory.items.add(Item.WOOD_SWORD)

    walls = WallSet(WallType.OPEN_DOOR, WallType.SHUTTER_DOOR, WallType.OPEN_DOOR, WallType.OPEN_DOOR)
    room = Room(
        room_num=0x10,
        room_type=RoomType.PLAIN_ROOM,
        walls=walls,
        enemy_spec=EnemySpec(Enemy.OLD_MAN),
        enemy_quantity=1,
        item=Item.NOTHING,
        item_position=ItemPosition.POSITION_A,
        room_action=RoomAction.KILLING_ENEMIES_OPENS_SHUTTERS,
        is_dark=False,
        boss_cry_1=False,
        boss_cry_2=False,
        movable_block=False,
        palette_0=0,
        palette_1=0,
    )
    assert not v._can_move(Direction.WEST, Direction.EAST, 1, 0x10, room)


def test_shutter_door_allowed_for_killable_enemies():
    """Shutter doors with killable enemies and a kill action are passable."""
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    v = _make_validator(gw)
    v.inventory.items.add(Item.WOOD_SWORD)

    walls = WallSet(WallType.OPEN_DOOR, WallType.SHUTTER_DOOR, WallType.OPEN_DOOR, WallType.OPEN_DOOR)
    room = Room(
        room_num=0x10,
        room_type=RoomType.PLAIN_ROOM,
        walls=walls,
        enemy_spec=EnemySpec(Enemy.RED_DARKNUT),
        enemy_quantity=3,
        item=Item.NOTHING,
        item_position=ItemPosition.POSITION_A,
        room_action=RoomAction.KILLING_ENEMIES_OPENS_SHUTTERS,
        is_dark=False,
        boss_cry_1=False,
        boss_cry_2=False,
        movable_block=False,
        palette_0=0,
        palette_1=0,
    )
    assert v._can_move(Direction.WEST, Direction.EAST, 1, 0x10, room)


def test_progressive_placement_only_checks_shuffled_locations():
    """Non-shuffled locations (not in pool) must not affect the invariant check."""
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    # Put WHITE_SWORD in a room but don't include it in the location pool
    gw.levels[0].rooms[0].item = Item.WHITE_SWORD
    # Only report room 1 as shuffled — room 0's WHITE_SWORD should be ignored
    room1 = gw.levels[0].rooms[1]
    room1.item = Item.WOOD_SWORD
    loc = DungeonLocation(level_num=1, room_num=room1.room_num)
    assert _check_progressive_placement_invariants(gw, [loc], _DEFAULT_CONFIG), \
        "WHITE_SWORD outside the shuffled pool should not trigger the invariant"
