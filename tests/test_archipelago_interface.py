"""Archipelago's interface (zora/archipelago.py; docs/archipelago.md "Interface"), Archipelago
Phase 4a test 3 and finish():
  - the pool has one item per place, every place name is one of all_place_names(), and the
    logic model's places are exactly the build's;
  - finish() by names makes the ROM pipeline.finish makes with the same items, passes another
    player's item through, and refuses a name that is no item and a ROM that is not PRG0."""
import pytest

from tests.archipelago_cases import FLAG_CASES
from tests.test_assignment import identity
from zora import archipelago
from zora.generate.finish import FOREIGN
from zora.generate.pipeline import finish
from zora.generate.places import all_place_names
from zora.model.item_names import ITEM_NAMES
from zora.rom.base_rom import BASE_ROM_PATH, BaseRomMismatch, remember_repo_base_rom

SEEDS = (1, 2)


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("vanilla ROM missing")
    return remember_repo_base_rom()


def built(case: str, seed: int, base: bytes) -> archipelago.BuildResult:
    flag_string, zora_flag_string = FLAG_CASES[case]
    return archipelago.build_from_strings(flag_string, zora_flag_string, seed, base)


def by_name(result: archipelago.BuildResult) -> dict[str, str | archipelago.Foreign]:
    return {place: ITEM_NAMES[item] if not isinstance(item, archipelago.Foreign) else item
            for place, item in identity(result.state).items()}


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_the_build(base: bytes, case: str, seed: int) -> None:
    result = built(case, seed, base)
    names = [place.name for place in result.places]
    assert len(result.pool) == len(result.places) == len(set(names))
    assert set(names) <= set(all_place_names())
    assert list(result.logic.places) == names
    assert all(name in ITEM_NAMES.values() for name in result.pool)
    hearts = {place.name: place.hearts for place in result.places if place.hearts is not None}
    assert set(hearts) <= {"White Sword Cave", "Magical Sword Cave"} and "White Sword Cave" in hearts


@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_finish_by_names(base: bytes, case: str) -> None:
    result = built(case, 1, base)
    assert archipelago.finish(result, by_name(result)) == finish(result.state, base, identity(result.state))


def test_finish_passes_another_players_item_through(base: bytes) -> None:
    result = built("baseline", 1, base)
    assignment = by_name(result)
    coast_item = assignment["Coast"]
    assert isinstance(coast_item, str)
    assignment["Coast"] = archipelago.FOREIGN
    expected = finish(result.state, base, {**identity(result.state), "Coast": FOREIGN},
                      received=[archipelago.item_named(coast_item)])
    assert archipelago.finish(result, assignment, received=[coast_item]) == expected


def test_finish_refuses_an_unknown_name(base: bytes) -> None:
    result = built("baseline", 1, base)
    with pytest.raises(archipelago.UnknownItem, match="Hookshot"):
        archipelago.finish(result, {**by_name(result), "Coast": "Hookshot"})


def test_build_refuses_another_rom(base: bytes) -> None:
    with pytest.raises(BaseRomMismatch, match="PRG0"):
        archipelago.build_from_strings(*FLAG_CASES["baseline"], 1, base[:-1] + b"\x00")
