"""VA-REJ-20: after the gate, level 9's last-boss shutter rooms keep only small items.

The rooms on the last-boss trigger (3) open only once Ganon is beaten: Ganon's room and the
neighbours that face Zelda with a shutter (VA-REJ-03 step 8). Any item there other than a key,
bombs, five rupees or (in Ganon's room) the Triforce of Power moves over the small item of a
random other level-9 room; that small item is lost. Runs once per pass, after the start-screen
pass and before the map move (SH-MAP-05 may still put the map behind those shutters).
"""
from ...model.enums import Item, RoomAction
from ...model.levels import Level
from ...model.rooms import Room
from ..errors import GenerationFailure
from ..rng import IntRng, discard

LEADING_DISCARDS = 3
SMALL_ITEMS = frozenset({Item.KEY, Item.BOMBS, Item.FIVE_RUPEES})
STAYING_ITEMS = SMALL_ITEMS | {Item.NOTHING, Item.TRIFORCE_OF_POWER}
NO_CANDIDATE_FAILURE = "VA-REJ-20: no level-9 room to take a last-boss room's item"


def is_last_boss_room(room: Room) -> bool:
    """A room on the last-boss trigger (3): its item stays hidden until Ganon is beaten
    (CreateRoomObjects), so VA-REJ-20 empties it of everything but small items. The item places
    (zora/generate/places.py) leave these rooms out by this same rule."""
    return room.room_action == RoomAction.LAST_BOSS


def receiving_rooms(level9: Level) -> list[Room]:
    """The rooms that may take a displaced item: a small item, not on the last-boss trigger,
    listed from room 127 down to room 0 (the order the draw indexes)."""
    return [room for room in sorted(level9.rooms, key=lambda room: room.room_num, reverse=True)
            if room.item in SMALL_ITEMS and not is_last_boss_room(room)]


def move_last_boss_room_items(level9: Level, rng: IntRng) -> None:
    """VA-REJ-20: visit level 9's rooms in room order; move each disallowed item out of a
    last-boss-trigger room over a random small item. No candidate restarts the pass.

    Only the item bits move: each room keeps its dark and boss-sound bits and its trigger.
    The second-quest copy of the block is skipped, as the spec allows (its only trigger-3 room
    holds the Triforce of Power, so nothing would move there)."""
    discard(rng, LEADING_DISCARDS)
    for room in sorted(level9.rooms, key=lambda room: room.room_num):
        if not is_last_boss_room(room) or room.item in STAYING_ITEMS:
            continue
        displaced, room.item = room.item, Item.NOTHING
        candidates = receiving_rooms(level9)
        if not candidates:
            raise GenerationFailure(NO_CANDIDATE_FAILURE)
        # Quirk (VA-REJ-20): the receiving room's small item is overwritten, not moved; level 9
        # ends with one item fewer.
        candidates[rng.below(len(candidates))].item = displaced
