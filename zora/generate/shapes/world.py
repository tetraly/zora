"""Working data for one dungeon set while the shape stage builds it
(SH-GRID-01), and the grid helpers the later passes share.

A set is either levels 1-6 (six blobs on the 128-cell grid) or levels 7-9
(three blobs). Cells are room numbers: row * 16 + col, row 7 = bottom.

Determinism: never iterate sets/dicts directly in generation logic — use the
sorted accessors below.
"""
from dataclasses import dataclass, field
from enum import Enum, auto

from zora.generate.shapes.tables import LEVEL_BOSS_POOL
from zora.model.enums import RoomAction, Side, WallType
from zora.model.levels import Level, LevelBlock
from zora.model.rooms import (
    BOSS_SOUND_SHIFT,
    COUNT_INDEX_MASK,
    COUNT_INDEX_SHIFT,
    DARK_BIT,
    ITEM_MASK,
    MONSTER_BIT,
    MONSTER_BIT_CODE,
    MONSTER_LIST_BITS,
    MONSTER_VALUE_BIT,
    NO_ITEM_CODE,
    PERSON_LISTS,
    PUSH_BLOCK_VARIANT,
    Room,
)

GRID_COLS = 16
GRID_ROWS = 8

UNASSIGNED = -1
FREED = -2          # cell freed for a staircase (SH-GRID-08)


def blocks_of(levels: list[Level]) -> list[LevelBlock]:
    """The distinct blocks the levels live in, in level order (the levels
    1-6 block, then the levels 7-9 block)."""
    blocks: list[LevelBlock] = []
    for level in sorted(levels, key=lambda lv: lv.level_num):
        if not any(block is level.block for block in blocks):
            blocks.append(level.block)
    return blocks


def side_of(room: Room, side: Side) -> WallType:
    """The room's own door state on a side."""
    wall: WallType = getattr(room.walls, side.wall_attr)
    return wall


def set_side(room: Room, side: Side, wall: WallType) -> None:
    setattr(room.walls, side.wall_attr, wall)


def sides_of(room: Room) -> tuple[WallType, WallType, WallType, WallType]:
    """The room's four sides, indexed by Side."""
    walls = room.walls
    return walls.north, walls.east, walls.south, walls.west


class StairKind(Enum):
    """What a staircase plan is (SH-STAIR-01)."""
    CELLAR = auto()              # an item cellar, entered from its house room
    TRANSPORT = auto()           # a transport staircase joining two rooms


class StairRole(Enum):
    """The part a stair room plays (SH-STAIR-05..08)."""
    CELLAR_HOUSE = auto()        # the room whose staircase leads to an item cellar
    FIRST_END = auto()           # a transport's first room
    SECOND_END = auto()          # a transport's second room


@dataclass
class StairPlan:
    """A staircase occupying a freed cell (SH-STAIR-01..10)."""
    cell: int
    kind: StairKind
    item: int | None = None      # cellar item code
    house: int | None = None     # cellar: room whose staircase leads here
    first: int | None = None     # transport: first stair room
    second: int | None = None    # transport: second stair room


# --- Door types (a side's door field; the data model's WallType) ------------
D_UNDECIDED = -1
D_OPEN = WallType.OPEN_DOOR
D_WALL = WallType.SOLID_WALL
D_BOMB = WallType.BOMB_HOLE
D_KEY1 = WallType.LOCKED_DOOR_1
D_KEY2 = WallType.LOCKED_DOOR_2
D_SHUTTER = WallType.SHUTTER_DOOR

# --- Room bytes as the spec reads them ---------------------------------------
# The bit layout of LevelBlockAttrsA to F is zora.model.rooms's. The plan's
# enemy code carries the monster-list id in bits 0-5 and the layout byte's
# "monster high bit" (the person / mixed-group flag) as bit 6
# (MONSTER_BIT_CODE), like the data model's Enemy codes.
# A34: some rules match the monster byte with its high count bit ignored.
WITHOUT_HIGH_COUNT_BIT = 0x7F
DEFAULT_TRIGGER = RoomAction.ALL_DEAD   # an undecided trigger ships as 1
# SH-DOOR-01: the palette selectors, bits 1-0 of LevelBlockAttrsA (outer)
# and LevelBlockAttrsB (inner)
DOOR_PASS_SELECTOR = 2          # the outer written, and ORed into the inner
PERSON_ROOM_INNER = 0           # person and hungry-goriya rooms clear it
ZELDA_ROOM_INNER = 2



# every boss monster code (bosses ship count code 0, SH-BOSS-07)
BOSS_CODES = frozenset(code for pool in LEVEL_BOSS_POOL.values() for code in pool)


@dataclass
class CellPlan:
    """Per-cell decisions of the shape stage; None fields mean 'not decided
    yet'. When the shape stage ends the plans become Rooms (ship.build_sets)
    and every later pass works on those.

    The properties give the room's bytes and flags as the spec states its
    rules on them."""
    walls: list[int] = field(default_factory=lambda: [-1, -1, -1, -1])
    layout: int | None = None
    movable: bool = False
    enemy: int | None = None
    qty_code: int | None = None
    item: int | None = None
    item_pos: int | None = None
    action: int | None = None
    dark: bool = False
    boss_sound: int = 0          # LevelBlockAttrsE bits 6-5 (BossSound index)
    inner_palette: int | None = None   # LevelBlockAttrsB bits 1-0 (SH-DOOR-01)

    @property
    def has_monster_bit(self) -> bool:
        """The layout byte's bit 7: the person flag (or a mixed group)."""
        return self.enemy is not None and bool(self.enemy & MONSTER_BIT_CODE)

    @property
    def monster_list(self) -> int:
        """The monster byte's low six bits."""
        return (self.enemy or 0) & MONSTER_LIST_BITS

    @property
    def layout_id(self) -> int:
        """The layout alone: the layout byte's low six bits."""
        return self.layout or 0

    @property
    def layout_code(self) -> int:
        """The layout with its push-block variant: the layout byte with the
        monster bit ignored."""
        return (self.layout or 0) | (PUSH_BLOCK_VARIANT if self.movable else 0)

    @property
    def layout_byte(self) -> int:
        """The whole `LevelBlockAttrsD` byte."""
        return self.layout_code | (MONSTER_BIT if self.has_monster_bit else 0)

    @property
    def monster_byte(self) -> int:
        """The whole `LevelBlockAttrsC` byte as written back (bosses ship
        count code 0, SH-BOSS-07)."""
        count = 0 if self.enemy in BOSS_CODES else (self.qty_code or 0)
        return self.monster_list | (count << COUNT_INDEX_SHIFT)

    @property
    def monster_value(self) -> int:
        """The nine-bit monster value (post-shapes-b2.md PS-MONLV-02): the
        whole monster byte plus $100 for the monster bit."""
        return self.monster_byte | (MONSTER_VALUE_BIT if self.has_monster_bit else 0)

    def set_monster_value(self, value: int) -> None:
        """Write a nine-bit value: the monster byte, and the monster bit
        into the layout byte's bit 7 (its other bits stay)."""
        self.enemy = ((value & MONSTER_LIST_BITS)
                      | (MONSTER_BIT_CODE if value & MONSTER_VALUE_BIT else 0))
        self.qty_code = (value >> COUNT_INDEX_SHIFT) & COUNT_INDEX_MASK

    @property
    def is_person(self) -> bool:
        """A person, as the post-shapes passes read one: the person flag with
        a person code (QUESTIONS #45.2; the layout is not tested)."""
        return self.has_monster_bit and self.monster_list in PERSON_LISTS

    @property
    def item_byte(self) -> int:
        """The whole `LevelBlockAttrsE` byte (item, boss sound, dark)."""
        item = self.item if self.item is not None else NO_ITEM_CODE
        return ((item & ITEM_MASK) | (self.boss_sound << BOSS_SOUND_SHIFT)
                | (DARK_BIT if self.dark else 0))

    @property
    def trigger(self) -> int:
        """The room's secret trigger as written back."""
        return self.action if self.action is not None else DEFAULT_TRIGGER



@dataclass
class SetWorld:
    """State of one dungeon set under construction."""
    base_level: int              # 0 for the first set (levels 1-6), 6 for 7-9
    blob_count: int
    blob_of: list[int] = field(default_factory=list)     # cell → blob index
    # Blob start/numbering helpers: blob index → assigned level number set in
    # numbering.py.
    levels: dict[int, int] = field(default_factory=dict)  # blob → level number
    cells_by_blob: list[list[int]] = field(default_factory=list)
    bands: list[list[int]] = field(default_factory=list)  # blob → [lo, hi]
    plans: list[CellPlan] = field(default_factory=list)
    stairs: dict[int, StairPlan] = field(default_factory=dict)  # cell → plan
    entrance: dict[int, int] = field(default_factory=dict)  # level → cell
    unreachable_levels: dict[int, int] = field(default_factory=dict)
    boss_room: dict[int, int] = field(default_factory=dict)  # level → first boss cell
    # level number → that level's four standard item-position bytes (the
    # preserved vanilla item_position_table; T5 matching happens against it).
    pos_tables: dict[int, list[int]] = field(default_factory=dict)
    ganon_room: int | None = None
    zelda_room: int | None = None
    # cell -> the base ROM block's inner palette selector there (SH-DOOR-01)
    base_inner_palettes: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.blob_of:
            self.blob_of = [UNASSIGNED] * (GRID_COLS * GRID_ROWS)
            self.plans = [CellPlan() for _ in range(GRID_COLS * GRID_ROWS)]
            self.cells_by_blob = [[] for _ in range(self.blob_count)]
            self.bands = [[0, GRID_COLS - 1] for _ in range(self.blob_count)]
        if not self.base_inner_palettes:
            # a set built without a base block (tests): selectors 0
            self.base_inner_palettes = [0] * (GRID_COLS * GRID_ROWS)

    # --- deterministic accessors ---

    def owned_cells(self, blob: int) -> list[int]:
        return self.cells_by_blob[blob]

    def all_cells_sorted(self) -> list[int]:
        return [c for c in range(len(self.blob_of))
                if self.blob_of[c] not in (UNASSIGNED, FREED)]

    def assign(self, cell: int, blob: int) -> None:
        assert self.blob_of[cell] == UNASSIGNED
        self.blob_of[cell] = blob
        self.cells_by_blob[blob].append(cell)
        self.cells_by_blob[blob].sort()

    def free_for_stair(self, cell: int) -> None:
        blob = self.blob_of[cell]
        assert blob >= 0
        self.cells_by_blob[blob].remove(cell)
        self.blob_of[cell] = FREED
        self.freed[cell] = blob

    def restore_cell(self, cell: int, blob: int) -> None:
        """Undo a freeing (used by the numbering/allowance fixed point before
        any content is placed on the cell)."""
        assert self.blob_of[cell] == FREED
        self.blob_of[cell] = blob
        self.cells_by_blob[blob].append(cell)
        self.cells_by_blob[blob].sort()
        self.freed.pop(cell, None)

    freed: dict[int, int] = field(default_factory=dict)  # stair cell → blob

    def stair_rooms_for_level(self, level: int) -> list[StairPlan]:
        """Stairs whose rooms belong to the given level (sorted by cell)."""
        out = []
        for sp in sorted(self.stairs.values(), key=lambda s: s.cell):
            rooms = ([sp.house] if sp.kind is StairKind.CELLAR
                     else [sp.first, sp.second])
            if any(r is not None and self.level_of_cell(r) == level for r in rooms):
                out.append(sp)
        return out

    def level_of_cell(self, cell: int) -> int | None:
        blob = self.blob_of[cell]
        if blob < 0:
            return None
        return self.levels.get(blob)
