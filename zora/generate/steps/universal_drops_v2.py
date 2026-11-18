"""Universal Drops v2.0 (ZORA extra, beta; owner rulings 2026-11-05; docs/zora-extras.md section 26):
universal drops whose counts and positions feel like the dungeons before Allow
Universal Drops In Shapes (B91), the research of docs/reports/research-universal-drops-balance.md.

It runs at the end of the shape stage, on each shaped level, before the post-shapes passes (so before
Shuffle Minor Dungeon Drops' deal, B17, which then runs unchanged: ruling 6):

1. Drop counts: the shape stage has run with B91's rows off (the two are never on together, ruling 2),
   so each level's bombs, five rupees and keys are the pre-Universal Drops counts (ruling 3).
2. The level's four positions: the center ($89), kept at the index it already has (item cellars point
   at it), and three drawn uniformly among the triples of CANDIDATE_SQUARES that give every room able
   to hold an item at least one of the four on its drop squares (ruling 4; drop_squares.py). The
   candidates are T5's squares: never a door square (the two middle squares of the top and bottom rows,
   the middle row's end squares), so Link never walks onto a drop entering a room, nor has to take it to
   leave (CustomShield's report on 2.0.1).
3. The drops are dealt over the rooms that can take one: only the item moves, never the room's
   dark and boss-sound bits; person rooms, the hungry Goriya's, Zelda's and Ganon's rooms, the
   entrance, a room whose trigger shows or hides its item, and a room holding anything else keep what
   they hold (ruling 7).
4. Every room able to seat one of the four takes a position its drop squares hold. The center is the
   Triforce rooms' alone (CustomShield's report on 2.0.1; it replaces ruling 2026-11-06's center half the
   time): a room holding a Triforce piece takes the center when its squares hold it, and every other room
   a uniformly drawn one of the other three its squares hold. Rooms
   with no item take a position too, so an item a later pass moves in (Shuffle Dungeon Drops, B15, moves
   whole item bytes and leaves positions) stands on a drop square; the finished-world check
   (drop_squares.check_drop_squares) restarts any attempt that still has one off its squares (ruling 5)."""
from __future__ import annotations

from collections.abc import Sequence
from itertools import combinations

from ...model.enums import Enemy, Item, ItemPosition, RoomAction
from ...model.levels import Level
from ...model.rooms import Room
from ..drop_squares import drop_squares, is_drop_square
from ..errors import GenerationFailure
from ..rng import IntRng
from ..shapes.t5_positions import T5_BASE, T5_UNIVERSAL, t5_row

CENTER = 0x89
# The door squares, where Link stands as he enters through a door: the top and bottom rows' two middle
# squares and the middle row's west and east end squares. No drop stands on one, so entering a room never
# takes its drop and leaving never needs it taken (CustomShield's report on 2.0.1; ruling 4 had added them)
DOOR_SQUARES = frozenset({0x76, 0x86, 0x29, 0xD9, 0x7C, 0x8C})
T5_SQUARES = frozenset(square for screen_type in set(T5_BASE) | set(T5_UNIVERSAL)
                       for square in t5_row(screen_type, True))
# The three other positions come from T5's squares, the door squares aside
CANDIDATE_SQUARES = tuple(sorted(T5_SQUARES - DOOR_SQUARES - {CENTER}))
TRIPLES = tuple(combinations(CANDIDATE_SQUARES, 3))
POSITIONS = tuple(ItemPosition)
MINOR_DROPS = frozenset({Item.BOMBS, Item.FIVE_RUPEES, Item.KEY})
# Rooms that keep what they hold (ruling 7): the people and the special rooms' monsters, and the
# triggers tied to the room's item (ALL_DEAD_ITEM shows it when the room is cleared, Gatekeeper bug 1;
# LAST_BOSS hides it at load)
KEPT_MONSTERS = frozenset({Enemy.HUNGRY_GORIYA, Enemy.THE_KIDNAPPED, Enemy.THE_BEAST})
ITEM_TRIGGERS = frozenset({RoomAction.ALL_DEAD_ITEM, RoomAction.LAST_BOSS, RoomAction.MONEY_OR_LIFE})
NO_COVER_FAILURE = "Universal Drops v2.0: no three positions give every item room a drop square"
CENTER_FAILURE = "Universal Drops v2.0: an item other than a Triforce piece at the center"


def balance_level(level: Level, rng: IntRng) -> None:
    """Steps 2-4 for one shaped level."""
    rooms = level.rooms
    dealt = [room for room in rooms if takes_drops(level, room) and drop_squares(room.layout_code)]
    holding = [room for room in rooms if room.item != Item.NOTHING]
    four = choose_positions(level, [room.layout_code for room in [*dealt, *holding] if not is_triforce_room(room)],
                            rng, [room.layout_code for room in holding if is_triforce_room(room)])
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


def is_triforce_room(room: Room) -> bool:
    """A room holding a Triforce piece: the only rooms that take the center."""
    return room.item == Item.TRIFORCE


def is_off_center_drop_square(layout_code: int, square: int) -> bool:
    """A drop square of the screen type other than the center, which only Triforce rooms take: the square rule
    for an item placed after the shape stage (Add L4 Sword's)."""
    return square != CENTER and is_drop_square(layout_code, square)


def choose_positions(level: Level, covered_types: list[int], rng: IntRng,
                     triforce_types: Sequence[int] = ()) -> list[int]:
    """Step 2: the center at its index, and the first qualifying triple after a uniform draw (ruling 4's
    coverage rule) in the other three: every room but a Triforce room needs one of the triple, a
    Triforce room (`triforce_types`) the center or one of the triple. Screen types with no square among
    the candidates hold no item and are left out of the rule."""
    needed: list[tuple[frozenset[int], tuple[int, ...]]] = [
        (squares, ()) for squares in {drop_squares(code) for code in covered_types}
        if squares.intersection(CANDIDATE_SQUARES)]
    needed += [(squares, (CENTER,)) for squares in {drop_squares(code) for code in triforce_types}
               if squares.intersection((*CANDIDATE_SQUARES, CENTER))]
    qualifying = [triple for triple in TRIPLES
                  if all(squares.intersection((*center, *triple)) for squares, center in needed)]
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
    """Step 4: a Triforce room the center when its drop squares hold it; every other room a uniformly
    drawn position of the other three its squares hold (a Triforce room too, when they leave out the
    center). A room whose squares hold none it may take keeps its index (it holds no item, or the
    finished-world check restarts the attempt)."""
    squares = drop_squares(room.layout_code)
    table = level.item_position_table
    if is_triforce_room(room) and CENTER in squares:
        room.item_position = POSITIONS[table.index(CENTER)]
        return
    valid = [index for index, square in enumerate(table) if square in squares and square != CENTER]
    if valid:
        room.item_position = POSITIONS[valid[rng.below(len(valid))]]


def balance_drops(levels: list[Level], rng: IntRng) -> None:
    """The step: each shaped level in level order."""
    for level in sorted(levels, key=lambda level: level.level_num):
        balance_level(level, rng)


def seat_triforces_at_the_center(levels: list[Level], rng: IntRng) -> None:
    """After every step that moves items (the Triforces trade places, the item shuffles and the room exchange
    move items and leave positions with the rooms): in each shaped level, a Triforce room takes the center
    when its squares hold it, and any other item at the center draws again among the other three its squares
    hold; one that has none restarts the attempt (CENTER_FAILURE). Ganon's room is left alone: the Triforce of
    Power drops at his ashes."""
    for level in sorted(levels, key=lambda level: level.level_num):
        table = level.item_position_table
        for room in level.rooms:
            if room.item in (Item.NOTHING, Item.TRIFORCE_OF_POWER) or room.enemy == Enemy.THE_BEAST:
                continue
            at_center = table[room.item_position] == CENTER
            if is_triforce_room(room) != at_center:
                place_on_drop_square(level, room, rng)
            if not is_triforce_room(room) and table[room.item_position] == CENTER:
                raise GenerationFailure(f"{CENTER_FAILURE} (level {level.level_num} room ${room.room_num:02X})")
