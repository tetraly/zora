"""Recorder (whistle) destinations: where the whirlwind drops Link for
each of levels 1-8 (read-only).

UpdateWhirlwind_Full (Z_01.asm): with TeleportingLevelIndex's low three
bits as the index, WhirlwindPrevRoomIdList gives the room that acts as the
previous room while the screen scrolls right into the destination, so the
destination is that room + 1. DestroyWhirlwind then drops Link at
TeleportYs[index]. SummonWhirlwind picks the index from the triforce
pieces held, through LevelMasks (index i is level i + 1).
"""
from dataclasses import dataclass

from zora.rom.vanilla_overworld.tables import RECORDER_LEVELS, TELEPORT_YS, WHIRLWIND_PREV_ROOM_ID_LIST

SCROLL_RIGHT_STEP = 1             # the destination is one room right of the "previous" room


@dataclass(frozen=True)
class RecorderDestination:
    level: int                    # 1-8
    previous_room: int            # WhirlwindPrevRoomIdList entry
    drop_y: int                   # TeleportYs entry

    @property
    def room(self) -> int:
        return self.previous_room + SCROLL_RIGHT_STEP


def read_recorder_destinations(rom: bytes) -> list[RecorderDestination]:
    rooms = WHIRLWIND_PREV_ROOM_ID_LIST.read(rom)
    ys = TELEPORT_YS.read(rom)
    return [RecorderDestination(index + 1, rooms[index], ys[index]) for index in range(RECORDER_LEVELS)]
