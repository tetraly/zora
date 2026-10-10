"""Sprite patterns and the enemy data (tiles, frames, hit points)."""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import ClassVar

from .enums import Enemy, EnemySpriteSet

TILE_BYTES = 16                 # one 8x8 pattern tile


class PatternBlock(Enum):
    """The sprite pattern blocks the group passes read and write, by
    aldonunez label (post-shapes-b5.md appendix). CommonBackgroundPatterns
    is reachable only from byte 768 on (the common boss block)."""
    UWSP127 = auto()            # enemy bank, tier 0 (levels 1, 2, 7)
    UWSP358 = auto()            # enemy bank, tier 1
    UWSP469 = auto()            # enemy bank, tier 2
    OWSP = auto()               # overworld sprites
    BOSS1257 = auto()           # boss bank, tier 0
    BOSS3468 = auto()           # boss bank, tier 1
    BOSS9 = auto()              # boss bank, tier 2
    COMMON_BACKGROUND = auto()  # CommonBackgroundPatterns


@dataclass
class SpriteData:
    enemy_set_a:        bytearray   # 0x220 bytes at ENEMY_SET_A_SPRITES_ADDRESS
    enemy_set_b:        bytearray   # 0x220 bytes at ENEMY_SET_B_SPRITES_ADDRESS
    enemy_set_c:        bytearray   # 0x220 bytes at ENEMY_SET_C_SPRITES_ADDRESS
    ow_sprites:         bytearray   # 0x640 bytes at OW_SPRITES_ADDRESS
    boss_set_a:         bytearray   # 0x400 bytes at BOSS_SET_A_SPRITES_ADDRESS
    boss_set_b:         bytearray   # 0x400 bytes at BOSS_SET_B_SPRITES_ADDRESS
    boss_set_c:         bytearray   # 0x400 bytes at BOSS_SET_C_SPRITES_ADDRESS
    boss_set_expansion: bytearray   # 0x200 bytes at BOSS_SET_EXPANSION_SPRITES_ADDRESS
    dungeon_common:     bytearray   # 0x100 bytes at DUNGEON_COMMON_SPRITES_ADDRESS

    # Where each pattern block's bytes live: (field, the label's byte offset
    # of the field's first byte). ow_sprites starts 224 bytes into
    # PatternBlockOWSP; boss_set_expansion is CommonBackgroundPatterns + 768.
    _BLOCKS: ClassVar[dict[PatternBlock, tuple[str, int]]] = {
        PatternBlock.UWSP127: ("enemy_set_a", 0),
        PatternBlock.UWSP358: ("enemy_set_b", 0),
        PatternBlock.UWSP469: ("enemy_set_c", 0),
        PatternBlock.OWSP: ("ow_sprites", 224),
        PatternBlock.BOSS1257: ("boss_set_a", 0),
        PatternBlock.BOSS3468: ("boss_set_b", 0),
        PatternBlock.BOSS9: ("boss_set_c", 0),
        PatternBlock.COMMON_BACKGROUND: ("boss_set_expansion", 768),
    }

    def _span(self, block: PatternBlock, byte_offset: int, size: int) -> tuple[bytearray, int]:
        name, first = self._BLOCKS[block]
        data: bytearray = getattr(self, name)
        start = byte_offset - first
        if start < 0 or start + size > len(data):
            raise IndexError(f"{block.name} + {byte_offset} is outside the modelled bytes")
        return data, start

    def read_tiles(self, block: PatternBlock, byte_offset: int, count: int) -> list[bytes]:
        """`count` 16-byte tiles starting at the label's byte offset."""
        data, start = self._span(block, byte_offset, count * TILE_BYTES)
        return [bytes(data[start + i * TILE_BYTES:start + (i + 1) * TILE_BYTES])
                for i in range(count)]

    def write_tile(self, block: PatternBlock, byte_offset: int, tile: bytes) -> None:
        data, start = self._span(block, byte_offset, TILE_BYTES)
        data[start:start + TILE_BYTES] = tile


@dataclass
class EnemyData:
    # Tile mapping tables (ROM 0x6E14 / 0x6E93).
    # The pointer table has 0x7F slots:
    #   slot 0          = player (Link) — not an Enemy enum value
    #   slots 1-0x53    = Enemy enum values 0x00-0x52 (slot = enemy_id + 1)
    #   slots 0x54-0x7E = overworld NPC sprite variants (43 entries)
    # Each pointer is an index into the tile_frames buffer.
    # Enemies sharing the same pointer share the same frame list.

    # Slot 0: player character (Link)
    player_pointer: int
    player_tiles:   list[int]

    # Slots 1-0x53: one entry per Enemy enum value (0x00-0x52), keyed by Enemy
    tile_pointers: dict["Enemy", int]    # enemy -> index into frame data buffer
    tile_frames:   dict["Enemy", list[int]]  # enemy -> list of tile codes

    # Slots 0x54-0x7E: overworld NPC sprite variants (43 entries, fixed order)
    overworld_npc_pointers: list[int]          # 43 pointer values
    overworld_npc_frames:   list[list[int]]    # 43 frame tile lists

    # HP for all enemies and bosses, keyed by Enemy enum.
    # Values are raw nibbles (0-15); actual HP in-game = value x 0x10 (value << 4).
    # Stored in ROM as nibble pairs:
    #   Enemy HP table:  0x1FB5E (26 bytes, 52 nibbles, Enemy 0x00-0x33)
    #   Boss HP table:   0x1FB78 (12 bytes, 24 nibbles, Enemy 0x34-0x4B)
    # Entry i occupies: byte = base + (i >> 1), nibble = high if (i & 1 == 0) else low.
    hp: dict["Enemy", int] = field(default_factory=dict)

    # Secondary HP bytes for multi-part bosses. These are separate ROM locations
    # that the engine reads independently from the main hp table above.
    # All values are stored as a full byte = nibble << 4 (i.e. high nibble only).
    #
    # To read from ROM:  value = rom[offset] >> 4
    # To write to ROM:   rom[offset] = value << 4
    #
    # Engine targets per aldonunez (fields renamed 2026-09-27; formerly
    # aquamentus_hp / aquamentus_sp / gleeok_hp / patra_hp — the ROM bin
    # file names in rom_data/ keep those old names):
    gleeok_neck_hp: int     = 0   # 0x120C6 — Gleeok neck HP (InitGleeok)
    gleeok_head_hp: int     = 0   # 0x12735 — Gleeok flying-head HP (Gleeok_CheckCollisions)
    ganon_hp: int           = 0   # 0x12F27 — Ganon HP (Ganon_CheckCollisions)
    moldorm_segment_hp: int = 0   # 0x114D5 — Moldorm segment HP (UpdateMoldorm)
    lamnola_segment_hp: int = 0   # 0x12A45 — Lanmola segment HP (UpdateLamnola)
    # InitRope's hit points, quest 1 and quest 2 (0x112D3, 0x112DF; PS-HP-01);
    # None when loaded from .bin files.
    rope_hp: tuple[int, int] | None = None
    # GleeokBodyTiles0-2 (0x12819, bank 4): Gleeok's 18 body frame bytes.
    gleeok_body_tiles: list[int] | None = None

    def _frame_lists(self) -> list[tuple[int, list[int]]]:
        """Every (pointer, frame list) into ObjAnimFrameHeap; lists sharing
        a pointer are one object."""
        return ([(self.player_pointer, self.player_tiles)]
                + [(self.tile_pointers[e], frames) for e, frames in self.tile_frames.items()]
                + list(zip(self.overworld_npc_pointers, self.overworld_npc_frames, strict=True)))

    def frame_bytes(self, offset: int, count: int) -> list[int]:
        """`count` bytes of ObjAnimFrameHeap from `offset`."""
        return [self._frame_at(offset + i) for i in range(count)]

    def _frame_at(self, offset: int) -> int:
        for pointer, frames in self._frame_lists():
            if pointer <= offset < pointer + len(frames):
                return frames[offset - pointer]
        raise IndexError(f"ObjAnimFrameHeap + {offset} belongs to no frame list")

    def set_frame_bytes(self, offset: int, values: list[int]) -> None:
        """Write ObjAnimFrameHeap bytes from `offset` (every list covering a
        byte is updated)."""
        for i, value in enumerate(values):
            hit = False
            for pointer, frames in self._frame_lists():
                if pointer <= offset + i < pointer + len(frames):
                    frames[offset + i - pointer] = value
                    hit = True
            if not hit:
                raise IndexError(f"ObjAnimFrameHeap + {offset + i} belongs to no frame list")

    # Set by the enemy-group pass after enemy group randomization.
    # Maps each sprite set to the list of Enemy values assigned to that group.
    # Empty dict until the enemy shuffler runs.
    cave_groups: dict["EnemySpriteSet", list["Enemy"]] = field(default_factory=dict)

    # Mixed enemy group definitions: group code (0x62-0x7F) → 8-member list.
    # Populated during parsing from the ROM's mixed enemy data table.
    # Updated by the enemy-group pass to keep members compatible with
    # their group's sprite set after shuffling.
    mixed_groups: dict[int, list["Enemy"]] = field(default_factory=dict)

    # Raw mixed enemy data blob and per-group byte offsets within it.
    # Substitutions are applied directly to this blob to preserve the
    # overlapping layout used by the vanilla ROM.  Serialized back as-is.
    mixed_enemy_data: bytearray = field(default_factory=bytearray)
    mixed_group_offsets: dict[int, int] = field(default_factory=dict)

    aquamentus_sprite_ptr: int | None = None
    # 12-byte tile column table at ROM 0x11844 used by the Aquamentus/Ganon draw
    # routine. Set by the boss-group pass when AQUAMENTUS is repacked.
    aquamentus_tile_layout_table: list[int] | None = None
    gleeok_head_sprite_ptr_a: int | None = None
    gleeok_head_sprite_ptr_b: int | None = None
    gleeok_head_sprite_ptr_c: int | None = None
