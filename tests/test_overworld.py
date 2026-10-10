"""The overworld readers (zora/rom/vanilla_overworld/) against the PRG0 base ROM: each
table's anchor bytes as the disassembly lists them, the game-level facts
the tables must agree with, and the parser's own overworld model."""
import importlib.util
import os
from pathlib import Path

import pytest

from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.rom.game_config import GameConfig, HintMode
from zora.model.game_world import GameWorld
from zora.model.enums import Item
from zora.rom.parse.rom_file import load_rom, parse_rom
from zora.rom.vanilla_overworld import caves
from zora.rom.vanilla_overworld import layouts
from zora.rom.vanilla_overworld import level_info
from zora.rom.vanilla_overworld import recorder
from zora.rom.vanilla_overworld import screens
from zora.rom.vanilla_overworld import tables
from zora.rom.vanilla_overworld.caves import CaveFlags
from zora.rom.vanilla_overworld.screens import EntranceKind, QuestSecret

REPO = Path(__file__).resolve().parents[1]
SHOP_FLAGS = CaveFlags.CHOOSE | CaveFlags.PAY | CaveFlags.SHOW_ITEMS | CaveFlags.SHOW_PRICES
# Generated hint text is written as generated seeds write it (the extended bank), not into the
# vanilla bank, which ZORA's wording outgrows.
GENERATED_HINTS = GameConfig(hint_mode=HintMode.CONSTERNATION)


@pytest.fixture(scope="module")
def rom() -> bytes:
    env = os.environ.get("ZORA_VANILLA_ROM")
    path = Path(env) if env else BASE_ROM_PATH
    if not path.exists():
        pytest.skip("vanilla ROM missing")
    verify_base_rom(path)
    return load_rom(path)


# The tables whose first bytes the pinned disassembly's .BYTE listing gives, read from that
# listing (fetched from git by scripts/asm_patches.py) rather than copied here.
ANCHOR_TABLES = (tables.COLUMN_DIRECTORY_OW, tables.PRIMARY_SQUARES_OW, tables.SECONDARY_SQUARES_OW,
                 tables.ROOM_LAYOUTS_OW_CAVE, tables.OVERWORLD_PERSON_TEXT_SELECTORS,
                 tables.WHIRLWIND_PREV_ROOM_ID_LIST, tables.TELEPORT_YS, tables.Q2_B_REPLACEMENT_OFFSETS,
                 tables.Q2_B_REPLACEMENT_VALUES)
ANCHOR_LENGTH = 8


@pytest.fixture(scope="module")
def disassembly_src() -> Path:
    path = REPO / "scripts" / "asm_patches.py"
    if not path.exists():
        pytest.skip("scripts/asm_patches.py is not in this tree (left out of releases)")
    spec = importlib.util.spec_from_file_location("asm_patches_tool", path)
    assert spec and spec.loader
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    if not tool.DISASSEMBLY_REPO.is_dir():
        pytest.skip("the pinned disassembly clone is missing")
    return Path(tool.disassembly()) / "src"


def listed_bytes(src: Path, table: tables.RomTable, count: int) -> list[int]:
    """The first `count` values of the .BYTE lines after `table`'s label in its source file."""
    lines = (src / table.source.split(",")[0]).read_text().splitlines()
    start = lines.index(f"{table.label}:") + 1
    values: list[int] = []
    for line in lines[start:]:
        code = line.split(";")[0].strip()
        if not code.upper().startswith(".BYTE"):
            break
        values += [int(value.strip().lstrip("$"), 16) for value in code[len(".BYTE"):].split(",")]
        if len(values) >= count:
            break
    return values[:count]


@pytest.mark.parametrize("table", ANCHOR_TABLES, ids=[t.label for t in ANCHOR_TABLES])
def test_table_anchor_bytes(rom: bytes, disassembly_src: Path, table: tables.RomTable) -> None:
    """Each reader's table starts with the bytes the disassembly lists under its label."""
    expected = listed_bytes(disassembly_src, table, ANCHOR_LENGTH)
    assert len(expected) == ANCHOR_LENGTH
    assert list(table.read(rom)[:ANCHOR_LENGTH]) == expected


def test_one_level_entrance_per_level_in_quest_1(rom: bytes) -> None:
    """Hiding the second quest's secrets leaves one entrance per level."""
    quest_1 = [s for s in screens.read_screens(rom) if s.quest_secret is not QuestSecret.SECOND_ONLY]
    levels = sorted(s.entrance.value for s in quest_1 if s.entrance.kind is EntranceKind.LEVEL)
    assert levels == list(range(1, 10))


def test_recorder_lands_on_level_entrances(rom: bytes) -> None:
    by_room = {s.room_id: s for s in screens.read_screens(rom)}
    for destination in recorder.read_recorder_destinations(rom):
        assert by_room[destination.room].entrance.level == destination.level


def test_shortcut_ring_and_start_screen(rom: bytes) -> None:
    info = level_info.read_level_info(rom)
    all_screens = screens.read_screens(rom)
    shortcut_rooms = sorted(s.room_id for s in all_screens if s.entrance.is_shortcut)
    assert sorted(info.shortcut_rooms) == shortcut_rooms and len(shortcut_rooms) == 4
    start = all_screens[info.start_room]
    assert info.start_room == 0x77 and start.entrance.cave_index == 0      # the wood-sword cave


def test_every_layout_decodes(rom: bytes) -> None:
    square_count = len(layouts.primary_squares(rom))
    used = {s.layout for s in screens.read_screens(rom)}
    assert max(used) < tables.OW_LAYOUT_COUNT
    for layout in range(tables.OW_LAYOUT_COUNT):
        columns = layouts.read_layout(rom, layout)
        assert len(columns) == tables.LAYOUT_COLUMNS
        assert all(len(column) == layouts.SQUARE_ROWS for column in columns)
        assert all(square < square_count for column in columns for square in column)
    for cave_layout in range(tables.CAVE_LAYOUT_COUNT):
        assert len(layouts.read_cave_layout(rom, cave_layout)) == tables.LAYOUT_COLUMNS


def test_square_tiles(rom: bytes) -> None:
    assert layouts.square_tiles(rom, 1) == (0x6F, 0x6F, 0x6F, 0x6F)        # secondary
    primary = layouts.primary_squares(rom)[0x10]
    assert layouts.square_tiles(rom, 0x10) == (primary, primary + 1, primary + 2, primary + 3)


def test_cave_contents(rom: bytes) -> None:
    all_caves = caves.read_caves(rom)
    assert len(all_caves) == tables.CAVE_COUNT
    # the three sword caves hold their sword in the middle slot
    assert [all_caves[i].item_ids[1] for i in (0, 2, 3)] == [Item.WOOD_SWORD, Item.WHITE_SWORD, Item.MAGICAL_SWORD]
    shops = [c for c in all_caves if c.flags & SHOP_FLAGS == SHOP_FLAGS]
    assert all(all(price for item, price in zip(c.item_ids, c.prices) if item != caves.NO_ITEM)
               for c in shops)
    assert len(shops) >= 4


def test_agrees_with_the_parser(rom: bytes) -> None:
    """The parser's overworld model (zora/rom/parse/) reads the same bytes
    with other units: exit X in pixels and the recorder's previous room."""
    overworld = parse_rom(rom).overworld
    for mine, theirs in zip(screens.read_screens(rom), overworld.screens, strict=True):
        assert (mine.layout, mine.outer_palette, mine.inner_palette) == \
            (theirs.screen_code, theirs.outer_palette, theirs.inner_palette)
        assert (mine.zora, mine.sea_sound, mine.monsters_from_edges) == \
            (theirs.has_zola, theirs.has_ocean_sound, theirs.enemies_from_sides)
        assert mine.shortcut_position_index == theirs.stairs_position_code
        assert mine.exit_x == theirs.exit_x_position * 0x10
    destinations = recorder.read_recorder_destinations(rom)
    assert [d.previous_room for d in destinations] == overworld.recorder_warp_destinations
    assert [d.drop_y for d in destinations] == overworld.recorder_warp_y_coordinates
    info = level_info.read_level_info(rom)
    assert list(info.shortcut_rooms) == overworld.any_road_screens
    assert (info.start_room, info.start_y) == (overworld.start_screen, overworld.start_position_y)


# --- the overworld passes on finished ROMs (overworld-behavior.md) ------------

@pytest.fixture(scope="module")
def finished(rom: bytes) -> list[tuple[bytes, GameWorld]]:
    from zora.generate.rng import Rng
    from zora.rom.serialize.rom_file import serialize_to_rom
    from zora.generate.generation_pass import generate_shapes
    from zora.generate.shapes.options import ShapeOptions
    outs = []
    for seed in range(4):
        gw = parse_rom(rom)
        generate_shapes(gw, Rng(seed), ShapeOptions())
        outs.append((serialize_to_rom(gw, rom, config=GENERATED_HINTS), gw))
    return outs


def test_cave_shuffle_bytes(rom: bytes, finished: list) -> None:
    """OW-CAVE-02/04/05 and OW-ENTR-02 as the finished bytes show them."""
    from zora.generate.steps.cave_entries import ENROLLED_SCREENS, FIXED_DUNGEON_DOORS, FIXED_SCREENS
    base = screens.read_screens(rom)
    for out, gw in finished:
        shipped = screens.read_screens(out)
        codes = [s.entrance.value for s in shipped]
        assert [codes.count(d) for d in range(1, 10)] == [1, 1, 1, 1, 2, 2, 2, 2, 2]
        assert codes.count(0x10) == 1 and codes.count(0x14) == 4
        for screen in FIXED_SCREENS:
            assert shipped[screen].b == base[screen].b
        assert all(codes[door] == dungeon for dungeon, door in FIXED_DUNGEON_DOORS.items())
        armos = tables.SECRET_ARMOS_ROOM_IDS.read(out)[0]
        any_road = level_info.read_level_info(out).shortcut_rooms
        list_order = [36 if s == armos else s for s in ENROLLED_SCREENS]
        assert list(any_road) == sorted((s for s in range(128) if codes[s] == 0x14), key=list_order.index)
        assert shipped[36].a == 0x43
        for level in gw.levels:                                    # OW-CAVE-03's ban
            assert codes[level.entrance_room] != level.level_num


def test_recorder_follows_entry_doors(finished: list) -> None:
    from zora.generate.steps.cave_entries import FIXED_DUNGEON_DOORS
    from zora.generate.steps.recorder_to_new_dungeons import recorder_bytes
    for out, _ in finished:
        codes = [s.entrance.value for s in screens.read_screens(out)]
        for destination in recorder.read_recorder_destinations(out):
            doors = [s for s in range(128) if codes[s] == destination.level
                     and s != FIXED_DUNGEON_DOORS.get(destination.level)]
            assert (destination.previous_room, destination.drop_y) == recorder_bytes(doors[0])


def test_shop_bytes(rom: bytes, finished: list) -> None:
    """OW-SHOP-01..05: slot flags, item multiset, distinct items, price
    ranges, the six extra bytes and the two candles."""
    base = caves.read_caves(rom)
    base_prices: dict[int, set[int]] = {}
    for cave in base[13:17]:
        for item, price in zip(cave.item_ids, cave.prices):
            base_prices.setdefault(item, set()).add(price)
    for out, _ in finished:
        shipped = caves.read_caves(out)
        shops = shipped[13:17]
        assert [ware & 0xC0 for cave in shops for ware in cave.ware_bytes] == [0, 0, 0xC0] * 4
        assert sorted(i for c in shops for i in c.item_ids) == sorted(i for c in base[13:17] for i in c.item_ids)
        assert all(len(set(c.item_ids)) == 3 for c in shops)
        for cave in shops:
            for item, price in zip(cave.item_ids, cave.prices):
                assert 1 <= price <= 254 and any(abs(price - p) <= 20 for p in base_prices[item])
        assert 25 <= shipped[10].prices[0] <= 55 and 48 <= shipped[10].prices[2] <= 88
        assert 25 <= shipped[17].prices[1] <= 40 and 50 <= shipped[18].prices[1] <= 150
        assert 1 <= shipped[19].prices[1] <= 20 and 15 <= out[0x048A0] <= 25
        assert shipped[0].ware_bytes[0] == 0x06 and shipped[1].ware_bytes[1] == 0x06


def test_recorder_byte_exceptions() -> None:
    from zora.generate.steps.recorder_to_new_dungeons import recorder_bytes
    assert recorder_bytes(14) == (29, 0x8D)
    assert recorder_bytes(109) == (108, 0x5D) and recorder_bytes(117) == (116, 0x7D)
    assert recorder_bytes(60) == (59, 0xAD) and recorder_bytes(55) == (54, 0x8D)


def test_price_jitter_undo() -> None:
    """OW-SHOP-03: a shift to 255 or above (or 0 or below) is undone."""
    from zora.model.enums import Item
    from zora.model.overworld import ShopItem
    from zora.generate.steps.shuffle_shop_items import jitter_prices
    from zora.generate.rng import ScriptedRng
    pairs = [ShopItem(Item.BLUE_RING, 250), ShopItem(Item.SINGLE_HEART, 10), ShopItem(Item.BOMBS, 20)]
    jitter_prices(pairs, ScriptedRng([25, 0, 40]))      # +5, -20, +20
    assert [p.price for p in pairs] == [250, 10, 40]


# --- OW-START-01: the start screen --------------------------------------------

MIXED_LIST_BIT = 0x80       # LevelBlockAttrsD bit 7


def test_start_y() -> None:
    from zora.generate.steps.shuffle_start_screen import start_y
    assert [start_y(s) for s in (119, 44, 66, 109, 114, 110, 117, 118, 121)] == \
        [0x8D, 0xAD, 0xAD, 0x5D, 0x5D, 0x7D, 0x7D, 0x7D, 0x7D]


def test_start_screen_draw() -> None:
    """One seed number and two discards, then numbers mod 128 until a
    listed screen: 5 is not listed, 152 mod 128 = 24 is."""
    from zora.generate.steps.shuffle_start_screen import shuffle_start_screen
    from zora.generate.rng import ScriptedRng
    assert shuffle_start_screen(ScriptedRng([7, 8, 9, 5, 152])).screen == 24


def test_start_screen_exchange(rom: bytes) -> None:
    """Steps 1-4 on the shipped bytes: the start screen and Y, the whole C
    byte exchanged with 119's, D bit 7 moved from S to 119, nothing else."""
    from zora.generate.steps.shuffle_start_screen import (
        START_SCREENS, StartScreen, apply_start_screen, start_y,
    )
    from zora.rom.serialize.rom_file import serialize_to_rom
    base = screens.read_screens(rom)
    flagged = [s for s in sorted(START_SCREENS) if base[s].d & MIXED_LIST_BIT and base[s].c]
    plain = [s for s in sorted(START_SCREENS) if not base[s].d & MIXED_LIST_BIT and base[s].c]
    for start in flagged[:1] + plain[:1]:
        gw = parse_rom(rom)
        apply_start_screen(gw.overworld, StartScreen(start))
        out = serialize_to_rom(gw, rom)
        shipped = screens.read_screens(out)
        info = level_info.read_level_info(out)
        assert (info.start_room, info.start_y) == (start, start_y(start))
        assert (shipped[start].c, shipped[119].c) == (base[119].c, base[start].c)
        assert shipped[119].d == base[119].d | (base[start].d & MIXED_LIST_BIT)
        assert shipped[start].d == base[start].d & ~MIXED_LIST_BIT
        for screen in set(range(128)) - {start, 119}:
            assert shipped[screen].attrs == base[screen].attrs
    assert flagged and plain


def test_start_screen_bytes(rom: bytes, finished: list) -> None:
    """OW-START-01's check lines on finished ROMs."""
    from zora.generate.steps.shuffle_start_screen import START_SCREENS, start_y
    base = screens.read_screens(rom)
    for out, _ in finished:
        info = level_info.read_level_info(out)
        shipped = screens.read_screens(out)
        assert info.start_room in START_SCREENS and info.start_y == start_y(info.start_room)
        assert shipped[119].d & ~MIXED_LIST_BIT == base[119].d & ~MIXED_LIST_BIT
        if info.start_room != 119:
            assert shipped[info.start_room].c == 0
            assert not shipped[info.start_room].d & MIXED_LIST_BIT


def test_wooden_sword_visit_refusal() -> None:
    """OW-CAVE-03: rule (a) redraws a partner holding code 16 on another
    entry's visit; at the code-16 visit a refused partner repeats the whole
    visit (a new discarded j, then a new partner), and the entry itself is
    a legal partner."""
    from zora.model.enums import Destination
    from zora.generate.steps.cave_entries import Entry
    from zora.generate.steps.shuffle_caves import walk_destination_codes
    from zora.generate.rng import ScriptedRng
    level_1 = Destination.LEVEL_1
    entries = [Entry(10, level_1, 0), Entry(119, Destination.WOOD_SWORD_CAVE, 0)]
    rng = ScriptedRng([
        1, 0,       # entry 0: partner 1 holds code 16 (rule a), redrawn as itself
        0, 0,       # code-16 visit: j discarded, partner entry 0 refused (119 = S(1))
        1, 1,       # repeat: j discarded, partner itself
    ])
    walk_destination_codes(entries, {1: 119}, rng)
    assert [e.code for e in entries] == [level_1, Destination.WOOD_SWORD_CAVE]
    with pytest.raises(IndexError):     # every scripted draw was spent
        rng.below(2)
