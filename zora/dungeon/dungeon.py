"""Dungeon randomization orchestrator.

Called by generate_game as a single pipeline step. Dispatches to the
individual dungeon randomization functions in the correct order, gating
each on the appropriate GameConfig flags.

Call order:
1. shuffle_dungeon_rooms — shuffles room contents within each level
"""

from __future__ import annotations

from zora.data_model import GameWorld
from zora.dungeon.shuffle_dungeon_rooms import shuffle_dungeon_rooms
from zora.game_config import GameConfig
from zora.rng import Rng


def randomize_dungeons(
    game_world: GameWorld,
    config: GameConfig,
    rng: Rng,
) -> None:
    """Run all dungeon randomization steps in order.

    Each sub-function either self-gates on its config flags or is gated
    here. The call order matters — future dungeon randomization steps
    may depend on the room shuffle having already run.

    Args:
        game_world: The game state to modify in place.
        config: Resolved game configuration.
        rng: Shared RNG instance (state flows between steps).
    """
    if config.shuffle_dungeon_rooms:
        if not shuffle_dungeon_rooms(game_world, rng):
            raise RuntimeError("Dungeon room shuffle failed")
