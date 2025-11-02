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

    def __init__(self):
        """Initialize the assignment solver."""
        if not ORTOOLS_AVAILABLE:
            raise ImportError(
                "OR-Tools is required for AssignmentSolver. "
                "Install with: pip install ortools"
            )

        self.model = cp_model.CpModel()
        self.var_map: Dict[Any, cp_model.IntVar] = {}  # source -> IntVar
        self.sources: List[Any] = []
        self.targets: List[Any] = []
        self.target_set: Set[Any] = set()

        # For permutation mode
        self.permutation_mode: bool = False
        self.permutation_keys: List[Any] = []  # e.g., screen numbers
        self.permutation_values: List[Any] = []  # e.g., cave types (can have duplicates)

    def add_assignment_problem(self, sources: List[Any], targets: List[Any]) -> None:
        """Define the sources and targets for the assignment problem.

        Creates decision variables for each source and ensures all sources
        map to unique targets (one-to-one assignment).

        Args:
            sources: List of items to be assigned (e.g., cave destinations, items)
            targets: List of slots to assign to (e.g., screens, locations)

        Raises:
            ValueError: If sources and targets have different lengths
        """
        if len(sources) != len(targets):
            raise ValueError(
                f"Sources and targets must have same length. "
                f"Got {len(sources)} sources and {len(targets)} targets."
            )

        self.sources = sources
        self.targets = targets
        self.target_set = set(targets)

        # Create integer variables for each source
        # Each variable can be assigned to any target value
        for src in sources:
            var = self.model.NewIntVarFromDomain(
                cp_model.Domain.FromValues(targets),
                f"assign_{src}"
            )
            self.var_map[src] = var

        # Constraint: All sources must map to unique targets (one-to-one)
        self.model.AddAllDifferent([self.var_map[s] for s in sources])

    def add_permutation_problem(
        self,
        keys: List[Any],
        values: List[Any]
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
        """
        if len(keys) != len(values):
            raise ValueError(
                f"Keys and values must have same length. "
                f"Got {len(keys)} keys and {len(values)} values."
            )

        self.permutation_mode = True
        self.permutation_keys = keys
        self.permutation_values = values

        # Internally, we use indices to avoid duplicate value issues
        num_items = len(keys)
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

        Example:
            solver.forbid(Item.RAFT, Location.LEVEL_9_BOSS)
            # Raft can go anywhere except the Level 9 boss location

        Args:
            source: The source to constrain
            target: The target it must NOT be assigned to

        Raises:
            ValueError: If source not in problem or target not valid
        """
        if source not in self.var_map:
            raise ValueError(f"Source {source} not in assignment problem")
        if target not in self.target_set:
            raise ValueError(f"Target {target} not in valid targets")

        self.model.Add(self.var_map[source] != target)
        log.debug(f"Constraint: {source} must NOT map to {target}")

    def allow_only(
        self,
        sources: Union[Any, List[Any]],
        targets: List[Any]
    ) -> None:
        """Restrict source(s) to only be assigned to specific targets.

        In permutation mode:
            sources = keys (e.g., screen numbers that can only get certain caves)
            targets = values (e.g., cave types these screens can receive)

        Example (permutation mode):
            solver.allow_only(
                sources=[0x22, 0x15, 0x84, ...],  # 15 screens
                targets=[CaveType.LEVEL_1, ..., CaveType.LEVEL_9]  # 9 level caves
            )
            # These 15 screens can only get level caves (creates 15-choose-9 constraint)

        Args:
            sources: Single source/key or list of sources/keys to constrain
            targets: List of allowed targets/values for these sources/keys

        Raises:
            ValueError: If any source not in problem or target not valid
        """
        # Handle single source or list of sources
        if not isinstance(sources, (list, tuple)):
            sources = [sources]

        if self.permutation_mode:
            # Convert keys and values to indices
            try:
                key_indices = [self.permutation_keys.index(src) for src in sources]
                value_indices = [self.permutation_values.index(tgt) for tgt in targets]
            except ValueError as e:
                raise ValueError(
                    f"In permutation mode: all sources must be in keys, "
                    f"all targets must be in values. Error: {e}"
                )

            # Create domain from allowed value indices
            allowed_domain = cp_model.Domain.FromValues(value_indices)

            # Apply constraint to each key index
            for key_idx in key_indices:
                self.model.AddLinearExpressionInDomain(
                    self.var_map[key_idx],
                    allowed_domain
                )

            log.debug(f"Constraint: {len(sources)} keys restricted to {len(targets)} values")
        else:
            # Original assignment mode
            # Validate targets
            for target in targets:
                if target not in self.target_set:
                    raise ValueError(f"Target {target} not in valid targets")

            # Create domain from allowed targets
            allowed_domain = cp_model.Domain.FromValues(targets)

            # Apply constraint to each source
            for src in sources:
                if src not in self.var_map:
                    raise ValueError(f"Source {src} not in assignment problem")

                self.model.AddLinearExpressionInDomain(
                    self.var_map[src],
                    allowed_domain
                )

            log.debug(f"Constraint: {len(sources)} sources restricted to {len(targets)} targets")

    def forbid_group(
        self,
        sources: Union[Any, List[Any]],
        targets: List[Any]
    ) -> None:
        """Prevent source(s) from being assigned to any of the specified targets.

        This is the inverse of allow_only - instead of restricting to a whitelist,
        it creates a blacklist.

        In permutation mode:
            sources = keys (e.g., screen numbers that can't get certain caves)
            targets = values (e.g., cave types these screens cannot receive)

        Example (permutation mode):
            solver.forbid_group(
                sources=[0x01, 0x03, 0x04],  # Non-vanilla screens
                targets=[CaveType.LEVEL_1, ..., CaveType.LEVEL_9]  # Level caves
            )
            # These screens cannot get level caves

        Args:
            sources: Single source or list of sources to constrain
            targets: List of forbidden targets for these sources

        Raises:
            ValueError: If any source not in problem or target not valid
        """
        # Handle single source or list of sources
        if not isinstance(sources, (list, tuple)):
            sources = [sources]

        if self.permutation_mode:
            # Convert keys and values to indices
            try:
                key_indices = [self.permutation_keys.index(src) for src in sources]
            except ValueError as e:
                raise ValueError(
                    f"In permutation mode: all sources must be in keys. Error: {e}"
                )

            # For each target value, find all its indices in the value list
            forbidden_value_indices = set()
            for target in targets:
                try:
                    # Find all occurrences of this value
                    for i, val in enumerate(self.permutation_values):
                        if val == target:
                            forbidden_value_indices.add(i)
                except ValueError as e:
                    raise ValueError(
                        f"In permutation mode: all targets must be in values. Error: {e}"
                    )

            # Apply forbid constraint to each key-value index pair
            for key_idx in key_indices:
                for value_idx in forbidden_value_indices:
                    self.model.Add(self.var_map[key_idx] != value_idx)

            log.debug(f"Constraint: {len(sources)} keys forbidden from {len(targets)} value types")
        else:
            # Original assignment mode
            # Validate targets
            for target in targets:
                if target not in self.target_set:
                    raise ValueError(f"Target {target} not in valid targets")

            # Apply forbid constraint to each source-target pair
            for src in sources:
                if src not in self.var_map:
                    raise ValueError(f"Source {src} not in assignment problem")

                for target in targets:
                    self.model.Add(self.var_map[src] != target)

            log.debug(f"Constraint: {len(sources)} sources forbidden from {len(targets)} targets")

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
        if self.permutation_mode:
            # Translate from indices back to keys/values
            solution = {}
            for key_idx, var in self.var_map.items():
                value_idx = solver.Value(var)
                key = self.permutation_keys[key_idx]
                value = self.permutation_values[value_idx]
                solution[key] = value
            return solution
        else:
            # Original assignment mode
            return {src: solver.Value(var) for src, var in self.var_map.items()}

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
