"""The monster passes' shared pieces: each level's room list with its monster
values (RoomLists) and the result staged outside the room blocks."""

from dataclasses import dataclass, field

from ...model.levels import LevelBlock
from ...model.rooms import MONSTER_LIST_BITS, MONSTER_VALUE_BIT, Room, RoomPlace
from ..shapes.world import SetWorld

# --- monster values ------------------------------------------------------------

MONSTER_BYTE_MASK = 0xFF
BOSS_FLAG = 0x40                 # the monster bit in a boss code ($43 = flagged $03)


def _low_six(value: int) -> int:
    return value & MONSTER_LIST_BITS


def _has_monster_bit(value: int) -> bool:
    return bool(value & MONSTER_VALUE_BIT)


def _byte(value: int) -> int:
    """The whole monster byte, without the monster bit."""
    return value & MONSTER_BYTE_MASK


def _boss_value(code: int) -> int:
    """A boss code ($40 = monster bit) as the value a boss write leaves:
    low six bits, count bits 0, monster bit from $40 (PS-BOSS-02)."""
    return _low_six(code) | (MONSTER_VALUE_BIT if code & BOSS_FLAG else 0)


def _boss_code(value: int) -> int:
    """PS-BOSS-03's view of a room: low six bits plus $40 for the monster
    bit, count bits ignored."""
    return _low_six(value) | (BOSS_FLAG if _has_monster_bit(value) else 0)


# --- room lists ----------------------------------------------------------------



@dataclass
class RoomLists:
    """Each level's room list with the monster values the B2 passes work
    on. Built at the end of the shape stage; person rooms are not in the
    lists (PS-DROP-01's builder drops flagged 11-18 rooms)."""
    rooms: dict[int, list[RoomPlace]] = field(default_factory=dict)   # level -> places
    values: dict[RoomPlace, int] = field(default_factory=dict)


def build_room_lists(worlds: list[SetWorld]) -> RoomLists:
    """The lists as they stand at the end of the shape stage, rooms in cell
    order (QUESTIONS #45.3). Values are not refreshed from later B1 moves
    (QUESTIONS #58.3): the only B1 move of a listed monster is the goriya
    swap, and a refreshed list would shuffle the arriving person out of its
    room, which no corpus person room shows."""
    lists = RoomLists()
    for block_index, world in enumerate(worlds):
        for blob, level in sorted(world.levels.items()):
            places = [RoomPlace(block_index, room_number) for room_number in sorted(world.cells_by_blob[blob])
                      if not world.plans[room_number].is_person]
            lists.rooms[level] = places
            lists.values.update({place: world.plans[place.room_number].monster_value for place in places})
    return lists


@dataclass
class MonsterShuffleResult:
    """What the passes decided outside the two room blocks."""
    boss_tiers: dict[int, int] = field(default_factory=dict)    # level -> boss bank tier
    enemy_tiers: dict[int, int] = field(default_factory=dict)   # level -> enemy bank tier
    goriya_tile: int | None = None       # PS-MONLV-06's ObjAnimFrameHeap+171 value
    rebossed: int = 0
    redrawn: int = 0
    redeal_draws: int = 0


def _room_at(blocks: list[LevelBlock], place: RoomPlace) -> Room:
    return blocks[place.block].room(place.room_number)
