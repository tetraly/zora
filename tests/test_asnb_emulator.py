"""The ROM side of All Swords No Boards (docs/design/asnb.md section 3; asm/asnb/) in the
emulator. Each ROM is tests/test_progressive_emulator.py's (ZORA's MVP-baseline output with the
progressive patches, its test wares and per-seed bytes), with the three ASNB patches and
sword-cap's byte written over it, and a wooden sword as the white- and magical-sword caves'
ware too.

  - The 4th sword upgrade, taken at sword level 3, gives level 4 on each path: the wooden-,
    white- and magical-sword caves, a shop ware (not hidden at level 3), a dungeon room, an
    item cellar, the coast and the Armos.
  - At sword level 4: a shop hides its sword; every other sword item shows the magical sword
    ($03), and taking it changes nothing (no bait).
  - Below level 3 the line is as before, and with sword-cap's byte $00 a shop hides its sword
    at level 3, as with Progressive Items alone.
  - The level-9 gate refuses at sword levels 0-3 and opens at 4, whatever the triforce pieces.
  - Sword level 4 is kept through Save, the console's reset and starting the file again."""
from collections.abc import Callable
from enum import Enum
from functools import cache

import pytest

from tests.emulator import (
    CUR_OPENED_DOORS,
    GAME_MODE,
    GAME_SUBMODE,
    INV_TRIFORCE,
    ITEMS,
    OBJ_TYPE,
    ROOM_ID,
    SHUTTER_TRIGGER,
)
from tests.test_asnb_patches import build as asnb
from tests.test_progressive_emulator import (
    COAST_SCREEN,
    ENTER_ROOM_MODE,
    GIVEN_WARE,
    IS_UPDATING_MODE,
    ITEM_ACTIVE,
    LEVEL_BLOCK_ATTRS_E,
    MAGICAL_SWORD,
    NO_ITEM,
    ROOM_ITEM_MASK,
    SHOP_WARE,
    SWORD,
    TEST_PRICE,
    WOODEN_SWORD,
    Game,
    build,
    cave_type,
    finished,
    rom_with_test_wares,
)
from tests.test_progressive_l4_emulator import INV_FOOD, LEVEL_WITH_ROOM_ITEMS, reveal_armos_item
from zora.model.enums import Destination, RoomType
from zora.model.game_world import GameWorld
from zora.model.rooms import StaircaseRoom
from zora.rom.parse.rom_file import parse_rom

L4_SWORD_LEVEL = 4
SWORD_CAVES = (Destination.WOOD_SWORD_CAVE, Destination.WHITE_SWORD_CAVE, Destination.MAGICAL_SWORD_CAVE)
SWORD_CAVE_WARE = 1                  # where those caves show their item
CELLAR_MODE = 0x09
CELLAR_SOURCE_ROOM = 0x527           # the room a cellar returns to
LEVEL_9 = 9
LEVEL_9_ENTRANCE_PERSON = 0x4B       # the man at level 9's entrance (object type)
MONSTER_SLOTS = range(1, 0x0C)
GATE_FRAMES = 120
ALL_TRIFORCE_PIECES = 0xFF


class Pickup(Enum):
    """Where a sword item is taken."""
    WOOD_SWORD_CAVE = "wooden-sword cave"
    WHITE_SWORD_CAVE = "white-sword cave"
    MAGICAL_SWORD_CAVE = "magical-sword cave"
    SHOP = "shop"
    ROOM = "dungeon room"
    CELLAR = "cellar"
    COAST = "coast"
    ARMOS = "Armos"


CAVE_OF = dict(zip((Pickup.WOOD_SWORD_CAVE, Pickup.WHITE_SWORD_CAVE, Pickup.MAGICAL_SWORD_CAVE), SWORD_CAVES,
                   strict=True))


# --- ROMs and games ---------------------------------------------------------------------------

@cache
def asnb_rom(sword_line_to_l4: bool = True, armos_item: int | None = None, coast_item: int | None = None) -> bytes:
    rom = rom_with_test_wares(True, "", armos_item, coast_item)
    for destination in SWORD_CAVES:
        rom = build.with_ware(rom, cave_type(destination), SWORD_CAVE_WARE, WOODEN_SWORD)
    return bytes(asnb.apply_patches(rom, sword_line_to_l4=sword_line_to_l4))


@cache
def new_game(sword_line_to_l4: bool = True, armos_item: int | None = None,
             coast_item: int | None = None) -> Callable[[], Game]:
    """A factory of games that all start from one saved state of a new file."""
    game = Game(asnb_rom(sword_line_to_l4, armos_item, coast_item))
    state = game.emu.save()

    def new() -> Game:
        game.emu.load(state)
        return game
    return new


def game_for(path: Pickup, sword_level: int, sword_line_to_l4: bool = True) -> Game:
    items = {Pickup.COAST: {"coast_item": WOODEN_SWORD}, Pickup.ARMOS: {"armos_item": WOODEN_SWORD}}.get(path, {})
    game = new_game(sword_line_to_l4, **items)()
    SWORD.set_level(game.emu, sword_level)
    return game


@cache
def item_cellar() -> tuple[int, StaircaseRoom]:
    """A level of the test ROM's world and its item cellar."""
    world: GameWorld = parse_rom(finished())
    for level in world.levels:
        for stair in level.block.staircases:
            if stair.room_type == RoomType.ITEM_STAIRCASE and stair.return_dest in level.room_nums:
                return level.level_num, stair
    raise AssertionError("no item cellar")


def enter_cellar_with_item(game: Game, item: int) -> None:
    """Load the cellar's level, put `item` in the cellar's level block in work RAM and step down
    into it, as its staircase does."""
    level_num, stair = item_cellar()
    game.enter_level(level_num)
    attrs = LEVEL_BLOCK_ATTRS_E + stair.room_num
    game.emu[attrs] = game.emu[attrs] & ~ROOM_ITEM_MASK & 0xFF | item
    assert stair.return_dest is not None
    game.emu[CELLAR_SOURCE_ROOM] = stair.return_dest
    game.emu[ROOM_ID] = stair.room_num
    game.emu[GAME_MODE] = CELLAR_MODE
    game.emu[GAME_SUBMODE] = 0
    game.emu[IS_UPDATING_MODE] = 0
    game.wait_for_play(CELLAR_MODE)
    game.emu.run(5)


def show_sword(game: Game, path: Pickup) -> int:
    """Bring up the path's sword item (a wooden sword where it is placed); return the ID shown."""
    if path in CAVE_OF:
        game.enter_cave(CAVE_OF[path])
        return game.wares()[SWORD_CAVE_WARE]
    if path is Pickup.SHOP:
        shop, position = SHOP_WARE[SWORD]
        game.enter_cave(shop)
        return game.wares()[position]
    if path is Pickup.ROOM:
        game.enter_level(LEVEL_WITH_ROOM_ITEMS)
        game.reload_room_with_item(WOODEN_SWORD)
    elif path is Pickup.CELLAR:
        enter_cellar_with_item(game, WOODEN_SWORD)
    elif path is Pickup.COAST:
        game.go_to_screen(COAST_SCREEN)
    else:
        reveal_armos_item(game, game_shown_armos(game))
    shown, state = game.room_item()
    assert state == ITEM_ACTIVE, path
    return shown


def game_shown_armos(game: Game) -> int:
    """The Armos item expected at the game's sword level (the magical sword at levels 2-4)."""
    return SWORD.items[min(SWORD.level(game.emu), len(SWORD.items) - 1)]


def take_sword(game: Game, path: Pickup) -> None:
    if path in CAVE_OF:
        game.take_ware(SWORD_CAVE_WARE)
    elif path is Pickup.SHOP:
        game.take_ware(SHOP_WARE[SWORD][1])
    else:
        game.take_room_item()


def sword_and_bait(game: Game) -> tuple[int, int]:
    return SWORD.level(game.emu), game.emu[INV_FOOD]


# --- the 4th upgrade at sword level 3 ----------------------------------------------------------

@pytest.mark.parametrize("path", list(Pickup), ids=[path.value for path in Pickup])
def test_the_fourth_upgrade_at_sword_level_3_gives_level_4(path: Pickup) -> None:
    """The item shows as the magical sword ($03), not as the line's top (a shop sells it at its
    price), and taking it gives sword level 4."""
    game = game_for(path, 3)
    assert show_sword(game, path) == MAGICAL_SWORD, path
    if path is Pickup.SHOP:
        assert game.price(SHOP_WARE[SWORD][1]) == TEST_PRICE
    take_sword(game, path)
    assert sword_and_bait(game) == (L4_SWORD_LEVEL, 0), path


# --- sword level 4 --------------------------------------------------------------------------

def test_at_sword_level_4_a_shop_hides_its_sword() -> None:
    game = game_for(Pickup.SHOP, L4_SWORD_LEVEL)
    shop, position = SHOP_WARE[SWORD]
    game.enter_cave(shop)
    assert (game.wares()[position], game.price(position)) == (NO_ITEM, 0)


@pytest.mark.parametrize("path", [path for path in Pickup if path is not Pickup.SHOP],
                         ids=[path.value for path in Pickup if path is not Pickup.SHOP])
def test_at_sword_level_4_a_sword_item_shows_the_magical_sword_and_changes_nothing(path: Pickup) -> None:
    game = game_for(path, L4_SWORD_LEVEL)
    assert show_sword(game, path) == MAGICAL_SWORD, path
    take_sword(game, path)
    assert sword_and_bait(game) == (L4_SWORD_LEVEL, 0), path


# --- below level 3, and the byte off -------------------------------------------------------------

@pytest.mark.parametrize("path", [Pickup.WOOD_SWORD_CAVE, Pickup.SHOP, Pickup.ROOM], ids=["cave", "shop", "room"])
def test_below_sword_level_3_each_sword_item_gives_the_next_level(path: Pickup) -> None:
    for level in range(3):
        game = game_for(path, level)
        assert show_sword(game, path) == SWORD.items[level], (path, level)
        take_sword(game, path)
        assert sword_and_bait(game) == (level + 1, 0), (path, level)


def test_with_the_byte_off_a_shop_hides_its_sword_at_level_3() -> None:
    """sword-cap's byte $00: the line's top is the magical sword, as with Progressive Items alone."""
    game = game_for(Pickup.SHOP, 3, sword_line_to_l4=False)
    shop, position = SHOP_WARE[SWORD]
    game.enter_cave(shop)
    assert (game.wares()[position], game.price(position)) == (NO_ITEM, 0)


# --- the level-9 gate ----------------------------------------------------------------------------

@cache
def level_9_entry_room() -> int:
    """The room one row north of level 9's entrance, where the man stands (VA-WALK-08)."""
    level = next(level for level in parse_rom(finished()).levels if level.level_num == LEVEL_9)
    return level.entrance_room - 0x10


def meet_the_level_9_man(sword_level: int, triforce: int) -> tuple[bool, bool, bool]:
    """Enter the man's room with this sword level and these triforce pieces; return whether he
    is still there, whether the shutters were triggered and whether the room's doors opened."""
    game = new_game()()
    SWORD.set_level(game.emu, sword_level)
    game.emu[INV_TRIFORCE] = triforce
    game.enter_level(LEVEL_9)
    game.emu[ROOM_ID] = level_9_entry_room()
    game.start_mode(ENTER_ROOM_MODE)
    triggered = False
    for _ in range(GATE_FRAMES):
        game.emu.run(1)
        triggered |= bool(game.emu[SHUTTER_TRIGGER])
    present = any(game.emu[OBJ_TYPE + slot] == LEVEL_9_ENTRANCE_PERSON for slot in MONSTER_SLOTS)
    return present, triggered, bool(game.emu[CUR_OPENED_DOORS])


@pytest.mark.parametrize("triforce", [0, ALL_TRIFORCE_PIECES], ids=["no pieces", "all pieces"])
def test_the_gate_refuses_below_sword_level_4(triforce: int) -> None:
    for level in range(L4_SWORD_LEVEL):
        assert meet_the_level_9_man(level, triforce) == (True, False, False), level


@pytest.mark.parametrize("triforce", [0, ALL_TRIFORCE_PIECES], ids=["no pieces", "all pieces"])
def test_the_gate_opens_at_sword_level_4(triforce: int) -> None:
    assert meet_the_level_9_man(L4_SWORD_LEVEL, triforce) == (False, True, True)


# --- saves ------------------------------------------------------------------------------------

def test_save_reset_and_reload_keep_sword_level_4() -> None:
    """Sword level 4 is an ordinary InvSword value: after Save, the console's reset and starting
    the file again it is still 4, and a sword item still shows the magical sword and changes
    nothing."""
    game = game_for(Pickup.WOOD_SWORD_CAVE, L4_SWORD_LEVEL)
    game.enter_cave(GIVEN_WARE[SWORD])
    game.leave_cave()
    game.emu.open_item_screen()
    game.emu.save_and_reload()
    assert game.emu[ITEMS] == L4_SWORD_LEVEL
    assert show_sword(game, Pickup.ROOM) == MAGICAL_SWORD
    take_sword(game, Pickup.ROOM)
    assert sword_and_bait(game) == (L4_SWORD_LEVEL, 0)
