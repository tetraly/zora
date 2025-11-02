"""Tests for AssignmentSolver wrapper."""

import sys
import os
import pytest

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from logic.assignment_solver import AssignmentSolver, ORTOOLS_AVAILABLE
except ImportError:
    ORTOOLS_AVAILABLE = False


@pytest.mark.skipif(not ORTOOLS_AVAILABLE, reason="OR-Tools not installed")
def test_basic_assignment():
    """Test basic one-to-one assignment without constraints."""
    solver = AssignmentSolver()

    sources = ["A", "B", "C"]
    targets = [1, 2, 3]

    solver.add_assignment_problem(sources, targets)
    solution = solver.solve(seed=42)

    assert solution is not None
    assert len(solution) == 3
    assert set(solution.values()) == {1, 2, 3}  # All targets used
    assert set(solution.keys()) == {"A", "B", "C"}  # All sources assigned


@pytest.mark.skipif(not ORTOOLS_AVAILABLE, reason="OR-Tools not installed")
def test_require_constraint():
    """Test forcing a specific assignment."""
    solver = AssignmentSolver()

    sources = ["A", "B", "C"]
    targets = [1, 2, 3]

    solver.add_assignment_problem(sources, targets)
    solver.require("A", 1)  # Force A -> 1

    solution = solver.solve(seed=42)

    assert solution is not None
    assert solution["A"] == 1  # A must be 1
    assert set(solution.values()) == {1, 2, 3}  # All targets used


@pytest.mark.skipif(not ORTOOLS_AVAILABLE, reason="OR-Tools not installed")
def test_forbid_constraint():
    """Test preventing a specific assignment."""
    solver = AssignmentSolver()

    sources = ["A", "B"]
    targets = [1, 2]

    solver.add_assignment_problem(sources, targets)
    solver.forbid("A", 1)  # A cannot be 1

    solution = solver.solve(seed=42)

    assert solution is not None
    assert solution["A"] == 2  # A must be 2 (only option left)
    assert solution["B"] == 1  # B must be 1


@pytest.mark.skipif(not ORTOOLS_AVAILABLE, reason="OR-Tools not installed")
def test_allow_only_constraint():
    """Test restricting sources to specific targets."""
    solver = AssignmentSolver()

    sources = ["LEVEL_1", "LEVEL_2", "CAVE_A", "CAVE_B"]
    targets = [0x10, 0x20, 0x30, 0x40]

    solver.add_assignment_problem(sources, targets)

    # Levels can only go to 0x10 or 0x20
    solver.allow_only(["LEVEL_1", "LEVEL_2"], [0x10, 0x20])

    solution = solver.solve(seed=42)

    assert solution is not None
    # Levels must be in allowed targets
    assert solution["LEVEL_1"] in [0x10, 0x20]
    assert solution["LEVEL_2"] in [0x10, 0x20]
    # Caves must be in remaining targets
    assert solution["CAVE_A"] in [0x30, 0x40]
    assert solution["CAVE_B"] in [0x30, 0x40]


@pytest.mark.skipif(not ORTOOLS_AVAILABLE, reason="OR-Tools not installed")
def test_forbid_group_constraint():
    """Test preventing sources from a group of targets."""
    solver = AssignmentSolver()

    sources = ["A", "B", "C"]
    targets = [1, 2, 3]

    solver.add_assignment_problem(sources, targets)
    solver.forbid_group("A", [1, 2])  # A cannot be 1 or 2

    solution = solver.solve(seed=42)

    assert solution is not None
    assert solution["A"] == 3  # A must be 3 (only option)


@pytest.mark.skipif(not ORTOOLS_AVAILABLE, reason="OR-Tools not installed")
def test_contradictory_constraints():
    """Test that contradictory constraints return None."""
    solver = AssignmentSolver()

    sources = ["A"]
    targets = [1]

    solver.add_assignment_problem(sources, targets)
    solver.require("A", 1)
    solver.forbid("A", 1)  # Contradiction!

    solution = solver.solve(seed=42)

    assert solution is None  # No valid solution


@pytest.mark.skipif(not ORTOOLS_AVAILABLE, reason="OR-Tools not installed")
def test_deterministic_solving():
    """Test that same seed produces same solution."""
    sources = ["A", "B", "C", "D"]
    targets = [1, 2, 3, 4]

    # Solve twice with same seed
    solver1 = AssignmentSolver()
    solver1.add_assignment_problem(sources, targets)
    solution1 = solver1.solve(seed=12345)

    solver2 = AssignmentSolver()
    solver2.add_assignment_problem(sources, targets)
    solution2 = solver2.solve(seed=12345)

    assert solution1 == solution2  # Same seed = same solution


@pytest.mark.skipif(not ORTOOLS_AVAILABLE, reason="OR-Tools not installed")
def test_cave_shuffling_scenario():
    """Test realistic cave shuffling scenario with 3 constraint types."""
    # Simulate constraint #3: 9 levels in 15 screens, other caves in remaining
    levels = [f"LEVEL_{i}" for i in range(1, 10)]  # 9 levels
    other_caves = ["WOOD_SWORD", "SHOP_1", "SHOP_2"]  # 3 other caves
    all_sources = levels + other_caves  # 12 total sources

    expanded_level_screens = list(range(0x10, 0x1F))  # 15 screens for levels
    other_screens = list(range(0x20, 0x23))  # 3 screens for other caves
    all_targets = expanded_level_screens + other_screens  # 18 total targets... wait

    # Actually need exactly 12 targets for 12 sources
    level_screen_pool = list(range(0x10, 0x19))  # 9 screens
    extra_level_screens = list(range(0x19, 0x1F))  # 6 more = 15 total
    other_screens = list(range(0x20, 0x23))  # 3 screens

    all_level_screens = level_screen_pool + extra_level_screens  # 15 screens
    all_targets = level_screen_pool + extra_level_screens + other_screens  # 18 screens

    # But we only have 12 sources, so we need exactly 12 targets
    # Let's pick 12 screens total
    all_targets = list(range(0x10, 0x1C))  # 12 screens

    solver = AssignmentSolver()
    solver.add_assignment_problem(all_sources, all_targets)

    # Constraint #1: Wood sword must be at specific screen
    solver.require("WOOD_SWORD", 0x10)

    # Constraint #3: Levels can only go to expanded screen pool (say first 9 screens)
    level_pool = list(range(0x11, 0x1A))  # 9 screens (excluding 0x10 which is wood sword)
    solver.allow_only(levels, level_pool)

    solution = solver.solve(seed=42)

    assert solution is not None
    assert solution["WOOD_SWORD"] == 0x10  # Pinned
    # All levels in allowed pool
    for level in levels:
        assert solution[level] in level_pool


@pytest.mark.skipif(not ORTOOLS_AVAILABLE, reason="OR-Tools not installed")
def test_mismatched_lengths():
    """Test that mismatched source/target lengths raise error."""
    solver = AssignmentSolver()

    sources = ["A", "B"]
    targets = [1, 2, 3]  # Too many targets

    with pytest.raises(ValueError, match="must have same length"):
        solver.add_assignment_problem(sources, targets)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
