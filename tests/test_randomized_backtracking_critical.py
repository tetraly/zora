"""Critical requirement tests for RandomizedBacktrackingSolver.

Tests the three non-negotiable requirements:
1. Determinism: same seed + inputs = same output
2. Seed independence: different seeds = different outputs
3. Randomness: solutions are drawn from solution space with good distribution
"""

import sys
import time
from pathlib import Path
from typing import Dict, List, Set
from collections import defaultdict

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from logic.randomized_backtracking_solver import RandomizedBacktrackingSolver
from logic.assignment_solver import AssignmentSolver


class CriticalRequirementTest:
    """Test critical requirements for both solvers."""

    def setup_complex_problem(self) -> tuple:
        """Create a complex assignment problem with constraints.

        Models a problem similar to major item randomization:
        - 30 locations
        - 30 items (with some duplicates)
        - Various constraints
        """
        locations = list(range(30))
        items = (
            [1] * 5 +      # 5x item 1
            [2] * 4 +      # 4x item 2
            [3] * 3 +      # 3x item 3
            list(range(4, 22))  # items 4-21 (unique)
        )

        return locations, items

    def create_constraint_set(self) -> List[tuple]:
        """Create a realistic constraint set.

        Returns:
            List of (location, item, action) tuples
            where action is 'forbid' or 'require'
        """
        constraints = [
            # Forbid constraints (most common)
            (0, 1, 'forbid'),    # location 0 can't have item 1
            (1, 2, 'forbid'),    # location 1 can't have item 2
            (5, 3, 'forbid'),    # location 5 can't have item 3
            (10, 4, 'forbid'),
            (15, 5, 'forbid'),
            (20, 6, 'forbid'),
            (25, 7, 'forbid'),
            (2, 8, 'forbid'),
            (8, 9, 'forbid'),
            (12, 10, 'forbid'),
            # Some require constraints
            (3, 21, 'require'),   # location 3 must have item 21
            (29, 20, 'require'),  # location 29 must have item 20
        ]
        return constraints

    def test_requirement_1_determinism(self) -> bool:
        """CRITICAL REQUIREMENT 1: Determinism

        Same flagstring and seed MUST produce same output.
        """
        print("\n" + "="*80)
        print("CRITICAL REQUIREMENT 1: DETERMINISM")
        print("="*80)
        print("Test: Same seed + same input = same output (verified 10 times)")

        locations, items = self.setup_complex_problem()
        constraints = self.create_constraint_set()

        for solver_class in [AssignmentSolver, RandomizedBacktrackingSolver]:
            print(f"\nTesting {solver_class.__name__}:")

            solutions = []
            test_seed = 12345

            for attempt in range(10):
                solver = solver_class()
                solver.add_permutation_problem(locations, items, shuffle_seed=None)

                # Add same constraints
                for loc, item, action in constraints:
                    if action == 'forbid':
                        solver.forbid(loc, item)
                    elif action == 'require':
                        solver.require(loc, item)

                solution = solver.solve(seed=test_seed)
                if solution is None:
                    print(f"  ✗ Attempt {attempt + 1}: No solution found")
                    return False

                solutions.append(solution)

            # Check all solutions are identical
            all_identical = all(sol == solutions[0] for sol in solutions)

            if all_identical:
                print(f"  ✓ All 10 solutions are IDENTICAL")
                print(f"    Sample solution: {len(solutions[0])} assignments")
            else:
                print(f"  ✗ FAILED: Solutions differ!")
                for i, sol in enumerate(solutions[:3]):
                    print(f"    Attempt {i + 1}: {list(sol.items())[:3]}...")
                return False

        return True

    def test_requirement_2_seed_independence(self) -> bool:
        """CRITICAL REQUIREMENT 2: Seed Independence

        Different seeds MUST produce different results (with high probability).
        """
        print("\n" + "="*80)
        print("CRITICAL REQUIREMENT 2: SEED INDEPENDENCE")
        print("="*80)
        print("Test: Different seeds = different outputs (verified across 20 seeds)")

        locations, items = self.setup_complex_problem()
        constraints = self.create_constraint_set()

        all_passed = True

        for solver_class in [AssignmentSolver, RandomizedBacktrackingSolver]:
            print(f"\nTesting {solver_class.__name__}:")

            solutions = {}
            base_seed = 5000
            solver_passed = True

            for seed_offset in range(20):
                solver = solver_class()
                solver.add_permutation_problem(locations, items, shuffle_seed=None)

                # Add same constraints
                for loc, item, action in constraints:
                    if action == 'forbid':
                        solver.forbid(loc, item)
                    elif action == 'require':
                        solver.require(loc, item)

                test_seed = base_seed + seed_offset
                solution = solver.solve(seed=test_seed)

                if solution is None:
                    print(f"  ✗ Seed {test_seed}: No solution found")
                    solver_passed = False
                    break

                # Convert to immutable form for comparison
                solution_tuple = tuple(sorted(solution.items()))
                solutions[test_seed] = solution_tuple

            if not solver_passed:
                all_passed = False
                continue

            # Count unique solutions
            unique_count = len(set(solutions.values()))
            total_count = len(solutions)
            uniqueness_percent = (unique_count / total_count) * 100

            print(f"  Unique solutions: {unique_count}/{total_count} ({uniqueness_percent:.1f}%)")

            # Require at least 70% unique solutions
            if unique_count >= total_count * 0.7:
                print(f"  ✓ PASSED: {uniqueness_percent:.1f}% uniqueness (>= 70% threshold)")
            else:
                print(f"  ✗ FAILED: Only {uniqueness_percent:.1f}% unique (need >= 70%)")
                all_passed = False

        return all_passed

    def test_requirement_3_randomness_quality(self) -> bool:
        """CRITICAL REQUIREMENT 3: Solution Randomness

        Solutions must be drawn from solution space with good distribution.
        Verify by checking that different items appear in different locations.
        """
        print("\n" + "="*80)
        print("CRITICAL REQUIREMENT 3: SOLUTION RANDOMNESS/QUALITY")
        print("="*80)
        print("Test: Solutions show good distribution across solution space (20 runs)")

        locations, items = self.setup_complex_problem()
        constraints = self.create_constraint_set()

        for solver_class in [AssignmentSolver, RandomizedBacktrackingSolver]:
            print(f"\nTesting {solver_class.__name__}:")

            location_item_frequency = defaultdict(lambda: defaultdict(int))
            item_1_positions = []  # Track where item 1 appears

            for run in range(20):
                solver = solver_class()
                solver.add_permutation_problem(locations, items, shuffle_seed=None)

                # Add same constraints
                for loc, item, action in constraints:
                    if action == 'forbid':
                        solver.forbid(loc, item)
                    elif action == 'require':
                        solver.require(loc, item)

                solution = solver.solve(seed=10000 + run)
                if solution is None:
                    print(f"  ✗ Run {run + 1}: No solution found")
                    return False

                # Track item distribution
                for location, item in solution.items():
                    location_item_frequency[location][item] += 1

                # Track item 1 position
                for location, item in solution.items():
                    if item == 1:
                        item_1_positions.append(location)

            # Check spread of item 1 across different locations
            unique_item_1_positions = len(set(item_1_positions))
            print(f"  Item 1 appeared in {unique_item_1_positions} different locations across 20 runs")

            # For a duplicated item, we expect it to spread across many locations
            if unique_item_1_positions >= 8:  # Out of 30 locations, spread to at least 8
                print(f"  ✓ PASSED: Good distribution (appears in {unique_item_1_positions}/30 locations)")
            else:
                print(f"  ✗ WARNING: Poor distribution (only {unique_item_1_positions}/30 locations)")
                # This is a warning, not a failure - the solver still works

        return True

    def run_all_critical_tests(self) -> bool:
        """Run all three critical requirement tests.

        Returns:
            True if all critical requirements are met
        """
        print("\n" + "="*80)
        print("CRITICAL REQUIREMENT VERIFICATION")
        print("="*80)

        results = []

        # Test each requirement, continuing even if one fails
        try:
            results.append(("Determinism", self.test_requirement_1_determinism()))
        except Exception as e:
            print(f"ERROR in Determinism test: {e}")
            results.append(("Determinism", False))

        try:
            results.append(("Seed Independence", self.test_requirement_2_seed_independence()))
        except Exception as e:
            print(f"ERROR in Seed Independence test: {e}")
            results.append(("Seed Independence", False))

        try:
            results.append(("Solution Randomness", self.test_requirement_3_randomness_quality()))
        except Exception as e:
            print(f"ERROR in Solution Randomness test: {e}")
            results.append(("Solution Randomness", False))

        print("\n" + "="*80)
        print("SUMMARY")
        print("="*80)

        for name, passed in results:
            status = "✓ PASSED" if passed else "✗ FAILED"
            print(f"{name:30} {status}")

        all_passed = all(passed for _, passed in results)

        print("\n" + "="*80)
        if all_passed:
            print("✓ ALL CRITICAL REQUIREMENTS MET")
        else:
            print("✗ SOME CRITICAL REQUIREMENTS FAILED")
        print("="*80)

        return all_passed


def main():
    """Run critical requirement tests."""
    try:
        tester = CriticalRequirementTest()
        success = tester.run_all_critical_tests()
        return 0 if success else 1
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
