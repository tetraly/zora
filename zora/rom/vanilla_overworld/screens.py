"""Overworld screens: LevelBlockOW's per-room attributes, decoded as the
game reads them (read-only).

Each of the 128 screens has one byte in each of LevelBlockAttrsA-F. The
bit meanings, with the routine that reads each:

  A  bits 0-1  outer palette selector            FillPlayAreaAttrs
     bit 2     sea sound                         (Z_07 ambient-sound check)
     bit 3     zora                              CheckZora
     bits 4-7  X where Link leaves a cave        (room entry, Z_05)
  B  bits 0-1  inner palette selector            FillPlayAreaAttrs
     bits 2-7  cave value: 0 none, 1-9 a level,  HandleWarpOW
               $10-$23 cave dweller $6A-$7D (InitMode ... cave index)
  C  bits 0-5  monster list, low six bits        (room entry, Z_05)
     bits 6-7  count index into LevelInfo_FoeCounts
  D  bits 0-6  unique screen layout              LayoutRoomOW
     bit 7     monster list bit 6 (mixed list)   (room entry, Z_05)
  F  bits 0-2  row where Link leaves a cave      (room entry, Z_05)
     bit 3     monsters come from the edges      (object spawning, Z_05/07)
     bits 4-5  shortcut position index           GetShortcutOrItemXYForRoom
     bits 6-7  quest secret: 0 both, 1 quest 1   IsQuestSecretMismatch
               only, 2 quest 2 only              (SecretQuestNumbers)

Table E is not per screen in the overworld: it holds the cave wares
(caves.py). LayoutRoomOW multiplies the whole D byte after one ASL, so the
layout is bits 0-6 (121 layouts); GetUniqueRoomId's AND #$3F is the
underworld's view.

The second quest patches eight B bytes (LevelBlockAttrsBQ2Replacement*)
and, in UpdateMode2Load_Full's code, writes D+11, D+60 and D+116 ($7B, $7B,
$5A), A+60 and A+116 ($72) and F+60 and F+116 ($01, $00). The immediate
writes are code, not a table; second_quest_patches lists them as read from
the disassembly.
"""
from dataclasses import dataclass
from enum import Enum

from zora.rom.vanilla_overworld.tables import (
    ATTRIBUTE_TABLE_SIZE,
    LEVEL_BLOCK_OW,
    Q2_B_REPLACEMENT_OFFSETS,
    Q2_B_REPLACEMENT_VALUES,
    SCREEN_COUNT,
)

PALETTE_SELECTOR_MASK = 0x03
SEA_SOUND_BIT = 0x04
ZORA_BIT = 0x08
EXIT_X_MASK = 0xF0
CAVE_VALUE_SHIFT = 2
LEVEL_VALUES = range(1, 10)
FIRST_CAVE_VALUE = 0x10
CAVE_DWELLER_BASE = 0x6A          # ObjType of cave index 0
SHORTCUT_CAVE_INDEX = 4           # cave value $14: mode $C, the "take any road" cave
MONSTER_LIST_LOW_MASK = 0x3F
COUNT_INDEX_SHIFT = 6
LAYOUT_MASK = 0x7F
MIXED_LIST_BIT = 0x80             # D bit 7 -> monster list bit 6
MONSTER_LIST_HIGH_BIT = 0x40
EXIT_ROW_MASK = 0x07
EDGE_MONSTERS_BIT = 0x08
SHORTCUT_POSITION_SHIFT = 4
SHORTCUT_POSITION_MASK = 0x03
QUEST_SECRET_SHIFT = 6
EXIT_Y_BASE = 0x4D                # $50 (square row 1) minus Link's 3-pixel offset
SQUARE_HEIGHT = 0x10

# UpdateMode2Load_Full's immediate writes for the second quest, as listed
# in the disassembly (Z_06.asm): (table, room, value).
Q2_IMMEDIATE_WRITES = (("D", 11, 0x7B), ("D", 60, 0x7B), ("D", 116, 0x5A),
                       ("A", 60, 0x72), ("A", 116, 0x72), ("F", 60, 0x01), ("F", 116, 0x00))


class EntranceKind(Enum):
    NONE = "none"
    LEVEL = "level"
    CAVE = "cave"


class QuestSecret(Enum):
    """F bits 6-7 through SecretQuestNumbers ($00, $00, $01)."""
    BOTH = 0
    FIRST_ONLY = 1
    SECOND_ONLY = 2


@dataclass(frozen=True)
class Entrance:
    """Where the screen's entrance (stairs or cave tile) leads: B >> 2."""
    value: int

    @property
    def kind(self) -> EntranceKind:
        if self.value == 0:
            return EntranceKind.NONE
        if self.value in LEVEL_VALUES:
            return EntranceKind.LEVEL
        assert self.value >= FIRST_CAVE_VALUE, f"cave value {self.value:#x}"
        return EntranceKind.CAVE

    @property
    def level(self) -> int | None:
        return self.value if self.kind is EntranceKind.LEVEL else None

    @property
    def cave_index(self) -> int | None:
        """0-19 for a cave: its dweller is object type $6A + index."""
        return self.value - FIRST_CAVE_VALUE if self.kind is EntranceKind.CAVE else None

    @property
    def is_shortcut(self) -> bool:
        """Cave value $14: HandleWarpOW enters mode $C, not mode $B."""
        return self.cave_index == SHORTCUT_CAVE_INDEX


@dataclass(frozen=True)
class OverworldScreen:
    room_id: int
    attrs: bytes                    # A, B, C, D, E, F as stored (E unused per screen)

    @property
    def a(self) -> int:
        return self.attrs[0]

    @property
    def b(self) -> int:
        return self.attrs[1]

    @property
    def c(self) -> int:
        return self.attrs[2]

    @property
    def d(self) -> int:
        return self.attrs[3]

    @property
    def f(self) -> int:
        return self.attrs[5]

    @property
    def outer_palette(self) -> int:
        return self.a & PALETTE_SELECTOR_MASK

    @property
    def inner_palette(self) -> int:
        return self.b & PALETTE_SELECTOR_MASK

    @property
    def sea_sound(self) -> bool:
        return bool(self.a & SEA_SOUND_BIT)

    @property
    def zora(self) -> bool:
        return bool(self.a & ZORA_BIT)

    @property
    def entrance(self) -> Entrance:
        return Entrance(self.b >> CAVE_VALUE_SHIFT)

    @property
    def exit_x(self) -> int:
        """Link's X on leaving the screen's cave or level."""
        return self.a & EXIT_X_MASK

    @property
    def exit_y(self) -> int:
        """Link's Y on leaving: square row (F bits 0-2) * $10 + $4D."""
        return (self.f & EXIT_ROW_MASK) * SQUARE_HEIGHT + EXIT_Y_BASE

    @property
    def layout(self) -> int:
        """The unique screen layout, 0-120 (RoomLayoutsOW)."""
        return self.d & LAYOUT_MASK

    @property
    def monster_list(self) -> int:
        """The monster list id: C bits 0-5, plus $40 when D bit 7 is set."""
        high = MONSTER_LIST_HIGH_BIT if self.d & MIXED_LIST_BIT else 0
        return (self.c & MONSTER_LIST_LOW_MASK) | high

    @property
    def count_index(self) -> int:
        return self.c >> COUNT_INDEX_SHIFT

    @property
    def monsters_from_edges(self) -> bool:
        return bool(self.f & EDGE_MONSTERS_BIT)

    @property
    def shortcut_position_index(self) -> int:
        """Index into LevelInfo_ShortcutOrItemPosArray."""
        return (self.f >> SHORTCUT_POSITION_SHIFT) & SHORTCUT_POSITION_MASK

    @property
    def quest_secret(self) -> QuestSecret:
        return QuestSecret(self.f >> QUEST_SECRET_SHIFT)


def read_screens(rom: bytes) -> list[OverworldScreen]:
    """All 128 screens, room id order."""
    block = LEVEL_BLOCK_OW.read(rom)
    tables = [block[t * ATTRIBUTE_TABLE_SIZE:(t + 1) * ATTRIBUTE_TABLE_SIZE] for t in range(6)]
    return [OverworldScreen(room, bytes(table[room] for table in tables))
            for room in range(SCREEN_COUNT)]


def second_quest_b_replacements(rom: bytes) -> list[tuple[int, int]]:
    """(offset from LevelBlockAttrsB, value) for the second quest's eight B
    writes. An offset of $80 or more lands in table C (offset - $80)."""
    offsets = Q2_B_REPLACEMENT_OFFSETS.read(rom)
    values = Q2_B_REPLACEMENT_VALUES.read(rom)
    return list(zip(offsets, values, strict=True))
