"""A fairy costs 20-40 rupees wherever a shop sells one (owner decision, 2026-10-19; beta 6
testing): the spare bait's fairy (Shop Items in the Item Pool with one hungry Goriya,
bait_in_pool), the logo look's shield fairies (finish.shields_to_fairies) and any joined ware the
price classes reprice holding a fairy (PRICES_BY_ITEM, SI-PRICE-01)."""
import copy

import pytest

from tests.test_bait_in_pool import SHAPES, _built
from tests.test_foreign_item_look import rom, shields_and_fairies
from zora.generate.finish import LOGO_SHOP_FAIRY_PRICES, ForeignLook
from zora.generate.pipeline import finish
from zora.generate.rng import Rng
from zora.generate.steps.bait_in_pool import bait_in_pool, bait_wares
from zora.generate.steps.extra_pool_items import ExtraPoolItems
from zora.generate.steps.shop_items_in_pool import FAIRY_PRICES, PRICES_BY_ITEM, price_displaced_wares
from zora.model.enums import Item
from zora.model.overworld import Shop
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

LOW, HIGH = 20, 40
DRAWS = 200                 # 21 prices: each end is missed with chance (20/21)^200, about 6e-5
SEEDS = (1, 2, 3, 4)


def fairy_prices(image: bytes) -> list[int]:
    world = parse_rom(image)
    return [ware.price for shop in world.overworld.caves if isinstance(shop, Shop)
            for ware in shop.items if ware.item == Item.FAIRY]


def test_every_path_shares_one_range() -> None:
    assert FAIRY_PRICES == (LOW, HIGH)
    assert PRICES_BY_ITEM[Item.FAIRY] == FAIRY_PRICES and LOGO_SHOP_FAIRY_PRICES == FAIRY_PRICES


def test_the_spare_bait_fairy_draws_over_the_whole_range() -> None:
    """The step on a flag-off world (two baits, one Goriya), once per stream: every price is
    20-40 and both ends come up."""
    built = _built(SHAPES, 1, "")
    prices = set()
    for stream in range(DRAWS):
        world, state = copy.deepcopy((built.world, built.result.item_shuffle_result))
        assert state is not None
        spare = bait_wares(world.overworld)[1]
        bait_in_pool(world.levels, state, ExtraPoolItems(), world.overworld, Rng(stream))
        assert spare.get() == Item.FAIRY
        prices.add(spare.shop.ware(spare.position).price)
    assert prices == set(range(LOW, HIGH + 1))


def test_a_joined_ware_holding_a_fairy_is_priced_20_to_40() -> None:
    """The price classes' path: a joined ware that ends up holding a fairy."""
    built = _built(SHAPES, 1)
    extras = copy.deepcopy(built.result.extra_pool_items)
    assert extras is not None and extras.shop_wares
    for stream in range(20):
        ware = extras.shop_wares[0]
        ware.shop.ware(ware.position).item = Item.FAIRY
        price_displaced_wares(extras, Rng(stream))
        assert LOW <= ware.shop.ware(ware.position).price <= HIGH


@pytest.mark.parametrize("seed", SEEDS)
def test_every_sold_fairy_costs_20_to_40_in_a_finished_rom(seed: int) -> None:
    prices = fairy_prices(finish(_built(SHAPES, seed), remember_repo_base_rom()))
    assert prices and all(LOW <= price <= HIGH for price in prices), prices


@pytest.mark.parametrize("look", list(ForeignLook))
def test_every_sold_fairy_costs_20_to_40_in_an_archipelago_rom(look: ForeignLook) -> None:
    """Archipelago's FINISH with every owner flag on: the spare bait's fairy, and with the logo
    the real shields' fairies too."""
    image = rom(look)
    prices = shields_and_fairies(image)[1]
    assert prices == fairy_prices(image)
    assert prices and all(LOW <= price <= HIGH for price in prices), prices
