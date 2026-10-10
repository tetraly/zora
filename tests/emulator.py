"""Headless NES emulator harness for the patch tests (docs/packaging.md,
"Emulator tests").

Wraps cynes (pip, MIT, binary wheels for macOS, Linux and Windows): load a
ROM, feed scripted controller input frame by frame, read CPU RAM, PPU
nametables and pattern tables, the last rendered frame (RGB) and the frame
count. RAM names are the pinned disassembly's labels (src/Variables.inc).
"""
import hashlib
import os
from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum, IntFlag
from pathlib import Path

import numpy as np
import pytest

cynes = pytest.importorskip("cynes")

REPO = Path(__file__).resolve().parent.parent
ROM_CACHE = REPO / "temp" / "emulator"

# CPU RAM (src/Variables.inc)
CUR_LEVEL = 0x10
GAME_MODE = 0x12
GAME_SUBMODE = 0x13
FRAME_COUNTER = 0x15
CUR_SAVE_SLOT = 0x16
OBJ_TIMER = 0x28                     # slot 0 is Link's
TRIGGERED_DOOR_CMD = 0x54
TRIGGERED_DOOR_DIR = 0x55
OBJ_X = 0x70
OBJ_Y = 0x84
OBJ_DIR = 0x98
PAUSED = 0xE0
MENU_STATE = 0xE1
ROOM_ID = 0xEB
OBJ_STATE = 0xAC
ROOM_ITEM_SLOT = 0x13                # the object slot of a room's item
CUR_PPU_CONTROL = 0xFF               # the shadow of PPUCTRL
CUR_OPENED_DOORS = 0xEE
SHUTTER_TRIGGER = 0x4CE
STATUS_BAR_MAP_TRIGGER = 0x4E5
TRIFORCE_FANFARE_ACTIVE = 0x509
LEVEL_INFO = 0x6B7E                  # the current level's information block
WHIRLWIND_TELEPORTING_STATE = 0x522
SELECTED_ITEM_SLOT = 0x656
OBJ_TYPE = 0x34F
ITEMS = 0x657
INV_RECORDER = ITEMS + 5
INV_BOMBS = 0x658
INV_BOOK = 0x661
INV_MAP = 0x668                      # one bit per level 1-8
INV_KEYS = 0x66E
INV_TRIFORCE = 0x671
LAST_BOSS_DEFEATED = 0x672
INV_BOOMERANG = 0x674
RECORDER_SLOT = 4                    # SelectedItemSlot value of the recorder
LEVEL_1_TRIFORCE = 0x01              # InvTriforce bit
LEVEL_1_MOUTH_X = 0x70
LEVEL_ENTRY_SETTLE_FRAMES = 40       # Link walks up from the entrance
FACE_FRAMES = 8
QUEST_NUMBERS = 0x62D                # one per save slot
NAMES = 0x638                        # 8 tiles per save slot
NAME_LENGTH = 8
SPRITES = 0x200                     # the OAM shadow, copied to the PPU each frame
OAM_SIZE = 0x100

# cynes 0.1.2 keeps CHR RAM (the 8 KB pattern tables) at this offset of its
# save state; test_emulator.py checks it against PRG0's common patterns.
CHR_RAM_STATE_OFFSET = 994
CHR_RAM_SIZE = 0x2000

# cynes 0.1.2 keeps the PPU's 2 KB of nametable RAM at this offset of its
# save state; the module cannot read PPU memory any other way (a $2007 read
# through the CPU bus returns 0). test_emulator.py checks the offset against
# PRG0's file-select screen, so a cynes upgrade that moves it fails loudly.
CIRAM_STATE_OFFSET = 17378
CIRAM_SIZE = 0x800
NAMETABLE_SIZE = 0x400
NAMETABLE_BASE = 0x2000
STATUS_BAR_ROWS = 0x2000, 0xC0       # PPU address and size of the status bar's tiles
SCREEN_WIDTH, SCREEN_HEIGHT = 256, 240


CONTROLLER_2_SHIFT = 8               # cynes: controller 2 is the high byte


class Button(IntFlag):
    RIGHT = 0x01
    LEFT = 0x02
    DOWN = 0x04
    UP = 0x08
    START = 0x10
    SELECT = 0x20
    B = 0x40
    A = 0x80


class Mode(IntEnum):
    """GameMode values the tests wait for."""
    TITLE = 0x00
    FILE_SELECT = 0x01
    LOAD_LEVEL = 0x02
    PLAY = 0x05
    ENTER = 0x10                     # walking into a cave or level mouth
    REGISTER = 0x0E


MENU_OPEN = 8                        # MenuState once the item screen is down
CONTINUE_MODE = 0x08                 # GameMode: continue / save / retry
SAVE_CHOICE = 1


class Direction(IntEnum):
    """ObjDir bits."""
    RIGHT = 0x01
    LEFT = 0x02
    DOWN = 0x04
    UP = 0x08


BLANK_TILE = 0x24

# The file-select menu's "End" choice in register mode, after the 3 slots.
REGISTER_END_CHOICE = 3


@dataclass(frozen=True)
class _Booted:
    """A console just after new_game from power-on: its state, frame count and last frame."""
    state: bytes
    frames: int
    last_frame: np.ndarray


# new_game's result per ROM (SHA-1), in this process (tasks/test-speed-2.md): booting takes
# about 300 frames, and many tests boot the same ROM. A reloaded state plays on exactly as the
# console it was saved from (RAM, save RAM, the whole state and the screen, checked through
# level entry), so a console that has done nothing yet loads the earlier boot instead.
_BOOTED: dict[str, _Booted] = {}


class Emulator:
    """One running console. `frames` counts the frames stepped so far."""

    def __init__(self, rom: bytes | Path) -> None:
        path = _rom_file(rom)
        self.nes = cynes.NES(str(path))
        self.rom_hash = hashlib.sha1(path.read_bytes()).hexdigest()
        self.frames = 0
        self.last_frame = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)
        self.untouched = True                # no frame, write, load or reset since power-on

    def __getitem__(self, address: int) -> int:
        """CPU RAM byte."""
        return int(self.nes[address])

    def __setitem__(self, address: int, value: int) -> None:
        self.untouched = False
        self.nes[address] = value

    def run(self, frames: int, buttons: Button = Button(0)) -> None:
        """Step `frames` frames holding `buttons`, then release them."""
        self.untouched = False
        self.nes.controller = int(buttons)
        for _ in range(frames):
            self.last_frame = self.nes.step(1)
        self.frames += frames
        self.nes.controller = 0

    def press(self, buttons: Button, after: int = 10) -> None:
        """Tap `buttons` for 2 frames (the game reads new presses as edges),
        then idle `after` frames."""
        self.run(2, buttons)
        self.run(after)

    def run_until(self, done: Callable[[], bool], limit: int = 600,
                  buttons: Button = Button(0)) -> int:
        """Step frame by frame until `done()`; return the frames taken."""
        for taken in range(limit):
            if done():
                return taken
            self.run(1, buttons)
        raise AssertionError(f"condition not reached within {limit} frames")

    @property
    def mode(self) -> int:
        return self[GAME_MODE]

    def ciram(self) -> bytes:
        """The PPU's 2 KB nametable RAM, physical order."""
        state = self.save()
        return state[CIRAM_STATE_OFFSET:CIRAM_STATE_OFFSET + CIRAM_SIZE]

    def nametable(self, ppu_address: int, count: int) -> bytes:
        """`count` bytes from PPU address `ppu_address` ($2000-$2FFF),
        under the horizontal mirroring the game keeps outside scrolling
        ($2000 = $2400, $2800 = $2C00)."""
        logical = ppu_address - NAMETABLE_BASE
        physical = (logical // (2 * NAMETABLE_SIZE)) * NAMETABLE_SIZE + logical % NAMETABLE_SIZE
        return self.ciram()[physical:physical + count]

    def pattern_tables(self) -> bytes:
        """CHR RAM: the 8 KB of tile patterns."""
        return self.save()[CHR_RAM_STATE_OFFSET:CHR_RAM_STATE_OFFSET + CHR_RAM_SIZE]

    def sprites(self) -> bytes:
        """The OAM shadow: 64 records of Y, tile, attributes, X."""
        return bytes(self[SPRITES + i] for i in range(OAM_SIZE))

    def save(self) -> bytes:
        return bytes(self.nes.save())

    def load(self, state: bytes) -> None:
        """Restore a state. The state holds RAM, save RAM and the CPU and
        PPU, not the ROM, so a state saved under one ROM loads under
        another (a save file carried across builds)."""
        self.untouched = False
        self.nes.load(np.frombuffer(bytearray(state), dtype=np.uint8))

    def reset(self) -> None:
        """Press the console's reset button."""
        self.untouched = False
        self.nes.reset()

    # Scripted menus

    def boot_to_file_select(self) -> None:
        self.run(60)
        self.press(Button.START)
        self.run_until(lambda: self.mode == Mode.FILE_SELECT)
        self.run(20)

    def register_file(self, name: bytes | None = None) -> None:
        """From the file-select menu, register a name in the first free
        slot and return to the menu. Without `name` it types one letter;
        with it, the tiles are written into the slot's name as typing them
        on the character board would."""
        while self[CUR_SAVE_SLOT] != REGISTER_END_CHOICE:
            self.press(Button.SELECT)
        self.press(Button.START, after=30)
        assert self.mode == Mode.REGISTER
        self.press(Button.A)
        if name is not None:
            slot = self[CUR_SAVE_SLOT]
            for i, tile in enumerate(name.ljust(NAME_LENGTH, bytes([BLANK_TILE]))):
                self[NAMES + slot * NAME_LENGTH + i] = tile
        while self[CUR_SAVE_SLOT] != REGISTER_END_CHOICE:
            self.press(Button.SELECT)
        self.press(Button.START)
        self.run_until(lambda: self.mode == Mode.FILE_SELECT)
        self.run(20)

    def start_game(self, slot: int = 0) -> None:
        """From the menu, start `slot` and run until Link can move."""
        while self[CUR_SAVE_SLOT] != slot:
            self.press(Button.SELECT)
        self.press(Button.START)
        self.run_until(lambda: self.mode == Mode.PLAY)

    def new_game(self) -> None:
        """Boot, register one file and start it; from power-on, a ROM this process has booted
        before loads that boot (_BOOTED)."""
        from_power_on = self.untouched and self.frames == 0
        booted = _BOOTED.get(self.rom_hash) if from_power_on else None
        if booted is not None:
            self.load(booted.state)
            self.frames = booted.frames
            self.last_frame = booted.last_frame.copy()
            return
        self.boot_to_file_select()
        self.register_file()
        self.start_game()
        if from_power_on:
            _BOOTED[self.rom_hash] = _Booted(self.save(), self.frames, self.last_frame.copy())

    def play_recorder(self, triforce_pieces: int) -> None:
        """Give Link the recorder and these triforce pieces (InvTriforce
        bits), play it, and run until the whirlwind sets him down."""
        self[INV_RECORDER] = 1
        self[INV_TRIFORCE] = triforce_pieces
        self[SELECTED_ITEM_SLOT] = RECORDER_SLOT
        # Face a direction first: at a ZORA start Link faces none, and uses
        # no item until he moves (FP-ENTR-01).
        self.run(FACE_FRAMES, Button.UP)
        self.run(5)                         # the B item is read from the slot next frame
        self.press(Button.B)
        self.run_until(lambda: self[WHIRLWIND_TELEPORTING_STATE] != 0)
        self.run_until(lambda: self[WHIRLWIND_TELEPORTING_STATE] == 0, limit=900)

    def open_item_screen(self) -> None:
        self.press(Button.START)
        self.run_until(lambda: self[MENU_STATE] == MENU_OPEN, limit=200)
        self.run(5)

    def close_item_screen(self) -> None:
        self.press(Button.START)
        self.run_until(lambda: self[MENU_STATE] == 0, limit=300)
        self.run(10)

    def save_and_reload(self) -> None:
        """From the item screen: Up and A held on both controllers (PRG0
        reads controller 2, FP-RESET-01 controller 1) to the continue
        screen, choose SAVE, press the console's reset and start slot 0
        again."""
        combination = Button.UP | Button.A
        self.nes.controller = combination << CONTROLLER_2_SHIFT | combination
        for _ in range(3):
            self.nes.step(1)
        self.nes.controller = 0
        self.run_until(lambda: self.mode == CONTINUE_MODE)
        self.run(20)
        while self[GAME_SUBMODE] != SAVE_CHOICE:
            self.press(Button.SELECT)
        self.press(Button.START)
        # Saving runs through its own mode and ends on the file-select menu.
        self.run_until(lambda: self.mode == Mode.FILE_SELECT, limit=900)
        self.reset()
        self.boot_to_file_select()
        self.start_game()

    def walk_into_level_1(self) -> None:
        """From play on the overworld: take the whirlwind to level 1's
        entrance (PRG0's screen layout: the mouth is left of where the
        whirlwind sets Link down), walk in, and run until Link stands in
        the start room."""
        self.play_recorder(LEVEL_1_TRIFORCE)
        self.run_until(lambda: self[OBJ_X] <= LEVEL_1_MOUTH_X, buttons=Button.LEFT)
        self.run_until(lambda: self.mode == Mode.PLAY and self[CUR_LEVEL] == 1,
                       buttons=Button.UP, limit=1000)
        self.run(LEVEL_ENTRY_SETTLE_FRAMES)


def _rom_file(rom: bytes | Path) -> Path:
    """cynes loads from a path; ROM images go to temp/ under their hash."""
    if isinstance(rom, Path):
        return rom
    ROM_CACHE.mkdir(parents=True, exist_ok=True)
    path = ROM_CACHE / f"{hashlib.sha1(rom).hexdigest()}.nes"
    if not path.exists():
        # Parallel test workers (pytest -n) may cache the same ROM at once: write
        # under a private name and rename, so no worker loads a half-written file.
        partial = path.with_name(f"{path.name}.{os.getpid()}.part")
        partial.write_bytes(rom)
        os.replace(partial, path)
    return path
