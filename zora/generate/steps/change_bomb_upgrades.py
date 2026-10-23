"""Change Bomb Upgrades (B12) and Increase Bomb Capacity Upgrade (B90); FP-BOMB-01."""

from ...model.game_world import GameWorld
from ...model.overworld import BombUpgrade
from ..rng import Rng

LARGER_CAPACITY = 2              # B90: bombs added on top of the drawn (or PRG0's) capacity


def change_bomb_upgrades(gw: GameWorld, rng: Rng | None, larger_capacity: bool = False) -> None:
    """Change Bomb Upgrades (rng given): price 75..125, capacity 2..6; Increase Bomb Capacity
    Upgrade: 2 more capacity, on the drawn values or on PRG0's (100 rupees, 4 bombs) with B12 off."""
    upgrade = gw.overworld.bomb_upgrade
    if rng is not None:
        upgrade = BombUpgrade(cost=rng.below(51) + 75, count=rng.below(5) + 2)
    if larger_capacity:
        upgrade = BombUpgrade(cost=upgrade.cost, count=upgrade.count + LARGER_CAPACITY)
    gw.overworld.bomb_upgrade = upgrade
