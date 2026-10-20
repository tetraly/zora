"""Archipelago access rules from ZORA's LogicModel (zora.generate.logic), which ZORA derives from
its own walk. A rule is a set of clauses, any one of which is enough; a clause is a set of terms,
all of which must hold.

Items are counted under both of their names (names.ItemNaming): the ZORA name, which a start
inventory may give, and the name this seed uses in Archipelago (Sword Upgrade, Bomb Upgrade, ...).
With Progressive Items on, an item term naming a line item at grade g holds once the line counts g
(the game gives a line's next level for any of its codes); ZORA's model already counts lines
there, so this is a safety net.
"""
from collections.abc import Callable

from BaseClasses import CollectionState

from .names import HEART_CONTAINER, ItemNaming
from .zora.generate.logic import CountTerm, EventTerm, HeartsTerm, ItemTerm, Line, LogicModel, Rule, Term
from .zora.model.enums import Item
from .zora.model.item_names import ITEM_NAMES

StateRule = Callable[[CollectionState], bool]

TAKE_ANY_FREE = 2      # the take-any allowance counts max(0, k - 2) caves (check_magical_sword_hearts)


def names_of(items: frozenset[Item], naming: ItemNaming) -> set[str]:
    """Every name the items are held under: their ZORA names and this seed's Archipelago names."""
    zora = {ITEM_NAMES[item] for item in items}
    return zora | {naming.archipelago_name(name) for name in zora}


def line_count(line: Line, state: CollectionState, player: int, naming: ItemNaming) -> int:
    count = line.starting + sum(state.count(name, player) for name in names_of(line.items, naming))
    if line.ware_event is not None and state.has(line.ware_event, player):
        count += 1
    return count


def item_holds(item: Item, state: CollectionState, player: int, model: LogicModel, naming: ItemNaming) -> bool:
    name = ITEM_NAMES[item]
    graded = naming.line_of(name)
    if graded is None:
        return any(state.has(held, player) for held in names_of(frozenset({item}), naming))
    upgrade, grade = graded
    line = next((line for line in model.lines.values() if item in line.items), None)
    if line is not None:
        return line_count(line, state, player, naming) >= grade
    held = state.count(upgrade, player) + sum(state.count(other, player) for other in naming.members(upgrade))
    return held >= grade


def term_holds(term: Term, state: CollectionState, player: int, model: LogicModel,
               naming: ItemNaming = ItemNaming()) -> bool:
    if isinstance(term, ItemTerm):
        return item_holds(term.item, state, player, model, naming)
    if isinstance(term, EventTerm):
        return state.has(term.name, player)
    if isinstance(term, CountTerm):
        return line_count(model.lines[term.line], state, player, naming) >= term.count
    if isinstance(term, HeartsTerm):
        hearts = model.starting_hearts + state.count(HEART_CONTAINER, player)
        if term.take_any:
            taken = sum(1 for event in model.take_any_events if state.has(event, player))
            hearts += max(0, taken - TAKE_ANY_FREE)
        return hearts >= term.hearts
    raise TypeError(f"unknown logic term {term!r}")


def state_rule(rule: Rule, player: int, model: LogicModel, naming: ItemNaming = ItemNaming()) -> StateRule:
    clauses = [tuple(clause) for clause in rule]
    if any(not clause for clause in clauses):
        return lambda state: True

    def holds(state: CollectionState) -> bool:
        return any(all(term_holds(term, state, player, model, naming) for term in clause) for clause in clauses)

    return holds
