"""Randomize Letter (ZORA flag; docs/zora-extras.md): the letter joins the
major-item pool, and the letter cave offers whatever item lands there. No
new logic rules: the letter is not a tracked item, and the item it
displaces into the letter cave is judged by that cave's screen needs
(extra_pool_items.is_extra_slot_collected)."""
from __future__ import annotations

from ...model.levels import Level
from ...model.overworld import Overworld
from ..rng import IntRng
from .extra_pool_items import ExtraPoolItems, PoolPlace, join_pool
from .item_shuffle_result import LETTER_SLOT, ItemShuffleOptions, ItemShuffleResult


def randomize_letter(levels: list[Level], state: ItemShuffleResult, extras: ExtraPoolItems,
                     overworld: Overworld, rng: IntRng, opts: ItemShuffleOptions | None = None) -> PoolPlace | None:
    """Randomize Letter: the letter cave joins the pool. One draw; returns
    the place the letter went to (None: it stayed)."""
    return join_pool(LETTER_SLOT, levels, state, extras, overworld, rng, opts)
