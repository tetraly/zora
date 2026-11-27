"""The world's item classes and where filler may go (design of 2026-11-23; docs/archipelago.md "Item
classes and filler spots").

The classes are the same in every seed:
- progression: the ladder, power bracelet, bow, both arrows, letter, heart containers, Triforces,
  raft and recorder, and one candle, one sword and one ring: the first copy of the Blue Candle,
  White Sword and Blue Ring's Archipelago names (with Progressive Items, one Candle, Sword and Ring
  Upgrade; both Arrow Upgrades, as both arrows are progression);
- filler: Bombs, 5 Rupees and Key;
- useful: every other item.
Whatever the seed's logic counts is progression too, as many copies as it counts (progression_copies),
so ZORA's sanity check never refuses what Archipelago placed. Where one name has copies in two classes
(two Sword Upgrades, one progression and one useful), each copy carries its own class: Archipelago's
state counts only the progression copies (World.collect_item), which are as many as any rule asks.

A minor place (Shuffle Minor Dungeon Drops' filler spot) takes only a filler-class item, this world's or
another's; every other place takes anything but this world's own Bombs, 5 Rupees and Keys. So the Item
Counter, which counts every place but the minor ones, never counts a spot holding this world's filler.
"""
from collections import Counter
from collections.abc import Iterable, Iterator

from BaseClasses import Item, ItemClassification

from .names import HEART_CONTAINER, KEY, ItemNaming
from .zora.generate.logic import CountTerm, HeartsTerm, ItemTerm, LogicModel, Term
from .zora.model.level_items import ALL_LEVEL_ITEM_NAMES

TRIFORCE_NAMES = frozenset(name for name in ALL_LEVEL_ITEM_NAMES if name.endswith(" Triforce"))
# Every copy is progression (ZORA names; with Progressive Items both arrows are Arrow Upgrades)
PROGRESSION_ITEMS = frozenset({"Ladder", "Power Bracelet", "Bow", "Wooden Arrow", "Silver Arrow", "Letter",
                               HEART_CONTAINER, "Raft", "Recorder"}) | TRIFORCE_NAMES
# One copy of each is progression: one sword, one candle, one ring (with Progressive Items, one Upgrade of each)
ONE_COPY_ITEMS = ("White Sword", "Blue Candle", "Blue Ring")
FILLER_ITEMS = frozenset({"Bombs", "5 Rupees", KEY})


def terms(model: LogicModel) -> Iterator[Term]:
    for rule in (*model.places.values(), *model.events.values(), model.goal):
        for clause in rule:
            yield from clause


def logic_needs(model: LogicModel, naming: ItemNaming) -> tuple[Counter[str], list[tuple[list[str], int]]]:
    """What the seed's logic counts, by Archipelago name: the copies of each name some rule asks for, and each
    count of a line whose items have names of their own (Progressive Items off) as (its names, lowest grade
    first; the count past the line's starting items), any of which counts."""
    needed: Counter[str] = Counter()
    lines: list[tuple[list[str], int]] = []
    line_of = {item: line for line in model.lines.values() for item in line.items}

    def at_least(name: str, count: int) -> None:
        needed[name] = max(needed[name], count)

    for term in terms(model):
        if isinstance(term, ItemTerm):
            name = naming.zora_name(term.item)
            graded = naming.line_of(name)
            if graded is None:
                at_least(naming.archipelago_name(name), 1)
            else:                       # a line's grade g: g of its upgrades (rules.item_holds)
                upgrade, grade = graded
                line = line_of.get(term.item)
                at_least(upgrade, grade - (line.starting if line else 0))
        elif isinstance(term, CountTerm):
            line = model.lines[term.line]
            names = list(dict.fromkeys(naming.archipelago_name(naming.zora_name(item)) for item in sorted(line.items)))
            if len(names) == 1:
                at_least(names[0], term.count - line.starting)
            else:
                lines.append((names, term.count - line.starting))
        elif isinstance(term, HeartsTerm):
            at_least(HEART_CONTAINER, term.hearts - model.starting_hearts)
    return needed, lines


def progression_copies(pool: Iterable[str], model: LogicModel, naming: ItemNaming) -> Counter[str]:
    """How many copies of each Archipelago name in the pool (ZORA's names, `pool`) are progression: the fixed
    classes' copies, raised to what the seed's logic counts."""
    pooled = Counter(naming.archipelago_name(name) for name in pool)
    copies: Counter[str] = Counter()
    for name in PROGRESSION_ITEMS:
        renamed = naming.archipelago_name(name)
        copies[renamed] = pooled[renamed]
    for name in ONE_COPY_ITEMS:
        renamed = naming.archipelago_name(name)
        copies[renamed] = max(copies[renamed], min(1, pooled[renamed]))
    needed, lines = logic_needs(model, naming)
    for name, count in needed.items():
        copies[name] = max(copies[name], min(count, pooled[name]))
    for names, count in lines:
        missing = count - sum(copies[name] for name in names)
        for name in names:              # lowest grade first
            if missing <= 0:
                break
            added = min(missing, pooled[name] - copies[name])
            copies[name] += added
            missing -= added
    return +copies


def base_class(name: str) -> ItemClassification:
    """A copy's class when it is not one of its name's progression copies."""
    return ItemClassification.filler if name in FILLER_ITEMS else ItemClassification.useful


def pool_classes(pool: Iterable[str], copies: Counter[str]) -> list[ItemClassification]:
    """Each copy's class, for the pool's Archipelago names in order: a name's first copies are its progression
    copies, the rest its base class."""
    given: Counter[str] = Counter()
    classes = []
    for name in pool:
        given[name] += 1
        classes.append(ItemClassification.progression if given[name] <= copies[name] else base_class(name))
    return classes


def is_filler(item: Item) -> bool:
    """A filler-class item, any world's (a trap counts as filler, as foreign_value takes it)."""
    return not item.advancement and not item.useful


def is_own_filler(item: Item, player: int) -> bool:
    return item.player == player and item.name in FILLER_ITEMS
