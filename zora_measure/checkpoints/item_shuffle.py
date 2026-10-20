"""Item Shuffle's other values: None (C06 = 0), Item Only (C06 = 1) and Random (C06 = 4)
(post-shapes-b1.md PS-ITEM-09 to PS-ITEM-11): the Checks measured on finished ROMs, against the
one-field corpora of the MVP baseline's string (zora_measure.corpora.corpus(name); hash manifests
docs/spec/corpus-c06-*-final-hash-manifest.csv). Items within each dungeon (C06 = 2) has its own
rows (items_within.py)."""
from collections import Counter

from zora.model.enums import Item
from zora.model.game_world import GameWorld
from zora_measure.checkpoints.acceptance import CAVE_SLOT, item_places
from zora_measure.checkpoints.items_within import PROGRESSION_ITEMS
from zora_measure.checkpoints.summaries import FLAG_COUNTS, Checkpoint, count_true, distribution
from zora_measure.statistics import b1_checkpoint, special_cave_items

SPEC_ITEM = "post-shapes-b1.md @ 1fd481e"
# The one-field corpora's strings: the MVP baseline corpus string with only C06 changed
NO_ITEM_SHUFFLE_FLAGS = "8hq4BeR1JXo89BJ2!TFpTP02u8TmBq"     # C06 = 0
ITEM_ONLY_FLAGS = "8hq4BeR1JXo89BJ2!TFpTP02u8TxTx"           # C06 = 1
RANDOM_ITEM_SHUFFLE_FLAGS = "8hq4BeR1JXo89BJ2!TFpTP02u8UULH"  # C06 = 4

# PS-ITEM-10: PRG0's three special-cave items, in special_cave_items' order (Armos, white-sword
# cave, coast)
PRG0_CAVE_ITEMS = [Item.POWER_BRACELET, Item.WHITE_SWORD, Item.HEART_CONTAINER]
HEART_CONTAINERS = 9
DUNGEON_HEART_COUNTS = (8, 9)


def cave_items_kept(gw: GameWorld) -> bool:
    """PS-ITEM-10: the three cave item bytes are PRG0's (bracelet, white sword, heart)."""
    return special_cave_items(gw) == PRG0_CAVE_ITEMS


def _dungeon_counts(gw: GameWorld) -> Counter[Item]:
    """How many level rooms and item cellars hold each item (the dungeon tables)."""
    return Counter({item: sum(place != CAVE_SLOT for place in places) for item, places in item_places(gw).items()})


def progression_items_once_in_levels(gw: GameWorld) -> bool:
    """PS-ITEM-10: each of the twelve progression items once in the dungeon tables."""
    counts = _dungeon_counts(gw)
    return all(counts[item] == 1 for item in PROGRESSION_ITEMS)


def no_deal(gw: GameWorld) -> bool:
    """PS-ITEM-11's "no deal": the cave bytes PRG0's and each progression item once in the tables."""
    return cave_items_kept(gw) and progression_items_once_in_levels(gw)


def dungeon_hearts(gw: GameWorld) -> int:
    """Heart containers in both blocks' rooms and cellars."""
    return b1_checkpoint(gw).hearts_dungeon


def hearts_in_all(gw: GameWorld) -> bool:
    """PS-ITEM-09: nine heart containers, dungeon tables plus the three cave slots."""
    checkpoint = b1_checkpoint(gw)
    return checkpoint.hearts_dungeon + checkpoint.hearts_caves == HEART_CONTAINERS


def two_hearts_in_caves(gw: GameWorld) -> bool:
    """PS-ITEM-09 and PS-ITEM-11: two or more heart containers in the cave slots (only full scope)."""
    return b1_checkpoint(gw).hearts_caves >= 2


def progression_items_missing(gw: GameWorld) -> dict[str, bool]:
    """PS-ITEM-09: each progression item missing from the dungeon tables (it is in a cave slot)."""
    counts = _dungeon_counts(gw)
    return {item.name.lower(): counts[item] == 0 for item in PROGRESSION_ITEMS}


def ladder_at_the_coast(gw: GameWorld) -> bool:
    """PS-ITEM-09: the coast cave slot holds the ladder (the spec's corpus never has it there)."""
    items = special_cave_items(gw)
    return len(items) == len(PRG0_CAVE_ITEMS) and items[-1] == Item.LADDER


_HEARTS_IN_ALL = Checkpoint("PS-ITEM-09", "nine heart containers (tables and cave slots)", "1000/1000",
                            SPEC_ITEM, hearts_in_all, count_true)

ITEM_SHUFFLE_SETS = {
    "c06-none": (
        Checkpoint("PS-ITEM-10", "the three cave items are PRG0's", "1000/1000", SPEC_ITEM, cave_items_kept,
                   count_true),
        Checkpoint("PS-ITEM-10", "each progression item once in the dungeon tables", "1000/1000", SPEC_ITEM,
                   progression_items_once_in_levels, count_true),
        Checkpoint("PS-ITEM-10", "dungeon tables hold 8 / 9 heart containers", "1000 / 0", SPEC_ITEM,
                   dungeon_hearts, distribution(DUNGEON_HEART_COUNTS)),
    ),
    "c06-itemonly": (
        _HEARTS_IN_ALL,
        Checkpoint("PS-ITEM-09", "dungeon tables hold 8 / 9 heart containers", "173 / 827", SPEC_ITEM,
                   dungeon_hearts, distribution(DUNGEON_HEART_COUNTS)),
        Checkpoint("PS-ITEM-09", "two or more heart containers in the cave slots", "0/1000 (CP-5: 296)",
                   SPEC_ITEM, two_hearts_in_caves, count_true),
        Checkpoint("PS-ITEM-09", "each progression item missing from the dungeon tables", "171 to 242 each",
                   SPEC_ITEM, progression_items_missing, FLAG_COUNTS),
        Checkpoint("PS-ITEM-09", "the ladder at the coast", "0/1000", SPEC_ITEM, ladder_at_the_coast, count_true),
    ),
    "c06-random": (
        _HEARTS_IN_ALL,
        Checkpoint("PS-ITEM-11", "no deal (cave items PRG0's, each progression item once in the tables)",
                   "280/1000 (expected about 250)", SPEC_ITEM, no_deal, count_true),
        Checkpoint("PS-ITEM-11", "two or more heart containers in the cave slots", "65/1000 (expected 74)",
                   SPEC_ITEM, two_hearts_in_caves, count_true),
    ),
}
ITEM_SHUFFLE_FLAGS = {"c06-none": NO_ITEM_SHUFFLE_FLAGS, "c06-itemonly": ITEM_ONLY_FLAGS,
                      "c06-random": RANDOM_ITEM_SHUFFLE_FLAGS}
