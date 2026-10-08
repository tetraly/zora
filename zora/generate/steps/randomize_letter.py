"""Randomize Letter (ZORA flag; docs/zora-extras.md): the letter joins the
major-item pool, and the letter cave offers whatever item lands there. No
new logic rules: the letter is not a tracked item, and the item it
displaces into the letter cave is judged by that cave's screen needs
(extra_pool_items.is_extra_slot_collected)."""
from __future__ import annotations

from zora.generate.rng import IntRng
from zora.generate.steps.extra_pool_items import ExtraPoolItems, PoolPlace, join_pool
from zora.generate.steps.item_shuffle_result import LETTER_SLOT, ItemShuffleOptions, ItemShuffleResult
from zora.model.levels import Level
from zora.model.overworld import Overworld


def randomize_letter(levels: list[Level], state: ItemShuffleResult, extras: ExtraPoolItems,
                     overworld: Overworld, rng: IntRng, opts: ItemShuffleOptions | None = None) -> PoolPlace | None:
    """Randomize Letter: the letter cave joins the pool. One draw; returns
    the place the letter went to (None: it stayed)."""
    return join_pool(LETTER_SLOT, levels, state, extras, overworld, rng, opts)
