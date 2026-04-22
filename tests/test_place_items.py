"""Tests for new_level_place_items fix and validate_level_items."""

from __future__ import annotations

import pytest

from zora.data_model import Item
from zora.level_gen.place_items import (
    ItemPlacementError,
    new_level_place_items,
    validate_level_items,
)
from zora.level_gen.rom_buffer import (
    GRID_COLS,
    GRID_ROWS,
    LevelGrid,
    ROMOFS_DOOR_DATA,
)
from zora.level_gen.test_xorshift import Xorshift32


def _make_level_grid(level_assignments: dict[int, int]) -> LevelGrid:
    """Build a level grid where specific rooms are assigned to specific levels."""
    grid: LevelGrid = [[0] * GRID_COLS for _ in range(GRID_ROWS)]
    for room, lv in level_assignments.items():
        row = room // 16
        col = room % 16
        grid[row][col] = lv
    return grid


def _make_rom(size: int = 110000) -> bytearray:
    return bytearray(size)


def _set_door_byte(rom: bytearray, room: int, value: int, base_offset: int = 0) -> None:
    rom[room + base_offset + ROMOFS_DOOR_DATA] = value


def _get_door_byte(rom: bytearray, room: int, base_offset: int = 0) -> int:
    return rom[room + base_offset + ROMOFS_DOOR_DATA]


class TestFixRegressionBug:
    """Phase 1 stamping a room with nonzero bits 5-6 no longer causes
    Phase 2 to overwrite the same room."""

    def test_phases_produce_distinct_rooms(self) -> None:
        """With the fix, Phase 2 draws a fresh room instead of reusing
        Phase 1's room, preventing duplicate item types."""
        rom = _make_rom()

        # Assign 5 rooms per level for levels 1-6
        assignments: dict[int, int] = {}
        for lv in range(1, 7):
            for i in range(5):
                room = (lv - 1) * 10 + i
                assignments[room] = lv
        grid = _make_level_grid(assignments)

        # Set bits 5-6 on the first room of each level
        for lv in range(1, 7):
            room = (lv - 1) * 10
            _set_door_byte(rom, room, 0x60)

        # Use a real Rng so the test exercises the actual code path
        rng = Xorshift32(42)
        result = new_level_place_items(rom, rng, 1, grid)
        assert result is True

        # Verify each level has exactly one item 22 and one item 23
        for lv in range(1, 7):
            counts: dict[int, int] = {22: 0, 23: 0}
            for room, assigned_lv in assignments.items():
                if assigned_lv == lv:
                    door_type = _get_door_byte(rom, room) & 0x1F
                    if door_type in counts:
                        counts[door_type] += 1
            assert counts[22] == 1, f"Level {lv}: expected 1 room with item 22, got {counts[22]}"
            assert counts[23] == 1, f"Level {lv}: expected 1 room with item 23, got {counts[23]}"

        # Levels 1 and 2 should also have their bonus items
        for lv in (1, 2):
            bonus_type = lv + 28
            count = 0
            for room, assigned_lv in assignments.items():
                if assigned_lv == lv:
                    if _get_door_byte(rom, room) & 0x1F == bonus_type:
                        count += 1
            assert count == 1, f"Level {lv}: expected 1 room with item {bonus_type}, got {count}"


class TestValidatorHappyPath:
    def test_correctly_placed_levels_pass(self) -> None:
        rom = _make_rom()
        assignments: dict[int, int] = {}
        for lv in range(1, 7):
            for i in range(5):
                assignments[(lv - 1) * 10 + i] = lv
        grid = _make_level_grid(assignments)

        # Stamp exactly one room per level with item 22 and another with 23
        for lv in range(1, 7):
            base_room = (lv - 1) * 10
            _set_door_byte(rom, base_room, 22)
            _set_door_byte(rom, base_room + 1, 23)
            if lv in (1, 2):
                _set_door_byte(rom, base_room + 2, lv + 28)

        validate_level_items(rom, grid, 1)  # should not raise


class TestValidatorCatchesDuplicates:
    def test_duplicate_item_22(self) -> None:
        rom = _make_rom()
        assignments = {0: 3, 1: 3, 2: 3, 3: 3, 4: 3}
        # Also need levels 1-2, 4-6 to be valid
        for lv in range(1, 7):
            if lv == 3:
                continue
            base = lv * 20
            assignments[base] = lv
            assignments[base + 1] = lv
            assignments[base + 2] = lv
            _set_door_byte(rom, base, 22)
            _set_door_byte(rom, base + 1, 23)
            if lv in (1, 2):
                _set_door_byte(rom, base + 2, lv + 28)

        grid = _make_level_grid(assignments)

        # Level 3: two rooms with item 22, zero with 23
        _set_door_byte(rom, 0, 22)
        _set_door_byte(rom, 1, 22)

        with pytest.raises(ItemPlacementError, match="Level 3.*door type 22.*2 time"):
            validate_level_items(rom, grid, 1)


class TestValidatorCatchesMissing:
    def test_missing_item_23(self) -> None:
        rom = _make_rom()
        assignments: dict[int, int] = {}
        for lv in range(1, 7):
            base = lv * 20
            for i in range(3):
                assignments[base + i] = lv

        grid = _make_level_grid(assignments)

        for lv in range(1, 7):
            base = lv * 20
            _set_door_byte(rom, base, 22)
            # No item 23 for level 5
            if lv != 5:
                _set_door_byte(rom, base + 1, 23)
            if lv in (1, 2):
                _set_door_byte(rom, base + 2, lv + 28)

        with pytest.raises(ItemPlacementError, match="Level 5.*door type 23.*0 time"):
            validate_level_items(rom, grid, 1)


class TestValidatorLevel9:
    def test_missing_triforce(self) -> None:
        rom = _make_rom()
        base_offset = 768
        assignments = {0: 9, 1: 9, 2: 9}
        # Also need valid levels 7 and 8
        for lv in (7, 8):
            base_room = lv * 10
            assignments[base_room] = lv
            assignments[base_room + 1] = lv
            _set_door_byte(rom, base_room, 22, base_offset)
            _set_door_byte(rom, base_room + 1, 23, base_offset)

        grid = _make_level_grid(assignments)
        # No TRIFORCE_OF_POWER in any level 9 room

        with pytest.raises(ItemPlacementError, match="Level 9.*TRIFORCE_OF_POWER.*0 time"):
            validate_level_items(rom, grid, 7)

    def test_multiple_triforce(self) -> None:
        rom = _make_rom()
        base_offset = 768
        assignments = {0: 9, 1: 9, 2: 9}
        for lv in (7, 8):
            base_room = lv * 10
            assignments[base_room] = lv
            assignments[base_room + 1] = lv
            _set_door_byte(rom, base_room, 22, base_offset)
            _set_door_byte(rom, base_room + 1, 23, base_offset)

        grid = _make_level_grid(assignments)

        # Two rooms with TRIFORCE_OF_POWER
        _set_door_byte(rom, 0, Item.TRIFORCE_OF_POWER.value, base_offset)
        _set_door_byte(rom, 1, Item.TRIFORCE_OF_POWER.value, base_offset)

        with pytest.raises(ItemPlacementError, match="Level 9.*TRIFORCE_OF_POWER.*2 time"):
            validate_level_items(rom, grid, 7)


class TestValidatorReportsAllFailures:
    def test_multiple_failures_in_message(self) -> None:
        rom = _make_rom()
        assignments: dict[int, int] = {}
        for lv in range(1, 7):
            base = lv * 20
            for i in range(3):
                assignments[base + i] = lv

        grid = _make_level_grid(assignments)

        # Level 3: duplicate 22, missing 23
        _set_door_byte(rom, 60, 22)
        _set_door_byte(rom, 61, 22)
        # Other levels valid
        for lv in range(1, 7):
            if lv == 3:
                continue
            base = lv * 20
            _set_door_byte(rom, base, 22)
            _set_door_byte(rom, base + 1, 23)
            if lv in (1, 2):
                _set_door_byte(rom, base + 2, lv + 28)

        with pytest.raises(ItemPlacementError) as exc_info:
            validate_level_items(rom, grid, 1)

        msg = str(exc_info.value)
        assert "door type 22 appears 2" in msg
        assert "door type 23 appears 0" in msg


class TestValidatorLevelRanges:
    def test_start_level_1_checks_1_through_6(self) -> None:
        """start_level=1 validates levels 1-6, not 7-9."""
        rom = _make_rom()
        assignments: dict[int, int] = {}
        for lv in range(1, 7):
            base = lv * 20
            for i in range(3):
                assignments[base + i] = lv
            _set_door_byte(rom, base, 22)
            _set_door_byte(rom, base + 1, 23)
            if lv in (1, 2):
                _set_door_byte(rom, base + 2, lv + 28)

        grid = _make_level_grid(assignments)
        # Should pass — levels 1-6 are valid, levels 7-9 not checked
        validate_level_items(rom, grid, 1)

    def test_start_level_7_checks_7_through_9(self) -> None:
        """start_level=7 validates levels 7-9, not 1-6."""
        rom = _make_rom()
        base_offset = 768
        assignments: dict[int, int] = {}

        for lv in (7, 8):
            base_room = lv * 10
            assignments[base_room] = lv
            assignments[base_room + 1] = lv
            _set_door_byte(rom, base_room, 22, base_offset)
            _set_door_byte(rom, base_room + 1, 23, base_offset)

        # Level 9 with triforce
        assignments[0] = 9
        _set_door_byte(rom, 0, Item.TRIFORCE_OF_POWER.value, base_offset)

        grid = _make_level_grid(assignments)
        # Should pass — levels 7-9 valid, levels 1-6 not checked
        validate_level_items(rom, grid, 7)

    def test_start_level_7_ignores_bad_level_1(self) -> None:
        """start_level=7 does not catch problems in levels 1-6."""
        rom = _make_rom()
        base_offset = 768
        assignments: dict[int, int] = {}

        # Level 1 is broken (no items) but in the other grid
        assignments[100] = 1

        for lv in (7, 8):
            base_room = lv * 10
            assignments[base_room] = lv
            assignments[base_room + 1] = lv
            _set_door_byte(rom, base_room, 22, base_offset)
            _set_door_byte(rom, base_room + 1, 23, base_offset)

        assignments[0] = 9
        _set_door_byte(rom, 0, Item.TRIFORCE_OF_POWER.value, base_offset)

        grid = _make_level_grid(assignments)
        validate_level_items(rom, grid, 7)  # should not raise
