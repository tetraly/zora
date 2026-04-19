"""ASCII dungeon map renderer for diagnostics and debugging.

Renders a level's room grid with walls, items, room types, and optional
traversal annotations from a GameValidator (visited/collected/stuck status).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zora.data_model import Item, Level, Room, RoomType, WallType

if TYPE_CHECKING:
    from zora.game_validator import GameValidator

_CELL_INNER_WIDTH = 13

_ROOM_TYPE_ABBREV: dict[str, str] = {
    "PLAIN_ROOM": "PLAIN",
    "SPIKE_TRAP_ROOM": "SPIKE TRAP",
    "FOUR_SHORT_ROOM": "4-SHORT",
    "FOUR_TALL_ROOM": "4-TALL",
    "AQUAMENTUS_ROOM": "AQUAMNTUS",
    "GLEEOK_ROOM": "GLEEOK",
    "GOHMA_ROOM": "GOHMA",
    "THREE_ROWS": "3-ROWS",
    "REVERSE_C": "REVERSE-C",
    "CIRCLE_WALL": "CIR WALL",
    "DOUBLE_BLOCK": "DBL BLOCK",
    "LAVA_MOAT": "LAVA MOAT",
    "MAZE_ROOM": "MAZE",
    "GRID_ROOM": "GRID",
    "HORIZONTAL_CHUTE_ROOM": "H-CHUTE",
    "VERTICAL_CHUTE_ROOM": "V-CHUTE",
    "VERTICAL_ROWS": "V-ROWS",
    "ZIGZAG_ROOM": "ZIGZAG",
    "T_ROOM": "T-ROOM",
    "VERTICAL_MOAT_ROOM": "V-MOAT",
    "CIRCLE_MOAT_ROOM": "CIR MOAT",
    "POINTLESS_MOAT_ROOM": "PT MOAT",
    "CHEVY_ROOM": "CHEVY",
    "NSU": "NSU",
    "HORIZONTAL_MOAT_ROOM": "H-MOAT",
    "DOUBLE_MOAT_ROOM": "DBL MOAT",
    "DIAMOND_STAIR_ROOM": "DIA STAIR",
    "NARROW_STAIR_ROOM": "NAR STAIR",
    "SPIRAL_STAIR_ROOM": "SPI STAIR",
    "DOUBLE_SIX_BLOCK_ROOM": "DBL 6-BLK",
    "SINGLE_SIX_BLOCK_ROOM": "SGL 6-BLK",
    "FIVE_PAIR_ROOM": "5-PAIR",
    "TURNSTILE_ROOM": "TURNSTILE",
    "ENTRANCE_ROOM": "ENTRANCE",
    "SINGLE_BLOCK_ROOM": "SGL BLOCK",
    "TWO_FIREBALL_ROOM": "2-FIREBALL",
    "FOUR_FIREBALL_ROOM": "4-FIREBALL",
    "DESERT_ROOM": "DESERT",
    "BLACK_ROOM": "BLACK",
    "ZELDA_ROOM": "ZELDA",
    "GANNON_ROOM": "GANNON",
    "TRIFORCE_ROOM": "TRIFORCE",
    "TRANSPORT_STAIRCASE": "TRANSPORT",
    "ITEM_STAIRCASE": "ITEM STAIR",
}

_ITEM_ABBREV: dict[str, str] = {
    "HEART_CONTAINER": "HEART-C",
    "WOOD_SWORD": "W.SWORD",
    "WHITE_SWORD": "WH.SWRD",
    "MAGICAL_SWORD": "MG.SWRD",
    "WOOD_ARROWS": "W.ARROW",
    "SILVER_ARROWS": "S.ARROW",
    "WOOD_BOOMERANG": "W.BOOM",
    "MAGICAL_BOOMERANG": "MG.BOOM",
    "BLUE_CANDLE": "BL.CNDL",
    "RED_CANDLE": "RD.CNDL",
    "BLUE_RING": "BL.RING",
    "RED_RING": "RD.RING",
    "MAGICAL_KEY": "MG.KEY",
    "MAGICAL_SHIELD": "MG.SHLD",
    "POWER_BRACELET": "BRACLET",
    "FIVE_RUPEES": "5 RUPEE",
    "TRIFORCE": "TRIFORCE",
    "SINGLE_HEART": "HEART",
}


def _wall_char(wt: WallType) -> str:
    if wt == WallType.SOLID_WALL:
        return "█"
    if wt == WallType.OPEN_DOOR:
        return " "
    if wt in (WallType.LOCKED_DOOR_1, WallType.LOCKED_DOOR_2):
        return "L"
    if wt == WallType.SHUTTER_DOOR:
        return "S"
    if wt == WallType.BOMB_HOLE:
        return "B"
    if wt in (WallType.WALK_THROUGH_WALL_1, WallType.WALK_THROUGH_WALL_2):
        return "W"
    return "?"


def _abbrev_room_type(name: str) -> str:
    return _ROOM_TYPE_ABBREV.get(name, name[:_CELL_INNER_WIDTH - 2])


def _abbrev_item(name: str) -> str:
    return _ITEM_ABBREV.get(name, name[:_CELL_INNER_WIDTH - 2])


def _room_status(
    room: Room,
    room_num: int,
    level_num: int,
    entrance_room: int,
    unreachable_rooms: set[int],
    validator: GameValidator | None,
) -> str:
    if room_num in unreachable_rooms:
        return "[UNREACH]"
    if room_num == entrance_room:
        return "[ENTER]"
    if validator is None:
        return ""
    visited = (level_num, room_num) in validator.visited_rooms
    collected = (level_num, room_num) in validator.items_collected_rooms
    if not visited:
        return "[no visit]"
    if collected:
        return "[ok]"
    if room.item != Item.NOTHING:
        return "[STUCK!]"
    return ""


def render_level_map(
    level: Level,
    *,
    validator: GameValidator | None = None,
    unreachable_rooms: set[int] | None = None,
) -> str:
    """Render an ASCII map of a dungeon level.

    Args:
        level: The Level to render.
        validator: Optional GameValidator with populated traversal state.
            When provided, rooms are annotated with visit/collection status.
        unreachable_rooms: Room numbers to mark as [UNREACH].
    """
    if unreachable_rooms is None:
        unreachable_rooms = set()

    rooms_by_num: dict[int, Room] = {r.room_num: r for r in level.rooms}
    if not rooms_by_num:
        return f"  Level {level.level_num}: no rooms\n"

    all_nums = list(rooms_by_num.keys())
    rows_list = [rn >> 4 for rn in all_nums]
    cols_list = [rn & 0xF for rn in all_nums]
    min_row, max_row = min(rows_list), max(rows_list)
    min_col, max_col = min(cols_list), max(cols_list)

    iw = _CELL_INNER_WIDTH
    cell_w = iw + 2 + 1  # inner + 2 side walls + 1 gap
    cell_h = 7
    grid_w = max_col - min_col + 1
    grid_h = max_row - min_row + 1

    lines: list[str] = []
    lines.append(
        f"  Level {level.level_num} map  "
        f"(entrance = R{level.entrance_room:#04x})"
    )
    lines.append("")

    for gr in range(grid_h):
        row = min_row + gr
        cell_lines: list[list[str]] = [[] for _ in range(cell_h)]

        for gc in range(grid_w):
            col = min_col + gc
            rn = (row << 4) | col
            room = rooms_by_num.get(rn)

            if room is None:
                blank = " " * cell_w
                for row_idx in range(cell_h):
                    cell_lines[row_idx].append(blank)
                continue

            n = _wall_char(room.walls.north)
            s = _wall_char(room.walls.south)
            e = _wall_char(room.walls.east)
            w = _wall_char(room.walls.west)

            status = _room_status(
                room, rn, level.level_num, level.entrance_room,
                unreachable_rooms, validator,
            )
            item_str = (
                _abbrev_item(room.item.name)
                if room.item != Item.NOTHING else ""
            )
            rt_str = _abbrev_room_type(room.room_type.name)

            half = (iw - 1) // 2
            top_bar = "─" * half + n + "─" * (iw - 1 - half)
            bot_bar = "─" * half + s + "─" * (iw - 1 - half)

            label_line = f"{rn:02X}  {status}"

            cell_lines[0].append(f"┌{top_bar}┐ ")
            cell_lines[1].append(f"{w} {label_line:<{iw - 2}s} {e} ")
            cell_lines[2].append(f"{w}{' ' * iw}{e} ")
            cell_lines[3].append(f"{w} {item_str:^{iw - 2}s} {e} ")
            cell_lines[4].append(f"{w} {rt_str:^{iw - 2}s} {e} ")
            cell_lines[5].append(f"{w}{' ' * iw}{e} ")
            cell_lines[6].append(f"└{bot_bar}┘ ")

        for row_cells in cell_lines:
            lines.append("  " + "".join(row_cells))

    lines.append("")
    if validator is not None:
        lines.append(
            "  Status: [ENTER] entrance  [UNREACH] unfilled & unreachable"
            "  [STUCK!] visited, item not collected"
        )
        lines.append(
            "          [ok] item collected"
            "  [no visit] never reached during traversal"
        )
    lines.append(
        "  Walls:  █ solid  (space) open  L locked"
        "  S shutter  B bomb  W walk-through"
    )
    return "\n".join(lines)
