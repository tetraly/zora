"""Items within each dungeon (C06 = 2; post-shapes-b1.md PS-ITW-01 to PS-ITW-05): the Checks
measured on finished ROMs. The spec's figures are the original randomizer's "within finals" (flag
string ITEMS_WITHIN_FLAGS, seeds 1-1000), the corpus corpus("items-within") (its hash manifest
is docs/spec/corpus-items-within-final-hash-manifest.csv); every row reproduces the spec's figure
there."""
from collections import Counter

from zora.generate.steps.hint_text import item_location_sentence
from zora.model.enums import Item, RoomType
from zora.model.game_world import GameWorld
from zora.model.rooms import StaircaseRoom
from zora_measure.checkpoints.acceptance import CAVE_SLOT, item_places
from zora_measure.checkpoints.summaries import Summary
from zora_measure.statistics import special_cave_items

SPEC_ITW = "post-shapes-b1.md @ a269b1a"
# PS-ITW's "within finals": the corpus string (CP-5) with C06 = 2 and no other change
ITEMS_WITHIN_FLAGS = "8hq4BeR1JXo89BJ2!TFpTP02u8U7m3"

# PS-ITEM-01's twelve progression items
PROGRESSION_ITEMS = (Item.RECORDER, Item.RAFT, Item.WOOD_BOOMERANG, Item.MAGICAL_BOOMERANG, Item.LADDER,
                     Item.WAND, Item.BOW, Item.RED_RING, Item.MAGICAL_KEY, Item.RED_CANDLE, Item.SILVER_ARROWS,
                     Item.BOOK)
# The fifteen tracked item types (PS-ITW-02 step 1): the twelve and the three special-cave items
TRACKED_ITEMS = frozenset({*PROGRESSION_ITEMS, Item.POWER_BRACELET, Item.WHITE_SWORD, Item.HEART_CONTAINER})
LEVELS = range(1, 10)
# How the within finals end a boss-form text naming the heart container
REFERENCE_BOSS_FORM_ENDING = "WITH THE HEART CONTAINER"


def hearts_per_level(gw: GameWorld) -> tuple[int, ...]:
    """PS-ITW-01: heart containers in each level's rooms and item cellars, levels 1-9."""
    counts = Counter(place for place in item_places(gw).get(Item.HEART_CONTAINER, []) if place != CAVE_SLOT)
    return tuple(counts[level] for level in LEVELS)


def _per_level_text(values: list[tuple[int, ...]]) -> str:
    """Per level, how many ROMs hold one heart / two (level 9: none / one)."""
    parts = []
    for index, level in enumerate(LEVELS):
        counts = Counter(value[index] for value in values)
        keys = (0, 1) if level == 9 else (1, 2)
        parts.append(f"L{level} " + "/".join(str(counts[key]) for key in keys))
    return ", ".join(parts)


HEARTS_PER_LEVEL = Summary(_per_level_text, lambda value: {
    f"L{level} {count}": float(value[index] == count)
    for index, level in enumerate(LEVELS) for count in ((0, 1) if level == 9 else (1, 2))})


def heart_in_cave_slot(gw: GameWorld) -> bool:
    """PS-ITW-01: a special-cave slot holds a heart container."""
    return Item.HEART_CONTAINER in special_cave_items(gw)


def progression_in_cave_slots(gw: GameWorld) -> int:
    """PS-ITW-01: how many of the twelve progression classes end in a special-cave slot."""
    cave_items = set(special_cave_items(gw))
    return sum(item in cave_items for item in PROGRESSION_ITEMS)


def tracked_in_levels(gw: GameWorld) -> int:
    """PS-ITW-02: tracked item types and heart containers in level rooms and level cellars."""
    places = item_places(gw)
    return sum(1 for item in TRACKED_ITEMS for place in places.get(item, []) if place != CAVE_SLOT)


def hearts_in_cellars(gw: GameWorld) -> tuple[int, int]:
    """PS-ITW-03: (heart containers in an item cellar of a level, heart containers in levels)."""
    in_cellars = 0
    for block in gw.level_blocks:
        for cell in block.cells:
            if (isinstance(cell, StaircaseRoom) and cell.room_type == RoomType.ITEM_STAIRCASE
                    and cell.item == Item.HEART_CONTAINER and cell.return_dest is not None
                    and block.owner_of(cell.return_dest) is not None):
                in_cellars += 1
    return in_cellars, sum(hearts_per_level(gw))


def _flat_text(text: str) -> str:
    """A hint text as one line of words: line breaks and the centring blanks dropped."""
    return " ".join(text.replace("~", " ").replace("|", " ").split())


def boss_form_names_heart(gw: GameWorld) -> bool:
    """PS-ITW-05: a boss-form requirement text (HT-HINT-01 rule 5) names the heart container. Two
    wordings: ZORA's item-location sentence ("... HEART CONTAINER HIDES IN LEVEL-3.", with or
    without an opener) and the within finals' ("<boss label> <verb> WITH THE HEART CONTAINER",
    the only reference text that ends so)."""
    sentences = [item_location_sentence(Item.HEART_CONTAINER, level) for level in range(1, 9)]
    texts = [_flat_text(quote.text) for quote in gw.quotes]
    return any(text.endswith(REFERENCE_BOSS_FORM_ENDING) or any(sentence in text for sentence in sentences)
               for text in texts)
