"""Starting items (features-behavior.md FP-START-02 to FP-START-05): which start items a seed gets.

The chosen items are the start-item fields that are on, after FL-DEP-04 has turned each possible
field into on or off by its coin; Max start items (C17, already resolved when at Random) then
limits them. The kept items go into the starting table (FP-START-03, zora/rom/start_items.py).
FP-START-04: item placement, the shuffles and the acceptance walk never read them; only the
wooden-sword cave pass (B03, OW-CAVE-07) does.

The draws come from their own stream (start_items_rng), so a seed's other draws are the same
with or without start items, and a seed that keeps every chosen item (or none) draws nothing."""
import hashlib

from ...flags.dependencies import start_item_limit
from ...flags.fields import TOGGLES_BY_ID, Settings, ToggleField
from ...model.enums import Item
from ..rng import IntRng, Rng

# FP-START-02's fixed order of the twenty-three fields, each with its item.
START_ITEM_ORDER: tuple[tuple[ToggleField, Item], ...] = tuple((TOGGLES_BY_ID[field_id], item) for field_id, item in (
    ("B68", Item.WOOD_SWORD), ("B69", Item.WHITE_SWORD), ("B70", Item.MAGICAL_SWORD),
    ("B59", Item.BOMBS), ("B71", Item.WOOD_ARROWS), ("B72", Item.SILVER_ARROWS), ("B58", Item.BOW),
    ("B73", Item.BLUE_CANDLE), ("B74", Item.RED_CANDLE),
    ("B60", Item.RECORDER), ("B61", Item.BAIT), ("B66", Item.WAND), ("B57", Item.RAFT), ("B67", Item.BOOK),
    ("B75", Item.BLUE_RING), ("B76", Item.RED_RING), ("B65", Item.LADDER), ("B62", Item.MAGICAL_KEY),
    ("B64", Item.POWER_BRACELET), ("B63", Item.LETTER), ("B77", Item.WOOD_BOOMERANG),
    ("B78", Item.MAGICAL_BOOMERANG), ("B85", Item.MAGICAL_SHIELD),
))

# The stream's key: the seed number as eight bytes, and its own label.
SEED_BYTES = 8
START_ITEMS_STREAM = b"zora start items"


def start_items_rng(seed: int, flag_string: str) -> Rng:
    """The stream that draws the kept start items: derived from the seed number and the canonical
    flag string only, apart from the generation's stream and the "?" stream."""
    key = hashlib.blake2b(flag_string.encode("utf-8"), key=seed.to_bytes(SEED_BYTES, "little"),
                          digest_size=SEED_BYTES, person=START_ITEMS_STREAM).digest()
    return Rng(int.from_bytes(key, "little"))


def chosen_start_items(settings: Settings) -> tuple[Item, ...]:
    """FP-START-02: the items whose fields are on, in the fixed order (settings already resolved)."""
    return tuple(item for field, item in START_ITEM_ORDER if settings.is_on(field))


def keep_at_most(chosen: tuple[Item, ...], limit: int | None, rng: IntRng) -> tuple[Item, ...]:
    """FP-START-02's limit: every chosen item when there is no limit or the list is not longer than
    it; otherwise `limit` of them drawn uniformly without replacement (every set equally likely),
    kept in the fixed order. No draw unless items must be dropped."""
    if limit is None or len(chosen) <= limit:
        return chosen
    indices = list(range(len(chosen)))
    for position in range(limit):           # the first `limit` steps of a Fisher-Yates shuffle
        swap = position + rng.below(len(indices) - position)
        indices[position], indices[swap] = indices[swap], indices[position]
    return tuple(chosen[index] for index in sorted(indices[:limit]))


def start_items(settings: Settings, seed: int, flag_string: str) -> tuple[Item, ...]:
    """FP-START-02 and FP-START-05: the start items a seed keeps, from its resolved settings."""
    chosen = chosen_start_items(settings)
    if not chosen:
        return ()
    return keep_at_most(chosen, start_item_limit(settings), start_items_rng(seed, flag_string))
