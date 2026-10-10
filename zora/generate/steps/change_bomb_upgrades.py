"""Change Bomb Upgrades (B12; FP-BOMB-01)."""

from ...model.game_world import GameWorld
from ...model.overworld import BombUpgrade
from ..rng import Rng


def change_bomb_upgrades(gw: GameWorld, rng: Rng) -> None:
    """Change Bomb Upgrades (FP-BOMB-01): price 75..125, capacity 2..6."""
    gw.overworld.bomb_upgrade = BombUpgrade(
        cost=rng.below(51) + 75,
        count=rng.below(5) + 2,
    )
