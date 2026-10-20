"""Allow Triforces in Stairways (ZORA flag allow_triforces_in_stairways; owner design, 2026-10-17,
redesigned 2026-10-18; docs/zora-extras.md section 13): before the item shuffle, each Triforce of
levels 1-8 picks its spot uniformly among its own level's item spots, and the shuffle then runs
over everything else, whatever Item Shuffle is set to.

A level's item spots are its rooms and item cellars that hold a major item when the shuffle starts
(one of the twelve progression items or a heart container), and the Triforce's own room, so it
may stay. The Triforce and the spot's item trade places, so the old Triforce room holds that item
and is an ordinary item spot for the shuffle (which finds its places by what they hold), and the
Triforce, never a pool item, stays where it landed: it never leaves its level. Only the item
moves: each room keeps its own boss sound and darkness (an owner design, not the spec's whole-byte
moves). Level 9 has no Triforce (the Triforce of Power never moves).

The compass points at the room with a cellar's stairs (serialize.levels.derive_triforce_room_ptr),
and the logic finds the Triforce in a room or an item cellar (AcceptanceCheck._can_reach_item)."""
from dataclasses import dataclass, replace

from ...model.enums import Item, RoomType
from ...model.levels import Level
from ...model.rooms import Room, StaircaseRoom
from ..rng import IntRng
from .dungeon_quest import SET_LEVELS
from .item_shuffle_result import ItemShuffleResult
from .move_last_boss_room_items import is_last_boss_room
from .shuffle_items import POOL_ORDER

TRIFORCE_LEVELS = range(1, 9)
# The major items a spot holds when the shuffle starts
SPOT_ITEMS = frozenset({*(Item(code) for code in POOL_ORDER), Item.HEART_CONTAINER})


@dataclass(frozen=True)
class Spot:
    """A room of the level, or an item cellar returning to one of its rooms."""
    room: Room | None = None
    cellar: StaircaseRoom | None = None

    @property
    def cell(self) -> int:
        cell = self.room if self.room is not None else self.cellar
        assert cell is not None
        return cell.room_num

    @property
    def item(self) -> Item | None:
        return self.room.item if self.room is not None else self.cellar.item if self.cellar is not None else None

    def put(self, item: Item) -> None:
        if self.room is not None:
            self.room.item_info = replace(self.room.item_info, item=item)
        else:
            assert self.cellar is not None
            self.cellar.item = item


def triforce_room(level: Level) -> Room | None:
    return next((room for room in level.rooms if room.item == Item.TRIFORCE), None)


def item_spots(level: Level, own_room: Room) -> list[Spot]:
    """The Triforce's own room, then the level's rooms in room order, then its item cellars in
    cell order, each holding a major item (never a room on the last-boss trigger)."""
    rooms = sorted((room for room in level.rooms if room.item in SPOT_ITEMS and not is_last_boss_room(room)),
                   key=lambda room: room.room_num)
    cellars = sorted((stair for stair in level.block.staircases
                      if stair.room_type == RoomType.ITEM_STAIRCASE and stair.item in SPOT_ITEMS
                      and stair.return_dest in level.room_nums), key=lambda stair: stair.room_num)
    return [Spot(room=own_room), *(Spot(room=room) for room in rooms), *(Spot(cellar=stair) for stair in cellars)]


def set_index_of(level: Level) -> int:
    return next(index for index, numbers in enumerate(SET_LEVELS) if level.level_num in numbers)


def place_triforces(levels: list[Level], state: ItemShuffleResult, rng: IntRng) -> None:
    """Each Triforce of levels 1-8, in level order, trades places with one spot drawn uniformly from
    its level's item spots (one draw per level). state.triforce_origins records each trade as
    (set index, spot cell) -> the old Triforce room, for the vanilla sets' fixed progression places
    (PS-VAN-03), which then stand at the old Triforce room."""
    for level in sorted(levels, key=lambda level: level.level_num):
        own_room = triforce_room(level) if level.level_num in TRIFORCE_LEVELS else None
        if own_room is None:
            continue
        spots = item_spots(level, own_room)
        spot = spots[rng.below(len(spots))]
        if spot.room is own_room:
            continue
        item = spot.item
        assert item is not None
        spot.put(Item.TRIFORCE)
        Spot(room=own_room).put(item)
        state.triforce_origins[set_index_of(level), spot.cell] = own_room.room_num
