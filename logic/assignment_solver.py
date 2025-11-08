"""OR-Tools wrapper for solving assignment problems with constraints.

DEPRECATED: This module has been moved to logic.solvers.assignment_solver.
This file is kept for backwards compatibility.

Use:
    from logic.solvers import AssignmentSolver
instead of:
    from logic.assignment_solver import AssignmentSolver
"""

# Re-export from new location for backwards compatibility
from logic.solvers.assignment_solver import AssignmentSolver

__all__ = ["AssignmentSolver"]
