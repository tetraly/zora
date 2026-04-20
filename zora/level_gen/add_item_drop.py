"""Add an item drop to a dungeon room.

Reads the room's screen type from Table 3 (EnemyData), looks it up in
a table of known screen types, and if found (and room % 3 != 0),
scans the level's sentinel area for matching sentinel bytes. Writes
the item drop type and position to DoorData (Table 4) and RoomFlags
(Table 5).

Ported line-by-line from Module.cs:20698 (newLevelAddItemDrop).
No separate .cs file exists for this function — Module.cs is the
sole source.
"""

from __future__ import annotations

from zora.level_gen.rom_buffer import LevelGrid

# Each entry: [screen_type_id, sentinel_value_1, sentinel_value_2, ...]
# Indexed lookup table — search entry[0] for the room's screen type.
_ITEM_DROP_TABLE: list[list[int]] = [
    [0, 135, 137, 153, 172],
    [2, 135, 137, 200],
    [3, 137, 153, 201],
    [4, 137, 201],
    [5, 44, 220],
    [6, 137],
    [8, 137],
    [10, 137],
    [12, 136],
    [13, 172, 214],
    [14, 137],
    [15, 137],
    [17, 137],
    [18, 138, 214, 220],
    [19, 137, 138],
    [20, 137, 138],
    [21, 135, 136, 138],
    [22, 136, 137],
    [23, 137, 138],
    [24, 137, 138, 200],
    [25, 137],
    [27, 137],
    [28, 214],
    [29, 137, 138, 201],
    [30, 38, 214],
    [31, 201],
    [35, 137],
    [36, 135, 137],
    [37, 137],
    [38, 137],
    [40, 137],
    [41, 137],
    [90, 214],
    [99, 137],
]


def new_level_add_item_drop(
    rom: bytearray,
    room: int,
    level_grid: LevelGrid,
) -> None:
    # Get room's level from level_grid
    room_level = level_grid[room // 16][room % 16]

    # DoorData base offset (Table 4): 100624 for levels 1-6, 101392 for levels 7-9
    door_data_base = 100624
    if room_level > 6:
        door_data_base = 101392

    # Read screen type from Table 3 (EnemyData), which is 128 bytes before DoorData
    screen_type = rom[door_data_base + room - 128] & 0x7F

    # Search table for matching screen type
    matched_idx = -1
    for i in range(len(_ITEM_DROP_TABLE)):
        if _ITEM_DROP_TABLE[i][0] == screen_type:
            matched_idx = i
            break

    if matched_idx < len(_ITEM_DROP_TABLE) and matched_idx >= 0 and room % 3 != 0:
        # Scan sentinel area for matching sentinel values
        level_sentinel_base = room_level * 252 + 103225
        matches: list[int] = []

        entry = _ITEM_DROP_TABLE[matched_idx]
        for sentinel_idx in range(1, len(entry)):
            for pos in range(4):
                if rom[level_sentinel_base + pos] == entry[sentinel_idx]:
                    matches.append(pos)

        if len(matches) > 0:
            pos_val = matches[0]
            rom[door_data_base + room] = 25
            rom[door_data_base + room + 128] &= 0x0F
            rom[door_data_base + room + 128] = (pos_val << 4) | (rom[door_data_base + room + 128] & 0x0F)
        else:
            rom[door_data_base + room] = 3
            flag_byte = rom[door_data_base + room + 128]
            if (flag_byte & 0x0F) == 7:
                rom[door_data_base + room + 128] = flag_byte & 0xF9
    else:
        rom[door_data_base + room] = 3
        flag_byte = rom[door_data_base + room + 128]
        if (flag_byte & 0x0F) == 7:
            rom[door_data_base + room + 128] = flag_byte & 0xF9
