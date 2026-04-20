"""Remap dungeon map screen types for levels 1-9.

For each level, performs a BFS from the dungeon entrance through the level
graph to find rooms whose screen type (low 5 bits of the door-data byte)
matches one of {0, 15, 22, 23, 25}.  Picks a candidate weighted by
Manhattan distance to the entrance, finds a "neutral" room (screen type 23)
belonging to the same level, and swaps their door-data bytes.  May also
randomize the enemy-column byte of the destination room.

Ported line-by-line from RemapMaps.cs (remapMaps, Module.cs:36432).
Cross-referenced against Module.cs:36432-36972.
"""

from __future__ import annotations

from collections import deque
from typing import Callable

from zora.level_gen.rom_buffer import (
    ROMOFS_DOOR_DATA,
    ROMOFS_ENTRANCE_DATA,
    ROMOFS_SCREEN_LAYOUT,
    signed_byte,
)
from zora.rng import Rng

_SCREEN_TYPES_TO_REMAP = [0, 15, 22, 23, 25]

BuildGraphFn = Callable[
    [bytearray, int, int, int, bool],
    list[list[int]],
]


def remap_maps(
    rom: bytearray,
    rng: Rng,
    quest_variants: list[int],
    room_type_mapping: list[list[int]],
    build_graph: BuildGraphFn,
) -> None:
    """Remap screen types across all 9 levels.

    Parameters
    ----------
    rom : bytearray
        The full ROM buffer (iNES header included).
    rng : Rng
        RNG with ``next()`` returning uint64.
    quest_variants : list[int]
        Per-level quest variant (index 0 unused, indices 1-9).
    room_type_mapping : list[list[int]]
        Room-to-level mapping.  Index = baseOffset // 768:
        0 = Q1 levels 1-6, 1 = Q1 levels 7-9, 2 = Q2 levels 1-6,
        3 = Q2 levels 7-9.  Each sub-list has 128 entries (room →
        level number).
    build_graph : BuildGraphFn
        ``build_level_graph_with_inventory(rom, level, quest,
        inventory, ohko)`` → graph.  graph[room][0] is a direction
        bitmask; graph[room][1..5] are neighbor room indices.
    """
    # sodiumRand::seed is a no-op; two RNG advances follow it.
    rng.next()
    rng.next()

    for level in range(1, 10):
        quest = quest_variants[level] if level < len(quest_variants) else 1

        dir_adjust = 0
        if quest == 2:
            if level in (2, 4, 7):
                dir_adjust = 1
            elif level in (3, 5, 8):
                dir_adjust = -1

        base_offset = 0
        if quest == 2:
            base_offset = 1536  # 0x600
        if level > 6:
            base_offset += 768  # 0x300

        screen_layout_addr = base_offset + ROMOFS_SCREEN_LAYOUT  # num5
        door_conn_addr = screen_layout_addr + 128                # num6
        door_data_addr = base_offset + ROMOFS_DOOR_DATA          # num7

        entrance_rom_addr = (dir_adjust + level) * 252 + ROMOFS_ENTRANCE_DATA
        entrance_screen = signed_byte(rom[entrance_rom_addr])

        graph = build_graph(rom, level, quest, 1, False)

        graph_node_count = len(graph)  # 128

        # visited[room][direction]: indices 0-5 (0 unused, 1-5 = directions).
        visited = [[False] * 6 for _ in range(graph_node_count)]

        candidates: list[int] = []
        bfs_deque: deque[tuple[int, int, int]] = deque()  # (depth, room, direction)

        first_depth = -1
        max_depth = 1000

        if 0 <= entrance_screen < graph_node_count:
            visited[entrance_screen][2] = True

        bfs_deque.appendleft((0, entrance_screen, 2))

        while bfs_deque:
            depth, room, direction = bfs_deque.popleft()

            if depth > max_depth:
                continue

            door_data_byte = signed_byte(rom[room + door_data_addr])
            screen_type = (door_data_byte + 256 if door_data_byte < 0 else door_data_byte) & 0x1F

            if screen_type in _SCREEN_TYPES_TO_REMAP:
                if first_depth == -1:
                    first_depth = depth
                    max_depth = depth
                candidates.append(room)

            for dir_ in range(1, 6):
                dir_bit_index = direction * 5 + dir_
                if (graph[room][0] & (1 << dir_bit_index)) == 0:
                    continue

                if dir_ == 1:
                    opposite_dir = 2
                elif dir_ == 2:
                    opposite_dir = 1
                elif dir_ == 3:
                    opposite_dir = 4
                elif dir_ == 4:
                    opposite_dir = 3
                else:
                    opposite_dir = 5

                neighbor = graph[room][dir_]
                if neighbor < 0 or neighbor >= graph_node_count:
                    continue
                if visited[neighbor][opposite_dir]:
                    continue
                if graph[neighbor][0] == -1:
                    continue

                group_idx = base_offset // 768
                if group_idx < len(room_type_mapping):
                    rtl = room_type_mapping[group_idx]
                    if neighbor < len(rtl) and rtl[neighbor] != level:
                        continue

                visited[neighbor][opposite_dir] = True

                if dir_ in (1, 2):
                    conn_byte = signed_byte(rom[room + screen_layout_addr])
                    conn_byte = (conn_byte + 256 if conn_byte < 0 else conn_byte) >> 2
                    conn_byte = (conn_byte >> 3) if dir_ == 1 else (conn_byte & 7)
                elif dir_ in (3, 4):
                    conn_byte = signed_byte(rom[room + door_conn_addr])
                    conn_byte = (conn_byte + 256 if conn_byte < 0 else conn_byte) >> 2
                    conn_byte = (conn_byte >> 3) if dir_ == 3 else (conn_byte & 7)
                else:
                    conn_byte = 0

                if conn_byte == 4 or conn_byte == 2:
                    bfs_deque.append((depth + 1, neighbor, opposite_dir))
                else:
                    bfs_deque.appendleft((depth, neighbor, opposite_dir))

        candidate_count = len(candidates)
        if candidate_count == 0:
            continue

        entrance_row = entrance_screen >> 4
        entrance_col = entrance_screen & 0xF

        distances = [0] * candidate_count
        total_dist = 0
        for i in range(candidate_count):
            c_room = candidates[i]
            c_row = c_room >> 4
            c_col = c_room & 0xF
            distances[i] = abs(entrance_col - c_col) + abs(entrance_row - c_row)
            total_dist += distances[i]

        if total_dist == 0:
            continue

        pick = rng.next() % total_dist
        chosen = -1
        while True:
            chosen += 1
            pick -= distances[chosen]
            if pick <= 0:
                break

        group_idx = base_offset // 768
        room_type_list = (
            room_type_mapping[group_idx]
            if group_idx < len(room_type_mapping)
            else None
        )

        neutral_room = -1
        if room_type_list is not None:
            for r in range(min(128, len(room_type_list))):
                st_byte = signed_byte(rom[r + door_data_addr])
                st = (st_byte + 256 if st_byte < 0 else st_byte) & 0x1F
                room_level = room_type_list[r] if r < len(room_type_list) else 0
                if room_level == level and st == 23:
                    neutral_room = r
                    break

        if neutral_room < 0:
            continue

        chosen_room = candidates[chosen]
        src_door_byte = rom[chosen_room + door_data_addr]
        dest_door_byte = rom[neutral_room + door_data_addr]
        rom[neutral_room + door_data_addr] = src_door_byte
        rom[chosen_room + door_data_addr] = dest_door_byte

        enemy_col_byte = signed_byte(rom[door_data_addr + chosen_room + 128])
        enemy_col = (enemy_col_byte + 256 if enemy_col_byte < 0 else enemy_col_byte) & 7

        if rng.next() % 5 > 0 and (enemy_col == 0 or enemy_col == 1):
            rom[door_data_addr + chosen_room + 128] = rom[door_data_addr + chosen_room + 128] | 7
