"""Shuffle Minor Dungeon Drops (B17; post-shapes-b1.md PS-ITEM-14) in the emulator: a cave slot that
holds bombs, five rupees or a key gives it as a dungeon room would. On the spec's Check string (CP-5
with B17 on), seeds whose Armos, white-sword cave or coast slot the deal gave a minor item: the
item is shown and taken, and the inventory gains four bombs, five rupees or a key. ZORA keeps keys
out of the white-sword cave (owner ruling 2026-10-27), so no seed has one there."""
from functools import cache

import pytest

from tests.emulator import INV_BOMBS, INV_KEYS, OBJ_STATE, OBJ_X, ROOM_ID, ROOM_ITEM_SLOT, Button
from tests.needs import needs_base_rom
from tests.test_progressive_emulator import (
    CAVE_INIT_FRAMES,
    CAVE_MODE,
    INV_RUPEES,
    ITEM_ACTIVE,
    ROOM_ITEM_ID,
    Game,
)
from zora.generate.pipeline import build, generate_rom, plan
from zora.model.enums import Destination, Item
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom

pytestmark = [needs_base_rom, pytest.mark.slow]

B17_ON = "8hq4BeR1JY64WVOsObF4MXVt3QUJ3A"       # PS-ITEM-14's Check string
COAST_SCREEN = 0x5F
WHITE_SWORD_WARE = 1                           # the cave's middle ware
BOMBS_GIVEN, RUPEES_GIVEN, KEYS_GIVEN = 4, 5, 1
REVEAL_LIMIT = 300
# (slot, item, seed): the first of seeds 1-40 whose slot holds the item
CASES = (("armos", Item.BOMBS, 9), ("armos", Item.FIVE_RUPEES, 2), ("armos", Item.KEY, 1),
         ("white_sword", Item.BOMBS, 1), ("white_sword", Item.FIVE_RUPEES, 4),
         ("coast", Item.BOMBS, 4), ("coast", Item.FIVE_RUPEES, 28), ("coast", Item.KEY, 1))


@cache
def rom(seed: int) -> bytes:
    return generate_rom(B17_ON, seed, remember_repo_base_rom()).rom


def gained(game: Game, item: Item) -> int:
    address = {Item.BOMBS: INV_BOMBS, Item.FIVE_RUPEES: INV_RUPEES, Item.KEY: INV_KEYS}[item]
    return game.emu[address]


def take_from_the_armos(game: Game, seed: int) -> None:
    overworld = parse_rom(rom(seed)).overworld
    game.go_to_screen(overworld.armos_screen_ids[0])
    game.emu[OBJ_X] = overworld.armos_positions[0]
    revealed = lambda: game.emu[OBJ_STATE + ROOM_ITEM_SLOT] == ITEM_ACTIVE and game.emu[ROOM_ID] > 0  # noqa: E731
    try:
        game.emu.run_until(revealed, buttons=Button.DOWN, limit=150)
    except AssertionError:
        game.emu.run_until(revealed, buttons=Button.UP, limit=REVEAL_LIMIT)
    game.emu.run(60)
    game.take_room_item()


def take_from_the_white_sword_cave(game: Game, seed: int) -> None:
    screen = next(screen.screen_num for screen in parse_rom(rom(seed)).overworld.screens
                  if screen.destination == Destination.WHITE_SWORD_CAVE)
    game.go_to_screen(screen)
    game.start_mode(CAVE_MODE)
    game.wait_for_play(CAVE_MODE)
    game.emu.run(CAVE_INIT_FRAMES)
    game.take_ware(WHITE_SWORD_WARE)


def take_from_the_coast(game: Game, _seed: int) -> None:
    game.go_to_screen(COAST_SCREEN)
    assert game.emu[OBJ_STATE + ROOM_ITEM_SLOT] == ITEM_ACTIVE
    game.take_room_item()


TAKE = {"armos": take_from_the_armos, "white_sword": take_from_the_white_sword_cave, "coast": take_from_the_coast}


@pytest.mark.parametrize(("slot", "item", "seed"), CASES, ids=[f"{slot}-{item.name.lower()}" for slot, item, _ in CASES])
def test_a_cave_slot_gives_its_minor_item(slot: str, item: Item, seed: int) -> None:
    result = build(plan(B17_ON, seed), remember_repo_base_rom()).result.item_shuffle_result
    assert result is not None and result.caves[slot] == item
    game = Game(rom(seed))
    game.emu[INV_RUPEES] = game.emu[INV_BOMBS] = game.emu[INV_KEYS] = 0
    TAKE[slot](game, seed)
    if slot != "white_sword":
        assert game.emu[ROOM_ITEM_ID] == item
    expected = {Item.BOMBS: BOMBS_GIVEN, Item.FIVE_RUPEES: RUPEES_GIVEN, Item.KEY: KEYS_GIVEN}[item]
    assert gained(game, item) == expected
