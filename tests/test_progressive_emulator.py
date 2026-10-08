"""The progressive-items patches of asm/progressive/ (docs/progressive-patches.md)
in the emulator, through the plan's checklist: caves and shops at each level
of each line, the bought bits after leaving and returning, re-buyable
consumables, a heart container sold once, room items under both "no item"
codes, the coast and Armos items, the potion shop's red potion, the off
byte, and the three RAM cases of PI-CODE-07 (new file, Continue,
save-reset-reload).

The patches are not wired into the serializer yet. Each ROM is ZORA's output
for the MVP baseline (generate_rom, the public API; level encoding off so the
world can be parsed for its screens) with the patches and their per-seed
bytes written over it by asm/progressive/build.py, and test items placed in
caves with its helpers. Link is moved to a screen by the game's own
leave-cave mode and into a cave by its enter-cave mode (enter_cave below);
dungeon rooms are reloaded after their item is set in the level block in
work RAM."""
import importlib.util
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import ModuleType

import pytest

from tests.emulator import (
    CONTINUE_MODE,
    CUR_LEVEL,
    GAME_MODE,
    GAME_SUBMODE,
    ITEMS,
    OBJ_STATE,
    OBJ_X,
    OBJ_Y,
    ROOM_ID,
    ROOM_ITEM_SLOT,
    Button,
    Emulator,
    Mode,
)
from tests.test_feature_patches import vanilla
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.model.enums import Destination
from zora.rom.parse.rom_file import parse_rom

REPO = Path(__file__).resolve().parent.parent


def _module(name: str, path: Path) -> ModuleType:
    if not path.exists():
        # asm/ is left out of releases (release/allowlist.txt): what needs it skips there.
        pytest.skip(f"{path.relative_to(REPO)} is not in this tree", allow_module_level=True)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = _module("progressive_build", REPO / "asm" / "progressive" / "build.py")

SEED = 1
RANDOMIZE_MAGICAL_SWORD = "1.D"      # a ZORA flag string whose ROMs use the $0E "no item" code

# CPU RAM and work RAM (the pinned disassembly's src/Variables.inc, CaveVars.inc)
IS_UPDATING_MODE = 0x11
UNDERGROUND_EXIT_TYPE = 0x5A
ROOM_ITEM_ID = 0xAB
CAVE_ITEM_IDS = 0x422
CAVE_PRICES = 0x430
INV_BOMBS = ITEMS + 1
POTION = ITEMS + 7                   # 1: blue, 2: red
INV_LETTER = 0x666                   # 2: the letter shown to the potion shop
INV_RUPEES = 0x66D
HEART_VALUES = 0x66F                 # high nibble: heart containers - 1
INV_BOOMERANG, INV_MAGIC_BOOMERANG = 0x674, 0x675
SHOP_BOUGHT_FLAGS = ITEMS + 0x20     # fp-prog-01's saved RAM, Items+$20..$22
LEVEL_BLOCK_ATTRS_E = 0x6A7E         # low 5 bits: the room item
LEVEL_BLOCK_ATTRS_F = 0x6AFE         # low 3 bits: the secret trigger
ROOM_ITEM_MASK = 0x1F
SECRET_TRIGGER_MASK = 0x07

CAVE_MODE = 0x0B
LEAVE_CAVE_MODE = 0x0A
ENTER_ROOM_MODE = 0x04
CONTINUE_CHOICE = 0
CAVE_WARE_XS = (0x58, 0x78, 0x98)    # CaveWareXs
CAVE_WARE_Y = 0x98
CAVE_EXIT_X = 0x70
CAVE_INIT_FRAMES = 30
TAKE_WARE_FRAMES = 600            # a cave's longest text, then the take
ITEM_ACTIVE, ITEM_INACTIVE = 0x00, 0xFF   # ObjState of the room item's slot
FULL_RUPEES = 0xFF
LETTER_DELIVERED = 2
MANY_HEARTS = 0xFF                   # 16 heart containers, all full
TEST_PRICE = 1
NO_ITEM = 0x3F
FIRST_CAVE_TYPE = 0x5A               # object type = destination + $5A ($10 -> $6A)

# Items (Item values)
WOODEN_SWORD, WHITE_SWORD, MAGICAL_SWORD = 0x01, 0x02, 0x03
BLUE_CANDLE, RED_CANDLE = 0x06, 0x07
WOODEN_ARROW, SILVER_ARROW = 0x08, 0x09
BLUE_RING, RED_RING = 0x12, 0x13
WOODEN_BOOMERANG, MAGICAL_BOOMERANG = 0x1D, 0x1E
BOMBS, HEART_CONTAINER, BLUE_POTION, RED_POTION = 0x00, 0x1A, 0x1F, 0x20


@dataclass(frozen=True)
class Line:
    """An upgrade line: its item IDs by level and its Items slot (None for
    the boomerangs, which have one slot each)."""
    name: str
    items: tuple[int, ...]
    slot: int | None

    def set_level(self, emu: Emulator, level: int) -> None:
        if self.slot is None:
            emu[INV_BOOMERANG] = int(level >= 1)
            emu[INV_MAGIC_BOOMERANG] = int(level >= 2)
        else:
            emu[ITEMS + self.slot] = level

    def level(self, emu: Emulator) -> int:
        if self.slot is None:
            return emu[INV_BOOMERANG] + emu[INV_MAGIC_BOOMERANG]
        return emu[ITEMS + self.slot]


SWORD = Line("sword", (WOODEN_SWORD, WHITE_SWORD, MAGICAL_SWORD), 0x00)
CANDLE = Line("candle", (BLUE_CANDLE, RED_CANDLE), 0x04)
ARROW = Line("arrow", (WOODEN_ARROW, SILVER_ARROW), 0x02)
RING = Line("ring", (BLUE_RING, RED_RING), 0x0B)
BOOMERANG = Line("boomerang", (WOODEN_BOOMERANG, MAGICAL_BOOMERANG), None)
LINES = (SWORD, CANDLE, ARROW, RING, BOOMERANG)


def cave_type(destination: Destination) -> int:
    return destination + FIRST_CAVE_TYPE


# Where each line's first item is placed: a shop ware (sold) and a cave
# that gives it away (the item at ware position 1, where those caves show it).
SHOP_WARE = {SWORD: (Destination.SHOP_1, 0), CANDLE: (Destination.SHOP_2, 0), ARROW: (Destination.SHOP_3, 0),
             RING: (Destination.SHOP_4, 0), BOOMERANG: (Destination.SHOP_1, 2)}
GIVEN_WARE = {SWORD: Destination.WOOD_SWORD_CAVE, CANDLE: Destination.WHITE_SWORD_CAVE,
              ARROW: Destination.MAGICAL_SWORD_CAVE, RING: Destination.LETTER_CAVE,
              BOOMERANG: Destination.TAKE_ANY}
GIVEN_POSITION = {BOOMERANG: 0}      # the take-any cave's first ware; the others at position 1
# Other test wares: re-buyable bombs, and a heart container sold once.
BOMBS_WARE = (Destination.SHOP_2, 1)
HEART_CONTAINER_WARE = (Destination.SHOP_3, 1)
POTION_SHOP_WARES = (BLUE_POTION, RED_POTION)


# --- ROMs ---------------------------------------------------------------------------

@cache
def finished(zora_flags: str = "") -> bytes:
    return generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, vanilla(), zora_flag_string=zora_flags).rom


@cache
def screens(zora_flags: str = "") -> dict[Destination, int]:
    """The overworld screen of each cave (the first, where several share one)."""
    found: dict[Destination, int] = {}
    for screen in parse_rom(finished(zora_flags)).overworld.screens:
        found.setdefault(Destination(screen.destination), screen.screen_num)
    return found


@cache
def armos(zora_flags: str = "") -> tuple[int, int]:
    """The Armos item's screen and statue X."""
    overworld = parse_rom(finished(zora_flags)).overworld
    return overworld.armos_screen_ids[0], overworld.armos_positions[0]


def with_test_wares(rom: bytes) -> bytes:
    """`rom` with each line's first item in a shop and in a cave that gives
    it away, re-buyable bombs and a heart container in shops, and the potion
    shop's potions; every shop ware placed here costs TEST_PRICE."""
    for line, (destination, position) in SHOP_WARE.items():
        rom = build.with_ware(rom, cave_type(destination), position, line.items[0], TEST_PRICE)
    for line, destination in GIVEN_WARE.items():
        rom = build.with_ware(rom, cave_type(destination), GIVEN_POSITION.get(line, 1), line.items[0])
    for item, (destination, position) in ((BOMBS, BOMBS_WARE), (HEART_CONTAINER, HEART_CONTAINER_WARE)):
        rom = build.with_ware(rom, cave_type(destination), position, item, TEST_PRICE)
    for position, item in enumerate(POTION_SHOP_WARES):
        rom = build.with_ware(rom, cave_type(Destination.POTION_SHOP), position, item, TEST_PRICE)
    return bytes(rom)


@cache
def rom_with_test_wares(progressive_items: bool = True, zora_flags: str = "", armos_item: int | None = None,
             coast_item: int | None = None) -> bytes:
    rom = with_test_wares(finished(zora_flags))
    if armos_item is not None:
        rom = build.with_armos_item(rom, armos_item)
    if coast_item is not None:
        rom = build.with_coast_item(rom, coast_item)
    return bytes(build.progressive_rom(rom, progressive_items))


# --- playing -----------------------------------------------------------------------------

class Game:
    """One console with a test ROM, in play from a new file."""

    def __init__(self, rom: bytes, zora_flags: str = "") -> None:
        self.emu = Emulator(rom)
        self.zora_flags = zora_flags
        self.emu.new_game()
        self.emu[INV_RUPEES] = FULL_RUPEES
        self.emu[HEART_VALUES] = MANY_HEARTS          # the sword caves' heart requirements

    def wait_for_play(self, mode: int = Mode.PLAY) -> None:
        self.emu.run_until(lambda: self.emu.mode == mode and self.emu[IS_UPDATING_MODE] == 1, limit=900)

    def start_mode(self, mode: int) -> None:
        self.emu[GAME_MODE] = mode
        self.emu[GAME_SUBMODE] = 0
        self.emu[IS_UPDATING_MODE] = 0

    def go_to_screen(self, screen: int) -> None:
        """Come out on overworld `screen` as from its cave: the leave-cave
        mode draws the screen and puts Link at its cave exit."""
        self.emu[ROOM_ID] = screen
        self.emu[CUR_LEVEL] = 0
        self.emu[UNDERGROUND_EXIT_TYPE] = 1
        self.start_mode(LEAVE_CAVE_MODE)
        self.wait_for_play()
        self.emu.run(10)

    def enter_cave(self, destination: Destination) -> None:
        """Go to the cave's screen and into the cave (the enter-cave mode),
        and wait until its wares are set up."""
        self.go_to_screen(screens(self.zora_flags)[destination])
        self.start_mode(CAVE_MODE)
        self.wait_for_play(CAVE_MODE)
        self.emu.run(CAVE_INIT_FRAMES)

    def leave_cave(self) -> None:
        """Walk out of the cave, down through its exit, back to the overworld."""
        self.emu[OBJ_X] = CAVE_EXIT_X
        self.emu.run_until(lambda: self.emu.mode != CAVE_MODE, buttons=Button.DOWN, limit=900)
        self.wait_for_play()

    def wares(self) -> list[int]:
        return [self.emu[CAVE_ITEM_IDS + position] & NO_ITEM for position in range(3)]

    def price(self, position: int) -> int:
        return self.emu[CAVE_PRICES + position]

    def take_ware(self, position: int) -> None:
        """Step onto the ware (buying it in a shop) and wait until it is taken. A ware can't be
        taken while the cave's text is still being written, which takes longer for a longer
        text: the limit leaves room for the longest."""
        self.emu[OBJ_X] = CAVE_WARE_XS[position]
        self.emu[OBJ_Y] = CAVE_WARE_Y
        self.emu.run_until(lambda: self.emu[CAVE_ITEM_IDS + position] == 0xFF, limit=TAKE_WARE_FRAMES)
        self.emu.run(60)

    def bought(self) -> list[int]:
        return [self.emu[SHOP_BOUGHT_FLAGS + position] for position in range(3)]

    def take_room_item(self) -> None:
        """Step onto the room item and wait until it is taken."""
        self.emu[OBJ_X] = self.emu[OBJ_X + ROOM_ITEM_SLOT]
        self.emu[OBJ_Y] = self.emu[OBJ_Y + ROOM_ITEM_SLOT]
        self.emu.run_until(lambda: self.emu[OBJ_STATE + ROOM_ITEM_SLOT] == ITEM_INACTIVE, limit=120)
        self.emu.run(60)

    def enter_level(self, level: int) -> None:
        """Load `level` (the level-load mode) and stand in its start room."""
        self.emu[CUR_LEVEL] = level
        self.start_mode(Mode.LOAD_LEVEL)
        self.wait_for_play()

    def reload_room_with_item(self, item: int) -> None:
        """Put `item` in this room's level block in work RAM, with no secret
        trigger, and enter the room again (CreateRoomObjects runs)."""
        room = self.emu[ROOM_ID]
        self.emu[LEVEL_BLOCK_ATTRS_E + room] = self.emu[LEVEL_BLOCK_ATTRS_E + room] & ~ROOM_ITEM_MASK & 0xFF | item
        self.emu[LEVEL_BLOCK_ATTRS_F + room] &= ~SECRET_TRIGGER_MASK & 0xFF
        self.start_mode(ENTER_ROOM_MODE)
        self.wait_for_play()
        self.emu.run(5)

    def room_item(self) -> tuple[int, int]:
        """(RoomItemId, ObjState of the room item's slot)."""
        return self.emu[ROOM_ITEM_ID], self.emu[OBJ_STATE + ROOM_ITEM_SLOT]

    def continue_screen(self, choice: int) -> None:
        """Up and A held on both controllers to the continue screen, then
        pick `choice` (0: Continue, 1: Save)."""
        self.emu.open_item_screen()
        combination = Button.UP | Button.A
        self.emu.nes.controller = combination << 8 | combination
        for _ in range(3):
            self.emu.nes.step(1)
        self.emu.nes.controller = 0
        self.emu.run_until(lambda: self.emu.mode == CONTINUE_MODE)
        self.emu.run(20)
        while self.emu[GAME_SUBMODE] != choice:
            self.emu.press(Button.SELECT)
        self.emu.press(Button.START)


def fresh_game(progressive_items: bool = True, zora_flags: str = "", armos_item: int | None = None,
               coast_item: int | None = None) -> Callable[[], Game]:
    """A factory of games that all start from one saved state of a new file."""
    game = Game(rom_with_test_wares(progressive_items, zora_flags, armos_item, coast_item), zora_flags)
    state = game.emu.save()

    def new() -> Game:
        game.emu.load(state)
        return game
    return new


def shown_level(line: Line, level: int) -> int:
    return line.items[min(level, len(line.items) - 1)]


# --- caves and shops ----------------------------------------------------------------------------

def test_caves_and_shops_show_and_give_each_level_of_each_line() -> None:
    """For each line and each level the player may hold: a shop shows the
    line's next level and sells it (the inventory goes up one level), and
    hides the ware at the top level; a cave that gives the item away shows
    the next level, and the top level once it is held."""
    new = fresh_game()
    for line in LINES:
        shop, position = SHOP_WARE[line]
        given = GIVEN_POSITION.get(line, 1)
        for level in range(len(line.items) + 1):
            top = level >= len(line.items)
            game = new()
            line.set_level(game.emu, level)
            game.enter_cave(shop)
            if top:
                assert game.wares()[position] == NO_ITEM and game.price(position) == 0, (line.name, level)
            else:
                assert game.wares()[position] == shown_level(line, level), (line.name, level)
                assert game.price(position) == TEST_PRICE
                game.take_ware(position)
                assert line.level(game.emu) == level + 1, (line.name, level)
            game = new()
            line.set_level(game.emu, level)
            game.enter_cave(GIVEN_WARE[line])
            assert game.wares()[given] == shown_level(line, level), (line.name, level, "given")


def test_a_bought_ware_stays_hidden_after_leaving_and_returning() -> None:
    """Buying a one-time ware sets this shop's bit in its position's bought
    byte (Items+$20 + position); after walking out and back in the ware is
    gone (no item, price 0), while the shop's other wares and the same
    position in another shop are still for sale."""
    game = fresh_game()()
    game.enter_cave(SHOP_WARE[SWORD][0])
    game.take_ware(0)
    assert SWORD.level(game.emu) == 1
    shop_a_bit = 1 << 1
    assert game.bought() == [shop_a_bit, 0, 0]
    game.leave_cave()
    game.enter_cave(SHOP_WARE[SWORD][0])
    assert game.wares()[0] == NO_ITEM and game.price(0) == 0
    assert game.wares()[2] == WOODEN_BOOMERANG and game.price(2) == TEST_PRICE
    game.leave_cave()
    game.enter_cave(SHOP_WARE[CANDLE][0])
    assert game.wares()[0] == BLUE_CANDLE and game.price(0) == TEST_PRICE
    assert game.bought() == [shop_a_bit, 0, 0]


def test_rebuyable_consumables_stay_for_sale() -> None:
    """Bombs (not in ZORA_B1_OneTimeWares) are sold again: buying them sets
    no bought bit, and they are offered at their price on the next visit."""
    game = fresh_game()()
    destination, position = BOMBS_WARE
    game.enter_cave(destination)
    assert game.wares()[position] == BOMBS
    bombs = game.emu[INV_BOMBS]
    game.take_ware(position)
    assert game.emu[INV_BOMBS] > bombs
    assert game.bought() == [0, 0, 0]
    game.leave_cave()
    game.enter_cave(destination)
    assert game.wares()[position] == BOMBS and game.price(position) == TEST_PRICE


def test_a_heart_container_is_sold_once() -> None:
    """A heart container in a shop is a one-time ware: bought once (one more
    heart container), then gone from that shop."""
    game = fresh_game()()
    destination, position = HEART_CONTAINER_WARE
    game.emu[HEART_VALUES] = 0x40
    game.enter_cave(destination)
    assert game.wares()[position] == HEART_CONTAINER
    game.take_ware(position)
    assert game.emu[HEART_VALUES] >> 4 == 0x5
    game.leave_cave()
    game.enter_cave(destination)
    assert game.wares()[position] == NO_ITEM and game.price(position) == 0


def test_the_potion_shop_keeps_its_potions() -> None:
    """The red potion ($20) is never treated as an upgrade (ITEM_ID_LIMIT
    $1F): the potion shop shows both potions as placed whatever potion is
    held, and sells the red potion again after a purchase."""
    new = fresh_game()
    for potion in range(3):
        game = new()
        game.emu[POTION] = potion
        game.enter_cave(Destination.POTION_SHOP)
        assert game.wares()[:2] == list(POTION_SHOP_WARES), potion
    game = new()
    game.emu[POTION] = 1
    game.emu[INV_LETTER] = LETTER_DELIVERED
    game.enter_cave(Destination.POTION_SHOP)
    game.take_ware(1)
    assert game.emu[POTION] == 2 and game.bought() == [0, 0, 0]
    game.leave_cave()
    game.enter_cave(Destination.POTION_SHOP)
    assert game.wares()[:2] == list(POTION_SHOP_WARES) and game.price(1) == TEST_PRICE


def test_the_off_byte_keeps_only_buy_once() -> None:
    """With ZORA_B1_ProgressiveItems = 0 (and fp-prog-02 left out) wares
    and room items show and give the item placed, while a one-time ware is
    still sold once."""
    game = fresh_game(progressive_items=False)()
    SWORD.set_level(game.emu, 1)
    game.enter_cave(SHOP_WARE[SWORD][0])
    assert game.wares()[0] == WOODEN_SWORD
    game.take_ware(0)
    assert SWORD.level(game.emu) == 1
    game.leave_cave()
    game.enter_cave(SHOP_WARE[SWORD][0])
    assert game.wares()[0] == NO_ITEM
    game.leave_cave()
    game.enter_level(1)
    game.reload_room_with_item(WOODEN_SWORD)
    assert game.room_item() == (WOODEN_SWORD, ITEM_ACTIVE)


# --- room, coast and Armos items -------------------------------------------------------------------

@pytest.mark.parametrize(("zora_flags", "nothing"), [("", 0x03), (RANDOMIZE_MAGICAL_SWORD, 0x0E)])
def test_room_items_under_both_no_item_codes(zora_flags: str, nothing: int) -> None:
    """A dungeon room's item appears at its line's next level and is given
    at that level; the ROM's "no item" code ($03, or $0E with Randomize
    Magical Sword) stays "no item" (the object stays inactive); with the
    $0E code, $03 is the magical sword and upgrades like any sword."""
    assert build.nothing_code(finished(zora_flags)) == nothing
    new = fresh_game(zora_flags=zora_flags)
    game = new()
    game.enter_level(1)
    game.reload_room_with_item(nothing)
    assert game.room_item() == (nothing, ITEM_INACTIVE)
    sword_item = MAGICAL_SWORD if nothing != MAGICAL_SWORD else WOODEN_SWORD
    for level in range(len(SWORD.items) + 1):
        game = new()
        SWORD.set_level(game.emu, level)
        game.enter_level(1)
        game.reload_room_with_item(sword_item)
        assert game.room_item() == (shown_level(SWORD, level), ITEM_ACTIVE), level
        game.take_room_item()
        assert SWORD.level(game.emu) == min(level + 1, len(SWORD.items)), level
    for line in (CANDLE, RING, BOOMERANG):
        game = new()
        line.set_level(game.emu, 1)
        game.enter_level(1)
        game.reload_room_with_item(line.items[0])
        assert game.room_item() == (shown_level(line, 1), ITEM_ACTIVE), line.name


COAST_SCREEN = 0x5F


def test_the_coast_item() -> None:
    """The coast item (room $5F) appears at its line's next level and is
    given at that level."""
    game = fresh_game(coast_item=WOODEN_SWORD)()
    SWORD.set_level(game.emu, 1)
    game.go_to_screen(COAST_SCREEN)
    assert game.room_item() == (WHITE_SWORD, ITEM_ACTIVE)
    game.take_room_item()
    assert SWORD.level(game.emu) == 2


def test_the_armos_item() -> None:
    """The Armos item appears at its line's next level when its statue is
    touched, and is given at that level."""
    game = fresh_game(armos_item=WOODEN_SWORD)()
    SWORD.set_level(game.emu, 1)
    screen, statue_x = armos()
    game.go_to_screen(screen)
    game.emu[OBJ_X] = statue_x
    revealed = lambda: game.emu[ROOM_ITEM_ID] == WHITE_SWORD and game.emu[OBJ_STATE + ROOM_ITEM_SLOT] == ITEM_ACTIVE  # noqa: E731
    try:
        game.emu.run_until(revealed, buttons=Button.DOWN, limit=150)
    except AssertionError:
        game.emu.run_until(revealed, buttons=Button.UP, limit=300)
    game.emu.run(60)
    game.take_room_item()
    assert SWORD.level(game.emu) == 2


# --- PI-CODE-07: the bought bits in saved RAM ---------------------------------------------------------

def buy_the_sword(game: Game) -> None:
    game.enter_cave(SHOP_WARE[SWORD][0])
    game.take_ware(0)
    game.leave_cave()
    assert game.bought()[0]


def test_a_new_file_starts_with_no_bought_bits() -> None:
    """PI-CODE-07, new file: Items+$20..$22 are 0 when a file starts, also a
    file registered after another file saved its bought bits."""
    game = Game(rom_with_test_wares())
    assert game.bought() == [0, 0, 0]
    buy_the_sword(game)
    game.emu.open_item_screen()
    game.emu.save_and_reload()
    assert game.bought()[0]
    game.emu.reset()
    game.emu.boot_to_file_select()
    game.emu.register_file()
    game.emu.start_game(1)
    assert game.bought() == [0, 0, 0]
    game.enter_cave(SHOP_WARE[SWORD][0])
    assert game.wares()[0] == WOODEN_SWORD


def test_continue_keeps_the_bought_bits() -> None:
    """PI-CODE-07, Continue: after the continue screen's Continue the
    bought bits are kept and the ware stays hidden."""
    game = fresh_game()()
    buy_the_sword(game)
    bought = game.bought()
    game.continue_screen(CONTINUE_CHOICE)
    game.wait_for_play()
    assert game.bought() == bought
    game.enter_cave(SHOP_WARE[SWORD][0])
    assert game.wares()[0] == NO_ITEM


def test_save_reset_and_reload_keep_the_bought_bits() -> None:
    """PI-CODE-07, save-reset-reload: the bought bits are saved with the
    file, so after Save, the console's reset and starting the file again
    the ware stays hidden."""
    game = fresh_game()()
    buy_the_sword(game)
    bought = game.bought()
    game.emu.open_item_screen()
    game.emu.save_and_reload()
    assert game.bought() == bought
    game.emu[INV_RUPEES] = FULL_RUPEES
    game.enter_cave(SHOP_WARE[SWORD][0])
    assert game.wares()[0] == NO_ITEM
