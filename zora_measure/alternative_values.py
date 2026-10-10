"""The Checks of the alternative values (flags-behavior.md FL-ALT-02 to
FL-ALT-04), per finished ROM, on the parsed GameWorld.

Each function returns named yes/no figures; a batch counts them (n = 200 in
the spec, scripts/alternative_values.py). The control is the same seeds
under CP-5 unchanged, where the alternative-value figures read the other way.
"""
from __future__ import annotations

from functools import cache

from zora.generate.steps.hint_text import HOLDER_SLOT, LEVEL9_TRIO_SLOTS, MEET_SLOT, POOL, SHOW_SLOT
from zora.generate.steps.shuffle_dungeon_text import SHUFFLED_SLOTS
from zora.model.enums import Destination, TollOption
from zora.model.game_world import GameWorld
from zora.model.overworld import HintShop, ItemCave
from zora.rom.base_rom import player_rom
from zora.rom.heart_values import heart_values
from zora.rom.parse.rom_file import parse_rom
from zora.rom.person_code import life_toll_heart_count_operand
from zora_measure.checkpoints.features import CONTINUE_HEARTS, FP_START_ITEMS

# FL-ALT-02: FP-START-01's 40-byte starting values with HeartValues (index 24) $32.
HEART_VALUES_INDEX = 24
FOUR_HEART_START_ITEMS = (FP_START_ITEMS[:HEART_VALUES_INDEX] + bytes([heart_values(4, 3)])
                          + FP_START_ITEMS[HEART_VALUES_INDEX + 1:])
# PS-MERCH-04: a starting-hearts byte above 32 reads as 34, so the toll asks for its count $30.
LIFE_TOLL_HEART_COUNT = 0x30
# FL-ALT-04: the texts that would be helpful ones, by slot: the white-sword cave entry,
# show-to, meet, and the level-9 trio (silver arrows, Ganon or Zelda, Zelda or the compass).
HELPFUL_TEXT_SLOTS = (HOLDER_SLOT, SHOW_SLOT, MEET_SLOT, *LEVEL9_TRIO_SLOTS)
WHITE_SWORD_SELECTOR = 0x66
WOOD_SWORD_CAVE_SLOT = 0
OWNER_SLOT_0_CLASS = "slot 0 (owner ruling)"
PAD = "~"


def _lines(text: str) -> tuple[str, ...]:
    """A shown text's lines without the centring pad."""
    return tuple(line.strip(PAD) for line in text.split("|"))


POOL_TEXTS = frozenset(entry.lines for entry in POOL)
OWNER_SLOT_0_TEXTS = frozenset(entry.lines for entry in POOL if entry.routing_class == OWNER_SLOT_0_CLASS)


def _slot_text(gw: GameWorld, slot: int) -> tuple[str, ...]:
    return next(_lines(quote.text) for quote in gw.quotes if quote.quote_id == slot)


def starting_hearts_4(gw: GameWorld, rom: bytes) -> dict[str, bool]:
    """FL-ALT-02's Check: the new file's starting values with HeartValues $32 (and the
    second-quest switch's, which set the same values), the Continue operand $02, and the life
    toll's heart-count operand $30 where the toll's first option is life."""
    toll = gw.life_or_money_toll
    life_toll = toll is not None and toll.first is TollOption.LIFE
    return {
        "new file $32, the rest FP-START-01's": gw.starting_items_new_file == FOUR_HEART_START_ITEMS,
        "second-quest switch the same": gw.starting_items_second_quest == FOUR_HEART_START_ITEMS,
        "new file FP-START-01's ($22)": gw.starting_items_new_file == FP_START_ITEMS,
        "continue $02": gw.continue_hearts_operand == CONTINUE_HEARTS,
        "life toll": life_toll,
        "life toll asks $30": life_toll and life_toll_heart_count_operand(rom) == LIFE_TOLL_HEART_COUNT,
    }


def white_sword_hearts(gw: GameWorld) -> dict[str, bool]:
    """FL-ALT-03's Check: the hearts each sword cave asks for, one figure per count."""
    figures: dict[str, bool] = {}
    for name, destination, counts in (("white", Destination.WHITE_SWORD_CAVE, range(4, 7)),
                                      ("magical", Destination.MAGICAL_SWORD_CAVE, range(10, 15))):
        cave = gw.overworld.get_cave(destination, ItemCave)
        asked = cave.heart_requirement if cave is not None else None
        figures |= {f"{name} {count}": asked == count for count in counts}
    return figures


HINT_SHOPS = (Destination.HINT_SHOP_1, Destination.HINT_SHOP_2)


def hint_shop_offers(gw: GameWorld) -> tuple[tuple[int, ...] | None, tuple[int, ...]]:
    """The hint shops' offer selectors and prices."""
    shops = [gw.overworld.get_cave(destination, HintShop) for destination in HINT_SHOPS]
    return gw.hint_shop_offer_selectors, tuple(hint.price for shop in shops if shop is not None
                                               for hint in shop.hints)


@cache
def prg0_hint_shop_offers() -> tuple[tuple[int, ...] | None, tuple[int, ...]]:
    """FL-ALT-04: PRG0's hint-shop offer selectors and prices, kept with community hints;
    read from the player's ROM."""
    return hint_shop_offers(parse_rom(player_rom()))


def community_hints(gw: GameWorld) -> dict[str, bool]:
    """FL-ALT-04's Check: no helpful text in its slots, PRG0's hint-shop offers and prices, the
    white-sword cave selector $66, and the eleven exchanged pointers distinct. Slot 0: the
    owner's ruling (one of the owner's seven quotes) in place of FL-ALT-04's greeting."""
    figures = {f"slot {slot} a pool text": _slot_text(gw, slot) in POOL_TEXTS for slot in HELPFUL_TEXT_SLOTS}
    selectors, prices = hint_shop_offers(gw)
    prg0_selectors, prg0_prices = prg0_hint_shop_offers()
    pointers = gw.hint_pointers or ()
    figures |= {
        "slot 0 an owner quote": _slot_text(gw, WOOD_SWORD_CAVE_SLOT) in OWNER_SLOT_0_TEXTS,
        "hint-shop offers PRG0's": selectors == prg0_selectors,
        "hint-shop prices PRG0's": prices == prg0_prices,
        "white-sword selector $66": gw.white_sword_text_selector == WHITE_SWORD_SELECTOR,
        "eleven pointers distinct": len({pointers[slot] for slot in SHUFFLED_SLOTS}) == len(SHUFFLED_SLOTS),
    }
    return figures


def alternative_value_figures(gw: GameWorld, rom: bytes) -> dict[str, bool]:
    """Every FL-ALT figure of one ROM."""
    return {**starting_hearts_4(gw, rom), **white_sword_hearts(gw), **community_hints(gw)}
