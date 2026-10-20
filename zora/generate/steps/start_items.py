"""Starting items (features-behavior.md FP-START-02 to FP-START-05): which start items a seed gets.

The chosen items are the start-item fields that are on, after FL-DEP-04 has turned each possible
field into on or off by its coin; Max start items (C17, already resolved when at Random) then
limits them. The kept items go into the starting table (FP-START-03, zora/rom/start_items.py).
FP-START-04: item placement, the shuffles and the acceptance walk never read them; only the
wooden-sword cave pass (B03, OW-CAVE-07) does.

The draws come from their own streams, so a seed's other draws are the same with or without start
items: each possible field's coin from the coin stream (start_item_coins_rng), one draw per field in
the fixed order whatever the field's value (FP-START-02), and the limit's from start_items_rng, which
draws nothing for a seed that keeps every chosen item (or none)."""
import hashlib
from dataclasses import dataclass

from ...flags.dependencies import start_item_limit, starting_pieces
from ...flags.fields import TOGGLES_BY_ID, Settings, ThreeState, ToggleField
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

# Each stream's key: the seed number as eight bytes, and its own label.
SEED_BYTES = 8
START_ITEMS_STREAM = b"zora start items"
START_ITEM_COINS_STREAM = b"zora start coins"
COIN_SIDES = (ThreeState.OFF, ThreeState.ON)
TRIFORCE_LEVELS = 8
ALL_PIECES = (1 << TRIFORCE_LEVELS) - 1


def _stream(seed: int, flag_string: str, label: bytes) -> Rng:
    key = hashlib.blake2b(flag_string.encode("utf-8"), key=seed.to_bytes(SEED_BYTES, "little"),
                          digest_size=SEED_BYTES, person=label).digest()
    return Rng(int.from_bytes(key, "little"))


def start_items_rng(seed: int, flag_string: str) -> Rng:
    """The stream that draws the kept start items: derived from the seed number and the canonical
    flag string only, apart from the generation's stream and the "?" stream."""
    return _stream(seed, flag_string, START_ITEMS_STREAM)


def start_item_coins_rng(seed: int, flag_string: str) -> Rng:
    """The stream of the possible start items' coins, apart from every other stream."""
    return _stream(seed, flag_string, START_ITEM_COINS_STREAM)


def resolve_start_item_coins(settings: Settings, seed: int, flag_string: str) -> Settings:
    """FP-START-02 and FL-DEP-04: each possible start-item field on or off by its own fair coin. One
    coin per field in the fixed order whatever the field's value, so a field's coin never depends on
    the others' values, and the "?" stream draws nothing for a start item."""
    coins = start_item_coins_rng(seed, flag_string)
    resolved: dict[str, ThreeState] = {}
    for field, _ in START_ITEM_ORDER:
        coin = coins.choice(COIN_SIDES)
        if settings.toggle(field) is ThreeState.POSSIBLE:
            resolved[field.id] = coin
    return settings.updated(toggles=resolved) if resolved else settings


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


@dataclass(frozen=True)
class StartState:
    """What a new save file starts with beyond PRG0's: the kept start items and the start pieces
    (one bit per level 1-8, InvTriforce)."""
    items: tuple[Item, ...] = ()
    triforce_pieces: int = 0


def start_items(settings: Settings, seed: int, flag_string: str) -> tuple[Item, ...]:
    """FP-START-02 and FP-START-05: the start items a seed keeps, from its resolved settings."""
    return start_state(settings, seed, flag_string).items


def start_state(settings: Settings, seed: int, flag_string: str) -> StartState:
    """FP-START-02, FP-START-05 and FL-ALT-06, all from the start-item stream: the limit's draws
    first, then the start pieces'. A seed with no start items and no start pieces draws nothing."""
    rng = start_items_rng(seed, flag_string)
    chosen = chosen_start_items(settings)
    items = keep_at_most(chosen, start_item_limit(settings), rng) if chosen else ()
    return StartState(items, draw_start_pieces(starting_pieces(settings), rng))


def draw_start_pieces(count: int, rng: IntRng) -> int:
    """FL-ALT-06: `count` of the eight pieces drawn uniformly without replacement (every set
    equally likely), as InvTriforce's bits; no draw for 0 or for all eight."""
    if count in (0, TRIFORCE_LEVELS):
        return ALL_PIECES if count else 0
    levels = list(range(TRIFORCE_LEVELS))
    for position in range(count):           # the first `count` steps of a Fisher-Yates shuffle
        swap = position + rng.below(TRIFORCE_LEVELS - position)
        levels[position], levels[swap] = levels[swap], levels[position]
    return sum(1 << level for level in levels[:count])
