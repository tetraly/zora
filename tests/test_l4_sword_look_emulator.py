"""Add L4 Sword's look (asm/asnb/l4-sword-look; docs/design/l4-sword.md Q2) in the emulator: the
sword's sprites as the game draws them, read from OAM (tile, palette row), on
tests/test_asnb_emulator.py's ROM (ZORA's MVP-baseline output with the progressive patches, test
wares, a wooden sword in each sword cave and the ASNB patches) against the same ROM without
l4-sword-look, today's look.

  - The A box, the swing (each direction) and the beam at sword levels 1-4; the item screen,
    which draws no sword. Levels 1-3 are drawn as today. Level 4: the magical sword's icon in
    row 1 in the A box (today the plain sword's icon in row 3), the swing in row 1 (today row 3);
    the beam as today.
  - A sword item on every path (the three sword caves, a shop, a dungeon room, an item cellar,
    the coast and the Armos) at sword levels 0-4: as today at levels 0-2; at levels 3 and 4,
    where it is the magical sword ($03) and the L4 item, the magical sword's icon in row 1 (today
    row 2). A shop hides it at level 4.
  - Link holding it up, taken from a cave at sword level 3: in row 1 (today row 2)."""
from collections.abc import Callable
from functools import cache

import pytest

from tests.emulator import ITEMS, MENU_STATE, OBJ_STATE, OBJ_X, OBJ_Y, Button
from tests.test_asnb_emulator import (
    SWORD_CAVE_WARE,
    SWORD_CAVES,
    Pickup,
    show_sword,
)
from tests.test_asnb_patches import build as asnb
from tests.test_progressive_emulator import (
    CAVE_ITEM_IDS,
    CAVE_WARE_XS,
    CAVE_WARE_Y,
    SWORD,
    WOODEN_SWORD,
    Game,
    build,
    cave_type,
    rom_with_test_wares,
)

LOOK = "l4-sword-look"
L4_SWORD_LEVEL = 4
SWORD_LEVELS = range(1, L4_SWORD_LEVEL + 1)
# Sprite tiles: the sword's vertical and horizontal frames (the swing, the beam, the plain sword's
# icon) and the magical sword's icon (item slot $20).
SWORD_TILE, SWORD_SIDE_TILE, MAGICAL_SWORD_TILE = 0x20, 0x82, 0x48
SWORD_TILES = frozenset({SWORD_TILE, SWORD_SIDE_TILE, MAGICAL_SWORD_TILE})
PALETTE_ROW_MASK = 0x03
WHITE_SWORD_ROW, MAGICAL_SWORD_ROW, LEVEL_PALETTE_ROW = 1, 2, 3
STATUS_BAR_Y = 0x1F
A_BOX_X = 0x98                        # DrawStatusBarSword's X $94, centred for a narrow item
HIDDEN_Y = 0xEF                       # a sprite at Y >= $EF is off screen
OAM = 0x200
OAM_RECORDS = 64
SWORD_OBJECT_SLOT, SHOT_OBJECT_SLOT = 0x0D, 0x0E
SWING_SHOWN_STATE = 2                 # UpdateSwordOrRod draws the sword from state 2 to 4
SWING_FRAMES = 16
BEAM_FRAMES = 4                       # the beam cycles the four rows, one each frame
HEART_PARTIAL = 0x670                 # full: the beam needs full hearts
FULL = 0xFF
UNDERWORLD_MENU_OPEN = 7              # MenuState once the item screen is down in a level
MENU_FRAMES = 300
WALK_IN_FRAMES = 40                   # up out of the start room's doorway, where Link can't swing
ITEM_FRAMES = 8
LIFT_TIMER = 0x506                    # ItemLiftTimer
TAKE_FRAMES, LIFT_SETTLE_FRAMES = 600, 20
TAKEN_WARE = 0xFF                     # a cave ware's ID once taken
LEVEL_1 = 1
DIRECTIONS = {"up": Button.UP, "down": Button.DOWN, "left": Button.LEFT, "right": Button.RIGHT}

Sprite = tuple[int, int, int, int]    # Y, tile, attributes, X


# --- ROMs and games -------------------------------------------------------------------------------

@cache
def rom(look: bool, armos_item: int | None = None, coast_item: int | None = None) -> bytes:
    """test_asnb_emulator.asnb_rom, with l4-sword-look or without it."""
    out = rom_with_test_wares(True, "", armos_item, coast_item)
    for destination in SWORD_CAVES:
        out = build.with_ware(out, cave_type(destination), SWORD_CAVE_WARE, WOODEN_SWORD)
    names = tuple(name for name in asnb.PATCHES if look or name != LOOK)
    return bytes(asnb.apply_patches(out, names))


@cache
def new_game(look: bool, armos_item: int | None = None, coast_item: int | None = None) -> Callable[[], Game]:
    game = Game(rom(look, armos_item, coast_item))
    state = game.emu.save()

    def new() -> Game:
        game.emu.load(state)
        return game
    return new


def game_for(look: bool, sword_level: int, path: Pickup | None = None) -> Game:
    placed = {Pickup.COAST: {"coast_item": WOODEN_SWORD}, Pickup.ARMOS: {"armos_item": WOODEN_SWORD}}
    items = placed.get(path, {}) if path is not None else {}
    game = new_game(look, **items)()
    SWORD.set_level(game.emu, sword_level)
    return game


# --- reading the sprites ---------------------------------------------------------------------------

def sword_sprites(game: Game) -> list[Sprite]:
    """The OAM records with a sword tile, on screen."""
    oam = game.emu.sprites()
    records = (tuple(oam[i:i + 4]) for i in range(0, OAM_RECORDS * 4, 4))
    return [record for record in records if record[0] < HIDDEN_Y and record[1] in SWORD_TILES]  # type: ignore[misc]


def look_of(record: Sprite) -> tuple[int, int]:
    """(tile, palette row)."""
    return record[1], record[2] & PALETTE_ROW_MASK


def a_box(game: Game) -> list[Sprite]:
    return [record for record in sword_sprites(game) if (record[0], record[3]) == (STATUS_BAR_Y, A_BOX_X)]


def outside_the_status_bar(game: Game) -> list[Sprite]:
    return [record for record in sword_sprites(game) if record[0] != STATUS_BAR_Y]


@cache
def in_hand(look: bool, level: int) -> dict[str, list[Sprite]]:
    """In level 1's start room at `level`: the A box, the item screen's sword sprites, the swing's
    sword at state 2 in each direction and the beam's four frames (shot up)."""
    game = game_for(look, level)
    game.emu[HEART_PARTIAL] = FULL
    game.enter_level(LEVEL_1)
    game.emu.run(WALK_IN_FRAMES, Button.UP)
    game.emu.run(10)
    seen: dict[str, list[Sprite]] = {"A box": a_box(game)}
    game.emu.press(Button.START)
    game.emu.run_until(lambda: game.emu[MENU_STATE] == UNDERWORLD_MENU_OPEN, limit=MENU_FRAMES)
    game.emu.run(10)
    seen["item screen"] = sword_sprites(game)
    game.emu.press(Button.START)
    game.emu.run_until(lambda: game.emu[MENU_STATE] == 0, limit=MENU_FRAMES)
    game.emu.run(10)
    for name, button in DIRECTIONS.items():
        game.emu.run(4, button)
        game.emu.run(10)
        game.emu.press(Button.A, after=0)
        for _ in range(SWING_FRAMES):
            game.emu.run(1)
            if game.emu[OBJ_STATE + SWORD_OBJECT_SLOT] & 0x0F == SWING_SHOWN_STATE:
                seen[f"swing {name}"] = [record for record in outside_the_status_bar(game)
                                         if abs(record[3] - game.emu[OBJ_X + SWORD_OBJECT_SLOT]) <= 8]
                break
        if name == "up":
            game.emu.run_until(lambda: game.emu[OBJ_STATE + SHOT_OBJECT_SLOT] != 0, limit=SWING_FRAMES)
            game.emu.run(2)                     # the shot moves off Link before it is drawn alone
            for frame in range(BEAM_FRAMES):
                game.emu.run(1)
                x, y = game.emu[OBJ_X + SHOT_OBJECT_SLOT], game.emu[OBJ_Y + SHOT_OBJECT_SLOT]
                seen[f"beam {frame}"] = [record for record in outside_the_status_bar(game)
                                         if abs(record[3] - x) <= 8 and abs(record[0] - y) <= 8]
        game.emu.run(40)
    return seen


def world_item(look: bool, path: Pickup, level: int) -> set[tuple[int, int]]:
    """The looks (tile, row) the path's sword item is drawn with, over a few frames."""
    game = game_for(look, level, path)
    show_sword(game, path)
    looks: set[tuple[int, int]] = set()
    for _ in range(ITEM_FRAMES):
        game.emu.run(1)
        looks |= {look_of(record) for record in outside_the_status_bar(game)}
    return looks


# --- the A box, the item screen, the swing and the beam ------------------------------------------------

@pytest.mark.parametrize("level", list(SWORD_LEVELS))
def test_in_hand_levels_1_to_3_are_drawn_as_today_and_level_4_in_row_1(level: int) -> None:
    today, now = in_hand(False, level), in_hand(True, level)
    assert set(now) == set(today) == {"A box", "item screen", *(f"swing {name}" for name in DIRECTIONS),
                                      *(f"beam {frame}" for frame in range(BEAM_FRAMES))}
    assert now["item screen"] == today["item screen"] == []
    for frame in range(BEAM_FRAMES):
        assert now[f"beam {frame}"] == today[f"beam {frame}"] != [], frame
    if level < L4_SWORD_LEVEL:
        assert now == today
        return
    assert [look_of(record) for record in today["A box"]] == [(SWORD_TILE, LEVEL_PALETTE_ROW)]
    assert [look_of(record) for record in now["A box"]] == [(MAGICAL_SWORD_TILE, WHITE_SWORD_ROW)]
    for name in DIRECTIONS:
        swing, swing_today = now[f"swing {name}"], today[f"swing {name}"]
        assert swing_today and len(swing) == len(swing_today), name
        for record, record_today in zip(swing, swing_today, strict=True):
            assert look_of(record_today)[1] == LEVEL_PALETTE_ROW, name
            # The same sprite, tile and flips; only the row is the white sword's.
            assert record == (*record_today[:2], record_today[2] & ~PALETTE_ROW_MASK | WHITE_SWORD_ROW,
                              record_today[3]), name


# --- the sword items ----------------------------------------------------------------------------------

@pytest.mark.parametrize("path", list(Pickup), ids=[path.value for path in Pickup])
def test_a_sword_item_has_level_4s_look_where_it_gives_level_4(path: Pickup) -> None:
    for level in range(L4_SWORD_LEVEL + 1):
        today, now = world_item(False, path, level), world_item(True, path, level)
        if path is Pickup.SHOP and level == L4_SWORD_LEVEL:
            assert today == now == set()                     # the shop hides its sword
        elif level < 3:
            assert now == today != set(), level
        else:
            assert today == {(MAGICAL_SWORD_TILE, MAGICAL_SWORD_ROW)}, level
            assert now == {(MAGICAL_SWORD_TILE, WHITE_SWORD_ROW)}, level


def held_up(look: bool) -> set[tuple[int, int]]:
    """Take the wooden-sword cave's sword at sword level 3 (it gives level 4) and read the sword
    Link holds up."""
    game = game_for(look, 3, Pickup.WOOD_SWORD_CAVE)
    show_sword(game, Pickup.WOOD_SWORD_CAVE)
    game.emu[OBJ_X] = CAVE_WARE_XS[SWORD_CAVE_WARE]
    game.emu[OBJ_Y] = CAVE_WARE_Y
    game.emu.run_until(lambda: game.emu[CAVE_ITEM_IDS + SWORD_CAVE_WARE] == TAKEN_WARE, limit=TAKE_FRAMES)
    game.emu.run(LIFT_SETTLE_FRAMES)
    assert game.emu[ITEMS] == L4_SWORD_LEVEL and game.emu[LIFT_TIMER]
    return {look_of(record) for record in outside_the_status_bar(game)}


def test_link_holds_up_the_l4_sword_in_row_1() -> None:
    assert held_up(False) == {(MAGICAL_SWORD_TILE, MAGICAL_SWORD_ROW)}
    assert held_up(True) == {(MAGICAL_SWORD_TILE, WHITE_SWORD_ROW)}
