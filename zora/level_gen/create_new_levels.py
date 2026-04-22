"""Top-level orchestrator for dungeon level generation.

Seeds the RNG, builds a dungeon assignment array [1..9], optionally
shuffles it (first 6 and last 3 independently), then calls a sequence
of sub-functions for levels 1-6 and/or 7-9.

If any sub-function returns False (placement failure), retries with a
fresh RNG seed up to MAX_RETRIES times.

Includes NewLevelRewriteMaps (mini-map data encoder) and
FixLevelNumbers (dungeon order remapper).

Ported line-by-line from CreateNewLevels.cs (createNewLevels,
Module.cs:29310-29487) and (newLevelRewriteMaps, Module.cs:28737-28926).
Cross-referenced: see CreateNewLevels_crossref.md.
"""

from __future__ import annotations

from typing import Callable

from zora.level_gen.place_items import validate_level_items
from zora.level_gen.rom_buffer import (
    GRID_COLS,
    GRID_ROWS,
    LevelGrid,
    clear_grid_data,
)
from zora.rng import Rng


MAX_RETRIES = 200


# ---------------------------------------------------------------------------
# FixLevelNumbers  (Module.cs:19352-19505)
# ---------------------------------------------------------------------------

def fix_level_numbers(
    level_grid: LevelGrid,
    dungeon_order: list[int],
    min_level: int,
    number_of_levels: int,
    sort_levels: bool,
) -> None:
    """Remap level numbers in the grid according to dungeon_order.

    Counts how many cells each temporary level (1..number_of_levels)
    occupies, sorts levels by room count ascending (selection sort),
    then assigns dungeon_order values to grid cells via the sorted
    mapping.
    """
    # Step 1: Build (level_index, count) pairs  (Module.cs:19358-19369)
    pairs: list[list[int]] = [[i + 1, 0] for i in range(number_of_levels)]

    # Step 2: Count cells per level  (Module.cs:19371-19404)
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            val = level_grid[row][col]
            if val > 0:
                idx = val - 1
                if 0 <= idx < number_of_levels:
                    pairs[idx][1] += 1

    # Step 3: Selection sort by count ascending  (Module.cs:19406-19433)
    n = len(pairs)
    for i in range(n):
        for j in range(i + 1, n):
            if pairs[i][1] > pairs[j][1]:
                pairs[i], pairs[j] = pairs[j], pairs[i]

    # Step 4: Build remapping table  (Module.cs:19435-19453)
    remap = [0] * 10
    for i in range(number_of_levels):
        old_level = pairs[i][0]
        new_level = dungeon_order[min_level - 1 + i]
        remap[old_level] = new_level

    # Step 5: Apply remap to grid  (Module.cs:19455-19490)
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            val = level_grid[row][col]
            if val != 0:
                level_grid[row][col] = remap[val]


# ---------------------------------------------------------------------------
# NewLevelRewriteMaps  (Module.cs:28737-28926)
# ---------------------------------------------------------------------------

def new_level_rewrite_maps(
    rom: bytearray,
    level_grid: LevelGrid,
    start_level: int,
) -> int:
    """Rewrite dungeon mini-map data in ROM for the specified level set.

    Returns the level-9 start column (Level9StartCol) or 0 if level 9
    is not in this group.
    """
    if start_level == 1:
        map_data_addr = 103515
        end_level = 6
    else:
        map_data_addr = 105027
        end_level = 9

    header_addr = map_data_addr - 33

    tile_lookup = [36, 251, 103, 255]

    level9_start_col = 0

    for current_level in range(start_level, end_level + 1):
        min_col = 15
        max_col = 0

        for row in range(8):
            for col in range(16):
                if level_grid[row][col] == current_level:
                    if col < min_col:
                        min_col = col
                    if col > max_col:
                        max_col = col

        if current_level == 9:
            level9_start_col = min_col
            if max_col - min_col < 6:
                level9_start_col = min_col - 1

        col_span = max_col - min_col
        center_offset = 6 - (col_span + 2) // 2
        start_col = min_col - center_offset + 2

        rom[header_addr] = (start_col * -8) & 0xFF

        write_pos = 0
        col_count = col_span + 1
        ppu_addr_low = center_offset + 96

        for row_pair in range(0, 8, 2):
            rom[map_data_addr + write_pos] = 32
            write_pos += 1
            rom[map_data_addr + write_pos] = ppu_addr_low & 0xFF
            write_pos += 1
            rom[map_data_addr + write_pos] = col_count & 0xFF
            write_pos += 1

            for col in range(min_col, max_col + 1):
                even_row_hit = 1 if level_grid[row_pair][col] == current_level else 0
                odd_row_hit = 1 if level_grid[row_pair + 1][col] == current_level else 0
                index = even_row_hit * 2 + odd_row_hit
                rom[map_data_addr + write_pos] = tile_lookup[index] & 0xFF
                write_pos += 1

            ppu_addr_low += 32

        rom[map_data_addr + write_pos] = 0xFF

        bitmap_addr = map_data_addr - 16
        bitmap_center = (min_col - max_col + 15) // 2

        for i in range(16):
            rom[bitmap_addr + i] = 0

        bitmap_col = bitmap_center
        for col in range(min_col, max_col + 1):
            bits = 0
            for row in range(8):
                occupied = 1 if level_grid[row][col] == current_level else 0
                bits = (bits << 1) | occupied
            rom[bitmap_addr + bitmap_col] = bits & 0xFF
            bitmap_col += 1

        rom[header_addr - 1] = (bitmap_center - min_col) & 0x0F

        map_data_addr += 252
        header_addr += 252

    return level9_start_col


# ---------------------------------------------------------------------------
# NewLevelFixForSanity  (Module.cs:29264 — decompiler failed)
# ---------------------------------------------------------------------------

def _new_level_fix_for_sanity(
    rom: bytearray,
    level_grid: LevelGrid,
) -> None:
    """Placeholder — Module.cs decompiler crashed on this function.

    The original calls this after all generation is complete.  Without
    the decompiled source we cannot implement it.  Callers should be
    aware this is a no-op until the function body is recovered.
    """
    pass


# ---------------------------------------------------------------------------
# CreateNewLevels  (Module.cs:29310-29487)
# ---------------------------------------------------------------------------

def create_new_levels(
    rom: bytearray,
    rng: Rng,
    seed: int,
    swordless: bool,
    add_2nd_monsters: bool,
    add_2nd_rooms: bool,
    add_2nd_doors: bool,
    create_16: bool,
    create_79: bool,
    shuffle_entrances: bool,
    sort_dungeons: bool,
    *,
    regenerate_level_map_fn: Callable[[Rng, int, bool], LevelGrid],
    new_level_doors_fn: Callable[[bytearray, Rng, LevelGrid, int, int, bool], None],
    new_level_add_entrances_fn: Callable[
        [bytearray, Rng, LevelGrid, int, bool],
        tuple[bool, int, int],
    ],
    new_level_place_initial_stairs_fn: Callable[..., bool],
    new_level_rooms_fn: Callable[[bytearray, Rng, LevelGrid, int, int, bool, int], bool],
    new_level_place_bosses_fn: Callable[[bytearray, Rng, int, LevelGrid], bool],
    new_level_place_enemies_fn: Callable[
        [bytearray, Rng, int, LevelGrid, bool], None
    ],
    new_level_place_items_fn: Callable[[bytearray, Rng, int, LevelGrid], bool],
    add_item_drop_fn: Callable[[bytearray, int], None],
    mixed_quest_type_1: int = 0,
    mixed_quest_type_2: int = 0,
) -> tuple[bool, LevelGrid, list[int], int]:
    """Top-level orchestrator for dungeon level generation.

    Returns (success, level_grid, dungeon_order, level9_start_col).
    """
    level_grid: LevelGrid = [[0] * GRID_COLS for _ in range(GRID_ROWS)]

    for attempt in range(MAX_RETRIES):
        try:
            result = _try_create(
                rom, rng, level_grid,
                swordless, add_2nd_monsters, add_2nd_rooms, add_2nd_doors,
                create_16, create_79, shuffle_entrances, sort_dungeons,
                regenerate_level_map_fn=regenerate_level_map_fn,
                new_level_doors_fn=new_level_doors_fn,
                new_level_add_entrances_fn=new_level_add_entrances_fn,
                new_level_place_initial_stairs_fn=new_level_place_initial_stairs_fn,
                new_level_rooms_fn=new_level_rooms_fn,
                new_level_place_bosses_fn=new_level_place_bosses_fn,
                new_level_place_enemies_fn=new_level_place_enemies_fn,
                new_level_place_items_fn=new_level_place_items_fn,
                add_item_drop_fn=add_item_drop_fn,
                mixed_quest_type_1=mixed_quest_type_1,
                mixed_quest_type_2=mixed_quest_type_2,
            )
        except ItemPlacementError:
            result = None
        if result is not None:
            return result
        # On retry, C# consumes 1 RNG for the recursive call's seed param
        # (Module.cs e.g. 29404: createNewLevels(A_0, sodiumRand()(A_0), ...))
        rng.next()

    dungeon_order = list(range(1, 10))
    return (True, level_grid, dungeon_order, 0)


def _try_create(
    rom: bytearray,
    rng: Rng,
    level_grid: LevelGrid,
    swordless: bool,
    add_2nd_monsters: bool,
    add_2nd_rooms: bool,
    add_2nd_doors: bool,
    create_16: bool,
    create_79: bool,
    shuffle_entrances: bool,
    sort_dungeons: bool,
    *,
    regenerate_level_map_fn: Callable[[Rng, int, bool], LevelGrid],
    new_level_doors_fn: Callable[[bytearray, Rng, LevelGrid, int, int, bool], None],
    new_level_add_entrances_fn: Callable[
        [bytearray, Rng, LevelGrid, int, bool],
        tuple[bool, int, int],
    ],
    new_level_place_initial_stairs_fn: Callable[..., bool],
    new_level_rooms_fn: Callable[[bytearray, Rng, LevelGrid, int, int, bool, int], bool],
    new_level_place_bosses_fn: Callable[[bytearray, Rng, int, LevelGrid], bool],
    new_level_place_enemies_fn: Callable[
        [bytearray, Rng, int, LevelGrid, bool], None
    ],
    new_level_place_items_fn: Callable[[bytearray, Rng, int, LevelGrid], bool],
    add_item_drop_fn: Callable[[bytearray, int], None],
    mixed_quest_type_1: int,
    mixed_quest_type_2: int,
) -> tuple[bool, LevelGrid, list[int], int] | None:
    """Single attempt. Returns result tuple on success, None to retry."""

    # Step 1: Advance RNG twice (sodiumRand::seed is a NO-OP)
    # Module.cs:29312-29314
    rng.next()
    rng.next()

    # Step 2: Create dungeon assignment array {1..9}
    # Module.cs:29315-29327
    dungeon_order = [1, 2, 3, 4, 5, 6, 7, 8, 9]

    # Step 3: Shuffle if !sort_dungeons
    # Module.cs:29328-29363
    if not sort_dungeons:
        # Shuffle first 6 elements (indices 0-5) — levels 1-6
        remaining = 6
        i = 0
        while remaining > 0:
            j = rng.next() % remaining
            dungeon_order[i], dungeon_order[i + j] = (
                dungeon_order[i + j], dungeon_order[i]
            )
            i += 1
            remaining -= 1

        # Shuffle remaining elements (indices 6+) — levels 7-9
        if 6 < len(dungeon_order):
            for i in range(6, len(dungeon_order)):
                j = rng.next() % (len(dungeon_order) - i)
                dungeon_order[i], dungeon_order[i + j] = (
                    dungeon_order[i + j], dungeon_order[i]
                )

    level9_start_col = 0
    goriya_room = 0

    # Step 4: Generate levels 1-6
    # Module.cs:29365-29423
    if create_16:
        # 4a: Clear data (Module.cs:29367)
        clear_grid_data(rom, 1)

        # 4b: Regenerate level map (Module.cs:29368)
        # regenerate_level_map consumes 1 RNG internally (matching call-site seed)
        level_grid_new = regenerate_level_map_fn(rng, 6, shuffle_entrances)
        for r in range(GRID_ROWS):
            for c in range(GRID_COLS):
                level_grid[r][c] = level_grid_new[r][c]

        # 4c: Fix level numbers (Module.cs:29369)
        fix_level_numbers(level_grid, dungeon_order, 1, 6, sort_dungeons)

        # 4d: Flatten grid into screen_type_data[0] (Module.cs:29370-29400)
        screen_type_data_0: list[int] = []
        for row in level_grid:
            for cell in row:
                screen_type_data_0.append(cell)

        # 4e: NewLevelDoors (Module.cs:29401)
        # Call-site consumes 1 RNG for seed param
        new_level_doors_fn(rom, rng, level_grid, rng.next(), 1, add_2nd_doors)

        # 4f: NewLevelAddEntrances (Module.cs:29402)
        result = new_level_add_entrances_fn(
            rom, rng, level_grid, rng.next(), shuffle_entrances,
        )
        if not result[0]:
            return None
        goriya_room = result[2]

        # 4g: NewLevelPlaceInitialStairs (Module.cs:29406)
        if not new_level_place_initial_stairs_fn(
            rom, rng, level_grid, rng.next(), 1, add_2nd_rooms,
            goriya_room, mixed_quest_type_1, mixed_quest_type_2,
            add_item_drop_fn,
        ):
            return None

        # 4h: NewLevelRooms (Module.cs:29410)
        if not new_level_rooms_fn(
            rom, rng, level_grid, rng.next(), 1, add_2nd_rooms, goriya_room,
        ):
            return None

        # 4i: NewLevelPlaceBosses (Module.cs:29414)
        # Call-site consumes 1 RNG for seed param; function doesn't take seed
        rng.next()
        if not new_level_place_bosses_fn(rom, rng, 1, level_grid):
            return None

        # 4j: NewLevelPlaceEnemies (Module.cs:29418)
        rng.next()
        new_level_place_enemies_fn(rom, rng, 1, level_grid, add_2nd_monsters)

        # 4k: NewLevelPlaceItems (Module.cs:29419)
        rng.next()
        if not new_level_place_items_fn(rom, rng, 1, level_grid):
            return None
        validate_level_items(rom, level_grid, 1)

        # 4l: NewLevelRewriteMaps (Module.cs:29423)
        new_level_rewrite_maps(rom, level_grid, 1)

    # Step 5: Generate levels 7-9
    # Module.cs:29425-29483
    if create_79:
        # 5a: Clear data (Module.cs:29427)
        clear_grid_data(rom, 7)

        # 5b: Regenerate level map (Module.cs:29428)
        level_grid_new = regenerate_level_map_fn(rng, 3, shuffle_entrances)
        for r in range(GRID_ROWS):
            for c in range(GRID_COLS):
                level_grid[r][c] = level_grid_new[r][c]

        # 5c: Fix level numbers (Module.cs:29429)
        fix_level_numbers(level_grid, dungeon_order, 7, 3, sort_dungeons)

        # 5d: Flatten grid into screen_type_data[1] (Module.cs:29430-29460)
        screen_type_data_1: list[int] = []
        for row in level_grid:
            for cell in row:
                screen_type_data_1.append(cell)

        # 5e: NewLevelDoors (Module.cs:29461)
        new_level_doors_fn(rom, rng, level_grid, rng.next(), 7, add_2nd_doors)

        # 5f: NewLevelAddEntrances (Module.cs:29462)
        result = new_level_add_entrances_fn(
            rom, rng, level_grid, rng.next(), shuffle_entrances,
        )
        if not result[0]:
            return None
        goriya_room = result[2]

        # 5g: NewLevelPlaceInitialStairs (Module.cs:29466)
        if not new_level_place_initial_stairs_fn(
            rom, rng, level_grid, rng.next(), 7, add_2nd_rooms,
            goriya_room, mixed_quest_type_1, mixed_quest_type_2,
            add_item_drop_fn,
        ):
            return None

        # 5h: NewLevelRooms (Module.cs:29470)
        if not new_level_rooms_fn(
            rom, rng, level_grid, rng.next(), 7, add_2nd_rooms, goriya_room,
        ):
            return None

        # 5i: NewLevelPlaceBosses (Module.cs:29474)
        rng.next()
        if not new_level_place_bosses_fn(rom, rng, 7, level_grid):
            return None

        # 5j: NewLevelPlaceEnemies (Module.cs:29478)
        rng.next()
        new_level_place_enemies_fn(rom, rng, 7, level_grid, add_2nd_monsters)

        # 5k: NewLevelPlaceItems (Module.cs:29479)
        rng.next()
        if not new_level_place_items_fn(rom, rng, 7, level_grid):
            return None
        validate_level_items(rom, level_grid, 7)

        # 5l: NewLevelRewriteMaps (Module.cs:29483)
        level9_start_col = new_level_rewrite_maps(rom, level_grid, 7)

    # Step 6: Final sanity fix (Module.cs:29485)
    _new_level_fix_for_sanity(rom, level_grid)

    return (True, level_grid, dungeon_order, level9_start_col)
