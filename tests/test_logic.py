"""Archipelago's access rules from ZORA's walk (zora/generate/logic.py; docs/archipelago.md
"Logic"), Archipelago Phase 3 test 3: derive turns a ZORA predicate into a rule, and its
monotonicity assertion is live."""
import pytest

from zora.generate.acceptance_check import LEVEL9_ENTRY, ONE_ARROW, TWO_ARROWS
from zora.generate.logic import (
    ARROW,
    FALSE,
    LEVEL9_ENTRY_EVENT,
    TRUE,
    CountTerm,
    EventTerm,
    HeartsTerm,
    ItemTerm,
    NonMonotoneCheck,
    conjoin,
    derive,
    disjoin,
    rule_of,
)
from zora.model.enums import Item

RAFT, LADDER, BOW = ItemTerm(Item.RAFT), ItemTerm(Item.LADDER), ItemTerm(Item.BOW)


def test_derive_keeps_the_minimal_true_subsets() -> None:
    def raft_or_ladder_and_bow(held: frozenset[int]) -> bool:
        return Item.RAFT in held or {Item.LADDER, Item.BOW} <= held
    universe = {Item.RAFT, Item.LADDER, Item.BOW, Item.RECORDER}
    assert derive(raft_or_ladder_and_bow, universe) == disjoin(rule_of(RAFT), rule_of(LADDER, BOW))


def test_derive_always_holds_the_wooden_sword() -> None:
    assert derive(lambda held: Item.WOOD_SWORD in held, {Item.RAFT}) == TRUE
    assert derive(lambda held: False, {Item.RAFT}) == FALSE


def test_derive_maps_pseudo_items_to_terms() -> None:
    def two_arrows_or_level9(held: frozenset[int]) -> bool:
        return TWO_ARROWS in held or LEVEL9_ENTRY in held
    rule = derive(two_arrows_or_level9, {ONE_ARROW, TWO_ARROWS, LEVEL9_ENTRY})
    assert rule == disjoin(rule_of(CountTerm(ARROW, 2)), rule_of(EventTerm(LEVEL9_ENTRY_EVENT)))


def test_the_monotonicity_assertion_is_live() -> None:
    """A deliberately non-monotone predicate (the ladder closes the door) is a hard error."""
    def ladder_closes(held: frozenset[int]) -> bool:
        return Item.RAFT in held and Item.LADDER not in held
    with pytest.raises(NonMonotoneCheck) as failure:
        derive(ladder_closes, {Item.RAFT, Item.LADDER}, check="a planted check")
    assert failure.value.check == "a planted check"
    assert Item.LADDER in failure.value.larger and Item.LADDER not in failure.value.smaller


def test_conjoin_and_disjoin_minimize() -> None:
    assert conjoin(rule_of(RAFT), TRUE) == rule_of(RAFT)
    assert conjoin(rule_of(RAFT), FALSE) == FALSE
    assert conjoin(disjoin(rule_of(RAFT), rule_of(LADDER)), rule_of(RAFT)) == rule_of(RAFT)
    assert disjoin(rule_of(CountTerm(ARROW, 2)), rule_of(CountTerm(ARROW, 1))) == rule_of(CountTerm(ARROW, 1))
    assert rule_of(CountTerm(ARROW, 1), CountTerm(ARROW, 2)) == rule_of(CountTerm(ARROW, 2))
    with_take_any = rule_of(HeartsTerm(6, take_any=True))
    assert disjoin(with_take_any, rule_of(HeartsTerm(6))) == with_take_any
