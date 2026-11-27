"""Shop prices (SI-PRICE-01, revision 2026-11-27: a budget per group; the beta 9 rules, 2026-10-24, before it;
zora/generate/steps/shop_prices.py, docs/deviations.md "Shop prices") and the bought fairy's full refill
(zora/rom/fairy_refill.py).

- The wares an extra moved an item into, and every ware holding an optional item, are priced by group
  (price_groups), in BUILD's world and FINISH's:
  - required items (read from the seed's resolved settings): with 3 or more in shops one total of 180-220, each
    20-100; with 1 or 2 each 60-80;
  - optional items: exactly one, the highest-ranked in shops (Magical Sword > Red Ring > White Sword > Blue Ring >
    Pegasus Boots > the rest), costs over 200, 200-240; every other 40-150; the group at most 450. The Blue Ring in
    its own ware is one of them (no PRG0 250).
- No item that can be required ever costs more than 100 in a shop: the group's cap, and the shops' own stock undoes
  a jitter that would lift the arrows, the candle or the bait above 100.
- Cheap: Triforce pieces, maps and compasses, the boomerangs without Pegasus Boots, heart containers and the
  letter 20-40, a fairy 20-40.
- Unchanged: a ware holding its own item, the Blue Ring aside.
- A bought fairy refills every heart, in a ZORA ROM and an Archipelago ROM; a dropped fairy's item entry stays
  PRG0's (three hearts); no ZORA patch, player setting or z1rr-coop range touches the patch's bytes."""
from dataclasses import replace
from functools import cache

import pytest

from tests.needs import needs_base_rom, needs_encoder
from tests.test_coop_reserved import hits, written
from zora.flags import codec, zora_flags
from zora.flags.fields import ENCODE_LEVEL_DATA, ThreeState
from zora.flags.form import metadata
from zora.flags.presets import ASNB_FLAGS, ASNB_ZORA_FLAGS, MVP_BASELINE
from zora.generate.pipeline import Built, build, extra_options, finish, plan
from zora.generate.rng import Rng, ScriptedRng
from zora.generate.steps.shop_prices import (
    ALWAYS_REQUIRED,
    BOOMERANG_DRAW,
    BOOMERANG_PRICES,
    BOOMERANGS,
    CHEAP_ITEMS,
    FAIRY_PRICES,
    HEADLINE_PRICES,
    HEART_CONTAINER_PRICES,
    LEVEL_ITEM_PRICES,
    OPTIONAL_PRICES,
    OPTIONAL_TOTAL_CAP,
    OTHER_OPTIONAL_PRICES,
    REQUIRED_GROUP_MIN,
    REQUIRED_PRICE_CAP,
    REQUIRED_PRICES,
    REQUIRED_SHARE,
    REQUIRED_TOTAL,
    SHOP_LEVEL_ITEMS,
    SWORDS,
    PriceRules,
    grouped_wares,
    headline_rank,
    price_groups,
    split_total,
)
from zora.generate.steps.shuffle_shop_items import jitter_prices
from zora.model.enums import Item
from zora.model.game_world import GameWorld
from zora.model.overworld import Shop, ShopItem
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.code_patch_data import PATCHES as SERIES_PATCHES
from zora.rom.fairy_refill import fairy_refill_writes
from zora.rom.flags2_patch_data import PATCHES as FLAG_PATCHES
from zora.rom.inventory import ITEM_ID_TO_DESCRIPTOR
from zora.rom.player_settings import written_offsets

DEFAULT = codec.decode(metadata()["defaultFlags"])
POOL = zora_flags.ZoraFlags(shop_items_in_pool=True)
ASNB = zora_flags.decode(ASNB_ZORA_FLAGS)
ON = ThreeState.ON


def z1r(**options: int) -> str:
    return codec.encode(DEFAULT.updated(options={k: v for k, v in options.items() if k.startswith("C")},
                                        toggles={k: v for k, v in options.items() if k.startswith("B")}))


# Setting sets that reach every price path (the review's sample, beta 9)
CASES: dict[str, tuple[str, zora_flags.ZoraFlags]] = {
    "page defaults": (z1r(), zora_flags.ZoraFlags()),
    "MVP baseline": (MVP_BASELINE, zora_flags.ZoraFlags()),
    "pool": (z1r(), POOL),
    "shops not shuffled": (z1r(B08=0), zora_flags.ZoraFlags()),
    "shops not shuffled, pool": (z1r(B08=0), POOL),
    "pool, progressive": (z1r(B09=0), replace(POOL, progressive_items=True)),
    "pool, blue potion": (z1r(), replace(POOL, shuffle_blue_potion=ON)),
    "pool, boots": (z1r(), replace(POOL, pegasus_boots=ON)),
    "pool, swordless": (z1r(C07=3), POOL),
    "pool, book to understand NPCs, mazes": (z1r(B48=1), replace(POOL, randomize_lost_hills=ON,
                                                                 randomize_dead_woods=ON)),
    "pool, wood sword": (z1r(), replace(POOL, shuffle_wood_sword=ON)),
    "ASNB, pool, blue potion": (ASNB_FLAGS, replace(ASNB, shop_items_in_pool=True, shuffle_blue_potion=ON)),
    "every price path": (z1r(B09=0), replace(POOL, progressive_items=True, shuffle_blue_potion=ON,
                                             randomize_letter=True, randomize_magical_sword=True,
                                             magical_sword_hearts_highest=12, pegasus_boots=ON,
                                             shuffle_wood_sword=ON)),
}
# Each case with Encode level data on (the MVP baseline) is planned only with the private encoder; a
# release tree skips it, as every encoder-dependent test does (tests/needs.py)
CASE_PARAMS = [pytest.param(case, marks=needs_encoder) if codec.decode(flags).is_on(ENCODE_LEVEL_DATA) else case
               for case, (flags, _extras) in CASES.items()]
# The joins that put a sword in a shop ware without pricing it before the fix, and how far to look
# for seeds where one lands there (about 1 seed in 8 in the review's sample)
SWORD_JOIN_CASES = ("pool, wood sword", "ASNB, pool, blue potion")
SWORD_SEARCH_SEEDS = range(1, 81)
SWORD_WARES_WANTED = 2


# --- the classes ---------------------------------------------------------------------------------

def test_every_required_class_is_at_most_100() -> None:
    for rules in (PriceRules(swordless=s, wood_sword_in_pool=w, swords_open_level_9=a, book_needed=b, pegasus_boots=p)
                  for s in (False, True) for w in (False, True) for a in (False, True) for b in (False, True)
                  for p in (False, True)):
        for item in rules.required_items:
            assert rules.prices[item][1] <= REQUIRED_PRICE_CAP, (rules, item)
        assert ALWAYS_REQUIRED <= rules.required_items


def test_the_classes_follow_the_settings() -> None:
    base = PriceRules()
    assert Item.WAND not in base.required_items and Item.BOOK not in base.required_items
    assert not SWORDS & base.required_items
    assert PriceRules(swordless=True).prices[Item.WAND] == REQUIRED_PRICES
    assert PriceRules(book_needed=True).prices[Item.BOOK] == REQUIRED_PRICES
    wood = PriceRules(wood_sword_in_pool=True)
    assert all(wood.prices[item] == REQUIRED_PRICES for item in (*SWORDS, Item.WAND))
    asnb = PriceRules(wood_sword_in_pool=True, swords_open_level_9=True)
    assert all(asnb.prices[item] == OPTIONAL_PRICES for item in SWORDS) and asnb.prices[Item.WAND] == REQUIRED_PRICES
    assert all(base.prices[item] == BOOMERANG_DRAW == (75, 125) for item in BOOMERANGS)   # the step's draw
    assert all(PriceRules(pegasus_boots=True).prices[item] == OPTIONAL_PRICES for item in BOOMERANGS)
    assert all(base.prices[item] == HEART_CONTAINER_PRICES == (20, 40) for item in CHEAP_ITEMS)
    assert LEVEL_ITEM_PRICES == (20, 40) and len(SHOP_LEVEL_ITEMS) == 26
    assert base.prices[Item.FAIRY] == FAIRY_PRICES == (20, 40)
    assert BOOMERANG_PRICES == (20, 40) and OPTIONAL_PRICES == (200, 240) and REQUIRED_PRICES == (60, 80)


@needs_base_rom
def test_the_rules_are_read_from_the_resolved_settings() -> None:
    def rules(case: str) -> PriceRules:
        flags, extras = CASES[case]
        return extra_options(plan(flags, 1, zora_flags.encode(extras))).price_rules
    assert rules("pool") == PriceRules(shops_shuffled=True)
    assert rules("shops not shuffled") == PriceRules()
    assert rules("pool, swordless").swordless
    assert rules("pool, book to understand NPCs, mazes").book_needed
    assert rules("pool, wood sword").wood_sword_in_pool and rules("pool, boots").pegasus_boots
    assert rules("ASNB, pool, blue potion").swords_open_level_9


# --- the groups (revision 2026-11-27) -------------------------------------------------------------

def test_the_groups_figures() -> None:
    assert (REQUIRED_TOTAL, REQUIRED_SHARE, REQUIRED_GROUP_MIN) == ((180, 220), (20, 100), 3)
    assert (HEADLINE_PRICES, OTHER_OPTIONAL_PRICES, OPTIONAL_TOTAL_CAP) == ((200, 240), (40, 150), 450)
    base, boots = PriceRules(), PriceRules(pegasus_boots=True)
    assert not BOOMERANGS & base.optional_items and BOOMERANGS <= boots.optional_items
    assert Item.BLUE_RING in base.optional_items
    assert Item.WAND not in PriceRules(swordless=True).optional_items
    ranked = [Item.MAGICAL_SWORD, Item.RED_RING, Item.WHITE_SWORD, Item.BLUE_RING, Item.MAGICAL_BOOMERANG,
              Item.WOOD_BOOMERANG]     # the boomerangs rank only as the boots: without them they are in no group
    assert [headline_rank(item) for item in ranked] == list(range(6))
    assert headline_rank(Item.WAND) == headline_rank(Item.BOOK) == 6


@pytest.mark.parametrize("count", range(3, 12))
def test_a_split_keeps_its_total_and_its_caps(count: int) -> None:
    rng = Rng(count)
    for total in range(max(REQUIRED_TOTAL[0], 20 * count), REQUIRED_TOTAL[1] + 1):
        parts = split_total(total, count, rng)
        assert sum(parts) == total and all(20 <= part <= 100 for part in parts), (total, parts)


def check_groups(wares: list[ShopItem], rules: PriceRules) -> None:
    """The group rules over one seed's grouped wares."""
    required = [ware.price for ware in wares if ware.item in rules.required_items]
    if len(required) >= REQUIRED_GROUP_MIN:
        assert REQUIRED_TOTAL[0] <= sum(required) <= REQUIRED_TOTAL[1], required
        assert all(REQUIRED_SHARE[0] <= price <= REQUIRED_SHARE[1] for price in required), required
    else:
        assert all(REQUIRED_PRICES[0] <= price <= REQUIRED_PRICES[1] for price in required), required
    optional = [ware for ware in wares if ware.item in rules.optional_items]
    if not optional:
        return
    # "over 200" read as 200 or more: the headline's range starts at 200, every other optional price ends at 150
    over = [ware for ware in optional if ware.price >= HEADLINE_PRICES[0]]
    best = min(headline_rank(ware.item) for ware in optional)
    assert len(over) == 1 and headline_rank(over[0].item) == best, optional
    assert HEADLINE_PRICES[0] <= over[0].price <= HEADLINE_PRICES[1], optional
    assert all(OTHER_OPTIONAL_PRICES[0] <= ware.price <= OTHER_OPTIONAL_PRICES[1]
               for ware in optional if ware is not over[0]), optional
    assert sum(ware.price for ware in optional) <= OPTIONAL_TOTAL_CAP, optional


@pytest.mark.parametrize("seed", range(40))
def test_price_groups_on_drawn_stock(seed: int) -> None:
    """Up to seven wares of any mix (the most the groups can price: three joined wares, two baits, the potion shop's
    middle and the Blue Ring's own ware), every setting the groups read; a heart container is left as it is, a
    boomerang without the boots and a level item cost 20-40."""
    rng = Rng(1000 + seed)
    rules = PriceRules(swordless=bool(seed & 1), pegasus_boots=bool(seed & 2), book_needed=bool(seed & 4))
    candidates = sorted(rules.required_items | rules.optional_items | BOOMERANGS | {Item.HEART_CONTAINER}
                        | set(sorted(SHOP_LEVEL_ITEMS, key=int)[seed % 26::13]), key=int)
    wares = [ShopItem(candidates[rng.below(len(candidates))], 7) for _ in range(1 + rng.below(7))]
    price_groups(wares, rules, Rng(seed))
    check_groups(wares, rules)
    assert all(ware.price == 7 for ware in wares if ware.item == Item.HEART_CONTAINER)
    if not rules.pegasus_boots:
        assert all(BOOMERANG_PRICES[0] <= ware.price <= BOOMERANG_PRICES[1]
                   for ware in wares if ware.item in BOOMERANGS)
    assert all(LEVEL_ITEM_PRICES[0] <= ware.price <= LEVEL_ITEM_PRICES[1]
               for ware in wares if ware.item in SHOP_LEVEL_ITEMS)


def test_too_many_optional_items_cost_40_each() -> None:
    wares = [ShopItem(Item.MAGICAL_SWORD, 0)] + [ShopItem(Item.WAND, 0) for _ in range(6)]
    price_groups(wares, PriceRules(), Rng(1))
    assert HEADLINE_PRICES[0] <= wares[0].price and all(ware.price == 40 for ware in wares[1:])


# --- the shops' own stock: OW-SHOP-03's jitter under the cap ---------------------------------------

def test_a_jitter_lifting_a_required_ware_above_100_is_undone() -> None:
    """d = +20 on each: the 100-rupee bait stays at 100, the arrows reach 100, the 60-rupee bait 80,
    and the shield, which is optional, 150."""
    pairs = [ShopItem(Item.BAIT, 100), ShopItem(Item.WOOD_ARROWS, 80), ShopItem(Item.BAIT, 60),
             ShopItem(Item.MAGICAL_SHIELD, 130), ShopItem(Item.BAIT, 95)]
    jitter_prices(pairs, ScriptedRng([40] * len(pairs)))
    assert [pair.price for pair in pairs] == [100, 100, 80, 150, 95]
    pairs = [ShopItem(Item.BAIT, 100)]
    jitter_prices(pairs, ScriptedRng([0]))                      # d = -20 still applies
    assert pairs[0].price == 80


# --- finished seeds ------------------------------------------------------------------------------

@cache
def _built(case: str, seed: int) -> Built:
    flags, extras = CASES[case]
    return build(plan(flags, seed, zora_flags.encode(extras)), remember_repo_base_rom())


def check_prices(built: Built, world: GameWorld | None = None) -> None:
    """Every shop ware of a built seed (or of the world FINISH made from it) against the rules its settings
    resolve to: the groups over the joined wares and every optional item's ware, the required cap, the fairy and
    the boomerangs without the boots everywhere."""
    world = world or built.world
    rules = extra_options(built.plan).price_rules
    for shop in world.overworld.caves:
        if not isinstance(shop, Shop):
            continue
        for position, ware in enumerate(shop.items):
            where = (shop.destination.name, position, ware.item.name, ware.price)
            if ware.item in rules.required_items:
                assert ware.price <= REQUIRED_PRICE_CAP, where
            if ware.item == Item.FAIRY:
                assert FAIRY_PRICES[0] <= ware.price <= FAIRY_PRICES[1], where
            if ware.item in BOOMERANGS and not rules.pegasus_boots:
                assert BOOMERANG_PRICES[0] <= ware.price <= BOOMERANG_PRICES[1], where
            if ware.item in SHOP_LEVEL_ITEMS:
                assert LEVEL_ITEM_PRICES[0] <= ware.price <= LEVEL_ITEM_PRICES[1], where
    grouped = grouped_wares(world, built.result.extra_pool_items, rules)
    check_groups(grouped, rules)
    if not grouped and not rules.shops_shuffled:          # the shops as PRG0 stocks them: PRG0's prices
        rings = [ware for shop in world.overworld.caves if isinstance(shop, Shop) for ware in shop.items
                 if ware.item == Item.BLUE_RING]
        assert all(ware.price == PRG0_BLUE_RING_PRICE for ware in rings), rings


SEEDS = (1, 2, 3)
PRG0_BLUE_RING_PRICE = 250
SWEEP_SEEDS = range(1, 31)


@needs_base_rom
@pytest.mark.parametrize("case", CASE_PARAMS)
@pytest.mark.parametrize("seed", SEEDS)
def test_no_required_item_costs_more_than_100_and_the_groups_hold(case: str, seed: int) -> None:
    check_prices(_built(case, seed))


@needs_base_rom
@pytest.mark.parametrize("seed", SEEDS)
def test_the_blue_ring_at_home_is_the_headline(seed: int) -> None:
    """Owner ruling, 2026-11-27: with Shuffle Shop Items on and nothing moved into the shops (the page's defaults)
    the Blue Ring in its own ware is the only optional item sold, so it is the headline, 200-240."""
    built = _built("page defaults", seed)
    rings = [ware for shop in built.world.overworld.caves if isinstance(shop, Shop)
             for ware in shop.items if ware.item == Item.BLUE_RING]
    assert len(rings) == 1 and HEADLINE_PRICES[0] <= rings[0].price <= HEADLINE_PRICES[1], rings


@needs_base_rom
@pytest.mark.parametrize("seed", SEEDS)
def test_unshuffled_shops_keep_prg0s_prices(seed: int) -> None:
    """Owner decision, 2026-11-27: prices are randomized only when the shops are. With Shuffle Shop Items off and no
    item moved into a shop, the groups price nothing: the Blue Ring costs PRG0's 250."""
    built = _built("shops not shuffled", seed)
    rules = extra_options(built.plan).price_rules
    assert not rules.shops_shuffled and not grouped_wares(built.world, built.result.extra_pool_items, rules)
    rings = [ware for shop in built.world.overworld.caves if isinstance(shop, Shop)
             for ware in shop.items if ware.item == Item.BLUE_RING]
    assert [ware.price for ware in rings] == [PRG0_BLUE_RING_PRICE]


@needs_base_rom
@pytest.mark.parametrize("case", SWORD_JOIN_CASES)
def test_a_sword_joined_into_a_shop_ware_is_priced_by_its_group(case: str) -> None:
    """Add L4 Sword = Level 2's and Shuffle Wood Sword's joins: the first seeds where a sword ends in
    a shop ware, each priced by its group (it kept a heart container's 20-40 before the beta 9 fix)."""
    found = 0
    for seed in SWORD_SEARCH_SEEDS:
        built = _built(case, seed)
        rules = extra_options(built.plan).price_rules
        for shop in built.world.overworld.caves:
            if isinstance(shop, Shop):
                for ware in shop.items:
                    if ware.item in SWORDS:
                        low, high = (REQUIRED_PRICES if ware.item in rules.required_items
                                     else (OTHER_OPTIONAL_PRICES[0], HEADLINE_PRICES[1]))
                        assert low <= ware.price <= high, (case, seed, ware)
                        found += 1
        check_prices(built)
        if found >= SWORD_WARES_WANTED:
            return
    raise AssertionError(f"{case}: only {found} swords in shops over seeds {SWORD_SEARCH_SEEDS}")


@pytest.mark.slow
@needs_base_rom
@pytest.mark.parametrize("case", CASE_PARAMS)
def test_the_rules_hold_over_30_seeds(case: str) -> None:
    """Every case (Swordless, Pegasus Boots and the Book needed among them) over 30 seeds: 330 seeds in all."""
    for seed in SWEEP_SEEDS:
        flags, extras = CASES[case]
        check_prices(build(plan(flags, seed, zora_flags.encode(extras)), remember_repo_base_rom()))


@pytest.mark.slow
@needs_base_rom
@pytest.mark.parametrize("seed", range(1, 11))
def test_finish_prices_by_group_too(seed: int) -> None:
    """FINISH's repricing (a single-player seed with Triforce Shuffle and Map & Compass Shuffle: Anywhere, whose
    solo assignment moves items into the joined wares) follows the groups."""
    from zora.generate.pipeline import finish_world
    from zora.generate.solo_assignment import solo_assignment
    level_items = replace(POOL, triforce_shuffle=zora_flags.LevelItemShuffle.ANYWHERE,
                          map_compass_shuffle=zora_flags.LevelItemShuffle.ANYWHERE, pegasus_boots=ON)
    built = build(plan(z1r(C06=3), seed, zora_flags.encode(level_items)), remember_repo_base_rom())
    world, _finished = finish_world(built, solo_assignment(built))
    check_prices(built, world)


LEVEL_ITEM_SEARCH_SEEDS = range(1, 41)
LEVEL_ITEM_WARES_WANTED = 2


@pytest.mark.slow
@needs_base_rom
def test_a_level_item_in_a_shop_costs_20_to_40() -> None:
    """Owner ruling, 2026-11-27: a Triforce piece, map or compass that Anywhere's solo assignment puts in a shop
    ware costs 20-40 (it kept the slot's price, 250 in the Blue Ring's ware). Looks until two have landed in shops."""
    from zora.generate.pipeline import finish_world
    from zora.generate.solo_assignment import solo_assignment
    level_items = replace(POOL, triforce_shuffle=zora_flags.LevelItemShuffle.ANYWHERE,
                          map_compass_shuffle=zora_flags.LevelItemShuffle.ANYWHERE)
    found = 0
    for seed in LEVEL_ITEM_SEARCH_SEEDS:
        built = build(plan(z1r(C06=3), seed, zora_flags.encode(level_items)), remember_repo_base_rom())
        world, _finished = finish_world(built, solo_assignment(built))
        check_prices(built, world)
        found += sum(ware.item in SHOP_LEVEL_ITEMS for shop in world.overworld.caves if isinstance(shop, Shop)
                     for ware in shop.items)
        if found >= LEVEL_ITEM_WARES_WANTED:
            return
    raise AssertionError(f"only {found} level items in shops over seeds {LEVEL_ITEM_SEARCH_SEEDS}")


# --- the bought fairy ----------------------------------------------------------------------------

FAIRY_ITEM = 0x23
DROPPED_FAIRY_DESCRIPTOR = 0x12          # PRG0: an amount of 2, three hearts
EIGHT_CONTAINERS_NO_HEARTS = 0x70        # HeartValues: containers - 1 high, full hearts low
REFILL_FRAMES = 300
HEART_VALUES = 0x066F


@needs_base_rom
def test_no_patch_setting_or_coop_range_touches_the_fairy_patch() -> None:
    remember_repo_base_rom()
    ours = {offset + i for offset, data in fairy_refill_writes() for i in range(len(data))}
    assert not hits(ours)
    for table in (SERIES_PATCHES, FLAG_PATCHES):
        for name, pieces in table.items():
            assert not written(pieces) & ours, name
    for setting in ("select_swap", "low_health_beep", "death_warp", "reduce_flashing", "tunic_colors",
                    "heart_color", "music", "level_word", "boss_sound_word", "link_sprite"):
        assert not written_offsets(setting) & ours, setting


def _bought(rom: bytes, screen: int, position: int, console_class: type) -> tuple[int, int]:
    """(containers - 1, full hearts) after buying ware `position` of the cave on `screen` with
    eight empty containers."""
    console = console_class(rom)
    console.enter_cave(screen)
    console.emu[HEART_VALUES] = EIGHT_CONTAINERS_NO_HEARTS
    console.take_ware(position)
    console.emu.run(REFILL_FRAMES)
    value = console.emu[HEART_VALUES]
    return value >> 4, value & 0x0F



@needs_base_rom
def test_a_fairy_bought_in_a_zora_rom_refills_every_heart() -> None:
    from tests.test_bait_in_pool import ON as SHOP_ITEMS_ON
    from tests.test_bait_in_pool import SHAPES, Console
    from tests.test_bait_in_pool import _built as bait_built
    from zora.generate.steps.shuffle_shop_items import SHOPS
    built = bait_built(SHAPES, 1, SHOP_ITEMS_ON)
    shop, position = next((shop, position) for destination in SHOPS
                          if isinstance(shop := built.world.overworld.get_cave(destination, Shop), Shop)
                          for position, ware in enumerate(shop.items) if ware.item == Item.FAIRY)
    screen = next(screen.screen_num for screen in built.world.overworld.screens
                  if screen.destination == shop.destination)
    rom = finish(built, remember_repo_base_rom())
    assert rom[ITEM_ID_TO_DESCRIPTOR + FAIRY_ITEM] == DROPPED_FAIRY_DESCRIPTOR      # a dropped fairy: as PRG0
    assert _bought(rom, screen, position, Console) == (7, 7)


@needs_base_rom
def test_a_fairy_bought_in_an_archipelago_rom_refills_every_heart() -> None:
    """A shop's fairy (the spare bait's, with every owner flag on), on Archipelago's FINISH."""
    from tests.test_assignment_emulator import Console
    from tests.test_foreign_item_look import rom
    from zora.generate.places import _screens
    from zora.rom.parse.rom_file import parse_rom
    image = rom()
    world = parse_rom(image)
    shop, position = next((cave, index) for cave in world.overworld.caves if isinstance(cave, Shop)
                          for index, ware in enumerate(cave.items) if ware.item == Item.FAIRY)
    assert all(image[offset:offset + len(data)] == data for offset, data in fairy_refill_writes())
    assert _bought(image, _screens(world, shop.destination)[0], position, Console) == (7, 7)
