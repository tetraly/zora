"""The shape stage's and the late gate's figures (shapes-behavior.md, late-gate.md)
and post-shapes batch B1's."""

import statistics
from collections import Counter
from typing import Any

from zora.model import room_grid
from zora.model.enums import Enemy, Item, RoomAction, RoomType, Side, TollOption, WallType
from zora.model.game_world import GameWorld
from zora.model.levels import L9_ENTRY_PERSON_LIST, Level
from zora.model.room_grid import neighbour
from zora.model.rooms import MONSTER_BIT, PERSON_LISTS, Room
from zora_measure.checkpoints.summaries import (
    LEVELS_1_6,
    LEVELS_7_9,
    POOL_ITEMS,
    THREE_LEVEL_CORNER,
    Component,
    Summary,
    _block_levels,
    _dungeon_items,
    _is_blank,
    _level9_person_room,
    _stair_exits,
    _unowned,
    _whole_bomb_upgrade_levels,
)
from zora_measure.checks import level_pieces, own_staircases

# --- per-ROM measures --------------------------------------------------------------

def unowned_count(gw: GameWorld) -> int:
    return sum(len(_unowned(gw, block)) for block in (LEVELS_1_6, LEVELS_7_9))


# Unowned cells per ROM, binned: 1, 2, 3 to 6, 7 or more (SH-GRID-01 has no bound).
UNOWNED_BINS = ("1", "2", "3-6", "7+")


def unowned_bin(gw: GameWorld) -> str:
    count = unowned_count(gw)
    if count > 6:
        return "7+"
    return "3-6" if count >= 3 else str(count)


def corner_unowned(gw: GameWorld) -> bool:
    return any(r.room_num == THREE_LEVEL_CORNER for r in _unowned(gw, LEVELS_7_9))


def unowned_blank(gw: GameWorld) -> tuple[int, int]:
    rooms = _unowned(gw, LEVELS_1_6) + _unowned(gw, LEVELS_7_9)
    return sum(_is_blank(r) for r in rooms), len(rooms)


def level_sizes(gw: GameWorld) -> list[int]:
    return [len(level.room_nums) for level in gw.levels]


def summarize_level1(values: list[list[int]]) -> str:
    sizes = [v[0] for v in values]
    return f"{min(sizes)} / {statistics.mean(sizes):.1f} / {max(sizes)}"


def summarize_later_levels(values: list[list[int]]) -> str:
    return " ".join(f"{statistics.mean(v[i] for v in values):.1f}" for i in range(1, 9))


LEVEL1_SIZES = Summary(summarize_level1, lambda sizes: {"level 1 mean": float(sizes[0])})
LATER_LEVEL_SIZES = Summary(summarize_later_levels,
                            lambda sizes: {f"L{i + 1}": float(sizes[i]) for i in range(1, 9)})


def level1_persons(gw: GameWorld) -> int:
    return sum(room.is_person for room in gw.levels[0].rooms)


def level1_person_lists(gw: GameWorld) -> list[int]:
    return [room.monster_list for room in gw.levels[0].rooms if room.is_person]


PERSON_LIST_CODES = range(0x0B, 0x12)


def summarize_person_lists(values: list[list[int]]) -> str:
    counts = Counter(code for codes in values for code in codes)
    return "/".join(str(counts[code]) for code in PERSON_LIST_CODES)


PERSON_LIST_SUMMARY = Summary(summarize_person_lists, lambda codes: {
    f"${code:02X}": float(codes.count(code)) for code in PERSON_LIST_CODES
})


def absent_items(gw: GameWorld) -> list[bool]:
    present = _dungeon_items(gw)
    return [item not in present for item in POOL_ITEMS]


def summarize_absent(values: list[list[bool]]) -> str:
    shares = [100 * sum(v[i] for v in values) / len(values) for i in range(len(POOL_ITEMS))]
    return f"{min(shares):.1f}-{max(shares):.1f}%"


ABSENT_SUMMARY = Summary(summarize_absent, lambda absent: {
    item.name.lower(): float(flag) for item, flag in zip(POOL_ITEMS, absent, strict=True)
})


def toll_pair(gw: GameWorld) -> tuple[TollOption, TollOption] | None:
    toll = gw.life_or_money_toll
    return (toll.first, toll.second) if toll else None


TOLL_PAIRS = ((TollOption.MAX_BOMBS, TollOption.KEYS), (TollOption.LIFE, TollOption.KEYS),
              (TollOption.MAX_BOMBS, TollOption.MONEY), (TollOption.LIFE, TollOption.MONEY),
              (TollOption.LIFE, TollOption.MAX_BOMBS))


def toll_costs(gw: GameWorld) -> tuple[int | None, int | None]:
    toll = gw.life_or_money_toll
    return (toll.key_cost, toll.money_cost) if toll else (None, None)


def summarize_costs(values: list[tuple[int | None, int | None]]) -> str:
    keys = Counter(k for k, _ in values if k is not None)
    money = [m for _, m in values if m is not None]
    offered = 100 * sum(k is not None for k, _ in values) / len(values)
    money_part = (f"; money {min(money)}-{max(money)}, mean {statistics.mean(money):.1f}"
                  if money else "")
    return f"keys {offered:.1f}%, cost {keys[2]}/{keys[3]}/{keys[4]}" + money_part


KEY_COSTS = (2, 3, 4)


def cost_components(costs: tuple[int | None, int | None]) -> dict[str, Component]:
    key_cost, money_cost = costs
    parts: dict[str, Component] = {"keys offered": float(key_cost is not None)}
    parts.update({f"key cost {n}": float(key_cost == n) for n in KEY_COSTS})
    parts["money mean"] = (float(money_cost or 0), float(money_cost is not None))
    return parts


COST_SUMMARY = Summary(summarize_costs, cost_components)


def bomb_operands(gw: GameWorld) -> tuple[bool, bool, bool]:
    """(branch patched, both operands name $0F-person levels, same level twice)."""
    levels = gw.bomb_upgrade_levels
    if levels is None:
        return False, False, False
    holders = _whole_bomb_upgrade_levels(gw)
    return True, all(level_num in holders for level_num in levels), levels[0] == levels[1]


def summarize_bomb(values: list[tuple[bool, bool, bool]]) -> str:
    return " / ".join(f"{sum(v[i] for v in values)}/{len(values)}" for i in range(3))


BOMB_SUMMARY = Summary(summarize_bomb, lambda flags: {
    name: float(flag) for name, flag in zip(("patched", "$0F levels", "same level"), flags, strict=True)
})


def push_rooms_7_9(gw: GameWorld) -> Counter[int]:
    """Push-block rooms of levels 7-9 by whole layout byte."""
    return Counter(room.layout_byte
                   for level in gw.levels[6:] for room in level.rooms if room.movable_block)


PUSH_EXEMPT_LAYOUTS = (0x5A, 0x60, 0xDA)


def per_thousand_by_code(codes: tuple[int, ...]) -> Summary:
    """Per-ROM Counters of layout bytes, reported per 1,000 ROMs."""
    def text(values: list[Counter[int]]) -> str:
        total: Counter[int] = Counter()
        for counts in values:
            total.update(counts)
        scale = 1000 / len(values)
        return " ".join(f"${code:02X} {total[code] * scale:.0f}" for code in codes)
    return Summary(text, lambda counts: {f"${code:02X}": float(counts[code]) for code in codes})


def per_thousand_by_key(keys: tuple[Any, ...]) -> Summary:
    """Per-ROM Counters with arbitrary keys, reported per 1,000 ROMs."""
    def text(values: list[Counter[Any]]) -> str:
        total: Counter[Any] = Counter()
        for counts in values:
            total.update(counts)
        scale = 1000 / len(values)
        return " ".join(f"{key} {total[key] * scale:.0f}" for key in keys)
    return Summary(text, lambda counts: {str(key): float(counts[key]) for key in keys})


def level9_person_shuttered(gw: GameWorld) -> bool:
    room = _level9_person_room(gw)
    return (room is not None and room.room_action == RoomAction.NONE
            and WallType.SHUTTER_DOOR in (room.walls.north, room.walls.east,
                                          room.walls.south, room.walls.west))


def level9_person_above_entrance(gw: GameWorld) -> bool:
    room = _level9_person_room(gw)
    return room is not None and room.room_num == gw.levels[8].entrance_room - 16


def stair_exits_in_level(gw: GameWorld) -> tuple[int, int]:
    """Staircases (each counted once) whose exits all lie inside a level
    that lists the staircase, none of them that level's entrance."""
    listing: dict[tuple[int, int], list[Level]] = {}
    for block in (LEVELS_1_6, LEVELS_7_9):
        for level in _block_levels(gw, block):
            for stair_num in level.staircase_nums:
                listing.setdefault((block, stair_num), []).append(level)
    good = 0
    for (block, stair_num), levels in listing.items():
        exits = _stair_exits(gw.blocks[block].staircase(stair_num))
        good += any(all(e in level.room_nums and e != level.entrance_room for e in exits)
                    for level in levels)
    return good, len(listing)


# Level 9 in pieces (SH-GRID-07): one piece; two, the small one a single room; two, the small
# one larger; three or more.
LEVEL9_PIECE_KEYS = ("one piece", "two, small one room", "two, small 2+ rooms", "three or more")
# Level 9's (pieces, transport staircases, item cellars) under SH-STAIR-02 and -03.
LEVEL9_STAIRCASE_KEYS = ((1, 6, 2), (2, 7, 2))


def _level9(gw: GameWorld) -> Level:
    return next(level for level in gw.levels if level.level_num == 9)


def level9_pieces(gw: GameWorld) -> str:
    sizes = [len(piece) for piece in level_pieces(_level9(gw))]
    if len(sizes) == 1:
        return LEVEL9_PIECE_KEYS[0]
    if len(sizes) == 2:
        return LEVEL9_PIECE_KEYS[1] if sizes[-1] == 1 else LEVEL9_PIECE_KEYS[2]
    return LEVEL9_PIECE_KEYS[3]


def level9_staircases(gw: GameWorld) -> tuple[int, int, int]:
    level = _level9(gw)
    kinds = Counter(staircase.room_type for staircase in own_staircases(level))
    return (len(level_pieces(level)), kinds[RoomType.TRANSPORT_STAIRCASE], kinds[RoomType.ITEM_STAIRCASE])


def transport_exits_differ(gw: GameWorld) -> tuple[int, int]:
    stairs = [s for block in gw.blocks for s in block.staircases
              if s.room_type == RoomType.TRANSPORT_STAIRCASE]
    return sum(s.left_exit != s.right_exit for s in stairs), len(stairs)


def trigger3_rooms_exact(gw: GameWorld) -> tuple[int, int]:
    """Non-Ganon trigger-3 rooms whose trigger byte is exactly $03."""
    rooms = [r for level in gw.levels for r in level.rooms
             if r.room_action == RoomAction.LAST_BOSS
             and r.enemy != Enemy.THE_BEAST]
    return sum(r.item_position == 0 for r in rooms), len(rooms)


def layout_byte(room: Room) -> int:
    """The whole LevelBlockAttrsD layout byte: layout code plus monster bit."""
    return room.layout_byte


def unowned_on_six_level_grid(gw: GameWorld) -> int:
    return len(_unowned(gw, LEVELS_1_6))


def unowned_off_bottom_row(gw: GameWorld) -> int:
    rooms = _unowned(gw, LEVELS_1_6) + _unowned(gw, LEVELS_7_9)
    return sum(room_grid.row(room.room_num) != room_grid.ROWS - 1 for room in rooms)


# late-gate.md's door-side classes: the two locked and two walk-through
# door types each count as one class.
SIDE_CLASSES = {
    WallType.OPEN_DOOR: "open", WallType.SHUTTER_DOOR: "shutter",
    WallType.SOLID_WALL: "wall", WallType.BOMB_HOLE: "bombable",
    WallType.LOCKED_DOOR_1: "locked", WallType.LOCKED_DOOR_2: "locked",
    WallType.WALK_THROUGH_WALL_1: "walk-through", WallType.WALK_THROUGH_WALL_2: "walk-through",
}
SIDE_CLASS_ORDER = ("open", "shutter", "wall", "bombable", "locked")


def internal_pairs(gw: GameWorld) -> list[tuple[WallType, WallType]]:
    """Facing side pairs between two rooms of the same level, each pair once
    (from the north or west room)."""
    pairs = []
    for level in gw.levels:
        owned = set(level.room_nums)
        for room in level.rooms:
            for side in (Side.EAST, Side.SOUTH):
                other = neighbour(room.room_num, side)
                if other in owned:
                    facing = level.block.room(other).walls[side.opposite]
                    pairs.append((room.walls[side], facing))
    return pairs


def door_side_mix(gw: GameWorld) -> dict[str, tuple[int, int]]:
    """Per ROM: mismatched internal pairs, and each side class's share of the
    internal pairs' sides, as (hits, cases)."""
    pairs = internal_pairs(gw)
    sides = Counter(SIDE_CLASSES[side] for pair in pairs for side in pair)
    mix = {"mismatched pairs": (sum(a != b for a, b in pairs), len(pairs))}
    mix.update({f"{name} sides": (sides[name], 2 * len(pairs)) for name in SIDE_CLASS_ORDER})
    return mix


def summarize_door_mix(values: list[dict[str, tuple[int, int]]]) -> str:
    def share(name: str) -> float:
        return 100 * sum(v[name][0] for v in values) / max(1, sum(v[name][1] for v in values))
    pairs = sum(v["mismatched pairs"][1] for v in values) / len(values)
    sides = " ".join(f"{name} {share(name + ' sides'):.1f}" for name in SIDE_CLASS_ORDER)
    return f"mismatched {share('mismatched pairs'):.2f}%; {sides}; {pairs:.0f} pairs per ROM"


DOOR_MIX_SUMMARY = Summary(summarize_door_mix, lambda mix: {
    name: (float(hits), float(cases)) for name, (hits, cases) in mix.items()
})


def layout_bytes(gw: GameWorld) -> Counter[int]:
    """Whole layout bytes of every ordinary room in both blocks."""
    return Counter(layout_byte(room) for block in gw.blocks for room in block.rooms)


def zelda_neighbour_push(gw: GameWorld) -> Counter[int]:
    """Non-Ganon trigger-3 rooms (Zelda's neighbours, A32) still holding a
    push block, by whole layout byte."""
    return Counter(layout_byte(room) for level in gw.levels for room in level.rooms
                   if room.room_action == RoomAction.LAST_BOSS
                   and room.enemy != Enemy.THE_BEAST and room.movable_block)


def _zelda_room(gw: GameWorld) -> Room | None:
    """Zelda's room: the last room of the levels-7-9 block holding her
    monster list, in any layout (VA-REJ-01.3). The whole block is scanned
    because a shapes-stage ROM's level 9 may not reach it yet."""
    zelda = [room for room in gw.blocks[LEVELS_7_9].rooms
             if room.enemy == Enemy.THE_KIDNAPPED]
    return zelda[-1] if zelda else None


def _ganon_room(gw: GameWorld) -> Room | None:
    """Ganon's room: the levels-7-9 block's room holding Ganon, any layout."""
    return next((room for room in gw.blocks[LEVELS_7_9].rooms
                 if room.enemy == Enemy.THE_BEAST), None)


def zelda_side_shuttered(gw: GameWorld) -> bool:
    zelda = _zelda_room(gw)
    return zelda is not None and WallType.SHUTTER_DOOR in (
        zelda.walls.north, zelda.walls.east, zelda.walls.south, zelda.walls.west
    )


# Room palettes (SH-DOOR-01 as corrected by U23): outer selector 2 on every
# level cell; person rooms and the hungry goriya's room inner 0; Zelda's
# room inner 2; every other room the base ROM's inner bits ORed with 2.
INNER_PALETTES = (0, 2, 3)


def _is_hungry_goriya(room: Room) -> bool:
    return not room.has_monster_bit and room.monster_list == Enemy.HUNGRY_GORIYA


def room_palettes(gw: GameWorld) -> dict[str, tuple[int, int]]:
    """Level rooms: outer selector 2; person rooms' inner 0; the hungry
    goriya's and Zelda's rooms' inner 0 and 2; each inner selector among
    the other rooms. Each as (hits, cases)."""
    rooms = [room for level in gw.levels for room in level.rooms]
    zelda = _zelda_room(gw)
    persons = [room for room in rooms if room.is_person]
    goriyas = [room for room in rooms if _is_hungry_goriya(room)]
    others = [room for room in rooms if not room.is_person and not _is_hungry_goriya(room)
              and room is not zelda]
    parts = {"outer 2": (sum(room.palette_0 == 2 for room in rooms), len(rooms))}
    parts["person inner 0"] = (sum(room.palette_1 == 0 for room in persons), len(persons))
    parts["goriya inner 0"] = (sum(room.palette_1 == 0 for room in goriyas), len(goriyas))
    parts["zelda inner 2"] = (int(zelda is not None and zelda.palette_1 == 2), int(zelda is not None))
    parts.update({f"other inner {n}": (sum(room.palette_1 == n for room in others), len(others))
                  for n in INNER_PALETTES})
    return parts


# Zelda's and Ganon's rooms against their shape-stage layouts: the shape
# stage puts Zelda on $27 and Ganon on $28 (SH-ROOM-06; the shapes-stage
# corpus agrees, 1,000/1,000); B2's re-deal moves their monsters within
# level 9, and B3's exchange moves layouts between levels.


def zelda_on_own_layout(gw: GameWorld) -> bool:
    zelda = _zelda_room(gw)
    return zelda is not None and zelda.room_type == RoomType.ZELDA_ROOM


def ganon_on_own_layout(gw: GameWorld) -> bool:
    ganon = _ganon_room(gw)
    return ganon is not None and ganon.room_type == RoomType.GANON_ROOM


def pin_pairs(gw: GameWorld, layout: int, sides: tuple[Side, ...]) -> tuple[int, int]:
    """Rooms of this layout (monster bit ignored): facing pairs on the given
    sides with a same-level neighbour, and how many ship wall/wall."""
    wall_wall = cases = 0
    for level in gw.levels:
        owned = set(level.room_nums)
        for room in level.rooms:
            if room.layout_code != layout:
                continue
            for side in sides:
                other = neighbour(room.room_num, side)
                if other not in owned:
                    continue
                cases += 1
                facing = level.block.room(other).walls[side.opposite]
                wall_wall += room.walls[side] == facing == WallType.SOLID_WALL
    return wall_wall, cases


# The pin table's person family in levels 1-8: layout byte exactly $A6 (the black
# room, $26, where persons stand)
# (person flag, no push block), person codes 11-18 except 17 ($11).
PERSON_PIN_LAYOUT_BYTE = RoomType.BLACK_ROOM | MONSTER_BIT   # $A6
PERSON_PIN_LISTS = frozenset(PERSON_LISTS) - {0x11}


def person_north_pairs(gw: GameWorld) -> tuple[int, int]:
    """Pinned person rooms of levels 1-8 whose north side faces a
    same-level room: (wall/wall pairs, pairs)."""
    wall_wall = cases = 0
    for level in gw.levels[:8]:
        owned = set(level.room_nums)
        for room in level.rooms:
            other = neighbour(room.room_num, Side.NORTH)
            if (layout_byte(room) != PERSON_PIN_LAYOUT_BYTE
                    or room.monster_list not in PERSON_PIN_LISTS or other not in owned):
                continue
            cases += 1
            facing = level.block.room(other).walls.south
            wall_wall += room.walls.north == facing == WallType.SOLID_WALL
    return wall_wall, cases


def level9_entrance_north_open(gw: GameWorld) -> bool:
    level9 = gw.levels[8]
    return level9.block.room(level9.entrance_room).walls.north != WallType.SOLID_WALL


def level9_plain_0b_rooms(gw: GameWorld) -> Counter[int]:
    """Level-9 rooms with monster list $0B and no person flag, by count
    index (A34: $0B and, with the count bit, $8B)."""
    return Counter(room.count_index for room in gw.levels[8].rooms
                   if room.monster_list == L9_ENTRY_PERSON_LIST and not room.has_monster_bit)


def by_count_index(indexes: tuple[int, ...]) -> Summary:
    def text(values: list[Counter[int]]) -> str:
        return " / ".join(str(sum(v[i] for v in values)) for i in indexes)
    return Summary(text, lambda counts: {f"index {i}": float(counts[i]) for i in indexes})


def layout_27_south_open(gw: GameWorld) -> bool:
    """Every layout-$27 room's south side (left free by the pin) is not a wall."""
    return all(room.walls.south != WallType.SOLID_WALL for level in gw.levels
               for room in level.rooms if room.layout_code == RoomType.ZELDA_ROOM)


def level9_entrance_side_pairs(gw: GameWorld) -> dict[str, tuple[int, int]]:
    """The level-9 entrance's east and west pairs with a level-9 room:
    (wall/wall, pairs) per side."""
    level9 = gw.levels[8]
    owned = set(level9.room_nums)
    entrance = level9.block.room(level9.entrance_room)
    pairs = {}
    for side in (Side.EAST, Side.WEST):
        other = neighbour(entrance.room_num, side)
        wall_wall = cases = 0
        if other in owned:
            cases = 1
            facing = level9.block.room(other).walls[side.opposite]
            wall_wall = int(entrance.walls[side] == facing == WallType.SOLID_WALL)
        pairs[side.name.lower()] = (wall_wall, cases)
    return pairs


def _pairs_text(values: list[dict[str, tuple[int, int]]]) -> str:
    return " ".join(f"{sum(v[k][0] for v in values)}/{sum(v[k][1] for v in values)}"
                    for k in values[0])


PAIR_SUMMARY = Summary(_pairs_text, lambda pairs: {
    name: (float(hits), float(cases)) for name, (hits, cases) in pairs.items()
})


def minimap_stale_tails(gw: GameWorld) -> int:
    """Levels whose minimap command block holds non-terminator bytes past the
    terminator: vanilla leftovers that the minimap pass leaves (SH-MAP-01)."""
    from zora.generate.shapes.minimap import COMMANDS_END, drawn_commands
    count = 0
    for level in gw.levels:
        drawn = drawn_commands(level.map_ppu_commands)
        count += any(b != COMMANDS_END for b in level.map_ppu_commands[len(drawn):])
    return count


def cellar_items_on_the_ledge(gw: GameWorld) -> bool:
    """SH-STAIR-16: every item cellar's item-position bits pick position $89
    (the middle of the upper ledge) from its level's four positions, with
    the other bits of the byte clear, and every transport staircase's
    byte is $00."""
    from zora.generate.shapes.writeback import CELLAR_ITEM_POSITION
    from zora.model.rooms import ITEM_POSITION_MASK, ITEM_POSITION_SHIFT
    for block in gw.blocks:
        for stair in block.staircases:
            if stair.room_type != RoomType.ITEM_STAIRCASE:
                if stair.t5_raw != 0:
                    return False
                continue
            owner = block.owner_of(stair.return_dest) if stair.return_dest is not None else None
            if owner is None:
                continue
            index = (stair.t5_raw >> ITEM_POSITION_SHIFT) & ITEM_POSITION_MASK
            if (stair.t5_raw != index << ITEM_POSITION_SHIFT
                    or owner.item_position_table[index] != CELLAR_ITEM_POSITION):
                return False
    return True


# --- VA-REJ-20, SH-MAP-05, SH-ROOM-13 (export a6fbf0a) -------------------------------------------

LAST_BOSS_ROOM_ITEM_KEYS = ("key", "bombs", "five rupees", "map", "compass", "other")
_LAST_BOSS_ROOM_ITEM_NAMES = {Item.KEY: "key", Item.BOMBS: "bombs", Item.FIVE_RUPEES: "five rupees",
                              Item.MAP: "map", Item.COMPASS: "compass"}
MAP_TRIGGER_KEYS = (RoomAction.ALL_DEAD_ITEM, RoomAction.ALL_DEAD, RoomAction.LAST_BOSS, "other")
TRIFORCE_ITEMS = frozenset({Item.TRIFORCE, Item.TRIFORCE_OF_POWER})


def _level9_last_boss_rooms(gw: GameWorld) -> list[Room]:
    """Level 9's trigger-3 rooms other than Ganon's."""
    return [room for room in gw.levels[8].rooms
            if room.room_action == RoomAction.LAST_BOSS and room.enemy != Enemy.THE_BEAST]


def last_boss_room_items(gw: GameWorld) -> Counter[str]:
    """VA-REJ-20: the items in level 9's non-Ganon trigger-3 rooms, by kind."""
    return Counter(_LAST_BOSS_ROOM_ITEM_NAMES.get(room.item, "other")
                   for room in _level9_last_boss_rooms(gw) if room.item != Item.NOTHING)


def last_boss_room_compass(gw: GameWorld) -> bool:
    return any(room.item == Item.COMPASS for room in _level9_last_boss_rooms(gw))


def level9_map_trigger(gw: GameWorld) -> RoomAction | str:
    """SH-MAP-05: the trigger of level 9's map room."""
    trigger = next(room.room_action for room in gw.levels[8].rooms if room.item == Item.MAP)
    return trigger if trigger in MAP_TRIGGER_KEYS else "other"


def _item_rooms(level: Level) -> list[Room]:
    """SH-ROOM-13's item rooms: on the level's map (item cellars are no level room), holding an
    item other than a triforce piece or the Triforce of Power."""
    return [room for room in level.rooms if room.item != Item.NOTHING and room.item not in TRIFORCE_ITEMS]


def item_trigger7_levels_1_8(gw: GameWorld) -> tuple[int, int]:
    """SH-ROOM-13, finals: levels 1-8's item rooms on trigger 7, of all of them."""
    rooms = [room for level in gw.levels[:8] for room in _item_rooms(level)]
    return sum(room.room_action == RoomAction.ALL_DEAD_ITEM for room in rooms), len(rooms)


def item_trigger7_level9(gw: GameWorld) -> tuple[int, int]:
    """SH-ROOM-13, finals: level 9's item rooms on trigger 7, of those on trigger 1 or 7."""
    rooms = [room for room in _item_rooms(gw.levels[8])
             if room.room_action in (RoomAction.ALL_DEAD, RoomAction.ALL_DEAD_ITEM)]
    return sum(room.room_action == RoomAction.ALL_DEAD_ITEM for room in rooms), len(rooms)
