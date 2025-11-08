"""Solver implementations for permutation/assignment problems.

This package provides multiple solver implementations with identical APIs
for testing and comparison:

- AssignmentSolver: OR-Tools CP-SAT solver
- RandomizedBacktrackingSolver: Greedy + backtracking approach
- RejectionSamplingSolver: Fast rejection sampling

All solvers implement the same interface, making them drop-in replacements.

Example usage:
    from logic.solvers import AssignmentSolver, RandomizedBacktrackingSolver, RejectionSamplingSolver

    # Create with any solver
    solver = RejectionSamplingSolver()

    # Use identical API
    solver.add_permutation_problem(locations, items)
    solver.forbid(loc1, item1)
    solver.require(loc2, item2)
    solution = solver.solve(seed=42)
"""

from .assignment_solver import AssignmentSolver
from .randomized_backtracking_solver import RandomizedBacktrackingSolver
from .rejection_sampling_solver import RejectionSamplingSolver
from .solver_interface import SolverInterface
from .solver_factory import SolverType

__all__ = [
    "AssignmentSolver",
    "RandomizedBacktrackingSolver",
    "RejectionSamplingSolver",
    "SolverInterface",
    "SolverType",
]
