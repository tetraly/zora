"""Levels and level blocks, and the level and monster codes the passes name."""

from dataclasses import dataclass, field

from zora.model.enums import BossSpriteSet, Direction, Enemy, EnemySpriteSet
from zora.model.rooms import MONSTER_BIT_CODE, PALETTE_SELECTOR_MASK, Room, StaircaseRoom

# --- Levels and the monster codes the passes name -----------------------------
LEVEL_9 = 9
HINT_LEVELS = range(1, LEVEL_9)    # levels 1-8: their persons take hint texts; level 9's are left alone
# Person codes are monster lists in a person room; outside one, the same
# values are ordinary enemies (Enemy.ZOLA is $11, Enemy.RED_DARKNUT $0B).
MERCHANT_LIST = 0x11               # the life-or-money merchant
L9_ENTRY_PERSON_LIST = 0x0B        # the person above level 9's entrance (SH-ROOM-05)
L9_ENTRY_PERSON = L9_ENTRY_PERSON_LIST | MONSTER_BIT_CODE   # $4B: its code with the monster high bit
ZELDA_LIST = Enemy.THE_KIDNAPPED   # $37, level 9's Zelda room
GANON_LIST = Enemy.THE_BEAST       # $3E, level 9's Ganon room
GANON_ITEM_BYTE = 0x8E             # Ganon room's whole item byte: dark room, Triforce of Power


Cell = Room | StaircaseRoom

LEVEL_BLOCK_ROOMS = 128


@dataclass
class LevelBlock:
    """One 128-room dungeon block (aldonunez LevelBlockUW1Q1, LevelBlockUW2Q1
    and the quest-2 pair): the six room attribute tables decoded per room.
    This is the canonical store of every room and staircase, owned by a
    level or not; a Level lists the room numbers it owns."""
    cells: list[Cell]
    # The levels whose rooms live in this block; each Level registers itself
    # when it is made (owner_of reads their room lists).
    levels: list["Level"] = field(default_factory=list, repr=False, compare=False)

    def __post_init__(self) -> None:
        assert len(self.cells) == LEVEL_BLOCK_ROOMS
        assert all(c.room_num == n for n, c in enumerate(self.cells))

    def owner_of(self, room_num: int) -> "Level | None":
        """The level that owns the room, or None. Levels of one block never
        share a room in ZORA's output (tests/test_flag_invariants.py); where
        a read ROM's do, the lowest-numbered owner wins."""
        owners = [level for level in self.levels if room_num in level.room_nums]
        return min(owners, key=lambda level: level.level_num, default=None)

    def __getitem__(self, room_num: int) -> Cell:
        return self.cells[room_num]

    def __setitem__(self, room_num: int, cell: Cell) -> None:
        assert cell.room_num == room_num
        self.cells[room_num] = cell

    def room(self, room_num: int) -> Room:
        cell = self.cells[room_num]
        assert isinstance(cell, Room), f"room {room_num:02X} is a staircase"
        return cell

    def staircase(self, room_num: int) -> StaircaseRoom:
        cell = self.cells[room_num]
        assert isinstance(cell, StaircaseRoom), f"room {room_num:02X} is not a staircase"
        return cell

    def palette_bits(self, room_num: int) -> tuple[int, int]:
        """Bits 1-0 of the room's A and B bytes, whatever the cell holds (on
        a staircase they are the low bits of its exit rooms)."""
        cell = self.cells[room_num]
        if isinstance(cell, Room):
            return cell.palette_0, cell.palette_1
        exit_a, exit_b = cell.exit_bytes()
        return exit_a & PALETTE_SELECTOR_MASK, exit_b & PALETTE_SELECTOR_MASK

    @property
    def rooms(self) -> list[Room]:
        """Every ordinary room of the block, in room-number order."""
        return [c for c in self.cells if isinstance(c, Room)]

    @property
    def staircases(self) -> list[StaircaseRoom]:
        return [c for c in self.cells if isinstance(c, StaircaseRoom)]

    @classmethod
    def blank(cls) -> "LevelBlock":
        return cls([Room.blank(n) for n in range(LEVEL_BLOCK_ROOMS)])


@dataclass
class Level:
    level_num: int
    entrance_room: int
    entrance_direction: Direction
    palette_raw: bytes               # 0x24 bytes: PPU header + 8 groups of 4 color bytes
    fade_palette_raw: bytes          # 0x60 bytes: stairway/death-fade palettes (block +0x7C)
    staircase_room_pool: list[int]
    room_nums: list[int]             # ordinary rooms this level owns, sorted
    staircase_nums: list[int]        # live staircases of its stairway pool, sorted
    # The block holding those rooms (shared by the levels of a set; kept
    # out of repr and equality, which compare the level's own data).
    block: LevelBlock = field(repr=False, compare=False)
    boss_room: int
    enemy_sprite_set: EnemySpriteSet
    boss_sprite_set: BossSpriteSet
    # Preserved for round-trip (not randomized)
    start_y: int
    item_position_table: list[int]  # 4 packed 0xXY bytes: high nibble=X tile, low nibble=Y tile
    map_start: int
    map_cursor_offset: int
    map_data: bytes              # 16 bytes: column occupancy bitmap (block 0x3F-0x4E)
    map_ppu_commands: bytes      # 45 bytes: PPU command sequences (block 0x4F-0x7B)
    qty_table: list[int]         # 4 bytes, preserved
    stairway_data_raw: bytes     # 10 bytes, preserved verbatim for round-trip
    rom_level_num: int = 0       # block[0x33]: ROM's display level number (differs from slot in Q2)
    # Offset in cartridge RAM for screen status (level_info +0x31, 2 bytes).
    # Vanilla value varies per level. Setting to 0xF0xx gives Link invincibility.
    # Preserved verbatim — not randomized.
    screen_status_ram_offset: bytes = b"\x00\x00"
    # block[0x30] TRIFORCE-ROOM POINTER (the compass follows it; in L9 it
    # points at the kidnapped-Zelda room). The room re-deal pass — a later
    # stage — rewrites this byte, so shapes-stage snapshots legitimately
    # carry a mid-pipeline value. The parser LOCKS the raw byte for
    # byte-faithful round-trip; passes that move the triforce set it to
    # None to re-derive on serialization (serializer.derive_triforce_room_ptr).
    triforce_room_ptr: int | None = None

    def __post_init__(self) -> None:
        self.block.levels.append(self)

    @property
    def rooms(self) -> list[Room]:
        return [self.block.room(n) for n in self.room_nums]

    # The level's two color sets (post-shapes-b5.md PS-COLOR): set 1 is the
    # 32 color bytes after the 3-byte PPU header at block + $03; set 2 the
    # 96 bytes at block + $7C (fade_palette_raw).
    COLOR_SET_1 = slice(3, 35)

    @property
    def color_sets(self) -> tuple[bytes, bytes]:
        return self.palette_raw[self.COLOR_SET_1], self.fade_palette_raw

    def set_color_sets(self, set_1: bytes, set_2: bytes) -> None:
        raw = bytearray(self.palette_raw)
        raw[self.COLOR_SET_1] = set_1
        assert len(raw) == len(self.palette_raw) and len(set_2) == len(self.fade_palette_raw)
        self.palette_raw, self.fade_palette_raw = bytes(raw), bytes(set_2)

    @property
    def staircase_rooms(self) -> list[StaircaseRoom]:
        return [self.block.staircase(n) for n in self.staircase_nums]

    def enemy_quantity(self, room: Room) -> int:
        """How many monsters the room holds: its count index looked up in
        this level's count table."""
        return self.qty_table[room.count_index]

    def palette_colors(self) -> list[int]:
        """Return the 8 color values (byte[1] of each 4-byte group after the 3-byte PPU header)."""
        data = self.palette_raw[3:3 + 32]  # 8 groups x 4 bytes
        return [data[g * 4 + 1] for g in range(8)]


def is_l9_entry_gate(level: Level, room: Room) -> bool:
    """Is this the L9 entry gate room?

    The room positioned adjacent to the L9 entrance that gates access to
    the rest of the level. In vanilla its shutters open when the player
    obtains all 8 Triforces (the engine's Triforce-of-Power-opens-shutters
    behavior fires when Ganon is defeated). The gate's NPC is removed at
    that point.

    Identified by position rather than by enemy, because the engine
    removes the NPC at the right moment and identifying-by-enemy would
    lose the gate after that.

    This room has structural meaning that ordinary NPC-handling and
    room-shuffling passes don't account for. Passes that operate on
    "rooms with unkillable NPCs" or "eligible-for-shuffle rooms" should
    skip this room.
    """
    if level.level_num != 9:
        return False
    return room.room_num == level.entrance_room - 16


# --- Post-definition constants ---


VANILLA_ENEMY_SPRITE_SETS: dict[int, "EnemySpriteSet"] = {
    0: EnemySpriteSet.A,  # overworld
    1: EnemySpriteSet.A, 2: EnemySpriteSet.A, 7: EnemySpriteSet.A,
    3: EnemySpriteSet.B, 5: EnemySpriteSet.B, 8: EnemySpriteSet.B,
    4: EnemySpriteSet.C, 6: EnemySpriteSet.C, 9: EnemySpriteSet.C,
}

VANILLA_BOSS_SPRITE_SETS = {
    1: BossSpriteSet.A, 2: BossSpriteSet.A, 5: BossSpriteSet.A, 7: BossSpriteSet.A,
    3: BossSpriteSet.B, 4: BossSpriteSet.B, 6: BossSpriteSet.B, 8: BossSpriteSet.B,
    9: BossSpriteSet.C,
}
