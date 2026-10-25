"""Shop prices (the beta 9 price rules, owner decisions 2026-10-24; zora/generate/steps/shop_prices.py,
docs/deviations.md "Shop prices: required items never cost more than 100 rupees") and the bought
fairy's full refill (zora/rom/fairy_refill.py).

- No item that can be required ever costs more than 100 rupees in a shop: a joined ware holding one
  costs 60-80, and the shops' own stock undoes a jitter that would lift the arrows, the candle or the
  bait above 100. "Can be required" is read from the seed's resolved settings.
- The other classes hold: the boomerangs 75-125 (optional with Pegasus Boots), optional items
  200-240 (the swords too under ASNB), heart containers and the letter 20-40, a fairy 20-40.
- Add L4 Sword = Level 2 and Shuffle Wood Sword price a joined ware their sword lands in (they kept
  the price of the item it held).
- A bought fairy refills every heart, in a ZORA ROM and an Archipelago ROM; a dropped fairy's item
  entry stays PRG0's (three hearts); no ZORA patch, player setting or z1rr-coop range touches the
  patch's bytes."""
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
from zora.generate.rng import ScriptedRng
from zora.generate.steps.shop_prices import (
    ALWAYS_REQUIRED,
    BOOMERANG_PRICES,
    BOOMERANGS,
    CHEAP_ITEMS,
    FAIRY_PRICES,
    HEART_CONTAINER_PRICES,
    OPTIONAL_PRICES,
    REQUIRED_PRICE_CAP,
    REQUIRED_PRICES,
    SWORDS,
    PriceRules,
)
from zora.generate.steps.shuffle_shop_items import jitter_prices
from zora.model.enums import Item
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
    assert all(base.prices[item] == BOOMERANG_PRICES for item in BOOMERANGS)
    assert all(PriceRules(pegasus_boots=True).prices[item] == OPTIONAL_PRICES for item in BOOMERANGS)
    assert all(base.prices[item] == HEART_CONTAINER_PRICES == (20, 40) for item in CHEAP_ITEMS)
    assert base.prices[Item.FAIRY] == FAIRY_PRICES == (20, 40)
    assert BOOMERANG_PRICES == (75, 125) and OPTIONAL_PRICES == (200, 240) and REQUIRED_PRICES == (60, 80)


@needs_base_rom
def test_the_rules_are_read_from_the_resolved_settings() -> None:
    def rules(case: str) -> PriceRules:
        flags, extras = CASES[case]
        return extra_options(plan(flags, 1, zora_flags.encode(extras))).price_rules
    assert rules("pool") == PriceRules()
    assert rules("pool, swordless").swordless
    assert rules("pool, book to understand NPCs, mazes").book_needed
    assert rules("pool, wood sword").wood_sword_in_pool and rules("pool, boots").pegasus_boots
    assert rules("ASNB, pool, blue potion").swords_open_level_9


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


def check_prices(built: Built) -> None:
    """Every shop ware of a built seed against the rules its settings resolve to."""
    rules = extra_options(built.plan).price_rules
    extras = built.result.extra_pool_items
    joined = {} if extras is None else {
        (ware.shop.destination, ware.position): own for ware, own in zip(extras.shop_wares, extras.shop_items,
                                                                         strict=True)}
    for shop in built.world.overworld.caves:
        if not isinstance(shop, Shop):
            continue
        for position, ware in enumerate(shop.items):
            where = (shop.destination.name, position, ware.item.name, ware.price)
            if ware.item in rules.required_items:
                assert ware.price <= REQUIRED_PRICE_CAP, where
            if ware.item == Item.FAIRY:
                assert FAIRY_PRICES[0] <= ware.price <= FAIRY_PRICES[1], where
            own = joined.get((shop.destination, position))
            if own is not None and ware.item != own and ware.item in rules.prices:
                low, high = rules.prices[ware.item]
                assert low <= ware.price <= high, where


SEEDS = (1, 2, 3)


@needs_base_rom
@pytest.mark.parametrize("case", CASE_PARAMS)
@pytest.mark.parametrize("seed", SEEDS)
def test_no_required_item_costs_more_than_100_and_the_classes_hold(case: str, seed: int) -> None:
    check_prices(_built(case, seed))


@needs_base_rom
@pytest.mark.parametrize("case", SWORD_JOIN_CASES)
def test_a_sword_joined_into_a_shop_ware_is_priced_by_its_class(case: str) -> None:
    """Add L4 Sword = Level 2's and Shuffle Wood Sword's joins: the first seeds where a sword ends in
    a shop ware, each priced by its class (it kept a heart container's 20-40 before the fix)."""
    found = 0
    for seed in SWORD_SEARCH_SEEDS:
        built = _built(case, seed)
        rules = extra_options(built.plan).price_rules
        for shop in built.world.overworld.caves:
            if isinstance(shop, Shop):
                for ware in shop.items:
                    if ware.item in SWORDS:
                        low, high = rules.prices[ware.item]
                        assert low <= ware.price <= high, (case, seed, ware)
                        found += 1
        if found >= SWORD_WARES_WANTED:
            return
    raise AssertionError(f"{case}: only {found} swords in shops over seeds {SWORD_SEARCH_SEEDS}")


@pytest.mark.slow
@needs_base_rom
@pytest.mark.parametrize("case", CASE_PARAMS)
def test_the_rules_hold_over_20_seeds(case: str) -> None:
    for seed in range(1, 21):
        flags, extras = CASES[case]
        check_prices(build(plan(flags, seed, zora_flags.encode(extras)), remember_repo_base_rom()))


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
    """The logo look's fairies (every real magical shield), on Archipelago's FINISH."""
    from tests.test_assignment_emulator import Console
    from tests.test_foreign_item_look import rom, shields_and_fairies
    from zora.generate.finish import ForeignLook
    from zora.generate.places import _screens
    from zora.rom.parse.rom_file import parse_rom
    image = rom(ForeignLook.LOGO)
    world = parse_rom(image)
    shields = {destination for destination, _ in shields_and_fairies(rom(ForeignLook.RUPEE))[0]}
    shop, position = next((cave, index) for cave in world.overworld.caves if isinstance(cave, Shop)
                          for index, ware in enumerate(cave.items)
                          if ware.item == Item.FAIRY and cave.destination in shields)
    assert all(image[offset:offset + len(data)] == data for offset, data in fairy_refill_writes())
    assert _bought(image, _screens(world, shop.destination)[0], position, Console) == (7, 7)
