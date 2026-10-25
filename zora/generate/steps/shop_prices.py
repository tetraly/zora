"""Shop prices by what a ware sells (SI-PRICE-01, owner revision 6 Oct 2026; the beta 9 price rules,
owner decisions 2026-10-24; docs/deviations.md "Shop prices: required items never cost more than
100 rupees").

A shop ware holding an item the extras moved there (Shop Items in the Item Pool, Shuffle Blue
Potion, Shuffle Wood Sword, Add L4 Sword = Level 2) is priced by that item's class, drawn uniformly
over the class's inclusive range:
  - an item that can be required for progression: 60-80. Which items can be is decided from the
    seed's settings once Random has resolved, never from its layout, so a price tells the player
    nothing the flags do not: the Ladder, Raft, Recorder, Power Bracelet, Bow, both candles, both
    arrows and the bait always; the Wand under Swords: Swordless (C07 = 3, VA-REJ-22: level 9 needs
    it); every sword and the Wand under Shuffle Wood Sword (the dungeons' sword family takes any of
    them; the swords stay optional under ASNB); the Book under Book to Understand NPCs (B48) with a
    randomized maze (its path is known only with the Book);
  - the boomerangs: 75-125, or optional (200-240) with Pegasus Boots on, which makes them boots;
  - an optional item: 200-240 (the other swords, rings, the Wand, the Book, the Magical Key);
  - heart containers and the letter: 20-40 (owner rulings, 6 Oct and 24 Oct 2026), and a fairy
    20-40 wherever it is sold (owner decision, 2026-10-19);
  - any other item keeps the slot's price.
No required item ever costs more than 100: the 60-80 class, and the shops' own stock, whose jitter
is undone when it would lift a required ware above 100 (shuffle_shop_items.jitter_prices).
"""
from __future__ import annotations

from dataclasses import dataclass

from ...model.enums import Item

# The classes' inclusive ranges
REQUIRED_PRICES = (60, 80)
OPTIONAL_PRICES = (200, 240)
BOOMERANG_PRICES = (75, 125)
HEART_CONTAINER_PRICES = (20, 40)
FAIRY_PRICES = (20, 40)
# The most a required item may cost anywhere (owner rule, 2026-10-24)
REQUIRED_PRICE_CAP = 100

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


@dataclass(frozen=True)
class PriceRules:
    """What the price classes read of a seed's resolved settings (ExtraOptions.price_rules)."""
    swordless: bool = False                  # Swords: Swordless (C07 = 3)
    wood_sword_in_pool: bool = False         # Shuffle Wood Sword
    swords_open_level_9: bool = False        # ASNB: Level 9 Entrance = Level 4 sword
    book_needed: bool = False                # B48 with a randomized maze (LogicRules.maze_hints_need_book)
    pegasus_boots: bool = False

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
    def prices(self) -> dict[Item, tuple[int, int]]:
        """Each priced item's range; an item not named keeps its slot's price."""
        prices = {**dict.fromkeys(OPTIONAL_ITEMS, OPTIONAL_PRICES),
                  **dict.fromkeys(CHEAP_ITEMS, HEART_CONTAINER_PRICES), Item.FAIRY: FAIRY_PRICES}
        if not self.pegasus_boots:
            prices.update(dict.fromkeys(BOOMERANGS, BOOMERANG_PRICES))
        prices.update(dict.fromkeys(self.required_items, REQUIRED_PRICES))
        return prices


DEFAULT_PRICE_RULES = PriceRules()
