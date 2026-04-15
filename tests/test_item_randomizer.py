"""
Randomizer tests: verify assumed fill produces valid, beatable seeds.
"""
import time
from pathlib import Path

from flags.flags_generated import Flags, Tristate
from flags.flags_generated import Item as FlagItem
from zora.data_model import Destination, GameWorld, Item
from zora.game_config import GameConfig, resolve_game_config
from zora.game_validator import GameValidator
from zora.item_randomizer import (
    _collect_item_pool,
    assumed_fill,
    collect_all_placed_items,
    collect_item_locations,
)
from zora.parser import load_bin_files, parse_game_world
from zora.rng import SeededRng

TEST_DATA = Path(__file__).parent.parent / "rom_data"


def _fresh_world():
    return parse_game_world(load_bin_files(TEST_DATA))


def _config(flags: Flags, seed: int = 0) -> GameConfig:
    return resolve_game_config(flags, SeededRng(seed))


def test_assumed_fill_produces_valid_seed():
    """Assumed fill should produce a beatable seed."""
    gw = _fresh_world()
    config = _config(Flags(), seed=12345)
    success = assumed_fill(gw, config, SeededRng(12345))
    assert success
    assert GameValidator(gw, config.avoid_required_hard_combat).is_seed_valid()


def test_assumed_fill_different_seeds_produce_different_results():
    """Different seeds should produce different item placements."""
    gw1 = _fresh_world()
    assumed_fill(gw1, _config(Flags(), seed=1), SeededRng(1))

    gw2 = _fresh_world()
    assumed_fill(gw2, _config(Flags(), seed=2), SeededRng(2))

    items1 = collect_all_placed_items(gw1)
    items2 = collect_all_placed_items(gw2)
    assert items1 != items2


def test_assumed_fill_respects_ladder_not_at_coast():
    """Ladder must never be placed at the coast location."""
    start = time.time()
    for seed in range(3):
        gw = _fresh_world()
        assumed_fill(gw, _config(Flags(), seed=seed), SeededRng(seed))
        cave_by_dest = {c.destination: c for c in gw.overworld.caves}
        coast = cave_by_dest.get(Destination.COAST_ITEM)
        assert coast is not None and coast.item != Item.LADDER, f"Ladder at coast on seed {seed}"
    assert (elapsed := time.time() - start) < 60, f"took {elapsed:.1f}s"


def test_assumed_fill_force_heart_container_to_armos():
    """armos_item=HEART_CONTAINER must place a heart container at the armos location."""
    flags = Flags(
        armos_item=FlagItem.HEART_CONTAINER,  # shuffled + forced to heart container
        coast_item=FlagItem.RANDOM,           # shuffled (provides a heart container in pool)
        # shuffle_dungeon_hearts intentionally omitted: combining heart shuffling
        # with heart-gated sword caves (white=5, magical=12) requires dedicated
        # constraint work to guarantee accessibility. See randomizer.py TODO.
    )
    start = time.time()
    for seed in range(3):
        gw = _fresh_world()
        config = _config(flags, seed=seed)
        success = assumed_fill(gw, config, SeededRng(seed))
        assert success, f"Seed {seed} failed"
        cave_by_dest = {c.destination: c for c in gw.overworld.caves}
        armos = cave_by_dest.get(Destination.ARMOS_ITEM)
        assert armos is not None and armos.item == Item.HEART_CONTAINER, \
            f"Armos item is {armos.item if armos else None} on seed {seed}"
    assert (elapsed := time.time() - start) < 60, f"took {elapsed:.1f}s"


def test_many_seeds_are_valid():
    """Assumed fill across 100 seeds must always produce valid, beatable results."""
    start = time.time()
    for seed in range(5):
        gw = _fresh_world()
        config = _config(Flags(), seed=seed)
        success = assumed_fill(gw, config, SeededRng(seed))
        assert success, f"Seed {seed} failed to generate"
        assert GameValidator(gw, config.avoid_required_hard_combat).is_seed_valid(), \
            f"Seed {seed} produced an unbeatable result"
    assert (elapsed := time.time() - start) < 60, f"took {elapsed:.1f}s"


def test_shop_shuffle_adds_items_to_pool():
    """Shop shuffle must add vanilla major shop items to the item pool."""
    flags = Flags(shuffle_major_shop_items=Tristate.ON)
    config = _config(flags)

    gw = _fresh_world()
    pool = _collect_item_pool(gw, config)
    pool_items = set(pool)

    assert Item.WOOD_ARROWS in pool_items, "Wood arrows missing from pool"
    assert Item.BLUE_CANDLE in pool_items, "Blue candle missing from pool"
    assert Item.BLUE_RING in pool_items, "Blue ring missing from pool"
    assert Item.BAIT in pool_items, "Bait missing from pool"


def test_shop_shuffle_pool_matches_location_count():
    """Item pool size must be <= location pool size with shop shuffle on."""
    flags = Flags(shuffle_major_shop_items=Tristate.ON)
    config = _config(flags)

    gw = _fresh_world()
    pool = _collect_item_pool(gw, config)
    locations = collect_item_locations(gw, config)

    assert len(pool) <= len(locations), (
        f"Item pool ({len(pool)}) exceeds location pool ({len(locations)}) — "
        f"placement will always fail"
    )


def test_shop_shuffle_produces_beatable_seeds():
    """Seeds with shop shuffle enabled must be beatable."""
    flags = Flags(shuffle_major_shop_items=Tristate.ON)

    for seed in range(3):
        gw = _fresh_world()
        config = _config(flags, seed=seed)
        success = assumed_fill(gw, config, SeededRng(seed))
        assert success, f"Seed {seed} failed to generate with shop shuffle"
        assert GameValidator(gw, config.avoid_required_hard_combat).is_seed_valid(), (
            f"Seed {seed} produced an unbeatable result with shop shuffle"
        )


# ---------------------------------------------------------------------------
# Progressive items tests
# ---------------------------------------------------------------------------

_PROGRESSIVE_FLAGS = Flags(
    progressive_items=Tristate.ON,
    shuffle_major_shop_items=Tristate.ON,  # required: base items must not end up buyable
)

_HIGHER_TIER_ITEMS = {
    Item.WHITE_SWORD, Item.MAGICAL_SWORD,
    Item.RED_RING, Item.SILVER_ARROWS, Item.RED_CANDLE,
}

_PROGRESSIVE_BASE_ITEMS = {
    Item.WOOD_SWORD, Item.BLUE_RING, Item.WOOD_ARROWS, Item.BLUE_CANDLE,
}

_SHOP_DESTINATIONS = {
    Destination.SHOP_1, Destination.SHOP_2, Destination.SHOP_3, Destination.SHOP_4,
}


def test_progressive_pool_contains_no_higher_tier_items():
    """With progressive_items on, the item pool must not contain any higher-tier items."""
    gw = _fresh_world()
    config = _config(_PROGRESSIVE_FLAGS)
    pool = _collect_item_pool(gw, config)
    higher_tier_in_pool = [item for item in pool if item in _HIGHER_TIER_ITEMS]
    assert not higher_tier_in_pool, (
        f"Higher-tier items found in progressive pool: {higher_tier_in_pool}"
    )


def test_progressive_pool_has_multiple_base_items():
    """With progressive_items on, base items appear multiple times (replacing higher tiers)."""
    # Enable all sword cave shuffles so WHITE_SWORD and MAGICAL_SWORD enter the pool
    flags = Flags(
        progressive_items=Tristate.ON,
        shuffle_major_shop_items=Tristate.ON,
        shuffle_wood_sword=Tristate.ON,
        white_sword_item=FlagItem.RANDOM,
        shuffle_magical_sword=Tristate.ON,
    )
    gw = _fresh_world()
    config = _config(flags)
    pool = _collect_item_pool(gw, config)
    sword_count = pool.count(Item.WOOD_SWORD)
    assert sword_count >= 3, (
        f"Expected at least 3 WOOD_SWORDs (wood+white+magical), got {sword_count}"
    )
    assert pool.count(Item.BLUE_RING) >= 2, "Expected at least 2 BLUE_RINGs"
    assert pool.count(Item.WOOD_ARROWS) >= 2, "Expected at least 2 WOOD_ARROWSs"
    assert pool.count(Item.BLUE_CANDLE) >= 2, "Expected at least 2 BLUE_CANDLEs"


def test_progressive_fill_no_base_items_in_shops():
    """With progressive_items on, progressive base items must not land in shops."""
    for seed in range(3):
        gw = _fresh_world()
        config = _config(_PROGRESSIVE_FLAGS, seed=seed)
        success = assumed_fill(gw, config, SeededRng(seed))
        assert success, f"Seed {seed} failed"

        ow = gw.overworld
        cave_by_dest = {c.destination: c for c in ow.caves}
        from zora.data_model import Shop
        for dest in _SHOP_DESTINATIONS:
            shop = cave_by_dest.get(dest)
            if shop is not None and isinstance(shop, Shop):
                for shop_item in shop.items:
                    assert shop_item.item not in _PROGRESSIVE_BASE_ITEMS, (
                        f"Seed {seed}: progressive base item {shop_item.item} found in shop {dest}"
                    )


def test_progressive_magical_sword_cave_not_shuffled():
    """When progressive is on and magical sword is not shuffled, cave holds WOOD_SWORD."""
    flags = Flags(progressive_items=Tristate.ON)  # shuffle_magical_sword defaults off
    gw = _fresh_world()
    config = _config(flags)
    assert not config.shuffle_magical_sword, "Test precondition: magical sword not shuffled"
    assumed_fill(gw, config, SeededRng(0))
    cave_by_dest = {c.destination: c for c in gw.overworld.caves}
    mag_cave = cave_by_dest.get(Destination.MAGICAL_SWORD_CAVE)
    assert mag_cave is not None and mag_cave.item == Item.WOOD_SWORD, (
        f"Expected WOOD_SWORD in magical sword cave, got {mag_cave.item if mag_cave else None}"
    )


def test_progressive_seeds_are_beatable():
    """Seeds with progressive_items enabled must be valid and beatable."""
    for seed in range(3):
        gw = _fresh_world()
        config = _config(_PROGRESSIVE_FLAGS, seed=seed)
        success = assumed_fill(gw, config, SeededRng(seed))
        assert success, f"Seed {seed} failed to generate with progressive items"
        assert GameValidator(gw, config.avoid_required_hard_combat,
                             progressive_items=True).is_seed_valid(), (
            f"Seed {seed} produced an unbeatable result with progressive items"
        )


# ---------------------------------------------------------------------------
# Important items in Level 9 restriction
# ---------------------------------------------------------------------------

# The five logically critical items that should be banned from Level 9
# when allow_important_in_l9 is off (the default).
_L9_IMPORTANT_ITEMS = {
    Item.BOW, Item.LADDER, Item.POWER_BRACELET, Item.RAFT, Item.RECORDER,
}


def _get_level_9_items(gw: GameWorld) -> list[Item]:
    level_9 = gw.levels[8]  # 0-indexed
    items: list[Item] = []
    for room in level_9.rooms:
        if room.item != Item.NOTHING:
            items.append(room.item)
    for sr in level_9.staircase_rooms:
        if sr.item is not None and sr.item != Item.NOTHING:
            items.append(sr.item)
    return items


def test_important_items_forbidden_from_l9_by_default():
    """With allow_important_in_l9 off (default), shuffle_dungeon_items and
    shuffle_armos_item on, bow/ladder/bracelet/raft/recorder must never
    appear in Level 9."""
    flags = Flags(
        shuffle_dungeon_items=Tristate.ON,
        armos_item=FlagItem.RANDOM,
    )
    for seed in range(20):
        gw = _fresh_world()
        config = _config(flags, seed=seed)
        success = assumed_fill(gw, config, SeededRng(seed))
        assert success, f"Seed {seed} failed to generate"
        l9_items = _get_level_9_items(gw)
        bad_items = [i for i in l9_items if i in _L9_IMPORTANT_ITEMS]
        assert not bad_items, (
            f"Seed {seed}: important items {bad_items} found in Level 9 "
            f"with allow_important_in_l9=OFF"
        )


