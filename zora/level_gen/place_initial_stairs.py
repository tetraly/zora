"""Place initial stair connections between dungeon levels.

Two stair types: passable (one-way, single room) and cross-level
(two-way, two rooms connecting different areas).

Ported line-by-line from NewLevelPlaceInitialStairs.cs
(newLevelPlaceInitialStairs, Module.cs:21316).
Cross-referenced against Module.cs:21316-22123.

Discrepancies found in the .cs file (fixed here to match Module.cs):
- emptyCells collection: .cs collects OCCUPIED cells (grid != 0).
  Module.cs:21342 collects EMPTY cells (grid == 0). Fixed to match
  Module.cs — the function collects unoccupied grid positions.
"""

from __future__ import annotations

from collections import deque
from typing import Callable

from zora.level_gen.rom_buffer import (
    GRID_COLS,
    GRID_ROWS,
    LevelGrid,
    ROMOFS_DOOR_DATA,
    ROMOFS_ENEMY_DATA,
    ROMOFS_ITEM_DATA,
    ROMOFS_ROOM_FLAGS,
    ROMOFS_SCREEN_LAYOUT,
    ROMOFS_SCREEN_LAYOUT_Q2,
)
from zora.rng import Rng

_DIR_ROW = (1, 0, -1, 0)
_DIR_COL = (0, 1, 0, -1)

_MAX_ROOM_SEARCH_ATTEMPTS = 10_000


def new_level_place_initial_stairs(
    rom: bytearray,
    rng: Rng,
    level_grid: LevelGrid,
    seed: int,
    level: int,
    add_2nd_quest: bool,
    goriya_room: int,
    mixed_quest_type_1: int,
    mixed_quest_type_2: int,
    add_item_drop: Callable[[bytearray, int], None],
) -> bool:
    # sodiumRand::seed is a NO-OP in the original. Do NOT reseed.
    rng.next()
    rng.next()

    # Collect EMPTY cells from level grid (Module.cs:21326-21358)
    empty_cells: list[int] = []
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            if level_grid[row][col] == 0:
                empty_cells.append(row * 16 + col)

    # Stair budget per level (Module.cs:21366-21390)
    stair_budget = [0] * 10
    if level == 1:
        stair_budget[1] = 1
        stair_budget[3] += 1
        stair_budget[4] += 1
        stair_budget[5] += 1
        stair_budget[6] += 1
        stair_budget[5] += 1
        stair_budget[6] += 1
    else:
        stair_budget[7] += 1
        stair_budget[8] += 2
        stair_budget[9] += 2
        stair_budget[7] += 1
        stair_budget[8] += 1
        stair_budget[9] += 6

    # BFS grid for connectivity analysis (Module.cs:21391-21501)
    # Uses grid adjacency (original behavior) for stair budget calculation.
    bfs_grid = [[0] * GRID_COLS for _ in range(GRID_ROWS)]
    connectivity_count = [0] * 10

    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            cell_level = level_grid[row][col]
            if cell_level != 0 and bfs_grid[row][col] == 0:
                connectivity_count[cell_level] += 1
                queue: deque[tuple[int, int]] = deque()
                queue.append((row, col))
                bfs_grid[row][col] = cell_level
                while queue:
                    r, c = queue.popleft()
                    for d in range(4):
                        nr = r + _DIR_ROW[d]
                        nc = c + _DIR_COL[d]
                        if (0 <= nr <= 7 and 0 <= nc <= 15
                                and bfs_grid[nr][nc] == 0
                                and level_grid[nr][nc] == cell_level):
                            bfs_grid[nr][nc] = cell_level
                            queue.append((nr, nc))

    # =========================================================================
    # WORKAROUND — NOT IN ORIGINAL C# PORT
    #
    # Separate wall-connectivity BFS for stair endpoint selection.  The door
    # weight tables can place solid walls between same-level adjacent rooms,
    # creating wall-disconnected segments within a single grid component.
    # The grid-based BFS above drives the stair budget (original behavior);
    # this wall-based BFS drives endpoint selection so that cross-level stairs
    # bridge wall-disconnected segments when possible.
    # =========================================================================
    layout_base_for_bfs = ROMOFS_SCREEN_LAYOUT_Q2 if level == 7 else ROMOFS_SCREEN_LAYOUT
    t0_base = layout_base_for_bfs
    t1_base = layout_base_for_bfs + 128

    def _wall_passable(r: int, c: int, d: int) -> bool:
        room_idx = r * 16 + c
        if d == 0:
            return ((rom[room_idx + t0_base] >> 2) & 0x07) != 1
        elif d == 1:
            return ((rom[room_idx + t1_base] >> 2) & 0x07) != 1
        elif d == 2:
            return ((rom[room_idx + t0_base] >> 5) & 0x07) != 1
        else:
            return ((rom[room_idx + t1_base] >> 5) & 0x07) != 1

    wall_component_grid = [[0] * GRID_COLS for _ in range(GRID_ROWS)]
    wall_bfs_grid = [[0] * GRID_COLS for _ in range(GRID_ROWS)]
    next_wall_comp = 1

    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            cell_level = level_grid[row][col]
            if cell_level != 0 and wall_bfs_grid[row][col] == 0:
                cur_comp = next_wall_comp
                next_wall_comp += 1
                queue2: deque[tuple[int, int]] = deque()
                queue2.append((row, col))
                wall_bfs_grid[row][col] = cell_level
                wall_component_grid[row][col] = cur_comp
                while queue2:
                    r, c = queue2.popleft()
                    for d in range(4):
                        nr = r + _DIR_ROW[d]
                        nc = c + _DIR_COL[d]
                        if (0 <= nr <= 7 and 0 <= nc <= 15
                                and wall_bfs_grid[nr][nc] == 0
                                and level_grid[nr][nc] == cell_level
                                and _wall_passable(r, c, d)):
                            wall_bfs_grid[nr][nc] = cell_level
                            wall_component_grid[nr][nc] = cur_comp
                            queue2.append((nr, nc))

    wall_comp_count: dict[int, int] = {}
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            lv_val = level_grid[row][col]
            if lv_val != 0:
                wc = wall_component_grid[row][col]
                if wc not in wall_comp_count:
                    wall_comp_count[wc] = 0
                wall_comp_count[wc] += 1
    # =========================================================================
    # END WORKAROUND (wall-based BFS)
    # =========================================================================

    # Adjust stair budget by connectivity (Module.cs:21502-21521)
    for i in range(len(connectivity_count)):
        adj = max(0, connectivity_count[i] - 1)
        stair_budget[i] += adj
        if stair_budget[i] > 9:
            return False

    # Passable stair weights per level
    passable_count = [0, 1, 0, 1, 1, 1, 1, 1, 2, 2]

    # Stair room screen types
    stair_screen_types = [90, 27, 98, 74, 72, 28, 65, 70, 71, 76, 77, 81, 92, 95]

    # Room counts per screen type (mutable)
    stair_room_counts = [14, 6, 2, 4, 2, 2, 0, 0, 0, 0, 0, 0, 0, 0]

    # Max stairs per screen type
    max_stairs_per_type = [4, 9, 5, 7, 3, 3, 2, 2, 2, 1, 2, 4, 1, 6]

    # If add_2nd_quest: merge max_stairs_per_type into stair_room_counts
    if add_2nd_quest:
        for i in range(len(stair_room_counts)):
            stair_room_counts[i] += max_stairs_per_type[i]

    # Compute total weight
    total_weight = sum(stair_room_counts)

    # ROM base offset: Q1 at 100112, Q2 at 100880
    base_ofs = 768 if level == 7 else 0

    # Per-level stair type data
    stair_type_data: list[list[int]] = [
        [],       # [0] unused
        [10],     # [1]
        [],       # [2] unused
        [12],     # [3]
        [13],     # [4]
        [5],      # [5]
        [16],     # [6]
        [7],      # [7]
        [17, 11], # [8]
        [9, 19],  # [9]
    ]

    # Mixed quest type overrides
    if mixed_quest_type_2 == 1:
        stair_type_data[6][0] = 17
    if mixed_quest_type_1 == 1:
        stair_type_data[8][0] = 16

    # Main stair placement loop: levels 1-9
    empty_cell_idx = 0
    lv = 1

    while True:
        stair_list_idx = 0
        stair_list_addr = lv * 252 + 103236
        sentinel_base = lv * 252 + 103225
        type_data_idx = 0

        if stair_budget[lv] != 0:
            while True:
                if passable_count[lv] != 0:
                    # ==== PASSABLE STAIR (one-way) ====
                    stair_slot = empty_cells[empty_cell_idx]
                    empty_cell_idx += 1

                    # Find random room in this level with empty screen type at +384
                    room = rng.next() % 128
                    attempts = 0
                    while True:
                        if level_grid[room // 16][room % 16] == lv:
                            if (rom[base_ofs + room + ROMOFS_ENEMY_DATA] & 0x7F) == 0:
                                break
                        room = rng.next() % 128
                        attempts += 1
                        if attempts >= _MAX_ROOM_SEARCH_ATTEMPTS:
                            return False

                    # Skip goriya room for level-7 set
                    if room == goriya_room and level == 7:
                        empty_cell_idx -= 1
                        continue

                    # Pick weighted random screen type
                    pick = rng.next() % total_weight
                    type_idx = 0
                    pick -= stair_room_counts[0]
                    while pick >= 0:
                        type_idx += 1
                        pick -= stair_room_counts[type_idx]

                    # ROM writes for passable stair
                    rom[base_ofs + stair_slot + ROMOFS_SCREEN_LAYOUT] = room & 0xFF
                    rom[base_ofs + stair_slot + ROMOFS_SCREEN_LAYOUT + 128] = room & 0xFF
                    rom[base_ofs + stair_slot + ROMOFS_ENEMY_DATA] = 63
                    rom[base_ofs + stair_slot + ROMOFS_ITEM_DATA] = 105
                    rom[base_ofs + room + ROMOFS_ENEMY_DATA] = stair_screen_types[type_idx] & 0xFF
                    rom[base_ofs + room + ROMOFS_DOOR_DATA] = (rom[base_ofs + room + ROMOFS_DOOR_DATA] & 0xE0) | 3

                    # Sentinel scan: find 0x89 marker
                    sentinel_count = 0
                    scan_addr = sentinel_base
                    while rom[scan_addr] != 137:
                        sentinel_count += 1
                        scan_addr += 1

                    # Stair type from per-level data
                    rom[base_ofs + stair_slot + ROMOFS_DOOR_DATA] = stair_type_data[lv][type_data_idx] & 0xFF
                    type_data_idx += 1

                    # Stair position
                    rom[base_ofs + stair_slot + ROMOFS_ROOM_FLAGS] = (sentinel_count * 16) & 0xFF

                    # Store stair index in per-level list
                    rom[stair_list_addr + stair_list_idx] = stair_slot & 0xFF
                    stair_list_idx += 1

                    # Screen type passage check
                    screen_type_val = stair_screen_types[type_idx]
                    if (screen_type_val & 0x40) != 0 and screen_type_val != 90 and screen_type_val != 92:
                        rom[base_ofs + room + ROMOFS_ROOM_FLAGS] = (rom[base_ofs + room + ROMOFS_ROOM_FLAGS] & 0xF8) | 5

                    # Add item drop
                    add_item_drop(rom, room)

                    # Random dark room
                    if rng.next() % 3 != 0:
                        door_byte = rom[base_ofs + room + ROMOFS_DOOR_DATA] & 0x1F
                        flag_byte = rom[base_ofs + room + ROMOFS_ROOM_FLAGS]
                        flag_low = flag_byte & 7
                        if door_byte != 3 and (flag_low == 0 or flag_low == 1):
                            rom[base_ofs + room + ROMOFS_ROOM_FLAGS] = (flag_byte | 7) & 0xFF

                    # Decrement counts
                    passable_count[lv] -= 1
                    stair_budget[lv] -= 1

                else:
                    # ==== CROSS-LEVEL STAIR (two-way) ====
                    stair_slot = empty_cells[empty_cell_idx]
                    empty_cell_idx += 1

                    # Find first room with 1000-retry limit
                    room1 = rng.next() % 128
                    retries = 0
                    while True:
                        if retries < 1000:
                            if level_grid[room1 // 16][room1 % 16] != lv:
                                room1 = rng.next() % 128
                                retries += 1
                                continue
                        if (rom[base_ofs + room1 + ROMOFS_ENEMY_DATA] & 0x7F) == 0:
                            break
                        room1 = rng.next() % 128
                        retries += 1

                    if retries == 1000:
                        return False

                    # Skip goriya room
                    if room1 == goriya_room and level == 7:
                        empty_cell_idx -= 1
                        continue

                    # Find second room, different from first
                    room2 = rng.next() % 128
                    retries2 = 0
                    while True:
                        if level_grid[room2 // 16][room2 % 16] == lv:
                            if (rom[base_ofs + room2 + ROMOFS_ENEMY_DATA] & 0x7F) == 0 and room1 != room2:
                                break
                        room2 = rng.next() % 128
                        retries2 += 1
                        if retries2 > 1000:
                            return False

                    # Skip goriya room
                    if room2 == goriya_room and level == 7:
                        empty_cell_idx -= 1
                        continue

                    # =============================================================
                    # WORKAROUND — NOT IN ORIGINAL C# PORT
                    #
                    # Use wall-connectivity components (not grid adjacency) to
                    # pick room2 in a different wall segment from room1.  This
                    # ensures cross-level stairs bridge wall-disconnected segments
                    # even when the grid BFS sees only one component.
                    # =============================================================
                    r1_wcomp = wall_component_grid[room1 // 16][room1 % 16]
                    r2_wcomp = wall_component_grid[room2 // 16][room2 % 16]
                    if r1_wcomp == r2_wcomp:
                        best_candidate = -1
                        best_comp_size = -1
                        for candidate in range(128):
                            cr, cc = candidate // 16, candidate % 16
                            if (level_grid[cr][cc] == lv
                                    and wall_component_grid[cr][cc] != r1_wcomp
                                    and (rom[base_ofs + candidate + ROMOFS_ENEMY_DATA] & 0x7F) == 0
                                    and candidate != room1
                                    and not (candidate == goriya_room and level == 7)):
                                cand_comp = wall_component_grid[cr][cc]
                                cand_size = wall_comp_count.get(cand_comp, 0)
                                if cand_size > best_comp_size:
                                    best_comp_size = cand_size
                                    best_candidate = candidate
                        if best_candidate >= 0:
                            room2 = best_candidate
                    # =============================================================
                    # END WORKAROUND
                    # =============================================================

                    # Pick screen type for room1
                    pick1 = rng.next() % total_weight
                    type_idx1 = 0
                    pick1 -= stair_room_counts[0]
                    while pick1 >= 0:
                        type_idx1 += 1
                        pick1 -= stair_room_counts[type_idx1]

                    # ROM writes for cross-level stair slot
                    rom[base_ofs + stair_slot + ROMOFS_SCREEN_LAYOUT] = room1 & 0xFF
                    rom[base_ofs + stair_slot + ROMOFS_SCREEN_LAYOUT + 128] = room2 & 0xFF
                    rom[base_ofs + stair_slot + ROMOFS_ENEMY_DATA] = 62
                    rom[base_ofs + stair_slot + ROMOFS_ITEM_DATA] = 105
                    rom[base_ofs + stair_slot + ROMOFS_DOOR_DATA] = 3
                    rom[base_ofs + stair_slot + ROMOFS_ROOM_FLAGS] = rom[base_ofs + stair_slot + ROMOFS_ROOM_FLAGS] & 0xF8

                    # Set screen type for room1
                    rom[base_ofs + room1 + ROMOFS_ENEMY_DATA] = stair_screen_types[type_idx1] & 0xFF
                    rom[base_ofs + room1 + ROMOFS_DOOR_DATA] = (rom[base_ofs + room1 + ROMOFS_DOOR_DATA] & 0xE0) | 3

                    # Room1 passage check — no 92 exclusion here
                    if (stair_screen_types[type_idx1] & 0x40) != 0 and stair_screen_types[type_idx1] != 90:
                        rom[base_ofs + room1 + ROMOFS_ROOM_FLAGS] = (rom[base_ofs + room1 + ROMOFS_ROOM_FLAGS] & 0xF8) | 5

                    # Pick screen type for room2
                    pick2 = rng.next() % total_weight
                    type_idx2 = 0
                    pick2 -= stair_room_counts[0]
                    while pick2 >= 0:
                        type_idx2 += 1
                        pick2 -= stair_room_counts[type_idx2]

                    # Set screen type for room2
                    rom[base_ofs + room2 + ROMOFS_ENEMY_DATA] = stair_screen_types[type_idx2] & 0xFF
                    rom[base_ofs + room2 + ROMOFS_DOOR_DATA] = (rom[base_ofs + room2 + ROMOFS_DOOR_DATA] & 0xE0) | 3

                    # Room2 passage check — includes 92 special case
                    screen_type_val2 = stair_screen_types[type_idx2]
                    if (screen_type_val2 & 0x40) != 0 and screen_type_val2 != 90 and screen_type_val2 != 92:
                        rom[base_ofs + room2 + ROMOFS_ROOM_FLAGS] = (rom[base_ofs + room2 + ROMOFS_ROOM_FLAGS] & 0xF8) | 5
                    elif screen_type_val2 == 92:
                        rom[base_ofs + room2 + ROMOFS_ROOM_FLAGS] = (rom[base_ofs + room2 + ROMOFS_ROOM_FLAGS] & 0xF8) | 4

                    # Store stair index
                    rom[stair_list_addr + stair_list_idx] = stair_slot & 0xFF
                    stair_list_idx += 1

                    # Add item drops for both rooms
                    add_item_drop(rom, room1)
                    add_item_drop(rom, room2)

                    # Random dark room for room1
                    if rng.next() % 3 != 0:
                        door_byte = rom[base_ofs + room1 + ROMOFS_DOOR_DATA] & 0x1F
                        flag_byte = rom[base_ofs + room1 + ROMOFS_ROOM_FLAGS]
                        flag_low = flag_byte & 7
                        if door_byte != 3 and (flag_low == 0 or flag_low == 1):
                            rom[base_ofs + room1 + ROMOFS_ROOM_FLAGS] = (flag_byte | 7) & 0xFF

                    # Random dark room for room2
                    if rng.next() % 3 != 0:
                        door_byte = rom[base_ofs + room2 + ROMOFS_DOOR_DATA] & 0x1F
                        flag_byte = rom[base_ofs + room2 + ROMOFS_ROOM_FLAGS]
                        flag_low = flag_byte & 7
                        if door_byte != 3 and (flag_low == 0 or flag_low == 1):
                            rom[base_ofs + room2 + ROMOFS_ROOM_FLAGS] = (flag_byte | 7) & 0xFF

                    # Decrement budget
                    stair_budget[lv] -= 1

                if stair_budget[lv] == 0:
                    break

        lv += 1
        if lv >= 10:
            break

    # =========================================================================
    # WORKAROUND — NOT IN ORIGINAL C# PORT
    #
    # After all stairs are placed, some wall-disconnected segments may remain
    # unreachable (the stair budget based on grid-connectivity is smaller than
    # the number of wall-connectivity components).  Open one solid wall per
    # remaining disconnected pair to merge them.
    # =========================================================================
    _merge_wall_segments(rom, level_grid, t0_base, t1_base)

    return True


def _merge_wall_segments(
    rom: bytearray,
    level_grid: LevelGrid,
    t0_base: int,
    t1_base: int,
) -> None:
    """Open solid walls to merge wall-disconnected segments within each level."""

    def _wall_type(r: int, c: int, d: int) -> int:
        room_idx = r * 16 + c
        if d == 0:
            return (rom[room_idx + t0_base] >> 2) & 0x07
        elif d == 1:
            return (rom[room_idx + t1_base] >> 2) & 0x07
        elif d == 2:
            return (rom[room_idx + t0_base] >> 5) & 0x07
        else:
            return (rom[room_idx + t1_base] >> 5) & 0x07

    def _open_wall(r: int, c: int, d: int) -> None:
        """Set wall type to 0 (open door) on both sides."""
        room_idx = r * 16 + c
        if d == 0:  # south
            addr = room_idx + t0_base
            rom[addr] = rom[addr] & ~0x1C
            nr_idx = (r + 1) * 16 + c
            addr2 = nr_idx + t0_base
            rom[addr2] = rom[addr2] & ~0xE0
        elif d == 1:  # east
            addr = room_idx + t1_base
            rom[addr] = rom[addr] & ~0x1C
            nr_idx = r * 16 + (c + 1)
            addr2 = nr_idx + t1_base
            rom[addr2] = rom[addr2] & ~0xE0
        elif d == 2:  # north
            addr = room_idx + t0_base
            rom[addr] = rom[addr] & ~0xE0
            nr_idx = (r - 1) * 16 + c
            addr2 = nr_idx + t0_base
            rom[addr2] = rom[addr2] & ~0x1C
        else:  # west
            addr = room_idx + t1_base
            rom[addr] = rom[addr] & ~0xE0
            nr_idx = r * 16 + (c - 1)
            addr2 = nr_idx + t1_base
            rom[addr2] = rom[addr2] & ~0x1C

    changed = True
    while changed:
        changed = False

        comp_grid = [[0] * GRID_COLS for _ in range(GRID_ROWS)]
        visited = [[False] * GRID_COLS for _ in range(GRID_ROWS)]
        comp_id = 0
        comp_level: dict[int, int] = {}

        for row in range(GRID_ROWS):
            for col in range(GRID_COLS):
                lv = level_grid[row][col]
                if lv != 0 and not visited[row][col]:
                    comp_id += 1
                    comp_level[comp_id] = lv
                    queue: deque[tuple[int, int]] = deque()
                    queue.append((row, col))
                    visited[row][col] = True
                    comp_grid[row][col] = comp_id
                    while queue:
                        r, c = queue.popleft()
                        for d in range(4):
                            nr = r + _DIR_ROW[d]
                            nc = c + _DIR_COL[d]
                            if (0 <= nr <= 7 and 0 <= nc <= 15
                                    and not visited[nr][nc]
                                    and level_grid[nr][nc] == lv
                                    and _wall_type(r, c, d) != 1):
                                visited[nr][nc] = True
                                comp_grid[nr][nc] = comp_id
                                queue.append((nr, nc))

        level_comps: dict[int, set[int]] = {}
        for cid, lv in comp_level.items():
            level_comps.setdefault(lv, set()).add(cid)

        for lv, comps in level_comps.items():
            if len(comps) <= 1:
                continue

            merged = False
            for row in range(GRID_ROWS):
                if merged:
                    break
                for col in range(GRID_COLS):
                    if merged:
                        break
                    if level_grid[row][col] != lv:
                        continue
                    for d in range(4):
                        nr = row + _DIR_ROW[d]
                        nc = col + _DIR_COL[d]
                        if (0 <= nr <= 7 and 0 <= nc <= 15
                                and level_grid[nr][nc] == lv
                                and comp_grid[row][col] != comp_grid[nr][nc]
                                and _wall_type(row, col, d) == 1):
                            _open_wall(row, col, d)
                            changed = True
                            merged = True
                            break
