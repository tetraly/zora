"""
GameValidator: reachability engine for Zelda 1 randomizer seeds.

Simulates what a player can collect given the current GameWorld state and
determines whether a seed is beatable (all itemdicts obtainable, kidnapped rescued).

Does NOT mutate GameWorld. All mutable state lives on this object.
"""
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

from zora.data_model import (
    Destination,
    Direction,
    Enemy,
    EnemySpec,
    EntranceType,
    GameWorld,
    Item,
    ItemCave,
    Level,
    OverworldItem,
    Room,
    RoomAction,
    RoomType,
    Screen,
    Shop,
    StaircaseRoom,
    TakeAnyCave,
    WallType,
)
from zora.inventory import Inventory

# Room types where mobility may be restricted without a ladder.
# Maps room type → valid travel directions when player has no ladder.
_LADDER_BLOCK_VALID_DIRS: dict[RoomType, list[Direction]] = {
    RoomType.CIRCLE_MOAT_ROOM:    [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST],
    RoomType.DOUBLE_MOAT_ROOM:    [Direction.EAST, Direction.WEST],
    RoomType.HORIZONTAL_MOAT_ROOM:[Direction.EAST, Direction.SOUTH, Direction.WEST],
    RoomType.VERTICAL_MOAT_ROOM:  [Direction.SOUTH, Direction.WEST, Direction.NORTH],
    RoomType.CHEVY_ROOM:          [],
}

# Room types with unconditionally constrained movement (chutes, T-room).
_CONSTRAINED_VALID_DIRS: dict[RoomType, list[Direction]] = {
    RoomType.HORIZONTAL_CHUTE_ROOM: [Direction.EAST, Direction.WEST],
    RoomType.VERTICAL_CHUTE_ROOM:   [Direction.NORTH, Direction.SOUTH],
    RoomType.T_ROOM:                [Direction.WEST, Direction.NORTH, Direction.EAST],
}

_SWORD_OR_WAND_ITEMS = (Item.WOOD_SWORD, Item.WHITE_SWORD, Item.MAGICAL_SWORD, Item.WAND)

# Room types where item accessibility depends on entry direction.
# On re-entry from a different direction, item collection must be re-attempted.
_DIRECTION_SENSITIVE_ROOM_TYPES: frozenset[RoomType] = frozenset(
    _LADDER_BLOCK_VALID_DIRS.keys() | _CONSTRAINED_VALID_DIRS.keys()
)


# ---------------------------------------------------------------------------
# Location types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DungeonLocation:
    level_num: int
    room_num: int


@dataclass(frozen=True)
class CaveLocation:
    destination: Destination
    position: int  # 0-indexed slot within the cave


Location = DungeonLocation | CaveLocation


class GameValidator:
    def __init__(self, game_world: GameWorld, avoid_required_hard_combat: bool,
                 progressive_items: bool = False) -> None:
        self.game_world = game_world
        self.avoid_required_hard_combat = avoid_required_hard_combat
        self.progressive_items = progressive_items
        self.inventory = Inventory(progressive_items=progressive_items)
        self.visited_rooms: set[tuple[int, int]] = set()  # (level_num, room_num)
        self.items_collected_rooms: set[tuple[int, int]] = set()  # rooms whose item has been collected
        self.room_entry_directions: dict[tuple[int, int], set[Direction]] = {}  # directions room was entered from
        # Room lookup caches: built once, keyed by (level_num, room_num)
        self._room_cache: dict[tuple[int, int], Room | None ] = {
            (level.level_num, room.room_num): room
            for level in game_world.levels
            for room in level.rooms
        }
        self._staircase_cache: dict[tuple[int, int], StaircaseRoom | None] = {
            (level.level_num, sr.room_num): sr
            for level in game_world.levels
            for sr in level.staircase_rooms
        }

    # -------------------------------------------------------------------------
    # State management
    # -------------------------------------------------------------------------

    def _reset(self) -> None:
        self.inventory.reset()
        self.visited_rooms.clear()
        self.items_collected_rooms.clear()
        self.room_entry_directions.clear()

    # -------------------------------------------------------------------------
    # GameWorld accessors
    # -------------------------------------------------------------------------

    def _get_level(self, level_num: int) -> Level:
        return self.game_world.levels[level_num - 1]

    def _get_room(self, level_num: int, room_num: int) -> Room | None:
        return self._room_cache.get((level_num, room_num))

    def _get_staircase_room(self, level_num: int, room_num: int) -> StaircaseRoom | None:
        return self._staircase_cache.get((level_num, room_num))

    def _get_screen(self, screen_num: int) -> Screen:
        return self.game_world.overworld.screens[screen_num]

    # -------------------------------------------------------------------------
    # Overworld traversal
    # -------------------------------------------------------------------------

    def _can_access_screen(self, screen: Screen) -> bool:
        match screen.entrance_type:
            case EntranceType.NONE:
                return False
            case EntranceType.OPEN:
                return True
            case EntranceType.BOMB:
                return self.inventory.has_sword_or_wand()
            case EntranceType.CANDLE:
                return self.inventory.has_candle()
            case EntranceType.RECORDER:
                return self.inventory.has(Item.RECORDER)
            case EntranceType.RAFT:
                return self.inventory.has(Item.RAFT)
            case EntranceType.RAFT_AND_BOMB:
                return self.inventory.has(Item.RAFT) and self.inventory.has_sword_or_wand()
            case EntranceType.LADDER:
                return self.inventory.has(Item.LADDER)
            case EntranceType.LADDER_AND_BOMB:
                return self.inventory.has(Item.LADDER) and self.inventory.has_sword_or_wand()
            case EntranceType.POWER_BRACELET:
                return self.inventory.has(Item.POWER_BRACELET)
            case EntranceType.POWER_BRACELET_AND_BOMB:
                return self.inventory.has(Item.POWER_BRACELET) and self.inventory.has_sword_or_wand()
            case EntranceType.LOST_HILLS_HINT:
                return self.inventory.has(Item.LOST_HILLS_HINT_VIRTUAL_ITEM)
            case EntranceType.DEAD_WOODS_HINT:
                return self.inventory.has(Item.DEAD_WOODS_HINT_VIRTUAL_ITEM)
            case _:
                return False

    def _get_accessible_destinations(self) -> list[Destination]:
        seen: set[Destination] = set()
        destinations: list[Destination] = []

        for screen in self.game_world.overworld.screens:
            if not self._can_access_screen(screen):
                continue
            dest = screen.destination
            if dest == Destination.NONE:
                continue

            # Side effects: hint screens grant virtual items regardless of dedup
            if dest == Destination.LOST_HILLS_HINT:
                self.inventory.add_item(Item.LOST_HILLS_HINT_VIRTUAL_ITEM)
            if dest == Destination.DEAD_WOODS_HINT:
                self.inventory.add_item(Item.DEAD_WOODS_HINT_VIRTUAL_ITEM)

            if dest not in seen:
                seen.add(dest)
                destinations.append(dest)

        # Armos item: no overworld screen references ARMOS_ITEM in vanilla —
        # push any armos statue (no items required). Always accessible.
        if Destination.ARMOS_ITEM not in seen:
            seen.add(Destination.ARMOS_ITEM)
            destinations.append(Destination.ARMOS_ITEM)

        # Coast item: screen 0x5F has Destination.NONE in the data model
        # (it's a special-cased location requiring Ladder). Add it explicitly
        # when Ladder is available.
        if Destination.COAST_ITEM not in seen and self.inventory.has(Item.LADDER):
            seen.add(Destination.COAST_ITEM)
            destinations.append(Destination.COAST_ITEM)

        return destinations

    # -------------------------------------------------------------------------
    # Cave processing
    # -------------------------------------------------------------------------

    def _can_get_items_from_cave(self, destination: Destination) -> bool:
        ow = self.game_world.overworld
        if destination == Destination.WHITE_SWORD_CAVE:
            cave = ow.get_cave(Destination.WHITE_SWORD_CAVE, ItemCave)
            if cave is not None and self.inventory.get_heart_count() < cave.heart_requirement:
                return False
        if destination == Destination.MAGICAL_SWORD_CAVE:
            cave = ow.get_cave(Destination.MAGICAL_SWORD_CAVE, ItemCave)
            if cave is not None and self.inventory.get_heart_count() < cave.heart_requirement:
                return False
        if destination == Destination.POTION_SHOP and not self.inventory.has(Item.LETTER):
            return False
        if destination == Destination.COAST_ITEM and not self.inventory.has(Item.LADDER):
            return False
        return True

    def _get_cave_items(self, destination: Destination) -> list[Item]:
        ow = self.game_world.overworld
        match destination:
            case Destination.WOOD_SWORD_CAVE | Destination.WHITE_SWORD_CAVE \
               | Destination.MAGICAL_SWORD_CAVE | Destination.LETTER_CAVE:
                cave = ow.get_cave(destination, ItemCave)
                assert cave is not None, f"Missing ItemCave for {destination}"
                return [cave.item]
            case Destination.ARMOS_ITEM | Destination.COAST_ITEM:
                ow_item = ow.get_cave(destination, OverworldItem)
                assert ow_item is not None, f"Missing OverworldItem for {destination}"
                return [ow_item.item]
            case Destination.TAKE_ANY:
                take_any = ow.get_cave(destination, TakeAnyCave)
                assert take_any is not None, f"Missing TakeAnyCave for {destination}"
                return list(take_any.items)
            case Destination.SHOP_1 | Destination.SHOP_2 | Destination.SHOP_3 \
               | Destination.SHOP_4 | Destination.POTION_SHOP:
                shop = ow.get_cave(destination, Shop)
                assert shop is not None, f"Missing Shop for {destination}"
                return [slot.item for slot in shop.items]
            case Destination.DOOR_REPAIR | Destination.MONEY_MAKING_GAME | \
                 Destination.ANY_ROAD | Destination.SMALL_SECRET | \
                 Destination.MEDIUM_SECRET | Destination.LARGE_SECRET | \
                 Destination.HINT_SHOP_1 | Destination.HINT_SHOP_2 | \
                 Destination.LOST_HILLS_HINT | Destination.DEAD_WOODS_HINT:
                return []
            case _:
                raise ValueError(f"Unknown Cave Destination: {destination!r}")


    # -------------------------------------------------------------------------
    # Dungeon traversal
    # -------------------------------------------------------------------------

    def _contains_enemy_type(self, enemy_spec: EnemySpec, enemy_list: list[Enemy]) -> bool:
        return any(e in enemy_list for e in enemy_spec.actual_enemies)

    def _room_has_only_zero_hp_enemies(self, actual_enemies: list[Enemy]) -> bool:
        zero_hp = {Enemy.GEL_1, Enemy.GEL_2, Enemy.BLUE_KEESE, Enemy.RED_KEESE, Enemy.DARK_KEESE}
        return len(actual_enemies) > 0 and all(e in zero_hp for e in actual_enemies)

    def _can_defeat_enemies(self, room: Room) -> bool:
        spec = room.enemy_spec
        enemy = spec.enemy

        if enemy.is_unkillable():
            return True

        actual = spec.actual_enemies

        if enemy == Enemy.THE_BEAST and not self.inventory.has_bow_silver_arrows_and_sword():
            return False
        if enemy.is_digdogger() and not self.inventory.has_recorder_and_reusable_weapon():
            return False
        if enemy.is_gohma() and not self.inventory.has_bow_and_arrows():
            return False
        if (self._contains_enemy_type(spec, [Enemy.RED_WIZZROBE, Enemy.BLUE_WIZZROBE])
                and not self.inventory.has_sword()):
            return False
        if enemy.is_gleeok_or_patra() and not self.inventory.has_sword_or_wand():
            return False
        if self._room_has_only_zero_hp_enemies(actual) and not self.inventory.has_reusable_weapon_or_boomerang():
            return False
        if enemy == Enemy.HUNGRY_GORIYA and not self.inventory.has(Item.BAIT):
            return False
        if (self._contains_enemy_type(spec, [Enemy.POLS_VOICE])
                and not (self.inventory.has_sword_or_wand() or self.inventory.has_bow_and_arrows())):
            return False
        if (self.avoid_required_hard_combat
                and self._contains_enemy_type(spec, [
                    Enemy.GLEEOK_1, Enemy.GLEEOK_2, Enemy.GLEEOK_3, Enemy.GLEEOK_4,
                    Enemy.PATRA_1, Enemy.PATRA_2, Enemy.BLUE_DARKNUT, Enemy.BLUE_WIZZROBE,
                ])
                and not (self.inventory.has_ring() and self.inventory.has(Item.WHITE_SWORD))):
            return False

        return self.inventory.has_reusable_weapon()

    def _get_item_xy(self, level_num: int, room: Room) -> tuple[int, int]:
        """Return (X, Y) tile coordinates of the room's item position.

        Unpacks the packed 0xXY byte from the level's item_position_table:
          high nibble = X tile coordinate
          low nibble  = Y tile coordinate
        """
        level = self._get_level(level_num)
        packed = level.item_position_table[room.item_position]
        return (packed >> 4) & 0x0F, packed & 0x0F

    def _can_get_room_item(self, entry_direction: Direction, room: Room,
                           level_num: int) -> bool:
        rt = room.room_type
        if (room.room_action == RoomAction.KILLING_ENEMIES_OPENS_SHUTTERS_AND_DROPS_ITEM
                and not self._can_defeat_enemies(room)):
            return False
        item_x, item_y = self._get_item_xy(level_num, room)
        if rt == RoomType.HORIZONTAL_CHUTE_ROOM:
            # Walls span rows 8 and a, dividing the room into three zones:
            #   top zone    (Y in {6, 7}): accessible only from NORTH door
            #   middle zone (Y == 9):      accessible only from EAST or WEST door
            #   bottom zone (Y in {b, c}): accessible only from SOUTH door
            if item_y in (0x6, 0x7):
                return entry_direction == Direction.NORTH
            if item_y == 0x9:
                return entry_direction in (Direction.EAST, Direction.WEST)
            if item_y in (0xB, 0xC):
                return entry_direction == Direction.SOUTH
            raise ValueError(
                f"Level {level_num} room {room.room_num:#04x}: "
                f"HORIZONTAL_CHUTE_ROOM item Y={item_y:#x} is not in a valid zone "
                f"(expected 6-7, 9, or b-c) — item is on a wall or obstacle"
            )
        if rt == RoomType.VERTICAL_CHUTE_ROOM:
            # Walls span columns 6 and 9, dividing the room into three zones:
            #   left zone   (X in {2..5}): accessible only from WEST door
            #   middle zone (X in {7, 8}): accessible only from NORTH or SOUTH door
            #   right zone  (X in {a..d}): accessible only from EAST door
            if 0x2 <= item_x <= 0x5:
                return entry_direction == Direction.WEST
            if item_x in (0x7, 0x8):
                return entry_direction in (Direction.NORTH, Direction.SOUTH)
            if 0xA <= item_x <= 0xD:
                return entry_direction == Direction.EAST
            raise ValueError(
                f"Level {level_num} room {room.room_num:#04x}: "
                f"VERTICAL_CHUTE_ROOM item X={item_x:#x} is not in a valid zone "
                f"(expected 2-5, 7-8, or a-d) — item is on a wall or obstacle"
            )
        if rt == RoomType.T_ROOM:
            # The T-room has a stem extending south from the horizontal bar.
            # Two zones based on item position:
            #   bar zone  (X==2, X==d, or Y==6):        accessible from WEST, NORTH, or EAST
            #   stem zone (X in {5..a} AND Y in {8..c}): accessible only from SOUTH
            if item_x == 0x2 or item_x == 0xD or item_y == 0x6:
                return entry_direction in (Direction.WEST, Direction.NORTH, Direction.EAST)
            if 0x5 <= item_x <= 0xA and 0x8 <= item_y <= 0xC:
                return entry_direction == Direction.SOUTH
            raise ValueError(
                f"Level {level_num} room {room.room_num:#04x}: "
                f"T_ROOM item X={item_x:#x} Y={item_y:#x} is not in a valid zone "
                f"(expected X==2, X==d, Y==6, or X in 5-a with Y in 8-c) — item is on a wall or obstacle"
            )
        if rt == RoomType.DOUBLE_MOAT_ROOM and not self.inventory.has(Item.LADDER):
            # Walls span columns 6 and 9, dividing the room into three zones:
            #   left zone   (X in {2..5}): accessible only from WEST door
            #   middle zone (X in {7, 8}): accessible only from NORTH or SOUTH door
            #   right zone  (X in {a..d}): accessible only from EAST door
            if item_y == 0x06 and entry_direction == Direction.NORTH:
                    return True
            if item_y in (0x08, 0x09, 0x0A) and entry_direction in (Direction.EAST, Direction.WEST):
                    return True
            if item_y == 0x0C and entry_direction == Direction.SOUTH:
                    return True
            return False
        if rt == RoomType.HORIZONTAL_MOAT_ROOM and not self.inventory.has(Item.LADDER):
            # Water spans row 8; two zones:
            #   top zone    (Y in {6, 7}): accessible only from NORTH door
            #   bottom zone (Y in {9..c}): accessible from WEST, SOUTH, or EAST door
            if item_y in (0x6, 0x7) and entry_direction == Direction.NORTH:
                    return True
            if 0x9 <= item_y <= 0xC and entry_direction in (Direction.WEST, Direction.SOUTH, Direction.EAST):
                    return True
            return False
        if rt == RoomType.VERTICAL_MOAT_ROOM and not self.inventory.has(Item.LADDER):
            # Water spans column A; two zones:
            #   left zone  (X in {2..9}): accessible from WEST, NORTH, or SOUTH door
            #   right zone (X in {b..d}): accessible only from EAST door
            if 0x2 <= item_x <= 0x9:
                if entry_direction in (Direction.WEST, Direction.NORTH, Direction.SOUTH):
                    return True
            elif 0xB <= item_x <= 0xD and entry_direction == Direction.EAST:
                    return True
            else:
                return False
        if rt == RoomType.CHEVY_ROOM:
            if self.inventory.has(Item.LADDER):
                return True
            if item_x == 0xC and item_y == 0x9:
                return entry_direction == Direction.EAST
            return False
        if rt == RoomType.CIRCLE_MOAT_ROOM and not self.inventory.has(Item.LADDER):
            # Item inside the moat ring (X in {4..b}, Y in {8..a}) requires ladder.
            # Item outside the ring is reachable without ladder regardless of entry door.
            if 0x4 <= item_x <= 0xB and 0x8 <= item_y <= 0xA:
                return False
        if rt in _LADDER_BLOCK_VALID_DIRS and not self.inventory.has(Item.LADDER):
            return False
        return True

    def _is_item_collectible_from_any_direction(
        self, level_num: int, room: Room,
        directions: set[Direction],
    ) -> bool:
        """Check if the item at this room's position could be collected from
        any of the given entry directions."""
        if room.room_type not in _DIRECTION_SENSITIVE_ROOM_TYPES:
            return True
        for d in directions:
            if self._can_get_room_item(d, room, level_num):
                return True
        return False

    def _has_stairway(self, room: Room) -> bool:
        if room.room_type.has_open_staircase():
            return True
        # Shutter doors mean the pushblock opens shutters, not a stairway
        for wall in (room.walls.north, room.walls.east, room.walls.south, room.walls.west):
            if wall == WallType.SHUTTER_DOOR:
                return False
        return room.room_type.can_have_push_block() and room.movable_block

    def _is_path_unconditionally_obstructed(self, room_type: RoomType,
                                             from_dir: Direction, to_dir: Direction) -> bool:
        # STAIRCASE entry means the player arrived via staircase — never obstructed
        if from_dir == Direction.STAIRCASE:
            return False
        if room_type in _CONSTRAINED_VALID_DIRS:
            valid = _CONSTRAINED_VALID_DIRS[room_type]
            if from_dir not in valid or to_dir not in valid:
                return True
        return False

    def _is_path_obstructed_by_water(self, room_type: RoomType,
                                      from_dir: Direction, to_dir: Direction,
                                      has_ladder: bool) -> bool:
        # STAIRCASE entry means the player arrived via staircase — never obstructed
        if from_dir == Direction.STAIRCASE:
            return False
        if not has_ladder and room_type in _LADDER_BLOCK_VALID_DIRS:
            valid = _LADDER_BLOCK_VALID_DIRS[room_type]
            if from_dir not in valid or to_dir not in valid:
                return True
        return False

    def _can_move(self, entry_direction: Direction, exit_direction: Direction,
                  level_num: int, room_num: int, room: Room) -> bool:
        has_ladder = self.inventory.has(Item.LADDER)

        if (self._is_path_unconditionally_obstructed(room.room_type, entry_direction, exit_direction)
                or self._is_path_obstructed_by_water(room.room_type, entry_direction, exit_direction, has_ladder)):
            return False

        if (exit_direction == Direction.NORTH
                and room.enemy_spec.enemy == Enemy.HUNGRY_GORIYA
                and not self.inventory.has(Item.BAIT)):
            return False

        wall = room.walls[exit_direction]

        if wall == WallType.SHUTTER_DOOR:
            if room.room_action == RoomAction.TRIFORCE_OF_POWER_OPENS_SHUTTERS:
                return self.inventory.has(Item.BEAST_DEFEATED_VIRTUAL_ITEM)
            if room.room_action == RoomAction.PUSHING_BLOCK_OPENS_SHUTTERS and not room.movable_block:
                assert False, (
                    f"L{level_num} R{room_num:#04x}: PUSHING_BLOCK_OPENS_SHUTTERS "
                    f"but no movable block — shuffler should not produce this"
                )
            enemy = room.enemy_spec.enemy
            if (enemy in (
                        Enemy.OLD_MAN, Enemy.OLD_MAN_2, Enemy.OLD_MAN_3,
                        Enemy.OLD_MAN_4, Enemy.OLD_MAN_5, Enemy.OLD_MAN_6,
                        Enemy.BOMB_UPGRADER,
                    )
                    and room.room_action in (
                        RoomAction.KILLING_ENEMIES_OPENS_SHUTTERS,
                        RoomAction.KILLING_ENEMIES_OPENS_SHUTTERS_AND_DROPS_ITEM,
                        RoomAction.DEFEATING_NPC_OPENS_SHUTTERS,
                    )):
                assert False, (
                    f"L{level_num} R{room_num:#04x}: NPC {enemy.name} with shutter "
                    f"doors and room_action {room.room_action.name} — "
                    f"shuffler should not produce this"
                )
            if not self._can_defeat_enemies(room):
                return False

        if wall == WallType.SOLID_WALL:
            return False

        if wall in (WallType.LOCKED_DOOR_1, WallType.LOCKED_DOOR_2):
            door_key = (level_num, room_num, exit_direction)
            already_unlocked = door_key in self.inventory.locations_where_keys_were_used
            if not already_unlocked and not self.inventory.has_key():
                return False
            if not already_unlocked:
                self.inventory.use_key(level_num, room_num, exit_direction)

        if wall == WallType.BOMB_HOLE:
            if not self.inventory.has_sword_or_wand():
                return False

        return True

    def _visit_room(self, level_num: int, room_num: int,
                    entry_direction: Direction) -> list[tuple[int, Direction]]:
        if not (0 <= room_num < 0x80):
            return []

        room = self._get_room(level_num, room_num)
        if room is None:
            return []

        tbr: list[tuple[int, Direction]] = []
        loc_key = (level_num, room_num)

        first_visit = loc_key not in self.visited_rooms
        direction_sensitive = room.room_type in _DIRECTION_SENSITIVE_ROOM_TYPES

        if first_visit:
            self.visited_rooms.add(loc_key)

        if loc_key not in self.room_entry_directions:
            self.room_entry_directions[loc_key] = set()
        self.room_entry_directions[loc_key].add(entry_direction)

        if first_visit or (direction_sensitive and loc_key not in self.items_collected_rooms):
            if self._can_get_room_item(entry_direction, room, level_num) and room.item != Item.NOTHING:
                self.inventory.add_item(room.item, loc_key)
                self.items_collected_rooms.add(loc_key)

            enemy = room.enemy_spec.enemy
            if enemy == Enemy.THE_BEAST and self._can_get_room_item(entry_direction, room, level_num):
                self.inventory.add_item(Item.BEAST_DEFEATED_VIRTUAL_ITEM)
            if enemy == Enemy.THE_KIDNAPPED:
                self.inventory.add_item(Item.KIDNAPPED_RESCUED_VIRTUAL_ITEM)

        for exit_dir in (Direction.WEST, Direction.NORTH, Direction.EAST, Direction.SOUTH):
            if self._can_move(entry_direction, exit_dir, level_num, room_num, room):
                tbr.append((room_num + exit_dir.value, Direction(-exit_dir.value)))

        if not self._has_stairway(room):
            return tbr

        level = self._get_level(level_num)
        for staircase_room_num in level.staircase_room_pool:
            sr = self._get_staircase_room(level_num, staircase_room_num)
            if sr is None:
                continue

            if sr.room_type == RoomType.ITEM_STAIRCASE:
                if sr.return_dest == room_num:
                    self.visited_rooms.add((level_num, staircase_room_num))
                    if sr.item is not None and sr.item != Item.NOTHING:
                        self.inventory.add_item(sr.item, (level_num, staircase_room_num))
            else:  # TRANSPORT_STAIRCASE
                left_exit = sr.left_exit
                right_exit = sr.right_exit
                if left_exit is not None and right_exit is not None:
                    if left_exit == room_num and right_exit != room_num:
                        tbr.append((right_exit, Direction.STAIRCASE))
                        break
                    if right_exit == room_num and left_exit != room_num:
                        tbr.append((left_exit, Direction.STAIRCASE))
                        break

        return tbr

    def _process_level(self, level_num: int) -> None:
        level = self._get_level(level_num)
        visited_room_direction_pairs: set[tuple[int, Direction]] = set()
        rooms_to_visit = [(level.entrance_room, level.entrance_direction)]

        while rooms_to_visit:
            room_num, direction = rooms_to_visit.pop()
            if (room_num, direction) in visited_room_direction_pairs:
                continue
            visited_room_direction_pairs.add((room_num, direction))
            new_rooms = self._visit_room(level_num, room_num, direction)
            rooms_to_visit.extend(new_rooms)

    # -------------------------------------------------------------------------
    # Starting sword/wand check
    # -------------------------------------------------------------------------

    def _has_accessible_sword_or_wand(self) -> bool:
        """True if wood sword cave or letter cave is reachable from an Open screen
        and contains a sword or wand."""
        for screen in self.game_world.overworld.screens:
            if screen.entrance_type != EntranceType.OPEN:
                continue
            dest = screen.destination
            if dest not in (Destination.WOOD_SWORD_CAVE, Destination.LETTER_CAVE):
                continue
            for item in self._get_cave_items(dest):
                if item in _SWORD_OR_WAND_ITEMS:
                    return True
        return False

    # -------------------------------------------------------------------------
    # HasAllImportantItems
    # -------------------------------------------------------------------------

    _IMPORTANT_ITEMS = (
        Item.WOOD_SWORD, Item.WHITE_SWORD, Item.MAGICAL_SWORD, Item.BAIT,
        Item.RECORDER, Item.BLUE_CANDLE, Item.RED_CANDLE, Item.WOOD_ARROWS,
        Item.SILVER_ARROWS, Item.BOW, Item.MAGICAL_KEY, Item.RAFT, Item.LADDER,
        Item.WAND, Item.BOOK, Item.BLUE_RING, Item.RED_RING, Item.POWER_BRACELET,
        Item.LETTER, Item.WOOD_BOOMERANG, Item.MAGICAL_BOOMERANG,
        Item.LOST_HILLS_HINT_VIRTUAL_ITEM, Item.DEAD_WOODS_HINT_VIRTUAL_ITEM,
    )

    def _has_all_important_items(self) -> bool:
        return all(self.inventory.has(item) for item in self._IMPORTANT_ITEMS)

    # -------------------------------------------------------------------------
    # Core traversal: get_reachable_locations
    # -------------------------------------------------------------------------

    def get_reachable_locations(
        self,
        assumed_inventory: Inventory | None = None,
    ) -> list[Location]:
        """Run full fixed-point world traversal and return all reachable locations.

        Seeds the inventory with assumed_inventory items before traversal if provided.
        Leaves self.inventory populated with all collected (and assumed) items after
        running — callers may inspect it directly.

        Args:
            assumed_inventory: Items to assume the player already has. If provided,
                these are merged into self.inventory before traversal begins and
                re-applied at the start of each iteration (since assumed items
                represent future finds, not collected ones).

        Returns:
            list of all Location objects (DungeonLocation and CaveLocation) that
            were reachable.
        """
        self._reset()

        # Collect assumed item values so we can re-seed each iteration.
        assumed_items: list[Item] = []
        if assumed_inventory is not None:
            assumed_items = list(assumed_inventory.items)
            # Also carry over assumed keys
            assumed_key_count = assumed_inventory.num_keys
        else:
            assumed_key_count = 0

        # Seed initial progress so the loop runs at least once.
        self.inventory.set_still_making_progress_bit()
        num_iterations = 0
        reachable: list[Location] = []

        while self.inventory.still_making_progress():
            num_iterations += 1
            self.inventory.clear_making_progress_bit()
            self.visited_rooms.clear()
            self.items_collected_rooms.clear()
            # Reset collected keys each iteration; previously-unlocked doors
            # remain in locations_where_keys_were_used (treated as permanently open).
            self.inventory.num_keys = assumed_key_count

            # Re-apply assumed items each iteration (they represent unplaced items
            # the player will eventually have — not yet "collected" from a location).
            for item in assumed_items:
                self.inventory.items.add(item)
            # Assumed triforces are tracked via levels_with_triforce_obtained on the
            # assumed inventory (pre-populated by the caller).  Re-apply them here
            # so L9 remains accessible across iterations.
            if assumed_inventory is not None:
                for lvl in assumed_inventory.levels_with_triforce_obtained:
                    if lvl not in self.inventory.levels_with_triforce_obtained:
                        self.inventory.levels_with_triforce_obtained.append(lvl)

            accessible_destinations = self._get_accessible_destinations()

            for destination in accessible_destinations:
                if destination.is_level:
                    level_num = destination.level_num
                    if level_num == 9 and self.inventory.get_triforce_count() < 8:
                        continue
                    self._process_level(level_num)
                else:
                    if self._can_get_items_from_cave(destination):
                        cave_key_base = destination.value
                        for i, item in enumerate(self._get_cave_items(destination)):
                            self.inventory.add_item(item, (cave_key_base, i))

            if num_iterations > 100:
                break

        # Build location list from visited rooms + reachable caves
        reachable = []
        for (level_num, room_num) in self.visited_rooms:
            room = self._get_room(level_num, room_num)
            if room is not None and room.room_type in _DIRECTION_SENSITIVE_ROOM_TYPES:
                directions = self.room_entry_directions.get((level_num, room_num), set())
                if not self._is_item_collectible_from_any_direction(level_num, room, directions):
                    continue
            reachable.append(DungeonLocation(level_num, room_num))
        # Cave locations: any destination that was processed
        # Re-run accessible destinations to enumerate cave locations reached
        for screen in self.game_world.overworld.screens:
            if not self._can_access_screen(screen):
                continue
            dest = screen.destination
            if dest == Destination.NONE or dest.is_level:
                continue
            if self._can_get_items_from_cave(dest):
                items = self._get_cave_items(dest)
                for i in range(len(items)):
                    reachable.append(CaveLocation(dest, i))
        # Armos item is always accessible (no overworld screen required)
        if self._can_get_items_from_cave(Destination.ARMOS_ITEM):
            reachable.append(CaveLocation(Destination.ARMOS_ITEM, 0))
        # Coast item: screen 0x5F has Destination.NONE in the data model;
        # accessible when Ladder is in inventory (collected or assumed).
        if self._can_get_items_from_cave(Destination.COAST_ITEM):
            reachable.append(CaveLocation(Destination.COAST_ITEM, 0))

        return reachable

    # -------------------------------------------------------------------------
    # Main entry point
    # -------------------------------------------------------------------------

    def _check_no_nothing_drops(self) -> None:
        """Raise if any room has the drop-item action with Item.NOTHING.

        The game engine's "nothing" sentinel (0x03) shares its value with
        MAGICAL_SWORD. The drop code path doesn't check the sentinel, so it
        spawns a phantom Magical Sword.
        """
        for level in self.game_world.levels:
            for room in level.rooms:
                if (room.room_action == RoomAction.KILLING_ENEMIES_OPENS_SHUTTERS_AND_DROPS_ITEM
                        and room.item == Item.NOTHING):
                    raise ValueError(
                        f"L{level.level_num} room 0x{room.room_num:02X}: "
                        f"KILLING_ENEMIES_OPENS_SHUTTERS_AND_DROPS_ITEM with "
                        f"Item.NOTHING — causes phantom Magical Sword drop"
                    )

    def is_seed_valid(self) -> bool:
        self._check_no_nothing_drops()

        # dont_guarantee_starting_sword_or_wand hardcoded False for MVP (always guarantee)
        # TODO: wire to flags_generated.py in future phase
        # if not dont_guarantee_starting_sword_or_wand:
        if not self._has_accessible_sword_or_wand():
            logger.info("is_seed_valid: FAIL — no accessible sword or wand")
            return False

        self.get_reachable_locations(assumed_inventory=None)

        rescued = self.inventory.has(Item.KIDNAPPED_RESCUED_VIRTUAL_ITEM)
        has_all = self._has_all_important_items()
        triforce_count = self.inventory.get_triforce_count()

        if rescued and has_all:
            return True

        self._log_seed_failure(rescued, triforce_count)
        return False

    def _log_seed_failure(self, rescued: bool, triforce_count: int) -> None:
        logger.info("is_seed_valid: FAIL — rescued=%s, triforces=%d/8", rescued, triforce_count)

        missing_items = [
            item for item in self._IMPORTANT_ITEMS
            if not self.inventory.has(item)
        ]
        if missing_items:
            logger.info("  Missing important items: %s",
                        [item.name for item in missing_items])

        if triforce_count < 8:
            obtained = set(self.inventory.levels_with_triforce_obtained)
            missing_levels = [lvl for lvl in range(1, 10) if lvl not in obtained]
            logger.info("  Missing triforces from levels: %s", missing_levels)

        all_missing = list(missing_items)
        if triforce_count < 8:
            all_missing.append(Item.TRIFORCE)
        if not rescued:
            all_missing.append(Item.KIDNAPPED_RESCUED_VIRTUAL_ITEM)

        for item in all_missing:
            self._log_item_placement(item)

    def _log_item_placement(self, item: Item) -> None:
        found = False
        for level in self.game_world.levels:
            for room in level.rooms:
                if room.item != item:
                    continue
                if item == Item.TRIFORCE:
                    obtained = set(self.inventory.levels_with_triforce_obtained)
                    if level.level_num in obtained:
                        continue
                found = True
                loc_key = (level.level_num, room.room_num)
                visited = loc_key in self.visited_rooms
                collected = loc_key in self.items_collected_rooms
                dirs = self.room_entry_directions.get(loc_key, set())
                dir_sensitive = room.room_type in _DIRECTION_SENSITIVE_ROOM_TYPES

                item_x, item_y = self._get_item_xy(level.level_num, room)

                walls = (f"N={room.walls.north.name} E={room.walls.east.name} "
                         f"S={room.walls.south.name} W={room.walls.west.name}")

                logger.info(
                    "  Item %s: L%d R%s %s pos=(%s,%s) %s",
                    item.name, level.level_num, f"{room.room_num:#04x}",
                    room.room_type.name, f"{item_x:#x}", f"{item_y:#x}", walls,
                )

                if not visited:
                    logger.info("    -> Room was NEVER VISITED during traversal")
                elif collected:
                    logger.info("    -> Item was COLLECTED (should not be missing)")
                elif dir_sensitive:
                    dir_names = [d.name for d in dirs]
                    logger.info("    -> Room visited from %s but item NOT collected "
                                "(direction-sensitive room)", dir_names)
                    for d in dirs:
                        can = self._can_get_room_item(d, room, level.level_num)
                        logger.info("       _can_get_room_item(%s) = %s", d.name, can)
                    if room.room_action == RoomAction.KILLING_ENEMIES_OPENS_SHUTTERS_AND_DROPS_ITEM:
                        can_defeat = self._can_defeat_enemies(room)
                        logger.info("       requires enemy defeat, can_defeat=%s",
                                    can_defeat)
                else:
                    logger.info("    -> Room visited but item not collected "
                                "(non-direction-sensitive)")

        if not found:
            for cave in self.game_world.overworld.caves:
                cave_items = self._get_cave_items(cave.destination)
                if item in cave_items:
                    found = True
                    logger.info("  Item %s: cave %s",
                                item.name, cave.destination.name)
                    break

        if not found:
            _PROGRESSIVE_CHAIN: dict[Item, tuple[Item, int]] = {
                Item.MAGICAL_SWORD: (Item.WOOD_SWORD, 3),
                Item.WHITE_SWORD: (Item.WOOD_SWORD, 2),
                Item.RED_RING: (Item.BLUE_RING, 2),
                Item.SILVER_ARROWS: (Item.WOOD_ARROWS, 2),
                Item.RED_CANDLE: (Item.BLUE_CANDLE, 2),
            }
            chain = _PROGRESSIVE_CHAIN.get(item) if self.progressive_items else None
            if chain:
                base_item, needed = chain
                num_collected = 0
                for (lv, rn) in self.items_collected_rooms:
                    r = self._get_room(lv, rn)
                    if r is not None and r.item == base_item:
                        num_collected += 1
                logger.info(
                    "  Item %s: progressive — needs %d×%s, collected %d",
                    item.name, needed, base_item.name, num_collected,
                )
            elif item in (Item.KIDNAPPED_RESCUED_VIRTUAL_ITEM,
                          Item.BEAST_DEFEATED_VIRTUAL_ITEM):
                logger.info("  Item %s: virtual item — enemy not defeated "
                            "during traversal", item.name)
            else:
                logger.info("  Item %s: NOT PLACED in game world (fill failed "
                            "before placing this item)", item.name)


