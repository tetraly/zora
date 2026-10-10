"""ResolveProgressive past a line's top (docs/design/progressive-items-plan.md PI-CODE-02, note of
2026-10-08), in the emulator. With Add L4 Sword, InvSword can be 4: the line's first ID plus the
level owned is then $05 (the recorder), and stepping back once would give the bait ($04). The
routine steps back until the ID is in the line's slot, so at sword level 4 every path shows the
magical sword ($03), a shop hides its sword ware, and taking the sword changes nothing (grade 3
is below 4). The regression: every line, below and at its top, on the room, coast and Armos
paths (the caves and shops: tests/test_progressive_emulator.py)."""
import pytest

from tests.emulator import ITEMS, OBJ_STATE, OBJ_X, ROOM_ID, ROOM_ITEM_SLOT, Button
from tests.test_progressive_emulator import (
    BOOMERANG,
    CANDLE,
    COAST_SCREEN,
    GIVEN_POSITION,
    GIVEN_WARE,
    ITEM_ACTIVE,
    LINES,
    MAGICAL_SWORD,
    NO_ITEM,
    RING,
    ROOM_ITEM_ID,
    SHOP_WARE,
    SWORD,
    WOODEN_SWORD,
    ARROW,
    Game,
    Line,
    armos,
    fresh_game,
    shown_level,
)

L4_SWORD_LEVEL = 4
INV_FOOD = ITEMS + 0x06              # the bait: one step back from the recorder ($05)
LEVEL_WITH_ROOM_ITEMS = 1
ARMOS_REVEAL_FRAMES = (150, 300)     # walking down onto the statue, then up


def reveal_armos_item(game: Game, item: int) -> None:
    """Walk Link onto the Armos item's statue until the item stands revealed as `item`."""
    screen, statue_x = armos()
    game.go_to_screen(screen)
    game.emu[OBJ_X] = statue_x

    def revealed() -> bool:
        return game.emu[ROOM_ITEM_ID] == item and game.emu[OBJ_STATE + ROOM_ITEM_SLOT] == ITEM_ACTIVE
    try:
        game.emu.run_until(revealed, buttons=Button.DOWN, limit=ARMOS_REVEAL_FRAMES[0])
    except AssertionError:
        game.emu.run_until(revealed, buttons=Button.UP, limit=ARMOS_REVEAL_FRAMES[1])
    game.emu.run(60)


def assert_sword_kept_at_level_4(game: Game, path: str) -> None:
    assert (SWORD.level(game.emu), game.emu[INV_FOOD]) == (L4_SWORD_LEVEL, 0), path


# --- sword level 4 ---------------------------------------------------------------------------

def test_at_sword_level_4_the_wooden_sword_cave_shows_the_magical_sword() -> None:
    game = fresh_game()()
    SWORD.set_level(game.emu, L4_SWORD_LEVEL)
    game.enter_cave(GIVEN_WARE[SWORD])
    position = GIVEN_POSITION.get(SWORD, 1)
    assert game.wares()[position] == MAGICAL_SWORD
    game.take_ware(position)
    assert_sword_kept_at_level_4(game, "cave")


def test_at_sword_level_4_a_shop_hides_its_sword() -> None:
    game = fresh_game()()
    SWORD.set_level(game.emu, L4_SWORD_LEVEL)
    shop, position = SHOP_WARE[SWORD]
    game.enter_cave(shop)
    assert (game.wares()[position], game.price(position)) == (NO_ITEM, 0)


def test_at_sword_level_4_a_level_room_sword_shows_the_magical_sword() -> None:
    game = fresh_game()()
    SWORD.set_level(game.emu, L4_SWORD_LEVEL)
    game.enter_level(LEVEL_WITH_ROOM_ITEMS)
    game.reload_room_with_item(WOODEN_SWORD)
    assert game.room_item() == (MAGICAL_SWORD, ITEM_ACTIVE)
    game.take_room_item()
    assert_sword_kept_at_level_4(game, "room")


def test_at_sword_level_4_the_coast_item_shows_the_magical_sword() -> None:
    game = fresh_game(coast_item=WOODEN_SWORD)()
    SWORD.set_level(game.emu, L4_SWORD_LEVEL)
    game.go_to_screen(COAST_SCREEN)
    assert game.room_item() == (MAGICAL_SWORD, ITEM_ACTIVE)
    game.take_room_item()
    assert_sword_kept_at_level_4(game, "coast")


def test_at_sword_level_4_the_armos_item_shows_the_magical_sword() -> None:
    game = fresh_game(armos_item=WOODEN_SWORD)()
    SWORD.set_level(game.emu, L4_SWORD_LEVEL)
    reveal_armos_item(game, MAGICAL_SWORD)
    game.take_room_item()
    assert_sword_kept_at_level_4(game, "Armos")


# --- the regression: every line, below and at its top ------------------------------------------

def levels(line: Line) -> range:
    """Every level the player may hold, the top included."""
    return range(len(line.items) + 1)


def given_level(line: Line, level: int) -> int:
    return min(level + 1, len(line.items))


@pytest.mark.parametrize("line", LINES, ids=[line.name for line in LINES])
def test_room_items_show_and_give_each_level(line: Line) -> None:
    new = fresh_game()
    for level in levels(line):
        game = new()
        line.set_level(game.emu, level)
        game.enter_level(LEVEL_WITH_ROOM_ITEMS)
        game.reload_room_with_item(line.items[0])
        assert game.room_item() == (shown_level(line, level), ITEM_ACTIVE), level
        game.take_room_item()
        assert line.level(game.emu) == given_level(line, level), level


@pytest.mark.parametrize("line", LINES, ids=[line.name for line in LINES])
def test_the_coast_item_shows_and_gives_each_level(line: Line) -> None:
    new = fresh_game(coast_item=line.items[0])
    for level in levels(line):
        game = new()
        line.set_level(game.emu, level)
        game.go_to_screen(COAST_SCREEN)
        assert game.emu[ROOM_ID] == COAST_SCREEN
        assert game.room_item() == (shown_level(line, level), ITEM_ACTIVE), level
        game.take_room_item()
        assert line.level(game.emu) == given_level(line, level), level


@pytest.mark.parametrize("line", LINES, ids=[line.name for line in LINES])
def test_the_armos_item_shows_and_gives_each_level(line: Line) -> None:
    new = fresh_game(armos_item=line.items[0])
    for level in levels(line):
        game = new()
        line.set_level(game.emu, level)
        reveal_armos_item(game, shown_level(line, level))
        game.take_room_item()
        assert line.level(game.emu) == given_level(line, level), level


def test_the_lines_are_the_five() -> None:
    assert LINES == (SWORD, CANDLE, ARROW, RING, BOOMERANG)
