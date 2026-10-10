"""Change "Leave your..." Rooms (B23; PS-MERCH-04): the life-or-money toll."""

from ...model.enums import TollOption
from ...model.rooms import LifeOrMoneyToll
from ..rng import IntRng, discard
from .item_shuffle_result import ItemShuffleResult
from .shuffle_bomb_upgrade_men import LEADING_DISCARDS

# PS-MERCH-02's draw order; ordering a pair by it puts life or max bombs first
TOLL_OPTIONS = (TollOption.LIFE, TollOption.MAX_BOMBS, TollOption.KEYS, TollOption.MONEY)
KEY_COSTS = (2, 3, 4)
MONEY_COST_MIN, MONEY_COST_MAX = 30, 70


def change_money_or_life_toll(state: ItemShuffleResult, rng: IntRng) -> None:
    """PS-MERCH-04's draw: two discards, the first option uniform, the
    second redrawn until it differs and the pair is not {keys, money}; the
    pair is ordered so the first option is life or max bombs (TOLL_OPTIONS
    order); a cost is drawn only for a keys or money second option."""
    discard(rng, LEADING_DISCARDS)
    first = rng.below(len(TOLL_OPTIONS))
    while True:
        second = rng.below(len(TOLL_OPTIONS))
        pair = {TOLL_OPTIONS[first], TOLL_OPTIONS[second]}
        if second != first and pair != {TollOption.KEYS, TollOption.MONEY}:
            break
    first, second = sorted((first, second))
    toll = LifeOrMoneyToll(TOLL_OPTIONS[first], TOLL_OPTIONS[second])
    if toll.second == TollOption.KEYS:
        toll.key_cost = KEY_COSTS[rng.below(len(KEY_COSTS))]
    elif toll.second == TollOption.MONEY:
        toll.money_cost = MONEY_COST_MIN + rng.below(MONEY_COST_MAX - MONEY_COST_MIN + 1)
    state.toll = toll
