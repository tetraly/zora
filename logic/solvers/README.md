# Solver Package - A/B/C Testing Framework

This package contains three solver implementations with identical APIs, enabling drop-in replacement for testing and comparison.

## Available Solvers

### 1. AssignmentSolver (OR-Tools)
- **Location**: `logic.solvers.assignment_solver.AssignmentSolver`
- **Approach**: Constraint Programming with OR-Tools CP-SAT
- **Best for**: Complex constraints, sparse solution spaces, guaranteed solutions
- **Performance**: ~3.6ms for 250 items
- **Dependencies**: `pip install ortools`

### 2. RandomizedBacktrackingSolver
- **Location**: `logic.solvers.randomized_backtracking_solver.RandomizedBacktrackingSolver`
- **Approach**: Greedy assignment + limited backtracking with variable reordering
- **Best for**: Moderate constraints, small-medium problems (<100 items)
- **Performance**: ~0.7ms for 100 items, ~3.6ms for 250 items
- **Dependencies**: None (stdlib only)

### 3. RejectionSamplingSolver
- **Location**: `logic.solvers.rejection_sampling_solver.RejectionSamplingSolver`
- **Approach**: Fast rejection sampling with constraint checking
- **Best for**: Dense solution spaces, large problems (100-1000+ items)
- **Performance**: ~0.2ms for 250 items
- **Dependencies**: None (stdlib only)

## Unified API

All three solvers implement the same interface:

```python
from logic.solvers import AssignmentSolver, RandomizedBacktrackingSolver, RejectionSamplingSolver

# Create any solver
solver = RejectionSamplingSolver()  # or AssignmentSolver() or RandomizedBacktrackingSolver()

# Define problem
solver.add_permutation_problem(locations, items)

# Add constraints (all APIs identical)
solver.forbid(location_1, item_1)
solver.forbid_all([loc1, loc2], [item1, item2])
solver.require(location_3, item_3)
solver.at_least_one_of(locations_list, items_list)

# Solve
solution = solver.solve(seed=42)

# Access results
print(solver.last_solution)          # Dict[location -> item]
print(solver.last_solution_indices)  # Dict[location -> value_index]
```

## Using the Solver Factory

For easy switching and testing:

```python
from logic.solvers import SolverType
from logic.solvers.solver_factory import create_solver, list_available_solvers

# List available solvers
for solver_type, available in list_available_solvers():
    print(f"{solver_type}: {'Available' if available else 'Not available (missing deps)'}")

# Create a solver by type
solver = create_solver(SolverType.REJECTION_SAMPLING)
# or
solver = create_solver(SolverType.ASSIGNMENT_SOLVER)
# or
solver = create_solver(SolverType.RANDOMIZED_BACKTRACKING)
```

## A/B/C Testing Example

Here's how to test all three solvers on your problem:

```python
from logic.solvers import SolverType
from logic.solvers.solver_factory import create_solver
import time

# Your problem
locations = list(range(250))
items = [1] * 30 + [2] * 50 + list(range(3, 100))

def run_test(solver_type, num_runs=5):
    print(f"\nTesting {solver_type}:")
    times = []

    for seed in range(num_runs):
        solver = create_solver(solver_type)
        solver.add_permutation_problem(locations, items)

        # Add your constraints
        solver.forbid(0, 1)
        solver.require(100, 2)

        start = time.time()
        solution = solver.solve(seed=1000 + seed)
        elapsed = time.time() - start

        if solution:
            times.append(elapsed)
            print(f"  Run {seed + 1}: {elapsed*1000:.2f}ms")
        else:
            print(f"  Run {seed + 1}: FAILED")

    if times:
        avg = sum(times) / len(times)
        print(f"  Average: {avg*1000:.2f}ms")
        return avg
    return None

# Run A/B/C test
results = {}
for solver_type in [SolverType.ASSIGNMENT_SOLVER,
                     SolverType.RANDOMIZED_BACKTRACKING,
                     SolverType.REJECTION_SAMPLING]:
    try:
        results[str(solver_type)] = run_test(solver_type)
    except ImportError as e:
        print(f"Skipping {solver_type}: {e}")

# Compare results
print("\n" + "="*60)
print("SUMMARY")
print("="*60)
for name, avg_time in sorted(results.items(), key=lambda x: x[1] if x[1] else float('inf')):
    if avg_time:
        print(f"{name:40} {avg_time*1000:8.2f}ms")
```

## Integration with MajorItemRandomizer

To use a specific solver in the major item randomizer:

### Option A: Hard-coded solver

```python
# In logic/items/major_item_randomizer.py

# Old way:
# from logic.assignment_solver import AssignmentSolver
# solver = AssignmentSolver()

# New way (pick your favorite):
from logic.solvers import RejectionSamplingSolver
solver = RejectionSamplingSolver()
```

### Option B: Configurable solver via flags

```python
# In MajorItemRandomizer.__init__
from logic.solvers import SolverType
from logic.solvers.solver_factory import create_solver

def __init__(self, data_table, flags):
    self.data_table = data_table
    self.flags = flags

    # Use solver type from flags, default to RejectionSampling
    solver_type = getattr(flags, 'solver_type', SolverType.REJECTION_SAMPLING)
    self.solver = create_solver(solver_type)
```

### Option C: Runtime selection

```python
# At call time:
from logic.solvers.solver_factory import create_solver, SolverType

randomizer = MajorItemRandomizer(data_table, flags)

# Use different solvers for testing
for solver_type in [SolverType.ASSIGNMENT_SOLVER,
                    SolverType.REJECTION_SAMPLING]:
    result = randomizer.randomize_with_solver(solver_type, seed=42)
    # Compare results...
```

## Backwards Compatibility

Import solvers from the `logic.solvers` module:

```python
from logic.solvers import AssignmentSolver, RandomizedBacktrackingSolver, RejectionSamplingSolver
```

## Choosing a Solver

**Start with RejectionSamplingSolver** for your major item randomizer:
- Fastest for 200-250 items (16.8x faster than backtracking)
- Simplest code (easier to debug)
- Perfect for your constraint density
- Falls back to others if needed

**Use RandomizedBacktrackingSolver if:**
- You need predictable performance on very tight constraints
- You're testing smaller problems (<100 items)
- You want hybrid determinism + backtracking

**Use AssignmentSolver if:**
- You need guaranteed optimal solutions
- Constraints become very complex
- Performance is not critical (10-second timeout acceptable)

## Testing Tips

1. **Determinism check**: Same seed should produce identical solutions
2. **Seed independence**: Different seeds should produce different solutions
3. **Constraint validation**: Verify all solutions satisfy constraints
4. **Performance tracking**: Log solve times across different problem sizes
5. **Solution distribution**: Check that items appear in diverse locations

See test files for examples:
- `tests/test_solver_scaling.py` - Performance benchmarks
- `tests/test_rejection_sampling_critical.py` - Critical requirement validation
- `tests/test_randomized_backtracking_critical.py` - Alternative validation
