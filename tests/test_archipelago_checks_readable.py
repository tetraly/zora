"""checks_readable (zora/rom/inventory.py, docs/archipelago.md "Interface") and the client's other
predicates in the emulator, never from zeroed RAM alone: a playtest's client read the pickup flags
($067F) in the first frames after power-on, while RAM still held garbage, reported false checks
and then withheld received items as already held.

Every frame of each run is recorded (Watched): the mode, checks_readable, may_receive,
goal_reached, the pickup flags and the received count. Two save files are prepared once, each with
its own pickup checks set and its own received count (the battery, the save RAM at $6000-$7FFF),
and the console is then powered on with that battery and RAM filled with $FF, $00, $10 or a
seeded random pattern; reset mid-game; power-cycled (RAM kept, or $FF); and switched from one file
to the other through the file-select screen. In every run:
  - checks_readable is false until a file is loaded, and whenever it is true the pickup flags and
    the received count are the loaded file's;
  - may_receive implies checks_readable and play, so the received count is never acted on outside
    play (nor read from another file); goal_reached is never true."""
import random
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache

import pytest

from tests.archipelago_cases import FLAG_CASES
from tests.emulator import CONTINUE_MODE, CONTROLLER_2_SHIFT, GAME_SUBMODE, SAVE_CHOICE, Button, Emulator, Mode
from tests.test_archipelago_client_ram import CASE, SEED, zora_rom
from zora import archipelago
from zora.rom import inventory
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")

RAM_SIZE = 0x800
SAVE_RAM = range(0x6000, 0x8000)
PICKUP_FLAGS = range(inventory.WORLD_FLAGS, inventory.WORLD_FLAGS + 3 * inventory.WORLD_FLAGS_SIZE)
COUNT = archipelago.RECEIVED_COUNT
WATCHED = sorted({*archipelago.CHECKS_STATE, *archipelago.RECEIVE_STATE, *archipelago.GOAL_STATE})
FIRST_FRAMES = 20                    # stepped one by one from power-on or reset
PLAY_FRAMES = 60
# Each file's received count and which of the seed's places it has taken (every third place from
# its own start), so the two files' pickup flags differ.
FILE_COUNTS = (3, 5)
FILE_STRIDE = 3
RANDOM_SEEDS = (1, 2, 3)
NO_BUTTONS = Button(0)


def random_fill(seed: int) -> Callable[[int], int]:
    """A seeded random byte for each RAM address."""
    return random.Random(seed).randbytes(RAM_SIZE).__getitem__


FILLS: dict[str, Callable[[int], int]] = {
    "$FF": lambda _address: 0xFF,
    "$00": lambda _address: 0x00,
    "$10": lambda _address: 0x10,
    **{f"random {seed}": random_fill(seed) for seed in RANDOM_SEEDS},
}
UP_A = Button.UP | Button.A
CONTINUE_SCREEN_FRAMES = 20
SETTLE_FRAMES = 30
SAVE_FRAMES = 900


@dataclass(frozen=True)
class Seen:
    """One frame of a run, after it was stepped."""
    mode: int
    readable: bool
    may_receive: bool
    goal: bool
    flags: bytes
    count: int


class Watched(Emulator):
    """An emulator that records every frame it steps (Emulator.run is the only stepper the menu
    scripts use)."""

    def __init__(self, rom: bytes) -> None:
        super().__init__(rom)
        self.seen: list[Seen] = []

    def look(self) -> Seen:
        ram = {address: self[address] for address in WATCHED}
        return Seen(self.mode, archipelago.checks_readable(ram), archipelago.may_receive(ram),
                    archipelago.goal_reached(ram), bytes(self[address] for address in PICKUP_FLAGS), self[COUNT])

    def run(self, frames: int, buttons: Button = NO_BUTTONS) -> None:
        for _ in range(frames):
            super().run(1, buttons)
            self.seen.append(self.look())

    def run_both_controllers(self, frames: int, buttons: Button) -> None:
        """Hold `buttons` on both controllers (PRG0 reads controller 2 for Up+A)."""
        for _ in range(frames):
            self.nes.controller = int(buttons) << CONTROLLER_2_SHIFT | int(buttons)
            self.last_frame = self.nes.step(1)
            self.frames += 1
            self.seen.append(self.look())
        self.nes.controller = 0

    def save_to_menu(self) -> None:
        """From play: the continue screen by the item screen and Up+A, SAVE, and on to the
        file-select screen the save ends on."""
        self.run(SETTLE_FRAMES)                      # the item screen opens only after these
        self.open_item_screen()
        self.run_both_controllers(3, UP_A)
        self.run_until(lambda: self.mode == CONTINUE_MODE)
        self.run(CONTINUE_SCREEN_FRAMES)
        while self[GAME_SUBMODE] != SAVE_CHOICE:
            self.press(Button.SELECT)
        self.press(Button.START)
        self.run_until(lambda: self.mode == Mode.FILE_SELECT, limit=SAVE_FRAMES)


@cache
def checks() -> dict[str, archipelago.RamCheck]:
    return archipelago.pickup_checks(archipelago.build_from_strings(*FLAG_CASES[CASE], SEED, remember_repo_base_rom()))


@dataclass(frozen=True)
class Battery:
    """Two saved files: the save RAM, and each file's pickup flags and received count as saved."""
    save_ram: bytes
    flags: tuple[bytes, bytes]


@cache
def battery() -> Battery:
    """Two registered files, each played, given its own taken places and count, and saved."""
    emu = Watched(zora_rom())
    emu.boot_to_file_select()
    emu.register_file()
    emu.register_file()
    flags = []
    places = list(checks().values())
    for slot, count in enumerate(FILE_COUNTS):
        emu.start_game(slot)
        for check in places[slot::FILE_STRIDE]:
            emu[check.address] |= check.mask
        emu[COUNT] = count
        emu.save_to_menu()
        flags.append(bytes(emu[address] for address in PICKUP_FLAGS))
    assert flags[0] != flags[1]
    return Battery(bytes(emu[address] for address in SAVE_RAM), (flags[0], flags[1]))


def power_on(save_ram: bytes, fill: Callable[[int], int]) -> Watched:
    """A console switched on with this battery and RAM holding `fill`'s pattern."""
    emu = Watched(zora_rom())
    for address, value in zip(SAVE_RAM, save_ram, strict=True):
        emu[address] = value
    for address in range(RAM_SIZE):
        emu[address] = fill(address)
    emu.seen.append(emu.look())                      # before the first frame
    return emu


def boot_and_start(emu: Watched, slot: int) -> None:
    """The first frames one by one, then the title, the file-select screen and `slot`'s game."""
    emu.run(FIRST_FRAMES)
    emu.boot_to_file_select()
    emu.start_game(slot)
    emu.run(PLAY_FRAMES)


def assert_safe(seen: list[Seen], slot: int) -> None:
    """Whenever checks are readable, the flags and count are `slot`'s file's; may_receive only
    then and in play; never the goal."""
    for index, frame in enumerate(seen):
        if frame.readable:
            assert (frame.flags, frame.count) == (battery().flags[slot], FILE_COUNTS[slot]), index
        if frame.may_receive:
            assert frame.readable and frame.mode == Mode.PLAY, index
        assert not frame.goal, index


def first_readable(seen: list[Seen]) -> int:
    return next(index for index, frame in enumerate(seen) if frame.readable)


def test_the_predicate_alone() -> None:
    """checks_readable on hand-made RAM: the markers, the loaded-file modes, the updating flag and
    the save slot each matter."""
    loaded = {inventory.GAME_MODE: Mode.PLAY, inventory.IS_UPDATING_MODE: 1, inventory.CUR_SAVE_SLOT: 2,
              inventory.TRANSFERRED_COMMON_PATTERNS: inventory.SET_UP, inventory.SKIPPED_DEMO: inventory.SET_UP}
    assert archipelago.checks_readable(loaded)
    for mode in range(0x100):
        expected = 0x02 <= mode <= 0x0C or 0x10 <= mode <= 0x13
        assert archipelago.checks_readable({**loaded, inventory.GAME_MODE: mode}) == expected, mode
    for address, wrong in ((inventory.IS_UPDATING_MODE, 2), (inventory.CUR_SAVE_SLOT, 3),
                           (inventory.TRANSFERRED_COMMON_PATTERNS, 0), (inventory.SKIPPED_DEMO, 0)):
        assert not archipelago.checks_readable({**loaded, address: wrong}), address
    for fill in FILLS.values():
        assert not archipelago.checks_readable({address: fill(address) for address in archipelago.CHECKS_STATE})


@pytest.mark.parametrize("fill", list(FILLS))
def test_power_on_with_garbage_ram(fill: str) -> None:
    """Power-on RAM holding `fill`: nothing readable, receivable or won through the first frames,
    the title and the file-select screen; then the second file's flags and count."""
    emu = power_on(battery().save_ram, FILLS[fill])
    boot_and_start(emu, 1)
    loaded = first_readable(emu.seen)
    assert all(frame.mode in (Mode.TITLE, Mode.FILE_SELECT) or index <= FIRST_FRAMES
               for index, frame in enumerate(emu.seen[:loaded]))
    assert emu.seen[loaded].mode == Mode.LOAD_LEVEL
    assert all(frame.readable for frame in emu.seen[loaded:])
    assert_safe(emu.seen, 1)


def test_a_reset_mid_game() -> None:
    """The console's reset in play: the flags stay the file's until ClearRam, then nothing is
    readable until the file is loaded again."""
    emu = power_on(battery().save_ram, FILLS["$FF"])
    boot_and_start(emu, 0)
    before = len(emu.seen)
    emu.reset()
    boot_and_start(emu, 0)
    after_reset = emu.seen[before:]
    cleared = next(index for index, frame in enumerate(after_reset) if not frame.readable)
    assert cleared <= FIRST_FRAMES
    reloaded = first_readable(after_reset[cleared:]) + cleared
    assert all(frame.mode in (Mode.TITLE, Mode.FILE_SELECT) for frame in after_reset[cleared:reloaded][FIRST_FRAMES:])
    assert_safe(emu.seen, 0)


@pytest.mark.parametrize("ram", ["kept", "$FF"])
def test_a_power_cycle(ram: str) -> None:
    """Off and on again with the battery: RAM as it was (a short power cycle keeps it) or $FF."""
    emu = power_on(battery().save_ram, FILLS["$FF"])
    boot_and_start(emu, 0)
    kept = [emu[address] for address in range(RAM_SIZE)]
    save_ram = bytes(emu[address] for address in SAVE_RAM)
    cycled = power_on(save_ram, (lambda address: kept[address]) if ram == "kept" else FILLS["$FF"])
    boot_and_start(cycled, 0)
    assert any(not frame.readable for frame in cycled.seen[:FIRST_FRAMES])
    assert_safe(cycled.seen, 0)


def test_switching_save_files() -> None:
    """File 1 in play, saved, back to the file-select screen (still holding file 1's flags, but
    not readable), then file 2: from its load on, file 2's flags and count."""
    emu = power_on(battery().save_ram, FILLS["$10"])
    boot_and_start(emu, 0)
    first_file = len(emu.seen)
    emu.save_to_menu()
    emu.run(PLAY_FRAMES)
    menu = emu.seen[-1]
    assert menu.mode == Mode.FILE_SELECT and not menu.readable
    assert menu.flags == battery().flags[0]          # stale: the predicate is what keeps it out
    second_file = len(emu.seen)
    emu.start_game(1)
    emu.run(PLAY_FRAMES)
    assert_safe(emu.seen[:second_file], 0)
    assert not any(frame.readable for frame in emu.seen[first_file:second_file] if frame.mode < Mode.LOAD_LEVEL)
    assert_safe(emu.seen[second_file:], 1)
    assert emu.seen[-1].readable
