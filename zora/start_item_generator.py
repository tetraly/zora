"""
Start-item generation.

Resolves the user's Start Items flag selections (per-item tristates, hearts,
max-items cap, triforce count) into a concrete set of starting equipment for
a single seed. The result is consumed only by the ROM patcher — assumed_fill
is intentionally unaware of these items (option 1 in the design discussion).

Logic-integration note (option 2, deferred):
    A future revision could remove the granted items from the placement pool
    and seed them into the assumed inventory in zora/item_randomizer.py to
    avoid placing duplicates of items the player already starts with. The
    simplest hook would be near assumed_fill() line ~735, after
    _collect_item_pool: drop one occurrence of each Item in
    config.start_items.items from item_pool, then add them to the assumed
    Inventory at both build sites (~lines 779 and ~861). Triforces would
    additionally pre-seed assumed.levels_with_triforce_obtained. For MVP
    we accept that some seeds will place a duplicate (e.g. a redundant bow)
    in the world.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from flags.flags_generated import (
    Flags,
    MaxStartItems,
    StartHearts,
    StartTriforce,
    Tristate,
)
from zora.data_model import Item
from zora.rng import Rng


# Mapping from Flags field name → zora Item enum value.
# Order matters: this is also the iteration order used to resolve tristates,
# so changing it would change the RNG draw sequence and break seed determinism.
_START_ITEM_FLAGS: tuple[tuple[str, Item], ...] = (
    ("start_wood_sword",        Item.WOOD_SWORD),
    ("start_white_sword",       Item.WHITE_SWORD),
    ("start_magical_sword",     Item.MAGICAL_SWORD),
    ("start_bombs",             Item.BOMBS),
    ("start_bow",               Item.BOW),
    ("start_wood_arrows",       Item.WOOD_ARROWS),
    ("start_silver_arrows",     Item.SILVER_ARROWS),
    ("start_blue_candle",       Item.BLUE_CANDLE),
    ("start_red_candle",        Item.RED_CANDLE),
    ("start_recorder",          Item.RECORDER),
    ("start_bait",              Item.BAIT),
    ("start_wand",              Item.WAND),
    ("start_raft",              Item.RAFT),
    ("start_book",              Item.BOOK),
    ("start_blue_ring",         Item.BLUE_RING),
    ("start_red_ring",          Item.RED_RING),
    ("start_ladder",            Item.LADDER),
    ("start_magical_key",       Item.MAGICAL_KEY),
    ("start_power_bracelet",    Item.POWER_BRACELET),
    ("start_letter",            Item.LETTER),
    ("start_wood_boomerang",    Item.WOOD_BOOMERANG),
    ("start_magical_boomerang", Item.MAGICAL_BOOMERANG),
    ("start_magic_shield",      Item.MAGICAL_SHIELD),
)

# Single-slot upgrade chains. Z1 stores one byte per slot (sword tier, ring
# tier, etc.); if the user grants multiple tiers we keep only the highest so
# the inventory byte ends up well-defined.
_UPGRADE_GROUPS: tuple[tuple[Item, ...], ...] = (
    (Item.WOOD_SWORD, Item.WHITE_SWORD, Item.MAGICAL_SWORD),
    (Item.WOOD_ARROWS, Item.SILVER_ARROWS),
    (Item.BLUE_CANDLE, Item.RED_CANDLE),
    (Item.BLUE_RING, Item.RED_RING),
    (Item.WOOD_BOOMERANG, Item.MAGICAL_BOOMERANG),
)


@dataclass(frozen=True)
class StartItemResult:
    items: tuple[Item, ...] = ()
    start_hearts: int = 3
    triforce_mask: int = 0  # 8-bit bitmask, bit i = triforce piece i+1
    bombs_granted: bool = field(default=False)


def _resolve_tristate(state: Tristate, rng: Rng) -> bool:
    if state == Tristate.ON:
        return True
    if state == Tristate.OFF:
        return False
    return rng.random() < 0.5


def _dedup_upgrades(items: list[Item]) -> list[Item]:
    """Within each upgrade group, keep only the highest tier present."""
    items_set = set(items)
    for group in _UPGRADE_GROUPS:
        present = [i for i in group if i in items_set]
        if len(present) > 1:
            keep = present[-1]
            for drop in present[:-1]:
                items_set.discard(drop)
            items_set.add(keep)
    # Preserve original order, filtered by the dedup set.
    seen: set[Item] = set()
    out: list[Item] = []
    for it in items:
        if it in items_set and it not in seen:
            out.append(it)
            seen.add(it)
    return out


def _resolve_start_hearts(value: StartHearts, rng: Rng) -> int:
    if value == StartHearts.RANDOM_1_5:
        # rng.choice is uniform over the sequence; matches "1-5 hearts".
        return rng.choice([1, 2, 3, 4, 5])
    # The enum ids one..sixteen map to ints 1..16; index() == 0 is "one".
    return int(value) + 1


# Order of MaxStartItems enum: ALL, N_0..N_20, RANDOM. Index 1 == 0 items.
def _resolve_max_start_items(value: MaxStartItems, rng: Rng) -> int | None:
    if value == MaxStartItems.ALL:
        return None
    if value == MaxStartItems.RANDOM:
        return rng.choice(list(range(0, 21)))
    return int(value) - 1  # N_0 has index 1, so subtract 1


def _resolve_start_triforce(value: StartTriforce, rng: Rng) -> int:
    if value == StartTriforce.RANDOM:
        return rng.choice(list(range(0, 9)))
    return int(value)  # T_0..T_8 are indices 0..8


def _build_triforce_mask(count: int, rng: Rng) -> int:
    if count <= 0:
        return 0
    pieces = list(range(8))
    rng.shuffle(pieces)
    mask = 0
    for bit in pieces[:count]:
        mask |= 1 << bit
    return mask


def generate_start_items(flags: Flags, rng: Rng) -> StartItemResult:
    """Resolve the Start Items flags into a concrete StartItemResult.

    Always consumes RNG draws in a fixed order (one tristate-resolve per item
    flag in declaration order, then max/hearts/triforce) so seed reproducibility
    is preserved regardless of which items end up granted.
    """
    items: list[Item] = []
    for field_name, item_value in _START_ITEM_FLAGS:
        state = getattr(flags, field_name, Tristate.OFF)
        if _resolve_tristate(state, rng):
            items.append(item_value)

    items = _dedup_upgrades(items)

    cap = _resolve_max_start_items(flags.max_start_items, rng)
    if cap is not None and cap < len(items):
        # Fisher-Yates partial shuffle: fully randomize which `cap` items are kept.
        for i in range(cap):
            j = i + int(rng.random() * (len(items) - i))
            if j >= len(items):
                j = len(items) - 1
            items[i], items[j] = items[j], items[i]
        items = items[:cap]

    bombs_granted = Item.BOMBS in items
    # Bombs are tracked separately on the ROM side (capacity + count fields)
    # so drop the BOMBS sentinel from the inventory-byte list.
    items_for_table = [it for it in items if it != Item.BOMBS]

    hearts = _resolve_start_hearts(flags.start_hearts, rng)
    triforce_count = _resolve_start_triforce(flags.start_triforce, rng)
    triforce_mask = _build_triforce_mask(triforce_count, rng)

    return StartItemResult(
        items=tuple(items_for_table),
        start_hearts=hearts,
        triforce_mask=triforce_mask,
        bombs_granted=bombs_granted,
    )
