"""Level 9 Entry (C08; FP-TRIF-02 to FP-TRIF-06) in the emulator, on generated ROMs: Link enters the
room of level 9's entrance person holding given pieces (or the gate's item), and the person either
leaves with the shutters opening, or stays with the shutters shut (the spec ran these in the
reference only: "not run in an emulator").

  - a count admits at that many pieces from any levels and refuses one fewer;
  - Open Level 9 admits with no pieces;
  - Specific Triforces admits with the chosen levels' pieces, and refuses more pieces that miss one;
  - Other Item admits with the item and no pieces, and refuses all eight pieces without it;
  - eight pieces (PRG0's check) still admits only all eight; a PRG1 ROM behaves as a PRG0 one."""
from functools import cache

import pytest

from tests.emulator import CUR_OPENED_DOORS, INV_TRIFORCE, OBJ_TYPE, ROOM_ID, SHUTTER_TRIGGER
from tests.needs import needs_base_rom
from tests.test_progressive_emulator import ENTER_ROOM_MODE, Game
from zora.flags.codec import decode, encode
from zora.flags.fields import Level9Requirement
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import build, finish, generate_rom, plan
from zora.model.level_9_gate import GateKind, Level9Gate
from zora.rom.base_rom import PRG1_ROM_PATH, remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora.rom.start_items import START_ITEM_SLOTS

pytestmark = needs_base_rom

ITEMS = 0x0657                       # Items, RAM $0657
LEVEL_9 = 9
ENTRANCE_PERSON = 0x4B
MONSTER_SLOTS = range(1, 0x0C)
GATE_FRAMES = 120
ALL_PIECES = 0xFF
# (C08, seed): seed 1 draws 1 piece under Triforce Range, seed 2 levels 2, 6 and 8 under Specific
# Triforces, seeds 1 and 2 the recorder and the wand under Other Item (tests/test_level_9_entry.py
# generates every value)
CASES = [(3, 1), (Level9Requirement.OPEN, 1), (Level9Requirement.RANDOM_COUNT_IN_RANGE, 1),
         (Level9Requirement.SPECIFIC_PIECES, 2), (Level9Requirement.ITEM_INSTEAD_OF_PIECES, 1),
         (Level9Requirement.ITEM_INSTEAD_OF_PIECES, 2), (0, 1)]


def flags(c08: int) -> str:
    return encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(options={"C08": c08}))


@cache
def generated(c08: int, seed: int, base: bytes) -> tuple[bytes, Level9Gate]:
    built = build(plan(flags(c08), seed), base)
    return finish(built, base), built.world.level_9_gate


def admits(rom: bytes, pieces: int, gate: Level9Gate | None = None) -> bool:
    """Enter the person's room (the room north of level 9's entrance) with these pieces, and the
    gate's item if `gate` is given: whether the person left and the shutters opened."""
    level_9 = next(level for level in parse_rom(rom).levels if level.level_num == LEVEL_9)
    game = Game(rom)
    game.emu[INV_TRIFORCE] = pieces
    if gate is not None and gate.item is not None:
        slot, value = START_ITEM_SLOTS[gate.item]
        game.emu[ITEMS + slot] = value
    game.enter_level(LEVEL_9)
    game.emu[ROOM_ID] = level_9.entrance_room - 0x10
    game.start_mode(ENTER_ROOM_MODE)
    triggered = False
    for _ in range(GATE_FRAMES):
        game.emu.run(1)
        triggered |= bool(game.emu[SHUTTER_TRIGGER])
    present = any(game.emu[OBJ_TYPE + slot] == ENTRANCE_PERSON for slot in MONSTER_SLOTS)
    opened = bool(game.emu[CUR_OPENED_DOORS])
    assert (not present) == triggered == opened, (present, triggered, opened)
    return opened


def pieces_of(levels: frozenset[int] | range) -> int:
    return sum(1 << (level - 1) for level in levels)


def check_gate(rom: bytes, gate: Level9Gate) -> None:
    if gate.kind is GateKind.ITEM:
        assert admits(rom, 0, gate)
        assert not admits(rom, ALL_PIECES)
    elif gate.kind is GateKind.LEVELS:
        assert admits(rom, pieces_of(gate.levels))
        missing_one = pieces_of(range(1, 9)) & ~(1 << (min(gate.levels) - 1))
        assert not admits(rom, missing_one)
    else:
        assert admits(rom, pieces_of(range(8, 8 - gate.pieces, -1)))       # the last levels' pieces
        if gate.pieces:
            assert not admits(rom, pieces_of(range(1, gate.pieces)))       # one fewer


@pytest.mark.parametrize(("c08", "seed"), CASES)
def test_the_entrance_admits_and_refuses_as_the_gate_says(c08: int, seed: int) -> None:
    rom, gate = generated(c08, seed, remember_repo_base_rom())
    if c08 == Level9Requirement.OPEN:
        assert gate.kind is GateKind.OPEN and admits(rom, 0)
    check_gate(rom, gate)


def test_a_prg1_rom_behaves_the_same() -> None:
    if not PRG1_ROM_PATH.exists():
        pytest.skip(f"{PRG1_ROM_PATH.name} is not beside the PRG0 base")
    for c08, seed in ((3, 1), (Level9Requirement.SPECIFIC_PIECES, 2), (Level9Requirement.ITEM_INSTEAD_OF_PIECES, 1)):
        rom = generate_rom(flags(c08), seed, PRG1_ROM_PATH.read_bytes()).rom      # the page's way, PRG1 identified
        _prg0_rom, gate = generated(c08, seed, remember_repo_base_rom())          # generation works in PRG0's layout
        check_gate(rom, gate)
