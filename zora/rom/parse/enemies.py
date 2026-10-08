"""Enemies: the mixed groups, tile mappings and hit points."""

from zora.model.enums import Enemy
from zora.model.rooms import EnemySpec
from zora.model.sprites import EnemyData
from zora.rom.layout import (
    BOSS_HP_FIRST_ENEMY_VALUE,
    BOSS_HP_NIBBLE_COUNT,
    ENEMY_HP_NIBBLE_COUNT,
    FIRST_MIXED_GROUP_CODE,
    POINTER_COUNT,
)
from zora.rom.parse.bin_files import RawBinFiles

# ---------------------------------------------------------------------------
# Mixed enemy group parsing
# ---------------------------------------------------------------------------

def _parse_mixed_enemy_groups_from_bytes(
    mixed_enemy_data: bytes,
    mixed_enemy_pointers: bytes,
) -> dict[int, EnemySpec]:
    """Returns a dict mapping enemy code (0x62-0x7F) → EnemySpec."""
    groups: dict[int, EnemySpec] = {}
    cpu_addrs = [
        mixed_enemy_pointers[i*2] | (mixed_enemy_pointers[i*2+1] << 8)
        for i in range(POINTER_COUNT)
    ]
    min_cpu = min(cpu_addrs)
    for i in range(POINTER_COUNT):
        code = FIRST_MIXED_GROUP_CODE + i
        cpu_addr = cpu_addrs[i]
        data_offset = cpu_addr - min_cpu
        member_bytes = mixed_enemy_data[data_offset:data_offset + 8]
        members = [Enemy(b) for b in member_bytes]
        groups[code] = EnemySpec(
            enemy=Enemy(code),
            is_group=True,
            group_members=members,
        )
    return groups


def _parse_mixed_enemy_groups(bins: RawBinFiles) -> dict[int, EnemySpec]:
    return _parse_mixed_enemy_groups_from_bytes(
        bins.mixed_enemy_data, bins.mixed_enemy_pointers,
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Enemy tile mapping parse
# ---------------------------------------------------------------------------

# Enemy enum values that have tile table entries, in ROM slot order (slot = enemy_id + 1).
_TILE_TABLE_ENEMIES: list[Enemy] = sorted(
    [e for e in Enemy if e.value <= 0x52],
    key=lambda e: e.value,
)
_OVERWORLD_NPC_SLOT_COUNT = 43   # slots 0x54-0x7E
_TILE_MAPPING_POINTERS_TOTAL = 0x7F   # total slots in the pointer table


def _parse_enemy_tile_data(ptr_bytes: bytes, frame_bytes: bytes) -> "EnemyData":
    """Parse the flat tile mapping tables into structured EnemyData fields.

    ptr_bytes  — 0x7F bytes at ROM 0x6E14: one pointer (frame buffer index) per slot.
    frame_bytes — 0xCC bytes at ROM 0x6E93: tile codes for all animation frames.

    Slot layout:
      slot 0          = player (Link)
      slots 1-0x53    = Enemy enum values 0x00-0x52 (slot = enemy_id + 1)
      slots 0x54-0x7E = overworld NPC sprite variants (43 entries)

    Frame list length for a pointer p = (next higher unique pointer value) - p.
    Multiple slots may share the same pointer; the frame list length is determined
    by sorted unique pointer values, not by adjacent slot order.
    """
    # Build a lookup: pointer value -> tile list, using sorted unique pointer values.
    unique_ptrs = sorted(set(ptr_bytes))
    ptr_to_tiles: dict[int, list[int]] = {}
    for i, p in enumerate(unique_ptrs):
        end = unique_ptrs[i + 1] if i + 1 < len(unique_ptrs) else len(frame_bytes)
        ptr_to_tiles[p] = list(frame_bytes[p:end])

    # Slot 0: player
    player_pointer = ptr_bytes[0]
    player_tiles   = ptr_to_tiles[player_pointer]

    # Slots 1-0x53: enemy enum entries
    tile_pointers: dict[Enemy, int]        = {}
    tile_frames:   dict[Enemy, list[int]]  = {}
    for enemy in _TILE_TABLE_ENEMIES:
        slot = enemy.value + 1
        tile_pointers[enemy] = ptr_bytes[slot]
        tile_frames[enemy]   = ptr_to_tiles[ptr_bytes[slot]]

    # Slots 0x54-0x7E: overworld NPC sprite variants
    overworld_npc_pointers: list[int]         = []
    overworld_npc_frames:   list[list[int]]   = []
    for i in range(_OVERWORLD_NPC_SLOT_COUNT):
        slot = 0x54 + i
        overworld_npc_pointers.append(ptr_bytes[slot])
        overworld_npc_frames.append(ptr_to_tiles[ptr_bytes[slot]])

    return EnemyData(
        player_pointer          = player_pointer,
        player_tiles            = player_tiles,
        tile_pointers           = tile_pointers,
        tile_frames             = tile_frames,
        overworld_npc_pointers  = overworld_npc_pointers,
        overworld_npc_frames    = overworld_npc_frames,
    )


def _read_hp_nibble(table: bytes, nibble_index: int) -> int:
    """Read a single HP nibble from a packed byte table.

    Even indices are stored in the high nibble, odd indices in the low nibble.
    """
    byte_val = table[nibble_index >> 1]
    if nibble_index & 1 == 0:
        return (byte_val >> 4) & 0x0F
    return byte_val & 0x0F


def _parse_enemy_hp(bins: RawBinFiles, enemies: EnemyData) -> None:
    """Populate EnemyData.hp and secondary boss HP fields from raw bin data."""
    # Enemy HP table: 52 nibbles, Enemy 0x00-0x33
    for i in range(ENEMY_HP_NIBBLE_COUNT):
        enemy_val = i
        try:
            enemy = Enemy(enemy_val)
        except ValueError:
            continue
        enemies.hp[enemy] = _read_hp_nibble(bins.enemy_hp_table, i)

    # Boss HP table: 24 nibbles, Enemy 0x34-0x4B
    for j in range(BOSS_HP_NIBBLE_COUNT):
        enemy_val = BOSS_HP_FIRST_ENEMY_VALUE + j
        try:
            enemy = Enemy(enemy_val)
        except ValueError:
            continue
        enemies.hp[enemy] = _read_hp_nibble(bins.boss_hp_table, j)

    # Secondary boss HP bytes (HP stored in high nibble)
    enemies.gleeok_neck_hp     = (bins.gleeok_neck_hp[0] >> 4) & 0x0F
    if bins.rope_hp_operands:
        enemies.rope_hp = ((bins.rope_hp_operands[0] >> 4) & 0x0F,
                           (bins.rope_hp_operands[1] >> 4) & 0x0F)
    enemies.gleeok_head_hp     = (bins.gleeok_head_hp[0] >> 4) & 0x0F
    enemies.ganon_hp           = (bins.ganon_hp[0] >> 4) & 0x0F
    enemies.moldorm_segment_hp = (bins.moldorm_segment_hp[0] >> 4) & 0x0F
    enemies.lamnola_segment_hp = (bins.lamnola_segment_hp[0] >> 4) & 0x0F

    # Boss engine sprite pointers (full bytes; written by the boss-group pass)
    enemies.aquamentus_sprite_ptr    = bins.aquamentus_sprite_ptr[0]
    enemies.gleeok_head_sprite_ptr_a = bins.gleeok_head_sprite_ptr_a[0]
    enemies.gleeok_head_sprite_ptr_b = bins.gleeok_head_sprite_ptr_b[0]
    enemies.gleeok_head_sprite_ptr_c = bins.gleeok_head_sprite_ptr_c[0]
    if bins.aquamentus_tiles:
        enemies.aquamentus_tile_layout_table = list(bins.aquamentus_tiles)
        enemies.gleeok_body_tiles = list(bins.gleeok_body_tiles)
