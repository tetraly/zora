"""Archipelago items piece 6 in the emulator (docs/design/archipelago-items.md section 8), on PRG0 and PRG1:
in per-level mode (zora/rom/level_items.py) a level's compass, map and Triforce piece, written by FINISH's
serializer into a room, a cave and a shop, sets exactly its own inventory bit wherever it is taken; the
generic codes are level 9's compass and map and level 8's piece. A piece refills the hearts as a potion
does and the level goes on (no GameMode $12); a map taken in its own level draws the status bar's map."""
from dataclasses import replace
from functools import cache

import pytest

from tests.emulator import (
    CUR_LEVEL,
    CUR_OPENED_DOORS,
    INV_MAP,
    INV_TRIFORCE,
    ITEMS,
    OBJ_TYPE,
    OBJ_X,
    OBJ_Y,
    ROOM_ID,
    ROOM_ITEM_SLOT,
    SHUTTER_TRIGGER,
    STATUS_BAR_ROWS,
    Mode,
)
from tests.archipelago_cases import FLAG_CASES
from tests.needs import needs_base_rom
from tests.test_assignment import identity
from tests.test_assignment_emulator import (
    CASE,
    ENTER_ROOM_MODE,
    HEART_VALUES,
    INV_RUPEES,
    MONSTER_SLOTS,
    SEED,
    Console,
    places_of_each_kind,
)
from tests.test_cave_takes_emulator import _base
from zora.flags.fields import ThreeState
from zora.flags.zora_flags import LevelItemShuffle, decode, encode
from zora.generate.finish import compass_item_rooms
from zora.generate.pipeline import build, finish_world, plan, written_world
from zora.generate.places import Place, PlaceKind, write_item
from zora.model.enums import Enemy, Item, RoomAction
from zora.model.level_items import LevelItemKind, level_item, level_of
from zora.rom import inventory, level_items
from zora.rom.base_rom import as_player_rom, using_player_rom
from zora.rom.serialize.levels import derive_triforce_room_ptr
from zora.rom.serialize.rom_file import serialize_to_rom

INVENTORY = range(ITEMS, ITEMS + 0x28)
# The hearts fill over time, the rupees count down after a purchase, a shop's bought flags mark a ware
CHANGING = {HEART_VALUES, HEART_VALUES + 1, INV_RUPEES,
            *range(inventory.SHOP_BOUGHT_FLAGS, inventory.SHOP_BOUGHT_FLAGS + 3)}
SLOTS = {LevelItemKind.COMPASS: 0x10, LevelItemKind.MAP: 0x11, LevelItemKind.TRIFORCE: 0x1A}
LEVEL_9_SLOTS = {LevelItemKind.COMPASS: 0x12, LevelItemKind.MAP: 0x13}
WORLD_IS_FILLING_HEARTS = 0x63
STATUS_BAR_MAP_TRIGGER = 0x4E5
GAME_MODE = 0x12
TILE_BUF_SELECTOR = 0x14
STATUS_BAR_MAP_TRANSFER = 0x44
SETTLE_FRAMES = 30
TAKE_FRAMES = 180
KINDS = ("room floor", "cave", "shop ware")


@cache
def _finished(revision: str):  # type: ignore[no-untyped-def]
    """CASE's seed built with Add Maps/Compasses to the Item Pool on, so FINISH runs per-level mode's own steps (the
    compass targets, write_level_codes) as a real seed does."""
    base = _base(revision)
    flag_string, zora_flag_string = FLAG_CASES[CASE]
    switches = replace(decode(zora_flag_string), map_compass_shuffle=LevelItemShuffle.ANYWHERE)
    return base, build(plan(flag_string, SEED, encode(switches)), base)


def rom_with(revision: str, items: tuple[tuple[Place, Item], ...],
             shown: tuple[int, ...] = tuple(range(1, 10))) -> bytes:
    """CASE's Archipelago ROM in per-level mode with each item written into its place."""
    base, built = _finished(revision)
    with using_player_rom(as_player_rom(base)):
        world, finished = finish_world(built, identity(built))
    for place, item in items:
        write_item(world, place, item)
    config = replace(finished.config, archipelago_rom=True, seed_number=None, per_level_shown=shown,
                     per_level_compass_rooms=compass_item_rooms(built.world))
    return serialize_to_rom(written_world(world, config), base, config=config)


@cache
def rom(revision: str, item: Item) -> tuple[bytes, dict[str, Place]]:
    """CASE's Archipelago ROM in per-level mode with `item` in a room floor, the White Sword Cave and a shop."""
    _, built = _finished(revision)
    places = {kind: place for kind, place in places_of_each_kind(built).items() if kind in KINDS}
    return rom_with(revision, tuple((place, item) for place in places.values())), places


def expected_bit(item: Item) -> tuple[int, int]:
    """(inventory address, mask) the item sets."""
    found = level_of(item)
    assert found is not None
    kind, level = found
    if level == 9:
        return ITEMS + LEVEL_9_SLOTS[kind], 0x01
    return ITEMS + SLOTS[kind], 1 << (level - 1)


def inventory_bytes(console: Console) -> dict[int, int]:
    return {address: console.emu[address] for address in INVENTORY if address not in CHANGING}


def take(console: Console, place: Place, kind: str) -> None:
    if kind == "room floor":
        assert place.level is not None and place.room_num is not None
        console.enter_room(place.level, place.room_num)
        console.clear_monsters()
        console.take_room_item()
    else:
        console.emu[inventory.RUPEES_TO_ADD] = 0
        console.emu[INV_RUPEES] = 0xFF
        console.enter_cave(place.screens[0])
        console.take_ware(1 if kind == "cave" else place.position or 0)


SAMPLE = (Item.COMPASS_3, Item.MAP_5, Item.TRIFORCE_2, Item.TRIFORCE_7, Item.COMPASS, Item.MAP, Item.TRIFORCE)


@needs_base_rom
@pytest.mark.parametrize("revision", ["prg0", "prg1"])
@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("item", SAMPLE, ids=lambda item: item.name)
def test_a_level_item_sets_exactly_its_bit(revision: str, kind: str, item: Item) -> None:
    image, places = rom(revision, item)
    console = Console(image)
    place = places[kind]
    before = inventory_bytes(console)
    take(console, place, kind)
    console.emu.run(SETTLE_FRAMES)
    after = inventory_bytes(console)
    address, mask = expected_bit(item)
    what = (revision, kind, item.name, place.name)
    assert {a: after[a] for a in after if after[a] != before.get(a)} == {address: before[address] | mask}, what
    assert not console.emu.nes.has_crashed, what


@needs_base_rom
@pytest.mark.parametrize("revision", ["prg0", "prg1"])
def test_a_piece_refills_and_the_level_goes_on(revision: str) -> None:
    item = Item.TRIFORCE_2
    image, places = rom(revision, item)
    console = Console(image)
    place = places["room floor"]
    assert place.level is not None and place.room_num is not None
    console.enter_room(place.level, place.room_num)
    console.clear_monsters()
    console.emu[HEART_VALUES] = console.emu[HEART_VALUES] & 0xF0          # one heart left
    console.take_room_item()
    assert console.emu[WORLD_IS_FILLING_HEARTS] != 0
    console.emu.run_until(lambda: console.emu[WORLD_IS_FILLING_HEARTS] == 0, limit=600)
    assert console.emu[HEART_VALUES] & 0x0F == console.emu[HEART_VALUES] >> 4    # full
    assert console.emu.mode == Mode.PLAY and console.emu[GAME_MODE] != 0x12


def map_cued(revision: str, item: Item, place: Place) -> bool:
    """Whether taking `item` from the room floor `place` cues the status bar's map, watched frame by frame."""
    image, _ = rom(revision, item)
    console = Console(image)
    assert place.level is not None and place.room_num is not None
    console.enter_room(place.level, place.room_num)
    console.clear_monsters()
    emu = console.emu
    emu[OBJ_X], emu[OBJ_Y] = emu[OBJ_X + ROOM_ITEM_SLOT], emu[OBJ_Y + ROOM_ITEM_SLOT]
    cued = False
    for _ in range(TAKE_FRAMES):
        emu.run(1)
        cued |= emu[STATUS_BAR_MAP_TRIGGER] != 0 or emu[TILE_BUF_SELECTOR] == STATUS_BAR_MAP_TRANSFER
    address, mask = expected_bit(item)
    assert emu[address] & mask, (revision, item.name)
    return cued


@needs_base_rom
@pytest.mark.parametrize("revision", ["prg0", "prg1"])
def test_a_map_in_its_own_level_draws_the_status_bar_map(revision: str) -> None:
    _, places = rom(revision, Item.MAP_5)
    place = places["room floor"]
    assert place.level is not None
    other = 1 if place.level != 1 else 2
    assert map_cued(revision, level_item(LevelItemKind.MAP, place.level), place)
    assert not map_cued(revision, level_item(LevelItemKind.MAP, other), place)


DIGIT_TILES = (0x55, 0x57, 0x59)
BACKGROUND_TABLE = 0x1000
TILE_BYTES = 16
SHOP_WARES = 3
DIGIT_FRAMES = 10


def shown_digits(console: Console, image: bytes) -> list[int]:
    """The digit each visible digit sprite shows, left to right, read from video memory: its pair's first
    tile is the font's digit (zora/rom/level_items.digit_glyph) in both planes, its second blank."""
    oam = console.emu.sprites()
    chr_ram = console.emu.pattern_tables()
    glyphs = {level_items.digit_glyph(image, digit) * 2: digit for digit in level_items.DIGITS}
    found = []
    for at in range(0, len(oam), 4):
        y, tile, _attributes, x = oam[at:at + 4]
        if tile in DIGIT_TILES and y < 0xEF:
            first = BACKGROUND_TABLE + (tile - 1) * TILE_BYTES
            assert chr_ram[first + TILE_BYTES:first + 2 * TILE_BYTES] == bytes(TILE_BYTES)
            found.append((x, glyphs.get(chr_ram[first:first + TILE_BYTES], -1)))
    return [digit for _x, digit in sorted(found)]


def shop_wares(revision: str) -> list[Place]:
    """A shop's three wares: its ware place and the other two positions (this case makes one a place)."""
    _, built = _finished(revision)
    ware = next(place for place in built.places if place.kind is PlaceKind.SHOP_WARE)
    return [replace(ware, position=position, name=f"{ware.name} ({position})") for position in range(SHOP_WARES)]


@needs_base_rom
@pytest.mark.parametrize("revision", ["prg0", "prg1"])
def test_three_wares_show_three_digits_at_once(revision: str) -> None:
    """A shop's row: a map, a Triforce piece (only ever the middle ware) and a compass, three digits."""
    wares = shop_wares(revision)
    items = (Item.MAP_1, Item.TRIFORCE_5, Item.COMPASS_3)
    image = rom_with(revision, tuple(zip(wares, items, strict=True)))
    console = Console(image)
    console.enter_cave(wares[0].screens[0])
    console.emu.run(DIGIT_FRAMES)
    assert shown_digits(console, image) == [1, 5, 3]


@needs_base_rom
@pytest.mark.parametrize("revision", ["prg0", "prg1"])
def test_the_digit_is_the_number_the_status_bar_shows(revision: str) -> None:
    """Data level 5's map shows the seed's number for it, not 5."""
    _, places = rom(revision, Item.MAP_5)
    shown = (1, 2, 3, 4, 7, 6, 5, 8, 9)
    image = rom_with(revision, ((places["room floor"], Item.MAP_5),), shown)
    console = Console(image)
    place = places["room floor"]
    assert place.level is not None and place.room_num is not None
    console.enter_room(place.level, place.room_num)
    console.emu.run(DIGIT_FRAMES)
    assert shown_digits(console, image) == [7]


@needs_base_rom
@pytest.mark.parametrize("revision", ["prg0", "prg1"])
def test_the_digits_stay_right_after_save_and_reload(revision: str) -> None:
    """Two rooms' digits, then save, reset and Continue: the cache starts empty and each digit is written
    again."""
    image, places = rom(revision, Item.TRIFORCE_7)
    console = Console(image)
    console.enter_cave(places["shop ware"].screens[0])
    console.emu.run(DIGIT_FRAMES)
    assert shown_digits(console, image) == [7]
    console.emu.open_item_screen()
    console.emu.save_and_reload()
    other = rom_with(revision, ((places["room floor"], Item.COMPASS_2),))
    assert other  # the same seed's ROM with another digit: the saved file plays on this console's ROM
    place = places["room floor"]
    assert place.level is not None and place.room_num is not None
    console.enter_room(place.level, place.room_num)
    console.emu.run(DIGIT_FRAMES)
    assert shown_digits(console, image) == [7]


CARRIERS = frozenset({Enemy.LIKE_LIKE, Enemy.STALFOS, Enemy.GIBDO})
CARRY_FRAMES = 90
SHOWN_LATER = (RoomAction.LAST_BOSS, RoomAction.ALL_DEAD_ITEM)      # the item is hidden at load
NARROW_DIGIT_X, DIGIT_Y = 12, 8          # a compass's or map's digit, from the item's position


def carrier_room(revision: str) -> Place:
    """A room of CASE's seed whose item a Like-Like, Stalfos or Gibdo carries (its item lies on the floor at
    once, not dropped when the room is cleared)."""
    base, built = _finished(revision)
    with using_player_rom(as_player_rom(base)):
        world, _ = finish_world(built, identity(built))
    for level in world.levels:
        for room in level.rooms:
            if room.enemy in CARRIERS and room.room_action not in SHOWN_LATER:
                return Place(PlaceKind.ROOM, f"carried {room.room_num:02X}", level=level.level_num,
                             room_num=room.room_num)
    raise AssertionError("no carrier room in this seed")


@needs_base_rom
@pytest.mark.parametrize("revision", ["prg0", "prg1"])
def test_the_digit_follows_a_carried_item(revision: str) -> None:
    """The carrier walks off with the map: each frame the digit is drawn at the item's lower right."""
    place = carrier_room(revision)
    assert place.level is not None and place.room_num is not None
    image = rom_with(revision, ((place, Item.MAP_5),))
    console = Console(image)
    console.enter_room(place.level, place.room_num)
    emu = console.emu
    positions = set()
    for _ in range(CARRY_FRAMES):
        emu.run(1)
        item = emu[OBJ_X + ROOM_ITEM_SLOT], emu[OBJ_Y + ROOM_ITEM_SLOT]
        positions.add(item)
        oam = emu.sprites()
        digits = [(oam[at + 3], oam[at]) for at in range(0, len(oam), 4) if oam[at + 1] in DIGIT_TILES
                  and oam[at] < 0xEF]
        assert digits in ([], [(item[0] + NARROW_DIGIT_X, item[1] + DIGIT_Y)]), (revision, item, digits)
    assert len(positions) > 1, "the item never moved"
    assert shown_digits(console, image) == [5]


# The gaps of section 8's piece 6 list: level 9 opens on a piece taken outside its level, a map taken in another
# level draws on entering its own, and a piece taken in a cave or shop fills the hearts there.
LEVEL_9 = 9
ENTRANCE_PERSON = 0x4B
GATE_FRAMES = 120
ALL_PIECES = 0xFF
BAR_FRAMES = 30
CAVE_MODE = 0x0B


def enter_level_room(console: Console, level: int, room: int) -> None:
    """Load `level` and enter `room` from where the console stands, keeping what Link holds."""
    emu = console.emu
    emu[CUR_LEVEL] = level
    console._mode(Mode.LOAD_LEVEL)
    console._wait()
    emu[ROOM_ID] = room
    console._mode(ENTER_ROOM_MODE)
    console._wait()


def gate_opens(console: Console, revision: str) -> bool:
    """Enter the room of level 9's entrance person: whether he left and the shutters opened."""
    _, built = _finished(revision)
    level_9 = next(level for level in built.world.levels if level.level_num == LEVEL_9)
    enter_level_room(console, LEVEL_9, level_9.entrance_room - 0x10)
    emu = console.emu
    triggered = False
    for _ in range(GATE_FRAMES):
        emu.run(1)
        triggered |= bool(emu[SHUTTER_TRIGGER])
    present = any(emu[OBJ_TYPE + slot] == ENTRANCE_PERSON for slot in MONSTER_SLOTS)
    opened = bool(emu[CUR_OPENED_DOORS])
    assert (not present) == triggered == opened, (present, triggered, opened)
    return opened


@needs_base_rom
@pytest.mark.parametrize("revision", ["prg0", "prg1"])
def test_level_9_opens_on_the_eighth_piece_taken_in_another_level(revision: str) -> None:
    """Seven pieces held, level 5's taken on another level's floor: the gate (eight pieces in this seed) opens;
    with the seven alone it stays shut."""
    _, built = _finished(revision)
    assert built.world.level_9_gate.pieces == 8
    image, places = rom(revision, Item.TRIFORCE_5)
    place = places["room floor"]
    assert place.level is not None and place.level != 5 and place.room_num is not None
    seven = ALL_PIECES & ~expected_bit(Item.TRIFORCE_5)[1]
    console = Console(image)
    console.emu[INV_TRIFORCE] = seven
    console.start = console.emu.save()
    console.emu.load(console.start)
    assert not gate_opens(console, revision)
    console.enter_room(place.level, place.room_num)
    console.clear_monsters()
    console.take_room_item()
    assert console.emu[INV_TRIFORCE] == ALL_PIECES
    assert gate_opens(console, revision)


def status_bar_in(console: Console, level: int, revision: str) -> bytes:
    _, built = _finished(revision)
    entrance = next(found.entrance_room for found in built.world.levels if found.level_num == level)
    enter_level_room(console, level, entrance)
    console.emu.run(BAR_FRAMES)
    return console.emu.nametable(*STATUS_BAR_ROWS)


@needs_base_rom
@pytest.mark.parametrize("revision", ["prg0", "prg1"])
@pytest.mark.parametrize("kind", ["room floor", "shop ware"])
def test_a_map_taken_elsewhere_draws_on_entering_its_level(revision: str, kind: str) -> None:
    """Level 5's map taken on another level's floor or in a shop: entering level 5, the status bar's map tiles (those the
    map bit changes; the rupees a purchase spent differ too) are drawn as with the bit set."""
    image, places = rom(revision, Item.MAP_5)
    place = places[kind]
    assert place.level != 5
    console = Console(image)
    take(console, place, kind)
    taken = status_bar_in(console, 5, revision)
    held, without = Console(image), Console(image)
    held.emu[INV_MAP] = expected_bit(Item.MAP_5)[1]
    with_bit, no_bit = status_bar_in(held, 5, revision), status_bar_in(without, 5, revision)
    map_tiles = [at for at, (one, other) in enumerate(zip(with_bit, no_bit, strict=True)) if one != other]
    assert map_tiles
    assert [taken[at] for at in map_tiles] == [with_bit[at] for at in map_tiles]


@needs_base_rom
@pytest.mark.parametrize("revision", ["prg0", "prg1"])
@pytest.mark.parametrize("kind", ["cave", "shop ware"])
def test_a_piece_taken_in_a_cave_or_shop_fills_the_hearts_there(revision: str, kind: str) -> None:
    """One heart left, level 2's piece taken as a ware: the hearts fill to full and Link stays in the cave."""
    image, places = rom(revision, Item.TRIFORCE_2)
    place = places[kind]
    console = Console(image)
    console.emu[inventory.RUPEES_TO_ADD] = 0
    console.enter_cave(place.screens[0])
    console.emu[HEART_VALUES] = console.emu[HEART_VALUES] & 0xF0          # one heart left
    console.take_ware(1 if kind == "cave" else place.position or 0)
    emu = console.emu
    emu.run_until(lambda: emu[WORLD_IS_FILLING_HEARTS] == 0 and emu[HEART_VALUES] & 0x0F == emu[HEART_VALUES] >> 4,
                  limit=900)
    assert emu[HEART_VALUES] & 0x0F == emu[HEART_VALUES] >> 4                # full
    assert emu.mode == CAVE_MODE and emu[GAME_MODE] != 0x12
    assert emu[INV_TRIFORCE] & expected_bit(Item.TRIFORCE_2)[1]
    assert not emu.nes.has_crashed


# The compass marks its level's original Triforce room, wherever the compass was taken or however it came: the
# game reads only the current level's bit and its level info's Triforce room (LevelInfo_TriforceRoomId). Before
# the fix, FINISH rewrote levels 1-7's pieces as their own codes and the serializer, finding no generic piece,
# wrote room $00: the marker stood off the status bar's map (a tester's report on 2.0.2's test build).
INV_COMPASS = ITEMS + SLOTS[LevelItemKind.COMPASS]
LEVEL_INFO_TRIFORCE_ROOM = 0x6BAE
LEVEL_INFO_MAP_X_OFFSET = 0x6BAC
TRIFORCE_MARKER = 0x200 + 88             # the Triforce position marker's sprite: Y, tile, attributes, X
MARKER_TILE = 0x3E
HIDDEN_Y = 0xF8                          # a sprite off the screen
BYTE = 0xFF
MARKER_FRAMES = 30
ROW_MASK, COLUMN_MASK = 0x70, 0x0F
MAP_TOP, UNDERWORLD_MAP_LEFT, COLUMN_WIDTH = 0x17, 0x12, 8


def original_triforce_room(revision: str, level_num: int) -> int:
    """The room the level's piece lay in when BUILD finished (a cellar's: its stairs' room)."""
    _, built = _finished(revision)
    return derive_triforce_room_ptr(next(level for level in built.world.levels if level.level_num == level_num))


def marker(console: Console) -> tuple[int, int, int]:
    """(Y, tile, X) of the Triforce position marker."""
    emu = console.emu
    return emu[TRIFORCE_MARKER], emu[TRIFORCE_MARKER + 1], emu[TRIFORCE_MARKER + 3]


def marks(console: Console, room: int) -> tuple[int, int, int]:
    """The marker on `room`, as UpdatePositionMarker places it with the current level's map offset (an 8-bit sum:
    the offset wraps the map's left edge around)."""
    x = (room & COLUMN_MASK) * COLUMN_WIDTH + UNDERWORLD_MAP_LEFT + console.emu[LEVEL_INFO_MAP_X_OFFSET]
    return ((room & ROW_MASK) >> 2) + MAP_TOP, MARKER_TILE, x & BYTE


def compass_level(place: Place) -> int:
    assert place.level is not None
    return 1 if place.level != 1 else 2


@needs_base_rom
@pytest.mark.parametrize("revision", ["prg0", "prg1"])
@pytest.mark.parametrize("how", ["taken in its level", "taken in another level", "given in another level"])
def test_a_compass_marks_its_levels_triforce_room(revision: str, how: str) -> None:
    """Level N's compass, however it came, puts the marker on level N's original Triforce room in level N."""
    _, places = rom(revision, Item.COMPASS_3)
    floor = places["room floor"]
    assert floor.level is not None and floor.room_num is not None
    level = floor.level if how == "taken in its level" else compass_level(floor)
    compass = level_item(LevelItemKind.COMPASS, level)
    image = rom_with(revision, ((floor, compass),))
    console = Console(image)
    console.enter_room(floor.level, floor.room_num)
    if how == "given in another level":
        console.emu[INV_COMPASS] |= expected_bit(compass)[1]
    else:
        console.clear_monsters()
        console.take_room_item()
    console.emu.run(MARKER_FRAMES)
    assert console.emu[INV_COMPASS] == expected_bit(compass)[1], how
    if level != floor.level:
        assert marker(console)[0] == HIDDEN_Y, "no marker in a level whose compass is not held"
        _, built = _finished(revision)
        enter_level_room(console, level, next(found.entrance_room for found in built.world.levels
                                              if found.level_num == level))
        console.emu.run(MARKER_FRAMES)
    room = original_triforce_room(revision, level)
    assert console.emu[LEVEL_INFO_TRIFORCE_ROOM] == room
    assert marker(console) == marks(console, room), (revision, how, level, f"${room:02X}")

