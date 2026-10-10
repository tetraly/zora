"""Shuffle Blue Potion's place, the potion shop's middle ware (owner design change, 2026-10-08;
zora/generate/steps/potion_shop.py): empty in PRG0, it holds whatever item is assigned there and
is sold once, while the shop's left blue potion stays a re-buyable ware.
  - the data: any item written into the middle ware reads back from the ROM, with the one-time
    ware table's bit for it set and the left and right potions' bits clear; without the flag the
    middle ware stays empty;
  - in the emulator: the middle ware is bought once (then gone, its bought bit set: Archipelago's
    check for it), and the left blue potion is bought again and again."""
from copy import deepcopy
from dataclasses import replace
from functools import cache

import pytest

from tests import test_progressive_emulator as hand_placed
from tests.emulator import ITEMS
from tests.test_assignment import _built, finish_unchecked, identity, reading
from zora import archipelago
from zora.flags import zora_flags
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.finish import FOREIGN_ITEM, Foreign
from zora.generate.pipeline import Built, generate_rom
from zora.generate.places import PlaceKind
from zora.generate.steps.potion_shop import potion_shop
from zora.model.enums import Destination, Item
from zora.model.item_names import ITEM_NAMES
from zora.model.overworld import POTION_SHOP_MIDDLE
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.code_patches import ONE_TIME_WARES, SHOPS_BY_NUMBER
from zora.rom.parse.rom_file import parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")

CASE = "every owner flag on"             # Shuffle Blue Potion on, with the other owner flags
SEED = 1
SHUFFLE_BLUE_POTION = zora_flags.encode(replace(zora_flags.DEFAULT, shuffle_blue_potion=ThreeState.ON))
POTION_SHOP_BIT = 1 << SHOPS_BY_NUMBER.index(Destination.POTION_SHOP)
INV_RAFT = ITEMS + 0x09
ANY_ITEM = sorted({*ITEM_NAMES, FOREIGN_ITEM})


def one_time_bits(rom: bytes) -> list[bool]:
    """The potion shop's bit at each ware position of ZORA_B1_OneTimeWares."""
    return [bool(rom[ONE_TIME_WARES + position] & POTION_SHOP_BIT) for position in range(3)]


def middle_place(built: Built) -> str:
    return next(place.name for place in built.places if place.kind == PlaceKind.POTION_SHOP)


# --- the data ----------------------------------------------------------------------------------

@pytest.mark.parametrize("item", ANY_ITEM, ids=lambda item: item.name)
def test_the_middle_ware_holds_any_item(item: Item) -> None:
    base = remember_repo_base_rom()
    built = _built(CASE, SEED)
    world = deepcopy(built.world)
    shop = potion_shop(world.overworld)
    assert shop.middle is not None
    shop.middle.item = item
    rom = serialize_to_rom(world, base, config=built.plan.config)
    parsed = potion_shop(parse_rom(rom, reading(built.plan.config)).overworld)
    assert parsed.middle is not None and parsed.middle.item == item
    assert [ware.item for ware in parsed.items] == [Item.BLUE_POTION, Item.RED_POTION]
    assert one_time_bits(rom) == [position == POTION_SHOP_MIDDLE for position in range(3)]


def test_zora_mode_sells_the_middle_ware_once_and_leaves_it_empty_without_the_flag() -> None:
    base = remember_repo_base_rom()
    with_flag = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, base, zora_flag_string=SHUFFLE_BLUE_POTION).rom
    without = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, base).rom
    assert potion_shop(parse_rom(with_flag).overworld).middle is not None
    assert one_time_bits(with_flag) == [False, True, False]
    assert potion_shop(parse_rom(without).overworld).middle is None
    table = slice(ONE_TIME_WARES, ONE_TIME_WARES + 3)
    assert without[table] == base[table]          # fp-prog-01 is not written: PRG0's bytes


# --- in the emulator ----------------------------------------------------------------------------

@cache
def rom_with_middle(item: Item) -> bytes:
    """CASE's world with `item` moved into the middle ware (and the middle ware's item to where
    `item` was)."""
    built = _built(CASE, SEED)
    assignment: dict[str, Item | Foreign] = identity(built)
    name = middle_place(built)
    if assignment[name] != item:
        source = next(place for place, held in assignment.items() if held == item)
        assignment[source], assignment[name] = assignment[name], item
    return finish_unchecked(built, remember_repo_base_rom(), assignment)


class PotionShopGame(hand_placed.Game):
    """hand_placed.Game on a finished ROM, finding the potion shop on its own screen, with the
    letter shown and no potion held."""

    def __init__(self, rom: bytes) -> None:
        super().__init__(rom)
        self.screen = next(screen.screen_num for screen in parse_rom(rom).overworld.screens
                           if screen.destination == Destination.POTION_SHOP)
        self.emu[hand_placed.INV_LETTER] = hand_placed.LETTER_DELIVERED
        self.emu[hand_placed.POTION] = 0

    def enter_cave(self, destination: Destination = Destination.POTION_SHOP) -> None:
        self.go_to_screen(self.screen)
        self.start_mode(hand_placed.CAVE_MODE)
        self.wait_for_play(hand_placed.CAVE_MODE)
        self.emu.run(hand_placed.CAVE_INIT_FRAMES)

    def buy(self, position: int) -> None:
        self.emu[hand_placed.INV_RUPEES] = hand_placed.FULL_RUPEES
        self.enter_cave()
        self.take_ware(position)
        self.leave_cave()


@pytest.mark.parametrize(("item", "inventory", "value"), [
    (Item.RAFT, INV_RAFT, 1),
    (Item.BLUE_POTION, hand_placed.POTION, 1),
], ids=["raft", "blue potion"])
def test_the_middle_ware_is_bought_once_and_the_left_potion_again_and_again(
        item: Item, inventory: int, value: int) -> None:
    game = PotionShopGame(rom_with_middle(item))
    game.enter_cave()
    assert game.wares() == [Item.BLUE_POTION, item, Item.RED_POTION]
    game.take_ware(POTION_SHOP_MIDDLE)
    assert game.emu[inventory] == value
    assert game.bought()[POTION_SHOP_MIDDLE] & POTION_SHOP_BIT
    check = archipelago.pickup_check(next(place for place in _built(CASE, SEED).places
                                          if place.kind == PlaceKind.POTION_SHOP))
    assert check.address == hand_placed.SHOP_BOUGHT_FLAGS + POTION_SHOP_MIDDLE
    assert check.is_set({check.address: game.emu[check.address]})
    game.leave_cave()
    game.emu[hand_placed.POTION] = 0
    for bought in range(1, 3):
        game.buy(0)
        assert game.emu[hand_placed.POTION] == bought
    game.emu[hand_placed.POTION] = 0
    game.enter_cave()
    assert game.wares() == [Item.BLUE_POTION, hand_placed.NO_ITEM, Item.RED_POTION]
    game.take_ware(0)
    assert game.emu[hand_placed.POTION] == 1
    assert game.bought()[0] == 0 and not game.emu.nes.has_crashed
