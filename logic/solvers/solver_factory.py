"""Factory for creating and selecting solver instances.

This module provides utilities for easily switching between different solver
implementations for A/B/C testing and comparison.
"""

from enum import Enum
from typing import Type
import logging as log

from .assignment_solver import AssignmentSolver
from .randomized_backtracking_solver import RandomizedBacktrackingSolver
from .rejection_sampling_solver import RejectionSamplingSolver


class SolverType(Enum):
    """Enum of available solver types."""

    ASSIGNMENT_SOLVER = "assignment_solver"
    RANDOMIZED_BACKTRACKING = "randomized_backtracking"
    REJECTION_SAMPLING = "rejection_sampling"

    def __str__(self):
        """Return human-readable name."""
        return {
            self.ASSIGNMENT_SOLVER: "OR-Tools AssignmentSolver",
            self.RANDOMIZED_BACKTRACKING: "Randomized Backtracking Solver",
            self.REJECTION_SAMPLING: "Rejection Sampling Solver",
        }[self]


def get_solver_class(solver_type: SolverType) -> Type:
    """Get the class for a specific solver type.

    Args:
        solver_type: The SolverType to get the class for

    Returns:
        The solver class corresponding to the type
    """
    mapping = {
        SolverType.ASSIGNMENT_SOLVER: AssignmentSolver,
        SolverType.RANDOMIZED_BACKTRACKING: RandomizedBacktrackingSolver,
        SolverType.REJECTION_SAMPLING: RejectionSamplingSolver,
    }
    return mapping[solver_type]


def create_solver(solver_type: SolverType):
    """Create a solver instance of the specified type.

    Args:
        solver_type: The SolverType to create

    Returns:
        An instance of the specified solver

    Raises:
        ImportError: If the solver requires unavailable dependencies
    """
    solver_class = get_solver_class(solver_type)

    try:
        solver = solver_class()
        log.info(f"Created solver: {solver_type}")
        return solver
    except ImportError as e:
        log.error(f"Failed to create {solver_type}: {e}")
        raise


def list_available_solvers() -> list:
    """List all solver types and their availability.

    Returns:
        List of (SolverType, available: bool) tuples
    """
    available = []

    for solver_type in SolverType:
        try:
            create_solver(solver_type)
            available.append((solver_type, True))
        except ImportError:
            available.append((solver_type, False))

    return available
