"""The 2026 tournament presets as v3.6.6 builds them in (owner, beta 8): TTP5 Uphill Battle, TTP5
Muffle Rug, TTP5 Pick 5 and SGLive Onsite. Each string is the built-in one exactly, ZORA produces
every field of it (flags-behavior.md FL-SUP-01, the beta 8 export), and each generates on the
spec's seeds and passes the acceptance check: every tracked item collected (E1) and Ganon reached
and beaten before the last-boss shutters open (E10).

The damaged copy of the Uphill Battle string (an out-of-date document's) is checked too: its five
out-of-range slots decode as their last options (FL-ENC-03 rule 3), it differs from the tournament
string, and with every value produced it generates, unmirrored, with the mirror notice."""
from functools import cache

import pytest

from tests.needs import needs_base_rom, needs_encoder
from zora.flags.codec import decode, encode
from zora.flags.fields import ENCODE_LEVEL_DATA
from zora.flags.presets import (
    SGLIVE_ONSITE_FLAGS,
    TTP5_MUFFLE_RUG_FLAGS,
    TTP5_PICK_5_FLAGS,
    TTP5_UPHILL_BATTLE_FLAGS,
    ZORA_PRESETS,
)
from zora.flags.support import MIRRORED_OVERWORLD_NOTICE, unsupported_fields
from zora.generate.acceptance_check import AcceptanceCheck
from zora.generate.pipeline import Built, build, plan, shipped_logic_rules
from zora.rom.base_rom import remember_repo_base_rom

TOURNAMENT = {
    "TTP5: Uphill Battle": "143oNtDD4Pw3Yw6SRryTCXlqTsRz2fxg4s4pJW",
    "TTP5: Muffle Rug": "2487lt0moGMFLRug1ofQdxPuUBWnJVSsi7d202I",
    "TTP5: Pick 5": "p8GIOeYEAonHy5131VdG6b94Ts3EMMvBaQoWR",
    "SGLive Onsite 2026": "12TDBKH6mxLfnSz4T7ME4bcIaaUe9sE7UVmj7RA",
}
# Each string with Encode level data on (B82: all four) is planned only with the private encoder; a
# release tree skips it, as every encoder-dependent test does (tests/needs.py).
ENCODED = [pytest.param(name, marks=needs_encoder) if decode(flags).is_on(ENCODE_LEVEL_DATA) else name
           for name, flags in TOURNAMENT.items()]
DAMAGED_UPHILL_BATTLE = "143oNtDD4Pw3Yw6SRryTCXlqTsN20hHVl8gF"
SEEDS = (1, 2, 3)


@cache
def built(flag_string: str, seed: int) -> Built:
    return build(plan(flag_string, seed), remember_repo_base_rom())


def test_the_presets_are_the_built_in_strings() -> None:
    assert (TTP5_UPHILL_BATTLE_FLAGS, TTP5_MUFFLE_RUG_FLAGS, TTP5_PICK_5_FLAGS, SGLIVE_ONSITE_FLAGS) == tuple(
        TOURNAMENT.values())
    assert {name: ZORA_PRESETS[name] for name in TOURNAMENT} == {name: (flags, "")
                                                                 for name, flags in TOURNAMENT.items()}


@pytest.mark.parametrize("name", ENCODED)
def test_every_field_is_produced_and_the_string_is_canonical(name: str) -> None:
    flag_string = TOURNAMENT[name]
    assert encode(decode(flag_string)) == flag_string
    assert unsupported_fields(decode(flag_string)) == []
    assert plan(flag_string, 1).notices == ()


@needs_base_rom
@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("name", ENCODED)
def test_each_generates_and_passes_acceptance(name: str, seed: int) -> None:
    seed_built = built(TOURNAMENT[name], seed)
    result = seed_built.result
    assert result.item_shuffle_result is not None and result.overworld is not None
    check = AcceptanceCheck(seed_built.world.levels, result.item_shuffle_result, seed_built.world.overworld,
                            result.overworld, shipped_logic_rules(seed_built.plan, seed_built.world))
    assert check.collects_everything() and check.reaches_ganon_before_shutters_open()


def test_the_damaged_uphill_battle_string() -> None:
    settings = decode(DAMAGED_UPHILL_BATTLE)
    assert [settings.option(field_id) for field_id in ("C01", "C07", "C10", "C22", "C23")] == [4] * 5
    assert encode(settings) != TTP5_UPHILL_BATTLE_FLAGS
    assert unsupported_fields(settings) == ["B06"]                 # postponed: accepted, not produced
    assert plan(DAMAGED_UPHILL_BATTLE, 1).notices == (MIRRORED_OVERWORLD_NOTICE,)


@needs_base_rom
def test_the_damaged_uphill_battle_string_generates_unmirrored() -> None:
    assert built(DAMAGED_UPHILL_BATTLE, 1).world.levels
