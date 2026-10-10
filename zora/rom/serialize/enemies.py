"""Enemies: tile mappings and hit points."""

from ...model.enums import Enemy
from ...model.game_world import GameWorld
from ..layout import (
    AQUAMENTUS_SPRITE_PTR_ADDRESS,
    AQUAMENTUS_TILE_LAYOUT_TABLE_ADDRESS,
    BOSS_HP_FIRST_ENEMY_VALUE,
    BOSS_HP_NIBBLE_COUNT,
    BOSS_HP_TABLE_ADDRESS,
    BOSS_HP_TABLE_SIZE,
    ENEMY_HP_NIBBLE_COUNT,
    ENEMY_HP_TABLE_ADDRESS,
    ENEMY_HP_TABLE_SIZE,
    GANON_HP_ADDRESS,
    GLEEOK_BODY_TILES_ADDRESS,
    GLEEOK_HEAD_HP_ADDRESS,
    GLEEOK_HEAD_SPRITE_PTR_A_ADDRESS,
    GLEEOK_HEAD_SPRITE_PTR_B_ADDRESS,
    GLEEOK_HEAD_SPRITE_PTR_C_ADDRESS,
    GLEEOK_NECK_HP_ADDRESS,
    LAMNOLA_SEGMENT_HP_ADDRESS,
    MOLDORM_SEGMENT_HP_ADDRESS,
    ROPE_HP_OPERAND_ADDRESSES,
)
from .patch import Patch

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Enemy tile mapping serialize
# ---------------------------------------------------------------------------

_TILE_TABLE_ENEMIES: list[Enemy] = sorted(
    [e for e in Enemy if e.value <= 0x52],
    key=lambda e: e.value,
)
_OVERWORLD_NPC_SLOT_COUNT       = 43    # slots 0x54-0x7E
_TILE_MAPPING_POINTERS_TOTAL    = 0x7F  # total slots in the pointer table
_TILE_MAPPING_DATA_SIZE         = 0xCC


def _serialize_enemy_tile_data(game_world: GameWorld) -> tuple[bytes, bytes]:
    """Reconstruct flat tile mapping byte arrays from structured EnemyData fields.

    Returns (ptr_bytes, frame_bytes) ready to write to ROM.

    Slot layout (ptr_bytes, 0x7F entries):
      slot 0          = player (Link)
      slots 1-0x53    = Enemy enum values 0x00-0x52
      slots 0x54-0x7E = overworld NPC sprite variants (43 entries)

    frame_bytes (0xCC bytes) is the flat buffer; each pointer is an index into it.
    Multiple enemies may share a pointer; we write each unique (pointer, tiles)
    pair once at the pointer's offset in the frame buffer.
    """
    ed = game_world.enemies

    # Build pointer table (0x7F bytes).
    ptr_buf = bytearray(_TILE_MAPPING_POINTERS_TOTAL)
    ptr_buf[0] = ed.player_pointer
    for enemy in _TILE_TABLE_ENEMIES:
        ptr_buf[enemy.value + 1] = ed.tile_pointers[enemy]
    for i in range(_OVERWORLD_NPC_SLOT_COUNT):
        ptr_buf[0x54 + i] = ed.overworld_npc_pointers[i]

    # Collect unique (pointer, tiles) pairs and write into frame buffer.
    frame_buf = bytearray(_TILE_MAPPING_DATA_SIZE)
    seen: set[int] = set()

    all_entries: list[tuple[int, list[int]]] = [
        (ed.player_pointer, ed.player_tiles),
    ]
    all_entries.extend((ed.tile_pointers[enemy], ed.tile_frames[enemy]) for enemy in _TILE_TABLE_ENEMIES)
    all_entries.extend((ed.overworld_npc_pointers[i], ed.overworld_npc_frames[i])
                       for i in range(_OVERWORLD_NPC_SLOT_COUNT))

    for ptr, tiles in all_entries:
        if ptr in seen:
            continue
        seen.add(ptr)
        for j, tile in enumerate(tiles):
            frame_buf[ptr + j] = tile

    return bytes(ptr_buf), bytes(frame_buf)


def _write_hp_nibble(buf: bytearray, nibble_index: int, value: int) -> None:
    """Write a single HP nibble into a packed byte table.

    Even indices are stored in the high nibble, odd indices in the low nibble.
    """
    byte_idx = nibble_index >> 1
    if nibble_index & 1 == 0:
        buf[byte_idx] = (buf[byte_idx] & 0x0F) | ((value & 0x0F) << 4)
    else:
        buf[byte_idx] = (buf[byte_idx] & 0xF0) | (value & 0x0F)


def _serialize_enemy_hp(game_world: GameWorld, patch: Patch) -> None:
    """Serialize EnemyData.hp and secondary boss HP fields into ROM patches."""
    ed = game_world.enemies

    # Enemy HP table: 52 nibbles, Enemy 0x00-0x33
    enemy_buf = bytearray(ENEMY_HP_TABLE_SIZE)
    for i in range(ENEMY_HP_NIBBLE_COUNT):
        try:
            enemy = Enemy(i)
        except ValueError:
            continue
        if enemy in ed.hp:
            _write_hp_nibble(enemy_buf, i, ed.hp[enemy])
    patch.add(ENEMY_HP_TABLE_ADDRESS, bytes(enemy_buf))

    # Boss HP table: 24 nibbles, Enemy 0x34-0x4B
    boss_buf = bytearray(BOSS_HP_TABLE_SIZE)
    for j in range(BOSS_HP_NIBBLE_COUNT):
        enemy_val = BOSS_HP_FIRST_ENEMY_VALUE + j
        try:
            enemy = Enemy(enemy_val)
        except ValueError:
            continue
        if enemy in ed.hp:
            _write_hp_nibble(boss_buf, j, ed.hp[enemy])
    patch.add(BOSS_HP_TABLE_ADDRESS, bytes(boss_buf))

    # Secondary boss HP bytes (HP stored in high nibble)
    patch.add(GLEEOK_NECK_HP_ADDRESS,     bytes([(ed.gleeok_neck_hp & 0x0F) << 4]))
    patch.add(GLEEOK_HEAD_HP_ADDRESS,     bytes([(ed.gleeok_head_hp & 0x0F) << 4]))
    patch.add(GANON_HP_ADDRESS,           bytes([(ed.ganon_hp & 0x0F) << 4]))
    patch.add(MOLDORM_SEGMENT_HP_ADDRESS, bytes([(ed.moldorm_segment_hp & 0x0F) << 4]))
    patch.add(LAMNOLA_SEGMENT_HP_ADDRESS, bytes([(ed.lamnola_segment_hp & 0x0F) << 4]))
    if ed.rope_hp is not None:
        for address, value in zip(ROPE_HP_OPERAND_ADDRESSES, ed.rope_hp, strict=True):
            patch.add(address, bytes([(value & 0x0F) << 4]))

    # Boss engine sprite pointers (set by the boss-group pass)
    if ed.aquamentus_sprite_ptr is not None:
        patch.add(AQUAMENTUS_SPRITE_PTR_ADDRESS, bytes([ed.aquamentus_sprite_ptr & 0xFF]))
    if ed.aquamentus_tile_layout_table is not None:
        patch.add(AQUAMENTUS_TILE_LAYOUT_TABLE_ADDRESS,
                  bytes(v & 0xFF for v in ed.aquamentus_tile_layout_table))
    if ed.gleeok_head_sprite_ptr_a is not None:
        patch.add(GLEEOK_HEAD_SPRITE_PTR_A_ADDRESS, bytes([ed.gleeok_head_sprite_ptr_a & 0xFF]))
    if ed.gleeok_head_sprite_ptr_b is not None:
        patch.add(GLEEOK_HEAD_SPRITE_PTR_B_ADDRESS, bytes([ed.gleeok_head_sprite_ptr_b & 0xFF]))
    if ed.gleeok_head_sprite_ptr_c is not None:
        patch.add(GLEEOK_HEAD_SPRITE_PTR_C_ADDRESS, bytes([ed.gleeok_head_sprite_ptr_c & 0xFF]))
    if ed.gleeok_body_tiles is not None:
        patch.add(GLEEOK_BODY_TILES_ADDRESS, bytes(ed.gleeok_body_tiles))
