"""A/B testing harness comparing AssignmentSolver vs RandomizedBacktrackingSolver.

This test suite validates that both solvers produce valid solutions and compares
their performance and randomness characteristics.
"""

import sys
import time
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
log = logging.getLogger(__name__)

from logic.solvers import AssignmentSolver, RandomizedBacktrackingSolver
from logic.randomizer_constants import Item, CaveType, CavePosition
from logic.items.major_item_randomizer import DungeonLocation, CaveLocation
from logic.data_table import DataTable
from logic.flags import Flags
from logic.items.major_item_randomizer import MajorItemRandomizer
from tests.test_rom_builder import build_minimal_rom


class SolverComparisonTest:
    """Test both solvers on the same problem set."""

    def __init__(self):
        self.rom_data = build_minimal_rom('data')
        self.data_table = DataTable(self.rom_data)
        self.data_table.ResetToVanilla()

    def setup_solver_problem(self, solver_class, flags: Flags) -> Tuple:
        """Setup a solver with the major item randomizer problem.

        Args:
            solver_class: AssignmentSolver or RandomizedBacktrackingSolver
            flags: Randomizer flags

        Returns:
            Tuple of (solver, locations, items)
        """
        randomizer = MajorItemRandomizer(self.data_table, flags)
        location_item_pairs = randomizer._CollectLocationsAndItems()

        if not location_item_pairs:
            log.warning("No major items found to shuffle")
            return None, None, None

        locations = [pair.location for pair in location_item_pairs]
        items = [pair.item for pair in location_item_pairs]

        solver = solver_class()
        solver.add_permutation_problem(keys=locations, values=items, shuffle_seed=None)

        # Add constraints based on flags (simplified version)
        randomizer._AddConstraints(solver, locations, items)

        return solver, locations, items

    def test_determinism(self, solver_class, num_runs: int = 5) -> bool:
        """Test that the same seed produces the same solution.

        Args:
            solver_class: AssignmentSolver or RandomizedBacktrackingSolver
            num_runs: Number of times to run the test

        Returns:
            True if determinism is verified
        """
        log.info(f"\n{'='*80}")
        log.info(f"Testing Determinism: {solver_class.__name__}")
        log.info(f"{'='*80}")

        flags = Flags()
        test_seed = 42

        solutions = []
        for run in range(num_runs):
            self.data_table = DataTable(self.rom_reader)
            self.data_table.ResetToVanilla()

            solver, locations, items = self.setup_solver_problem(solver_class, flags)
            if solver is None:
                return False

            solution = solver.solve(seed=test_seed)
            if solution is None:
                log.error(f"  Run {run + 1}: No solution found")
                return False

            solutions.append(solution)
            log.info(f"  Run {run + 1}: Found solution with {len(solution)} items")

        # Check all solutions are identical
        first_solution = solutions[0]
        all_same = all(sol == first_solution for sol in solutions)

        if all_same:
            log.info(f"✓ Determinism verified: All {num_runs} runs produced identical solutions")
            return True
        else:
            log.error(f"✗ Determinism failed: Solutions differ across runs")
            for i, sol in enumerate(solutions):
                log.error(f"  Run {i + 1}: {sol}")
            return False

    def test_seed_independence(self, solver_class, num_seeds: int = 10) -> bool:
        """Test that different seeds produce different solutions.

        Args:
            solver_class: AssignmentSolver or RandomizedBacktrackingSolver
            num_seeds: Number of different seeds to try

        Returns:
            True if seed independence is verified
        """
        log.info(f"\n{'='*80}")
        log.info(f"Testing Seed Independence: {solver_class.__name__}")
        log.info(f"{'='*80}")

        flags = Flags()
        solutions = {}

        for seed_idx in range(num_seeds):
            self.data_table = DataTable(self.rom_reader)
            self.data_table.ResetToVanilla()

            solver, locations, items = self.setup_solver_problem(solver_class, flags)
            if solver is None:
                return False

            test_seed = 1000 + seed_idx
            solution = solver.solve(seed=test_seed)

            if solution is None:
                log.error(f"  Seed {test_seed}: No solution found")
                return False

            solutions[test_seed] = solution
            log.info(f"  Seed {test_seed}: Found solution")

        # Check that at least some solutions are different
        unique_solutions = len(set(str(s) for s in solutions.values()))
        log.info(f"  Found {unique_solutions} unique solutions out of {num_seeds} seeds")

        if unique_solutions >= num_seeds * 0.7:  # At least 70% different
            log.info(f"✓ Seed independence verified: {unique_solutions}/{num_seeds} solutions are unique")
            return True
        else:
            log.warning(f"✗ Seed independence concern: Only {unique_solutions}/{num_seeds} solutions are unique")
            return False

    def test_solution_validity(self, solver_class) -> bool:
        """Test that solutions are valid (all items placed, constraints satisfied).

        Args:
            solver_class: AssignmentSolver or RandomizedBacktrackingSolver

        Returns:
            True if solution is valid
        """
        log.info(f"\n{'='*80}")
        log.info(f"Testing Solution Validity: {solver_class.__name__}")
        log.info(f"{'='*80}")

        flags = Flags()

        self.data_table = DataTable(self.rom_reader)
        self.data_table.ResetToVanilla()

        solver, locations, items = self.setup_solver_problem(solver_class, flags)
        if solver is None:
            return False

        solution = solver.solve(seed=42)
        if solution is None:
            log.error("  No solution found")
            return False

        # Check 1: All locations have assignments
        if len(solution) != len(locations):
            log.error(f"  Solution size mismatch: {len(solution)} vs {len(locations)}")
            return False

        log.info(f"  ✓ All {len(locations)} locations have assignments")

        # Check 2: All items are used exactly once
        solution_items = list(solution.values())
        if sorted(solution_items) != sorted(items):
            log.error(f"  Items mismatch")
            return False

        log.info(f"  ✓ All items are used exactly once")

        # Check 3: No location gets an item twice (permutation property)
        if len(set(solution_items)) != len(items) and len(set(items)) == len(items):
            # Items have duplicates, so check differently
            item_counts_expected = defaultdict(int)
            item_counts_actual = defaultdict(int)
            for item in items:
                item_counts_expected[item] += 1
            for item in solution_items:
                item_counts_actual[item] += 1

            if item_counts_expected != item_counts_actual:
                log.error(f"  Item distribution mismatch")
                return False

        log.info(f"  ✓ Item counts match expected distribution")

        log.info(f"✓ Solution validity verified")
        return True

    def test_performance(self, solver_class, num_runs: int = 10) -> Tuple[float, float]:
        """Benchmark solver performance.

        Args:
            solver_class: AssignmentSolver or RandomizedBacktrackingSolver
            num_runs: Number of times to run the solver

        Returns:
            Tuple of (mean_time, std_dev)
        """
        log.info(f"\n{'='*80}")
        log.info(f"Performance Benchmark: {solver_class.__name__}")
        log.info(f"{'='*80}")

        flags = Flags()
        times = []

        for run in range(num_runs):
            self.data_table = DataTable(self.rom_reader)
            self.data_table.ResetToVanilla()

            solver, locations, items = self.setup_solver_problem(solver_class, flags)
            if solver is None:
                return None, None

            start_time = time.time()
            solution = solver.solve(seed=42 + run)
            elapsed = time.time() - start_time

            if solution is None:
                log.error(f"  Run {run + 1}: No solution found")
                return None, None

            times.append(elapsed)
            log.info(f"  Run {run + 1}: {elapsed*1000:.2f}ms")

        mean_time = sum(times) / len(times)
        variance = sum((t - mean_time) ** 2 for t in times) / len(times)
        std_dev = variance ** 0.5

        log.info(f"  Mean: {mean_time*1000:.2f}ms, StdDev: {std_dev*1000:.2f}ms")

        return mean_time, std_dev

    def run_all_tests(self) -> bool:
        """Run all comparison tests.

        Returns:
            True if all tests pass
        """
        log.info("\n" + "="*80)
        log.info("SOLVER COMPARISON TEST SUITE")
        log.info("="*80)

        all_passed = True

        # Test each solver
        for solver_class in [AssignmentSolver, RandomizedBacktrackingSolver]:
            try:
                # Determinism test
                if not self.test_determinism(solver_class):
                    all_passed = False

                # Seed independence test
                if not self.test_seed_independence(solver_class):
                    all_passed = False

                # Solution validity test
                if not self.test_solution_validity(solver_class):
                    all_passed = False

                # Performance benchmark
                mean_time, std_dev = self.test_performance(solver_class, num_runs=10)
                if mean_time is None:
                    all_passed = False

            except Exception as e:
                log.error(f"Error testing {solver_class.__name__}: {e}")
                import traceback
                traceback.print_exc()
                all_passed = False

        # Summary
        log.info("\n" + "="*80)
        if all_passed:
            log.info("✓ ALL TESTS PASSED")
        else:
            log.info("✗ SOME TESTS FAILED")
        log.info("="*80)

        return all_passed


def main():
    """Run the comparison tests."""
    try:
        tester = SolverComparisonTest()
        success = tester.run_all_tests()
        return 0 if success else 1
    except Exception as e:
        log.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
