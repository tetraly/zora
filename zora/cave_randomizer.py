from zora.data_model import (
    Destination,
    GameWorld,
    Item,
    ItemCave,
    MoneyMakingGameCave,
    TakeAnyCave,
)
from zora.game_config import GameConfig
from zora.rng import Rng


def randomize_caves(game_world: GameWorld, config: GameConfig, rng: Rng) -> None:
    ow = game_world.overworld

    if config.randomize_mmg:
        mmg = ow.get_cave(Destination.MONEY_MAKING_GAME, MoneyMakingGameCave)
        if mmg is None:
            raise ValueError("No MoneyMakingGameCave found in overworld caves")

        mmg.lose_small   = rng.choice(range(1, 21))
        mmg.lose_small_2 = rng.choice(range(1, 21))
        mmg.lose_large   = rng.choice(range(30, 51))
        mmg.win_small    = rng.choice(range(10, 31))
        mmg.win_large    = rng.choice(range(25, 76))
        # lose_large must not equal win_small (win-check uses exact value match)
        while mmg.lose_large == mmg.win_small:
            mmg.lose_large = rng.choice(range(30, 51))
        # win_large must exceed win_small
        while mmg.win_large <= mmg.win_small:
            mmg.win_large = rng.choice(range(25, 76))

    if config.add_extra_candles:
        wood_sword_cave = ow.get_cave(Destination.WOOD_SWORD_CAVE, ItemCave)
        if wood_sword_cave is not None:
            wood_sword_cave.maybe_extra_candle = Item.BLUE_CANDLE
        take_any = ow.get_cave(Destination.TAKE_ANY, TakeAnyCave)
        if take_any is not None:
            take_any.items[1] = Item.BLUE_CANDLE

    if config.randomize_bomb_upgrade:
        ow.bomb_upgrade.cost  = rng.choice(range(75, 126))
        ow.bomb_upgrade.count = rng.choice(range(2, 7))

    if config.randomize_white_sword_hearts:
        white_sword_cave = ow.get_cave(Destination.WHITE_SWORD_CAVE, ItemCave)
        if white_sword_cave is not None:
            white_sword_cave.heart_requirement = rng.choice([4, 5, 6])

    if config.randomize_magical_sword_hearts:
        magical_sword_cave = ow.get_cave(Destination.MAGICAL_SWORD_CAVE, ItemCave)
        if magical_sword_cave is not None:
            magical_sword_cave.heart_requirement = rng.choice([10, 11, 12])
