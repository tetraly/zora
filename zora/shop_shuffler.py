"""
Shop item shuffler.

Shuffles the 12 items across shops A-D, jitters prices, and randomizes
prices for the potion shop, secret caves, and door repair cave.

When shuffle_major_shop_items is on, normalizer.py will have already replaced
the second BAIT with a FAIRY before assumed fill runs, so the shop item pool
seen here reflects that normalization.

The shuffler guarantees at least one major item per shop: major items are
distributed round-robin across shops, with any extras wrapping back around.
Non-major items fill remaining slots freely.
"""

from zora.data_model import (
    Destination,
    DoorRepairCave,
    GameWorld,
    Item,
    Overworld,
    SecretCave,
    Shop,
    ShopItem,
)
from zora.game_config import GameConfig
from zora.hint_randomizer import HINTABLE_NICE_TO_HAVE_ITEMS, HINTABLE_PROGRESSION_ITEMS
from zora.item_randomizer import MAJOR_ITEMS
from zora.rng import Rng

_MAJOR_ITEMS: frozenset[Item] = frozenset(MAJOR_ITEMS)

_SHOP_DESTINATIONS = [
    Destination.SHOP_1,
    Destination.SHOP_2,
    Destination.SHOP_3,
    Destination.SHOP_4,
]

_ITEMS_PER_SHOP = 3
_SHOP_COUNT = 4
_TOTAL_SLOTS = _SHOP_COUNT * _ITEMS_PER_SHOP  # 12


def randomize_shops(game_world: GameWorld, config: GameConfig, rng: Rng) -> None:
    """Shuffle shop items across shops A-D and randomize auxiliary prices.

    When config.shuffle_shop_items is False, this function is a no-op.

    Shuffling:
      - Reads all 12 (item, price) pairs from shops A-D.
      - Identifies which items are major items (from MAJOR_ITEMS) and
        distributes them round-robin across shops, guaranteeing at least one
        major item per shop. Non-major items fill remaining slots freely.
      - Jitters each price by a random amount in [-20, +20], clamped to
        [1, 254].

    Auxiliary price randomization (also gated on shuffle_shop_items):
      - Potion shop item 0 price: range [25, 55]
      - Potion shop item 1 price: range [48, 88]
      - Medium secret rupee value: range [25, 40]
      - Large secret rupee value:  range [50, 150]
      - Small secret rupee value:  range [1, 20]
      - Door repair cost:          range [15, 25]
    """
    if not config.shuffle_shop_items:
        return

    ow = game_world.overworld

    # --- Collect shops ---
    shops: list[Shop] = []
    for dest in _SHOP_DESTINATIONS:
        c = ow.get_cave(dest, Shop)
        if c is None:
            raise ValueError(f"Expected Shop at {dest} but found none")
        shops.append(c)

    # --- Build flat list of (item, price) pairs ---
    all_pairs: list[ShopItem] = [
        ShopItem(item=si.item, price=si.price)
        for shop in shops
        for si in shop.items
    ]
    assert len(all_pairs) == _TOTAL_SLOTS

    # --- Separate major items from the rest ---
    major_pairs: list[ShopItem] = []
    free_pairs: list[ShopItem] = []
    for si in all_pairs:
        if si.item in _MAJOR_ITEMS:
            major_pairs.append(si)
        else:
            free_pairs.append(si)

    # --- Assign major items to shops, guaranteeing at least one per shop ---
    # Shuffle both pools, then assign major items round-robin across shops
    # so the first _SHOP_COUNT go one-per-shop. Any extras wrap back around.
    # Each shop's items are then placed at randomized slot positions.
    rng.shuffle(major_pairs)
    rng.shuffle(free_pairs)

    # Distribute major items round-robin so every shop gets at least one.
    shop_majors: list[list[ShopItem]] = [[] for _ in range(_SHOP_COUNT)]
    for i, si in enumerate(major_pairs):
        shop_majors[i % _SHOP_COUNT].append(si)

    result: list[ShopItem] = []
    free_idx = 0

    for shop_idx in range(_SHOP_COUNT):
        majors = shop_majors[shop_idx]
        n_major = len(majors)
        n_free = _ITEMS_PER_SHOP - n_major

        # Build an unordered list of items for this shop, then shuffle positions.
        # When picking free items, swap forward if the candidate would duplicate
        # an item already assigned to this shop.
        shop_items_unordered: list[ShopItem] = list(majors)
        taken: set[Item] = {si.item for si in shop_items_unordered}
        for _ in range(n_free):
            # Find the first free item that doesn't duplicate an existing item.
            swap_target = free_idx
            while swap_target < len(free_pairs) and free_pairs[swap_target].item in taken:
                swap_target += 1
            if swap_target < len(free_pairs):
                # Swap the non-duplicate into position and use it.
                free_pairs[free_idx], free_pairs[swap_target] = free_pairs[swap_target], free_pairs[free_idx]
            shop_items_unordered.append(free_pairs[free_idx])
            taken.add(free_pairs[free_idx].item)
            free_idx += 1
        rng.shuffle(shop_items_unordered)
        result.extend(shop_items_unordered)

    # --- Post-process: resolve any remaining within-shop duplicates ---
    # The forward-swap above can miss duplicates when the only non-duplicate
    # candidates were already consumed by earlier shops.  Fix by swapping
    # duplicates with items in other shops where no new conflict is created.
    _resolve_shop_duplicates(result)

    # --- Write shuffled items back into shops ---
    # Prices are set later by randomize_shop_prices, which runs after
    # randomize_items so it sees the final shop contents (major-item shop
    # slots can be reassigned by assumed fill when shuffle_major_shop_items
    # is enabled).
    for shop_idx, shop in enumerate(shops):
        base = shop_idx * _ITEMS_PER_SHOP
        for slot in range(_ITEMS_PER_SHOP):
            shop.items[slot] = result[base + slot]


def randomize_shop_prices(game_world: GameWorld, config: GameConfig, rng: Rng) -> None:
    """Price shop items based on their final post-fill contents.

    Runs after randomize_items so that major shop slots reassigned by
    assumed fill are priced according to the item that actually lands there:
      - Progression items (required to beat the game): [80, 120]
      - Nice-to-have items (rings, rods, etc.):        [180, 240]
      - Everything else: vanilla price jittered by ±20, clamped to [1, 254]

    Also randomizes potion shop / secret cave / door repair prices.
    Gated on shuffle_shop_items.
    """
    if not config.shuffle_shop_items:
        return

    ow = game_world.overworld
    for dest in _SHOP_DESTINATIONS:
        shop = ow.get_cave(dest, Shop)
        if shop is None:
            continue
        for si in shop.items:
            si.price = _price_for(si.item, si.price, rng)

    _randomize_aux_prices(ow, rng)


def _price_for(item: Item, vanilla_price: int, rng: Rng) -> int:
    """Return a randomized price for a shop item based on its category."""
    if item in HINTABLE_PROGRESSION_ITEMS:
        return int(rng.random() * 41) + 80    # [80, 120]
    if item in HINTABLE_NICE_TO_HAVE_ITEMS:
        return int(rng.random() * 61) + 180   # [180, 240]
    delta = int(rng.random() * 41) - 20       # [-20, +20]
    adjusted = vanilla_price + delta
    if 1 <= adjusted <= 254:
        return adjusted
    return vanilla_price


def _swap_preserves_major_constraint(
    result: list[ShopItem],
    shop_a: int, slot_a: int,
    shop_b: int, slot_b: int,
) -> bool:
    """Return True if swapping two slots keeps ≥1 major item in each shop."""
    item_a = result[shop_a * _ITEMS_PER_SHOP + slot_a].item
    item_b = result[shop_b * _ITEMS_PER_SHOP + slot_b].item
    a_is_major = item_a in _MAJOR_ITEMS
    b_is_major = item_b in _MAJOR_ITEMS
    # If neither or both are major, major counts don't change.
    if a_is_major == b_is_major:
        return True
    # One is major and the other isn't — the shop losing a major item must
    # still have at least one other major item remaining after the swap.
    if a_is_major:
        losing_shop, losing_slot = shop_a, slot_a
    else:
        losing_shop, losing_slot = shop_b, slot_b
    base = losing_shop * _ITEMS_PER_SHOP
    major_count = sum(
        1 for s in range(_ITEMS_PER_SHOP)
        if s != losing_slot and result[base + s].item in _MAJOR_ITEMS
    )
    return major_count >= 1


def _resolve_shop_duplicates(result: list[ShopItem]) -> None:
    """Swap items between shops to eliminate within-shop duplicates.

    Iterates over each shop's slots and, when a duplicate is found, searches
    all slots in *other* shops for a swap partner that resolves the conflict
    without introducing a new duplicate in either shop.
    """
    def _shop_items_set(shop_idx: int) -> set[Item]:
        base = shop_idx * _ITEMS_PER_SHOP
        return {result[base + s].item for s in range(_ITEMS_PER_SHOP)}

    for shop_idx in range(_SHOP_COUNT):
        base = shop_idx * _ITEMS_PER_SHOP
        seen: set[Item] = set()
        for slot in range(_ITEMS_PER_SHOP):
            item = result[base + slot].item
            if item not in seen:
                seen.add(item)
                continue
            # Duplicate found — try to swap with a slot in another shop.
            for other_shop in range(_SHOP_COUNT):
                if other_shop == shop_idx:
                    continue
                other_base = other_shop * _ITEMS_PER_SHOP
                other_items = _shop_items_set(other_shop)
                for other_slot in range(_ITEMS_PER_SHOP):
                    candidate = result[other_base + other_slot].item
                    # The swap is safe if:
                    #  1. candidate is not already in the current shop
                    #  2. the duplicate item is not already elsewhere in the other shop
                    #  3. both shops retain at least one major item after the swap
                    if candidate in seen or item in (other_items - {candidate}):
                        continue
                    # Check that the swap preserves the major-item-per-shop invariant.
                    if not _swap_preserves_major_constraint(
                        result, shop_idx, slot, other_shop, other_slot,
                    ):
                        continue
                    # Perform the swap.
                    abs_slot = base + slot
                    abs_other = other_base + other_slot
                    result[abs_slot], result[abs_other] = result[abs_other], result[abs_slot]
                    seen.add(result[abs_slot].item)
                    break
                else:
                    continue
                break


def _randomize_aux_prices(ow: Overworld, rng: Rng) -> None:
    """Randomize potion shop, secret cave, and door repair prices."""
    # Potion shop (SHOP_E) — two items, slots 0 and 1
    potion = ow.get_cave(Destination.POTION_SHOP, Shop)
    if potion is not None:
        potion.items[0].price = int(rng.random() * 31) + 25   # [25, 55]
        potion.items[1].price = int(rng.random() * 41) + 48   # [48, 88]

    # Secret caves — rupee_value (positive = reward, negative = penalty)
    for dest in [Destination.MEDIUM_SECRET, Destination.LARGE_SECRET, Destination.SMALL_SECRET]:
        sc = ow.get_cave(dest, SecretCave)
        if sc is None:
            continue
        if dest == Destination.MEDIUM_SECRET:
            sc.rupee_value = int(rng.random() * 16) + 25   # [25, 40]
        elif dest == Destination.LARGE_SECRET:
            sc.rupee_value = int(rng.random() * 101) + 50  # [50, 150]
        else:
            sc.rupee_value = int(rng.random() * 20) + 1    # [1, 20]

    # Door repair
    dr = ow.get_cave(Destination.DOOR_REPAIR, DoorRepairCave)
    if dr is not None:
        dr.cost = int(rng.random() * 11) + 15  # [15, 25]
