"""Visualize pipeline output using the z1r-visualizer.

Takes the reference ROM, patches in the pipeline-generated data, and
runs the z1r-visualizer to dump human-readable room/enemy/item info.

Uses the level grid to restrict room traversal to rooms belonging to
each level, preventing cross-level bleed through staircase rooms or
empty cells with leftover wall data.
"""

from __future__ import annotations

import io
import math
import os
import sys

sys.path.insert(0, "/tmp/z1r-visualizer")

from zora.level_gen.api import (
    NewLevelInput,
    NewLevelOutput,
    generate_new_levels,
    _OW_ENEMY_TABLES_SIZE,
    _LEVEL_INFO_SIZE,
    _SPRITE_TABLE_ADDR,
    _SPRITE_TABLE_SIZE,
)
from zora.level_gen.rom_buffer import (
    GRID_SIZE,
    ROMOFS_SCREEN_LAYOUT,
    ROMOFS_SCREEN_LAYOUT_Q2,
    ROMOFS_OW_ENEMY_TABLE_1,
    ROMOFS_LEVEL_INFO_BASE,
)

from constants import Direction, WallType, ROOM_TYPES, ENEMY_TYPES, ITEM_TYPES, DOOR_TYPES
from data_extractor import DataExtractor

SEED = 12345
ROM_PATH = os.path.join(os.path.dirname(__file__), "prg0.nes")


def run_pipeline(seed: int) -> tuple[bytearray, list[list[int]], list[list[int]]]:
    """Returns (rom, grid_16, grid_79) — separate grids for each level group."""
    ref_rom = open(ROM_PATH, "rb").read()

    inputs = NewLevelInput(
        overworld_enemy_tables=ref_rom[ROMOFS_OW_ENEMY_TABLE_1:ROMOFS_OW_ENEMY_TABLE_1 + _OW_ENEMY_TABLES_SIZE],
        level_info=ref_rom[ROMOFS_LEVEL_INFO_BASE:ROMOFS_LEVEL_INFO_BASE + _LEVEL_INFO_SIZE],
        sprite_table=ref_rom[_SPRITE_TABLE_ADDR:_SPRITE_TABLE_ADDR + _SPRITE_TABLE_SIZE],
    )
    output = generate_new_levels(seed, inputs)

    rom = bytearray(ref_rom)
    rom[ROMOFS_SCREEN_LAYOUT:ROMOFS_SCREEN_LAYOUT + GRID_SIZE] = output.level_1_6_grid
    rom[ROMOFS_SCREEN_LAYOUT_Q2:ROMOFS_SCREEN_LAYOUT_Q2 + GRID_SIZE] = output.level_7_9_grid
    rom[ROMOFS_LEVEL_INFO_BASE:ROMOFS_LEVEL_INFO_BASE + _LEVEL_INFO_SIZE] = output.level_info
    rom[_SPRITE_TABLE_ADDR:_SPRITE_TABLE_ADDR + _SPRITE_TABLE_SIZE] = output.sprite_table

    return rom, output.grid_16, output.grid_79


def get_wall_type(extractor: DataExtractor, level_num: int, room_num: int,
                  direction: Direction) -> int:
    offset = 0x80 if direction in [Direction.EAST, Direction.WEST] else 0x00
    bits_to_shift = 32 if direction in [Direction.NORTH, Direction.WEST] else 4
    return math.floor(extractor.GetRoomData(level_num, room_num + offset) / bits_to_shift) % 0x08


def get_room_type(extractor: DataExtractor, level_num: int, room_num: int) -> str:
    code = extractor.GetRoomData(level_num, room_num + 3 * 0x80) & 0x3F
    return ROOM_TYPES.get(code, f'CODE_0x{code:02X}')


def get_enemy_text(extractor: DataExtractor, level_num: int, room_num: int) -> str:
    code = extractor.GetRoomData(level_num, room_num + 2 * 0x80)
    qty_code = code >> 6
    qty = [3, 5, 6, 8][qty_code]
    enemy_6bit = code & 0x3F
    if extractor.GetRoomData(level_num, room_num + 3 * 0x80) >= 0x80:
        enemy_6bit += 0x40
    name = ENEMY_TYPES.get(enemy_6bit, f'E_0x{enemy_6bit:02X}')
    if not name:
        return ''
    if (enemy_6bit <= 0x30 or enemy_6bit >= 0x62) and enemy_6bit != 0:
        return f'{qty} {name}'
    return name


def get_item_text(extractor: DataExtractor, level_num: int, room_num: int) -> str:
    code = extractor.GetRoomData(level_num, room_num + 4 * 0x80) & 0x1F
    nothing_code = extractor.rom_reader.GetNothingCode()
    enemy_6bit = extractor.GetRoomData(level_num, room_num + 2 * 0x80) & 0x3F
    if extractor.GetRoomData(level_num, room_num + 3 * 0x80) >= 0x80:
        enemy_6bit += 0x40
    if code == nothing_code and enemy_6bit != 0x3E:
        return ''
    is_drop = (extractor.GetRoomData(level_num, room_num + 5 * 0x80) >> 2) & 1
    name = ITEM_TYPES.get(code, f'ITEM_0x{code:02X}')
    return f'{"D " if is_drop else ""}{name}'


def gather_level_data(
    extractor: DataExtractor, level_num: int,
    level_rooms: set[int], stairway_rooms: list[int],
) -> tuple[dict[int, dict], dict[int, str], int, set[int]]:
    """BFS from entrance; returns (visited, stair_info, entrance, unreachable)."""
    entrance = extractor.GetLevelStartRoomNumber(level_num)

    # Build stair info and teleport links before BFS
    stair_info: dict[int, str] = {}
    stair_teleports: dict[int, int] = {}
    stair_num = 1
    for sr in stairway_rooms:
        left = extractor.GetRoomData(level_num, sr) & 0x7F
        right = extractor.GetRoomData(level_num, sr + 0x80) & 0x7F
        if left == right:
            item_code = extractor.GetRoomData(level_num, sr + 4 * 0x80) & 0x1F
            item_name = ITEM_TYPES.get(item_code, f'ITEM_0x{item_code:02X}')
            stair_info[left] = f'I:{_abbrev_item(item_name)}'
        else:
            stair_info[left] = f'Stair #{stair_num}'
            stair_info[right] = f'Stair #{stair_num}'
            stair_teleports[left] = right
            stair_teleports[right] = left
            stair_num += 1

    visited: dict[int, dict] = {}
    queue = [entrance]

    while queue:
        room_num = queue.pop(0)
        if room_num in visited:
            continue
        if room_num not in range(0x80):
            continue
        if room_num not in level_rooms:
            continue

        room_data: dict = {
            'room_type': get_room_type(extractor, level_num, room_num),
            'enemy_info': get_enemy_text(extractor, level_num, room_num),
            'item_info': get_item_text(extractor, level_num, room_num),
            'walls': {},
        }

        for direction in [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]:
            wt = get_wall_type(extractor, level_num, room_num, direction)
            dir_name = {Direction.NORTH: 'N', Direction.SOUTH: 'S',
                        Direction.EAST: 'E', Direction.WEST: 'W'}[direction]
            room_data['walls'][dir_name] = wt
            if wt != WallType.SOLID_WALL:
                neighbor = room_num + int(direction)
                if neighbor in level_rooms:
                    queue.append(neighbor)

        if room_num in stair_teleports:
            queue.append(stair_teleports[room_num])

        visited[room_num] = room_data

    unreachable = level_rooms - set(visited.keys())
    return visited, stair_info, entrance, unreachable


# ── Abbreviation tables ──

_ROOM_ABBREV: dict[str, str] = {
    "Plain": "PLAIN", "Spike Trap": "SPIKE", "Four Short": "4-SHORT",
    "Four Tall": "4-TALL", "Aqua Room": "AQUA", "Gleeok Room": "GLEEOK",
    "Gohma Room": "GOHMA", "Three Rows": "3-ROWS", "Reverse C": "REV-C",
    "Circle Wall": "CIR WALL", "Double Block": "DBL BLK",
    "Lava Moat": "LAVA", "Maze Room": "MAZE", "Grid Room": "GRID",
    "Vert. Chute": "V-CHUTE", "Horiz. Chute": "H-CHUTE",
    "Vertical Rows": "V-ROWS", "Zigzag": "ZIGZAG", "T Room": "T-ROOM",
    "Vert. Moat": "V-MOAT", "Circle Moat": "CIR MOAT",
    "Pointless Moat": "PT MOAT", "Chevy": "CHEVY", "NSU": "NSU",
    "Horiz. Moat": "H-MOAT", "Double Moat": "DBL MOAT",
    "Diamond Stair": "DIA STR", "Corridor Stair": "COR STR",
    "Spiral Stair": "SPI STR", "Double Six": "DBL 6",
    "Single Six": "SGL 6", "Five Pair": "5-PAIR",
    "Turnstile": "TURNSTL", "Entrance Room": "ENTRANCE",
    "Single Block": "SGL BLK", "Two Fireball": "2-FIRE",
    "Four Fireball": "4-FIRE", "Desert Room": "DESERT",
    "Black Room": "BLACK", "Zelda Room": "ZELDA",
    "Gannon Room": "GANNON", "Triforce Room": "TRIFORCE",
}

_ITEM_ABBREV: dict[str, str] = {
    "Heart Container": "HEART-C", "Wood Sword": "W.SWRD",
    "White Sword": "WH.SWRD", "Magical Sword": "MG.SWRD",
    "Wooden Arrow": "W.ARRW", "Silver Arrow": "S.ARRW",
    "Boomerang": "BOOM", "Magical Boomerang": "MG.BOOM",
    "Blue Candle": "BL.CNDL", "Red Candle": "RD.CNDL",
    "Blue Ring": "BL.RING", "Red Ring": "RD.RING",
    "Magical Key": "MG.KEY", "Shield": "SHIELD",
    "Power Bracelet": "BRACLT", "5 Rupees": "5 RUPEE",
    "Triforce": "TRIFRCE", "Triforce of Power": "TRI-PWR",
    "Heart": "HEART", "Compass": "COMPASS", "Map": "MAP",
    "Key": "KEY", "Bombs": "BOMBS", "Bait": "BAIT",
    "Recorder": "RECORDR", "Raft": "RAFT", "Ladder": "LADDER",
    "Wand": "WAND", "Book": "BOOK", "Letter": "LETTER",
    "Bow": "BOW", "Rupee": "RUPEE", "Blue Potion": "BL.POT",
    "Red Potion": "RD.POT",
}

_ENEMY_ABBREV: dict[str, str] = {
    "Blue Lynel": "BL.LYNL", "Red Lynel": "RD.LYNL",
    "Blue Moblin": "BL.MOBL", "Red Moblin": "RD.MOBL",
    "Blue Goriya": "BL.GORI", "Red Goriya": "RD.GORI",
    "Red Darknut": "RD.DARK", "Blue Darknut": "BL.DARK",
    "Blue Wizzrobe": "BL.WIZZ", "Red Wizzrobe": "RD.WIZZ",
    "Blue Keese": "BL.KEES", "Red Keese": "RD.KEES",
    "Black Keese": "BK.KEES", "Like Like": "LIKLIKE",
    "Pols Voice": "POLSVCE", "Wallmaster": "WALLMST",
    "Digdogger (3)": "DIG-3", "Digdogger (1)": "DIG-1",
    "Red Lanmola": "RD.LANM", "Blue Lanmola": "BL.LANM",
    "Manhandala": "MANHNDA", "Aquamentus": "AQUAMNT",
    "The Beast": "GANNON", "The Kidnapped": "ZELDA",
    "Moldorm": "MOLDORM", "Patra (Ellipse)": "PATRA-E",
    "Patra (Circle)": "PATRA-C", "Horiz. Traps": "H.TRAPS",
    "Corner Traps": "C.TRAPS", "Rupee Boss": "RUP.BOS",
    "Hungry Enemy": "HUNGRY", "Bomb Upgrade": "BOMB-UP",
    "1 Head Gleeok": "1H.GLEK", "2 Head Gleeok": "2H.GLEK",
    "3 Head Gleeok": "3H.GLEK", "4 Head Gleeok": "4H.GLEK",
    "Falling Rocks": "ROCKS", "Stalfos": "STALFO",
    "Rope": "ROPE", "Gibdo": "GIBDO", "Vire": "VIRE",
    "Zol": "ZOL", "Gel": "GEL", "Bubble": "BUBBLE",
    "Blue Bubble": "BL.BUBL", "Red Bubble": "RD.BUBL",
    "3 Dodongos": "3 DODNG", "1 Dodongo": "1 DODNG",
    "Blue Gohma": "BL.GOHM", "Red Gohma": "RD.GOHM",
    "Mugger": "MUGGER", "Peahat": "PEAHAT", "Armos": "ARMOS",
    "Ghini": "GHINI",
}


def _abbrev_room(name: str) -> str:
    return _ROOM_ABBREV.get(name, name[:9])


def _abbrev_item(name: str) -> str:
    return _ITEM_ABBREV.get(name, name[:7])


def _abbrev_enemy(text: str) -> str:
    if not text:
        return ''
    parts = text.split(' ', 1)
    if len(parts) == 2 and parts[0].isdigit():
        qty, name = parts
        if name.startswith('Enemy Mix '):
            short = 'MIX ' + name[-1]
        else:
            short = _ENEMY_ABBREV.get(name, name[:7])
        return f'{qty} {short}'
    if text.startswith('Enemy Mix '):
        return 'MIX ' + text[-1]
    short = _ENEMY_ABBREV.get(text, text[:9])
    return short


def _wall_char(wt: int) -> str:
    """Returns a marker character for non-solid walls, or None for solid."""
    if wt == WallType.SOLID_WALL:
        return None
    if wt == WallType.DOOR:
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


_CELL_W = 13

def render_ascii_map(
    level_num: int,
    visited: dict[int, dict],
    stair_info: dict[int, str],
    entrance: int,
    unreachable: set[int],
) -> str:
    all_rooms = set(visited.keys()) | unreachable
    if not all_rooms:
        return f"  Level {level_num}: no rooms\n"

    all_nums = sorted(all_rooms)
    rows_present = [rn >> 4 for rn in all_nums]
    cols_present = [rn & 0xF for rn in all_nums]
    min_row, max_row = min(rows_present), max(rows_present)
    min_col, max_col = min(cols_present), max(cols_present)

    iw = _CELL_W
    cell_total_w = iw + 2 + 1
    cell_h = 7
    grid_w = max_col - min_col + 1
    grid_h = max_row - min_row + 1

    lines: list[str] = []
    lines.append(f"  Level {level_num} map  (entrance=0x{entrance:02X},"
                 f" {len(visited)} reachable, {len(unreachable)} unreachable)")
    lines.append("")

    for gr in range(grid_h):
        row = min_row + gr
        cell_lines: list[list[str]] = [[] for _ in range(cell_h)]

        for gc in range(grid_w):
            col = min_col + gc
            rn = (row << 4) | col
            blank = " " * cell_total_w

            if rn not in all_rooms:
                for idx in range(cell_h):
                    cell_lines[idx].append(blank)
                continue

            if rn in visited:
                rd = visited[rn]
                rt = _abbrev_room(rd['room_type'])
                enemy = _abbrev_enemy(rd['enemy_info'])
                item = rd['item_info']
                if item:
                    item_parts = item.split(' ', 1)
                    if item_parts[0] == 'D':
                        item = 'D ' + _abbrev_item(item_parts[1]) if len(item_parts) > 1 else 'D'
                    else:
                        item = _abbrev_item(item)

                tag = ""
                if rn == entrance:
                    tag = "[ENTER]"
                elif rn in stair_info:
                    tag = stair_info[rn]
            else:
                rd = None
                rt = "UNREACH"
                enemy = ""
                item = ""
                tag = ""

            label = f"{rn:02X} {tag}"

            fit = iw - 2
            enemy = enemy[:fit]
            item = item[:fit]
            rt = rt[:fit]
            label = label[:fit]

            if rd is not None:
                n = _wall_char(rd['walls']['N'])
                s = _wall_char(rd['walls']['S'])
                wl = _wall_char(rd['walls']['W'])
                wr = _wall_char(rd['walls']['E'])
            else:
                n = s = wl = wr = "?"

            def _ns_bar(ch: str | None) -> str:
                if ch is None:
                    return "─" * iw
                half = (iw - 3) // 2
                return "─" * half + ch * 3 + "─" * (iw - 3 - half)

            wl_mid = wl if wl is not None else "│"
            wr_mid = wr if wr is not None else "│"

            cell_lines[0].append(f"┌{_ns_bar(n)}┐ ")
            cell_lines[1].append(f"│ {label:<{fit}s} │ ")
            cell_lines[2].append(f"│ {rt:^{fit}s} │ ")
            cell_lines[3].append(f"{wl_mid} {enemy:^{fit}s} {wr_mid} ")
            cell_lines[4].append(f"│ {item:^{fit}s} │ ")
            cell_lines[5].append(f"│{' ' * iw}│ ")
            cell_lines[6].append(f"└{_ns_bar(s)}┘ ")

        for cl in cell_lines:
            lines.append("  " + "".join(cl))

    lines.append("")
    lines.append("  Walls:  ─/│ solid  (space) open  L locked"
                 "  S shutter  B bomb  W walk-through")
    return "\n".join(lines)


def visualize_level(extractor: DataExtractor, level_num: int,
                    level_rooms: set[int], stairway_rooms: list[int]) -> None:
    visited, stair_info, entrance, unreachable = gather_level_data(
        extractor, level_num, level_rooms, stairway_rooms)
    print()
    print(render_ascii_map(level_num, visited, stair_info, entrance, unreachable))


def main() -> None:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else SEED
    print(f"Running pipeline with seed={seed}", file=sys.stderr)

    rom, grid_16, grid_79 = run_pipeline(seed)

    rom_io = io.BytesIO(bytes(rom))
    extractor = DataExtractor(rom=rom_io)

    # Build per-level room sets from the appropriate grid
    level_room_sets: dict[int, set[int]] = {}
    for grid in [grid_16, grid_79]:
        for r in range(8):
            for c in range(16):
                lv = grid[r][c]
                if lv > 0:
                    room = r * 16 + c
                    level_room_sets.setdefault(lv, set()).add(room)

    # Print both grids
    print("\nLevel grid (levels 1-6):")
    for r in range(8):
        print("  " + " ".join(f"{grid_16[r][c]:2d}" for c in range(16)))
    print("\nLevel grid (levels 7-9):")
    for r in range(8):
        print("  " + " ".join(f"{grid_79[r][c]:2d}" for c in range(16)))

    # Get stairway rooms per level from the level info blocks
    for level_num in range(1, 10):
        rooms = level_room_sets.get(level_num, set())
        if not rooms:
            print(f"\n=== Level {level_num}: NOT IN GRID ===")
            continue

        stairway_rooms = []
        try:
            stairway_rooms = extractor.GetLevelStairwayRoomNumberList(level_num)
        except (IndexError, KeyError):
            pass

        visualize_level(extractor, level_num, rooms, stairway_rooms)


if __name__ == "__main__":
    main()
