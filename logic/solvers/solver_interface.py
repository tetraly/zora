"""Unified interface for all solver implementations.

This protocol defines the expected API that all solvers must implement,
enabling drop-in replacement between different solver backends.
"""

from typing import Any, Dict, List, Optional, Protocol, Union


class SolverInterface(Protocol):
    """Protocol defining the unified solver interface.

    All solver implementations must support these methods and attributes
    with identical signatures and behavior.
    """

    # Initialization
    def __init__(self) -> None:
        """Initialize the solver with default state."""
        ...

    # Problem Definition
    def add_permutation_problem(
        self,
        keys: List[Any],
        values: List[Any],
        shuffle_seed: Optional[int] = None
    ) -> None:
        """Define a permutation problem.

        Args:
            keys: List of unique identifiers (locations, positions, etc.)
            values: List of items to assign (can have duplicates)
            shuffle_seed: Optional seed for pre-shuffling keys/values

        Raises:
            ValueError: If keys and values have different lengths
        """
        ...

    # Constraints
    def forbid(self, source: Any, target: Any) -> None:
        """Prevent a specific source from being assigned to target.

        Args:
            source: The key that cannot map to target
            target: The value that source cannot receive

        Raises:
            ValueError: If source or target not in problem
        """
        ...

    def forbid_all(
        self,
        sources: Union[Any, List[Any]],
        targets: Union[Any, List[Any]]
    ) -> None:
        """Prevent multiple sources from being assigned to multiple targets.

        Args:
            sources: Single source or list of sources (None = all sources)
            targets: Single target or list of targets (None = all targets)
        """
        ...

    def require(self, source: Any, target: Any) -> None:
        """Force a specific source to be assigned to a specific target.

        Args:
            source: The key that must map to target
            target: The value that source must receive

        Raises:
            ValueError: If source or target not in problem
        """
        ...

    def at_least_one_of(
        self,
        sources: Union[Any, List[Any]],
        targets: Union[Any, List[Any]]
    ) -> None:
        """Require at least one source to receive one of the target values.

        Args:
            sources: Single source or list of sources to consider
            targets: Single target or list of targets that must appear

        Raises:
            ValueError: If sources/targets empty or not in problem
        """
        ...

    # Forbidden Solutions
    def add_forbidden_solution_map(self, solution_map: Dict[Any, Any]) -> None:
        """Record a complete solution to exclude from future solves.

        Args:
            solution_map: Dictionary mapping key -> value that should be forbidden
        """
        ...

    def clear_forbidden_solution_maps(self) -> None:
        """Remove all previously recorded forbidden solutions."""
        ...

    # Solving
    def solve(
        self,
        seed: Optional[int] = None,
        time_limit_seconds: float = 10.0
    ) -> Optional[Dict[Any, Any]]:
        """Solve the permutation problem.

        Args:
            seed: Random seed for deterministic solving (same seed = same solution)
            time_limit_seconds: Best-effort timeout (not all solvers respect this)

        Returns:
            Dictionary mapping keys -> values if solution found, None if no solution
        """
        ...

    # Results Access
    @property
    def last_solution(self) -> Optional[Dict[Any, Any]]:
        """The most recently found solution (key -> value mapping)."""
        ...

    @property
    def last_solution_indices(self) -> Optional[Dict[Any, int]]:
        """The most recently found solution as indices into values list."""
        ...

    # Statistics
    def get_stats(self) -> Dict[str, int]:
        """Get statistics about the problem.

        Returns:
            Dictionary with problem statistics (varies by solver)
        """
        ...
