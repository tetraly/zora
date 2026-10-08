"""The seed-level acceptance check (acceptance.md, B6): after the late gate,
a generation pass is judged by E1, E3, E4 and E5 in that order, and the
first failure restarts the whole seed (VA-REJ-06, VA-REJ-12).

  E1 (VA-REJ-07/08)  a cold-start player can collect every tracked item
  E3 (VA-REJ-09)     Zelda's room is reachable in level 9
  E4/E5 (VA-REJ-10/11, OW-SHOP-06)  the candle and arrow shops' front doors

E1's walk is VA-WALK's (validation-behavior.md) with VA-REJ-17's
differences and arrival rule and VA-REJ-18's entry-side rule, over a
level's rooms (the pass's staged levels in generation, a parsed ROM's in the
corpus checks); E3's is the plain walk.

Settled by acceptance.md A55 (QUESTIONS #62):
  - VA-REJ-17's four family lists are monster values (FAMILY_LISTS); the
    sword list never blocks, since the wooden sword is always held.
  - A level's entrance screen (VA-REJ-07 (i)) is its entry door
    (OW-ENTR-02), the door the recorder uses, and its needs are the Raft,
    Recorder, Ladder and Bracelet sets (the Burnable set is not consulted).
  - The arrival rule judges only the walk's target room; a stair arrival
    records the stair side, which no side test counts.

The ZORA flags Progressive Items and Shop Items in the Item Pool change some
rules (docs/design/progressive-items-plan.md section 5; LogicRules): each
rule applies only when its flag is on, so with both off the rules are
today's.
"""
from dataclasses import dataclass, field, replace

from zora.generate.dungeon_walk import (
    FAMILY_LISTS,
    FamilyLists,
    Walk,
    family_items,
    is_family_blocked,
    item_cellar,
    item_room,
    walk_level,
)
from zora.generate.steps.cave_entries import (
    BRACELET_SCREENS,
    BURNABLE_SCREENS,
    LADDER_SCREENS,
    RAFT_SCREENS,
    RECORDER_SCREENS,
    CaveShuffle,
)
from zora.generate.steps.item_shuffle_result import EXTRA_SLOT_CAVES, ItemShuffleResult, shop_of_slot
from zora.generate.steps.overworld_gates import NO_GATES, OverworldGates
from zora.generate.steps.shuffle_shop_items import front_door_failure
from zora.model.enums import Destination, Item, RoomType
from zora.model.levels import LEVEL_9, ZELDA_LIST, Level
from zora.model.overworld import Overworld, Shop

LONG_ITEMS = frozenset({Item.RECORDER, Item.BOW, Item.RAFT, Item.LADDER, Item.POWER_BRACELET})     # VA-REJ-08
LEVEL9_ENTRY = -1                  # the held set's pseudo-item for level-9 entry
TRIFORCES_NEEDED = 8
DUNGEONS = range(1, 10)
SCREEN_NEEDS = ((RAFT_SCREENS, Item.RAFT), (RECORDER_SCREENS, Item.RECORDER), (LADDER_SCREENS, Item.LADDER),
                (BRACELET_SCREENS, Item.POWER_BRACELET))
LADDER_LAYOUTS = frozenset({RoomType.LAVA_MOAT, RoomType.T_ROOM, RoomType.VERTICAL_MOAT_ROOM,
                            RoomType.CIRCLE_MOAT_ROOM, RoomType.CHEVY_ROOM, RoomType.HORIZONTAL_MOAT_ROOM,
                            RoomType.DOUBLE_MOAT_ROOM})            # VA-REJ-07 (iv)
FAMILY_EXEMPT_LAYOUT = RoomType.LAYOUT_0x3D   # VA-REJ-07 (iii): layouts above it are never blocked


# --- the progressive items' rules (plan section 5) ----------------------------------

# PI-LOGIC-01: an upgrade line's count is how many of its items are held. The counts the
# rules read are pseudo-items in the held set, as LEVEL9_ENTRY is.
ARROW_LINE = frozenset({Item.WOOD_ARROWS, Item.SILVER_ARROWS})
CANDLE_LINE = frozenset({Item.BLUE_CANDLE, Item.RED_CANDLE})
ONE_ARROW = -2                     # an arrow count of at least 1
TWO_ARROWS = -3                    # an arrow count of at least 2
ONE_CANDLE = -4                    # a candle count of at least 1
# The vanilla shop ware each line's count may take (PI-LOGIC-01, Shop Items in the Item Pool off).
LINE_SHOP_WARES = ((ARROW_LINE, Item.WOOD_ARROWS, (ONE_ARROW, TWO_ARROWS)),
                   (CANDLE_LINE, Item.BLUE_CANDLE, (ONE_CANDLE,)))


@dataclass(frozen=True)
class LogicRules:
    """The rules E1 judges by. The defaults are VA-REJ-07's (today's); logic_rules changes
    them for the ZORA flags."""
    family_lists: FamilyLists = FAMILY_LISTS
    screen_needs: tuple[tuple[frozenset[int], int], ...] = SCREEN_NEEDS
    counts_lines: bool = False             # PI-LOGIC-01: the held set carries the line counts
    counts_shop_wares: bool = True         # a line's vanilla shop ware counts once its door is reached
    checks_front_doors: bool = True        # E4/E5 (OW-SHOP-06)
    # The owner's 2.0 overworld gates (overworld_gates.py): each maze's hint pseudo-item, held once
    # the hint shop that sells its path is reached; and the gated screens the candle and arrow
    # shops' front doors must avoid as well (E4/E5).
    maze_hints: tuple[tuple[int, Destination], ...] = ()
    front_door_barred: frozenset[int] = frozenset()

    def needs(self, screen: int) -> frozenset[int]:
        """The items a screen's entrance needs."""
        return frozenset(item for screens, item in self.screen_needs if screen in screens)


DEFAULT_RULES = LogicRules()


def _family(family_lists: FamilyLists, name: str, *unblocked_by: frozenset[int]) -> FamilyLists:
    return tuple(replace(family_list, unblocked_by=unblocked_by) if family_list.name == name else family_list
                 for family_list in family_lists)


def logic_rules(progressive_items: bool, shop_items_in_pool: bool, gates: OverworldGates = NO_GATES) -> LogicRules:
    """Plan section 5, and the owner's 2.0 overworld gates: each rule only when its flag is on."""
    rules = DEFAULT_RULES
    if gates.any:
        rules = replace(rules, screen_needs=(*rules.screen_needs, *gates.screen_needs()),
                        maze_hints=gates.maze_hints(), front_door_barred=gates.gated_screens())
    if progressive_items:
        # PI-LOGIC-02: Ganon (the "arrow" family) needs the bow and two arrow upgrades
        rules = replace(rules, counts_lines=True,
                        family_lists=_family(rules.family_lists, "arrow", frozenset({Item.BOW, TWO_ARROWS})))
    if shop_items_in_pool:
        # PI-LOGIC-03: Gohma (the "bow" family) needs the bow and an arrow upgrade; PI-LOGIC-04:
        # a burnable screen's entrance needs a candle; PI-LOGIC-05: E4/E5 are skipped; the shop
        # wares join the pool, so no vanilla ware counts toward a line.
        rules = replace(rules, counts_lines=True, counts_shop_wares=False, checks_front_doors=False,
                        family_lists=_family(rules.family_lists, "bow", frozenset({Item.BOW, ONE_ARROW})),
                        screen_needs=(*rules.screen_needs, (BURNABLE_SCREENS, ONE_CANDLE)))
    return rules


def _screen_needs(screen: int) -> frozenset[int]:
    return DEFAULT_RULES.needs(screen)


@dataclass
class AcceptanceCheck:
    levels: list[Level]              # the nine levels being judged
    item_shuffle_result: ItemShuffleResult
    overworld: Overworld
    caves: CaveShuffle
    rules: LogicRules = DEFAULT_RULES
    _walks: dict[tuple[int, int | None, frozenset[int]], Walk] = field(default_factory=dict)

    def _level(self, level_num: int) -> Level:
        return next(level for level in self.levels if level.level_num == level_num)

    def _walk(self, level: int, target: int | None, held: frozenset[int]) -> Walk:
        """The inventory walk toward a target. It depends on the held set
        only through the family lists and the ladder (VA-REJ-18's rows)."""
        key = (level, target, held & (family_items(self.rules.family_lists) | {Item.LADDER}))
        if key not in self._walks:
            self._walks[key] = walk_level(self._level(level), held, is_last_boss_open=False,
                                          uses_families=True, target=target, family_lists=self.rules.family_lists)
        return self._walks[key]

    def _can_enter(self, level: int, held: frozenset[int]) -> bool:
        needs = self.rules.needs(self.caves.entry_door(level))
        if level == LEVEL_9:
            needs |= LONG_ITEMS
        return needs <= held

    def _can_reach_room(self, level: int, room: int, held: frozenset[int]) -> bool:
        """VA-REJ-07 (ii)-(iv) for a target room."""
        target = self._level(level).block.room(room)
        layout = target.room_type
        return (self._walk(level, room, held).accepts(self._level(level), room)
                and (not is_family_blocked(target, held, self.rules.family_lists) or layout > FAMILY_EXEMPT_LAYOUT)
                and (Item.LADDER in held or layout not in LADDER_LAYOUTS))

    def _can_reach_item(self, level: int, item: int, held: frozenset[int]) -> bool:
        """A level item: located as the level's room (then item cellar)
        holding it; none found is unreachable."""
        place = item_room(self._level(level), item)
        if place is not None:
            return self._can_reach_room(level, place, held)
        cellar = item_cellar(self._level(level), item)
        return cellar is not None and cellar in self._walk(level, None, held).cellars

    def _completes(self, level: int, held: frozenset[int]) -> bool:
        boss = item_room(self._level(level), Item.TRIFORCE)
        return boss is not None and self._can_reach_room(level, boss, held)

    def collects_everything(self) -> bool:
        """E1 (VA-REJ-07): the closure reaches every tracked item type and
        level-9 entry."""
        target = {Item.WOOD_SWORD, LEVEL9_ENTRY} | {place.item for place in self.item_shuffle_result.tracked}
        return target <= self.closure()[0]

    def closure(self) -> tuple[set[int], set[int]]:
        """VA-REJ-07's closure from the wooden sword and the tracked item in
        the armos slot (0x10D05), if one is there: the held set and the
        completed dungeons when nothing more changes."""
        tracked = self.item_shuffle_result.tracked
        white_sword = self.caves.movable_screens(Destination.WHITE_SWORD_CAVE)
        held = {Item.WOOD_SWORD} | {place.item for place in tracked if place.slot == "armos"}
        completed: set[int] = set()
        changed = True
        while changed:
            changed = False
            frozen = frozenset(held)
            for place in tracked:
                if place.item in held:
                    continue
                if place.slot == "white_sword":
                    is_collected = bool(white_sword) and self.rules.needs(white_sword[0]) <= frozen
                elif place.slot == "coast":
                    is_collected = Item.LADDER in frozen
                elif (shop := shop_of_slot(place.slot)) is not None:
                    # a joined shop ware (SI-JOIN-01): collected once a door of its shop is reached,
                    # and the letter held for the potion shop (Shuffle Blue Potion)
                    is_collected = self.shop_door_reached(shop, frozen) and (
                        shop != Destination.POTION_SHOP or Item.LETTER in frozen)
                elif place.slot in EXTRA_SLOT_CAVES:
                    # a ZORA extra's cave (docs/zora-extras.md): as the white-sword slot, by its
                    # screen needs; the magical-sword cave's hearts are the heart check's
                    extra_cave = self.caves.movable_screens(EXTRA_SLOT_CAVES[place.slot])
                    is_collected = bool(extra_cave) and self.rules.needs(extra_cave[0]) <= frozen
                elif place.level is not None:
                    is_collected = self._can_enter(place.level, frozen) \
                        and self._can_reach_item(place.level, place.item, frozen)
                else:
                    is_collected = False
                if is_collected:
                    held.add(place.item)
                    changed = True
            for level in DUNGEONS:
                if level not in completed and self._can_enter(level, frozen) \
                        and self._completes(level, frozen):
                    completed.add(level)
                    changed = True
            if len(completed) >= TRIFORCES_NEEDED and LEVEL9_ENTRY not in held:
                held.add(LEVEL9_ENTRY)
                changed = True
            for hint, hint_shop in self.rules.maze_hints:
                if hint not in held and self.shop_door_reached(hint_shop, frozenset(held)):
                    held.add(hint)
                    changed = True
            if self.rules.counts_lines:
                counts = self.line_counts(frozenset(held))
                changed |= not counts <= held
                held |= counts
        return held, completed

    def line_counts(self, held: frozenset[int]) -> set[int]:
        """PI-LOGIC-01: the line-count pseudo-items a held set gives: the line's held items,
        plus (Shop Items in the Item Pool off) its vanilla shop ware once a door of a shop
        selling it is reached. Rupees are not modelled."""
        counts: set[int] = set()
        for line, ware, at_least in LINE_SHOP_WARES:
            count = len(held & line)
            if self.rules.counts_shop_wares and self._shop_door_reached(ware, held):
                count += 1
            counts.update(at_least[:count])
        return counts

    def _shop_door_reached(self, ware: Item, held: frozenset[int]) -> bool:
        return any(self.shop_door_reached(cave.destination, held) for cave in self.overworld.caves
                   if isinstance(cave, Shop) and any(item.item == ware for item in cave.items))

    def shop_door_reached(self, shop: Destination, held: frozenset[int]) -> bool:
        """A shop's front door is reached: one of its screens' needs are held."""
        return any(self.rules.needs(screen) <= held for screen in self.caves.movable_screens(shop))

    def is_zelda_reachable(self) -> bool:
        """E3 (VA-REJ-09): the first $37 room of level 9's block, accepted
        from level 9's start room with no family blocking, the ladder held
        and last-boss shutters open."""
        level9 = self._level(LEVEL_9)
        zelda = next((room.room_num for room in level9.block.rooms
                      if room.monster_byte == ZELDA_LIST), None)
        if zelda is None:
            return False
        walk = walk_level(level9, frozenset({Item.LADDER}), is_last_boss_open=True, uses_families=False,
                          target=zelda, uses_entry_sides=False)
        return walk.accepts(level9, zelda)


def acceptance_check(levels: list[Level], item_shuffle_result: ItemShuffleResult, overworld: Overworld,
                     caves: CaveShuffle, rules: LogicRules = DEFAULT_RULES) -> str | None:
    """VA-REJ-12: E1, E3, E4, E5 in order; the first failure's label, or
    None when the pass is accepted. levels: the pass's nine staged levels.
    E4/E5 are skipped under Shop Items in the Item Pool (PI-LOGIC-05)."""
    checks = AcceptanceCheck(levels, item_shuffle_result, overworld, caves, rules)
    if not checks.collects_everything():
        return "E1"
    if not checks.is_zelda_reachable():
        return "E3"
    if not rules.checks_front_doors:
        return None
    door = front_door_failure(overworld, caves, rules.front_door_barred)
    if door is not None:
        return "E4" if door.startswith("(a)") else "E5"
    return None
