"""Other players' items look like (foreign_item_look; owner decision 2026-10-18; the spec "ZORA
Archipelago beta 5 fixes", item 4): an Archipelago game's setting of the page's Multiworld mode.

A rupee (the default): another player's item is written as one rupee ($18; five rupees, $0F, up to
beta 5), and none of the logo's bytes is written. The Archipelago logo: it is written as the
magical shield ($1C), drawn as the 16x16 logo from background tiles of its own (binarybrain11's
art), whose take does nothing and whose palette is blue (zora/rom/archipelago_logo.py); every shop's
real magical shield becomes a fairy priced 20-40, drawn from FINISH's stream, so the recipe rebuilds
the same ROM.

In the emulator, on the logo ROM: a room holding another player's item draws the logo's two 8x16
halves side by side, unflipped, in the blue palette; taking it leaves the inventory as it was and
sets the room's pickup flag (the
client's location check); a shop that sold the magical shield shows a fairy at its new price, and
buying it takes that price and fills Link's hearts. With Progressive Items on, the White Sword Cave
and a shop show another player's item and give it (its descriptor is no upgrade line)."""
from functools import cache

import pytest

from tests.archipelago_cases import FLAG_CASES
from tests.test_archipelago_interface import by_name
from tests.test_assignment_emulator import CAVE_ITEM_IDS, HEART_VALUES, INV_RUPEES, Console, floor_room
from tests.test_progressive_emulator import NO_ITEM
from zora import archipelago
from zora.generate.finish import FOREIGN, LOGO_SHOP_FAIRY_PRICES, ForeignLook
from zora.generate import pipeline
from zora.generate.places import PlaceKind, _screens, read_item
from zora.generate.steps.group_banks import OVERWORLD
from zora.generate.steps.randomize_boss_groups import packed_slots
from zora.model.enums import Destination, Item
from zora.model.overworld import Shop
from zora.rom import archipelago_logo, inventory
from zora.rom.base_rom import BASE_ROM_PATH, original_bytes, remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

CASE = "every owner flag on"                 # shop wares joined, so a shop ware is a place
SEED = 1
LOOK = archipelago.PAGE_FOREIGN_ITEM_LOOK
OAM_ENTRY = 4
SPRITE_PALETTE_BITS = 0x03
FAIRY = 0x23
# The logo's two 8x16 sprites in OAM: tiles $5D and $5F (odd: the background table's $5C/$5D, $5E/$5F)
LOGO_TILE_BYTES = set(archipelago_logo.LOGO_SPRITE_TILES)
FLIP_BITS = 0xC0
HIDDEN_Y = 0xEF                              # an OAM record at this Y or below the screen is not drawn
SOME_HEARTS = 0x21                           # three containers, two hearts
PLAY_FRAMES = 30
RUPEE_COUNT_FRAMES = 300            # the rupee counter runs down after a purchase


@cache
def result() -> archipelago.BuildResult:
    return archipelago.build_from_strings(*FLAG_CASES[CASE], SEED, remember_repo_base_rom())


def foreign_places() -> tuple[str, str]:
    """A floor room and a shop ware, each given another player's item."""
    built = result().state
    shop_ware = next(place.name for place in built.places if place.kind is PlaceKind.SHOP_WARE)
    return floor_room(built).name, shop_ware


def assignment() -> dict[str, str | archipelago.Foreign]:
    return {**by_name(result()), **dict.fromkeys(foreign_places(), FOREIGN)}


def received() -> list[str]:
    """The items those two places held, which this player then receives from other worlds."""
    own = by_name(result())
    return [str(own[name]) for name in foreign_places()]


@cache
def rom(look: ForeignLook) -> bytes:
    return archipelago.finish(result(), assignment(), received(), player_settings={LOOK: look.value})


def shields_and_fairies(image: bytes) -> tuple[list[tuple[Destination, int]], list[int]]:
    """Every shop ware holding the magical shield, and every fairy ware's price."""
    world = parse_rom(image)
    shops = [cave for cave in world.overworld.caves if isinstance(cave, Shop)]
    shields = [(shop.destination, position) for shop in shops for position, ware in enumerate(shop.items)
               if ware.item == Item.MAGICAL_SHIELD]
    return shields, [ware.price for shop in shops for ware in shop.items if ware.item == Item.FAIRY]


def written(image: bytes) -> bool:
    return all(image[offset:offset + len(data)] == data for offset, data in archipelago_logo.logo_writes())


def test_the_rupee_look_writes_one_rupee_and_nothing_of_the_logo() -> None:
    image = rom(ForeignLook.RUPEE)
    world = parse_rom(image)
    by_place = {place.name: place for place in result().state.places}
    assert {read_item(world, by_place[name]) for name in foreign_places()} == {Item.ITEM_0x18}
    for offset, data in archipelago_logo.logo_writes():
        assert image[offset:offset + len(data)] == original_bytes(offset, len(data)), hex(offset)
    assert rom(ForeignLook.RUPEE) == archipelago.finish(result(), assignment(), received())        # the default


def test_the_logo_look_writes_the_shield_and_the_logo_and_sells_fairies() -> None:
    image = rom(ForeignLook.LOGO)
    world = parse_rom(image)
    by_place = {place.name: place for place in result().state.places}
    assert {read_item(world, by_place[name]) for name in foreign_places()} == {Item.MAGICAL_SHIELD}
    assert written(image) and not written(rom(ForeignLook.RUPEE))
    shields, _fairy_prices = shields_and_fairies(image)
    foreign_ware = by_place[foreign_places()[1]]
    assert shields == [(foreign_ware.destination, foreign_ware.position)]     # only the foreign one
    real_shields, _ = shields_and_fairies(rom(ForeignLook.RUPEE))
    assert real_shields
    low, high = LOGO_SHOP_FAIRY_PRICES
    for destination, position in real_shields:                               # each became a fairy
        shop = world.overworld.get_cave(destination, Shop)
        assert shop is not None
        ware = shop.items[position]
        assert ware.item == Item.FAIRY and low <= ware.price <= high, (destination, position)
    recipe = archipelago.recipe(result(), assignment(), received(), player_settings={LOOK: "logo"})
    assert recipe["formatVersion"] == archipelago.RECIPE_FORMAT_VERSION
    assert archipelago.rom_from_recipe(recipe, remember_repo_base_rom()) == image


# The inventory but the hearts, which fill over time
HEART_BYTES = {HEART_VALUES, HEART_VALUES + 1}


def items_held(console: Console) -> dict[int, int]:
    return {address: console.emu[address] for address in range(inventory.ITEMS, inventory.MAX_BOMBS + 1)
            if address not in HEART_BYTES}


def oam_records(console: Console) -> list[bytes]:
    sprites = console.emu.sprites()
    return [sprites[i:i + OAM_ENTRY] for i in range(0, len(sprites), OAM_ENTRY)]


def test_a_logo_pickup_draws_the_logo_gives_nothing_and_is_checked() -> None:
    room_place = next(place for place in result().state.places if place.name == foreign_places()[0])
    assert room_place.level is not None and room_place.room_num is not None
    console = Console(rom(ForeignLook.LOGO))
    console.enter_room(room_place.level, room_place.room_num)
    console.emu.run(PLAY_FRAMES)
    logo = sorted((record for record in oam_records(console) if record[1] in LOGO_TILE_BYTES and record[0] < HIDDEN_Y),
                  key=lambda record: record[3])
    assert [record[1] for record in logo] == list(archipelago_logo.LOGO_SPRITE_TILES)   # left, then right
    assert logo[1][3] - logo[0][3] == 8                                                 # side by side
    assert all(record[2] & SPRITE_PALETTE_BITS == archipelago_logo.LOGO_PALETTE for record in logo)
    assert not any(record[2] & FLIP_BITS for record in logo)                            # not mirrored
    held = items_held(console)
    console.take_room_item()
    assert items_held(console) == held
    check = archipelago.pickup_checks(result())[room_place.name]
    assert check.is_set({check.address: console.emu[check.address]})


def test_a_fairy_ware_sells_and_fills_the_hearts() -> None:
    image = rom(ForeignLook.LOGO)
    world = parse_rom(image)
    shop, position = next((cave, index) for cave in world.overworld.caves if isinstance(cave, Shop)
                          for index, ware in enumerate(cave.items) if ware.item == Item.FAIRY
                          and cave.destination in {destination for destination, _ in
                                                   shields_and_fairies(rom(ForeignLook.RUPEE))[0]})
    price = shop.items[position].price
    console = Console(image)
    console.enter_cave(_screens(world, shop.destination)[0])
    assert console.emu[CAVE_ITEM_IDS + position] & NO_ITEM == FAIRY
    console.emu[HEART_VALUES] = SOME_HEARTS
    rupees = console.emu[INV_RUPEES]
    console.take_ware(position)
    console.emu.run_until(lambda: console.emu[INV_RUPEES] == rupees - price, limit=RUPEE_COUNT_FRAMES)
    assert console.emu[HEART_VALUES] & 0x0F == SOME_HEARTS >> 4


# With Progressive Items on (this case's), fp-prog-01's ResolveProgressive hides a cave or shop ware
# whose upgrade line is at its top level. Up to 2.0.1 the logo's descriptor was $20 (graded, value 0),
# which it read as such a line, so another player's item showed as no item ($3F) in every cave and
# shop and could not be taken. A class 1 descriptor is no upgrade, so the ware shows and sells.
DESCRIPTOR_CLASS_BITS = 0xF0
GRADED_CLASS = 0x20
WHITE_SWORD_CAVE = "White Sword Cave"
WHITE_SWORD_WARE = 1                         # the cave's middle ware
TAKE_CHANGES = {INV_RUPEES, *range(inventory.SHOP_BOUGHT_FLAGS, inventory.SHOP_BOUGHT_FLAGS + 3)}


def test_the_logo_is_no_upgrade_line() -> None:
    assert result().state.plan.config.progressive_items                     # the case these tests need
    descriptor = rom(ForeignLook.LOGO)[inventory.ITEM_ID_TO_DESCRIPTOR + archipelago_logo.MAGICAL_SHIELD]
    assert descriptor == archipelago_logo.DO_NOTHING_DESCRIPTOR
    assert descriptor & DESCRIPTOR_CLASS_BITS != GRADED_CLASS
    assert descriptor & ~DESCRIPTOR_CLASS_BITS == 0                         # adds 0


@cache
def white_sword_cave_rom() -> bytes:
    own = by_name(result())
    return archipelago.finish(result(), {**own, WHITE_SWORD_CAVE: FOREIGN}, [str(own[WHITE_SWORD_CAVE])],
                              player_settings={LOOK: ForeignLook.LOGO.value})


def take_and_check(console: Console, name: str, position: int) -> None:
    """Take ware `position`: nothing in the inventory changes but the rupees and a shop's bought
    flags (fp-prog-01 marks a ware place sold once), and the place's check is set."""
    def kept() -> dict[int, int]:
        return {address: value for address, value in items_held(console).items() if address not in TAKE_CHANGES}
    held = kept()
    console.take_ware(position)
    assert kept() == held
    check = archipelago.pickup_checks(result())[name]
    assert check.is_set({check.address: console.emu[check.address]})


def test_with_progressive_items_the_white_sword_cave_shows_and_gives_the_logo() -> None:
    cave = next(place for place in result().state.places if place.name == WHITE_SWORD_CAVE)
    console = Console(white_sword_cave_rom())
    console.enter_cave(cave.screens[0])
    assert console.emu[CAVE_ITEM_IDS + WHITE_SWORD_WARE] & NO_ITEM == archipelago_logo.MAGICAL_SHIELD
    console.emu.run(PLAY_FRAMES)
    assert any(record[1] in LOGO_TILE_BYTES and record[0] < HIDDEN_Y for record in oam_records(console))
    take_and_check(console, WHITE_SWORD_CAVE, WHITE_SWORD_WARE)


def test_with_progressive_items_a_shop_sells_the_logo() -> None:
    image = rom(ForeignLook.LOGO)
    ware = next(place for place in result().state.places if place.name == foreign_places()[1])
    assert ware.destination is not None and ware.position is not None
    world = parse_rom(image)
    shop = world.overworld.get_cave(ware.destination, Shop)
    assert shop is not None
    price = shop.items[ware.position].price
    console = Console(image)
    console.enter_cave(_screens(world, ware.destination)[0])
    assert console.emu[CAVE_ITEM_IDS + ware.position] & NO_ITEM == archipelago_logo.MAGICAL_SHIELD
    rupees = console.emu[INV_RUPEES]
    take_and_check(console, ware.name, ware.position)
    console.emu.run_until(lambda: console.emu[INV_RUPEES] == rupees - price, limit=RUPEE_COUNT_FRAMES)


# The logo's background tiles ($5C-$5F) and Randomize Boss Groups (B40): the bosses' common block is $30-$4F
# in every game (owner decision 2026-11-14; from 2026-11-13 an Archipelago game's stopped at $4B for the
# logo, then at $4C-$4F), so the logo is drawn whole whatever the deal.
def boss_tiles(built: pipeline.Built) -> set[int]:
    groups = built.result.groups
    assert groups is not None and groups.boss_deal is not None
    return {tile for block, _boss, _sprite, slots in packed_slots(groups.boss_deal) if block == OVERWORLD
            for tile in slots}


def test_the_bosses_never_take_the_logo_tiles_and_it_is_drawn_whole() -> None:
    built = result().state
    assert built.plan.steps.randomize_boss_groups
    assert boss_tiles(built) <= set(range(0x30, 0x50))
    assert not boss_tiles(built) & set(archipelago_logo.LOGO_BACKGROUND_TILES)
    assert written(rom(ForeignLook.LOGO))                                    # the whole logo's writes
