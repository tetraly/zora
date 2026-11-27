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
        pytest.skip("needs the base ROM")
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


# Archipelago scan seed 300030 (2026-11-21): Offense Item Pacing on, the white sword in the magical-sword cave. Its
# sword counts once the hearts meet that cave's requirement, and the sanity walk counted only the heart containers
# BUILD had dealt to the extras' caves and joined wares, not the assigned world's, so it never counted the second
# sword and refused the seed's own items (E1).
PACED_FLAGS, PACED_ZORA, PACED_SEED = "2J1ncTGmHLYYHBdk4Gmpr8zaJYEUPJYU8v2AE9oX0", "15.1r1bHV1S!Y", 30


def test_offense_pacing_counts_the_assigned_worlds_hearts(base: bytes) -> None:
    from zora import archipelago
    built = archipelago.build_from_strings(PACED_FLAGS, PACED_ZORA, PACED_SEED, base)
    archipelago.finish(built, {place.name: item for place, item in zip(built.places, built.pool, strict=True)})


# Archipelago rescan seed 304026 (2026-11-21): Shuffle Minor Dungeon Drops (B17) On dealt the wand to level 9 room $50, an
# enemy room; the monster re-deal moved Zelda in, and the late gate moved her room to $11, the wand with it. Zelda's room
# is never a place, so the wand stays there whatever the assignment, and the sanity walk counted it elsewhere (E1).
# Since 2026-11-23 an Archipelago build skips B17's own deal (archipelago.without_minor_deal), so this world is built
# with the deal, as it was then: FINISH's tracking of an item in Zelda's room is still the code under test.
ZELDA_FLAGS, ZELDA_ZORA, ZELDA_SEED = "4lfVz10KngNcVPv61Ywnkeghfg6MhtWnM9AMUr0i6", "15.MEAd78uVN", 26


def test_an_item_in_zeldas_room_is_tracked_where_it_lies(base: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    from zora import archipelago
    from zora.generate.places import room_name
    from zora.model.enums import Enemy
    monkeypatch.setattr(archipelago, "without_minor_deal", lambda chosen: chosen)
    built = archipelago.build_from_strings(ZELDA_FLAGS, ZELDA_ZORA, ZELDA_SEED, base)
    level9 = next(level for level in built.state.world.levels if level.level_num == 9)
    zelda = next(room for room in level9.rooms if room.enemy == Enemy.THE_KIDNAPPED)
    assert zelda.item == Item.WAND
    assert room_name(level9.rom_level_num, zelda.room_num) not in {place.name for place in built.places}
    assert "Wand" not in built.pool
    archipelago.finish(built, {place.name: item for place, item in zip(built.places, built.pool, strict=True)})
