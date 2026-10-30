"""Mirror Overworld (B06) in Archipelago, in the emulator: on a mirrored seed the client's pickup checks
(zora/archipelago.py pickup_checks) name the flags the game sets when an overworld place's item is taken.
The places are read from the built world, before the flip (pipeline.written_world), so a cave, the Armos
item and the coast item name screen s; the game, played on the flipped overworld, marks the item taken in
the flags of screen s XOR $0F (the coast's at $50), which is where each check must look.

The seed (Randomize Magical Sword and Randomize Letter on, so three caves are places) is finished with its own items (the identity assignment), made from PRG0 and from PRG1. Link is
put on the place's screen as written by the leave-cave mode (tests/test_progressive_emulator.py Game):
a cave is then entered and its item taken; the Armos item is revealed by walking onto its statue; the
coast item stands on its screen. Each check is set after the take and was clear before it, and the screen
the place names before the flip has no taken item."""
from collections.abc import Callable
from functools import cache

import pytest

from tests.emulator import OBJ_STATE, OBJ_X, ROOM_ITEM_SLOT, Button, Emulator
from tests.needs import needs_base_rom
from tests.test_assignment import identity
from tests.test_coop_reserved import z1r_with
from tests.test_mirror_overworld_emulator import RELEASES
from tests.test_progressive_emulator import CAVE_INIT_FRAMES, CAVE_MODE, ITEM_ACTIVE, Game
from tests.test_progressive_l4_emulator import ARMOS_REVEAL_FRAMES, STEP_BACK_FRAMES
from tests.test_revision import prg1
from zora import archipelago
from zora.flags.fields import ThreeState
from zora.generate.pipeline import finish
from zora.generate.places import Place
from zora.model.enums import Destination
from zora.rom import inventory
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.mirror_overworld import mirror_screen
from zora.rom.parse.rom_file import parse_rom

pytestmark = [needs_base_rom, pytest.mark.slow]

MIRRORED = z1r_with(toggles={"B06": ThreeState.ON})
SWORD_AND_LETTER = "1.F"                 # Randomize Magical Sword and Randomize Letter: three cave places
SEED = 1
CAVE_ITEM_POSITION = 1                   # a one-item cave's ware stands in the middle
CAVES = (Destination.WHITE_SWORD_CAVE, Destination.MAGICAL_SWORD_CAVE, Destination.LETTER_CAVE)


@cache
def base(on_prg1: bool) -> bytes:
    return prg1() if on_prg1 else remember_repo_base_rom()


@cache
def built(on_prg1: bool) -> archipelago.BuildResult:
    return archipelago.build_from_strings(MIRRORED, SWORD_AND_LETTER, SEED, base(on_prg1))


@cache
def finished(on_prg1: bool) -> bytes:
    state = built(on_prg1).state
    return finish(state, base(on_prg1), identity(state), check=False)


def place_named(on_prg1: bool, name: str) -> Place:
    return next(place for place in built(on_prg1).state.places if place.name == name)


def screen_before_flip(place: Place) -> int:
    return place.screens[0] if place.screens else inventory.COAST_SCREEN


def is_set(check: archipelago.RamCheck, emu: Emulator) -> bool:
    return bool(emu[check.address] & check.mask)


def take_and_check(on_prg1: bool, place: Place, take: Callable[[Game, int], None]) -> None:
    """Take the place's item with `take(game, screen)` on its screen as played and judge its check."""
    check = archipelago.pickup_checks(built(on_prg1))[place.name]
    before_flip = archipelago.pickup_check(place)
    played_screen = mirror_screen(screen_before_flip(place))
    assert check == archipelago.pickup_check(place, mirrored=True) != before_flip
    game = Game(finished(on_prg1))
    assert not is_set(check, game.emu), place.name
    take(game, played_screen)
    assert is_set(check, game.emu), place.name
    assert not is_set(before_flip, game.emu), place.name


@RELEASES
def test_the_seed_is_mirrored(on_prg1: bool) -> None:
    assert built(on_prg1).state.plan.config.mirror_overworld
    assert parse_rom(finished(on_prg1)).overworld_mirrored


@RELEASES
@pytest.mark.parametrize("destination", CAVES, ids=lambda d: d.name.lower())
def test_a_cave_s_check_is_its_mirrored_screen_s(destination: Destination, on_prg1: bool) -> None:
    place = next(place for place in built(on_prg1).state.places if place.destination == destination)

    def take(game: Game, screen: int) -> None:
        game.go_to_screen(screen)
        game.start_mode(CAVE_MODE)
        game.wait_for_play(CAVE_MODE)
        game.emu.run(CAVE_INIT_FRAMES)
        game.take_ware(CAVE_ITEM_POSITION)
    take_and_check(on_prg1, place, take)


@RELEASES
def test_the_armos_item_s_check_is_its_mirrored_screen_s(on_prg1: bool) -> None:
    overworld = parse_rom(finished(on_prg1)).overworld
    statue_x = overworld.armos_positions[0]

    def take(game: Game, screen: int) -> None:
        assert screen == overworld.armos_screen_ids[0]      # the written world's Armos screen
        game.go_to_screen(screen)
        game.emu[OBJ_X] = statue_x

        def revealed() -> bool:
            return game.emu[OBJ_STATE + ROOM_ITEM_SLOT] == ITEM_ACTIVE
        try:
            game.emu.run_until(revealed, buttons=Button.DOWN, limit=ARMOS_REVEAL_FRAMES[0])
            back = Button.UP
        except AssertionError:
            game.emu.run_until(revealed, buttons=Button.UP, limit=ARMOS_REVEAL_FRAMES[1])
            back = Button.DOWN
        game.emu.run(STEP_BACK_FRAMES, back)
        game.emu.run(60 - STEP_BACK_FRAMES)
        game.take_room_item()
    take_and_check(on_prg1, place_named(on_prg1, "Armos"), take)


@RELEASES
def test_the_coast_item_s_check_is_its_mirrored_screen_s(on_prg1: bool) -> None:
    def take(game: Game, screen: int) -> None:
        game.go_to_screen(screen)
        assert game.emu[OBJ_STATE + ROOM_ITEM_SLOT] == ITEM_ACTIVE
        game.take_room_item()
    take_and_check(on_prg1, place_named(on_prg1, "Coast"), take)
