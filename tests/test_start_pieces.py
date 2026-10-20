"""Starting Triforce pieces (C18) and the piece-count range (C24, C25; flags-behavior.md FL-ALT-06):
C18 = i starts a new file with i pieces drawn uniformly without replacement (9: i drawn from 0 to 8),
in fp-start-02's table (InvTriforce); the draws come from the start-item stream; C24 and C25 are
inert while C08 = 0 (no byte, no draw). Muffle Rug's values: C18 = 2 with C24 = 8."""
from collections import Counter
from functools import cache

import pytest

from tests.emulator import INV_TRIFORCE, Emulator
from tests.needs import needs_base_rom
from zora.flags import codec
from zora.flags.form import metadata
from zora.flags.support import Support, support
from zora.generate.pipeline import Built, build, finish, plan
from zora.generate.rng import Rng, ScriptedRng
from zora.generate.steps.start_items import ALL_PIECES, draw_start_pieces
from zora.model.canonical import canonical_bytes
from zora.model.game_world import GameWorld
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom

DEFAULT_SETTINGS = codec.decode(metadata()["defaultFlags"])      # CP-5
SEEDS = range(1, 7)


def flags(**options: int) -> str:
    return codec.encode(DEFAULT_SETTINGS.updated(options=options))


@pytest.mark.parametrize(("field_id", "values"), [("C18", range(10)), ("C24", range(9)), ("C25", range(9))])
def test_every_value_is_supported(field_id: str, values: range) -> None:
    for index in values:
        assert support(DEFAULT_SETTINGS.updated(options={field_id: index}))[field_id] is Support.SUPPORTED


def test_the_draw_takes_count_pieces() -> None:
    for count in range(9):
        assert bin(draw_start_pieces(count, Rng(count))).count("1") == count


def test_no_draw_for_none_or_all() -> None:
    empty = ScriptedRng([])
    assert draw_start_pieces(0, empty) == 0 and draw_start_pieces(8, empty) == ALL_PIECES


def test_every_piece_equally_likely() -> None:
    """FL-ALT-06: every set of i pieces equally likely, so each piece is held in i/8 of the draws."""
    rng, draws = Rng(2026), 4000
    held = Counter(level for _ in range(draws) for level in range(8) if draw_start_pieces(2, rng) >> level & 1)
    assert all(abs(held[level] - draws / 4) < draws / 20 for level in range(8)), held


def test_the_range_is_inert() -> None:
    """C24 and C25 change no generation setting while C08 = 0 (the start-item stream depends on the
    canonical string, so the start state is compared without start pieces)."""
    plain = plan(flags(), 1)
    for options in ({"C24": 8}, {"C25": 8}, {"C24": 3, "C25": 2}):
        ranged = plan(flags(**options), 1)
        assert (ranged.alternatives, ranged.steps, ranged.config) == (plain.alternatives, plain.steps, plain.config)


@cache
def _built(flag_string: str, seed: int) -> Built:
    return build(plan(flag_string, seed), remember_repo_base_rom())


@cache
def _rom(flag_string: str, seed: int) -> bytes:
    return finish(_built(flag_string, seed), remember_repo_base_rom())


@needs_base_rom
def test_muffle_rug_values_in_seeds() -> None:
    """C18 = 2 with C24 = 8: two pieces in every seed's table, read back from the ROM."""
    for seed in SEEDS:
        flag_string = flags(C18=2, C24=8)
        world: GameWorld = parse_rom(_rom(flag_string, seed))
        assert bin(world.start_triforce_pieces).count("1") == 2
        assert world.start_triforce_pieces == _built(flag_string, seed).world.start_triforce_pieces


@needs_base_rom
def test_random_count_in_seeds() -> None:
    counts = {bin(parse_rom(_rom(flags(C18=9), seed)).start_triforce_pieces).count("1") for seed in range(1, 13)}
    assert len(counts) > 2 and counts <= set(range(9))


@needs_base_rom
def test_no_pieces_keeps_prg0s_start() -> None:
    """C18 = 0: no table for the pieces, the world as before (its code unchanged)."""
    world = _built(flags(), 1).world
    assert world.start_triforce_pieces == 0 and not world.uses_start_table
    assert b"start_triforce_pieces" not in canonical_bytes(world)


@needs_base_rom
def test_a_new_file_starts_with_the_pieces() -> None:
    """In play: a new save file's InvTriforce holds the drawn pieces."""
    flag_string = flags(C18=2, C24=8)
    emu = Emulator(_rom(flag_string, 1))
    emu.new_game()
    assert emu[INV_TRIFORCE] == _built(flag_string, 1).world.start_triforce_pieces
    assert bin(emu[INV_TRIFORCE]).count("1") == 2
