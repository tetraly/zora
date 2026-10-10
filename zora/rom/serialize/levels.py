"""Levels: the room bytes, level blocks, level information and sprite-set pointers."""

from ...model.enums import BossSpriteSet, Enemy, EnemySpriteSet, Item, RoomType
from ...model.game_world import GameWorld
from ...model.levels import Level, LevelBlock
from ...model.rooms import Room, StaircaseRoom
from ..layout import DUNGEON_NOTHING_CODE, LEVEL_TABLE_SIZE, NUM_TABLES

# ---------------------------------------------------------------------------
# Level serialization
# ---------------------------------------------------------------------------

RoomBytes = tuple[int, int, int, int, int, int]   # LevelBlockAttrsA..F


def _room_bytes(room: Room, nothing_code: int = DUNGEON_NOTHING_CODE) -> RoomBytes:
    """An ordinary room's six attribute bytes.

    nothing_code is the ROM byte for the Item.NOTHING MEANING (a game-config
    serialization setting; see game_config.DungeonNothingCode)."""
    t0 = ((room.walls.north & 0x07) << 5) | ((room.walls.south & 0x07) << 2) | (room.palette_0 & 0x03)
    t1 = ((room.walls.west & 0x07) << 5) | ((room.walls.east & 0x07) << 2) | (room.palette_1 & 0x03)
    enemy_code = room.enemy.value
    t2 = ((room.count_index & 0x03) << 6) | (enemy_code & 0x3F)
    mixed_bit   = 0x80 if enemy_code >= 0x40 else 0
    movable_bit = 0x40 if room.movable_block else 0x00
    t3 = mixed_bit | movable_bit | (room.room_type & 0x3F)
    if (room.item == Item.TRIFORCE_OF_POWER and nothing_code == Item.TRIFORCE_OF_POWER
            and room.enemy != Enemy.THE_BEAST):
        # under ZORA_REMAP only Ganon's room can carry $0E as the TFoP
        # (QUESTIONS #39); anywhere else it would re-parse as no item
        raise ValueError(
            f"room {room.room_num:02X}: triforce of power outside a Ganon "
            "($3E) room under ZORA_REMAP"
        )
    item_code = nothing_code if room.item == Item.NOTHING else room.item.value & 0x1F
    dark_bit = 0x80 if room.is_dark else 0
    t4 = dark_bit | ((room.boss_sound & 0x03) << 5) | item_code
    t5 = ((room.item_position & 0x03) << 4) | (room.room_action & 0x07)
    return t0, t1, t2, t3, t4, t5


def _staircase_bytes(sc: StaircaseRoom,
                     nothing_code: int = DUNGEON_NOTHING_CODE) -> RoomBytes:
    """A staircase's six attribute bytes: A/B hold its exit rooms (a
    transport's two, a cellar's return room twice), C the exit position."""
    t0, t1 = sc.exit_bytes()        # with the bits A43 cleared
    t2 = ((sc.exit_x & 0x0F) << 4) | (sc.exit_y & 0x0F)
    t3 = sc.room_type & 0x3F
    if sc.room_type == RoomType.ITEM_STAIRCASE and sc.item is not None:
        t4 = nothing_code if sc.item == Item.NOTHING else sc.item.value & 0x1F
    else:
        t4 = DUNGEON_NOTHING_CODE       # a transport's item byte (PS-DROP-01)
    return t0, t1, t2, t3, t4, sc.t5_raw


def encode_level_block(block: LevelBlock,
                       nothing_code: int = DUNGEON_NOTHING_CODE) -> bytes:
    """The six 128-byte attribute tables of a level block, every room
    written from the model."""
    grid = bytearray(NUM_TABLES * LEVEL_TABLE_SIZE)
    for cell in block.cells:
        encoded = (_room_bytes(cell, nothing_code) if isinstance(cell, Room)
                   else _staircase_bytes(cell, nothing_code))
        for table, value in enumerate(encoded):
            grid[table * LEVEL_TABLE_SIZE + cell.room_num] = value
    return bytes(grid)


# ---------------------------------------------------------------------------
# Level info serialization
# ---------------------------------------------------------------------------

def _serialize_level_info(level: Level, block: bytearray) -> None:
    """Write level info fields back into the 0xFC-byte block bytearray in-place."""
    block[0x00:0x24] = level.palette_raw
    block[0x7C:0xDC] = level.fade_palette_raw
    for i, q in enumerate(level.qty_table):
        block[0x24 + i] = q
    block[0x28] = level.start_y
    for i, v in enumerate(level.item_position_table):
        block[0x29 + i] = v
    block[0x2D] = level.map_start
    block[0x2E] = level.map_cursor_offset
    block[0x2F] = level.entrance_room
    block[0x3F:0x4F] = level.map_data
    block[0x4F:0x7C] = level.map_ppu_commands

    # Locked-raw round-trip: the parser stores the raw +0x30 triforce-room
    # pointer in level.triforce_room_ptr; None means "re-derive from
    # (possibly modified) room content" (the shapes writeback and any pass
    # that relocates the triforce).
    block[0x30] = (level.triforce_room_ptr if level.triforce_room_ptr is not None
                   else derive_triforce_room_ptr(level))

    block[0x31] = level.screen_status_ram_offset[0]
    block[0x32] = level.screen_status_ram_offset[1]
    block[0x33] = level.rom_level_num
    for i, b in enumerate(level.stairway_data_raw):
        block[0x34 + i] = b
    block[0x3E] = level.boss_room


# ---------------------------------------------------------------------------
# Sprite set pointer table serialization
# ---------------------------------------------------------------------------

# CPU addresses of pattern blocks in bank 3 (maps to CPU 0x8000-0xBFFF).
# These belong here, not in zora.model — they're a serialization detail.
_ENEMY_SET_CPU_ADDRS: dict[EnemySpriteSet, int] = {
    EnemySpriteSet.A:  0x9DBB,  # enemy_set_a  (file 0xDDCB)
    EnemySpriteSet.B:  0x987B,  # enemy_set_b  (file 0xD88B)
    EnemySpriteSet.C:  0x9A9B,  # enemy_set_c  (file 0xDAAB)
    EnemySpriteSet.OW: 0x965B,  # ow_sprites enemy region (file 0xD66B)
}

_BOSS_SET_CPU_ADDRS: dict[BossSpriteSet, int] = {
    BossSpriteSet.A: 0x9FDB,   # boss_set_a   (file 0xDFEB)
    BossSpriteSet.B: 0xA3DB,   # boss_set_b   (file 0xE3EB)
    BossSpriteSet.C: 0xA7DB,   # boss_set_c   (file 0xE7EB)
}


def _serialize_sprite_set_pointers(game_world: GameWorld) -> tuple[bytes, bytes]:
    """Return (level_ptr_bytes, boss_ptr_bytes) — 20 bytes each."""
    level_table = bytearray(20)
    boss_table  = bytearray(20)

    ow_addr = _ENEMY_SET_CPU_ADDRS[game_world.overworld.enemy_sprite_set]
    level_table[0] = ow_addr & 0xFF
    level_table[1] = (ow_addr >> 8) & 0xFF
    boss_table[0]  = _BOSS_SET_CPU_ADDRS[BossSpriteSet.A] & 0xFF
    boss_table[1]  = (_BOSS_SET_CPU_ADDRS[BossSpriteSet.A] >> 8) & 0xFF

    for lvl in game_world.levels:
        i = lvl.level_num
        e_addr = _ENEMY_SET_CPU_ADDRS[lvl.enemy_sprite_set]
        b_addr = _BOSS_SET_CPU_ADDRS[lvl.boss_sprite_set]
        level_table[i * 2]     = e_addr & 0xFF
        level_table[i * 2 + 1] = (e_addr >> 8) & 0xFF
        boss_table[i * 2]      = b_addr & 0xFF
        boss_table[i * 2 + 1]  = (b_addr >> 8) & 0xFF

    return bytes(level_table), bytes(boss_table)


def derive_triforce_room_ptr(level: "Level") -> int:
    """The compass points to the room containing the triforce (or Zelda in
    L9). If the triforce is in an item staircase, point to the room with the
    stairway down (return_dest) rather than the staircase room itself, since
    the staircase room isn't visible on the map."""
    for room in level.rooms:
        if room.item == Item.TRIFORCE or room.enemy == Enemy.THE_KIDNAPPED:
            return room.room_num
    for sr in level.staircase_rooms:
        if sr.room_type == RoomType.ITEM_STAIRCASE and sr.item == Item.TRIFORCE:
            return sr.exit_bytes()[0]    # the return room as its A byte holds it
    return 0x00
