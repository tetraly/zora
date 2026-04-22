"""Place item rooms in dungeon levels.

For each level, finds random rooms belonging to that level whose door-type
byte is not already reserved, then stamps item-room door types into the
ROM door table.

Ported from NewLevelPlaceItems.cs (newLevelPlaceItems, Module.cs:20346).
"""

from __future__ import annotations

from zora.data_model import Item
from zora.level_gen.rom_buffer import LevelGrid, ROMOFS_DOOR_DATA
from zora.rng import Rng

_FORBIDDEN_DOOR_TYPES = {3, 14, 26, 27, 22, 23, 29, 30}

_MAX_ATTEMPTS = 10000


class ItemPlacementError(Exception):
    """Raised when a generated dungeon has incorrect item room counts."""


def new_level_place_items(
    rom: bytearray,
    rng: Rng,
    level: int,
    level_grid: LevelGrid,
) -> bool:
    """Place item rooms for all levels in the current grid group.

    *level* is the starting level (1 for levels 1-6, 7 for levels 7-9).
    Returns True if all items were placed, False on failure.
    """
    # sodiumRand::seed is a no-op; two RNG advances follow it
    rng.next()
    rng.next()

    end_level = 7 if level == 1 else 10

    for lv in range(level, end_level):
        base_offset = 768 if lv >= 7 else 0
        attempts = 0

        # --- Phase 1: item type 22 (primary item) ---
        room = rng.next() % 128
        while True:
            row = room // 16
            col = room % 16

            if level_grid[row][col] == lv:
                # Mask to 5 bits: the item type occupies bits 0-4 only.
                # Using & 0x1F (not & 0x7F) and drawing a fresh room at the
                # start of each phase are both corrections to decompilation
                # artifacts in the C# source. See validate_level_items for
                # defense-in-depth.
                door_byte = rom[room + base_offset + ROMOFS_DOOR_DATA] & 0x1F
                if door_byte not in _FORBIDDEN_DOOR_TYPES:
                    rom[room + base_offset + ROMOFS_DOOR_DATA] = \
                        (rom[room + base_offset + ROMOFS_DOOR_DATA] & ~0x1F) | 22
                    break

            room = rng.next() % 128
            if attempts > _MAX_ATTEMPTS:
                return False
            attempts += 1

        # --- Phase 2: item type 23 (secondary item) ---
        room = rng.next() % 128
        while True:
            row = room // 16
            col = room % 16

            if level_grid[row][col] == lv:
                door_byte = rom[room + base_offset + ROMOFS_DOOR_DATA] & 0x1F
                if door_byte not in _FORBIDDEN_DOOR_TYPES:
                    rom[room + base_offset + ROMOFS_DOOR_DATA] = \
                        (rom[room + base_offset + ROMOFS_DOOR_DATA] & ~0x1F) | 23
                    break

            room = rng.next() % 128
            if attempts > _MAX_ATTEMPTS:
                return False
            attempts += 1

        # --- Phase 3: levels 1 and 2 only — item type (level + 28) ---
        if lv == 1 or lv == 2:
            room = rng.next() % 128
            while True:
                row = room // 16
                col = room % 16

                if level_grid[row][col] == lv:
                    door_byte = rom[room + base_offset + ROMOFS_DOOR_DATA] & 0x1F
                    if door_byte not in _FORBIDDEN_DOOR_TYPES:
                        rom[room + base_offset + ROMOFS_DOOR_DATA] = \
                            (rom[room + base_offset + ROMOFS_DOOR_DATA] & ~0x1F) | (lv + 28)
                        break

                room = rng.next() % 128
                if attempts > _MAX_ATTEMPTS:
                    return False
                attempts += 1

    return True


def validate_level_items(
    rom: bytearray,
    level_grid: LevelGrid,
    start_level: int,
) -> None:
    """Verify each level has exactly the expected item rooms.

    Levels 1-8: exactly one room with door-data bits 0-4 = 22, and exactly
    one with bits 0-4 = 23. Additionally, levels 1 and 2 must each have
    one room with door-data bits 0-4 = (level + 28), i.e. 29 or 30.

    Level 9: exactly one room whose Table 4 item field (bits 0-4) equals
    Item.TRIFORCE_OF_POWER.

    Raises ItemPlacementError with all failures listed if any expectation
    is not met.
    """
    end_level = 7 if start_level == 1 else 10
    failures: list[str] = []

    for lv in range(start_level, end_level):
        base_offset = 768 if lv >= 7 else 0

        if lv == 9:
            triforce_count = 0
            for room in range(128):
                row = room // 16
                col = room % 16
                if level_grid[row][col] == lv:
                    item_byte = rom[room + base_offset + ROMOFS_DOOR_DATA] & 0x1F
                    if item_byte == Item.TRIFORCE_OF_POWER.value:
                        triforce_count += 1
            if triforce_count != 1:
                failures.append(
                    f"Level 9: TRIFORCE_OF_POWER appears {triforce_count} time(s), expected 1"
                )
        else:
            expected: dict[int, int] = {22: 1, 23: 1}
            if lv in (1, 2):
                expected[lv + 28] = 1

            counts: dict[int, int] = {t: 0 for t in expected}
            for room in range(128):
                row = room // 16
                col = room % 16
                if level_grid[row][col] == lv:
                    door_type = rom[room + base_offset + ROMOFS_DOOR_DATA] & 0x1F
                    if door_type in counts:
                        counts[door_type] += 1

            for door_type, want in expected.items():
                got = counts[door_type]
                if got != want:
                    failures.append(
                        f"Level {lv}: door type {door_type} appears {got} time(s), expected {want}"
                    )

    if failures:
        msg = "Item placement validation failed:\n" + "\n".join(
            f"  {f}" for f in failures
        )
        raise ItemPlacementError(msg)
