"""Per-level Triforce pieces, maps and compasses (docs/design/archipelago-items.md piece 6, section 4).

With either pool flag on (Add Triforces to the Item Pool, Add Maps/Compasses to the Item Pool) the ROM
is in per-level mode: each level's piece, map and compass has a code of its own, keyed by the level's
data number (`Level.level_num`, the one `CurLevel` holds), and sets that level's inventory bit wherever
it is taken. Its name uses the number the status bar shows (`Level.rom_level_num`), as place names do:
"Level 3 Map"."""
from collections.abc import Mapping
from enum import Enum

from .enums import Item


class LevelItemKind(Enum):
    TRIFORCE = "Triforce"
    MAP = "Map"
    COMPASS = "Compass"


TRIFORCE_LEVELS = range(1, 9)
MAP_COMPASS_LEVELS = range(1, 10)
LEVEL_9 = 9
LEVEL_8 = 8
LEVELS = {LevelItemKind.TRIFORCE: TRIFORCE_LEVELS, LevelItemKind.MAP: MAP_COMPASS_LEVELS,
          LevelItemKind.COMPASS: MAP_COMPASS_LEVELS}
# The generic codes stand for one level each in per-level mode: level 8's piece, level 9's map and compass
GENERIC_LEVEL = {LevelItemKind.TRIFORCE: (Item.TRIFORCE, LEVEL_8), LevelItemKind.MAP: (Item.MAP, LEVEL_9),
                 LevelItemKind.COMPASS: (Item.COMPASS, LEVEL_9)}
FIRST_CODE = {LevelItemKind.TRIFORCE: Item.TRIFORCE_1, LevelItemKind.MAP: Item.MAP_1,
              LevelItemKind.COMPASS: Item.COMPASS_1}


def level_item(kind: LevelItemKind, level: int) -> Item:
    """The code of data level `level`'s item of this kind."""
    if level not in LEVELS[kind]:
        raise ValueError(f"level {level} has no {kind.value}")
    generic, generic_level = GENERIC_LEVEL[kind]
    return generic if level == generic_level else Item(FIRST_CODE[kind] + level - 1)


LEVEL_ITEMS: dict[Item, tuple[LevelItemKind, int]] = {
    level_item(kind, level): (kind, level) for kind, levels in LEVELS.items() for level in levels}


def level_of(item: Item) -> tuple[LevelItemKind, int] | None:
    """(kind, data level) of a per-level code, the generic three included; None for any other item."""
    return LEVEL_ITEMS.get(item)


def level_item_name(kind: LevelItemKind, shown_level: int) -> str:
    """"Level N Triforce", N being the number the status bar shows."""
    return f"Level {shown_level} {kind.value}"


ALL_LEVEL_ITEM_NAMES = tuple(level_item_name(kind, level) for kind, levels in LEVELS.items() for level in levels)


def level_item_names(shown: Mapping[int, int]) -> dict[Item, str]:
    """Each per-level code's name in a seed, from its levels' shown numbers (data level -> shown)."""
    return {item: level_item_name(kind, shown[level]) for item, (kind, level) in LEVEL_ITEMS.items()}
