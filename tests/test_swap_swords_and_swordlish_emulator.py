"""BogieSmalls' additions in the emulator (features-behavior.md FP-SWL-01, FP-SWL-05, FP-SWAP-01,
FP-SWAP-02 and FP-SWAP-05; their Known open issues name these checks), on PRG0 and PRG1:
  - Swordlish: the wooden-sword cave refuses its sword with N - 1 pieces held and gives it with N (the pieces'
    bits set in InvTriforce, as starting pieces are), and its person shows the Swordlish text naming N; another
    cave's person, and a dungeon elder's under Book to Understand NPCs (B48, every person without the book
    showing text 0), show their own texts;
  - the swap: the shop that sells the White Sword sells it at its ware's price; the magical-sword cave offers
    the Red Ring and still asks its hearts (refused one heart container short, given at the requirement); the
    Red Ring's old dungeon room holds the Magical Sword with its dark and sound bits."""
from functools import cache

import pytest

from tests.emulator import ITEMS, OBJ_X, OBJ_Y
from tests.needs import needs_base_rom
from tests.test_assignment_emulator import Console
from tests.test_coop_reserved import z1r_with
from tests.test_mirror_overworld_emulator import RELEASES
from tests.test_progressive_emulator import (
    CAVE_INIT_FRAMES,
    CAVE_ITEM_IDS,
    CAVE_MODE,
    CAVE_WARE_XS,
    CAVE_WARE_Y,
    HEART_VALUES,
    INV_RUPEES,
    LEVEL_BLOCK_ATTRS_E,
    NO_ITEM,
    ROOM_ITEM_MASK,
    TAKE_WARE_FRAMES,
    TAKEN,
    Game,
)
from tests.test_revision import prg1
from zora.flags import zora_flags
from zora.flags.fields import ThreeState
from zora.flags.zora_flags import Swordlish, ZoraFlags
from zora.generate.pipeline import Built, build, finish, plan
from zora.model.enums import Destination, Enemy, Item
from zora.model.game_world import GameWorld
from zora.model.overworld import ItemCave, Shop
from zora.rom import swordlish
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora.rom.text_encoding import BYTE_TO_CHAR

pytestmark = [needs_base_rom, pytest.mark.slow]

PIECES = 3
SWORDLISH = zora_flags.encode(ZoraFlags(swordlish=Swordlish.ON, swordlish_lowest=PIECES, swordlish_highest=PIECES))
SWAP = zora_flags.encode(ZoraFlags(swap_swords_and_rings=ThreeState.ON))
NO_CANDLES = z1r_with(toggles={"B09": ThreeState.OFF})
WITH_BOOK_RULE = z1r_with(toggles={"B09": ThreeState.OFF, "B48": ThreeState.ON})
SEED = 1
ROOM_SEED = 2                        # a seed whose Red Ring the shuffle put in a dungeon room (level 1, $26)
SWORD_WARE = 1                       # a one-item cave's ware stands in the middle
SWORD_SLOT, RING_SLOT = 0x00, 0x0B   # Items offsets
TEXT_ROWS = (0x21A4, 0x21C4, 0x21E4)     # where the text box's three lines start
TEXT_WIDTH = 24
TEXT_FRAMES = 400                    # long enough for the longest text to finish
PIECE_BITS = 0b0000_0111             # levels 1 to 3
INV_TRIFORCE = 0x671
RUPEE_FRAMES = 600                   # the longest price, taken a rupee at a time
ELDERS = frozenset({Enemy.ELDER, Enemy.ELDER_2, Enemy.ELDER_3, Enemy.ELDER_4, Enemy.ELDER_5, Enemy.ELDER_6})


def base(on_prg1: bool) -> bytes:
    return prg1() if on_prg1 else remember_repo_base_rom()


@cache
def built(flags: str, zora: str, on_prg1: bool, seed: int = SEED) -> Built:
    return build(plan(flags, seed, zora), base(on_prg1))


@cache
def rom(flags: str, zora: str, on_prg1: bool, seed: int = SEED) -> bytes:
    return finish(built(flags, zora, on_prg1, seed), base(on_prg1))


def screen_of(data: bytes, destination: Destination) -> int:
    return next(screen.screen_num for screen in parse_rom(data).overworld.screens
                if screen.destination == destination)


def in_cave(data: bytes, destination: Destination) -> Game:
    game = Game(data)
    game.go_to_screen(screen_of(data, destination))
    game.start_mode(CAVE_MODE)
    game.wait_for_play(CAVE_MODE)
    game.emu.run(CAVE_INIT_FRAMES)
    return game


def shown_text(game: Game) -> str:
    """The text box's three lines once the text has run, as one line of words."""
    game.emu.run(TEXT_FRAMES)
    lines = ("".join(BYTE_TO_CHAR.get(tile, " ") for tile in game.emu.nametable(row, TEXT_WIDTH))
             for row in TEXT_ROWS)
    return " ".join(" ".join(lines).replace("~", " ").split())


def stands_on_ware(game: Game, position: int) -> None:
    game.emu[OBJ_X] = CAVE_WARE_XS[position]
    game.emu[OBJ_Y] = CAVE_WARE_Y
    game.emu.run(TAKE_WARE_FRAMES)


def heart_containers(containers: int) -> int:
    """HeartValues for `containers` full containers (high nibble: containers - 1)."""
    return (containers - 1) << 4 | (containers - 1)


# --- Swordlish ------------------------------------------------------------------------------------

@RELEASES
def test_the_cave_refuses_the_sword_below_n_and_gives_it_at_n(on_prg1: bool) -> None:
    data = rom(NO_CANDLES, SWORDLISH, on_prg1)
    assert parse_rom(data).swordlish_pieces == PIECES
    short = in_cave(data, Destination.WOOD_SWORD_CAVE)
    short.emu[INV_TRIFORCE] = PIECE_BITS >> 1                 # two pieces
    stands_on_ware(short, SWORD_WARE)
    assert short.emu[ITEMS + SWORD_SLOT] == 0 and short.emu[CAVE_ITEM_IDS + SWORD_WARE] != TAKEN
    short.emu[INV_TRIFORCE] = PIECE_BITS                      # three: the same visit now gives it
    short.take_ware(SWORD_WARE)
    assert short.emu[ITEMS + SWORD_SLOT] == 1


@RELEASES
def test_with_extra_candles_the_cave_shows_the_sword_and_no_candle(on_prg1: bool) -> None:
    """FP-SWL-03 on the default preset (Extra Candles on): the cave's wares are nothing, the sword, nothing."""
    game = in_cave(rom(z1r_with(), SWORDLISH, on_prg1), Destination.WOOD_SWORD_CAVE)
    assert game.wares() == [NO_ITEM, Item.WOOD_SWORD, NO_ITEM]


@RELEASES
def test_the_swordlish_text_shows_in_the_wooden_sword_cave(on_prg1: bool) -> None:
    text = shown_text(in_cave(rom(NO_CANDLES, SWORDLISH, on_prg1), Destination.WOOD_SWORD_CAVE))
    assert text == " ".join(swordlish.swordlish_text(PIECES).split())


@RELEASES
def test_no_other_person_shows_the_swordlish_text(on_prg1: bool) -> None:
    """Another overworld cave's person, and under B48 a dungeon elder (who shows text 0 without the book,
    the text the add-on overwrote), show their own texts, as the same seed without Swordlish's bytes does."""
    expected = " ".join(swordlish.swordlish_text(PIECES).split())
    data = rom(WITH_BOOK_RULE, SWORDLISH, on_prg1)
    assert shown_text(in_cave(data, Destination.WOOD_SWORD_CAVE)) == expected
    assert shown_text(in_cave(data, Destination.WHITE_SWORD_CAVE)) not in ("", expected)
    world = built(WITH_BOOK_RULE, SWORDLISH, on_prg1).world
    level, room = next((level.level_num, room.room_num) for level in world.levels for room in level.rooms
                       if room.enemy in ELDERS)
    console = Console(data)
    console.enter_room(level, room)
    elder_text = shown_text(_as_game(console))
    assert elder_text and elder_text != expected


def _as_game(console: Console) -> Game:
    game = Game.__new__(Game)
    game.emu, game.zora_flags = console.emu, ""
    return game


# --- the swap -------------------------------------------------------------------------------------

def white_sword_ware(world: GameWorld) -> tuple[Destination, int, int]:
    """(shop, position, price) of the ware that sells the White Sword."""
    return next((cave.destination, position, ware.price) for cave in world.overworld.caves if isinstance(cave, Shop)
                for position, ware in enumerate(cave.items) if ware.item == Item.WHITE_SWORD)


@RELEASES
def test_the_white_sword_is_sold_at_its_ware_s_price(on_prg1: bool) -> None:
    data, world = rom(z1r_with(), SWAP, on_prg1), built(z1r_with(), SWAP, on_prg1).world
    shop, position, price = white_sword_ware(world)
    game = in_cave(data, shop)
    assert game.wares()[position] == Item.WHITE_SWORD and game.price(position) == price
    rupees = game.emu[INV_RUPEES]
    game.take_ware(position)
    assert game.emu[ITEMS + SWORD_SLOT] == 2
    game.emu.run_until(lambda: game.emu[INV_RUPEES] == rupees - price, limit=RUPEE_FRAMES)  # paid a rupee a frame


@RELEASES
def test_the_magical_sword_cave_offers_the_red_ring_and_keeps_its_hearts(on_prg1: bool) -> None:
    """FP-SWAP-02: one heart container short of the cave's requirement the ring stays; at it, it is given."""
    data, world = rom(z1r_with(), SWAP, on_prg1), built(z1r_with(), SWAP, on_prg1).world
    cave = world.overworld.get_cave(Destination.MAGICAL_SWORD_CAVE, ItemCave)
    assert cave is not None and cave.item == Item.RED_RING and cave.heart_requirement
    short = in_cave(data, Destination.MAGICAL_SWORD_CAVE)
    assert short.wares()[SWORD_WARE] == Item.RED_RING
    short.emu[HEART_VALUES] = heart_containers(cave.heart_requirement - 1)
    stands_on_ware(short, SWORD_WARE)
    assert short.emu[ITEMS + RING_SLOT] == 0
    enough = in_cave(data, Destination.MAGICAL_SWORD_CAVE)
    enough.emu[HEART_VALUES] = heart_containers(cave.heart_requirement)
    enough.take_ware(SWORD_WARE)
    assert enough.emu[ITEMS + RING_SLOT] == 2


@RELEASES
def test_the_red_ring_s_old_room_holds_the_magical_sword(on_prg1: bool) -> None:
    """The Magical Sword lies where the shuffle put the Red Ring (a dungeon room in ROOM_SEED): the level block
    the game loads holds item $03 there, with the room's dark and sound bits as the world has them."""
    world = built(z1r_with(), SWAP, on_prg1, ROOM_SEED).world
    level, room = next((level, room) for level in world.levels for room in level.rooms
                       if room.item == Item.MAGICAL_SWORD)
    console = Console(rom(z1r_with(), SWAP, on_prg1, ROOM_SEED))
    console.enter_room(level.level_num, room.room_num)
    loaded = console.emu[LEVEL_BLOCK_ATTRS_E + room.room_num]
    assert loaded & ROOM_ITEM_MASK == Item.MAGICAL_SWORD
    assert loaded & ~ROOM_ITEM_MASK & 0xFF == room.item_byte & ~ROOM_ITEM_MASK & 0xFF
