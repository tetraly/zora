"""The overworld's level info (LevelInfoOW, loaded to $6B7E): the fields
the overworld reads, at their LevelInfo_* labels' offsets (read-only).

  LevelInfo_FoeCounts             +$24  4 monster counts (C bits 6-7 index them)
  LevelInfo_StartY                +$28  Link's Y in the start screen
  LevelInfo_ShortcutOrItemPosArray +$29 4 shortcut positions (F bits 4-5 index them)
  LevelInfo_StartRoomId           +$2F  the start screen
  LevelInfo_CellarRoomIdArray     +$34  in the overworld: the 4 screens joined by
                                        the shortcut cave (Z_05.asm's mode $C
                                        exit: stair 1-3 goes that many entries on,
                                        wrapping over four)
Each position byte packs X in its high nibble and Y in its low nibble
(GetShortcutOrItemXYForRoom).
"""
from dataclasses import dataclass

from .tables import LEVEL_INFO_OW

FOE_COUNTS = slice(0x24, 0x28)
START_Y = 0x28
SHORTCUT_POSITIONS = slice(0x29, 0x2D)
START_ROOM_ID = 0x2F
SHORTCUT_ROOMS = slice(0x34, 0x38)


@dataclass(frozen=True)
class OverworldLevelInfo:
    foe_counts: tuple[int, ...]
    start_y: int
    shortcut_positions: tuple[int, ...]
    start_room: int
    shortcut_rooms: tuple[int, ...]


def read_level_info(rom: bytes) -> OverworldLevelInfo:
    info = LEVEL_INFO_OW.read(rom)
    return OverworldLevelInfo(tuple(info[FOE_COUNTS]), info[START_Y],
                              tuple(info[SHORTCUT_POSITIONS]), info[START_ROOM_ID],
                              tuple(info[SHORTCUT_ROOMS]))
