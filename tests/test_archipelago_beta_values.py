"""Archipelago's beta values (zora/archipelago.py HELD_BACK; owner, 2026-11-21): values that have not passed
ZORA's logic scan for multiworld are offered as beta values, and a YAML that names one generates. Each case here
builds a seed through Archipelago's interface with one on and sweeps its logic model with the items where ZORA
put them: every place and the goal are reached. (One seed each: the scan itself is a separate, longer run.)"""
import pytest

from tests.test_assignment import identity
from zora import archipelago
from zora.generate.logic import sweep
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom

SEED = 1
# option key -> value key: one beta value per held field that generates alone (the level 9 pins at the Ladder,
# the Power Bracelet, the Raft and the Recorder need Allow Important Items in 9, B25, too)
CASES = {
    "universal_drops_v2": "on",
    "add_extra_bosses": "on",
    "swap_swords_and_rings": "on",
}
WITH_B25 = {"allow_important_items_in_9": "on", "level_9_item_1": "raft"}


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("needs the base ROM")
    return remember_repo_base_rom()


def test_every_held_field_has_a_case() -> None:
    keys = {spec.id: spec.key for spec in archipelago.option_fields()}
    assert {keys[field] for field in archipelago.HELD_BACK} - set(CASES) == {"level_9_item_1", "level_9_item_2"}


@pytest.mark.parametrize("values", [{key: value} for key, value in CASES.items()] + [WITH_B25], ids=str)
def test_a_beta_value_generates(base: bytes, values: dict[str, str]) -> None:
    assert archipelago.beta_in_use(values)
    result = archipelago.build_from_strings(*archipelago.flag_strings(values), SEED, base)
    swept = sweep(result.logic, identity(result.state))
    assert swept.reaches_goal
    assert set(result.logic.places) <= swept.places
