"""Change MMG (B11; FP-MMG-01): the money-making game's amounts."""

from zora.generate.rng import Rng
from zora.model.enums import Destination
from zora.model.game_world import GameWorld
from zora.model.overworld import MoneyMakingGameCave


def change_money_making_game(gw: GameWorld, rng: Rng) -> None:
    """Change MMG (FP-MMG-01): the money-making game's amounts, p1 1..20,
    p2 30..50, s 10..30, l 25..75, p3 1..20."""
    money_making_game = gw.overworld.get_cave(Destination.MONEY_MAKING_GAME, MoneyMakingGameCave)
    if money_making_game is not None:
        money_making_game.lose_small = rng.below(20) + 1
        money_making_game.lose_large = rng.below(21) + 30
        money_making_game.win_small = rng.below(21) + 10
        money_making_game.win_large = rng.below(51) + 25
        money_making_game.lose_small_2 = rng.below(20) + 1
