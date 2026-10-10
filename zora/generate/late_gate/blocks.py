"""The staged blocks as the gate works on them, and the room helpers its steps share."""

from dataclasses import dataclass, field
from typing import cast

from ...model.enums import BossSound, Item, ItemPosition, RoomAction
from ...model.levels import LEVEL_9, Level, LevelBlock
from ...model.rooms import ItemInfo, LayoutInfo, Room, SecretInfo, StaircaseRoom
from ..shapes.world import blocks_of

LEVELS_7_TO_9 = (7, 8, 9)


@dataclass
class GateBlock:
    """One of the pass's two staged blocks as the gate works on it: its
    levels, and the rooms any of them owns."""
    block: LevelBlock
    levels: list[Level]
    owned_set: frozenset[int] = field(init=False)
    # The gate moves contents between rooms and never replaces a cell, so
    # these stay valid for the whole gate.
    owned_rooms: list[Room] = field(init=False)      # in room order
    staircases: list[StaircaseRoom] = field(init=False)

    def __post_init__(self) -> None:
        owned = sorted(room for level in self.levels for room in level.room_nums)
        self.owned_set = frozenset(owned)
        self.owned_rooms = [self.block.room(room_num) for room_num in owned]
        self.staircases = self.block.staircases

    def room(self, room_num: int) -> Room:
        return self.block.room(room_num)

    @property
    def level9(self) -> Level | None:
        return next((level for level in self.levels if level.level_num == LEVEL_9), None)


def gate_blocks(levels: list[Level]) -> list[GateBlock]:
    """The levels grouped by the block they share, in level order."""
    in_order = sorted(levels, key=lambda level: level.level_num)
    return [GateBlock(block, [level for level in in_order if level.block is block])
            for block in blocks_of(levels)]
NO_ITEM = ItemInfo(Item.NOTHING)                                         # item byte $03
GANON_ITEM = ItemInfo(Item.TRIFORCE_OF_POWER, BossSound.NONE, True)      # item byte $8E
# VA-REJ-03 step 5: a room walled off around Zelda's gets the whole trigger byte $03
LAST_BOSS_SECRET = SecretInfo(RoomAction.LAST_BOSS, ItemPosition.POSITION_A)


def _room_table(block: LevelBlock) -> list[Room]:
    """The block's cells, indexed by room number, for reading rooms a level
    owns. Fast-pathed: LevelBlock.room checks the cell's type on every call,
    and the gate asks millions of times a seed; an owned room number always
    holds a Room, so the check is skipped here."""
    return cast("list[Room]", block.cells)


def _rooms(level: Level) -> list[Room]:
    """The level's rooms in grid order (Level.rooms without the type checks)."""
    table = _room_table(level.block)
    return [table[room_num] for room_num in level.room_nums]


def _set_trigger(room: Room, trigger: RoomAction) -> None:
    """Write the trigger, keeping the item position."""
    room.secret_info = SecretInfo(trigger, room.secret_info.item_position)


def _clear_push_block(room: Room) -> None:
    room.layout_info = LayoutInfo(room.layout_info.room_type, False)
