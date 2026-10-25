"""Gatekeeper Bosses (ZORA extra, owner 2026-10-24; docs/zora-extras.md section 19; the design and its
measurements: docs/reports/research-gatekeeper-bosses.md).

In each level 1-8 one room, the gatekeeper, holds the level's boss and is the only way from the start
into the part of the level holding the triforce (the gated part). Its sides into that part are
shutters on trigger 7, so they open when the boss falls, and the room's item (the heart container, or
what the item shuffle put in its place) appears on the kill (CheckUnderworldSecrets). The compass
stays in front of the gatekeeper.

Built on a level the late gate has just accepted (gate._attempt), or, when the gate does not run
(VA-REJ-02), on the levels as they stand. One try:
  1. draw the boss to move and the gated part's size by the setting;
  2. grow the part from the triforce's room, room by room, until it is that size and a room the boss
     may stand in borders it: that room is the gatekeeper;
  3. take in the far end of every transport staircase with one end in the part, and every room the
     part cuts off from the start;
  4. seal: each side between the part and the rest becomes a wall, both ways, except the gatekeeper's
     sides into the part, which become shutters;
  5. reconnect each side by opening walled pairs that do not cross the cut, until the late gate's
     connectivity walk passes again;
  6. check the cut (gated_part): with the gatekeeper a dead end, the door graph reaches the compass but
     not the triforce;
  7. move the boss's monsters and the heart container's place's item into the gatekeeper, on trigger 7.
A failed try restores the level's rooms; when every try fails the gate rejects the attempt and deals
the level again."""
from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass, field

from ...flags.zora_flags import GatekeeperBosses
from ...model import room_grid
from ...model.enums import Enemy, Item, RoomAction, RoomType, Side
from ...model.levels import Level
from ...model.rooms import Room, SecretInfo
from ..dungeon_walk import item_cellar, item_code, item_room
from ..item_spots import item_spot_positions
from ..rng import Rng
from ..shapes.world import D_BOMB, D_OPEN, D_SHUTTER, D_WALL, set_side, side_of
from ..steps.randomize_boss_groups import is_boss_pick_barred
from .walk import State, WalkResult, build_graph, connectivity_walk

GATEKEEPER_LEVELS = range(1, 9)
# The bosses a gatekeeper may hold: every boss ZORA's boss shuffles may leave in levels 1-8 (owner
# decision 4), Ganon, the hungry Goriya and the people aside.
GATEKEEPER_BOSSES = frozenset({
    Enemy.AQUAMENTUS, Enemy.SINGLE_DODONGO, Enemy.TRIPLE_DODONGO, Enemy.MANHANDLA,
    Enemy.GLEEOK_1, Enemy.GLEEOK_2, Enemy.GLEEOK_3, Enemy.GLEEOK_4,
    Enemy.SINGLE_DIGDOGGER, Enemy.TRIPLE_DIGDOGGER, Enemy.BLUE_GOHMA, Enemy.RED_GOHMA,
    Enemy.PATRA_1, Enemy.PATRA_2, Enemy.MOLDORM, Enemy.RED_LANMOLA, Enemy.BLUE_LANMOLA,
})
# Triggers a gatekeeper never takes: its stairs or Ganon's shutters would stop working
BARRED_TRIGGERS = frozenset({RoomAction.BLOCK_STAIRS, RoomAction.LAST_BOSS, RoomAction.MONEY_OR_LIFE})
# Tries per accepted attempt before the gate deals the level again. Early's large parts fail more
# often (more crossings to seal and transports to take in), so it tries longer.
TRIES = {GatekeeperBosses.ANYWHERE: 6, GatekeeperBosses.LATE: 6, GatekeeperBosses.EARLY: 12}
# Without the gate (VA-REJ-02) the level is never dealt again: tries before the generation restarts
TRIES_WITHOUT_GATE = 50
# The items the compass may trade places with to come in front of the gatekeeper (no tracked item)
SMALL_ITEMS = frozenset({Item.NOTHING, Item.KEY, Item.BOMBS, Item.FIVE_RUPEES, Item.MAP})
# Early: grow to at least this share of the level's other rooms behind the gatekeeper
EARLY_SHARE = 2 / 3
# The share of the level's other rooms behind the gatekeeper each setting accepts: a try outside it
# fails, so the gate deals the level again. Early wants a large part (at least half), Late a small one
# (at most a quarter): a triforce room that alone leads to a large area would put all of it behind the
# gatekeeper. Measured, Late's cap costs no attempts on average (docs/zora-extras.md section 19).
SHARE_ACCEPTED = {GatekeeperBosses.ANYWHERE: (0.0, 1.0), GatekeeperBosses.LATE: (0.0, 1 / 4),
                  GatekeeperBosses.EARLY: (1 / 2, 1.0)}
# The connectivity repair's opening, as the gate's (VA-REJ-01.2): north-south bombable one time in three
BOMBABLE_CHANCE = (1, 3)


@dataclass
class GatekeeperPlan:
    """The setting, and each level's item for the gatekeeper: what the item shuffle left in the room
    that held the level's heart container before it (heart_place_items)."""
    setting: GatekeeperBosses
    heart_place_items: dict[int, Item] = field(default_factory=dict)


def heart_place_rooms(levels: list[Level]) -> dict[int, Room]:
    """Each level 1-8's heart-container room before the item shuffle: its first room holding one."""
    places = {}
    for level in levels:
        heart_room = next((room for room in level.rooms if room.item == Item.HEART_CONTAINER), None)
        if level.level_num in GATEKEEPER_LEVELS and heart_room is not None:
            places[level.level_num] = heart_room
    return places


# --- The door graph and the cut ----------------------------------------------------------------

def level_neighbors(level: Level, room_number: int) -> Iterator[tuple[Side, int]]:
    """The level's rooms one step away on each side: the gate's step, which crosses a row's end (A26)."""
    rooms = set(level.room_nums)
    for side in Side:
        other = room_grid.step(room_number, side)
        if other is not None and other in rooms:
            yield side, other


def item_place(level: Level, item: Item) -> int | None:
    """The room holding the item, or the room over the item cellar holding it."""
    room = item_room(level, item_code(item))
    if room is not None:
        return room
    cellar = item_cellar(level, item_code(item))
    if cellar is None:
        return None
    return next(stair.return_dest for stair in level.block.staircases if stair.room_num == cellar)


def reached_before(level: Level, gatekeeper: int) -> set[int]:
    """The rooms reached from the start when nothing leaves the gatekeeper: the late gate's graph, every
    passable side (open, walk-through, bombable, locked, and shutters that open), every staircase,
    transports included even for Do Not Segment Dungeons' levels, since the player still uses them."""
    graph = build_graph(level)
    start: State = (level.entrance_room, Side.SOUTH)
    seen = {start}
    stack = [start]
    while stack:
        room_number, side = stack.pop()
        for next_state in graph.edges.get((room_number, side), ()):
            if room_number == gatekeeper and next_state[0] != gatekeeper:
                continue
            if next_state not in seen:
                seen.add(next_state)
                stack.append(next_state)
    return {room_number for room_number, _side in seen}


def gated_part(level: Level, gatekeeper: int) -> set[int]:
    """The level's rooms only the gatekeeper leads to."""
    return set(level.room_nums) - reached_before(level, gatekeeper) - {gatekeeper}


def has_stairs(level: Level, room_number: int) -> bool:
    """A transport staircase ends in the room, or an item cellar returns to it."""
    return any(room_number in (stair.left_exit, stair.right_exit, stair.return_dest, stair.return_dest_b)
               for stair in level.block.staircases)


def drops_nothing(room: Room) -> bool:
    """Trigger 7 on a room with no item: the engine re-activates the hidden object on the kill and shows
    item $03 (the magical sword) or, under the no-item remap, a second triforce of power (TFOP-ROOM)."""
    return room.item == Item.NOTHING and room.room_action == RoomAction.ALL_DEAD_ITEM


def _stop_dropping_nothing(room: Room) -> None:
    """A room whose item moved away keeps its shutters opening on the kill (trigger 1, as trigger 7
    opens them) but no longer drops an item."""
    if drops_nothing(room):
        room.room_action = RoomAction.ALL_DEAD


def gatekeeper_problems(level: Level) -> list[str]:
    """Why the level's gatekeeper no longer holds (empty when it does): its boss, trigger and item, its
    shutters into the gated part, the boss room the roar follows, the cut itself, and no room of the
    level left dropping an item it does not hold (the swaps that fill the gatekeeper empty others)."""
    gatekeeper = level.gatekeeper_room
    if gatekeeper is None:
        return []
    room = level.block.room(gatekeeper)
    problems = [f"room ${other.room_num:02X} drops an item on the kill but holds none"
                for other in level.rooms if other is not room and drops_nothing(other)]
    if room.enemy not in GATEKEEPER_BOSSES:
        problems.append(f"holds {room.enemy.name}, not a boss")
    if room.room_action != RoomAction.ALL_DEAD_ITEM:
        problems.append(f"trigger {int(room.room_action)}, not 7")
    if room.item == Item.NOTHING:
        problems.append("holds no item")
    if level.boss_room != gatekeeper:
        problems.append(f"the level's boss room is ${level.boss_room:02X}")
    behind = gated_part(level, gatekeeper)
    for side, other in level_neighbors(level, gatekeeper):
        if other in behind and side_of(room, side) not in (D_SHUTTER, D_WALL):
            problems.append(f"its {side.name.lower()} side into the gated part is not a shutter")
    triforce, compass = item_place(level, Item.TRIFORCE), item_place(level, Item.COMPASS)
    if triforce not in behind:
        problems.append("the triforce is in front of it")
    if compass is not None and compass not in reached_before(level, gatekeeper) - {gatekeeper}:
        problems.append("the compass is behind it")
    return [f"level {level.level_num}, gatekeeper ${gatekeeper:02X}: {problem}" for problem in problems]


# --- One try -----------------------------------------------------------------------------------

def _target_size(setting: GatekeeperBosses, room_count: int, rng: Rng) -> int:
    """The gated part's size to grow to: the triforce's room alone for Late, a drawn size for Anywhere,
    at least EARLY_SHARE of the other rooms for Early."""
    largest = max(1, room_count - 3)        # the start, the gatekeeper and the compass stay in front
    if setting is GatekeeperBosses.LATE:
        return 1
    if setting is GatekeeperBosses.EARLY:
        smallest = min(largest, math.ceil(EARLY_SHARE * (room_count - 1)))
        return smallest + rng.below(largest - smallest + 1)
    return 1 + rng.below(largest)


def _boss_may_stand(level: Level, room: Room, boss: Enemy, kept_in_front: set[int]) -> bool:
    """A room the gatekeeper may be: not the start, triforce or compass room, no person, stairs or
    barred trigger, and a layout the boss may stand in (PS-BGRP-03's bars)."""
    return (room.room_num not in kept_in_front and not room.is_person
            and room.room_action not in BARRED_TRIGGERS and not has_stairs(level, room.room_num)
            and not is_boss_pick_barred(boss, room.room_type, room.movable_block))


def _transport_partners(level: Level) -> dict[int, set[int]]:
    """Each room with the rooms its transport staircases lead to (both ways: a cut must keep both ends
    on one side, or the staircase passes the gatekeeper)."""
    rooms = set(level.room_nums)
    partners: dict[int, set[int]] = {}
    for stair in level.block.staircases:
        first, second = stair.left_exit, stair.right_exit
        if stair.room_type == RoomType.TRANSPORT_STAIRCASE and first in rooms and second in rooms:
            assert first is not None and second is not None
            partners.setdefault(first, set()).add(second)
            partners.setdefault(second, set()).add(first)
    return partners


@dataclass
class _Growth:
    """The level's rooms as the part grows: grid steps and transport links join them."""
    level: Level
    partners: dict[int, set[int]]
    rooms: set[int]

    def steps(self, room_number: int) -> Iterator[int]:
        for _side, other in level_neighbors(self.level, room_number):
            yield other
        yield from self.partners.get(room_number, ())

    def joined_from_start(self, in_front: set[int]) -> set[int]:
        """The rooms of in_front that grid steps and transports within it join to the start."""
        joined = {self.level.entrance_room} & in_front
        stack = list(joined)
        while stack:
            for other in self.steps(stack.pop()):
                if other in in_front and other not in joined:
                    joined.add(other)
                    stack.append(other)
        return joined

    def unit(self, room_number: int) -> set[int]:
        """The room and every room its transports chain to: they join the part together."""
        unit = {room_number}
        stack = [room_number]
        while stack:
            for other in self.partners.get(stack.pop(), ()):
                if other not in unit:
                    unit.add(other)
                    stack.append(other)
        return unit

    def taken_in(self, behind: set[int], room_number: int) -> set[int]:
        """The part after taking in the room's unit and every room it cuts off from the start."""
        grown = behind | self.unit(room_number)
        in_front = self.rooms - grown
        return grown | (in_front - self.joined_from_start(in_front))


def _grow(level: Level, rng: Rng, triforce: int, kept_in_front: set[int], may_stand: set[int],
          target: int, smallest_steps: bool = False) -> tuple[set[int], int] | None:
    """Steps 2-3: the gated part and its gatekeeper, or None. The part takes a room (with its transport
    unit and the rooms it cuts off) only when the start and the compass stay joined in front; once it
    reaches the target size, the gatekeeper is a bordering room the boss may stand in whose loss leaves
    them joined too (rooms only it leads to become a pocket behind its shutters). When growth runs out
    first, the part falls back to the largest size it reached that a room could guard. smallest_steps
    (Late): each step takes one of the rooms that grow the part least, so the part stays as close to
    the triforce's room as the layout allows when its neighbours cannot guard it."""
    growth = _Growth(level, _transport_partners(level), set(level.room_nums))

    def keeps_front(part: set[int]) -> bool:
        return not part & kept_in_front and kept_in_front <= growth.joined_from_start(growth.rooms - part)

    behind = growth.taken_in(set(), triforce)
    if not keeps_front(behind):
        return None
    largest_guarded: tuple[set[int], list[int]] | None = None    # the last size a room could guard
    while True:
        bordering = sorted({other for room in behind for _side, other in level_neighbors(level, room)
                            if other in may_stand and other not in behind})
        guards = [room_number for room_number in bordering if keeps_front(behind | {room_number})]
        if guards:
            largest_guarded = behind, guards
            if len(behind) >= target:
                break
        frontier = sorted({other for room in behind for _side, other in level_neighbors(level, room)
                           if other not in behind and other not in kept_in_front})
        options = [grown for grown in (growth.taken_in(behind, other) for other in frontier) if keeps_front(grown)]
        if not options:
            break
        if smallest_steps:
            fewest = min(len(grown) for grown in options)
            options = [grown for grown in options if len(grown) == fewest]
        behind = options[rng.below(len(options))]
    if largest_guarded is None:
        return None
    behind, guards = largest_guarded
    return behind, guards[rng.below(len(guards))]


def _seal(level: Level, behind: set[int], gatekeeper: int) -> None:
    """Step 4. The gatekeeper takes trigger 7 now, so the repair's walks open its shutters as the boss's
    fall will."""
    gatekeeper_room = level.block.room(gatekeeper)
    gatekeeper_room.secret_info = SecretInfo(RoomAction.ALL_DEAD_ITEM, gatekeeper_room.secret_info.item_position)
    for room_number in level.room_nums:
        room = level.block.room(room_number)
        for side, other in level_neighbors(level, room_number):
            if room_number == gatekeeper:
                if other in behind:
                    set_side(room, side, D_SHUTTER)
            elif other != gatekeeper and (room_number in behind) != (other in behind):
                set_side(room, side, D_WALL)


def _repair(level: Level, rng: Rng, behind: set[int], gatekeeper: int, transports: bool,
            before_seal: WalkResult) -> bool:
    """Step 5: open a walled pair on one side of the cut with exactly one room reached (the gate's
    repair's "reached", VA-REJ-01.2), drawn among them, until the gate's walk is as good as before the
    seal: it passes, or, for a level that did not pass (a vanilla level the gate never walked,
    VA-REJ-02), both walks reach every room they reached before."""
    def is_as_good(walk: WalkResult) -> bool:
        if before_seal.passed:
            return walk.passed
        return (walk.forward_rooms >= before_seal.forward_rooms
                and walk.reverse_rooms >= before_seal.reverse_rooms)

    walk = connectivity_walk(level, transports)
    while not is_as_good(walk):
        reached = walk.repair_reached()
        pairs = []
        for room_number in level.room_nums:
            for side, other in level_neighbors(level, room_number):
                if side not in (Side.EAST, Side.SOUTH) or (room_number in reached) == (other in reached):
                    continue
                crosses_cut = (room_number in behind) != (other in behind)
                into_part = gatekeeper in (room_number, other) and (room_number in behind or other in behind)
                if crosses_cut or into_part:
                    continue
                if D_WALL in (side_of(level.block.room(room_number), side),
                              side_of(level.block.room(other), side.opposite)):
                    pairs.append((room_number, side, other))
        if not pairs:
            return False
        room_number, side, other = pairs[rng.below(len(pairs))]
        door = D_OPEN if side == Side.EAST or not rng.chance(*BOMBABLE_CHANCE) else D_BOMB
        set_side(level.block.room(room_number), side, door)
        set_side(level.block.room(other), side.opposite, door)
        walk = connectivity_walk(level, transports)
    return True


def _shut_pockets(level: Level, gatekeeper: int, behind: set[int]) -> None:
    """Every passable side of the gatekeeper into a room only it leads to becomes a shutter too: the
    grown part's, and any pocket of front rooms the repair left behind it."""
    room = level.block.room(gatekeeper)
    for side, other in level_neighbors(level, gatekeeper):
        if other in behind and side_of(room, side) != D_WALL:
            set_side(room, side, D_SHUTTER)


def _install(level: Level, gatekeeper: int, boss_room: Room, heart_item: Item | None) -> bool:
    """Step 7: the boss's monsters and the heart container's place's item into the gatekeeper, on
    trigger 7 at a spot that may hold an item. False when the room is left with no item, or no spot of
    the room may hold one."""
    room = level.block.room(gatekeeper)
    if boss_room is not room:
        room.enemy_info, boss_room.enemy_info = boss_room.enemy_info, room.enemy_info
    holder = None if heart_item is None else next(
        (other for other in level.rooms if other.item == heart_item and other is not room), None)
    if heart_item is not None and holder is not None and room.item != heart_item:
        room.item, holder.item = heart_item, room.item
        _stop_dropping_nothing(holder)
    spots = item_spot_positions(level, room)
    if room.item == Item.NOTHING or not spots:
        return False
    position = room.secret_info.item_position if room.secret_info.item_position in spots else spots[0]
    room.secret_info = SecretInfo(RoomAction.ALL_DEAD_ITEM, position)
    level.gatekeeper_room = gatekeeper
    level.boss_room = gatekeeper            # LevelInfo_BossRoomId: the roar stops once it falls
    return True


def _snapshot(level: Level) -> list[tuple[dict[str, object], dict[str, object]]]:
    return [(room.__dict__.copy(), room.walls.__dict__.copy()) for room in level.rooms]


def _restore(level: Level, snapshot: list[tuple[dict[str, object], dict[str, object]]]) -> None:
    for room, (fields, walls) in zip(level.rooms, snapshot, strict=True):
        room.__dict__.update(fields)
        room.walls.__dict__.update(walls)


def _bring_compass_forward(level: Level, rng: Rng, compass: int, before: set[int]) -> bool:
    """Swap the compass with a small item (or no item) of a room reached before the gatekeeper, at a
    spot that room may hold an item on. False when no such room exists or the compass is in a
    cellar."""
    compass_room = level.block.room(compass)
    if compass_room.item != Item.COMPASS:
        return False                          # in the room's item cellar: not moved
    candidates = [room for room in level.rooms if room.room_num in before and room.item in SMALL_ITEMS
                  and room.room_num != level.entrance_room and item_spot_positions(level, room)]
    if not candidates:
        return False
    target = candidates[rng.below(len(candidates))]
    target.item, compass_room.item = Item.COMPASS, target.item
    _stop_dropping_nothing(compass_room)
    spots = item_spot_positions(level, target)
    if target.secret_info.item_position not in spots:
        target.secret_info = SecretInfo(target.room_action, spots[0])
    return True


def _try(level: Level, rng: Rng, plan: GatekeeperPlan, transports: bool, compass_may_move: bool) -> bool:
    """One try, steps 1-7, on the level as it stands; the caller restores it on failure.
    compass_may_move: the part may take the compass's room, and the compass then moves to a room in
    front (_bring_compass_forward)."""
    boss_rooms = [room for room in level.rooms if room.enemy in GATEKEEPER_BOSSES]
    triforce, compass = item_place(level, Item.TRIFORCE), item_place(level, Item.COMPASS)
    if not boss_rooms or triforce is None or triforce == level.entrance_room or triforce == compass:
        return False
    boss_room = boss_rooms[rng.below(len(boss_rooms))]
    kept_in_front = {level.entrance_room} if compass is None or compass_may_move else {level.entrance_room, compass}
    kept_out = kept_in_front | {triforce} if compass is None else kept_in_front | {triforce, compass}
    may_stand = {room.room_num for room in level.rooms if _boss_may_stand(level, room, boss_room.enemy, kept_out)}
    grown = _grow(level, rng, triforce, kept_in_front, may_stand,
                  _target_size(plan.setting, len(level.room_nums), rng),
                  smallest_steps=plan.setting is GatekeeperBosses.LATE)
    if grown is None:
        return False
    behind, gatekeeper = grown
    before_seal = connectivity_walk(level, transports)
    _seal(level, behind, gatekeeper)
    if not _repair(level, rng, behind, gatekeeper, transports, before_seal):
        return False
    before = reached_before(level, gatekeeper)
    if triforce in before or gatekeeper not in before:
        return False
    lowest, highest = SHARE_ACCEPTED[plan.setting]
    gated_share = (len(level.room_nums) - len(before)) / (len(level.room_nums) - 1)
    if not lowest <= gated_share <= highest:
        return False
    in_front = before - {gatekeeper}
    if compass is not None and compass not in in_front and not _bring_compass_forward(level, rng, compass, in_front):
        return False
    _shut_pockets(level, gatekeeper, set(level.room_nums) - before)
    return _install(level, gatekeeper, boss_room, plan.heart_place_items.get(level.level_num))


def place_gatekeeper(level: Level, rng: Rng, plan: GatekeeperPlan, transports: bool = True,
                     tries: int | None = None) -> bool:
    """Up to the setting's tries (TRIES) at building the level's gatekeeper; the level is left as it
    was when none succeeds. transports=False: Do Not Segment Dungeons' level, whose repair walks doors
    only."""
    for attempt in range(TRIES[plan.setting] if tries is None else tries):
        snapshot = _snapshot(level)
        # Early may always move the compass forward; the others keep it where it is on the first half
        # of the tries, and may move it on the second (a level whose triforce room lies on the only
        # way to the compass needs it).
        compass_may_move = plan.setting is GatekeeperBosses.EARLY or 2 * attempt >= (tries or TRIES[plan.setting])
        if _try(level, rng, plan, transports, compass_may_move):
            return True
        _restore(level, snapshot)
    return False
