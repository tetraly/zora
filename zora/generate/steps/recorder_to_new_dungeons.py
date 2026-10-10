"""Recorder To New Dungeons (B01; OW-WARP-01): each dungeon's recorder warp."""

from ...model.overworld import Overworld
from .cave_entries import CaveShuffle

RECORDER_DUNGEONS = range(1, 9)
# OW-WARP-01's exceptions
RECORDER_SCREEN_14 = 14
RECORDER_SCREEN_14_STORED = 29       # (14 - 1) + 16
TELEPORT_Y_DEFAULT = 0x8D
TELEPORT_YS = ((frozenset({82, 92, 109, 114}), 0x5D),
               (frozenset({9, 16, 17, 110, 117, 118, 121}), 0x7D),
               (frozenset({10, 11, 44, 57, 60, 66, 67}), 0xAD))


def recorder_bytes(entry_door: int) -> tuple[int, int]:
    """OW-WARP-01: (WhirlwindPrevRoomIdList byte, TeleportYs byte)."""
    previous = RECORDER_SCREEN_14_STORED if entry_door == RECORDER_SCREEN_14 else entry_door - 1
    drop_y = next((drop_row for screens, drop_row in TELEPORT_YS if entry_door in screens), TELEPORT_Y_DEFAULT)
    return previous, drop_y


def recorder_to_new_dungeons(overworld: Overworld, caves: CaveShuffle) -> None:
    """OW-WARP-01: each of dungeons 1-8 warps to its entry door; no draws."""
    pairs = [recorder_bytes(caves.entry_door(dungeon)) for dungeon in RECORDER_DUNGEONS]
    overworld.recorder_warp_destinations = [previous for previous, _ in pairs]
    overworld.recorder_warp_y_coordinates = [drop_row for _, drop_row in pairs]
