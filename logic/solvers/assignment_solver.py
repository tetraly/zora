"""OR-Tools wrapper for solving assignment problems with constraints.

This module provides a simple interface for solving assignment problems like:
- Assigning cave destinations to overworld screens
- Assigning items to locations
- Any one-to-one mapping with constraints

Example usage for cave shuffling:
    solver = AssignmentSolver()
    solver.add_assignment_problem(sources=cave_destinations, targets=screen_numbers)
    solver.require(source=CaveType.WOOD_SWORD_CAVE, target=0x77)
    solver.allow_only(sources=[CaveType.LEVEL_1, ...], targets=[0x22, 0x15, ...])
    solution = solver.solve(seed=12345)

Example usage for item shuffling:
    solver = AssignmentSolver()
    solver.add_assignment_problem(sources=items, targets=locations)
    solver.require(source=Item.WOODEN_SWORD, target=Location.LEVEL_1_ITEM_1)
    solver.forbid(source=Item.RAFT, target=Location.LEVEL_9_ITEM_3)
    solution = solver.solve(seed=12345)
"""

from typing import Any, Dict, List, Optional, Set, Union
import logging as log

from rng.random_number_generator import RandomNumberGenerator

try:
    from ortools.sat.python import cp_model
    ORTOOLS_AVAILABLE = True
except ImportError:
    ORTOOLS_AVAILABLE = False
    log.warning("OR-Tools not available. AssignmentSolver will not work.")


class AssignmentSolver:
    """Solves one-to-one assignment problems with constraints using OR-Tools.

    This wrapper provides a clean interface for expressing assignment constraints
    like "assign these sources to these targets" with rules like "this source must
    go to this target" or "these sources can only go to these targets".
    """

    def __init__(self, rng: RandomNumberGenerator):
        """Initialize the assignment solver.

        Args:
            rng: RandomNumberGenerator instance for deterministic shuffling
        """
        if not ORTOOLS_AVAILABLE:
            raise ImportError(
                "OR-Tools is required for AssignmentSolver. "
                "Install with: pip install ortools"
            )
        self.rng = rng

        self.model = cp_model.CpModel()
        self.var_map: Dict[Any, cp_model.IntVar] = {}  # source -> IntVar
        self.sources: List[Any] = []
        self.targets: List[Any] = []
        self.target_set: Set[Any] = set()

        # For permutation mode
        self.permutation_mode: bool = False
        self.permutation_keys: List[Any] = []  # e.g., screen numbers
        self.permutation_values: List[Any] = []  # e.g., cave types (can have duplicates)
        self._bool_var_counter: int = 0  # unique suffix for auxiliary boolean variables

        # Tracking for determinism / post-processing
        self.last_solution: Optional[Dict[Any, Any]] = None
        self.last_solution_indices: Optional[Dict[Any, int]] = None
        self.forbidden_solution_maps: List[Dict[Any, Any]] = []
        self._applied_forbidden_fingerprints: Set[tuple] = set()

    def add_permutation_problem(
        self,
        keys: List[Any],
        values: List[Any],
        shuffle_seed: Optional[int] = None
    ) -> None:
        """Define a permutation problem where keys are shuffled to different values.

        This is for problems like "shuffle which screen gets which cave" where:
        - Keys are unique (e.g., screen numbers)
        - Values can have duplicates (e.g., cave types with 9 DOOR_REPAIR)

        The solver creates a permutation: key[i] -> value[j]
        This preserves value counts since it's just rearranging.

        Example:
            keys = [0x01, 0x03, 0x77]  # Screen numbers
            values = [SHOP, SHOP, WOOD_SWORD]  # Cave types (SHOP appears twice)
            # Solver shuffles which screen gets which cave

        Args:
            keys: List of unique identifiers (e.g., screens, locations)
            values: List of items to assign (can have duplicates, e.g., cave types, items)

        Raises:
            ValueError: If keys and values have different lengths
        Args:
            keys: List of unique identifiers (e.g., screens, locations)
            values: List of items to assign (can have duplicates, e.g., cave types, items)
            shuffle_seed: Optional seed to deterministically shuffle keys and values.

        Raises:
            ValueError: If keys and values have different lengths
        """
        if len(keys) != len(values):
            raise ValueError(
                f"Keys and values must have same length. "
                f"Got {len(keys)} keys and {len(values)} values."
            )

        self.permutation_mode = True
        keys_copy = list(keys)
        values_copy = list(values)
        if shuffle_seed is not None:
            temp_rng = RandomNumberGenerator(shuffle_seed)
            temp_rng.shuffle(keys_copy)
            temp_rng.shuffle(values_copy)
        self.permutation_keys = keys_copy
        self.permutation_values = values_copy

        # Internally, we use indices to avoid duplicate value issues
        num_items = len(keys_copy)
        indices = list(range(num_items))

        # Create variables: each key index gets assigned a value index
        for key_idx in indices:
            var = self.model.NewIntVarFromDomain(
                cp_model.Domain.FromValues(indices),
                f"key_{key_idx}"
            )
            self.var_map[key_idx] = var

        # Constraint: All keys map to unique value indices (creates permutation)
        self.model.AddAllDifferent([self.var_map[i] for i in indices])

    def require(self, source: Any, target: Any) -> None:
        """Force a specific source to be assigned to a specific target.

        In permutation mode:
            source = key (e.g., screen 0x77)
            target = value (e.g., CaveType.WOOD_SWORD_CAVE)
            Constraint: "screen 0x77 must get WOOD_SWORD_CAVE"

        In assignment mode:
            source and target are from the original add_assignment_problem() call

        Example:
            # Permutation mode:
            solver.require(0x77, CaveType.WOOD_SWORD_CAVE)
            # Screen 0x77 MUST get wood sword cave

        Args:
            source: The source to constrain (key in permutation mode)
            target: The target it must be assigned to (value in permutation mode)

        Raises:
            ValueError: If source/target not in problem
        """
        if self.permutation_mode:
            # Find the indices
            try:
                key_idx = self.permutation_keys.index(source)
                value_idx = self.permutation_values.index(target)
            except ValueError:
                raise ValueError(
                    f"In permutation mode: source {source} must be in keys, "
                    f"target {target} must be in values"
                )

            self.model.Add(self.var_map[key_idx] == value_idx)
            log.debug(f"Constraint: {source} MUST map to {target}")
        else:
            # Original assignment mode
            if source not in self.var_map:
                raise ValueError(f"Source {source} not in assignment problem")
            if target not in self.target_set:
                raise ValueError(f"Target {target} not in valid targets")

            self.model.Add(self.var_map[source] == target)
            log.debug(f"Constraint: {source} MUST map to {target}")

    def forbid(self, source: Any, target: Any) -> None:
        """Prevent a specific source from being assigned to a specific target.

        In permutation mode:
            source = key (e.g., room 0x53)
            target = value (e.g., Item.NO_ITEM)
            Constraint: "room 0x53 must NOT get NO_ITEM"

        In assignment mode:
            source and target are from the original add_assignment_problem() call

        Example:
            solver.forbid(Item.RAFT, Location.LEVEL_9_BOSS)
            # Raft can go anywhere except the Level 9 boss location

        Args:
            source: The source to constrain
            target: The target it must NOT be assigned to

        Raises:
            ValueError: If source not in problem or target not valid
        """
        if self.permutation_mode:
            # Find the key index
            try:
                key_idx = self.permutation_keys.index(source)
            except ValueError:
                raise ValueError(
                    f"In permutation mode: source {source} must be in keys"
                )

            # Find ALL occurrences of the target value (there may be duplicates)
            value_indices = [i for i, v in enumerate(self.permutation_values) if v == target]
            if not value_indices:
                raise ValueError(
                    f"In permutation mode: target {target} must be in values"
                )

            # Forbid this key from mapping to ANY occurrence of the target value
            for value_idx in value_indices:
                self.model.Add(self.var_map[key_idx] != value_idx)
            log.debug(f"Constraint: {source} must NOT map to {target} ({len(value_indices)} occurrences)")
        else:
            # Original assignment mode
            if source not in self.var_map:
                raise ValueError(f"Source {source} not in assignment problem")
            if target not in self.target_set:
                raise ValueError(f"Target {target} not in valid targets")

            self.model.Add(self.var_map[source] != target)
            log.debug(f"Constraint: {source} must NOT map to {target}")

    def forbid_all(
        self,
        sources: Union[Any, List[Any]] = None,
        targets: Union[Any, List[Any]] = None
    ) -> None:
        """Prevent multiple sources from being assigned to multiple targets.

        This is a convenience method that creates cross-product forbid constraints.
        It's useful for forbidding entire categories of assignments at once.

        Args:
            sources: Single source or list of sources to forbid from targets.
                    If None, applies to all sources in the problem.
            targets: Single target or list of targets to forbid.
                    If None, applies to all targets in the problem.

        Examples:
            # Forbid all dungeon locations from getting RED_POTION
            solver.forbid_all(sources=dungeon_locations, targets=Item.RED_POTION)

            # Forbid all shop locations from getting any heart containers
            solver.forbid_all(sources=shop_locations, targets=[Item.HEART_CONTAINER])

            # Forbid multiple items from multiple locations
            solver.forbid_all(
                sources=[loc1, loc2, loc3],
                targets=[Item.A, Item.B, Item.C]
            )

        Raises:
            ValueError: If any source or target is not in the problem
        """
        # Normalize inputs to lists
        if sources is None:
            sources = self.permutation_keys if self.permutation_mode else self.sources
        elif not isinstance(sources, (list, tuple)):
            sources = [sources]

        if targets is None:
            targets = self.permutation_values if self.permutation_mode else self.targets
        elif not isinstance(targets, (list, tuple)):
            targets = [targets]

        # Apply forbid constraint for each source-target pair
        constraint_count = 0
        for source in sources:
            for target in targets:
                self.forbid(source, target)
                constraint_count += 1

        log.debug(f"Added {constraint_count} forbid constraints ({len(sources)} sources × {len(targets)} targets)")

    def at_least_one_of(
        self,
        sources: Union[Any, List[Any]],
        targets: Union[Any, List[Any]]
    ) -> None:
        """Require that at least one source receives at least one of the target values.

        Works for both standard assignment problems and permutation problems.

        Args:
            sources: Single source or list of sources/keys to consider.
            targets: Single target or list of targets/values that must appear.

        Raises:
            ValueError: If sources/targets are empty or reference items not in the problem.
        """
        # Normalize inputs to ordered, unique lists
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

        bool_vars = []

        if self.permutation_mode:
            # Map sources to key indices
            key_indices = []
            for src in sources:
                try:
                    key_indices.append(self.permutation_keys.index(src))
                except ValueError:
                    raise ValueError(f"Source {src} not in permutation keys")

            # Map targets to all value indices (values may appear multiple times)
            target_index_map: Dict[Any, List[int]] = {}
            for tgt in targets:
                indices = [i for i, val in enumerate(self.permutation_values) if val == tgt]
                if not indices:
                    raise ValueError(f"Target {tgt} not in permutation values")
                target_index_map[tgt] = indices

            for key_idx in key_indices:
                for indices in target_index_map.values():
                    for value_idx in indices:
                        bool_var = self.model.NewBoolVar(f"alo_{self._bool_var_counter}")
                        self._bool_var_counter += 1
                        self.model.Add(self.var_map[key_idx] == value_idx).OnlyEnforceIf(bool_var)
                        bool_vars.append(bool_var)
        else:
            # Standard assignment mode
            for src in sources:
                if src not in self.var_map:
                    raise ValueError(f"Source {src} not in assignment problem")

                for tgt in targets:
                    if tgt not in self.target_set:
                        raise ValueError(f"Target {tgt} not in valid targets")

                    bool_var = self.model.NewBoolVar(f"alo_{self._bool_var_counter}")
                    self._bool_var_counter += 1
                    self.model.Add(self.var_map[src] == tgt).OnlyEnforceIf(bool_var)
                    bool_vars.append(bool_var)

        if not bool_vars:
            raise ValueError("at_least_one_of could not create any valid source/target combinations")

        # Require at least one of the auxiliary boolean variables to be true
        self.model.AddBoolOr(bool_vars)

    def solve(
        self,
        seed: Optional[int] = None,
        time_limit_seconds: float = 10.0
    ) -> Optional[Dict[Any, Any]]:
        """Solve the assignment problem and return one valid solution.

        Args:
            seed: Random seed for deterministic solving (default: None)
            time_limit_seconds: Maximum time to spend solving (default: 10.0)

        Returns:
            Dictionary mapping source -> target if solution found, None otherwise.

            In permutation mode: Returns key -> value mapping
            Example: {0x77: CaveType.WOOD_SWORD_CAVE, 0x01: CaveType.SHOP_1, ...}

            In assignment mode: Returns source -> target mapping
            Example: {source1: target1, source2: target2, ...}

        Example:
            # Permutation mode
            solution = solver.solve(seed=12345)
            if solution:
                for screen, cave in solution.items():
                    print(f"Screen {hex(screen)} gets {cave}")
        """
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit_seconds

        # Set random seed for determinism
        if seed is not None:
            solver.parameters.random_seed = seed
            log.debug(f"Solving with random seed: {seed}")
        else:
            solver.parameters.random_seed = 0
        # Single worker + deterministic search prevents run-to-run races between threads.
        solver.parameters.num_search_workers = 1
        solver.parameters.randomize_search = True

        # Apply any recorded forbidden assignments (if not already added).
        if self.forbidden_solution_maps:
            if self.permutation_mode:
                ordered_vars = [self.var_map[i] for i in range(len(self.permutation_keys))]
            else:
                ordered_vars = [self.var_map[src] for src in self.sources]

            for solution_map in self.forbidden_solution_maps:
                fingerprint = tuple(sorted((repr(k), repr(v)) for k, v in solution_map.items()))
                if fingerprint in self._applied_forbidden_fingerprints:
                    continue
                index_map = self._solution_map_to_indices(solution_map)
                if not index_map:
                    log.debug("Skipping malformed forbidden solution map: %s", solution_map)
                    continue
                if self.permutation_mode:
                    ordered_values = [index_map[key] for key in self.permutation_keys]
                else:
                    ordered_values = [index_map[src] for src in self.sources]
                self.model.AddForbiddenAssignments(ordered_vars, [ordered_values])
                self._applied_forbidden_fingerprints.add(fingerprint)
        # Solve the model
        status = solver.Solve(self.model)

        # Check if we found a solution
        if status == cp_model.OPTIMAL:
            log.debug("Found optimal solution")
        elif status == cp_model.FEASIBLE:
            log.debug("Found feasible solution")
        elif status == cp_model.INFEASIBLE:
            log.error("No solution exists - constraints are contradictory")
            return None
        else:
            log.error(f"Solver failed with status: {status}")
            return None

        # Build solution based on mode
        self.last_solution = {}
        self.last_solution_indices = {}
        if self.permutation_mode:
            # Translate from indices back to keys/values
            solution = {}
            for key_idx, var in self.var_map.items():
                value_idx = solver.Value(var)
                key = self.permutation_keys[key_idx]
                value = self.permutation_values[value_idx]
                solution[key] = value
                self.last_solution[key] = value
                self.last_solution_indices[key] = value_idx
            return solution
        else:
            # Original assignment mode
            solution = {src: solver.Value(var) for src, var in self.var_map.items()}
            self.last_solution = solution.copy()
            self.last_solution_indices = solution.copy()
            return solution

    def get_stats(self) -> Dict[str, int]:
        """Get statistics about the assignment problem.

        Returns:
            Dictionary with problem statistics
        """
        return {
            "num_sources": len(self.sources),
            "num_targets": len(self.targets),
            "num_variables": len(self.var_map),
            "num_constraints": self.model.Proto().constraints_size
        }

    def forbid_solution_indices(self, solution_indices: Dict[Any, int]) -> None:
        """Forbid a full assignment identified by key -> value-index mapping."""
        if self.permutation_mode:
            ordered_vars = [self.var_map[i] for i in range(len(self.permutation_keys))]
            ordered_values = [
                solution_indices[self.permutation_keys[i]]
                for i in range(len(self.permutation_keys))
            ]
            self.model.AddForbiddenAssignments(ordered_vars, [ordered_values])
        else:
            ordered_vars = [self.var_map[src] for src in self.sources]
            ordered_values = [solution_indices[src] for src in self.sources]
            self.model.AddForbiddenAssignments(ordered_vars, [ordered_values])

    def add_forbidden_solution_map(self, solution_map: Dict[Any, Any]) -> None:
        """Record a full source->target mapping that should be excluded."""
        self.forbidden_solution_maps.append(solution_map.copy())

    def clear_forbidden_solution_maps(self) -> None:
        """Remove any previously recorded forbidden assignments."""
        self.forbidden_solution_maps.clear()
        self._applied_forbidden_fingerprints.clear()

    def _solution_map_to_indices(self, solution_map: Dict[Any, Any]) -> Optional[Dict[Any, int]]:
        """Convert a source->target mapping into internal index form."""
        if self.permutation_mode:
            value_positions: Dict[Any, List[int]] = {}
            for idx, value in enumerate(self.permutation_values):
                value_positions.setdefault(value, []).append(idx)

            value_usage: Dict[Any, int] = {}
            index_map: Dict[Any, int] = {}
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
                index_map[key] = positions[usage]
                value_usage[target_value] = usage + 1
            return index_map
        else:
            # Non-permutation mode already works in target values.
            index_map: Dict[Any, int] = {}
            for source in self.sources:
                if source not in solution_map:
                    return None
                target_value = solution_map[source]
                if target_value not in self.target_set:
                    return None
                index_map[source] = target_value
            return index_map

    # ----------------------------------------------------------------------
    # One-to-one assignment API - not currently used by the project.
    # These helpers remain available for future features that need
    # classic bipartite matching instead of permutation shuffles.

    def add_assignment_problem(self, sources: List[Any], targets: List[Any]) -> None:
        """Define a classic one-to-one assignment problem."""
        if len(sources) != len(targets):
            raise ValueError(
                f"Sources and targets must have same length. "
                f"Got {len(sources)} sources and {len(targets)} targets."
            )

        self.sources = sources
        self.targets = targets
        self.target_set = set(targets)

        for src in sources:
            var = self.model.NewIntVarFromDomain(
                cp_model.Domain.FromValues(targets),
                f"assign_{src}"
            )
            self.var_map[src] = var

        self.model.AddAllDifferent([self.var_map[s] for s in sources])

    def allow_only(
        self,
        sources: Union[Any, List[Any]],
        targets: List[Any]
    ) -> None:
        """Restrict sources to only the specified targets."""
        if not isinstance(sources, (list, tuple)):
            sources = [sources]

        if self.permutation_mode:
            try:
                key_indices = [self.permutation_keys.index(src) for src in sources]
                value_indices = [self.permutation_values.index(tgt) for tgt in targets]
            except ValueError as e:
                raise ValueError(
                    f"In permutation mode: all sources must be in keys, "
                    f"all targets must be in values. Error: {e}"
                )

            allowed_domain = cp_model.Domain.FromValues(value_indices)
            for key_idx in key_indices:
                self.model.AddLinearExpressionInDomain(
                    self.var_map[key_idx],
                    allowed_domain
                )
        else:
            for target in targets:
                if target not in self.target_set:
                    raise ValueError(f"Target {target} not in valid targets")

            allowed_domain = cp_model.Domain.FromValues(targets)
            for src in sources:
                if src not in self.var_map:
                    raise ValueError(f"Source {src} not in assignment problem")

                self.model.AddLinearExpressionInDomain(
                    self.var_map[src],
                    allowed_domain
                )

    def forbid_group(
        self,
        sources: Union[Any, List[Any]],
        targets: List[Any]
    ) -> None:
        """Forbid sources from the specified targets."""
        if not isinstance(sources, (list, tuple)):
            sources = [sources]

        if self.permutation_mode:
            try:
                key_indices = [self.permutation_keys.index(src) for src in sources]
            except ValueError as e:
                raise ValueError(
                    f"In permutation mode: all sources must be in keys. Error: {e}"
                )

            forbidden_value_indices = set()
            for target in targets:
                matching_indices = [
                    i for i, val in enumerate(self.permutation_values) if val == target
                ]
                if not matching_indices:
                    raise ValueError(
                        f"In permutation mode: all targets must be in values. Target {target} missing."
                    )
                forbidden_value_indices.update(matching_indices)

            for key_idx in key_indices:
                for value_idx in forbidden_value_indices:
                    self.model.Add(self.var_map[key_idx] != value_idx)
        else:
            for target in targets:
                if target not in self.target_set:
                    raise ValueError(f"Target {target} not in valid targets")

            for src in sources:
                if src not in self.var_map:
                    raise ValueError(f"Source {src} not in assignment problem")

                for target in targets:
                    self.model.Add(self.var_map[src] != target)
