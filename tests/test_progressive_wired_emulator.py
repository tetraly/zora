"""PI-CODE-07's three RAM cases on a wired ZORA ROM (docs/design/progressive-items-plan.md):
generate_rom with Progressive Items on (B09 off, PI-FLAG-03), so the patches, their per-seed
bytes, FP-START-01's table and FP-HOT-01's $067A byte are all ZORA's own. The shop ware bought
is a one-time ware of the seed's own stock (the blue ring, candle or arrows). The patched
routines' other cases run in tests/test_progressive_emulator.py on hand-placed wares."""
from functools import cache

import pytest

from tests import test_progressive_emulator as hand_placed
from tests.emulator import Emulator
from zora.flags.codec import decode, encode
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.model.enums import Destination, Item
from zora.model.overworld import Shop
from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.rom.code_patches import ONE_TIME_WARES, PROGRESSIVE_ITEMS_BYTE, REBUYABLE_ITEMS
from zora.rom.parse.rom_file import parse_rom

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")

FLAGS = encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(toggles={"B09": ThreeState.OFF}))
PROGRESSIVE_ITEMS = "2.O"
SEED = 1
SHOPS = (Destination.SHOP_1, Destination.SHOP_2, Destination.SHOP_3, Destination.SHOP_4)


@cache
def wired_rom() -> bytes:
    return generate_rom(FLAGS, SEED, verify_base_rom().read_bytes(), zora_flag_string=PROGRESSIVE_ITEMS).rom


@cache
def wired_screens() -> dict[Destination, int]:
    found: dict[Destination, int] = {}
    for screen in parse_rom(wired_rom()).overworld.screens:
        found.setdefault(Destination(screen.destination), screen.screen_num)
    return found


@cache
def one_time_ware() -> tuple[Destination, int, Item]:
    """The first shop ware, in shop order, that is sold once: not a re-buyable item."""
    for cave in parse_rom(wired_rom()).overworld.caves:
        if isinstance(cave, Shop) and cave.destination in SHOPS:
            for position, ware in enumerate(cave.items):
                if ware.item not in REBUYABLE_ITEMS:
                    return cave.destination, position, ware.item
    raise AssertionError("no one-time ware")


class WiredGame(hand_placed.Game):
    """hand_placed.Game on the wired ROM, finding caves on its own screens."""

    def __init__(self) -> None:
        self.emu = Emulator(wired_rom())
        self.zora_flags = PROGRESSIVE_ITEMS
        self.emu.new_game()
        self.emu[hand_placed.INV_RUPEES] = hand_placed.FULL_RUPEES

    def enter_cave(self, destination: Destination) -> None:
        self.go_to_screen(wired_screens()[destination])
        self.start_mode(hand_placed.CAVE_MODE)
        self.wait_for_play(hand_placed.CAVE_MODE)
        self.emu.run(hand_placed.CAVE_INIT_FRAMES)


def buy_the_one_time_ware(game: WiredGame) -> int:
    shop, position, _ = one_time_ware()
    game.enter_cave(shop)
    assert game.wares()[position] != hand_placed.NO_ITEM
    game.take_ware(position)
    game.leave_cave()
    assert game.bought()[position]
    return position


def test_the_wired_rom_carries_the_patches_and_its_bytes() -> None:
    rom = wired_rom()
    assert rom[PROGRESSIVE_ITEMS_BYTE] == 1
    shop, position, _ = one_time_ware()
    shop_number = 1 + SHOPS.index(shop)
    assert rom[ONE_TIME_WARES + position] & (1 << shop_number)


def test_a_new_file_starts_with_no_bought_bits() -> None:
    """New file: Items+$20..$22 are 0, also in a file registered after another file saved its
    bought bits."""
    game = WiredGame()
    assert game.bought() == [0, 0, 0]
    position = buy_the_one_time_ware(game)
    game.emu.open_item_screen()
    game.emu.save_and_reload()
    assert game.bought()[position]
    game.emu.reset()
    game.emu.boot_to_file_select()
    game.emu.register_file()
    game.emu.start_game(1)
    assert game.bought() == [0, 0, 0]
    game.emu[hand_placed.INV_RUPEES] = hand_placed.FULL_RUPEES
    game.enter_cave(one_time_ware()[0])
    assert game.wares()[position] != hand_placed.NO_ITEM


def test_continue_keeps_the_bought_bits() -> None:
    game = WiredGame()
    position = buy_the_one_time_ware(game)
    bought = game.bought()
    game.continue_screen(hand_placed.CONTINUE_CHOICE)
    game.wait_for_play()
    assert game.bought() == bought
    game.enter_cave(one_time_ware()[0])
    assert game.wares()[position] == hand_placed.NO_ITEM


def test_save_reset_and_reload_keep_the_bought_bits() -> None:
    game = WiredGame()
    position = buy_the_one_time_ware(game)
    bought = game.bought()
    game.emu.open_item_screen()
    game.emu.save_and_reload()
    assert game.bought() == bought
    game.emu[hand_placed.INV_RUPEES] = hand_placed.FULL_RUPEES
    game.enter_cave(one_time_ware()[0])
    assert game.wares()[position] == hand_placed.NO_ITEM
    assert not game.emu.nes.has_crashed
