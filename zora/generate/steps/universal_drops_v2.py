"""Universal Drops v2.0 (ZORA extra, beta; owner rulings 2026-11-05; docs/zora-extras.md section 26):
universal drops whose counts and positions feel like the dungeons before Allow
Universal Drops In Shapes (B91), the research of docs/reports/research-universal-drops-balance.md.

It runs at the end of the shape stage, on each shaped level, before the post-shapes passes (so before
Shuffle Minor Dungeon Drops' deal, B17, which then runs unchanged: ruling 6):

1. Drop counts: the shape stage has run with B91's rows off (the two are never on together, ruling 2),
   so each level's bombs, five rupees and keys are the pre-Universal Drops counts (ruling 3).
2. The level's four positions: the center ($89), kept at the index it already has (item cellars point
   at it), and three drawn uniformly among the triples of CANDIDATE_SQUARES that give every room able
   to hold an item at least one of the four on its drop squares (ruling 4; drop_squares.py).
3. The drops are dealt over the rooms that can take one: only the item moves, never the room's
   dark and boss-sound bits; person rooms, the hungry Goriya's, Zelda's and Ganon's rooms, the
   entrance, a room whose trigger shows or hides its item, and a room holding anything else keep what
   they hold (ruling 7).
4. Every room able to seat one of the four takes a position its drop squares hold: when they hold the
   center, the center half the time (CENTER_WEIGHT_PERCENT) and otherwise a uniformly drawn one of the
   four they hold, the center included (ruling 2026-11-06); else a uniformly drawn one they hold. Rooms
   with no item take a position too, so an item a later pass moves in (Shuffle Dungeon Drops, B15, moves
   whole item bytes and leaves positions) stands on a drop square; the finished-world check
   (drop_squares.check_drop_squares) restarts any attempt that still has one off its squares (ruling 5)."""
from __future__ import annotations

from itertools import combinations

from ...model.enums import Enemy, Item, ItemPosition, RoomAction
from ...model.levels import Level
from ...model.rooms import Room
from ..drop_squares import drop_squares
from ..errors import GenerationFailure
from ..rng import IntRng
from ..shapes.t5_positions import T5_BASE, T5_UNIVERSAL, t5_row

CENTER = 0x89
# The three other positions come from T5's squares and the six wall-middle squares (ruling 4): the top
# row's two middle squares, the west and east walls' middle squares, the bottom row's two.
WALL_MIDDLES = frozenset({0x76, 0x86, 0x29, 0xD9, 0x7C, 0x8C})
T5_SQUARES = frozenset(square for screen_type in set(T5_BASE) | set(T5_UNIVERSAL)
                       for square in t5_row(screen_type, True))
CANDIDATE_SQUARES = tuple(sorted((T5_SQUARES | WALL_MIDDLES) - {CENTER}))
TRIPLES = tuple(combinations(CANDIDATE_SQUARES, 3))
POSITIONS = tuple(ItemPosition)
MINOR_DROPS = frozenset({Item.BOMBS, Item.FIVE_RUPEES, Item.KEY})
# Rooms that keep what they hold (ruling 7): the people and the special rooms' monsters, and the
# triggers tied to the room's item (ALL_DEAD_ITEM shows it when the room is cleared, Gatekeeper bug 1;
# LAST_BOSS hides it at load)
KEPT_MONSTERS = frozenset({Enemy.HUNGRY_GORIYA, Enemy.THE_KIDNAPPED, Enemy.THE_BEAST})
ITEM_TRIGGERS = frozenset({RoomAction.ALL_DEAD_ITEM, RoomAction.LAST_BOSS, RoomAction.MONEY_OR_LIFE})
# The share of center-seating rooms that take the center outright (ruling 2026-11-06); the rest draw
# uniformly among the room's valid positions, the center included
CENTER_WEIGHT_PERCENT = 50
PERCENT = 100
NO_COVER_FAILURE = "Universal Drops v2.0: no three positions give every item room a drop square"


def balance_level(level: Level, rng: IntRng) -> None:
    """Steps 2-4 for one shaped level."""
    rooms = level.rooms
    dealt = [room for room in rooms if takes_drops(level, room) and drop_squares(room.layout_code)]
    holding = [room for room in rooms if room.item != Item.NOTHING]
    four = choose_positions(level, [room.layout_code for room in [*dealt, *holding]], rng)
    level.item_position_table[:] = four
    deal_drops(dealt, rng)
    for room in rooms:
        place_on_drop_square(level, room, rng)


def takes_drops(level: Level, room: Room) -> bool:
    """A room the drops are dealt over: empty or holding a drop, and none of ruling 7's exceptions."""
    return ((room.item == Item.NOTHING or room.item in MINOR_DROPS)
            and room.room_num != level.entrance_room
            and not room.is_person
            and room.enemy not in KEPT_MONSTERS
            and room.room_action not in ITEM_TRIGGERS)


def choose_positions(level: Level, covered_types: list[int], rng: IntRng) -> list[int]:
    """Step 2: the center at its index, and the first qualifying triple after a uniform draw (ruling 4's
    coverage rule) in the other three. Screen types with no square among the candidates hold no item
    and are left out of the rule."""
    reachable = (*CANDIDATE_SQUARES, CENTER)
    needed = [squares for squares in {drop_squares(code) for code in covered_types}
              if squares.intersection(reachable)]
    qualifying = [triple for triple in TRIPLES
                  if all(squares.intersection((CENTER, *triple)) for squares in needed)]
    if not qualifying:
        raise GenerationFailure(NO_COVER_FAILURE)
    others = list(qualifying[rng.below(len(qualifying))])
    table = level.item_position_table
    center_index = table.index(CENTER)
    return [CENTER if index == center_index else others.pop(0) for index in range(len(table))]


def deal_drops(dealt: list[Room], rng: IntRng) -> None:
    """Step 3: the drops these rooms hold, dealt uniformly over them (a Fisher-Yates walk); only the item
    moves. Every drop comes from one of these rooms, so there are never more drops than rooms."""
    items = [room.item for room in dealt]
    rng.shuffle(items)
    for room, item in zip(dealt, items, strict=True):
        room.item = item


def place_on_drop_square(level: Level, room: Room, rng: IntRng) -> None:
    """Step 4: when the room's drop squares hold the center, the center CENTER_WEIGHT_PERCENT of the time and
    otherwise a uniformly drawn position of the four they hold, the center included (ruling 2026-11-06);
    else a uniformly drawn position they hold. A room whose squares hold none of the four keeps its index
    (it holds no item, or the finished-world check restarts the attempt)."""
    squares = drop_squares(room.layout_code)
    table = level.item_position_table
    valid = [index for index, square in enumerate(table) if square in squares]
    if not valid:
        return
    if CENTER in squares and rng.below(PERCENT) < CENTER_WEIGHT_PERCENT:
        room.item_position = POSITIONS[table.index(CENTER)]
        return
    room.item_position = POSITIONS[valid[rng.below(len(valid))]]


def balance_drops(levels: list[Level], rng: IntRng) -> None:
    """The step: each shaped level in level order."""
    for level in sorted(levels, key=lambda level: level.level_num):
        balance_level(level, rng)
