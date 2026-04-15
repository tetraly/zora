"""
Invariant validator: raises ValueError if a GameWorld violates structural constraints.

Call validate_game_world(gw) before serializing to catch constraint violations
that would produce a corrupt or unplayable ROM.
"""
from zora.data_model import Destination, GameWorld, HintShop, ItemCave, Level, Shop, TakeAnyCave


def validate_game_world(gw: GameWorld) -> None:
    """Validate all structural invariants of a GameWorld.

    Raises ValueError with a descriptive message on the first violation found.
    """
    _validate_levels(gw.levels)
    _validate_overworld(gw)
    _validate_quotes(gw)


# ---------------------------------------------------------------------------
# Levels
# ---------------------------------------------------------------------------

def _validate_levels(levels: list[Level]) -> None:
    if len(levels) != 9:
        raise ValueError(f"Expected 9 levels, got {len(levels)}")

    level_nums = [lvl.level_num for lvl in levels]
    if sorted(level_nums) != list(range(1, 10)):
        raise ValueError(f"Level numbers must be 1-9, got {sorted(level_nums)}")

    for lvl in levels:
        _validate_level(lvl)

    # Levels sharing a grid (1-6 and 7-9 separately) must have no common room numbers
    for grid_levels in [levels[:6], levels[6:]]:
        seen: dict[int, int] = {}  # room_num -> level_num
        for lvl in grid_levels:
            all_rooms = [r.room_num for r in lvl.rooms] + [r.room_num for r in lvl.staircase_rooms]
            for rn in all_rooms:
                if rn in seen:
                    raise ValueError(
                        f"Room {rn:#04x} shared by levels {seen[rn]} and {lvl.level_num} "
                        f"(both in same grid)"
                    )
                seen[rn] = lvl.level_num


def _validate_level(lvl: Level) -> None:
    tag = f"Level {lvl.level_num}"

    # Room number uniqueness across rooms + staircase rooms
    room_nums = [r.room_num for r in lvl.rooms] + [r.room_num for r in lvl.staircase_rooms]
    seen = set()
    for rn in room_nums:
        if rn in seen:
            raise ValueError(f"{tag}: duplicate room_num {rn:#04x}")
        seen.add(rn)

    # All room numbers in range
    for rn in room_nums:
        if not (0x00 <= rn <= 0x7F):
            raise ValueError(f"{tag}: room_num {rn:#04x} out of range 0x00-0x7F")

    # At most 4 unique enemy_quantity values (qty table is 4 bytes)
    unique_qtys = set(r.enemy_quantity for r in lvl.rooms)
    if len(unique_qtys) > 4:
        raise ValueError(
            f"{tag}: {len(unique_qtys)} unique enemy_quantity values (max 4): {sorted(unique_qtys)}"
        )

    # palette_raw must be exactly 36 bytes
    if len(lvl.palette_raw) != 36:
        raise ValueError(f"{tag}: palette_raw length {len(lvl.palette_raw)}, expected 36")

    # item_position_table must be exactly 4 bytes
    if len(lvl.item_position_table) != 4:
        raise ValueError(
            f"{tag}: item_position_table length {len(lvl.item_position_table)}, expected 4"
        )


# ---------------------------------------------------------------------------
# Overworld
# ---------------------------------------------------------------------------

def _validate_overworld(gw: GameWorld) -> None:
    ow = gw.overworld
    screens = ow.screens

    # Exactly 0x80 screens
    if len(screens) != 0x80:
        raise ValueError(f"Expected 0x80 overworld screens, got {len(screens)}")

    # Screen numbers unique and in range
    screen_nums = [s.screen_num for s in screens]
    if sorted(screen_nums) != list(range(0x80)):
        dupes = [n for n in screen_nums if screen_nums.count(n) > 1]
        raise ValueError(f"Overworld screen numbers must be 0x00-0x7F unique; duplicates: {dupes}")

    # Recorder warp destinations: exactly 8, all valid screen numbers
    if len(ow.recorder_warp_destinations) != 8:
        raise ValueError(
            f"recorder_warp_destinations must have 8 entries, got {len(ow.recorder_warp_destinations)}"
        )
    for i, d in enumerate(ow.recorder_warp_destinations):
        if not (0x00 <= d <= 0x7F):
            raise ValueError(
                f"recorder_warp_destinations[{i}] = {d:#04x} out of range 0x00-0x7F"
            )

    # Recorder Y coordinates: exactly 8
    if len(ow.recorder_warp_y_coordinates) != 8:
        raise ValueError(
            f"recorder_warp_y_coordinates must have 8 entries, got {len(ow.recorder_warp_y_coordinates)}"
        )

    # Any-road screens: exactly 4, all valid screen numbers
    if len(ow.any_road_screens) != 4:
        raise ValueError(f"any_road_screens must have 4 entries, got {len(ow.any_road_screens)}")
    for i, s in enumerate(ow.any_road_screens):
        if not (0x00 <= s <= 0x7F):
            raise ValueError(f"any_road_screens[{i}] = {s:#04x} out of range 0x00-0x7F")

    # Start screen in range
    if not (0x00 <= ow.start_screen <= 0x7F):
        raise ValueError(f"start_screen {ow.start_screen:#04x} out of range 0x00-0x7F")

    cave_by_dest = {c.destination: c for c in ow.caves}

    # Take-any: exactly 2 items
    take_any = cave_by_dest.get(Destination.TAKE_ANY)
    if take_any is not None and isinstance(take_any, TakeAnyCave):
        if len(take_any.items) not in [2, 3]:
            raise ValueError(f"take_any must have 2 or 3 items, got {len(take_any.items)}")

    # Shops: each must have exactly 3 item slots (potion shop has 2)
    for dest in [Destination.SHOP_1, Destination.SHOP_2, Destination.SHOP_3, Destination.SHOP_4]:
        c = cave_by_dest.get(dest)
        if c is not None and isinstance(c, Shop):
            if len(c.items) != 3:
                raise ValueError(f"{dest.name} must have 3 items, got {len(c.items)}")

    # Hint shops: each must have exactly 3 slots
    for dest, name in [(Destination.HINT_SHOP_1, "hint_shop_1"), (Destination.HINT_SHOP_2, "hint_shop_2")]:
        c = cave_by_dest.get(dest)
        if c is not None and isinstance(c, HintShop):
            if len(c.hints) != 3:
                raise ValueError(f"{name} must have 3 hints, got {len(c.hints)}")

    # Heart requirements in valid range (1-16)
    for dest, name in [
        (Destination.WHITE_SWORD_CAVE, "white_sword_cave"),
        (Destination.MAGICAL_SWORD_CAVE, "magical_sword_cave"),
    ]:
        c = cave_by_dest.get(dest)
        if c is not None and isinstance(c, ItemCave):
            if not (1 <= c.heart_requirement <= 16):
                raise ValueError(f"{name}.heart_requirement {c.heart_requirement} out of range 1-16")


# ---------------------------------------------------------------------------
# Quotes
# ---------------------------------------------------------------------------

def _validate_quotes(gw: GameWorld) -> None:
    if not gw.quotes:
        return  # quotes are optional (bin file may be absent in test environments)

    if len(gw.quotes) != 38:
        raise ValueError(f"Expected 38 quotes, got {len(gw.quotes)}")

    ids = [q.quote_id for q in gw.quotes]
    if sorted(ids) != list(range(38)):
        raise ValueError(f"Quote IDs must be 0-37 unique, got {sorted(ids)}")
