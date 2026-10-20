"""The ring check of Archipelago games' ROMs (asm/flags2/ring-color; the spec "ZORA Archipelago
beta 5 fixes", item 1; owner decision 2026-10-18). The client gives a ring by writing InvRing alone
(archipelago.receive), and the game's own pickup is what repaints Link, so a received ring left his
tunic the old color. Each frame of play the check repaints him from the game's own color table when
his ring and his tunic disagree.

In the emulator, on PRG0 and PRG1, with the default tunic colors and custom ones: after a ring given
through receive() alone, the whole frame equals that of a control ROM whose green tunic is already
the ring's color, run with the same inputs: 30 frames after the ring, after a scroll to the next
screen, in level 1's start room (loaded by the level-load mode), and after the continue screen (reached by Up+A, the screen a death
leads to) and Continue. Before the ring the two frames differ, so the comparison sees the tunic.
Without a ring change the check never writes the palette. ZORA's own seeds don't get the check."""
from functools import cache

import numpy as np
import pytest

from tests.emulator import ROOM_ID, Button, Emulator, Mode
from tests.test_archipelago_interface import by_name
from tests.test_progressive_emulator import CONTINUE_CHOICE
from tests.test_progressive_emulator import Game as HandPlaced
from zora import archipelago
from zora.generate.pipeline import generate_rom
from zora.rom import inventory
from zora.rom.base_rom import BASE_ROM_PATH, PRG1_ROM_PATH, original_bytes, remember_repo_base_rom
from zora.rom.owner_patches import archipelago_patch_writes
from zora.rom.revision import Revision

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

SEED = 1
DEFAULT_COLORS = (0x29, 0x32, 0x16)              # green tunic, blue ring, red ring (PRG0's)
CUSTOM_COLORS = (0x2A, 0x11, 0x05)
TUNIC_KEYS = ("greenTunic", "blueRingTunic", "redRingTunic")
RINGS = {"Blue Ring": 1, "Red Ring": 2}          # the ring's InvRing value: its color's index
INVENTORY = range(inventory.ITEMS, inventory.MAX_BOMBS + 1)
INV_RING = 0x0662
# Link's color in the save slot's menu palette row (MenuPalettesTransferBuf+20, slot 0) and in the
# loaded level palette (LevelInfo_PalettesTransferBuf+20).
MENU_TUNIC, LEVEL_TUNIC = 0x67F0 + 20, 0x6B7E + 20
SETTLE_FRAMES = 30
QUIET_FRAMES = 120
SCROLL_LIMIT = 400


def base_rom(revision: Revision) -> bytes:
    if revision is Revision.PRG0:
        return remember_repo_base_rom()
    if not PRG1_ROM_PATH.exists():
        pytest.skip(f"{PRG1_ROM_PATH.name} is not beside the PRG0 base")
    remember_repo_base_rom()
    return PRG1_ROM_PATH.read_bytes()


@cache
def archipelago_rom(revision: Revision, colors: tuple[int, int, int]) -> bytes:
    """Seed 1 with Archipelago's default flags and its own items, finished as an Archipelago game."""
    result = archipelago.build_from_strings(archipelago.DEFAULT_FLAGS, archipelago.DEFAULT_ZORA_FLAGS, SEED,
                                            base_rom(revision))
    return archipelago.finish(result, by_name(result), player_settings=dict(zip(TUNIC_KEYS, colors, strict=True)))


def give(emu: Emulator, item: str) -> None:
    """As the client gives a received item: receive()'s writes, the inventory only."""
    for address, value in archipelago.receive(item, {address: emu[address] for address in INVENTORY}).items():
        emu[address] = value


def leaves_the_screen(emu: Emulator, direction: Button) -> bool:
    screen = emu[ROOM_ID]
    emu.run(SCROLL_LIMIT, direction)
    return emu[ROOM_ID] != screen


def scroll(emu: Emulator, control: Emulator) -> None:
    """Both consoles walk off the screen the same way, the first way open, and settle on the next."""
    here = emu.save()
    for direction in (Button.LEFT, Button.RIGHT, Button.DOWN, Button.UP):
        leaves = leaves_the_screen(emu, direction)
        emu.load(here)
        if leaves:
            break
    else:
        raise AssertionError("no way off the screen")
    for console in (emu, control):
        walk_to_the_next_screen(console, direction)


def walk_to_the_next_screen(emu: Emulator, direction: Button) -> None:
    emu.run_until(lambda: emu.mode != Mode.PLAY, buttons=direction, limit=SCROLL_LIMIT)
    emu.run_until(lambda: emu.mode == Mode.PLAY, limit=SCROLL_LIMIT)
    emu.run(SETTLE_FRAMES)


def as_game(emu: Emulator) -> HandPlaced:
    """The console under tests/test_progressive_emulator.py's play helpers."""
    game = HandPlaced.__new__(HandPlaced)
    game.emu = emu
    game.zora_flags = ""
    return game


def enter_level_1(emu: Emulator) -> None:
    """Level 1's start room, by the level-load mode (wherever this seed put its entrance)."""
    as_game(emu).enter_level(1)
    emu.run(SETTLE_FRAMES)


def continue_after_the_continue_screen(emu: Emulator) -> None:
    game = as_game(emu)
    game.continue_screen(CONTINUE_CHOICE)
    game.wait_for_play()
    emu.run(SETTLE_FRAMES)


def same_frames(emu: Emulator, control: Emulator) -> bool:
    return bool(np.array_equal(emu.last_frame, control.last_frame))


@pytest.mark.parametrize("ring", RINGS)
@pytest.mark.parametrize("colors", [DEFAULT_COLORS, CUSTOM_COLORS], ids=["default colors", "custom colors"])
@pytest.mark.parametrize("revision", [Revision.PRG0, Revision.PRG1], ids=["prg0", "prg1"])
def test_a_received_ring_repaints_link(revision: Revision, colors: tuple[int, int, int], ring: str) -> None:
    ring_color = colors[RINGS[ring]]
    emu = Emulator(archipelago_rom(revision, colors))
    control = Emulator(archipelago_rom(revision, (ring_color, *colors[1:])))
    for console in (emu, control):
        console.new_game()
        console.run(SETTLE_FRAMES)
    assert not same_frames(emu, control)                       # green, and the ring's color
    give(emu, ring)
    assert emu[INV_RING] == RINGS[ring]
    for console in (emu, control):
        console.run(SETTLE_FRAMES)
    assert (emu[MENU_TUNIC], emu[LEVEL_TUNIC]) == (ring_color, ring_color)
    assert same_frames(emu, control)
    # each stage from the moment above, on both consoles
    given = (emu.save(), control.save())
    scroll(emu, control)
    assert same_frames(emu, control), "after a scroll"
    for step in (enter_level_1, continue_after_the_continue_screen):
        emu.load(given[0])
        control.load(given[1])
        step(emu)
        step(control)
        assert same_frames(emu, control), step.__name__


@pytest.mark.parametrize("revision", [Revision.PRG0, Revision.PRG1], ids=["prg0", "prg1"])
def test_without_a_ring_change_the_palette_is_left_alone(revision: Revision) -> None:
    emu = Emulator(archipelago_rom(revision, CUSTOM_COLORS))
    emu.new_game()
    seen = set()
    for _ in range(QUIET_FRAMES):
        emu.run(1, Button.UP)
        seen.add((emu[MENU_TUNIC], emu[LEVEL_TUNIC]))
    assert seen == {(CUSTOM_COLORS[0], CUSTOM_COLORS[0])}


def test_zora_seeds_do_not_get_the_check() -> None:
    """ZORA mode's ROM holds PRG0's bytes wherever the check writes."""
    rom = generate_rom(archipelago.DEFAULT_FLAGS, SEED, remember_repo_base_rom()).rom
    for offset, data in archipelago_patch_writes():
        assert rom[offset:offset + len(data)] == original_bytes(offset, len(data)), hex(offset)
