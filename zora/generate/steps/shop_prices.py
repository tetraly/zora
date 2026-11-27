"""Shop prices (SI-PRICE-01, revision 2026-11-27: a budget per group instead of class prices, the Blue Ring in
the optional group wherever it is sold, boomerangs cheap; the revision of 2026-11-26, owner revision 6 Oct 2026 and
the beta 9 price rules, 2026-10-24, before it; docs/deviations.md "Shop prices").

The wares holding an item the extras moved there (Shop Items in the Item Pool, Shuffle Blue Potion, Shuffle Wood
Sword, Add L4 Sword = Level 2), not their own item, and every ware in any shop holding an optional item, its own
included, are priced by the group the item falls in, over all of them at once (price_groups), so the shops' total
stays affordable when several upgrades land there. Prices are randomized only when the shops are (owner decision,
2026-11-27): with Shuffle Shop Items (B08) off and no item moved into a shop, the groups price nothing and the shops
keep PRG0's prices, the Blue Ring's 250 included (grouped_wares):
  - the required group, the items that can be required for progression (PriceRules.required_items). Which items can
    be is decided from the seed's settings once Random has resolved, never from its layout, so a price tells the
    player nothing the flags do not: the Ladder, Raft, Recorder, Power Bracelet, Bow, both candles, both arrows and
    the bait always; the Wand under Swords: Swordless (C07 = 3, VA-REJ-22: level 9 needs it); every sword and the
    Wand under Shuffle Wood Sword (the dungeons' sword family takes any of them; the swords stay optional under
    ASNB); the Book under Book to Understand NPCs (B48) with a randomized maze (its path is known only with the
    Book). With 3 or more in shops one total of 180-220 is drawn (PRG0's required total is 200: candle 60, arrows
    80, bait 60) and split among them, each 20-100; with 1 or 2 each costs 60-80. A shop's own required item in its
    own ware is outside the group and keeps its slot's price;
  - the optional group: the swords, the rings, the Wand, the Book, the Magical Key and, when Pegasus Boots makes the
    boomerangs boots, both boots. The highest-ranked one in shops, the headline, costs 200-240, ranked Magical Sword
    > Red Ring > White Sword > Blue Ring > the Pegasus Boots (L2, then L1) > the rest, the first ware winning a tie;
    with no optional item in shops there is no headline. Every other costs 40-150 and the group stays at or under
    450 (the rest at 40 each if they could not fit). Only the headline costs over 200. The Blue Ring is priced so
    in its own ware too (2026-11-27), whenever B08 is on or an item was moved into a shop;
  - cheap, outside both groups, drawn by price_groups after the groups from their stream (the steps' own draws
    stay, so generation and FINISH draw as before): the Triforce pieces, maps and compasses that Triforce Shuffle
    or Map & Compass Shuffle: Anywhere puts in a shop ware, 20-40 (owner ruling, 2026-11-27), the wooden and
    magical boomerangs without Pegasus Boots, 20-40 (owner ruling,
    2026-11-27: they only hurt weak enemies and take a menu slot, so they are early-game items), heart containers and
    the letter 20-40 (owner rulings, 6 Oct and 24 Oct 2026), a fairy 20-40 wherever it is sold (owner decision,
    2026-10-19);
  - unchanged: a blue potion away from the potion shop 25-55 (BLUE_POTION_PRICES), Archipelago's foreign wares
    (finish.FOREIGN_WARE_PRICES, drawn last), and any other item keeps the slot's price.
The groups' prices come from a stream of their own (price_groups_rng), drawn after every class draw of the steps that
moved the items (their draws stay, so placement and hints do not move): BUILD's at the end of generation
(pipeline.generate_world), FINISH's after its repricing (finish.reprice_wares). No required item ever costs more
than 100: the group's cap, and the shops' own stock, whose jitter is undone when it would lift a required ware above
100 (shuffle_shop_items.jitter_prices). The jitter acts on the stock before any ware is priced by group, so it never
moves a group's price.
"""
from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ...model.enums import Item
from ...model.level_items import LEVEL_ITEMS
from ...model.overworld import Shop, ShopItem
from ..rng import IntRng, Rng

if TYPE_CHECKING:
    from ...model.game_world import GameWorld
    from .extra_pool_items import ExtraPoolItems

# The classes' inclusive ranges
REQUIRED_PRICES = (60, 80)
OPTIONAL_PRICES = (200, 240)
BOOMERANG_PRICES = (20, 40)     # without Pegasus Boots (owner ruling, 2026-11-27), set by price_groups
# The steps' class draw for a boomerang, kept from before 2026-11-27 and overwritten by price_groups: a narrower
# range would draw differently and move everything generation draws after it
BOOMERANG_DRAW = (75, 125)
HEART_CONTAINER_PRICES = (20, 40)
FAIRY_PRICES = (20, 40)
# The most a required item may cost anywhere (owner rule, 2026-10-24)
REQUIRED_PRICE_CAP = 100
# The groups (SI-PRICE-01 revision 2026-11-26): 3 or more required items share one total
REQUIRED_TOTAL = (180, 220)
REQUIRED_SHARE = (20, REQUIRED_PRICE_CAP)
REQUIRED_GROUP_MIN = 3
HEADLINE_PRICES = (200, 240)
OTHER_OPTIONAL_PRICES = (40, 150)
OPTIONAL_TOTAL_CAP = 450
# The headline's ranking, strongest first; an optional item not named ranks after them all. With Pegasus Boots both
# boomerangs are the boots, L2 (the magical boomerang's code) then L1, in the fifth and sixth places; without them
# the boomerangs are cheap and in no group
HEADLINE_RANKING = (Item.MAGICAL_SWORD, Item.RED_RING, Item.WHITE_SWORD, Item.BLUE_RING,
                    Item.MAGICAL_BOOMERANG, Item.WOOD_BOOMERANG)
PRICE_GROUPS_STREAM = b"zora shop prices"     # 16 bytes at most (BLAKE2b's person)
SEED_BYTES = 8

# Required under every setting: the overworld's four, the bow, and every candle-line and arrow-line
# item (a candle burns the bushes, the arrows beat Gohma and Ganon), and the bait (a hungry Goriya
# blocks his room's north side)
ALWAYS_REQUIRED = frozenset({Item.LADDER, Item.RAFT, Item.POWER_BRACELET, Item.RECORDER, Item.BOW,
                             Item.BLUE_CANDLE, Item.RED_CANDLE, Item.WOOD_ARROWS, Item.SILVER_ARROWS, Item.BAIT})
SWORDS = frozenset({Item.WOOD_SWORD, Item.WHITE_SWORD, Item.MAGICAL_SWORD})
BOOMERANGS = frozenset({Item.WOOD_BOOMERANG, Item.MAGICAL_BOOMERANG})
OPTIONAL_ITEMS = SWORDS | BOOMERANGS | {Item.BLUE_RING, Item.RED_RING, Item.WAND, Item.BOOK, Item.MAGICAL_KEY}
# Priced cheap: the letter reaches a shop ware only with Randomize Letter on (owner decision, 6 Oct 2026)
CHEAP_ITEMS = frozenset({Item.HEART_CONTAINER, Item.LETTER})
# Triforce pieces, maps and compasses in a shop ware, each level's code (owner ruling, 2026-11-27)
LEVEL_ITEM_PRICES = (20, 40)
SHOP_LEVEL_ITEMS = frozenset(LEVEL_ITEMS)


@dataclass(frozen=True)
class PriceRules:
    """What the price classes read of a seed's resolved settings (ExtraOptions.price_rules)."""
    swordless: bool = False                  # Swords: Swordless (C07 = 3)
    wood_sword_in_pool: bool = False         # Shuffle Wood Sword
    swords_open_level_9: bool = False        # ASNB: Level 9 Entrance = Level 4 sword
    book_needed: bool = False                # B48 with a randomized maze (LogicRules.maze_hints_need_book)
    pegasus_boots: bool = False
    shops_shuffled: bool = False             # Shuffle Shop Items (B08) on, as it runs

    @property
    def required_items(self) -> frozenset[Item]:
        """The items that can be required under these settings."""
        items = set(ALWAYS_REQUIRED)
        if self.swordless or self.wood_sword_in_pool:
            items.add(Item.WAND)
        if self.wood_sword_in_pool and not self.swords_open_level_9:
            items |= SWORDS
        if self.book_needed:
            items.add(Item.BOOK)
        return frozenset(items)

    @property
    def optional_items(self) -> frozenset[Item]:
        """The optional group's items under these settings: the optional items no setting makes required, the
        boomerangs only as the Pegasus Boots (without them they are cheap)."""
        optional = OPTIONAL_ITEMS if self.pegasus_boots else OPTIONAL_ITEMS - BOOMERANGS
        return frozenset(optional - self.required_items)

    @property
    def prices(self) -> dict[Item, tuple[int, int]]:
        """Each priced item's range; an item not named keeps its slot's price."""
        prices = {**dict.fromkeys(OPTIONAL_ITEMS, OPTIONAL_PRICES),
                  **dict.fromkeys(CHEAP_ITEMS, HEART_CONTAINER_PRICES), Item.FAIRY: FAIRY_PRICES}
        if not self.pegasus_boots:
            prices.update(dict.fromkeys(BOOMERANGS, BOOMERANG_DRAW))
        prices.update(dict.fromkeys(self.required_items, REQUIRED_PRICES))
        return prices


DEFAULT_PRICE_RULES = PriceRules()


# --- the groups (SI-PRICE-01 revision 2026-11-26) ----------------------------------------------------

def price_groups_rng(generation_seed: int, stage: bytes) -> Rng:
    """The groups' own stream, keyed by the generation seed and the stage (b"build" or b"finish"), so the draws of
    generation's and FINISH's streams stay where they were."""
    message = generation_seed.to_bytes(SEED_BYTES, "little") + stage
    key = hashlib.blake2b(message, digest_size=SEED_BYTES, person=PRICE_GROUPS_STREAM).digest()
    return Rng(int.from_bytes(key, "little"))


def _uniform(rng: IntRng, low: int, high: int) -> int:
    return low + rng.below(high - low + 1)


def split_total(total: int, count: int, rng: IntRng, share: tuple[int, int] = REQUIRED_SHARE) -> list[int]:
    """`total` split into `count` prices, each within `share`: uniform over the splits, by cut points drawn again
    while a part breaks the cap."""
    low, high = share
    spare = total - low * count
    assert 0 <= spare <= (high - low) * count, (total, count)
    while True:
        cuts = sorted(rng.below(spare + 1) for _ in range(count - 1))
        parts = [b - a for a, b in zip([0, *cuts], [*cuts, spare], strict=True)]
        if all(part <= high - low for part in parts):
            return [low + part for part in parts]


def headline_rank(item: Item) -> int:
    """The item's place in the headline ranking (0 strongest); every unnamed item shares the last."""
    return HEADLINE_RANKING.index(item) if item in HEADLINE_RANKING else len(HEADLINE_RANKING)


def price_groups(wares: Sequence[ShopItem], rules: PriceRules, rng: IntRng) -> None:
    """Price the wares (each holding an item a step moved there, in a fixed order) by group: the required group's
    total or 60-80 each, then the optional group's headline and the rest, then the cheap ones, 20-40 each: a
    Triforce piece, map or compass, and a boomerang without the boots. Any other ware is left as it is."""
    required = [ware for ware in wares if ware.item in rules.required_items]
    if len(required) >= REQUIRED_GROUP_MIN:
        total = _uniform(rng, *REQUIRED_TOTAL)
        for ware, price in zip(required, split_total(total, len(required), rng), strict=True):
            ware.price = price
    else:
        for ware in required:
            ware.price = _uniform(rng, *REQUIRED_PRICES)
    price_optional_group([ware for ware in wares if ware.item in rules.optional_items], rng)
    cheap = SHOP_LEVEL_ITEMS if rules.pegasus_boots else SHOP_LEVEL_ITEMS | BOOMERANGS
    for ware in wares:
        if ware.item in cheap:
            ware.price = _uniform(rng, *(LEVEL_ITEM_PRICES if ware.item in SHOP_LEVEL_ITEMS else BOOMERANG_PRICES))


def price_optional_group(optional: Sequence[ShopItem], rng: IntRng) -> None:
    """The optional group: the headline 200-240, every other 40-150, the group at most 450."""
    if not optional:
        return
    headline = min(optional, key=lambda ware: headline_rank(ware.item))      # the first of the best rank
    headline.price = _uniform(rng, *HEADLINE_PRICES)
    others = [ware for ware in optional if ware is not headline]
    budget = OPTIONAL_TOTAL_CAP - headline.price
    low, high = OTHER_OPTIONAL_PRICES
    if low * len(others) > budget:
        for ware in others:
            ware.price = low
        return
    order = list(range(len(others)))
    rng.shuffle(order)
    for left, index in enumerate(order, start=1):
        most = min(high, budget - low * (len(others) - left))
        others[index].price = _uniform(rng, low, most)
        budget -= others[index].price


def grouped_wares(world: GameWorld, extras: ExtraPoolItems | None, rules: PriceRules) -> list[ShopItem]:
    """The wares the groups price: the joined wares of `world` holding an item other than their own, in join order,
    then every other ware of every shop holding an optional item (its own Blue Ring included), in shop order.
    Every item a step moves into a shop sits in a joined ware, so the cheap ones are among them. None when the
    shops are as PRG0 stocks them: Shuffle Shop Items off and no item moved (owner decision, 2026-11-27)."""
    found: list[ShopItem] = []
    for ware, own_item in zip(extras.shop_wares, extras.shop_items, strict=True) if extras else ():
        shop = world.overworld.get_cave(ware.shop.destination, Shop)
        assert shop is not None
        held = shop.ware(ware.position)
        if held.item != own_item:
            found.append(held)
    if not found and not rules.shops_shuffled:
        return found
    for cave in world.overworld.caves:
        if isinstance(cave, Shop):
            found += [ware for ware in cave.items
                      if ware.item in rules.optional_items and not any(ware is other for other in found)]
    return found
