"""Randomized backtracking solver for assignment problems with constraints.

DEPRECATED: This module has been moved to logic.solvers.randomized_backtracking_solver.
This file is kept for backwards compatibility.

Use:
    from logic.solvers import RandomizedBacktrackingSolver
instead of:
    from logic.randomized_backtracking_solver import RandomizedBacktrackingSolver
"""

# Re-export from new location for backwards compatibility
from logic.solvers.randomized_backtracking_solver import RandomizedBacktrackingSolver

__all__ = ["RandomizedBacktrackingSolver"]
