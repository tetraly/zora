"""Randomized backtracking solver for assignment problems with constraints.

This module provides a lightweight alternative to OR-Tools for solving
assignment/permutation problems where we only need to find ONE valid solution
(not optimize). It uses randomized backtracking with a seeded RNG to ensure:
- Determinism: same seed + same constraints = same solution
- Variability: different seeds = different solutions
- Randomness: solutions are drawn from the solution space with good distribution

API is compatible with AssignmentSolver for drop-in replacement testing.
"""

from typing import Any, Dict, List, Optional, Set, Tuple, Union
import logging as log
import random
from collections import defaultdict


class RandomizedBacktrackingSolver:
    """Solves assignment/permutation problems using randomized backtracking.

    This solver is optimized for finding any valid solution quickly when:
    - Problem size is small to medium (< 100 items)
    - Constraints are mostly exclusion-based (forbid relationships)
    - You need deterministic results with good randomness
    """

    def __init__(self):
        """Initialize the backtracking solver."""
        self.rng = random.Random()

        # Permutation mode state
        self.permutation_mode: bool = False
        self.permutation_keys: List[Any] = []
        self.permutation_values: List[Any] = []

        # Constraint storage
        self.forbidden_pairs: Set[Tuple[Any, Any]] = set()  # (key, value_index) pairs
        self.required_pairs: Dict[Any, int] = {}  # key -> value_index
        self.at_least_one_constraints: List[Tuple[List[int], List[int]]] = []  # (key_indices, value_indices)

        # Forbidden solutions
        self.forbidden_solution_maps: List[Dict[Any, Any]] = []
        self.forbidden_solutions_indices: List[Dict[int, int]] = []  # key_idx -> value_idx mappings

        # Results tracking
        self.last_solution: Optional[Dict[Any, Any]] = None
        self.last_solution_indices: Optional[Dict[Any, int]] = None

        # Backtracking configuration
        self.max_iterations: int = 100  # Reduced from 1000
        self.max_backtrack_depth: int = 10  # Reduced from 50 - fail fast

    def add_permutation_problem(
        self,
        keys: List[Any],
        values: List[Any],
        shuffle_seed: Optional[int] = None
    ) -> None:
        """Define a permutation problem where keys are shuffled to different values.

        Args:
            keys: List of unique identifiers
            values: List of items to assign (can have duplicates)
            shuffle_seed: Optional seed to pre-shuffle keys/values before solving

        Raises:
            ValueError: If keys and values have different lengths
        """
        if len(keys) != len(values):
            raise ValueError(
                f"Keys and values must have same length. "
                f"Got {len(keys)} keys and {len(values)} values."
            )

        self.permutation_mode = True

        # Pre-shuffle if requested (for compatibility with AssignmentSolver API)
        keys_copy = list(keys)
        values_copy = list(values)
        if shuffle_seed is not None:
            pre_shuffle_rng = random.Random(shuffle_seed)
            pre_shuffle_rng.shuffle(keys_copy)
            pre_shuffle_rng.shuffle(values_copy)

        self.permutation_keys = keys_copy
        self.permutation_values = values_copy

    def require(self, source: Any, target: Any) -> None:
        """Force a specific source to be assigned to a specific target.

        Args:
            source: The source/key to constrain
            target: The target/value it must be assigned to

        Raises:
            ValueError: If source/target not in problem
        """
        if self.permutation_mode:
            try:
                key_idx = self.permutation_keys.index(source)
                value_idx = self.permutation_values.index(target)
            except ValueError:
                raise ValueError(
                    f"In permutation mode: source {source} must be in keys, "
                    f"target {target} must be in values"
                )
            self.required_pairs[key_idx] = value_idx
            log.debug(f"Constraint: {source} MUST map to {target}")
        else:
            raise NotImplementedError("Non-permutation mode not yet implemented")

    def forbid(self, source: Any, target: Any) -> None:
        """Prevent a specific source from being assigned to a specific target.

        Args:
            source: The source/key to constrain
            target: The target/value it cannot be assigned to

        Raises:
            ValueError: If source/target not in problem
        """
        if self.permutation_mode:
            try:
                key_idx = self.permutation_keys.index(source)
            except ValueError:
                raise ValueError(f"In permutation mode: source {source} must be in keys")

            # Find ALL value indices for this target (may have duplicates)
            value_indices = [i for i, v in enumerate(self.permutation_values) if v == target]
            if not value_indices:
                raise ValueError(f"In permutation mode: target {target} must be in values")

            # Add forbidden pairs
            for value_idx in value_indices:
                self.forbidden_pairs.add((key_idx, value_idx))

            log.debug(f"Constraint: {source} must NOT map to {target} ({len(value_indices)} occurrences)")
        else:
            raise NotImplementedError("Non-permutation mode not yet implemented")

    def forbid_all(
        self,
        sources: Union[Any, List[Any]] = None,
        targets: Union[Any, List[Any]] = None
    ) -> None:
        """Prevent multiple sources from being assigned to multiple targets.

        Args:
            sources: Single source or list of sources (None = all sources)
            targets: Single target or list of targets (None = all targets)
        """
        # Normalize inputs
        if sources is None:
            sources = self.permutation_keys if self.permutation_mode else []
        elif not isinstance(sources, (list, tuple)):
            sources = [sources]

        if targets is None:
            targets = self.permutation_values if self.permutation_mode else []
        elif not isinstance(targets, (list, tuple)):
            targets = [targets]

        # Apply forbid for each pair
        constraint_count = 0
        for source in sources:
            for target in targets:
                self.forbid(source, target)
                constraint_count += 1

        log.debug(f"Added {constraint_count} forbid constraints")

    def at_least_one_of(
        self,
        sources: Union[Any, List[Any]],
        targets: Union[Any, List[Any]]
    ) -> None:
        """Require that at least one source receives at least one of the target values.

        Args:
            sources: Single source or list of sources to consider
            targets: Single target or list of targets that must appear at one source
        """
        # Normalize inputs
        if not isinstance(sources, (list, tuple, set)):
            sources = [sources]
        else:
            sources = list(dict.fromkeys(sources))

        if not isinstance(targets, (list, tuple, set)):
            targets = [targets]
        else:
            targets = list(dict.fromkeys(targets))

        if not sources:
            raise ValueError("at_least_one_of requires at least one source")
        if not targets:
            raise ValueError("at_least_one_of requires at least one target")

        if self.permutation_mode:
            # Convert sources to key indices
            key_indices = []
            for src in sources:
                try:
                    key_indices.append(self.permutation_keys.index(src))
                except ValueError:
                    raise ValueError(f"Source {src} not in permutation keys")

            # Convert targets to value indices
            target_value_indices = set()
            for tgt in targets:
                indices = [i for i, v in enumerate(self.permutation_values) if v == tgt]
                if not indices:
                    raise ValueError(f"Target {tgt} not in permutation values")
                target_value_indices.update(indices)

            # Store constraint
            self.at_least_one_constraints.append((key_indices, list(target_value_indices)))
            log.debug(f"Constraint: At least one of {len(key_indices)} keys must map to one of {len(target_value_indices)} values")
        else:
            raise NotImplementedError("Non-permutation mode not yet implemented")

    def add_forbidden_solution_map(self, solution_map: Dict[Any, Any]) -> None:
        """Record a full source->target mapping that should be excluded.

        Args:
            solution_map: Dictionary mapping source/key -> target/value
        """
        self.forbidden_solution_maps.append(solution_map.copy())

        # Also convert to indices for faster checking during backtracking
        if self.permutation_mode:
            index_map = self._solution_map_to_indices(solution_map)
            if index_map is not None:
                self.forbidden_solutions_indices.append(index_map)

    def solve(
        self,
        seed: Optional[int] = None,
        time_limit_seconds: float = 10.0
    ) -> Optional[Dict[Any, Any]]:
        """Solve the assignment problem using randomized backtracking with greedy placement.

        Args:
            seed: Random seed for deterministic solving
            time_limit_seconds: Maximum time to spend solving (best-effort)

        Returns:
            Dictionary mapping source -> target if solution found, None otherwise.
        """
        if not self.permutation_mode:
            raise NotImplementedError("Non-permutation mode not yet implemented")

        # Seed the RNG
        if seed is not None:
            self.rng.seed(seed)
            log.debug(f"Solving with seed: {seed}")

        # Try to find a valid solution using greedy randomized placement
        num_keys = len(self.permutation_keys)

        for attempt in range(self.max_iterations):
            # Use greedy + backtracking approach
            assignment = self._greedy_solve_with_backtrack(num_keys, max_depth=5)

            if assignment is not None:
                # Found a valid solution
                self.last_solution_indices = {}
                self.last_solution = {}

                for key_idx, value_idx in enumerate(assignment):
                    key = self.permutation_keys[key_idx]
                    value = self.permutation_values[value_idx]
                    self.last_solution[key] = value
                    self.last_solution_indices[key] = value_idx

                # Check against forbidden solutions
                if self._is_solution_forbidden(assignment):
                    log.debug(f"Found solution matches forbidden list, trying again (attempt {attempt + 1})")
                    continue

                log.info(f"Found valid solution on attempt {attempt + 1}")
                return self.last_solution

        log.error(f"No valid solution found after {self.max_iterations} attempts")
        return None

    def _greedy_solve_with_backtrack(self, num_keys: int, max_depth: int = 5) -> Optional[List[int]]:
        """Solve using greedy placement with backtracking on conflicts.

        Args:
            num_keys: Number of keys to assign
            max_depth: Maximum backtracking depth when greedy fails

        Returns:
            Assignment as list of value indices, or None if no solution found
        """
        # Create random order for greedy assignment
        key_order = list(range(num_keys))
        self.rng.shuffle(key_order)

        # Initialize assignment
        assignment = [-1] * num_keys
        used_indices = set()

        # First, handle required assignments
        for key_idx, value_idx in self.required_pairs.items():
            if value_idx in used_indices:
                # Conflict: required value already used
                return None
            assignment[key_idx] = value_idx
            used_indices.add(value_idx)

        # Try greedy assignment for remaining keys
        for key_idx in key_order:
            if assignment[key_idx] != -1:
                continue  # Already assigned (required)

            # Get valid options for this key
            valid_indices = self._get_valid_value_indices(key_idx, used_indices)

            if not valid_indices:
                # Greedy failed, try backtracking
                if not self._backtrack(list(range(num_keys)), 0, assignment, used_indices, max_depth):
                    return None
                # Update used_indices after backtracking
                used_indices = {assignment[i] for i in range(num_keys) if assignment[i] != -1}
            else:
                # Randomly choose from valid options
                value_idx = self.rng.choice(valid_indices)
                assignment[key_idx] = value_idx
                used_indices.add(value_idx)

        # Check at_least_one constraints
        if not self._check_at_least_one_constraints(assignment):
            return None

        return assignment

    def _backtrack(
        self,
        key_order: List[int],
        depth: int,
        assignment: List[int],
        used_indices: Set[int],
        max_depth: int = 10
    ) -> bool:
        """Recursively try to assign keys to values.

        Args:
            key_order: Order in which to try assigning keys
            depth: Current recursion depth
            assignment: Current assignment state (-1 = unassigned)
            used_indices: Set of value indices already used
            max_depth: Maximum recursion depth

        Returns:
            True if a complete valid assignment was found, False otherwise
        """
        # Count unassigned keys
        unassigned_count = sum(1 for x in assignment if x == -1)
        if unassigned_count == 0:
            return self._check_at_least_one_constraints(assignment)

        # Limit backtracking depth
        if depth > max_depth:
            return False

        # Find next unassigned key (prefer more constrained keys)
        next_key_idx = None
        min_valid_options = len(self.permutation_values) + 1

        for key_idx in range(len(assignment)):
            if assignment[key_idx] == -1:
                # Count valid options for this key
                valid_count = len(self._get_valid_value_indices(key_idx, used_indices))
                if valid_count < min_valid_options:
                    min_valid_options = valid_count
                    next_key_idx = key_idx

        if next_key_idx is None:
            return False

        key_idx = next_key_idx

        # If this key has a required target, use it
        if key_idx in self.required_pairs:
            value_idx = self.required_pairs[key_idx]
            if value_idx not in used_indices and (key_idx, value_idx) not in self.forbidden_pairs:
                assignment[key_idx] = value_idx
                used_indices.add(value_idx)

                if self._backtrack(key_order, depth + 1, assignment, used_indices, max_depth):
                    return True

                # Undo assignment
                assignment[key_idx] = -1
                used_indices.remove(value_idx)
            return False

        # Get valid value indices for this key
        valid_indices = self._get_valid_value_indices(key_idx, used_indices)

        if not valid_indices:
            return False

        # Randomize order of trying valid indices
        self.rng.shuffle(valid_indices)

        # Try each valid value index
        for value_idx in valid_indices:
            assignment[key_idx] = value_idx
            used_indices.add(value_idx)

            if self._backtrack(key_order, depth + 1, assignment, used_indices, max_depth):
                return True

            # Undo assignment
            assignment[key_idx] = -1
            used_indices.remove(value_idx)

        return False

    def _get_valid_value_indices(self, key_idx: int, used_indices: Set[int]) -> List[int]:
        """Get all valid value indices for a given key.

        A value index is valid if:
        - It hasn't been used yet
        - It's not forbidden for this key

        Args:
            key_idx: Index of the key to assign
            used_indices: Set of already-used value indices

        Returns:
            List of valid value indices (randomized order)
        """
        num_values = len(self.permutation_values)
        valid = []

        for value_idx in range(num_values):
            # Skip if already used
            if value_idx in used_indices:
                continue

            # Skip if explicitly forbidden
            if (key_idx, value_idx) in self.forbidden_pairs:
                continue

            valid.append(value_idx)

        return valid

    def _check_at_least_one_constraints(self, assignment: List[int]) -> bool:
        """Check if all at_least_one constraints are satisfied.

        Args:
            assignment: Complete assignment mapping key indices to value indices

        Returns:
            True if all at_least_one constraints are satisfied
        """
        for key_indices, value_indices in self.at_least_one_constraints:
            # Check if at least one key is assigned to at least one required value
            found = False
            for key_idx in key_indices:
                if assignment[key_idx] in value_indices:
                    found = True
                    break

            if not found:
                return False

        return True

    def _is_solution_forbidden(self, assignment: List[int]) -> bool:
        """Check if a solution matches any forbidden solution.

        Args:
            assignment: Assignment as list of value indices

        Returns:
            True if this solution is forbidden, False otherwise
        """
        for forbidden_indices in self.forbidden_solutions_indices:
            # Check if this assignment matches the forbidden one
            if all(assignment[key_idx] == forbidden_indices[key_idx]
                   for key_idx in forbidden_indices):
                return True

        return False

    def _solution_map_to_indices(self, solution_map: Dict[Any, Any]) -> Optional[Dict[int, int]]:
        """Convert a source->target mapping to key_index->value_index mapping.

        Args:
            solution_map: Dictionary mapping key -> value

        Returns:
            Dictionary mapping key_index -> value_index, or None if invalid
        """
        index_map: Dict[int, int] = {}

        # Track which value indices we've used for deduplication
        value_usage: Dict[Any, int] = {}
        value_positions: Dict[Any, List[int]] = {}

        for idx, value in enumerate(self.permutation_values):
            value_positions.setdefault(value, []).append(idx)

        for key in self.permutation_keys:
            if key not in solution_map:
                return None

            target_value = solution_map[key]
            positions = value_positions.get(target_value)

            if not positions:
                return None

            usage = value_usage.get(target_value, 0)
            if usage >= len(positions):
                return None

            try:
                key_idx = self.permutation_keys.index(key)
                index_map[key_idx] = positions[usage]
                value_usage[target_value] = usage + 1
            except ValueError:
                return None

        return index_map

    def clear_forbidden_solution_maps(self) -> None:
        """Remove any previously recorded forbidden assignments."""
        self.forbidden_solution_maps.clear()
        self.forbidden_solutions_indices.clear()

    def get_stats(self) -> Dict[str, int]:
        """Get statistics about the problem.

        Returns:
            Dictionary with problem statistics
        """
        num_possible_assignments = 1
        for i in range(len(self.permutation_keys)):
            num_possible_assignments *= (len(self.permutation_values) - i)

        return {
            "num_keys": len(self.permutation_keys),
            "num_values": len(self.permutation_values),
            "num_forbidden_pairs": len(self.forbidden_pairs),
            "num_required_pairs": len(self.required_pairs),
            "num_at_least_one_constraints": len(self.at_least_one_constraints),
            "num_forbidden_solutions": len(self.forbidden_solutions_indices),
            "max_iterations": self.max_iterations,
            "max_backtrack_depth": self.max_backtrack_depth,
        }
