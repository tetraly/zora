"""The acceptance check as FINISH's sanity check (R4; zora/generate/finish.py, docs/archipelago.md),
Archipelago Phase 2 test 10, with the owner's decision of 2026-10-08:
  (a) the strict walk (this player's items in other worlds unavailable) is a hard error only in a
      solo game, a diagnostic otherwise;
  (b) the walk with the items received from other worlds granted at the start is the hard check
      in every game."""
import pytest

from tests.archipelago_cases import FLAG_CASES
from tests.test_assignment import _built, identity
from zora.generate.finish import FOREIGN, AssignmentUnbeatable, Foreign
from zora.generate.pipeline import Built, finish, finish_world
from zora.model.enums import Item
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom

SEEDS = (1, 2)


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("vanilla ROM missing")
    return remember_repo_base_rom()


def _holding(built: Built, item: Item) -> str:
    assignment = identity(built)
    return next(name for name, held in assignment.items() if held == item)


def ladder_at_the_coast(built: Built) -> dict[str, Item | Foreign]:
    """A planted bad assignment: the ladder in the coast place, which only the ladder reaches."""
    assignment = identity(built)
    ladder = _holding(built, Item.LADDER)
    assignment[ladder], assignment["Coast"] = assignment["Coast"], Item.LADDER
    return assignment


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_solo_a_valid_assignment_passes(base: bytes, case: str, seed: int) -> None:
    built = _built(case, seed)
    _, finished = finish_world(built, identity(built))
    assert finished.sanity is not None
    assert finished.sanity.solo and finished.sanity.strict is None and finished.sanity.granted is None


@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_solo_a_planted_bad_assignment_fails(base: bytes, case: str) -> None:
    built = _built(case, 1)
    with pytest.raises(AssignmentUnbeatable) as failure:
        finish(built, base, ladder_at_the_coast(built))
    assert failure.value.sanity.solo and failure.value.sanity.strict == "E1"


@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_multiworld_items_received_from_elsewhere_pass(base: bytes, case: str) -> None:
    """The ladder lives in another world: the strict walk fails (a diagnostic only), the walk with
    the ladder granted passes."""
    built = _built(case, 1)
    assignment = identity(built)
    assignment[_holding(built, Item.LADDER)] = FOREIGN
    _, finished = finish_world(built, assignment, received=[Item.LADDER])
    assert finished.sanity is not None
    assert not finished.sanity.solo
    assert finished.sanity.strict == "E1" and finished.sanity.granted is None
    assert finished.tracking.elsewhere == [Item.LADDER]
    finish(built, base, assignment, received=[Item.LADDER])


@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_multiworld_an_own_item_behind_what_it_unlocks_fails(base: bytes, case: str) -> None:
    built = _built(case, 1)
    assignment = ladder_at_the_coast(built)
    raft = _holding(built, Item.RAFT)
    assignment[raft] = FOREIGN
    with pytest.raises(AssignmentUnbeatable) as failure:
        finish(built, base, assignment, received=[Item.RAFT])
    assert not failure.value.sanity.solo and failure.value.sanity.granted == "E1"


def test_multiworld_an_item_neither_here_nor_received_fails(base: bytes) -> None:
    """An own item the filler dropped (in no place, not received) fails the hard walk too."""
    built = _built("baseline", 2)
    assignment = identity(built)
    assignment[_holding(built, Item.LADDER)] = FOREIGN
    with pytest.raises(AssignmentUnbeatable) as failure:
        finish(built, base, assignment)
    assert failure.value.sanity.granted == "E1"
