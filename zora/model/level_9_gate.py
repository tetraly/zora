"""What level 9's entrance asks for (features-behavior.md FP-TRIF-01 to FP-TRIF-06): any number of
Triforce pieces, nothing, the pieces of chosen levels, or an item. The generation step
(zora/generate/steps/level_9_entry.py) decides it in each pass, the acceptance check judges by it,
and the serializer writes it (zora/rom/level_9_entrance.py)."""
from dataclasses import dataclass
from enum import Enum

from .enums import Item

ALL_PIECES = 8
TRIFORCE_LEVELS = range(1, ALL_PIECES + 1)


class GateKind(Enum):
    PIECES = "pieces"        # FP-TRIF-01, FP-TRIF-02, FP-TRIF-04: any `pieces` of the eight
    OPEN = "open"            # FP-TRIF-03: nothing
    LEVELS = "levels"        # FP-TRIF-05: the pieces of every level in `levels`
    ITEM = "item"            # FP-TRIF-06: `item` held


# FP-TRIF-06's items, as the owner ruled for ZORA (2026-10-22; docs/deviations.md): never the
# letter. The gate tests one inventory byte, so a sword stands for any sword, a candle for either,
# an arrow for either.
GATE_ITEMS = (Item.WOOD_SWORD, Item.RECORDER, Item.BLUE_CANDLE, Item.WOOD_ARROWS, Item.BOW, Item.MAGICAL_KEY,
              Item.RAFT, Item.LADDER, Item.WAND, Item.BOOK, Item.POWER_BRACELET)


@dataclass(frozen=True)
class Level9Gate:
    kind: GateKind = GateKind.PIECES
    pieces: int = ALL_PIECES
    levels: frozenset[int] = frozenset()
    item: Item | None = None

    @property
    def is_eight_pieces(self) -> bool:
        """PRG0's gate (FP-TRIF-01): the ROM keeps PRG0's own check."""
        return self == EIGHT_PIECES


EIGHT_PIECES = Level9Gate()
OPEN_GATE = Level9Gate(GateKind.OPEN, pieces=0)


def pieces_gate(pieces: int) -> Level9Gate:
    return Level9Gate(GateKind.PIECES, pieces=pieces)


def levels_gate(levels: frozenset[int]) -> Level9Gate:
    return Level9Gate(GateKind.LEVELS, pieces=len(levels), levels=levels)


def item_gate(item: Item) -> Level9Gate:
    return Level9Gate(GateKind.ITEM, pieces=0, item=item)
