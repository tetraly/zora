"""Allow OW Blocks of Wood Sword (B03; overworld-behavior.md OW-CAVE-07): the wooden-sword cave's
partner set (OW-CAVE-03 rule (b)) widens by the item-gate sets whose item the player can have from
the start: the starting inventory's, or the "free item" under the secret Armos (the coast item
instead when the Armos item is the ladder or the start holds it). ZORA's own: an Armos on a screen a
gate walls in (Extra Raft Blocks and $34) is not reached from the start, so its item is not free (the
follow-up to 4ab25424; seeds 6 and 22 of tests/test_wood_sword_behind_blocks.py put the wooden-sword
cave behind the bracelet under such an Armos)."""
from ...model.enums import Item
from ...model.overworld import Overworld
from .cave_entries import BRACELET_SCREENS, BURNABLE_SCREENS, RAFT_SCREENS, recorder_screens
from .overworld_gates import OverworldGates

# The Bracelet set of OW-APP-A4 together with screens 32 and 33
BRACELET_SCREENS_WITH_32_33 = BRACELET_SCREENS | {32, 33}
# Only these free items count (a blue candle as the free item does not: only the starting candle
# slot accepts it)
FREE_ITEMS = frozenset({Item.RECORDER, Item.RED_CANDLE, Item.RAFT, Item.POWER_BRACELET})
CANDLES = frozenset({Item.BLUE_CANDLE, Item.RED_CANDLE})
# FP-START-01's starting inventory, without start items (FP-START-04: the pass reads the kept ones)
NO_STARTING_ITEMS: frozenset[Item] = frozenset()


def free_item(armos_item: int, coast_item: int, starting: frozenset[Item] = NO_STARTING_ITEMS,
              armos_reached: bool = True) -> Item | None:
    """OW-CAVE-07's free item: the Armos item, or the coast item when the Armos item is the ladder
    or the start holds the ladder (quirk: then the Armos item is ignored); None unless it is one of
    the four that count. armos_reached: whether Link reaches the Armos from the start
    (armos_reached_from_start); when not, the Armos item is never free, nor the coast item behind an Armos
    ladder, but the coast item still is when the start holds the ladder."""
    if Item.LADDER in starting:
        item = Item(coast_item)
    elif not armos_reached:
        return None
    else:
        item = Item(coast_item if armos_item == Item.LADDER else armos_item)
    return item if item in FREE_ITEMS else None


def wood_sword_extra_screens(overworld: Overworld, armos_item: int, coast_item: int,
                             starting: frozenset[Item] = NO_STARTING_ITEMS, armos_reached: bool = True,
                             ) -> frozenset[int]:
    """OW-CAVE-07: the screens added to the wooden-sword partner set, each set when its item is
    available (the starting inventory holds it, or it is the free item)."""
    available = set(starting)
    free = free_item(armos_item, coast_item, starting, armos_reached)
    if free is not None:
        available.add(free)
    screens: set[int] = set()
    if Item.POWER_BRACELET in available:
        screens |= BRACELET_SCREENS_WITH_32_33
    if Item.RECORDER in available:
        screens |= recorder_screens(overworld)
    if Item.RAFT in available:
        screens |= RAFT_SCREENS
    if available & CANDLES:
        screens |= BURNABLE_SCREENS
    return frozenset(screens)


def armos_reached_from_start(armos_screen: int, gates: OverworldGates, starting: frozenset[Item]) -> bool:
    """Whether Link reaches the Armos screen with the starting inventory: everything a gate asks to walk
    onto it (OverworldGates.walk_in_needs) is held from the start."""
    return all(item in starting for screens, item in gates.walk_in_needs() if armos_screen in screens)
