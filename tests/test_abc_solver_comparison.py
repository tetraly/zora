"""A/B/C testing script for comparing all three solvers.

This script lets you easily test and compare the performance of:
- AssignmentSolver (OR-Tools)
- RandomizedBacktrackingSolver
- RejectionSamplingSolver

Run with: python tests/test_abc_solver_comparison.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from logic.solvers import SolverType
from logic.solvers.solver_factory import create_solver, list_available_solvers


class ABCTest:
    """A/B/C testing harness for solvers."""

    def __init__(self, num_locations=250, num_items=30):
        """Initialize test with problem size.

        Args:
            num_locations: Number of locations to shuffle
            num_items: Number of unique items
        """
        self.num_locations = num_locations
        self.num_items = num_items

        # Create problem
        self.locations = list(range(num_locations))

        # Create items with duplicates
        unique_items = list(range(num_items))
        items = unique_items.copy()
        while len(items) < num_locations:
            items.append(unique_items[-1])  # Duplicate last item

        self.items = items

        # Create some constraints
        self.constraints = [
            (0, 1, 'forbid'),
            (5, 2, 'forbid'),
            (10, 3, 'forbid'),
            (3, num_items - 2, 'require'),
            (num_locations - 1, num_items - 1, 'require'),
        ]

    def test_solver(self, solver_type, num_runs=5):
        """Test a specific solver.

        Args:
            solver_type: SolverType to test
            num_runs: Number of times to run

        Returns:
            Dict with results or None if failed
        """
        print(f"\n{'='*70}")
        print(f"Testing: {solver_type}")
        print(f"Problem: {self.num_locations} locations, {self.num_items} items")
        print(f"{'='*70}")

        times = []
        success_count = 0

        for run in range(num_runs):
            try:
                solver = create_solver(solver_type)
            except ImportError as e:
                print(f"✗ Cannot create solver: {e}")
                return None

            solver.add_permutation_problem(self.locations, self.items)

            # Add constraints
            for source, target, action in self.constraints:
                if action == 'forbid':
                    solver.forbid(source, target)
                elif action == 'require':
                    solver.require(source, target)

            # Solve and time it
            start = time.time()
            solution = solver.solve(seed=1000 + run)
            elapsed = time.time() - start

            if solution is None:
                print(f"  Run {run + 1}: ✗ NO SOLUTION FOUND ({elapsed*1000:.3f}ms)")
                continue

            # Validate solution
            if not self._validate_solution(solution):
                print(f"  Run {run + 1}: ✗ INVALID SOLUTION ({elapsed*1000:.3f}ms)")
                continue

            times.append(elapsed)
            success_count += 1
            print(f"  Run {run + 1}: ✓ {elapsed*1000:.3f}ms")

        print()

        if success_count == 0:
            print(f"✗ FAILED: No successful solutions found")
            return None

        avg_time = sum(times) / len(times)
        min_time = min(times)
        max_time = max(times)

        print(f"✓ Success rate: {success_count}/{num_runs}")
        print(f"  Average time: {avg_time*1000:.3f}ms")
        print(f"  Min time:     {min_time*1000:.3f}ms")
        print(f"  Max time:     {max_time*1000:.3f}ms")

        return {
            "solver_type": solver_type,
            "success_count": success_count,
            "avg_time": avg_time,
            "min_time": min_time,
            "max_time": max_time,
        }

    def _validate_solution(self, solution):
        """Validate that a solution satisfies all constraints.

        Args:
            solution: Dictionary mapping location -> item

        Returns:
            True if solution is valid, False otherwise
        """
        # Check all locations have assignments
        if len(solution) != self.num_locations:
            return False

        # Check all items are used
        solution_items = list(solution.values())
        if sorted(solution_items) != sorted(self.items):
            return False

        # Check required constraints
        for source, target, action in self.constraints:
            if action == 'require':
                if solution.get(source) != target:
                    return False
            elif action == 'forbid':
                if solution.get(source) == target:
                    return False

        return True

    def run_all_tests(self):
        """Run A/B/C tests for all available solvers."""
        print("\n" + "="*70)
        print("A/B/C SOLVER COMPARISON")
        print("="*70)

        # Check availability
        print("\nChecking solver availability:")
        available_solvers = []
        for solver_type, available in list_available_solvers():
            status = "✓ Available" if available else "✗ Missing dependencies"
            print(f"  {str(solver_type):40} {status}")
            if available:
                available_solvers.append(solver_type)

        if not available_solvers:
            print("\n✗ No solvers available!")
            return False

        # Run tests
        results = {}
        for solver_type in available_solvers:
            result = self.test_solver(solver_type, num_runs=5)
            if result:
                results[str(solver_type)] = result

        # Compare results
        if not results:
            print("\n✗ All tests failed!")
            return False

        print("\n" + "="*70)
        print("COMPARISON SUMMARY")
        print("="*70)

        # Sort by average time
        sorted_results = sorted(results.items(), key=lambda x: x[1]['avg_time'])

        print(f"\n{'Solver':<40} {'Avg Time':>12} {'Min Time':>12} {'Max Time':>12}")
        print("-" * 78)

        fastest_time = sorted_results[0][1]['avg_time'] if sorted_results else 1
        for name, result in sorted_results:
            avg_ms = result['avg_time'] * 1000
            min_ms = result['min_time'] * 1000
            max_ms = result['max_time'] * 1000
            speedup = fastest_time / result['avg_time'] if result['avg_time'] > 0 else 1

            speedup_str = f"({speedup:.1f}x)" if speedup > 1 else ""
            print(f"{name:<40} {avg_ms:>10.3f}ms {min_ms:>10.3f}ms {max_ms:>10.3f}ms {speedup_str}")

        print("\n" + "="*70)
        print("RECOMMENDATIONS")
        print("="*70)

        fastest = sorted_results[0] if sorted_results else None
        if fastest:
            print(f"\n✓ Fastest: {fastest[0]}")
            print(f"  Average time: {fastest[1]['avg_time']*1000:.3f}ms")

        print("\nFor your 30-location major item randomizer:")
        print("  → RejectionSamplingSolver: Smallest code, fastest")
        print("  → RandomizedBacktracking:  Good for tight constraints")
        print("  → AssignmentSolver:        Most robust (requires OR-Tools)")

        return True


def main():
    """Run A/B/C tests."""
    try:
        # Test with 250 locations (your actual use case)
        tester = ABCTest(num_locations=250, num_items=30)
        success = tester.run_all_tests()
        return 0 if success else 1
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
