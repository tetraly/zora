"""Another player's item in an Archipelago game's ROM (docs/design/archipelago-items.md piece 5): written
as the code of its class (finish.FOREIGN_ITEMS: $34 progression, $35 useful, $36 filler) and drawn by
asm/flags2/ap-items' far routines as the 16x16 Archipelago logo (binarybrain11's art, background tiles
$5C-$5F; zora/rom/archipelago_logo.py), in the red, blue or Link's palette row as the swords are
colored; its take gives nothing and sets the place's pickup flag (the client's location check). The
look setting "Other players' items look like" is retired: any value is accepted and ignored, and the
shops' real magical shields stay shields.

In the emulator, with this case's Progressive Items, Pegasus Boots and Item Sprites: a room, the White
Sword Cave and a shop each show their class's logo, unflipped, side by side, and give nothing."""
from functools import cache

import pytest

from tests.archipelago_cases import FLAG_CASES
from tests.test_archipelago_interface import by_name
from tests.test_assignment_emulator import CAVE_ITEM_IDS, HEART_VALUES, INV_RUPEES, Console, floor_room
from tests.test_progressive_emulator import NO_ITEM
from zora import archipelago
from zora.generate import pipeline
from zora.generate.finish import FOREIGN_ITEMS, Foreign, ItemClass
from zora.generate.places import Place, PlaceKind, _screens, read_item
from zora.generate.steps.group_banks import OVERWORLD
from zora.generate.steps.randomize_boss_groups import packed_slots
from zora.model.enums import Destination, Item
from zora.model.game_world import GameWorld
from zora.model.overworld import Shop
from zora.rom import archipelago_logo, inventory
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

CASE = "every owner flag on"                 # shop wares joined, so a shop ware is a place
SEED = 1
WHITE_SWORD_CAVE = "White Sword Cave"
WHITE_SWORD_WARE = 1                         # the cave's middle ware
OAM_ENTRY = 4
SPRITE_PALETTE_BITS = 0x03
LOGO_TILE_BYTES = set(archipelago_logo.LOGO_SPRITE_TILES)
FLIP_BITS = 0xC0
HIDDEN_Y = 0xEF                              # an OAM record at this Y or below the screen is not drawn
PLAY_FRAMES = 30
RUPEE_COUNT_FRAMES = 300                     # the rupee counter runs down after a purchase
# The palette row each class's logo is drawn in, as DrawItemBySlot colors the three swords
PALETTE_ROWS = {ItemClass.PROGRESSION: 2, ItemClass.USEFUL: 1, ItemClass.FILLER: 0}
# The inventory but the hearts, which fill over time, the rupees and a shop's bought flags (fp-prog-01
# marks a ware place sold once)
KEPT_BYTES_BUT = {HEART_VALUES, HEART_VALUES + 1, INV_RUPEES,
                  *range(inventory.SHOP_BOUGHT_FLAGS, inventory.SHOP_BOUGHT_FLAGS + 3)}


@cache
def result() -> archipelago.BuildResult:
    return archipelago.build_from_strings(*FLAG_CASES[CASE], SEED, remember_repo_base_rom())


@cache
def foreign_places() -> dict[str, ItemClass]:
    """A floor room, a shop ware and the White Sword Cave, each given another player's item of a class."""
    built = result().state
    shop_ware = next(place.name for place in built.places if place.kind is PlaceKind.SHOP_WARE)
    return {floor_room(built).name: ItemClass.PROGRESSION, shop_ware: ItemClass.USEFUL,
            WHITE_SWORD_CAVE: ItemClass.FILLER}


def assignment() -> dict[str, str | archipelago.Foreign]:
    return {**by_name(result()), **{name: Foreign(item_class) for name, item_class in foreign_places().items()}}


def received() -> list[str]:
    """The items those places held, which this player then receives from other worlds."""
    own = by_name(result())
    return [str(own[name]) for name in foreign_places()]


@cache
def rom(**player_settings: str) -> bytes:
    return archipelago.finish(result(), assignment(), received(), player_settings=player_settings)


def place(name: str) -> Place:
    return next(place for place in result().state.places if place.name == name)


def test_each_class_is_written_as_its_code_and_the_logo_is_written() -> None:
    image = rom()
    world = parse_rom(image)
    for name, item_class in foreign_places().items():
        assert read_item(world, place(name)) == FOREIGN_ITEMS[item_class], name
    for offset, data in archipelago_logo.logo_writes():
        assert image[offset:offset + len(data)] == data
    recipe = archipelago.recipe(result(), assignment(), received())
    assert archipelago.rom_from_recipe(recipe, remember_repo_base_rom()) == image


def test_the_shops_shields_stay_shields() -> None:
    """Up to piece 5 the logo look turned every shop's real magical shield into a fairy."""
    own = parse_rom(archipelago.finish(result(), by_name(result())))
    world = parse_rom(rom())
    foreign = {(destination, position) for name in foreign_places()
               if (destination := place(name).destination) is not None and (position := place(name).position) is not None}

    def shields(world: GameWorld) -> set[tuple[Destination, int]]:
        return {(shop.destination, position) for shop in world.overworld.caves if isinstance(shop, Shop)
                for position, ware in enumerate(shop.items) if ware.item == Item.MAGICAL_SHIELD}

    assert shields(own) - foreign
    assert shields(world) == shields(own) - foreign


@pytest.mark.parametrize("given", [{"foreignItemLook": "logo"}, {"foreignItemLook": "rupee"},
                                   {"foreign_item_look": "logo"}, {"foreign_item_look": "anything"}])
def test_the_retired_look_setting_is_accepted_and_ignored(given: dict[str, str]) -> None:
    archipelago.check_player_settings(given)
    assert rom(**given) == rom()
    assert "foreignItemLook" not in archipelago.MULTIWORLD_SETTINGS
    assert "foreign_item_look" in archipelago.RETIRED_MULTIWORLD_SETTINGS


def oam_records(console: Console) -> list[bytes]:
    sprites = console.emu.sprites()
    return [sprites[i:i + OAM_ENTRY] for i in range(0, len(sprites), OAM_ENTRY)]


def assert_the_logo(console: Console, item_class: ItemClass) -> None:
    logo = sorted((record for record in oam_records(console) if record[1] in LOGO_TILE_BYTES and record[0] < HIDDEN_Y),
                  key=lambda record: record[3])
    assert [record[1] for record in logo] == list(archipelago_logo.LOGO_SPRITE_TILES), item_class  # left, right
    assert logo[1][3] - logo[0][3] == 8                                                            # side by side
    assert {record[2] & SPRITE_PALETTE_BITS for record in logo} == {PALETTE_ROWS[item_class]}
    assert not any(record[2] & FLIP_BITS for record in logo)                                       # not mirrored


def kept(console: Console) -> dict[int, int]:
    return {address: console.emu[address] for address in range(inventory.ITEMS, inventory.MAX_BOMBS + 1)
            if address not in KEPT_BYTES_BUT}


def assert_checked(console: Console, name: str) -> None:
    check = archipelago.pickup_checks(result())[name]
    assert check.is_set({check.address: console.emu[check.address]}), name


def test_a_room_shows_the_progression_logo_gives_nothing_and_is_checked() -> None:
    name = next(name for name, item_class in foreign_places().items() if item_class is ItemClass.PROGRESSION)
    room = place(name)
    assert room.level is not None and room.room_num is not None
    console = Console(rom())
    console.enter_room(room.level, room.room_num)
    console.emu.run(PLAY_FRAMES)
    assert_the_logo(console, ItemClass.PROGRESSION)
    held = kept(console)
    console.take_room_item()
    assert kept(console) == held
    assert_checked(console, name)


def test_the_white_sword_cave_shows_the_filler_logo_and_gives_nothing() -> None:
    cave = place(WHITE_SWORD_CAVE)
    console = Console(rom())
    console.enter_cave(cave.screens[0])
    assert console.emu[CAVE_ITEM_IDS + WHITE_SWORD_WARE] & NO_ITEM == FOREIGN_ITEMS[ItemClass.FILLER]
    console.emu.run(PLAY_FRAMES)
    assert_the_logo(console, ItemClass.FILLER)
    held = kept(console)
    console.take_ware(WHITE_SWORD_WARE)
    assert kept(console) == held
    assert_checked(console, WHITE_SWORD_CAVE)


def test_a_shop_sells_the_useful_logo() -> None:
    name = next(name for name, item_class in foreign_places().items() if item_class is ItemClass.USEFUL)
    ware = place(name)
    assert ware.destination is not None and ware.position is not None
    image = rom()
    world = parse_rom(image)
    shop = world.overworld.get_cave(ware.destination, Shop)
    assert shop is not None
    price = shop.items[ware.position].price
    console = Console(image)
    console.enter_cave(_screens(world, ware.destination)[0])
    assert console.emu[CAVE_ITEM_IDS + ware.position] & NO_ITEM == FOREIGN_ITEMS[ItemClass.USEFUL]
    console.emu.run(PLAY_FRAMES)
    assert_the_logo(console, ItemClass.USEFUL)
    rupees, held = console.emu[INV_RUPEES], kept(console)
    console.take_ware(ware.position)
    assert kept(console) == held
    console.emu.run_until(lambda: console.emu[INV_RUPEES] == rupees - price, limit=RUPEE_COUNT_FRAMES)
    assert_checked(console, name)


# The logo's background tiles ($5C-$5F) and Randomize Boss Groups (B40): the bosses' common block is $30-$4F
# in every game (owner decision 2026-11-14), so the logo is drawn whole whatever the deal.
def boss_tiles(built: pipeline.Built) -> set[int]:
    groups = built.result.groups
    assert groups is not None and groups.boss_deal is not None
    return {tile for block, _boss, _sprite, slots in packed_slots(groups.boss_deal) if block == OVERWORLD
            for tile in slots}


def test_the_bosses_never_take_the_logo_tiles() -> None:
    built = result().state
    assert built.plan.steps.randomize_boss_groups
    assert boss_tiles(built) <= set(range(0x30, 0x50))
    assert not boss_tiles(built) & set(archipelago_logo.LOGO_BACKGROUND_TILES)
