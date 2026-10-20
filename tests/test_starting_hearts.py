"""Starting hearts at every value (C16; flags-behavior.md FL-ALT-02 and FL-ALT-07): C16 = i starts a
new file with i + 1 containers, the smaller of i + 1 and 3 of them full (HeartValues i * 16 + m,
m = min(i, 2)); a Continue restores m + 1 hearts (0x14B83); one heart fixes the meter's blank branch
(0x06731, $04 to $00); the life toll's heart count is $10, $20 or $30 (0x04C35); 16 is random over 1
to 5. Pick 5's value is five hearts (C16 = 4, $42). In the emulator, a one-heart file's meter on the
file-select screen shows its heart, which PRG0's branch leaves blank."""
from functools import cache

import pytest

from tests.emulator import Emulator
from tests.needs import needs_base_rom
from zora.flags import codec
from zora.flags.form import metadata
from zora.flags.support import Support, support
from zora.generate.pipeline import Built, build, finish, plan
from zora.model.enums import TollOption
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.heart_values import heart_values
from zora.rom.layout import HEART_METER_BLANK_BRANCH_ADDRESS
from zora.rom.parse.rom_file import parse_rom
from zora.rom.person_code import heart_count_operand, life_toll_heart_count_operand

DEFAULT_SETTINGS = codec.decode(metadata()["defaultFlags"])      # CP-5
SEEDS = range(1, 5)
PRG0_METER_BRANCH, FIXED_METER_BRANCH = 0x04, 0x00
PRG0_CONTINUE_OPERAND = 0x02
METER_FRAMES = 30
FULL_HEART_TILE = 0xF2
NAMETABLE_BASE, NAMETABLE_TILES = 0x2000, 0x3C0


def flags(hearts_index: int) -> str:
    return codec.encode(DEFAULT_SETTINGS.updated(options={"C16": hearts_index}))


@pytest.mark.parametrize("index", range(17))
def test_every_value_is_supported(index: int) -> None:
    assert support(DEFAULT_SETTINGS.updated(options={"C16": index}))["C16"] is Support.SUPPORTED


@pytest.mark.parametrize(("containers", "operand"), [(1, 0x10), (2, 0x20), (3, 0x30), (4, 0x30), (16, 0x30)])
def test_the_toll_heart_count(containers: int, operand: int) -> None:
    assert heart_count_operand(containers) == operand


@pytest.mark.parametrize("index", [0, 1, 2, 3, 4, 15, 16])
def test_the_plan_carries_the_hearts(index: int) -> None:
    hearts = plan(flags(index), 1).alternatives.starting_hearts
    assert hearts == index + 1 if index < 16 else 1 <= hearts <= 5


@cache
def _built(index: int, seed: int) -> Built:
    return build(plan(flags(index), seed), remember_repo_base_rom())


@cache
def _rom(index: int, seed: int) -> bytes:
    return finish(_built(index, seed), remember_repo_base_rom())


@needs_base_rom
@pytest.mark.parametrize("index", [0, 1, 2, 3, 4, 15])
def test_the_bytes_in_seeds(index: int) -> None:
    """HeartValues i * 16 + m, Continue m, the meter branch $00 only for one heart, and the toll's
    count where its first option is life; read back from the finished ROM."""
    full = min(index, 2)
    for seed in SEEDS:
        rom = _rom(index, seed)
        world = parse_rom(rom)
        assert heart_values(world.new_file_heart_containers, world.new_file_full_hearts) == index * 16 + full
        assert world.continue_hearts_operand == full
        assert rom[HEART_METER_BLANK_BRANCH_ADDRESS] == (FIXED_METER_BRANCH if index == 0 else PRG0_METER_BRANCH)
        toll = world.life_or_money_toll
        if toll is not None and toll.first == TollOption.LIFE:
            assert life_toll_heart_count_operand(rom) == heart_count_operand(index + 1)


@needs_base_rom
def test_pick_5s_five_hearts() -> None:
    """C16 = 4: $42, five containers and three full; Continue $02 (PRG0's)."""
    world = parse_rom(_rom(4, 1))
    assert heart_values(world.new_file_heart_containers, world.new_file_full_hearts) == 0x42
    assert world.continue_hearts_operand == PRG0_CONTINUE_OPERAND


@needs_base_rom
def test_three_hearts_keep_prg0s_bytes() -> None:
    world = _built(2, 1).world
    assert (world.new_file_heart_containers, world.new_file_full_hearts, world.continue_hearts_operand,
            world.heart_meter_blank_branch) == (3, 3, PRG0_CONTINUE_OPERAND, PRG0_METER_BRANCH)


@needs_base_rom
def test_random_hearts_in_seeds() -> None:
    assert {_built(16, seed).world.new_file_heart_containers for seed in range(1, 13)} <= set(range(1, 6))


def _file_select_screen(rom: bytes) -> bytes:
    """The file-select screen after registering one file (its meter is FormatHeartsInTextBuf's)."""
    emu = Emulator(rom)
    emu.boot_to_file_select()
    emu.register_file()
    emu.run(METER_FRAMES)
    return emu.nametable(NAMETABLE_BASE, NAMETABLE_TILES)


@needs_base_rom
def test_the_one_heart_meter_on_file_select() -> None:
    """The file-select meter of a one-heart file shows its heart with the fix; with PRG0's branch
    put back, the same file's meter is blank. (The in-play status bar draws it either way.)"""
    fixed = _rom(0, 1)
    prg0_branch = bytearray(fixed)
    prg0_branch[HEART_METER_BLANK_BRANCH_ADDRESS] = PRG0_METER_BRANCH
    assert FULL_HEART_TILE in _file_select_screen(fixed)
    assert FULL_HEART_TILE not in _file_select_screen(bytes(prg0_branch))


LIFE_TOLL_SEED = 202


@needs_base_rom
@pytest.mark.parametrize("features_b10", [False, True])
def test_one_heart_with_start_pieces_round_trips(features_b10: bool) -> None:
    """The batch run of be53e6e (test_flag_invariants seeds 101 and 303): with start pieces the hearts
    go in fp-start-02's table, which needs the B10 data; without it the routines' immediates must
    carry them, or the ROM starts with PRG0's three hearts while the life toll counts one."""
    from dataclasses import replace

    from tests.test_flag_invariants import Flags, generate, serialization_config
    from zora.rom.serialize.rom_file import serialize_to_rom

    remember_repo_base_rom()
    base = Flags()
    combination = replace(base, alternatives=replace(base.alternatives, starting_hearts=1, start_triforce_pieces=33),
                          config=replace(base.config, features_b10=features_b10))
    # Seed 202: its life toll asks for life first, so the operand is written (seed 101's did until
    # 114f280 moved its toll to max bombs, whose seeds leave the operand PRG0's)
    rom = generate(combination, LIFE_TOLL_SEED)
    config = serialization_config(combination)
    world = parse_rom(rom, config=config)
    assert world.life_or_money_toll is not None and world.life_or_money_toll.first == TollOption.LIFE
    assert world.new_file_heart_containers == 1
    assert life_toll_heart_count_operand(rom) == heart_count_operand(1)
    assert serialize_to_rom(world, rom, config=config) == rom
