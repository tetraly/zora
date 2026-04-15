"""
Tests for shop_shuffler.randomize_shops.

Covers:
  - No-op when flag is off
  - At least one major item per shop after shuffling
  - Major items each land in a different shop (one per shop)
  - All 12 original items are preserved (same multiset)
  - Prices are jittered within bounds [1, 254]
  - Different seeds produce different arrangements
  - Auxiliary prices (potion shop, secrets, door repair) are in range
  - Constraint holds when shuffle_major_shop_items moves major items around
"""

from pathlib import Path

from flags.flags_generated import Flags, Tristate
from zora.data_model import (
    Destination,
    DoorRepairCave,
    GameWorld,
    Item,
    SecretCave,
    Shop,
)
from zora.game_config import GameConfig, resolve_game_config
from zora.item_randomizer import assumed_fill
from zora.normalizer import normalize_data
from zora.parser import load_bin_files, parse_game_world
from zora.rng import SeededRng
from zora.shop_shuffler import _MAJOR_ITEMS, _SHOP_DESTINATIONS, randomize_shops

TEST_DATA = Path(__file__).parent.parent / "rom_data"

_ITEMS_PER_SHOP = 3


def _fresh_world():
    return parse_game_world(load_bin_files(TEST_DATA))


def _config(flags: Flags, seed: int = 0) -> GameConfig:
    return resolve_game_config(flags, SeededRng(seed))


def _shop_items(game_world: GameWorld) -> list[Item]:
    """Flat list of all 12 shop items across shops A-D."""
    ow = game_world.overworld
    items: list[Item] = []
    for dest in _SHOP_DESTINATIONS:
        shop = ow.get_cave(dest, Shop)
        assert shop is not None
        items.extend(si.item for si in shop.items)
    return items


def _shop_prices(game_world: GameWorld) -> list[int]:
    """Flat list of all 12 shop prices across shops A-D."""
    ow = game_world.overworld
    prices: list[int] = []
    for dest in _SHOP_DESTINATIONS:
        shop = ow.get_cave(dest, Shop)
        assert shop is not None
        prices.extend(si.price for si in shop.items)
    return prices


# ---------------------------------------------------------------------------
# Second BAIT replaced with FAIRY (normalize_data)
# ---------------------------------------------------------------------------

def test_second_bait_replaced_with_fairy():
    """When shuffle_major_shop_items is on, normalize_data replaces the second BAIT with a FAIRY."""
    flags = Flags(shuffle_major_shop_items=Tristate.ON)
    gw = _fresh_world()
    config = _config(flags)

    normalize_data(gw, config, SeededRng(0))

    items = _shop_items(gw)
    bait_count = items.count(Item.BAIT)
    fairy_count = items.count(Item.FAIRY)

    assert bait_count == 1, f"Expected 1 BAIT after normalize_data, got {bait_count}"
    assert fairy_count == 1, f"Expected 1 FAIRY after normalize_data, got {fairy_count}"


def test_bait_unchanged_when_flag_off():
    """When shuffle_major_shop_items is off, normalize_data must not touch BAIT."""
    gw_vanilla = _fresh_world()
    vanilla_bait = _shop_items(gw_vanilla).count(Item.BAIT)

    gw = _fresh_world()
    config = _config(Flags())
    normalize_data(gw, config, SeededRng(0))

    assert _shop_items(gw).count(Item.BAIT) == vanilla_bait


# ---------------------------------------------------------------------------
# No-op when flag is off
# ---------------------------------------------------------------------------

def test_no_op_when_flag_off():
    """randomize_shops must not mutate anything when shuffle_shop_items is off."""
    gw = _fresh_world()
    config = _config(Flags())

    before_items = _shop_items(gw)
    before_prices = _shop_prices(gw)

    randomize_shops(gw, config, SeededRng(0))

    assert _shop_items(gw) == before_items
    assert _shop_prices(gw) == before_prices


# ---------------------------------------------------------------------------
# Major items land in different shops (one per shop)
# ---------------------------------------------------------------------------

def test_major_items_in_different_shops():
    """When there are ≤4 major items, each must land in a different shop."""
    flags = Flags(shuffle_shop_items=Tristate.ON, shuffle_major_shop_items=Tristate.ON)
    gw = _fresh_world()
    config = _config(flags)

    normalize_data(gw, config, SeededRng(0))
    randomize_shops(gw, config, SeededRng(42))

    ow = gw.overworld
    shops_with_major: list[Destination] = []
    for dest in _SHOP_DESTINATIONS:
        shop = ow.get_cave(dest, Shop)
        assert shop is not None
        for si in shop.items:
            if si.item in _MAJOR_ITEMS:
                shops_with_major.append(dest)

    assert len(shops_with_major) == len(set(shops_with_major)), (
        f"Major item(s) landed in the same shop: {shops_with_major}"
    )


def test_major_items_in_different_shops_across_seeds():
    """When there are ≤4 major items, constraint holds across multiple seeds."""
    flags = Flags(shuffle_shop_items=Tristate.ON, shuffle_major_shop_items=Tristate.ON)
    for seed in range(10):
        gw = _fresh_world()
        config = _config(flags, seed=seed)
        normalize_data(gw, config, SeededRng(seed))
        randomize_shops(gw, config, SeededRng(seed))

        ow = gw.overworld
        shops_with_major: list[Destination] = []
        for dest in _SHOP_DESTINATIONS:
            shop = ow.get_cave(dest, Shop)
            assert shop is not None
            for si in shop.items:
                if si.item in _MAJOR_ITEMS:
                    shops_with_major.append(dest)

        assert len(shops_with_major) == len(set(shops_with_major)), (
            f"Seed {seed}: major items in same shop: {shops_with_major}"
        )


def test_at_least_one_major_item_per_shop():
    """Every shop must contain at least one major item after shuffling."""
    flags = Flags(shuffle_shop_items=Tristate.ON)
    for seed in range(10):
        gw = _fresh_world()
        config = _config(flags, seed=seed)
        randomize_shops(gw, config, SeededRng(seed))

        ow = gw.overworld
        for dest in _SHOP_DESTINATIONS:
            shop = ow.get_cave(dest, Shop)
            assert shop is not None
            major_in_shop = [si.item for si in shop.items if si.item in _MAJOR_ITEMS]
            assert len(major_in_shop) >= 1, (
                f"Seed {seed}: {dest.name} has no major item: "
                f"{[si.item.name for si in shop.items]}"
            )


# ---------------------------------------------------------------------------
# Item multiset preserved
# ---------------------------------------------------------------------------

def test_item_multiset_preserved_except_bait_to_fairy():
    """With shuffle_major_shop_items on, the only multiset change is second BAIT → FAIRY."""
    flags = Flags(shuffle_shop_items=Tristate.ON, shuffle_major_shop_items=Tristate.ON)
    gw = _fresh_world()
    config = _config(flags)

    before = sorted(i.value for i in _shop_items(gw))
    normalize_data(gw, config, SeededRng(0))
    randomize_shops(gw, config, SeededRng(7))
    after = sorted(i.value for i in _shop_items(gw))

    # Derive the expected multiset: replace one BAIT with a FAIRY
    expected = list(before)
    expected.remove(Item.BAIT.value)
    expected.append(Item.FAIRY.value)
    expected.sort()

    assert after == expected, (
        f"Item multiset wrong after shuffling.\n"
        f"Before:   {[Item(v).name for v in before]}\n"
        f"Expected: {[Item(v).name for v in expected]}\n"
        f"After:    {[Item(v).name for v in after]}"
    )


# ---------------------------------------------------------------------------
# Price jitter stays in bounds
# ---------------------------------------------------------------------------

def test_prices_in_bounds_after_jitter():
    """All shop prices must be in [1, 254] after shuffling."""
    flags = Flags(shuffle_shop_items=Tristate.ON)
    for seed in range(5):
        gw = _fresh_world()
        config = _config(flags, seed=seed)
        randomize_shops(gw, config, SeededRng(seed))

        for price in _shop_prices(gw):
            assert 1 <= price <= 254, f"Seed {seed}: price {price} out of bounds"


# ---------------------------------------------------------------------------
# Shuffling produces different results for different seeds
# ---------------------------------------------------------------------------

def test_different_seeds_produce_different_shops():
    """Two different seeds should (very likely) produce different shop arrangements."""
    flags = Flags(shuffle_shop_items=Tristate.ON)

    gw1 = _fresh_world()
    randomize_shops(gw1, _config(flags, seed=1), SeededRng(1))
    items1 = _shop_items(gw1)

    gw2 = _fresh_world()
    randomize_shops(gw2, _config(flags, seed=99), SeededRng(99))
    items2 = _shop_items(gw2)

    assert items1 != items2, "Different seeds produced identical shop arrangements"


# ---------------------------------------------------------------------------
# Auxiliary price ranges
# ---------------------------------------------------------------------------

def test_potion_shop_prices_in_range():
    """Potion shop prices must be in their expected ranges after shuffling."""
    flags = Flags(shuffle_shop_items=Tristate.ON)
    for seed in range(5):
        gw = _fresh_world()
        config = _config(flags, seed=seed)
        randomize_shops(gw, config, SeededRng(seed))

        potion = gw.overworld.get_cave(Destination.POTION_SHOP, Shop)
        assert potion is not None
        p0 = potion.items[0].price
        p1 = potion.items[1].price
        assert 25 <= p0 <= 55, f"Seed {seed}: potion item 0 price {p0} out of [25,55]"
        assert 48 <= p1 <= 88, f"Seed {seed}: potion item 1 price {p1} out of [48,88]"


def test_secret_cave_prices_in_range():
    """Secret cave rupee values must be in their expected ranges after shuffling."""
    flags = Flags(shuffle_shop_items=Tristate.ON)
    for seed in range(5):
        gw = _fresh_world()
        config = _config(flags, seed=seed)
        randomize_shops(gw, config, SeededRng(seed))

        ow = gw.overworld
        medium = ow.get_cave(Destination.MEDIUM_SECRET, SecretCave)
        large  = ow.get_cave(Destination.LARGE_SECRET,  SecretCave)
        small  = ow.get_cave(Destination.SMALL_SECRET,  SecretCave)

        assert medium is not None and 25 <= medium.rupee_value <= 40, (
            f"Seed {seed}: medium secret {medium.rupee_value} out of [25,40]"
        )
        assert large is not None and 50 <= large.rupee_value <= 150, (
            f"Seed {seed}: large secret {large.rupee_value} out of [50,150]"
        )
        assert small is not None and 1 <= small.rupee_value <= 20, (
            f"Seed {seed}: small secret {small.rupee_value} out of [1,20]"
        )


def test_door_repair_cost_in_range():
    """Door repair cost must be in [15, 25] after shuffling."""
    flags = Flags(shuffle_shop_items=Tristate.ON)
    for seed in range(5):
        gw = _fresh_world()
        config = _config(flags, seed=seed)
        randomize_shops(gw, config, SeededRng(seed))

        dr = gw.overworld.get_cave(Destination.DOOR_REPAIR, DoorRepairCave)
        assert dr is not None
        assert 15 <= dr.cost <= 25, f"Seed {seed}: door repair cost {dr.cost} out of [15,25]"


def test_aux_prices_unchanged_when_flag_off():
    """Potion shop, secret caves, and door repair must not change when flag is off."""
    gw = _fresh_world()
    config = _config(Flags())

    ow = gw.overworld
    potion = ow.get_cave(Destination.POTION_SHOP, Shop)
    medium = ow.get_cave(Destination.MEDIUM_SECRET, SecretCave)
    large  = ow.get_cave(Destination.LARGE_SECRET,  SecretCave)
    small  = ow.get_cave(Destination.SMALL_SECRET,  SecretCave)
    dr     = ow.get_cave(Destination.DOOR_REPAIR,   DoorRepairCave)

    assert potion and medium and large and small and dr

    before = (
        potion.items[0].price, potion.items[1].price,
        medium.rupee_value, large.rupee_value, small.rupee_value,
        dr.cost,
    )

    randomize_shops(gw, config, SeededRng(0))

    after = (
        potion.items[0].price, potion.items[1].price,
        medium.rupee_value, large.rupee_value, small.rupee_value,
        dr.cost,
    )

    assert before == after, "Aux prices changed even though shuffle_shop_items is off"


# ---------------------------------------------------------------------------
# Interaction with shuffle_major_shop_items — major items may vary
# ---------------------------------------------------------------------------

def test_major_item_constraint_holds_after_assumed_fill():
    """Constraint holds when assumed fill has placed a different set of major items in shops."""
    flags = Flags(
        shuffle_shop_items=Tristate.ON,
        shuffle_major_shop_items=Tristate.ON,
        shuffle_dungeon_items=Tristate.ON,
    )
    for seed in range(5):
        gw = _fresh_world()
        config = _config(flags, seed=seed)
        normalize_data(gw, config, SeededRng(seed))
        assumed_fill(gw, config, SeededRng(seed))
        randomize_shops(gw, config, SeededRng(seed + 1000))

        ow = gw.overworld
        shops_with_major: list[Destination] = []
        for dest in _SHOP_DESTINATIONS:
            shop = ow.get_cave(dest, Shop)
            assert shop is not None
            for si in shop.items:
                if si.item in _MAJOR_ITEMS:
                    shops_with_major.append(dest)

        major_placements = [
            (si.item.name, dest.name)
            for dest in _SHOP_DESTINATIONS
            for si in ow.get_cave(dest, Shop).items
            if si.item in _MAJOR_ITEMS
        ]
        assert len(shops_with_major) == len(set(shops_with_major)), (
            f"Seed {seed}: major items share a shop: {major_placements}"
        )


# ---------------------------------------------------------------------------
# No shop contains duplicate items
# ---------------------------------------------------------------------------

def test_no_duplicate_items_in_any_shop():
    """No single shop should contain two copies of the same item after shuffling."""
    flags = Flags(shuffle_shop_items=Tristate.ON)
    for seed in range(50):
        gw = _fresh_world()
        config = _config(flags, seed=seed)
        randomize_shops(gw, config, SeededRng(seed))

        ow = gw.overworld
        for dest in _SHOP_DESTINATIONS:
            shop = ow.get_cave(dest, Shop)
            assert shop is not None
            items = [si.item for si in shop.items]
            assert len(items) == len(set(items)), (
                f"Seed {seed}: {dest.name} has duplicate items: "
                f"{[i.name for i in items]}"
            )


def test_no_duplicate_items_with_major_shop_items_flag():
    """Duplicate check holds when shuffle_major_shop_items moves items around."""
    flags = Flags(shuffle_shop_items=Tristate.ON, shuffle_major_shop_items=Tristate.ON)
    for seed in range(50):
        gw = _fresh_world()
        config = _config(flags, seed=seed)
        normalize_data(gw, config, SeededRng(seed))
        randomize_shops(gw, config, SeededRng(seed))

        ow = gw.overworld
        for dest in _SHOP_DESTINATIONS:
            shop = ow.get_cave(dest, Shop)
            assert shop is not None
            items = [si.item for si in shop.items]
            assert len(items) == len(set(items)), (
                f"Seed {seed}: {dest.name} has duplicate items: "
                f"{[i.name for i in items]}"
            )
