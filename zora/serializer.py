"""
Serializer: GameWorld → Patch

Converts a GameWorld data model back to a ROM Patch. Call serialize_game_world()
to produce a Patch, then Patch.apply() to write it into a ROM bytearray.

Covers all parsed ROM regions:
- Level grids (levels 1-9): room walls, enemies, items, room types
- Level info blocks: palette, qty table, metadata, stairway data
- Overworld screens: destinations, exits, enemy flags, quest visibility
- Cave item + price data (20 caves): shops, take-any, rupee values, door repair
- Cave quote ID table (20 bytes): quote_id per cave slot
- Hint shop slot quote ID table (6 bytes): quote_id per hint shop slot
- Sprite set pointer tables (bank 3): enemy + boss pattern block assignments
- Recorder warp destinations + Y coordinates
- Any-road shortcut screens + start screen
- Armos/coast items, white/magical sword heart requirements
- MMG win/lose prize amounts (9 patch locations)
- Bomb upgrade cost, count, and display tiles
- Quotes (38 hints): pointer table + encoded text
"""

import logging
from dataclasses import dataclass, field

from zora.char_encoding import (
    CHAR_TO_BYTE as _CHAR_TO_BYTE,
)
from zora.char_encoding import (
    QUOTE_BLANK,
    QUOTE_END_BITS,
    QUOTE_LINE1_BIT,
    QUOTE_LINE2_BIT,
)
from zora.data_model import (
    BossSpriteSet,
    CaveDefinition,
    Destination,
    DoorRepairCave,
    Enemy,
    EnemySpriteSet,
    GameWorld,
    HintShop,
    Item,
    ItemCave,
    Level,
    MoneyMakingGameCave,
    Overworld,
    OverworldItem,
    QuestVisibility,
    Quote,
    Room,
    RoomType,
    SecretCave,
    Shop,
    ShopType,
    StaircaseRoom,
    TakeAnyCave,
)
from zora.game_config import HintMode
from zora.rom_layout import (
    OW_SPRITES_ADDRESS,
    ANY_ROAD_SCREENS_ADDRESS,
    ARMOS_ITEM_ADDRESS,
    ARMOS_TABLES_ADDRESS,
    ASM_NOTHING_CODE_PATCH_VALUE,
    BOMB_COST_OFFSET,
    BOMB_COUNT_OFFSET,
    BOMB_DISP_BASE,
    BOMB_DISPLAY_SPACE_TILE,
    BOSS_SET_A_SPRITES_ADDRESS,
    BOSS_SET_B_SPRITES_ADDRESS,
    BOSS_SET_C_SPRITES_ADDRESS,
    BOSS_SET_EXPANSION_SPRITES_ADDRESS,
    BOSS_SPRITE_SET_POINTERS_ADDRESS,
    CAVE_ITEM_DATA_ADDRESS,
    CAVE_NOTHING_CODE,
    CAVE_PRICE_DATA_ADDRESS,
    CAVE_QUOTES_DATA_ADDRESS,
    COAST_ITEM_ADDRESS,
    DOOR_REPAIR_CHARGE_ADDRESS,
    DUNGEON_COMMON_SPRITES_ADDRESS,
    DUNGEON_NOTHING_CODE,
    ENEMY_SET_A_SPRITES_ADDRESS,
    ENEMY_SET_B_SPRITES_ADDRESS,
    ENEMY_SET_C_SPRITES_ADDRESS,
    EXT_BANK1_ROM_START,
    EXT_HINT_CPU_BASE,
    EXT_HINT_DATA_ROM_END,
    EXT_HINT_DATA_ROM_START,
    HINT_SHOP_QUOTES_ADDRESS,
    LEVEL_1_6_DATA_ADDRESS,
    LEVEL_1_6_DATA_ADDRESS_Q2,
    LEVEL_7_9_DATA_ADDRESS,
    LEVEL_7_9_DATA_ADDRESS_Q2,
    LEVEL_INFO_ADDRESS,
    LEVEL_INFO_SIZE,
    LEVEL_SPRITE_SET_POINTERS_ADDRESS,
    LEVEL_TABLE_SIZE,
    MAGICAL_SWORD_REQUIREMENT_ADDRESS,
    MAZE_DIRECTIONS_ADDRESS,
    MMG_LOSE_LARGE_OFFSET,
    MMG_LOSE_SMALL_2_OFFSET,
    MMG_LOSE_SMALL_OFFSET,
    MMG_WIN_LARGE_OFFSET_A,
    MMG_WIN_LARGE_OFFSET_B,
    MMG_WIN_LARGE_OFFSET_C,
    MMG_WIN_SMALL_OFFSET_A,
    MMG_WIN_SMALL_OFFSET_B,
    MMG_WIN_SMALL_OFFSET_C,
    OVERWORLD_DATA_ADDRESS,
    QUOTE_DATA_ADDRESS,
    RECORDER_WARP_DESTINATIONS_ADDRESS,
    RECORDER_WARP_Y_COORDINATES_ADDRESS,
    START_POSITION_Y_ADDRESS,
    START_SCREEN_ADDRESS,
    TILE_MAPPING_DATA_ADDRESS,
    TILE_MAPPING_POINTERS_ADDRESS,
    VANILLA_HINT_TEXT_MAX_BYTES,
    WHITE_SWORD_REQUIREMENT_ADDRESS,
    AQUAMENTUS_HP_ADDRESS,
    AQUAMENTUS_SP_ADDRESS,
    BOSS_HP_FIRST_ENEMY_VALUE,
    BOSS_HP_NIBBLE_COUNT,
    BOSS_HP_TABLE_ADDRESS,
    BOSS_HP_TABLE_SIZE,
    ENEMY_HP_NIBBLE_COUNT,
    ENEMY_HP_TABLE_ADDRESS,
    ENEMY_HP_TABLE_SIZE,
    GANON_HP_ADDRESS,
    GLEEOK_HP_ADDRESS,
    MIXED_ENEMY_DATA_ADDRESS,
    PATRA_HP_ADDRESS,
)

log = logging.getLogger(__name__)


@dataclass
class Patch:
    data: dict[int, bytes] = field(default_factory=dict)

    def add(self, address: int, bytes_: bytes | bytearray) -> None:
        self.data[address] = bytes(bytes_)

    def merge(self, other: "Patch") -> "Patch":
        """Return a new Patch combining self and other.
        Raises ValueError if any offset appears in both."""
        conflicts = self.data.keys() & other.data.keys()
        if conflicts:
            raise ValueError(
                f"Patch merge conflict at offsets: "
                f"{[hex(a) for a in sorted(conflicts)]}"
            )
        return Patch(data={**self.data, **other.data})

    def apply(self, rom: bytearray) -> None:
        for address, bytes_ in self.data.items():
            rom[address:address + len(bytes_)] = bytes_


# ---------------------------------------------------------------------------
# Level serialization
# ---------------------------------------------------------------------------

def _serialize_level_grid(level: Level, grid: bytearray, level_index: int,
                          change_dungeon_nothing_code: bool = False) -> None:
    """Write one level's room data into the 6-table grid bytearray in-place."""

    def qty_code(qty: int) -> int:
        return level.qty_table.index(qty)

    def item_byte(item: Item) -> int:
        if item == Item.NOTHING:
            return ASM_NOTHING_CODE_PATCH_VALUE if change_dungeon_nothing_code else DUNGEON_NOTHING_CODE
        return item.value & 0x1F

    room_map: dict[int, Room] = {r.room_num: r for r in level.rooms}
    staircase_map: dict[int, StaircaseRoom] = {r.room_num: r for r in level.staircase_rooms}

    for room_num in range(LEVEL_TABLE_SIZE):
        sc = staircase_map.get(room_num)
        if sc is not None:
            if sc.room_type == RoomType.TRANSPORT_STAIRCASE:
                assert sc.left_exit is not None and sc.right_exit is not None
                t0 = sc.left_exit & 0x7F
                t1 = sc.right_exit & 0x7F
            else:
                assert sc.return_dest is not None
                t0 = sc.return_dest & 0x7F
                t1 = sc.return_dest & 0x7F
            t2 = ((sc.exit_x & 0x0F) << 4) | (sc.exit_y & 0x0F)
            t3 = sc.room_type & 0x3F
            t4 = (
                (sc.item.value & 0x1F)
                if sc.room_type == RoomType.ITEM_STAIRCASE and sc.item is not None
                else item_byte(Item.NOTHING)
            )
            t5 = sc.t5_raw
        else:
            room = room_map.get(room_num)
            if room is None:
                continue
            t0 = ((room.walls.north & 0x07) << 5) | ((room.walls.south & 0x07) << 2) | (room.palette_0 & 0x03)
            t1 = ((room.walls.west & 0x07) << 5) | ((room.walls.east & 0x07) << 2) | (room.palette_1 & 0x03)
            enemy_code = room.enemy_spec.enemy.value
            t2_enemy_bits = (enemy_code - 0x40) if enemy_code >= 0x40 else enemy_code
            t2 = (qty_code(room.enemy_quantity) << 6) | (t2_enemy_bits & 0x3F)
            mixed_bit   = 0x80 if enemy_code >= 0x40 else 0
            movable_bit = 0x40 if room.movable_block else 0x00
            t3 = mixed_bit | movable_bit | (room.room_type & 0x3F)
            dark_bit = 0x80 if room.is_dark else 0
            cry2_bit = 0x40 if room.boss_cry_2 else 0
            cry1_bit = 0x20 if room.boss_cry_1 else 0
            t4 = dark_bit | cry2_bit | cry1_bit | item_byte(room.item)
            t5 = ((room.item_position & 0x03) << 4) | (room.room_action & 0x07)

        grid[0 * LEVEL_TABLE_SIZE + room_num] = t0
        grid[1 * LEVEL_TABLE_SIZE + room_num] = t1
        grid[2 * LEVEL_TABLE_SIZE + room_num] = t2
        grid[3 * LEVEL_TABLE_SIZE + room_num] = t3
        grid[4 * LEVEL_TABLE_SIZE + room_num] = t4
        grid[5 * LEVEL_TABLE_SIZE + room_num] = t5


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

    # The compass points to the room containing the triforce (or Zelda in L9).
    # If the triforce is in an item staircase, point to the room with the
    # stairway down (return_dest) rather than the staircase room itself,
    # since the staircase room isn't visible on the map.
    compass_room = 0x00
    for room in level.rooms:
        if room.item == Item.TRIFORCE or room.enemy_spec.enemy == Enemy.THE_KIDNAPPED:
            compass_room = room.room_num
            break
    else:
        for sr in level.staircase_rooms:
            if sr.room_type == RoomType.ITEM_STAIRCASE and sr.item == Item.TRIFORCE:
                assert sr.return_dest is not None
                compass_room = sr.return_dest
                break
    block[0x30] = compass_room

    block[0x31] = level.screen_status_ram_offset[0]
    block[0x32] = level.screen_status_ram_offset[1]
    block[0x33] = level.rom_level_num
    for i, b in enumerate(level.stairway_data_raw):
        block[0x34 + i] = b
    block[0x3E] = level.boss_room


# ---------------------------------------------------------------------------
# Overworld serialization
# ---------------------------------------------------------------------------

def _serialize_overworld(overworld: Overworld, grid: bytearray) -> None:
    """Write overworld screen data into the 6-table grid bytearray in-place."""
    for screen in overworld.screens:
        s = screen.screen_num
        t0 = ((screen.exit_x_position & 0x0F) << 4) \
           | (0x08 if screen.has_zola else 0) \
           | (0x04 if screen.has_ocean_sound else 0) \
           | (screen.outer_palette & 0x03)
        t1 = ((screen.destination & 0x3F) << 2) | (screen.inner_palette & 0x03)
        enemy_code = screen.enemy_spec.enemy.value
        enemy_low  = (enemy_code - 0x40) if enemy_code >= 0x40 else enemy_code
        t2 = (overworld.qty_table.index(screen.enemy_quantity) << 6) | (enemy_low & 0x3F)
        mixed_bit = 0x80 if enemy_code >= 0x40 else 0
        t3 = mixed_bit | (screen.screen_code & 0x7F)
        # t4 is the cave item table region — written entirely by _serialize_cave_data
        if screen.quest_visibility == QuestVisibility.BOTH_QUESTS:
            qv = 0
        elif screen.quest_visibility == QuestVisibility.FIRST_QUEST:
            qv = 1
        else:
            qv = 2
        t5 = ((qv & 0x03) << 6) \
           | ((screen.stairs_position_code & 0x03) << 4) \
           | (0x08 if screen.enemies_from_sides else 0) \
           | (screen.exit_y_position & 0x07)
        grid[0 * 0x80 + s] = t0
        grid[1 * 0x80 + s] = t1
        grid[2 * 0x80 + s] = t2
        grid[3 * 0x80 + s] = t3
        # grid[4 * 0x80 + s] intentionally not written here
        grid[5 * 0x80 + s] = t5


# ---------------------------------------------------------------------------
# Cave data serialization
# ---------------------------------------------------------------------------

# Flag bit constants for cave item bytes — derived from cave type, not stored in model.
# Byte 0: 0x80 = negative prices, 0x40 = heart container condition
# Byte 1: 0x80 = rupees received/lost, 0x40 = pay for hint
# Byte 2: 0x80 = prices displayed, 0x40 = items displayed
_NOTHING = CAVE_NOTHING_CODE   # 0x3F = unused slot

def _item_code(item: Item) -> int:
    """Encode an Item as a 6-bit cave item code. NOTHING → CAVE_NOTHING_CODE."""
    return CAVE_NOTHING_CODE if item == Item.NOTHING else (item.value & 0x3F)


def _serialize_cave_data(overworld: Overworld, patch: "Patch") -> None:
    """
    Build 60-byte item and price buffers from scratch using the caves list,
    write the cave quote ID table, hint shop slot quote ID table, and
    door repair charge to patch.

    Flag bits in item bytes are fully determined by cave type — no raw bytes
    needed. Layout matches ROM table at CAVE_ITEM_DATA_ADDRESS.
    """
    items  = bytearray(60)   # 20 caves x 3 bytes
    prices = bytearray(60)

    # Build a lookup from Destination → cave object for clean access
    cave_by_dest: dict[Destination, CaveDefinition] = {c.destination: c for c in overworld.caves}

    def get(dest: Destination) -> CaveDefinition | None:
        return cave_by_dest.get(dest)

    # Cave 0: Wood Sword — byte 0 = optional extra item, byte 1 = main item, byte 2 = nothing
    if c := get(Destination.WOOD_SWORD_CAVE):
        assert isinstance(c, ItemCave)
        items[0*3+0] = 0x00 | _item_code(c.maybe_extra_candle)
        items[0*3+1] = 0x00 | _item_code(c.item)
        items[0*3+2] = 0x40 | 0x7F              # items displayed, external marker

    # Cave 1: Take Any — byte 0 = left item, byte 1 = middle item, byte 2 = right item
    if c := get(Destination.TAKE_ANY):
        assert isinstance(c, TakeAnyCave)
        items[1*3+0] = 0x00 | _item_code(c.items[0])
        items[1*3+1] = 0x00 | _item_code(c.items[1])
        items[1*3+2] = 0x40 | _item_code(c.items[2])  # items displayed

    # Cave 2: White Sword — byte 0 = heart flag | optional extra item, byte 1 = main item, byte 2 = nothing
    if c := get(Destination.WHITE_SWORD_CAVE):
        assert isinstance(c, ItemCave)
        heart_flag = 0x40 if c.heart_requirement > 0 else 0x00
        items[2*3+0] = heart_flag | _item_code(c.maybe_extra_candle)
        items[2*3+1] = 0x00 | _item_code(c.item)
        items[2*3+2] = 0x40 | 0x7F

    # Cave 3: Magical Sword — byte 0 = heart flag | optional extra item, byte 1 = main item, byte 2 = nothing
    if c := get(Destination.MAGICAL_SWORD_CAVE):
        assert isinstance(c, ItemCave)
        heart_flag = 0x40 if c.heart_requirement > 0 else 0x00
        items[3*3+0] = heart_flag | _item_code(c.maybe_extra_candle)
        items[3*3+1] = 0x00 | _item_code(c.item)
        items[3*3+2] = 0x40 | 0x7F

    # Cave 4: Any Road — all nothing (hint only)
    items[4*3+0] = _NOTHING
    items[4*3+1] = _NOTHING
    items[4*3+2] = _NOTHING

    # Cave 5: Lost Hills Hint — all nothing (hint only)
    items[5*3+0] = _NOTHING
    items[5*3+1] = _NOTHING
    items[5*3+2] = _NOTHING

    # Cave 6: Money Making Game — all nothing in items; prices = bet amounts
    if c := get(Destination.MONEY_MAKING_GAME):
        assert isinstance(c, MoneyMakingGameCave)
        items[6*3+0] = 0x80 | 0x18        # negative prices flag
        items[6*3+1] = 0x80 | 0x18        # rupees received/lost flag
        items[6*3+2] = 0x80 | 0x40 | 0x18  # prices + items displayed flag
        prices[6*3+0] = c.bet_low
        prices[6*3+1] = c.bet_mid
        prices[6*3+2] = c.bet_high

    # Cave 7: Door Repair — all nothing in items; price from separate address
    items[7*3+0] = _NOTHING
    items[7*3+1] = _NOTHING
    items[7*3+2] = _NOTHING

    # Cave 8: Letter Cave — slot 1 = item
    if c := get(Destination.LETTER_CAVE):
        assert isinstance(c, ItemCave)
        items[8*3+0] = 0x00 | _NOTHING
        items[8*3+1] = 0x00 | _item_code(c.item)
        items[8*3+2] = 0x40 | 0x7F

    # Cave 9: Dead Woods Hint — all nothing (hint only)
    items[9*3+0] = _NOTHING
    items[9*3+1] = _NOTHING
    items[9*3+2] = _NOTHING

    # Cave 10: Potion Shop (SHOP_E) — slots 0,2 = items; slot 1 unused; letter required
    if c := get(Destination.POTION_SHOP):
        assert isinstance(c, Shop)
        items[10*3+0]  = 0x00 | _item_code(c.items[0].item)
        items[10*3+1]  = _NOTHING            # unused middle slot
        items[10*3+2]  = 0xC0 | _item_code(c.items[1].item)  # prices+items displayed
        prices[10*3+0] = c.items[0].price
        prices[10*3+1] = 0x00
        prices[10*3+2] = c.items[1].price

    # Cave 11: Hint Shop 1 — prices only; item bytes use 0x18 as the slot sentinel
    if c := get(Destination.HINT_SHOP_1):
        assert isinstance(c, HintShop)
        items[11*3+0]  = 0x80 | 0x18   # negative prices
        items[11*3+1]  = 0x40 | 0x18   # pay for hint
        items[11*3+2]  = 0xC0 | 0x18   # prices+items displayed
        prices[11*3+0] = c.hints[0].price
        prices[11*3+1] = c.hints[1].price
        prices[11*3+2] = c.hints[2].price

    # Cave 12: Hint Shop 2 — same structure as Hint Shop 1
    if c := get(Destination.HINT_SHOP_2):
        assert isinstance(c, HintShop)
        items[12*3+0]  = 0x80 | 0x18
        items[12*3+1]  = 0x40 | 0x18
        items[12*3+2]  = 0xC0 | 0x18
        prices[12*3+0] = c.hints[0].price
        prices[12*3+1] = c.hints[1].price
        prices[12*3+2] = c.hints[2].price

    # Caves 13-16: Shops A-D — all 3 item slots used
    for dest, shop_type in [
        (Destination.SHOP_1, ShopType.SHOP_A),
        (Destination.SHOP_2, ShopType.SHOP_B),
        (Destination.SHOP_3, ShopType.SHOP_C),
        (Destination.SHOP_4, ShopType.SHOP_D),
    ]:
        c = get(dest)
        if c is None:
            continue
        assert isinstance(c, Shop)
        cave_idx = 13 + [ShopType.SHOP_A, ShopType.SHOP_B,
                          ShopType.SHOP_C, ShopType.SHOP_D].index(shop_type)
        items[cave_idx*3+0]  = 0x00 | _item_code(c.items[0].item)
        items[cave_idx*3+1]  = 0x00 | _item_code(c.items[1].item)
        items[cave_idx*3+2]  = 0xC0 | _item_code(c.items[2].item)  # prices+items displayed
        prices[cave_idx*3+0] = c.items[0].price
        prices[cave_idx*3+1] = c.items[1].price
        prices[cave_idx*3+2] = c.items[2].price

    # Caves 17-19: Secrets — rupee value in price byte 1; item bytes carry rupees flag
    for cave_idx, dest in [
        (17, Destination.MEDIUM_SECRET),
        (18, Destination.LARGE_SECRET),
        (19, Destination.SMALL_SECRET),
    ]:
        c = get(dest)
        if c is None:
            continue
        assert isinstance(c, SecretCave)
        items[cave_idx*3+0]  = 0x00 | _NOTHING
        items[cave_idx*3+1]  = 0x80 | 0x18   # rupees received/lost flag; 0x18 = slot sentinel
        items[cave_idx*3+2]  = 0x40 | 0x7F       # items displayed, external
        prices[cave_idx*3+1] = c.rupee_value

    patch.add(CAVE_ITEM_DATA_ADDRESS,  bytes(items))
    patch.add(CAVE_PRICE_DATA_ADDRESS, bytes(prices))

    # Door repair charge — separate ROM location
    if c := get(Destination.DOOR_REPAIR):
        assert isinstance(c, DoorRepairCave)
        patch.add(DOOR_REPAIR_CHARGE_ADDRESS, bytes([c.cost]))

    # Armos and coast items — separate ROM locations
    if c := get(Destination.ARMOS_ITEM):
        assert isinstance(c, OverworldItem)
        patch.add(ARMOS_ITEM_ADDRESS, bytes([c.item.value]))
    if c := get(Destination.COAST_ITEM):
        assert isinstance(c, OverworldItem)
        patch.add(COAST_ITEM_ADDRESS, bytes([c.item.value]))

    # Heart requirements for sword caves — separate ROM locations
    if c := get(Destination.WHITE_SWORD_CAVE):
        assert isinstance(c, ItemCave)
        patch.add(WHITE_SWORD_REQUIREMENT_ADDRESS, bytes([(c.heart_requirement - 1) * 16]))
    if c := get(Destination.MAGICAL_SWORD_CAVE):
        assert isinstance(c, ItemCave)
        patch.add(MAGICAL_SWORD_REQUIREMENT_ADDRESS, bytes([(c.heart_requirement - 1) * 16]))

    # Cave quote ID table (20 bytes) — low 6 bits per slot, top 2 bits preserved from ROM.
    # We only control the low 6 bits (quote_id * 2); top 2 bits are display flags owned
    # by the ROM engine.  These constants must contain ONLY the top-2-bit flags (& 0xC0),
    # not the full vanilla byte — otherwise old quote_id bits leak through the OR.
    cave_quote_display_flags = [
        0x40,  # 0  Wood Sword
        0x40,  # 1  Take Any
        0x40,  # 2  White Sword
        0x40,  # 3  Magical Sword
        0x00,  # 4  Any Road
        0x00,  # 5  Lost Hills Hint
        0x40,  # 6  MMG
        0x00,  # 7  Door Repair
        0x40,  # 8  Letter Cave
        0x00,  # 9  Dead Woods Hint
        0xC0,  # 10 Potion Shop
        0xC0,  # 11 Hint Shop 1
        0xC0,  # 12 Hint Shop 2
        0xC0,  # 13 Shop 1
        0xC0,  # 14 Shop 2
        0xC0,  # 15 Shop 3
        0xC0,  # 16 Shop 4
        0x40,  # 17 Medium Secret
        0x40,  # 18 Large Secret
        0x40,  # 19 Small Secret
    ]
    quote_table = bytearray(20)
    for cave_idx in range(20):
        c = cave_by_dest.get(Destination(0x10 + cave_idx))
        qid = getattr(c, "quote_id", 0) if c is not None else 0
        quote_table[cave_idx] = cave_quote_display_flags[cave_idx] | ((qid * 2) & 0x3F)
    patch.add(CAVE_QUOTES_DATA_ADDRESS, bytes(quote_table))

    # Hint shop slot quote ID table (6 bytes)
    hs1 = cave_by_dest.get(Destination.HINT_SHOP_1)
    hs2 = cave_by_dest.get(Destination.HINT_SHOP_2)
    hint_shop_quotes = bytearray(6)
    if hs1 is not None:
        assert isinstance(hs1, HintShop)
        hint_shop_quotes[0] = (hs1.hints[0].quote_id * 2) & 0x3F
        hint_shop_quotes[1] = (hs1.hints[1].quote_id * 2) & 0x3F
        hint_shop_quotes[2] = (hs1.hints[2].quote_id * 2) & 0x3F
    if hs2 is not None:
        assert isinstance(hs2, HintShop)
        hint_shop_quotes[3] = (hs2.hints[0].quote_id * 2) & 0x3F
        hint_shop_quotes[4] = (hs2.hints[1].quote_id * 2) & 0x3F
        hint_shop_quotes[5] = (hs2.hints[2].quote_id * 2) & 0x3F
    patch.add(HINT_SHOP_QUOTES_ADDRESS, bytes(hint_shop_quotes))


# ---------------------------------------------------------------------------
# MMG prize serialization
# ---------------------------------------------------------------------------

def _serialize_mmg_prizes(overworld: Overworld, patch: Patch) -> None:
    """Write MMG win/lose amounts to all 9 patch locations."""
    cave_by_dest = {c.destination: c for c in overworld.caves}
    c = cave_by_dest.get(Destination.MONEY_MAKING_GAME)
    if c is None:
        return
    assert isinstance(c, MoneyMakingGameCave)
    patch.add(MMG_LOSE_SMALL_OFFSET,   bytes([c.lose_small]))
    patch.add(MMG_LOSE_SMALL_2_OFFSET, bytes([c.lose_small_2]))
    patch.add(MMG_LOSE_LARGE_OFFSET,   bytes([c.lose_large]))
    patch.add(MMG_WIN_SMALL_OFFSET_A,  bytes([c.win_small]))
    patch.add(MMG_WIN_SMALL_OFFSET_B,  bytes([c.win_small]))
    patch.add(MMG_WIN_SMALL_OFFSET_C,  bytes([c.win_small]))
    patch.add(MMG_WIN_LARGE_OFFSET_A,  bytes([c.win_large]))
    patch.add(MMG_WIN_LARGE_OFFSET_B,  bytes([c.win_large]))
    patch.add(MMG_WIN_LARGE_OFFSET_C,  bytes([c.win_large]))


# ---------------------------------------------------------------------------
# Bomb upgrade serialization
# ---------------------------------------------------------------------------

def _serialize_bomb_upgrade(overworld: Overworld, patch: Patch) -> None:
    """Write bomb upgrade cost, count, and display tiles to patch."""
    bu = overworld.bomb_upgrade
    hundreds = bu.cost // 100
    tens     = (bu.cost % 100) // 10
    ones     = bu.cost % 10
    hundreds_tile = BOMB_DISPLAY_SPACE_TILE if hundreds == 0 else hundreds
    patch.add(BOMB_COST_OFFSET,  bytes([bu.cost]))
    patch.add(BOMB_COUNT_OFFSET, bytes([bu.count]))
    patch.add(BOMB_DISP_BASE,    bytes([hundreds_tile, tens, ones]))


# ---------------------------------------------------------------------------
# Quotes serialization
# ---------------------------------------------------------------------------

_QUOTE_PAD_BYTE = 0x25   # '~' tile — renders as blank space in-game
_NES_LINE_WIDTH = 24     # total rendered columns per line on the NES
_QUOTE_MAX_TEXT_COLS = 22  # usable text columns per line (24 total minus 2 border cols)


def _center_line(line: str) -> list[int]:
    """Return the encoded bytes for one centered hint line, with leading pad bytes."""
    line = line.rstrip()[:_QUOTE_MAX_TEXT_COLS]
    line_len = len(line)
    left_padding = (_NES_LINE_WIDTH - line_len) // 2

    result = [_QUOTE_PAD_BYTE] * left_padding
    for char in line:
        result.append(_CHAR_TO_BYTE.get(char.upper(), _QUOTE_PAD_BYTE))
    return result


def _encode_quote(text: str, center: bool = False) -> list[int]:
    """Encode a pipe-separated quote string into ROM bytes.

    When center=True each line is padded with leading 0x25 bytes to visually
    center it in the 24-column hint display. Use this for randomized hints
    (COMMUNITY / HELPFUL modes). Leave False for vanilla text, which already
    has its own hand-crafted spacing.
    """
    if not text:
        return [QUOTE_BLANK]
    lines = text.split("|")
    result: list[int] = []
    for line_idx, line in enumerate(lines):
        if center:
            if not line.strip():
                continue
            result.extend(_center_line(line))
        else:
            for char in line:
                result.append(_CHAR_TO_BYTE.get(char.upper(), _QUOTE_PAD_BYTE))
        if result and line_idx < len(lines) - 1:
            if line_idx == 0:
                result[-1] |= QUOTE_LINE1_BIT
            elif line_idx == 1:
                result[-1] |= QUOTE_LINE2_BIT
    if result:
        result[-1] |= QUOTE_END_BITS
    return result


def _serialize_quotes(quotes: list[Quote],
                      max_text_bytes: int | None = None,
                      center: bool = False) -> bytes:
    """Produce the full quotes_data block: pointer table (n*2 bytes) + encoded text.

    The pointer table is indexed by quote_id (not by list position), so quote_ids
    must be unique and contiguous from 0 to max_id. Gaps (e.g. id=38 missing when
    ids 39-43 exist) receive a pointer to a blank quote.
    """
    if not quotes:
        return b""
    max_id = max(q.quote_id for q in quotes)
    ptr_table_size = (max_id + 1) * 2
    ptr_table = bytearray(ptr_table_size)
    text_data = bytearray()

    # Build a lookup by quote_id
    by_id: dict[int, Quote] = {q.quote_id: q for q in quotes}

    for qid in range(max_id + 1):
        quote = by_id.get(qid)
        if quote is not None:
            raw_text = quote.text
        else:
            raw_text = ""  # gap — write blank pointer
        encoded = _encode_quote(raw_text, center=center)
        projected = len(text_data) + len(encoded)
        if max_text_bytes is not None and projected > max_text_bytes:
            log.warning(
                "Quote id=%d would overflow vanilla hint bank at byte "
                "%d/%d. Writing blank.",
                qid, projected, max_text_bytes,
            )
            encoded = _encode_quote("")
        data_offset = ptr_table_size + len(text_data)
        ptr_table[qid * 2]     = data_offset & 0xFF
        ptr_table[qid * 2 + 1] = ((data_offset >> 8) & 0xFF) | 0x80
        text_data.extend(encoded)

    return bytes(ptr_table) + bytes(text_data)


def _serialize_hints(game_world: GameWorld, patch: Patch,
                     hint_mode: HintMode) -> None:
    """Write hint data to patch, branching on hint_mode."""
    if not game_world.quotes:
        return

    use_extended_hint_bank = hint_mode in (HintMode.COMMUNITY, HintMode.HELPFUL)

    if not use_extended_hint_bank:
        patch.add(
            QUOTE_DATA_ADDRESS,
            _serialize_quotes(game_world.quotes,
                              max_text_bytes=VANILLA_HINT_TEXT_MAX_BYTES,
                              center=False),
        )
        return

    write_pos = EXT_HINT_DATA_ROM_START
    max_id = max(q.quote_id for q in game_world.quotes)
    ptr_table_size = (max_id + 1) * 2
    ptr_table = bytearray(ptr_table_size)
    text_writes: dict[int, bytes] = {}
    by_id: dict[int, Quote] = {q.quote_id: q for q in game_world.quotes}

    for qid in range(max_id + 1):
        quote = by_id.get(qid)
        raw_text = (quote.text if quote.text else "") if quote is not None else ""
        encoded = bytes(_encode_quote(raw_text, center=True))
        if write_pos + len(encoded) > EXT_HINT_DATA_ROM_END:
            log.warning(
                "Extended hint bank full at quote id=%d. Writing blank.",
                qid,
            )
            encoded = bytes(_encode_quote(""))
            if write_pos + len(encoded) > EXT_HINT_DATA_ROM_END:
                log.error("No space remaining in extended hint bank. Stopping.")
                break
        cpu_addr = EXT_HINT_CPU_BASE + (write_pos - EXT_BANK1_ROM_START)
        ptr_table[qid * 2]     = cpu_addr & 0xFF
        ptr_table[qid * 2 + 1] = (cpu_addr >> 8) & 0xFF
        text_writes[write_pos] = encoded
        write_pos += len(encoded)

    patch.add(QUOTE_DATA_ADDRESS, bytes(ptr_table))
    for rom_off, data in text_writes.items():
        patch.add(rom_off, data)

    used      = write_pos - EXT_HINT_DATA_ROM_START
    available = EXT_HINT_DATA_ROM_END - EXT_HINT_DATA_ROM_START
    log.info(
        "Extended hint bank: %d/%d bytes used (%.1f%%), %d remaining.",
        used, available, 100 * used / available, available - used,
    )


# ---------------------------------------------------------------------------
# Sprite set pointer table serialization
# ---------------------------------------------------------------------------

# CPU addresses of pattern blocks in bank 3 (maps to CPU 0x8000-0xBFFF).
# These belong here, not in data_model — they're a serialization detail.
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
    for enemy in _TILE_TABLE_ENEMIES:
        all_entries.append((ed.tile_pointers[enemy], ed.tile_frames[enemy]))
    for i in range(_OVERWORLD_NPC_SLOT_COUNT):
        all_entries.append((ed.overworld_npc_pointers[i], ed.overworld_npc_frames[i]))

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
    patch.add(AQUAMENTUS_HP_ADDRESS, bytes([(ed.aquamentus_hp & 0x0F) << 4]))
    patch.add(AQUAMENTUS_SP_ADDRESS, bytes([(ed.aquamentus_sp & 0x0F) << 4]))
    patch.add(GANON_HP_ADDRESS,      bytes([(ed.ganon_hp & 0x0F) << 4]))
    patch.add(GLEEOK_HP_ADDRESS,     bytes([(ed.gleeok_hp & 0x0F) << 4]))
    patch.add(PATRA_HP_ADDRESS,      bytes([(ed.patra_hp & 0x0F) << 4]))


# ---------------------------------------------------------------------------
# Top-level serialize
# ---------------------------------------------------------------------------

def serialize_game_world(game_world: GameWorld, original_bins_bytes: dict[str, bytes],
                         hint_mode: HintMode = HintMode.VANILLA,
                         change_dungeon_nothing_code: bool = False) -> Patch:
    """
    Produce a Patch from a GameWorld.

    original_bins_bytes: dict mapping bin filename → bytes, used to initialize
    output buffers with original data before overwriting changed fields.

    change_dungeon_nothing_code: when True, Item.NOTHING in dungeon rooms is
    serialized as 0x18 instead of the vanilla 0x03 sentinel, matching the
    NothingCode ASM behavior patch. Set this when config.shuffle_magical_sword
    is True and config.progressive_items is False.
    """
    patch = Patch()

    # --- Level 1-6 grid ---
    grid_1_6 = bytearray(original_bins_bytes["level_1_6_data.bin"])
    for lvl in game_world.levels[:6]:
        _serialize_level_grid(lvl, grid_1_6, lvl.level_num - 1, change_dungeon_nothing_code)
    patch.add(LEVEL_1_6_DATA_ADDRESS, bytes(grid_1_6))

    # --- Level 7-9 grid ---
    grid_7_9 = bytearray(original_bins_bytes["level_7_9_data.bin"])
    for lvl in game_world.levels[6:]:
        _serialize_level_grid(lvl, grid_7_9, lvl.level_num - 7, change_dungeon_nothing_code)
    patch.add(LEVEL_7_9_DATA_ADDRESS, bytes(grid_7_9))

    # --- Level info ---
    level_info = bytearray(original_bins_bytes["level_info.bin"])
    for lvl in game_world.levels:
        offset = lvl.level_num * LEVEL_INFO_SIZE
        block_arr = bytearray(level_info[offset:offset + LEVEL_INFO_SIZE])
        _serialize_level_info(lvl, block_arr)
        level_info[offset:offset + LEVEL_INFO_SIZE] = block_arr
    patch.add(LEVEL_INFO_ADDRESS, bytes(level_info))

    # --- Overworld ---
    grid_ow = bytearray(original_bins_bytes["overworld_data.bin"])
    _serialize_overworld(game_world.overworld, grid_ow)
    patch.add(OVERWORLD_DATA_ADDRESS, bytes(grid_ow))

    # --- Cave data (items, prices, door repair, armos, coast,
    #     heart requirements, quote tables) ---
    _serialize_cave_data(game_world.overworld, patch)

    # --- MMG win/lose prizes ---
    _serialize_mmg_prizes(game_world.overworld, patch)

    # --- Bomb upgrade ---
    _serialize_bomb_upgrade(game_world.overworld, patch)

    # --- Armos statue lookup tables ---
    ow = game_world.overworld
    patch.add(ARMOS_TABLES_ADDRESS, bytes(ow.armos_screen_ids) + bytes(ow.armos_positions))

    # --- Maze direction sequences ---
    maze_bytes = bytes([d.value for d in ow.dead_woods_directions]) \
               + bytes([d.value for d in ow.lost_hills_directions])
    patch.add(MAZE_DIRECTIONS_ADDRESS, maze_bytes)

    # --- Recorder warp data ---
    patch.add(RECORDER_WARP_DESTINATIONS_ADDRESS,  bytes(ow.recorder_warp_destinations))
    patch.add(RECORDER_WARP_Y_COORDINATES_ADDRESS, bytes(ow.recorder_warp_y_coordinates))
    patch.add(ANY_ROAD_SCREENS_ADDRESS,            bytes(ow.any_road_screens))
    patch.add(START_SCREEN_ADDRESS,                bytes([ow.start_screen]))
    patch.add(START_POSITION_Y_ADDRESS,            bytes([ow.start_position_y]))

    # --- Sprite set pointer tables ---
    level_ptrs, boss_ptrs = _serialize_sprite_set_pointers(game_world)
    patch.add(LEVEL_SPRITE_SET_POINTERS_ADDRESS, level_ptrs)
    patch.add(BOSS_SPRITE_SET_POINTERS_ADDRESS,  boss_ptrs)

    # --- Sprite data blocks ---
    sp = game_world.sprites
    patch.add(OW_SPRITES_ADDRESS,              sp.ow_sprites)
    patch.add(ENEMY_SET_B_SPRITES_ADDRESS,    sp.enemy_set_b)
    patch.add(ENEMY_SET_C_SPRITES_ADDRESS,    sp.enemy_set_c)
    patch.add(DUNGEON_COMMON_SPRITES_ADDRESS, sp.dungeon_common)
    patch.add(ENEMY_SET_A_SPRITES_ADDRESS,    sp.enemy_set_a)
    patch.add(BOSS_SET_A_SPRITES_ADDRESS,     sp.boss_set_a)
    patch.add(BOSS_SET_B_SPRITES_ADDRESS,     sp.boss_set_b)
    patch.add(BOSS_SET_C_SPRITES_ADDRESS,     sp.boss_set_c)
    patch.add(BOSS_SET_EXPANSION_SPRITES_ADDRESS, sp.boss_set_expansion)

    # --- Enemy tile maps ---
    ptr_bytes, frame_bytes = _serialize_enemy_tile_data(game_world)
    patch.add(TILE_MAPPING_POINTERS_ADDRESS, ptr_bytes)
    patch.add(TILE_MAPPING_DATA_ADDRESS,     frame_bytes)

    # --- Enemy / boss HP ---
    _serialize_enemy_hp(game_world, patch)

    # --- Mixed enemy group data ---
    if game_world.enemies.mixed_enemy_data:
        patch.add(MIXED_ENEMY_DATA_ADDRESS,
                  bytes(game_world.enemies.mixed_enemy_data))

    # --- Quotes ---
    _serialize_hints(game_world, patch, hint_mode)

    return patch


def serialize_game_world_q2(game_world: GameWorld, original_bins_bytes: dict[str, bytes],
                            change_dungeon_nothing_code: bool = False) -> Patch:
    """Produce a Patch for the second-quest level grids and level info only."""
    patch = Patch()

    grid_1_6 = bytearray(original_bins_bytes["level_1_6_data_q2.bin"])
    for lvl in game_world.levels[:6]:
        _serialize_level_grid(lvl, grid_1_6, lvl.level_num - 1, change_dungeon_nothing_code)
    patch.add(LEVEL_1_6_DATA_ADDRESS_Q2, bytes(grid_1_6))

    grid_7_9 = bytearray(original_bins_bytes["level_7_9_data_q2.bin"])
    for lvl in game_world.levels[6:]:
        _serialize_level_grid(lvl, grid_7_9, lvl.level_num - 7, change_dungeon_nothing_code)
    patch.add(LEVEL_7_9_DATA_ADDRESS_Q2, bytes(grid_7_9))

    level_info = bytearray(original_bins_bytes["level_info_q2.bin"])
    for lvl in game_world.levels:
        offset = lvl.level_num * LEVEL_INFO_SIZE
        block_arr = bytearray(level_info[offset:offset + LEVEL_INFO_SIZE])
        _serialize_level_info(lvl, block_arr)
        level_info[offset:offset + LEVEL_INFO_SIZE] = block_arr
    patch.add(LEVEL_INFO_ADDRESS, bytes(level_info))

    return patch
