"""Archipelago access rules from ZORA's LogicModel (zora.generate.logic), which ZORA derives from
its own walk. A rule is a set of clauses, any one of which is enough; a clause is a set of terms,
all of which must hold.
"""
from collections.abc import Callable

from BaseClasses import CollectionState

from .names import HEART_CONTAINER
from .zora.generate.logic import CountTerm, EventTerm, HeartsTerm, ItemTerm, LogicModel, Rule, Term
from .zora.model.item_names import ITEM_NAMES

StateRule = Callable[[CollectionState], bool]

TAKE_ANY_FREE = 2      # the take-any allowance counts max(0, k - 2) caves (check_magical_sword_hearts)


def term_holds(term: Term, state: CollectionState, player: int, model: LogicModel) -> bool:
    if isinstance(term, ItemTerm):
        return state.has(ITEM_NAMES[term.item], player)
    if isinstance(term, EventTerm):
        return state.has(term.name, player)
    if isinstance(term, CountTerm):
        line = model.lines[term.line]
        count = line.starting + sum(state.count(ITEM_NAMES[item], player) for item in line.items)
        if line.ware_event is not None and state.has(line.ware_event, player):
            count += 1
        return count >= term.count
    if isinstance(term, HeartsTerm):
        hearts = model.starting_hearts + state.count(HEART_CONTAINER, player)
        if term.take_any:
            taken = sum(1 for event in model.take_any_events if state.has(event, player))
            hearts += max(0, taken - TAKE_ANY_FREE)
        return hearts >= term.hearts
    raise TypeError(f"unknown logic term {term!r}")


def state_rule(rule: Rule, player: int, model: LogicModel) -> StateRule:
    clauses = [tuple(clause) for clause in rule]
    if any(not clause for clause in clauses):
        return lambda state: True

    def holds(state: CollectionState) -> bool:
        return any(all(term_holds(term, state, player, model) for term in clause) for clause in clauses)

    return holds
