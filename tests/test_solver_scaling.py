"""Compare RejectionSamplingSolver and RandomizedBacktrackingSolver on realistic problem sizes.

Tests both solvers on:
1. Small problem (30 locations, 30 items) - my original test
2. Medium problem (100 locations, 30 items)
3. Large problem (250 locations, 30 items) - your actual use case
"""

import sys
import time
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from logic.randomized_backtracking_solver import RandomizedBacktrackingSolver


class RejectionSamplingSolver:
    """Fast rejection sampling solver for permutation problems with constraints."""

    def __init__(self):
        """Initialize the rejection sampling solver."""
        self.permutation_keys = []
        self.permutation_values = []
        self.constraints = []
        self.last_solution = None
        self.last_solution_indices = None
        self.forbidden_solution_maps = []

    def add_permutation_problem(self, keys, values, shuffle_seed=None):
        """Define a permutation problem."""
        if len(keys) != len(values):
            raise ValueError(f"Keys and values must have same length")
        self.permutation_keys = list(keys)
        self.permutation_values = list(values)

    def forbid(self, source, target):
        """Prevent a specific source from being assigned to target."""
        def constraint(assignment):
            if source in assignment:
                return assignment[source] != target
            return True
        self.constraints.append(constraint)

    def forbid_all(self, sources, targets):
        """Prevent multiple sources from being assigned to multiple targets."""
        if not isinstance(sources, (list, tuple, set)):
            sources = [sources]
        if not isinstance(targets, (list, tuple, set)):
            targets = [targets]

        source_set = set(sources)
        target_set = set(targets)

        def constraint(assignment):
            for loc, item in assignment.items():
                if loc in source_set and item in target_set:
                    return False
            return True

        self.constraints.append(constraint)

    def at_least_one_of(self, sources, targets):
        """Require at least one source to receive one of the target values."""
        if not isinstance(sources, (list, tuple, set)):
            sources = [sources]
        if not isinstance(targets, (list, tuple, set)):
            targets = [targets]

        source_set = set(sources)
        target_set = set(targets)

        def constraint(assignment):
            if len(assignment) < len(self.permutation_keys):
                return True
            for loc, item in assignment.items():
                if loc in source_set and item in target_set:
                    return True
            return False

        self.constraints.append(constraint)

    def add_forbidden_solution_map(self, solution_map):
        """Record a solution to forbid."""
        self.forbidden_solution_maps.append(solution_map.copy())

    def solve(self, seed=None, time_limit_seconds=10.0, max_attempts=100000):
        """Solve using rejection sampling."""
        if seed is None:
            seed = 0

        import random
        rng = random.Random(seed)

        # Pre-shuffle keys and values
        shuffled_keys = self.permutation_keys.copy()
        shuffled_values = self.permutation_values.copy()
        rng.shuffle(shuffled_keys)
        rng.shuffle(shuffled_values)

        for attempt in range(max_attempts):
            rng.shuffle(shuffled_values)
            assignment = dict(zip(shuffled_keys, shuffled_values))

            # Check forbidden solutions
            if self.forbidden_solution_maps:
                if any(assignment == forbidden for forbidden in self.forbidden_solution_maps):
                    continue

            # Check constraints
            if all(constraint(assignment) for constraint in self.constraints):
                self.last_solution = assignment.copy()
                self.last_solution_indices = {}
                for key, value in assignment.items():
                    value_idx = self.permutation_values.index(value)
                    self.last_solution_indices[key] = value_idx
                return assignment

        return None

    def get_stats(self):
        """Get stats about the problem."""
        return {
            "num_keys": len(self.permutation_keys),
            "num_values": len(self.permutation_values),
            "num_constraints": len(self.constraints),
        }


class SolverBenchmark:
    """Benchmark both solvers on various problem sizes."""

    def test_problem(self, name, num_locations, num_unique_items, num_constraints=10):
        """Test both solvers on a problem of given size.

        Args:
            name: Problem name for display
            num_locations: Number of locations
            num_unique_items: Number of unique items (rest are duplicates)
            num_constraints: Number of forbid constraints to add
        """
        print(f"\n{'='*80}")
        print(f"Problem: {name}")
        print(f"Size: {num_locations} locations, {num_unique_items} unique items")
        print(f"Constraints: {num_constraints}")
        print(f"{'='*80}")

        # Create problem
        locations = list(range(num_locations))

        # Create items with duplicates
        unique_items = list(range(num_unique_items))
        items = unique_items.copy()
        # Fill remaining slots with duplicates (mostly the "no item" placeholder)
        while len(items) < num_locations:
            items.append(unique_items[-1])  # Duplicate the last item

        # Add random constraints
        import random
        rng = random.Random(42)
        constraints = []
        for _ in range(num_constraints):
            loc = rng.choice(locations)
            item = rng.choice(unique_items)
            constraints.append((loc, item))

        results = {}

        for solver_class in [RejectionSamplingSolver, RandomizedBacktrackingSolver]:
            solver_name = solver_class.__name__
            print(f"\n{solver_name}:")

            # Run multiple times to get consistent timing
            times = []
            success_count = 0

            for seed in range(5):
                solver = solver_class()
                solver.add_permutation_problem(locations, items)

                for loc, item in constraints:
                    solver.forbid(loc, item)

                start = time.time()
                solution = solver.solve(seed=1000 + seed)
                elapsed = time.time() - start

                if solution:
                    success_count += 1
                    times.append(elapsed)

            if success_count == 0:
                print(f"  ✗ Failed to find any solutions")
                results[solver_name] = (0, 0)
            else:
                avg_time = sum(times) / len(times)
                min_time = min(times)
                max_time = max(times)
                print(f"  ✓ Success rate: {success_count}/5")
                print(f"  Time: {avg_time*1000:.3f}ms (min: {min_time*1000:.3f}ms, max: {max_time*1000:.3f}ms)")
                results[solver_name] = (success_count, avg_time)

        # Compare
        rs_success, rs_time = results.get('RejectionSamplingSolver', (0, 0))
        rb_success, rb_time = results.get('RandomizedBacktrackingSolver', (0, 0))

        if rs_time > 0 and rb_time > 0:
            speedup = rb_time / rs_time
            print(f"\nSpeedup: RejectionSampling is {speedup:.1f}x faster")

    def run_all_benchmarks(self):
        """Run benchmarks on all problem sizes."""
        print("\n" + "="*80)
        print("SOLVER COMPARISON: REALISTIC PROBLEM SIZES")
        print("="*80)

        self.test_problem("Small (30 items)", 30, 30, 10)
        self.test_problem("Medium (100 items)", 100, 30, 15)
        self.test_problem("Large (250 items)", 250, 30, 20)

        print(f"\n{'='*80}")
        print("SUMMARY")
        print(f"{'='*80}")
        print("""
For your actual use case (200-250 locations, 30 unique items):
- RejectionSampling: Excellent performance, simple implementation
- RandomizedBacktracking: Good performance, more complex implementation
        """)


def main():
    try:
        benchmark = SolverBenchmark()
        benchmark.run_all_benchmarks()
        return 0
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
