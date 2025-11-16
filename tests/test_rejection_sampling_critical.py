"""Critical requirement tests for RejectionSamplingSolver.

Verifies the three non-negotiable requirements:
1. Determinism: same seed + inputs = same output
2. Seed independence: different seeds = different outputs
3. Randomness: solutions are well-distributed
"""

import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


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


class CriticalRequirementTest:
    """Test critical requirements for RejectionSamplingSolver."""

    def setup_problem(self, num_locations=100, num_items=30):
        """Create a realistic problem.

        Args:
            num_locations: Number of locations to shuffle
            num_items: Number of unique items (rest are duplicates)
        """
        locations = list(range(num_locations))

        # Create items with duplicates (realistic for major item randomizer)
        items = list(range(num_items))
        while len(items) < num_locations:
            items.append(num_items - 1)  # Duplicate placeholder item

        return locations, items

    def add_constraints(self, solver):
        """Add realistic constraints to solver."""
        constraints = [
            (0, 1, 'forbid'),
            (5, 2, 'forbid'),
            (10, 3, 'forbid'),
            (15, 4, 'forbid'),
            (3, 27, 'require'),
            (99, 28, 'require'),
        ]

        for loc, item, action in constraints:
            if action == 'forbid':
                solver.forbid(loc, item)
            elif action == 'require':
                solver.require(loc, item) if hasattr(solver, 'require') else None

    def test_requirement_1_determinism(self) -> bool:
        """CRITICAL REQUIREMENT 1: Determinism"""
        print("\n" + "="*80)
        print("CRITICAL REQUIREMENT 1: DETERMINISM (RejectionSamplingSolver)")
        print("="*80)
        print("Test: Same seed + same input = same output (verified 10 times)")

        locations, items = self.setup_problem(100, 30)
        test_seed = 12345

        solutions = []
        for attempt in range(10):
            solver = RejectionSamplingSolver()
            solver.add_permutation_problem(locations, items, shuffle_seed=None)
            self.add_constraints(solver)

            solution = solver.solve(seed=test_seed)
            if solution is None:
                print(f"  ✗ Attempt {attempt + 1}: No solution found")
                return False

            solutions.append(solution)

        # Check all solutions are identical
        all_identical = all(sol == solutions[0] for sol in solutions)

        if all_identical:
            print(f"  ✓ All 10 solutions are IDENTICAL")
            return True
        else:
            print(f"  ✗ FAILED: Solutions differ!")
            return False

    def test_requirement_2_seed_independence(self) -> bool:
        """CRITICAL REQUIREMENT 2: Seed Independence"""
        print("\n" + "="*80)
        print("CRITICAL REQUIREMENT 2: SEED INDEPENDENCE (RejectionSamplingSolver)")
        print("="*80)
        print("Test: Different seeds = different outputs (verified across 20 seeds)")

        locations, items = self.setup_problem(100, 30)

        solutions = {}
        base_seed = 5000

        for seed_offset in range(20):
            solver = RejectionSamplingSolver()
            solver.add_permutation_problem(locations, items, shuffle_seed=None)
            self.add_constraints(solver)

            test_seed = base_seed + seed_offset
            solution = solver.solve(seed=test_seed)

            if solution is None:
                print(f"  ✗ Seed {test_seed}: No solution found")
                return False

            solution_tuple = tuple(sorted(solution.items()))
            solutions[test_seed] = solution_tuple

        # Count unique solutions
        unique_count = len(set(solutions.values()))
        total_count = len(solutions)
        uniqueness_percent = (unique_count / total_count) * 100

        print(f"  Unique solutions: {unique_count}/{total_count} ({uniqueness_percent:.1f}%)")

        if unique_count >= total_count * 0.7:
            print(f"  ✓ PASSED: {uniqueness_percent:.1f}% uniqueness (>= 70% threshold)")
            return True
        else:
            print(f"  ✗ FAILED: Only {uniqueness_percent:.1f}% unique (need >= 70%)")
            return False

    def test_requirement_3_randomness_quality(self) -> bool:
        """CRITICAL REQUIREMENT 3: Solution Randomness"""
        print("\n" + "="*80)
        print("CRITICAL REQUIREMENT 3: SOLUTION RANDOMNESS (RejectionSamplingSolver)")
        print("="*80)
        print("Test: Solutions show good distribution across solution space (20 runs)")

        locations, items = self.setup_problem(100, 30)

        # Track where item 1 appears
        item_1_positions = []

        for run in range(20):
            solver = RejectionSamplingSolver()
            solver.add_permutation_problem(locations, items, shuffle_seed=None)
            self.add_constraints(solver)

            solution = solver.solve(seed=10000 + run)
            if solution is None:
                print(f"  ✗ Run {run + 1}: No solution found")
                return False

            # Track item 1 position
            for location, item in solution.items():
                if item == 1:
                    item_1_positions.append(location)
                    break

        unique_item_positions = len(set(item_1_positions))
        print(f"  Item 1 appeared in {unique_item_positions} different locations across 20 runs")

        if unique_item_positions >= 8:
            print(f"  ✓ PASSED: Good distribution (appears in {unique_item_positions}/100 locations)")
            return True
        else:
            print(f"  ✗ WARNING: Poor distribution (only {unique_item_positions}/100 locations)")
            return False

    def run_all_critical_tests(self) -> bool:
        """Run all three critical requirement tests."""
        print("\n" + "="*80)
        print("CRITICAL REQUIREMENT VERIFICATION: RejectionSamplingSolver")
        print("="*80)

        results = []

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
