"""Shuffle Bomb Upgraders off (B29 = 0; flags-behavior.md FL-OFF-04, owner request for beta 5): the
bomb-upgrade move (PS-BOMB-01 to PS-BOMB-03) does not run, the seller path keeps PRG0's code (the
branch $90 $08 and the level operands 5 and 7) and the person-kind table PRG0's low bytes, and the
person-flag $0F rooms of levels 5 and 7 are the sellers: one in each, or both in level 7 when the
hungry-goriya move (B28) took the level-5 person, and under 1st Quest dungeons (C02 = 0) also one in
level 5 and two in level 7 when it took the level-8 person. Its "?" is supported since the beta 9
export (a coin, then FL-DEP-02 rule 4; tests/test_beta9_possible.py).
The Check over 1,000 seeds per string: temp/ scratch runs, figures in the commit's report (the spec's
reference run is n = 200; no corpus has B29 off)."""
from functools import cache

import pytest

from zora.flags.codec import decode, encode
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.support import unsupported_fields
from zora.generate import generation_pass
from zora.generate.pipeline import generate_rom, plan
from zora.model.enums import VANILLA_PERSON_INITS
from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.rom.layout import PERSON_UPDATE_BRANCH_ADDRESS
from zora.rom.parse.rom_file import parse_rom
from zora.rom.person_code import FIRST_BOMB_LEVEL_OPERAND, SECOND_BOMB_LEVEL_OPERAND
from zora_measure.checkpoints.shapes_and_gate import bomb_upgrade_person_levels

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

OFF = ThreeState.OFF
PRG0_BRANCH = bytes([0x90, 0x08])                 # BCC: the bomb-upgrade path behind a branch
PRG0_SELLER_LEVELS: tuple[int, ...] = (5, 7)
SELLER_LEVELS = frozenset(PRG0_SELLER_LEVELS)
SELLERS: set[tuple[int, ...]] = {(5, 7), (7, 7)}  # one in each, or the level-5 person moved to 7
SELLERS_FIRST_QUEST = SELLERS | {(5, 7, 7)}      # C02 = 0: or the level-8 person moved to 7
# Each string's changes from CP-5 (toggles, options) and the seller placements it may give
StringCase = tuple[dict[str, ThreeState], dict[str, int], set[tuple[int, ...]]]
STRINGS: dict[str, StringCase] = {
    "B29 off": ({"B29": OFF}, {}, SELLERS),
    "B29 and B28 off": ({"B29": OFF, "B28": OFF}, {}, {PRG0_SELLER_LEVELS}),
    "B29 off, 1st Quest dungeons": ({"B29": OFF}, {"C02": 0}, SELLERS_FIRST_QUEST),
    "B29 and B28 off, 1st Quest dungeons": ({"B29": OFF, "B28": OFF}, {"C02": 0}, {PRG0_SELLER_LEVELS}),
}


def cp5_with(toggles: dict[str, ThreeState], options: dict[str, int]) -> str:
    return encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(options=options, toggles=toggles))


@cache
def base_rom() -> bytes:
    return verify_base_rom().read_bytes()


@cache
def finished(name: str, seed: int) -> bytes:
    toggles, options, _sellers = STRINGS[name]
    return generate_rom(cp5_with(toggles, options), seed, base_rom()).rom      # raises unless accepted


@pytest.mark.parametrize("name", list(STRINGS))
def test_the_bomb_upgrade_move_does_not_run(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The plan turns the step off, and a generation never calls the move (it would raise)."""
    toggles, options, _sellers = STRINGS[name]
    chosen = plan(cp5_with(toggles, options), 1)
    assert not chosen.steps.shuffle_bomb_upgraders

    def must_not_run(*_args: object) -> None:
        raise AssertionError("PS-BOMB ran with B29 off")
    monkeypatch.setattr(generation_pass, "shuffle_bomb_upgraders", must_not_run)
    generate_rom(cp5_with(toggles, options), 1, base_rom())
    with pytest.raises(AssertionError, match="PS-BOMB ran"):
        generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, base_rom())      # B29 on: it does run


@pytest.mark.parametrize("seed", [1, 2, 3])
@pytest.mark.parametrize("name", list(STRINGS))
def test_the_sellers_and_their_code_are_prg0s(name: str, seed: int) -> None:
    """Generated and accepted; the branch and both operands are PRG0's, so the parse finds no
    move; the table's eight low bytes are PRG0's; the $0F persons of levels 5 and 7 are the
    sellers, none in levels 1 or 2 (the hint pass keeps those of the recorded levels 1, 2, 5, 7)."""
    rom = finished(name, seed)
    gw = parse_rom(rom)
    assert gw.bomb_upgrade_levels is None
    assert rom[PERSON_UPDATE_BRANCH_ADDRESS:PERSON_UPDATE_BRANCH_ADDRESS + len(PRG0_BRANCH)] == PRG0_BRANCH
    assert (rom[FIRST_BOMB_LEVEL_OPERAND], rom[SECOND_BOMB_LEVEL_OPERAND]) == PRG0_SELLER_LEVELS
    assert gw.person_inits == VANILLA_PERSON_INITS
    levels = bomb_upgrade_person_levels(gw)
    assert tuple(level for level in levels if level in SELLER_LEVELS) in STRINGS[name][2]
    assert not {1, 2} & set(levels)


def test_random_is_supported() -> None:
    """FL-SUP-01 (beta 9 export): B29's "?" is supported, a coin per seed before FL-DEP-02 rule 4."""
    flag_string = cp5_with({"B29": ThreeState.POSSIBLE}, {})
    assert unsupported_fields(decode(flag_string)) == []
    assert {plan(flag_string, seed).settings.is_on("B29") for seed in range(1, 21)} == {False, True}


def test_b29_on_still_moves_the_sellers() -> None:
    """The default (B29 on) is unchanged: the move runs and patches the branch."""
    rom = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, base_rom()).rom
    assert parse_rom(rom).bomb_upgrade_levels is not None
