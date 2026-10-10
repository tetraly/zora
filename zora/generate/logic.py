"""Archipelago's access rules, generated from ZORA's own walk (Archipelago Phase 3, owner
refinement R1; docs/archipelago.md "Logic").

Archipelago places items itself, so it needs to know what a player must hold to reach each place.
These rules are not written by hand: each comes from a predicate of ZORA's acceptance check
(acceptance_check.AcceptanceCheck), evaluated on every subset of the few items it can depend on.
Every such predicate is monotone (more items never close a door), so its minimal true subsets
are the whole rule, in disjunctive form: any one clause, every term in it. AP seeds then get
exactly the guarantees ZORA seeds have.

A term is an item, an upgrade line's count (Progressive Items or Shop Items in the Item Pool), an
event (a triforce, level-9 entry, a maze's hint, ...), or a heart count.
"""
from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass, replace
from functools import partial
from typing import TYPE_CHECKING, Any

from ..model.enums import Destination, Item
from ..model.levels import GANON_LIST, LEVEL_9
from ..model.overworld import ItemCave
from .acceptance_check import (
    ARROW_LINE,
    CANDLE_LINE,
    DUNGEONS,
    HELD_FROM_START_SWORDS,
    LEVEL9_ENTRY,
    LINE_SHOP_WARES,
    LONG_ITEMS,
    ONE_ARROW,
    ONE_CANDLE,
    SWORD_LINE,
    SWORDS_FOR_LEVEL_9,
    TRIFORCES_NEEDED,
    TWO_ARROWS,
    AcceptanceCheck,
    LogicRules,
)
from .dungeon_walk import family_items, is_family_blocked
from .finish import tracked_place
from .places import Place, PlaceKind, major_pool
from .steps.item_shuffle_result import LETTER_SLOT, TrackedPlace
from .steps.overworld_gates import DEAD_WOODS_HINT, LOST_HILLS_HINT
from .steps.randomize_magical_sword import take_any_heart_allowance, take_any_heart_screens

if TYPE_CHECKING:
    from .pipeline import Built

# --- terms and rules ---------------------------------------------------------------------------

ARROW = "Arrow"
CANDLE = "Candle"
SWORD = "Sword"                   # ASNB: level-9 entry is Sword 4 (docs/design/asnb.md section 5)
MAGICAL_SWORD_CAVE_EVENT = "Magical Sword Cave"
LEVEL9_ENTRY_EVENT = "Level 9 Entry"


@dataclass(frozen=True)
class ItemTerm:
    """The item is held."""
    item: Item


@dataclass(frozen=True)
class CountTerm:
    """At least `count` of an upgrade line (PI-LOGIC-01): its items held, plus its vanilla shop
    ware's event when Shop Items in the Item Pool is off (LogicModel.lines)."""
    line: str
    count: int


@dataclass(frozen=True)
class EventTerm:
    """An event (LogicModel.events) is held."""
    name: str


@dataclass(frozen=True)
class HeartsTerm:
    """starting hearts + heart containers held (+ with `take_any`, the take-any allowance:
    max(0, k - 2) for k take-any heart events held) >= hearts. The sword caves' R2 condition."""
    hearts: int
    take_any: bool = False


Term = ItemTerm | CountTerm | EventTerm | HeartsTerm
Clause = frozenset[Term]
Rule = frozenset[Clause]          # any one clause, every term in it
TRUE: Rule = frozenset({frozenset()})
FALSE: Rule = frozenset()

# The acceptance check's pseudo-items (held-set codes below zero), as terms.
PSEUDO_TERMS: dict[int, Term] = {
    ONE_ARROW: CountTerm(ARROW, 1),
    TWO_ARROWS: CountTerm(ARROW, 2),
    ONE_CANDLE: CountTerm(CANDLE, 1),
    LEVEL9_ENTRY: EventTerm(LEVEL9_ENTRY_EVENT),
    LOST_HILLS_HINT: EventTerm("Lost Hills Hint"),
    DEAD_WOODS_HINT: EventTerm("Dead Woods Hint"),
}
# A pseudo-item that implies another: a count of two is a count of one. The subsets derive
# evaluates are closed under these, as every held set the closure builds is.
IMPLIED: dict[int, frozenset[int]] = {TWO_ARROWS: frozenset({ONE_ARROW})}


def term_of(code: int, named: Mapping[int, Term] = PSEUDO_TERMS) -> Term:
    """A held-set code (an item, or a pseudo-item) as a term."""
    return named[code] if code in named else ItemTerm(Item(code))


def implies(clause: Clause, term: Term) -> bool:
    """Whatever satisfies every term of `clause` satisfies `term`: it is in the clause, or a
    stronger count or heart term is."""
    if term in clause:
        return True
    if isinstance(term, CountTerm):
        return any(isinstance(other, CountTerm) and other.line == term.line and other.count >= term.count
                   for other in clause)
    if isinstance(term, HeartsTerm):
        # the take-any allowance only adds hearts, so a term without it is the stronger
        return any(isinstance(other, HeartsTerm) and other.hearts >= term.hearts
                   and (term.take_any or not other.take_any) for other in clause)
    return False


def simplified(clause: Iterable[Term]) -> Clause:
    """The clause without terms another of its terms implies."""
    terms = frozenset(clause)
    return frozenset(term for term in terms if not implies(terms - {term}, term))


def minimal(clauses: Iterable[Iterable[Term]]) -> Rule:
    """The rule of these clauses without a clause another one subsumes (one whose every term
    the other implies, so it is never needed)."""
    candidates = {simplified(clause) for clause in clauses}
    return frozenset(clause for clause in candidates
                     if not any(other != clause and all(implies(clause, term) for term in other)
                                for other in candidates))


def conjoin(*rules: Rule) -> Rule:
    """Every rule holds (AND)."""
    result = TRUE
    for rule in rules:
        result = minimal(left | right for left in result for right in rule)
    return result


def disjoin(*rules: Rule) -> Rule:
    """Any rule holds (OR)."""
    return minimal(clause for rule in rules for clause in rule)


def rule_of(*terms: Term) -> Rule:
    """One clause of these terms."""
    return frozenset({simplified(terms)})


# --- deriving a rule from ZORA's predicate (spec "Design" 2) ------------------------------------

class NonMonotoneCheck(AssertionError):
    """A ZORA check that turned False when an item was added. Archipelago's fill assumes
    monotone rules, so this is a hard error, never hidden."""

    def __init__(self, check: str, smaller: frozenset[int], larger: frozenset[int]) -> None:
        def names(held: frozenset[int]) -> list[str]:
            return sorted(str(term_of(code)) for code in held)
        super().__init__(f"{check}: True with {names(smaller)} but False with {names(larger)}")
        self.check, self.smaller, self.larger = check, smaller, larger


def _closed(held: Iterable[int], implied: Mapping[int, frozenset[int]]) -> frozenset[int]:
    codes = set(held)
    for code in list(codes):
        codes |= implied.get(code, frozenset())
    return frozenset(codes)


def derive(predicate: Callable[[frozenset[int]], bool], universe: Collection[int], check: str = "",
           always_held: frozenset[int] = frozenset({Item.WOOD_SWORD}),
           named: Mapping[int, Term] = PSEUDO_TERMS) -> Rule:
    """Phase 3 spec, Design 2: a ZORA predicate on held sets as a rule.

    1. Evaluate it on every subset of `universe` (closed under IMPLIED), each with the wooden
       sword, which the closure always holds.
    2. Assert monotonicity: adding an item never turns True into False (NonMonotoneCheck,
       naming the check and both sets).
    3. Keep the minimal true subsets, the rule's clauses, with the pseudo-items as terms
       (`named`: the codes that are not plain items).
    """
    codes = sorted(frozenset(universe) - always_held)
    implied = {code: IMPLIED[code] & frozenset(codes) for code in codes if code in IMPLIED}
    subsets = {_closed((code for bit, code in enumerate(codes) if mask >> bit & 1), implied)
               for mask in range(1 << len(codes))}
    verdicts = {subset: predicate(always_held | subset) for subset in subsets}
    for subset, verdict in verdicts.items():
        if not verdict:
            continue
        for code in codes:
            larger = _closed(subset | {code}, implied)
            if not verdicts[larger]:
                raise NonMonotoneCheck(check, subset, larger)
    return minimal(frozenset(term_of(code, named) for code in subset)
                   for subset, verdict in verdicts.items() if verdict)


# --- the model (spec "Design" 3) ----------------------------------------------------------------

TRIFORCE_LEVELS = range(1, TRIFORCES_NEEDED + 1)
GANON_EVENT = "Ganon"
LETTER_EVENT = "Letter"
ZELDA_EVENT = "Zelda"
LINE_NAMES = {ARROW_LINE: ARROW, CANDLE_LINE: CANDLE}


def triforce_event(level: int) -> str:
    return f"Level {level} Triforce"


def take_any_event(screen: int) -> str:
    """A take-any cave offering a heart container, by its screen (the magical-sword cave's heart
    rule counts them)."""
    return f"Take Any {screen:02X} Heart"


def ware_event(ware: Item) -> str:
    """A line's vanilla shop ware, counted once a door of a shop selling it is reached."""
    return f"{ware.name.replace('_', ' ').title()} Ware"


@dataclass(frozen=True)
class Line:
    """An upgrade line a CountTerm counts: its items, and (Shop Items in the Item Pool off) the
    event of its vanilla shop ware, which counts one more (PI-LOGIC-01). ASNB's Sword line: the
    swords held, `starting` for the wooden-sword cave's (never a place), and its ware_event the
    magical-sword cave's own sword while that cave keeps it (Randomize Magical Sword off)."""
    items: frozenset[Item]
    ware_event: str | None = None
    starting: int = 0


@dataclass(frozen=True)
class LogicModel:
    """What Archipelago needs to fill a ZORA world (docs/archipelago.md "Logic"): a rule for
    every place (by name) and event, the goal, the progression items, and what the count and
    heart terms read."""
    places: dict[str, Rule]
    events: dict[str, Rule]
    goal: Rule
    progression: frozenset[Item]
    starting_hearts: int
    lines: dict[str, Line]
    take_any_events: tuple[str, ...] = ()     # the events a HeartsTerm's take-any allowance counts


@dataclass(frozen=True)
class Universes:
    """The items each kind of check can depend on (spec "Design" 2), from the rules themselves."""
    screen: frozenset[int]          # a screen's entrance: every screen set's need
    entry: frozenset[int]           # a level's entry door, and level 9's long items and entry
    inside: frozenset[int]          # a dungeon walk: the family items and the ladder (its cache key)
    cave: frozenset[int]            # a cave or shop place: its screen, the coast's ladder, the letter

    @classmethod
    def of(cls, rules: LogicRules) -> Universes:
        screen = frozenset(need for _screens, need in rules.screen_needs)
        return cls(screen=screen, entry=screen | LONG_ITEMS | {LEVEL9_ENTRY},
                   inside=family_items(rules.family_lists) | {Item.LADDER},
                   cave=screen | {Item.LADDER, Item.LETTER})


def logic_model(built: Built) -> LogicModel:
    """Phase 3 spec, Design 3: every rule of a built seed, each derived from the acceptance
    check's own predicate on the built layout (none depends on where ZORA put the items)."""
    from .pipeline import extra_options
    extras = extra_options(built.plan)
    rules = extras.logic_rules
    world = built.world
    assert built.result.item_shuffle_result is not None and built.result.overworld is not None
    check = AcceptanceCheck(world.levels, built.result.item_shuffle_result, world.overworld,
                            built.result.overworld, rules)
    universes = Universes.of(rules)
    events: dict[str, Rule] = {}
    named = dict(PSEUDO_TERMS)
    if extras.shuffle_blue_potion and Item.LETTER not in major_pool(extras):
        # the potion shop's middle ware needs the letter, which stays in its own cave (Randomize
        # Letter off), where the closure collects it (a tracked record): an event, not an item to place
        named[Item.LETTER] = EventTerm(LETTER_EVENT)
        events[LETTER_EVENT] = derive(partial(check.collects, TrackedPlace(Item.LETTER, slot=LETTER_SLOT)),
                                      universes.cave, LETTER_EVENT)
    entry = {level: derive(partial(check.can_enter, level), universes.entry, f"Level {level} entry")
             for level in DUNGEONS}

    def place_rule(place: Place) -> Rule:
        return conjoin(reach_rule(place), *(rule_of(HeartsTerm(required.hearts, take_any=True))
                                            for required in place.requires))

    def reach_rule(place: Place) -> Rule:
        if place.level is not None and place.room_num is not None:
            reaches = check.can_reach_room if place.kind == PlaceKind.ROOM else check.reaches_cellar
            inside = derive(partial(reaches, place.level, place.room_num), universes.inside, place.name)
            return conjoin(entry[place.level], inside)
        # the item code is never read for a cave or shop slot
        return derive(partial(check.collects, tracked_place(place, Item.WOOD_SWORD)), universes.cave, place.name,
                      named=named)

    for level in TRIFORCE_LEVELS:
        events[triforce_event(level)] = conjoin(
            entry[level], derive(partial(check.completes, level), universes.inside, triforce_event(level)))
    lines = {LINE_NAMES[line]: Line(frozenset(Item(code) for code in line)) for line, _ware, _counts in LINE_SHOP_WARES}
    if rules.level_9_by_swords:
        # ASNB: level-9 entry is four swords (the closure's sword_count); the magical-sword cave's
        # own sword is an event with its cave's hearts (R2), as the game asks
        lines[SWORD] = Line(frozenset(Item(code) for code in SWORD_LINE), starting=HELD_FROM_START_SWORDS)
        if rules.magical_sword_cave_counts:
            cave = world.overworld.get_cave(Destination.MAGICAL_SWORD_CAVE, ItemCave)
            assert cave is not None
            hearts = cave.heart_requirement
            events[MAGICAL_SWORD_CAVE_EVENT] = conjoin(
                derive(partial(check.reaches_cave, Destination.MAGICAL_SWORD_CAVE), universes.screen,
                       MAGICAL_SWORD_CAVE_EVENT),
                rule_of(HeartsTerm(hearts, take_any=True)))
            lines[SWORD] = replace(lines[SWORD], ware_event=MAGICAL_SWORD_CAVE_EVENT)
        events[LEVEL9_ENTRY_EVENT] = rule_of(CountTerm(SWORD, SWORDS_FOR_LEVEL_9))
    else:
        events[LEVEL9_ENTRY_EVENT] = rule_of(*(EventTerm(triforce_event(level)) for level in TRIFORCE_LEVELS))
    for hint, hint_shop in rules.maze_hints:
        hint_event = PSEUDO_TERMS[hint]
        assert isinstance(hint_event, EventTerm)
        events[hint_event.name] = derive(partial(check.shop_door_reached, hint_shop), universes.screen,
                                         hint_event.name)
    if rules.counts_lines and rules.counts_shop_wares:
        for line, ware, _counts in LINE_SHOP_WARES:
            events[ware_event(ware)] = derive(partial(check.ware_door_reached, ware), universes.screen,
                                              ware_event(ware))
            lines[LINE_NAMES[line]] = replace(lines[LINE_NAMES[line]], ware_event=ware_event(ware))
    # The sword caves' hearts (R2): ZORA's heart check (check_magical_sword_hearts), which counts
    # the take-any allowance toward both caves; the game enforces them, and Archipelago moves heart
    # containers between worlds.
    take_any_events = tuple(take_any_event(screen) for screen in take_any_heart_screens(world.overworld))
    for screen, name in zip(take_any_heart_screens(world.overworld), take_any_events, strict=True):
        events[name] = derive(partial(check.reaches_screen, screen), universes.screen, name)
    # Ganon: level 9 entered (its door, the long items and level-9 entry) and his family list
    # unblocked (the bow and the silver arrows; two arrow upgrades under Progressive Items). His
    # room's reachability is E3's walk, Zelda's: the closure's family walk is not asked to reach
    # it, and in some accepted seeds it does not (its entry sides).
    level9 = next(level for level in world.levels if level.level_num == LEVEL_9)
    ganon_room = next(room for room in level9.rooms if room.enemy == GANON_LIST)

    def defeats_ganon(held: frozenset[int]) -> bool:
        return not is_family_blocked(ganon_room, held, rules.family_lists)
    events[GANON_EVENT] = conjoin(entry[LEVEL_9], derive(defeats_ganon, universes.inside, GANON_EVENT))
    # Zelda: E3 (VA-REJ-09), a walk on the layout alone, and Ganon.
    events[ZELDA_EVENT] = conjoin(TRUE if check.is_zelda_reachable() else FALSE, rule_of(EventTerm(GANON_EVENT)))
    places = {place.name: place_rule(place) for place in built.places}
    return LogicModel(places=places, events=events, goal=rule_of(EventTerm(ZELDA_EVENT)),
                      progression=progression(places, events, lines, major_pool(extras)),
                      starting_hearts=extras.starting_heart_containers, lines=lines,
                      take_any_events=take_any_events)


def progression(places: Mapping[str, Rule], events: Mapping[str, Rule], lines: Mapping[str, Line],
                pool: frozenset[Item]) -> frozenset[Item]:
    """Every item a term names (a count term: its line's items), plus heart containers (the
    heart terms) and the letter while it is in the pool (the potion shop; spec "Design" 3)."""
    items = {Item.HEART_CONTAINER} | ({Item.LETTER} & pool)
    for rule in (*places.values(), *events.values()):
        for clause in rule:
            for term in clause:
                if isinstance(term, ItemTerm):
                    items.add(term.item)
                elif isinstance(term, CountTerm):
                    items |= lines[term.line].items
    return frozenset(items)


# --- a reference evaluator (spec "Design" 4) ------------------------------------------------------

@dataclass
class Swept:
    """sweep's fixed point: the places collected and the events held."""
    places: set[str]
    events: set[str]
    items: Counter[Item]

    @property
    def reaches_goal(self) -> bool:
        return ZELDA_EVENT in self.events

    def holds(self, model: LogicModel, term: Term) -> bool:
        """The term holds at the fixed point."""
        return _State(model, self.items, self.events).holds(term)


@dataclass
class _State:
    model: LogicModel
    items: Counter[Item]
    events: set[str]

    def count(self, line: str) -> int:
        spec = self.model.lines[line]
        return (spec.starting + sum(self.items[item] for item in spec.items)
                + (spec.ware_event is not None and spec.ware_event in self.events))

    def hearts(self, take_any: bool) -> int:
        hearts = self.model.starting_hearts + self.items[Item.HEART_CONTAINER]
        if take_any:
            held = sum(name in self.events for name in self.model.take_any_events)
            hearts += take_any_heart_allowance(held)
        return hearts

    def holds(self, term: Term) -> bool:
        if isinstance(term, ItemTerm):
            return self.items[term.item] > 0
        if isinstance(term, CountTerm):
            return self.count(term.line) >= term.count
        if isinstance(term, EventTerm):
            return term.name in self.events
        return self.hearts(term.take_any) >= term.hearts

    def satisfies(self, rule: Rule) -> bool:
        return any(all(self.holds(term) for term in clause) for clause in rule)


def sweep(model: LogicModel, assignment: Mapping[str, Item | object], received: Iterable[Item] = ()) -> Swept:
    """The fixed point over the model's rules with an assignment (place name -> item; anything
    else, as another player's item, gives nothing) and the items received from other worlds:
    the Archipelago-style counterpart of AcceptanceCheck.closure()."""
    state = _State(model, Counter(received), set())
    collected: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, rule in model.places.items():
            if name not in collected and state.satisfies(rule):
                collected.add(name)
                if isinstance(item := assignment.get(name), Item):
                    state.items[item] += 1
                changed = True
        for name, rule in model.events.items():
            if name not in state.events and state.satisfies(rule):
                state.events.add(name)
                changed = True
    return Swept(collected, state.events, state.items)


# --- JSON (spec "Design" 5) ---------------------------------------------------------------------

JsonTerm = dict[str, str | int | bool]


def term_to_json(term: Term) -> JsonTerm:
    """A term by name: {"item": "RAFT"}, {"count": "Arrow", "at_least": 2}, {"event": ...},
    {"hearts": 6, "take_any": true}."""
    if isinstance(term, ItemTerm):
        return {"item": term.item.name}
    if isinstance(term, CountTerm):
        return {"count": term.line, "at_least": term.count}
    if isinstance(term, EventTerm):
        return {"event": term.name}
    return {"hearts": term.hearts, "take_any": term.take_any}


def term_from_json(data: Mapping[str, str | int | bool]) -> Term:
    if "item" in data:
        return ItemTerm(Item[str(data["item"])])
    if "count" in data:
        return CountTerm(str(data["count"]), int(data["at_least"]))
    if "event" in data:
        return EventTerm(str(data["event"]))
    return HeartsTerm(int(data["hearts"]), bool(data["take_any"]))


def _sort_key(data: object) -> str:
    return json.dumps(data, sort_keys=True)


def rule_to_json(rule: Rule) -> list[list[JsonTerm]]:
    """A rule as a list of clauses, each a list of terms, in a fixed order."""
    clauses = [sorted((term_to_json(term) for term in clause), key=_sort_key) for clause in rule]
    return sorted(clauses, key=_sort_key)


def rule_from_json(data: Iterable[Iterable[Mapping[str, str | int | bool]]]) -> Rule:
    return frozenset(frozenset(term_from_json(term) for term in clause) for clause in data)


def model_to_json(model: LogicModel) -> dict[str, object]:
    """The model as plain JSON data (items and terms by name), for the AP world's slot data."""
    return {
        "places": {name: rule_to_json(rule) for name, rule in model.places.items()},
        "events": {name: rule_to_json(rule) for name, rule in model.events.items()},
        "goal": rule_to_json(model.goal),
        "progression": sorted(item.name for item in model.progression),
        "starting_hearts": model.starting_hearts,
        "lines": {name: {"items": sorted(item.name for item in line.items), "ware_event": line.ware_event,
                         "starting": line.starting}
                  for name, line in model.lines.items()},
        "take_any_events": list(model.take_any_events),
    }


def model_from_json(data: Mapping[str, Any]) -> LogicModel:
    return LogicModel(
        places={name: rule_from_json(rule) for name, rule in data["places"].items()},
        events={name: rule_from_json(rule) for name, rule in data["events"].items()},
        goal=rule_from_json(data["goal"]),
        progression=frozenset(Item[name] for name in data["progression"]),
        starting_hearts=int(data["starting_hearts"]),
        lines={name: Line(frozenset(Item[item] for item in line["items"]), line["ware_event"],
                          int(line.get("starting", 0)))
               for name, line in data["lines"].items()},
        take_any_events=tuple(data["take_any_events"]),
    )
