"""Rooms: the six room attribute bytes as named fields (Room, StaircaseRoom),
their masks, and the records that name rooms and door pairs."""

from dataclasses import dataclass, replace
from typing import ClassVar, NamedTuple

from .enums import (
    BossSound,
    Direction,
    Enemy,
    Item,
    ItemPosition,
    RoomAction,
    RoomType,
    Side,
    TollOption,
    WallType,
)

# --- Dataclasses ---

@dataclass
class WallSet:
    north: WallType
    east:  WallType
    south: WallType
    west:  WallType

    # Indexed by a Side or by its Direction (Side.EAST and Direction.EAST
    # are both 1 and name the same field).
    _ATTRS: ClassVar[dict[int, str]] = {
        **{side: side.wall_attr for side in Side},
        **{side.direction: side.wall_attr for side in Side},
    }

    def __getitem__(self, side: Side | Direction) -> WallType:
        result: WallType = getattr(self, self._ATTRS[side])
        return result

    def __setitem__(self, side: Side | Direction, value: WallType) -> None:
        setattr(self, self._ATTRS[side], value)


@dataclass
class EnemySpec:
    enemy: Enemy
    is_group: bool = False
    group_members: list[Enemy] | None = None

    def __post_init__(self) -> None:
        if self.is_group:
            assert self.group_members is not None and len(self.group_members) == 8
            self.actual_enemies: list[Enemy] = list(self.group_members)
        else:
            assert self.group_members is None
            self.actual_enemies = [self.enemy]


# --- The six room attribute bytes (aldonunez LevelBlockAttrsA to F) ----------
# One home for the bit layout the spec states its rules on; the field-by-field
# reading of each spec byte expression is docs/glossary/room-byte-fields.md.
PALETTE_SELECTOR_MASK = 0x03   # LevelBlockAttrsA / B bits 1-0
MONSTER_LIST_BITS = 0x3F    # LevelBlockAttrsC bits 5-0
COUNT_INDEX_SHIFT = 6       # LevelBlockAttrsC bits 7-6: the count index
COUNT_INDEX_MASK = 0x03
LAYOUT_ID_MASK = 0x3F       # LevelBlockAttrsD bits 5-0: the layout alone
PUSH_BLOCK_VARIANT = 0x40   # layout-code offset of a layout's push-block variant
# layout codes the passes test with their push-block variant
DIAMOND_STAIRS_PUSH = RoomType.DIAMOND_STAIR_ROOM | PUSH_BLOCK_VARIANT     # $5A
SPIRAL_STAIRS_PUSH = RoomType.SPIRAL_STAIR_ROOM | PUSH_BLOCK_VARIANT       # $5C
TURNSTILE_PUSH = RoomType.TURNSTILE_ROOM | PUSH_BLOCK_VARIANT              # $60
MONSTER_BIT = 0x80          # LevelBlockAttrsD bit 7, in whole layout bytes
PERSON_LAYOUT_BYTE = RoomType.BLACK_ROOM | MONSTER_BIT   # $A6: a person room's whole layout byte
MONSTER_BIT_CODE = 0x40     # enemy codes $40+ carry LevelBlockAttrsD's monster high bit
MONSTER_VALUE_BIT = 0x100   # the monster bit as a ninth bit of a monster value
PERSON_LISTS = range(0x0B, 0x13)   # person monster lists $0B-$12
ITEM_MASK = 0x1F            # LevelBlockAttrsE bits 4-0: the item
BOSS_SOUND_SHIFT = 5        # LevelBlockAttrsE bits 6-5: the boss sound index
BOSS_SOUND_MASK = 0x03
DARK_BIT = 0x80             # LevelBlockAttrsE bit 7
NO_ITEM_CODE = 0x03         # the vanilla "no item" code, as the spec reads item bytes
TRIGGER_MASK = 0x07         # LevelBlockAttrsF bits 2-0: the secret trigger
ITEM_POSITION_SHIFT = 4     # LevelBlockAttrsF bits 5-4: the item position
ITEM_POSITION_MASK = 0x03
STAIR_EXIT_MASK = 0x7F      # a staircase's LevelBlockAttrsA / B bits 6-0: an exit room


@dataclass(frozen=True)
class EnemyInfo:
    """A room's monsters: the whole `LevelBlockAttrsC` byte (monster list and
    count index) plus the monster bit, which the ROM keeps in
    `LevelBlockAttrsD` bit 7 but which belongs to the enemy code. Together
    they are the spec's nine-bit monster value (PS-MONLV-02), so a rule that
    moves or writes a monster value moves or builds one of these."""
    enemy: Enemy
    count_index: int = 0    # index into the owning level's four monster counts

    @classmethod
    def from_monster_value(cls, value: int) -> "EnemyInfo":
        """The monsters a nine-bit monster value names."""
        code = (value & MONSTER_LIST_BITS) | (MONSTER_BIT_CODE if value & MONSTER_VALUE_BIT else 0)
        return cls(Enemy(code), (value >> COUNT_INDEX_SHIFT) & COUNT_INDEX_MASK)

    def with_monster_list(self, monster_list: int) -> "EnemyInfo":
        """The monster list replaced, the monster bit and count kept."""
        code = (self.enemy.value & MONSTER_BIT_CODE) | (monster_list & MONSTER_LIST_BITS)
        return EnemyInfo(Enemy(code), self.count_index)

    # These views are read millions of times a seed by the late gate and the
    # walks, so they use the enemy code as the int it is (an IntEnum's
    # .value is a slow descriptor).

    @property
    def monster_list(self) -> int:
        """The monster byte's low six bits."""
        return self.enemy & MONSTER_LIST_BITS

    @property
    def has_monster_bit(self) -> bool:
        """LevelBlockAttrsD bit 7: the person flag (or a mixed group)."""
        return self.enemy >= MONSTER_BIT_CODE

    @property
    def monster_byte(self) -> int:
        """The whole `LevelBlockAttrsC` byte."""
        return (self.enemy & MONSTER_LIST_BITS) | (self.count_index << COUNT_INDEX_SHIFT)

    @property
    def monster_value(self) -> int:
        """The nine-bit monster value (post-shapes-b2.md PS-MONLV-02): the
        whole monster byte, count index included, plus $100 for the monster
        bit."""
        return self.monster_byte | (MONSTER_VALUE_BIT if self.enemy >= MONSTER_BIT_CODE else 0)

    @property
    def is_person(self) -> bool:
        """A person: the flag with a person list $0B-$12 (QUESTIONS #45.2)."""
        return self.enemy >= MONSTER_BIT_CODE and (self.enemy & MONSTER_LIST_BITS) in PERSON_LISTS


@dataclass(frozen=True)
class LayoutInfo:
    """A room's layout: `LevelBlockAttrsD` bits 6-0, the layout and whether
    it is the push-block variant."""
    room_type: RoomType
    movable_block: bool = False

    @classmethod
    def from_layout_code(cls, layout_code: int) -> "LayoutInfo":
        return cls(RoomType(layout_code & LAYOUT_ID_MASK), bool(layout_code & PUSH_BLOCK_VARIANT))

    @property
    def layout_code(self) -> int:
        """The layout as the spec's layout tables number it: the room type,
        plus $40 for its push-block variant (LevelBlockAttrsD bits 0-6)."""
        return self.room_type | (PUSH_BLOCK_VARIANT if self.movable_block else 0)


@dataclass(frozen=True)
class ItemInfo:
    """What `LevelBlockAttrsE` holds: the room item, the boss sound and
    darkness. They share a byte, and several of ZORA's passes move that byte
    whole, so the boss sound and darkness travel with the item there
    (SH-MAP-06 states this quirk). The spec requires it; do not split them
    to "fix" it."""
    item: Item
    boss_sound: BossSound = BossSound.NONE
    is_dark: bool = False

    @classmethod
    def from_item_byte(cls, item_byte: int) -> "ItemInfo":
        """The contents of a whole item byte as the spec reads one ($03 is
        "no item")."""
        code = item_byte & ITEM_MASK
        return cls(Item.NOTHING if code == NO_ITEM_CODE else Item(code),
                   BossSound((item_byte >> BOSS_SOUND_SHIFT) & BOSS_SOUND_MASK),
                   bool(item_byte & DARK_BIT))

    @property
    def item_code(self) -> int:
        """The item's five bits as the spec reads them ($03 is "no item")."""
        return NO_ITEM_CODE if self.item == Item.NOTHING else self.item.value & ITEM_MASK

    @property
    def item_byte(self) -> int:
        """The whole byte as the spec reads it. The byte actually written is
        the serializer's (game_config.DungeonNothingCode picks the "no item"
        code)."""
        return (self.item_code | (self.boss_sound << BOSS_SOUND_SHIFT)
                | (DARK_BIT if self.is_dark else 0))


@dataclass(frozen=True)
class SecretInfo:
    """What `LevelBlockAttrsF` holds for a dungeon room: the secret trigger
    and the item position. (Its bits 3, 6 and 7 are overworld-only and zero
    in every dungeon room.)"""
    trigger: RoomAction
    item_position: ItemPosition = ItemPosition.POSITION_A

    @classmethod
    def from_trigger_byte(cls, trigger_byte: int) -> "SecretInfo":
        return cls(RoomAction(trigger_byte & TRIGGER_MASK),
                   ItemPosition((trigger_byte >> ITEM_POSITION_SHIFT) & ITEM_POSITION_MASK))

    @property
    def trigger_byte(self) -> int:
        """The whole `LevelBlockAttrsF` byte."""
        return self.trigger | (self.item_position << ITEM_POSITION_SHIFT)


@dataclass
class Room:
    """A dungeon room. Its contents are grouped as the ROM groups them into
    bytes, because the spec moves and tests them by the byte: `enemy_info`
    (LevelBlockAttrsC and the monster bit), `layout_info` (LevelBlockAttrsD
    bits 6-0), `item_info` (LevelBlockAttrsE) and `secret_info`
    (LevelBlockAttrsF). The walls and the two palette selectors share
    LevelBlockAttrsA and B, but no rule moves those bytes whole, so they
    stay separate fields. The single-field properties below read and write
    through the groups."""
    room_num: int
    walls: WallSet
    enemy_info: EnemyInfo
    layout_info: LayoutInfo
    item_info: ItemInfo
    secret_info: SecretInfo
    palette_0: int   # LevelBlockAttrsA bits 1-0: the outer palette selector
    palette_1: int   # LevelBlockAttrsB bits 1-0: the inner palette selector

    @classmethod
    def blank(cls, room_num: int, palette_0: int = 0, palette_1: int = 0,
              walls: "WallSet | None" = None) -> "Room":
        """SH-GRID-17's blank room: walls on all four sides, monster, layout
        and item bytes $00, trigger byte $01."""
        return cls(
            room_num=room_num,
            walls=walls or WallSet(north=WallType.SOLID_WALL, east=WallType.SOLID_WALL,
                                   south=WallType.SOLID_WALL, west=WallType.SOLID_WALL),
            enemy_info=EnemyInfo(Enemy(0)), layout_info=LayoutInfo(RoomType(0)),
            item_info=ItemInfo(Item(0)), secret_info=SecretInfo(RoomAction(1)),
            palette_0=palette_0, palette_1=palette_1
        )

    # --- single fields, through the groups ---

    @property
    def enemy(self) -> Enemy:
        return self.enemy_info.enemy

    @enemy.setter
    def enemy(self, enemy: Enemy) -> None:
        self.enemy_info = replace(self.enemy_info, enemy=enemy)

    @property
    def count_index(self) -> int:
        """LevelBlockAttrsC bits 7-6: the index into the owning level's four
        monster counts (Level.qty_table; Level.enemy_quantity gives the count)."""
        return self.enemy_info.count_index

    @count_index.setter
    def count_index(self, count_index: int) -> None:
        self.enemy_info = replace(self.enemy_info, count_index=count_index)

    @property
    def room_type(self) -> RoomType:
        return self.layout_info.room_type

    @room_type.setter
    def room_type(self, room_type: RoomType) -> None:
        self.layout_info = replace(self.layout_info, room_type=room_type)

    @property
    def movable_block(self) -> bool:
        return self.layout_info.movable_block

    @movable_block.setter
    def movable_block(self, movable_block: bool) -> None:
        self.layout_info = replace(self.layout_info, movable_block=movable_block)

    @property
    def item(self) -> Item:
        return self.item_info.item

    @item.setter
    def item(self, item: Item) -> None:
        self.item_info = replace(self.item_info, item=item)

    @property
    def boss_sound(self) -> BossSound:
        return self.item_info.boss_sound

    @boss_sound.setter
    def boss_sound(self, boss_sound: BossSound) -> None:
        self.item_info = replace(self.item_info, boss_sound=boss_sound)

    @property
    def is_dark(self) -> bool:
        return self.item_info.is_dark

    @is_dark.setter
    def is_dark(self, is_dark: bool) -> None:
        self.item_info = replace(self.item_info, is_dark=is_dark)

    @property
    def room_action(self) -> RoomAction:
        return self.secret_info.trigger

    @room_action.setter
    def room_action(self, trigger: RoomAction) -> None:
        self.secret_info = replace(self.secret_info, trigger=trigger)

    @property
    def item_position(self) -> ItemPosition:
        return self.secret_info.item_position

    @item_position.setter
    def item_position(self, item_position: ItemPosition) -> None:
        self.secret_info = replace(self.secret_info, item_position=item_position)

    # --- the room as the spec's rules read it ---

    @property
    def monster_list(self) -> int:
        """The monster byte's low six bits."""
        return self.enemy_info.enemy & MONSTER_LIST_BITS

    @property
    def has_monster_bit(self) -> bool:
        """LevelBlockAttrsD bit 7: the person flag (or a mixed group)."""
        return self.enemy_info.enemy >= MONSTER_BIT_CODE

    @property
    def monster_byte(self) -> int:
        """The whole `LevelBlockAttrsC` byte."""
        return self.enemy_info.monster_byte

    @property
    def monster_value(self) -> int:
        """The nine-bit monster value (post-shapes-b2.md PS-MONLV-02)."""
        return self.enemy_info.monster_value

    @property
    def is_person(self) -> bool:
        """A person: the flag with a person list $0B-$12 (QUESTIONS #45.2)."""
        return self.enemy_info.is_person

    # The four views below are the hottest in the late gate and the walks;
    # each reads its group once instead of going through other properties.

    @property
    def is_person_room(self) -> bool:
        """A person room: the Black room ($26) with the person flag."""
        return (self.layout_info.room_type == RoomType.BLACK_ROOM
                and self.enemy_info.enemy >= MONSTER_BIT_CODE)

    @property
    def layout_code(self) -> int:
        """The layout as the spec's layout tables number it: the room type,
        plus $40 for its push-block variant (LevelBlockAttrsD bits 0-6)."""
        layout = self.layout_info
        return layout.room_type | (PUSH_BLOCK_VARIANT if layout.movable_block else 0)

    @property
    def layout_byte(self) -> int:
        """The whole `LevelBlockAttrsD` byte: the layout code and the
        monster bit."""
        layout = self.layout_info
        return (layout.room_type | (PUSH_BLOCK_VARIANT if layout.movable_block else 0)
                | (MONSTER_BIT if self.enemy_info.enemy >= MONSTER_BIT_CODE else 0))

    @property
    def item_byte(self) -> int:
        """The whole `LevelBlockAttrsE` byte as the spec reads it."""
        return self.item_info.item_byte

    @property
    def trigger_byte(self) -> int:
        """The whole `LevelBlockAttrsF` byte."""
        return self.secret_info.trigger_byte

    @property
    def item_appears_on_clear(self) -> bool:
        """The real "drops on clear": trigger 7 re-activates the room item
        once all foes are dead (aldonunez CheckUnderworldSecrets)."""
        return self.room_action == RoomAction.ALL_DEAD_ITEM

    @property
    def item_hidden_at_load(self) -> bool:
        """CreateRoomObjects deactivates the room item at load for the
        no-item code and for triggers 3 (last boss) and 7 (all dead + item).
        The triforce of power is revealed by Ganon's own death code
        (Ganon_ActivateRoomItem), whatever the trigger."""
        return (self.item == Item.NOTHING
                or self.room_action in (RoomAction.LAST_BOSS,
                                        RoomAction.ALL_DEAD_ITEM))


@dataclass
class StaircaseRoom:
    room_num: int
    room_type: RoomType             # ITEM_STAIRCASE or TRANSPORT_STAIRCASE
    exit_x: int                     # t2 upper 4 bits — X position exiting staircase
    exit_y: int                     # t2 lower 4 bits — Y position exiting staircase
    # ITEM_STAIRCASE fields
    item: Item | None = None
    return_dest: int | None = None   # screen location Link returns to after item
    # an item cellar's B byte (t1 bits 6-0) when it differs from its A byte
    # (a late-gate tail write cleared bits of one of them, A43); None = same
    return_dest_b: int | None = None
    # TRANSPORT_STAIRCASE fields
    left_exit: int | None = None    # left door destination (t0 bits 6-0)
    right_exit: int | None = None   # right door destination (t1 bits 6-0)
    # Preserved raw bytes (not semantically meaningful for staircase rooms)
    t5_raw: int = 0
    # A43: bits the late gate's tail write cleared in the staircase's A and B
    # bytes. The exit fields above keep the rooms the staircase leads to, as
    # the generator's passes read them; the cleared bits are applied only
    # when the bytes are written (exit_bytes). A parsed staircase has none.
    cleared_a_bits: int = 0
    cleared_b_bits: int = 0

    def exit_bytes(self) -> tuple[int, int]:
        """The exit rooms as the ROM's A and B bytes hold them (bits 6-0): a
        transport's two exits, a cellar's return room twice, less the bits
        A43 cleared."""
        if self.room_type == RoomType.TRANSPORT_STAIRCASE:
            exit_a, exit_b = self.left_exit, self.right_exit
        else:
            exit_a = self.return_dest
            exit_b = self.return_dest_b if self.return_dest_b is not None else exit_a
        assert exit_a is not None and exit_b is not None
        return (exit_a & ~self.cleared_a_bits & STAIR_EXIT_MASK,
                exit_b & ~self.cleared_b_bits & STAIR_EXIT_MASK)



class DoorPair(NamedTuple):
    """Two rooms of one level that face each other, named once, from the
    north or west room: axis is the first room's side toward the second,
    Side.EAST or Side.SOUTH."""
    first: int
    second: int
    axis: Side


class RoomPlace(NamedTuple):
    """Where a room is: the index of its level block in GameWorld.blocks
    (0 for levels 1-6, 1 for levels 7-9) and its room number."""
    block: int
    room_number: int


@dataclass
class LifeOrMoneyToll:
    """PS-MERCH-04: the one toll every life-or-money merchant asks for. The
    first option is LIFE or MAX_BOMBS; the second MAX_BOMBS, KEYS or MONEY,
    with its key count (2-4) or rupee price (30-70) where it needs one."""
    first: TollOption
    second: TollOption
    key_cost: int | None = None
    money_cost: int | None = None
