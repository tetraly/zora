"""The seed-level acceptance check (acceptance.md, B6): after the late gate,
a generation pass is judged by E1, E3, E4 and E5 in that order, and the
first failure restarts the whole seed (VA-REJ-06, VA-REJ-12).

  E1 (VA-REJ-07/08)  a cold-start player can collect every tracked item
  E3 (VA-REJ-09)     Zelda's room is reachable in level 9
  E4/E5 (VA-REJ-10/11, OW-SHOP-06)  the candle and arrow shops' front doors
  E9 (VA-REJ-21)     no level's start-room number is the screen of its own door
  E10 (ZORA's own)   Ganon's room is reachable before the last-boss shutters open

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
from typing import TYPE_CHECKING

from ..flags.fields import WoodenSwordState
from ..flags.zora_flags import Pacing
from ..model.enums import Destination, Item, RoomType
from ..model.level_9_gate import EIGHT_PIECES, TRIFORCE_LEVELS, GateKind, Level9Gate
from ..model.levels import GANON_LIST, LEVEL_9, ZELDA_LIST, Level
from ..model.overworld import Overworld, Shop
from .dungeon_walk import (
    FAMILY_LISTS,
    LOGIC_WALK,
    SPEC_WALK,
    FamilyLists,
    Walk,
    WalkRules,
    family_items,
    is_family_blocked,
    item_cellar,
    item_room,
    walk_level,
)
from .steps.cave_entries import (
    BRACELET_SCREENS,
    BURNABLE_SCREENS,
    EXPANDED_RECORDER_SCREENS,
    LADDER_SCREENS,
    MIXED_RECORDER_SCREENS,
    RAFT_SCREENS,
    RECORDER_SCREENS,
    CaveShuffle,
)
from .steps.item_shuffle_result import EXTRA_SLOT_CAVES, ItemShuffleResult, TrackedPlace, shop_of_slot

if TYPE_CHECKING:
    from .steps.extra_pool_items import ExtraPoolItems, PoolPlace
from .steps.overworld_gates import NO_GATES, OverworldGates
from .steps.shuffle_shop_items import bomb_shop_door_failure, front_door_failure

LONG_ITEMS = frozenset({Item.RECORDER, Item.BOW, Item.RAFT, Item.LADDER, Item.POWER_BRACELET})     # VA-REJ-08
LEVEL9_ENTRY = -1                  # the held set's pseudo-item for level-9 entry
# FP-TRIF-06 (C08 = 11): the item level 9's entrance asks for is held (any sword, either candle,
# either arrow: the gate tests one inventory byte)
LEVEL9_ITEM = -5
TRIFORCES_NEEDED = 8
TRIFORCE_LEVEL_SET = frozenset(TRIFORCE_LEVELS)
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
# ASNB (docs/design/asnb.md section 5): with Level 9 Entrance = Level 4 sword, level-9 entry is a
# sword count of at least 4 by the same counting rule, each sword record collected once: the
# wooden-sword cave's sword (always held), the magical-sword cave's while its cave keeps it (reached),
# and every tracked sword (the white sword, a randomized magical sword, the level-2 sword).
SWORD_LINE = frozenset({Item.WOOD_SWORD, Item.WHITE_SWORD, Item.MAGICAL_SWORD})
RING_LINE = frozenset({Item.BLUE_RING, Item.RED_RING})
SWORDS_FOR_LEVEL_9 = 4
HELD_FROM_START_SWORDS = 1                 # the wooden-sword cave's (C07 = normal; VA-REJ-07's start)
# VA-REJ-22: the wooden-sword states under which the wooden sword is held from the start
WOOD_SWORD_FROM_START = frozenset({WoodenSwordState.NORMAL, WoodenSwordState.WOODEN_SWORD_ONLY})
# Offense and Defense Item Pacing (docs/zora-extras.md section 22; Z1M1's GameBuilder.cs:2468-2507 and
# docs/z1m1/pacing.md): how many swords or rings a dungeon needs before its items count. The counts are
# pseudo-items in the held set, as the line counts are: SWORDS_2 is a sword count of at least 2.
# "N swords" counts sword items, as Z1M1 does, not tiers: the wooden sword (held from the start) is one.
SWORDS_1, SWORDS_2 = -6, -7
RINGS_1, RINGS_2 = -8, -9
SWORD_COUNTS = (SWORDS_1, SWORDS_2)
RING_COUNTS = (RINGS_1, RINGS_2)
PACING_CURVES = {Pacing.EARLIER: 0, Pacing.NORMAL: 1, Pacing.LATER: 2}      # Z1M1's OffenseCurve, DefenseCurve


def swords_needed(pacing: Pacing, level: int) -> int:
    """Z1M1's CreateDungeonDest: 1 sword from level 2c + 1, 2 from level 2c + 5 (c is the curve)."""
    if pacing is Pacing.OFF:
        return 0
    curve = PACING_CURVES[pacing]
    return (level >= 2 * curve + 1) + (level >= 2 * curve + 5)


def rings_needed(pacing: Pacing, level: int) -> int:
    """Z1M1's CreateDungeonDest: 1 ring from level 2c + 5, 2 from level 2c + 9."""
    if pacing is Pacing.OFF:
        return 0
    curve = PACING_CURVES[pacing]
    return (level >= 2 * curve + 5) + (level >= 2 * curve + 9)


# The vanilla shop ware each line's count may take (PI-LOGIC-01, Shop Items in the Item Pool off).
LINE_SHOP_WARES = ((ARROW_LINE, Item.WOOD_ARROWS, (ONE_ARROW, TWO_ARROWS)),
                   (CANDLE_LINE, Item.BLUE_CANDLE, (ONE_CANDLE,)))


@dataclass(frozen=True)
class PacingHearts:
    """Offense Item Pacing's heart model: a sword cave's sword counts only once the heart containers
    reachable at that point, plus the starting hearts, meet the cave's requirement. The requirements
    are the highest the draw can give (the sword caves' counts are drawn after the attempt ships, as
    white_sword_cave_hearts_met judges them), or PRG0's with Change Sword Hearts off."""
    starting: int
    white_sword: int
    magical_sword: int


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
    # Book to Understand NPCs (B48, HT-BOOK-01): every person, the hint shops' too, shows text 0
    # until the book is held, so a maze's path is known only with the book as well
    maze_hints_need_book: bool = False
    # ASNB: level-9 entry by SWORDS_FOR_LEVEL_9 swords instead of the eight triforces; and whether
    # the magical-sword cave's own sword counts once its cave is reached (Randomize Magical Sword
    # off; the heart check leaves it out, AcceptanceHeartReach)
    level_9_by_swords: bool = False
    magical_sword_cave_counts: bool = False
    # VA-REJ-08: entering level 9 (its items) needs the five long items, but with Allow Important
    # Items in 9 (B25)
    level_9_needs_long_items: bool = True
    # Level 9 Entry (C08; VA-REJ-07, FP-TRIF-01 to FP-TRIF-06): the pass's gate. Level-9 entry is
    # held once that many of levels 1 to 8 have completed (any of them), once the chosen levels
    # have, or from the start; level 9's own completion never counts (owner ruling 2026-10-21: it
    # never completes, VA-REJ-07). Under an item, level 9's items and completion need the item,
    # and so does E1's target, whatever the item (owner ruling 2026-10-22; docs/deviations.md).
    level_9_gate: Level9Gate = EIGHT_PIECES
    # Shop Items in the Item Pool's baits (docs/zora-extras.md section 10): tracked items, and
    # no bait is usable until every bait record is collected (owner rule, 2026-10-17: the player
    # can never feed one Goriya the bait another needs); until then a hungry Goriya blocks its
    # room's north side (dungeon_walk.HUNGRY_GORIYA_ROW)
    bait_in_pool: bool = False
    # Shuffle Wood Sword (docs/zora-extras.md section 13): the wood sword is a tracked item to
    # collect, no longer held from the start (the sword family still takes it or the wand)
    wood_sword_in_pool: bool = False
    # Offense and Defense Item Pacing (Pacing): a dungeon's items count only with that many swords or rings held
    offense_pacing: Pacing = Pacing.OFF
    defense_pacing: Pacing = Pacing.OFF
    # Offense Item Pacing only: the hearts a sword cave's sword needs (None: the caves count when reached)
    pacing_hearts: PacingHearts | None = None
    # Recorder Warping: a dungeon whose entry door needs the raft is also entered with the recorder, which
    # warps to its entry door (set only with Recorder to Unbeaten Dungeons and the new entries on)
    recorder_warps: bool = False
    # Swords (C07; VA-REJ-22): the wooden sword is held from the start only under Normal and Wood
    # Sword Only, and part of the target but under Swordless; under No Wood Sword the white sword
    # brings it; under Swordless with B25 off level 9 needs the wand too, and E6 runs
    wooden_sword_state: WoodenSwordState = WoodenSwordState.NORMAL
    # Swordlish (features FP-SWL-02, VA-REJ-23; generated as Normal): the wooden sword is held once the walk
    # holds N pieces (0: off), counting the starting pieces (one bit per level 1-8, FL-ALT-06) and the levels
    # completed, each level once; or once the white sword is held, as under No Wood Sword
    swordlish_pieces: int = 0
    start_triforce_pieces: int = 0
    # Which walk (dungeon_walk.WalkRules): VA-REJ-17/18's in generation (ZORA mode and the
    # original randomizer's validator); the logic walk only for Archipelago's rules and FINISH's
    # sanity check (logic_walk_rules)
    walk: WalkRules = SPEC_WALK

    @property
    def paces(self) -> bool:
        return self.offense_pacing is not Pacing.OFF or self.defense_pacing is not Pacing.OFF

    @property
    def counts_swords(self) -> bool:
        """The closure tracks the sword records it collects: ASNB's level-9 entrance and Offense Item Pacing."""
        return self.level_9_by_swords or self.offense_pacing is not Pacing.OFF

    def pacing_needs(self, level: int) -> frozenset[int]:
        """The count pseudo-items a level's items need (none for a level that asks nothing)."""
        return frozenset({*SWORD_COUNTS[:swords_needed(self.offense_pacing, level)],
                          *RING_COUNTS[:rings_needed(self.defense_pacing, level)]})

    @property
    def level_9_entry_needs(self) -> frozenset[int]:
        """VA-REJ-08: what level 9's items and completion need besides its entrance screen: level-9
        entry, and the five long items unless B25 is on; VA-REJ-22: with them, under Swordless, the
        wand."""
        gate_item = {LEVEL9_ITEM} if self.level_9_gate.kind is GateKind.ITEM else set()
        if not self.level_9_needs_long_items:
            return frozenset({LEVEL9_ENTRY} | gate_item)
        wand = {Item.WAND} if self.wooden_sword_state is WoodenSwordState.SWORDLESS else set()
        return frozenset(LONG_ITEMS | {LEVEL9_ENTRY} | wand | gate_item)

    def opens_level_9(self, completed: set[int]) -> bool:
        """VA-REJ-07: the gate's pieces are won (the closure's completed levels, 1 to 8 only)."""
        gate = self.level_9_gate
        if gate.kind is GateKind.LEVELS:
            return gate.levels <= completed
        return len(completed & TRIFORCE_LEVEL_SET) >= gate.pieces

    @property
    def wood_sword_from_start(self) -> bool:
        """VA-REJ-07 and VA-REJ-22: the closure starts with the wooden sword under Normal and Wood
        Sword Only (unless Shuffle Wood Sword puts it in the pool)."""
        if self.swordlish_pieces:
            return self.swordlish_opens(set())         # VA-REJ-23: with N starting pieces or more
        return not self.wood_sword_in_pool and self.wooden_sword_state in WOOD_SWORD_FROM_START

    def swordlish_opens(self, completed: set[int]) -> bool:
        """VA-REJ-23: the pieces held, the starting pieces and the completed levels 1 to 8 (each level once),
        are N or more."""
        starting = {level for level in TRIFORCE_LEVEL_SET if self.start_triforce_pieces >> (level - 1) & 1}
        return len(starting | (completed & TRIFORCE_LEVEL_SET)) >= self.swordlish_pieces

    @property
    def wood_sword_in_target(self) -> bool:
        """VA-REJ-22: the wooden sword is part of E1's target but under Swordless."""
        return self.wooden_sword_state is not WoodenSwordState.SWORDLESS

    def needs(self, screen: int) -> frozenset[int]:
        """The items a screen's entrance needs."""
        return frozenset(item for screens, item in self.screen_needs if screen in screens)


DEFAULT_RULES = LogicRules()


def _family(family_lists: FamilyLists, name: str, *unblocked_by: frozenset[int]) -> FamilyLists:
    return tuple(replace(family_list, unblocked_by=unblocked_by) if family_list.name == name else family_list
                 for family_list in family_lists)


def logic_rules(progressive_items: bool, shop_items_in_pool: bool, gates: OverworldGates = NO_GATES,
                level_9_by_swords: bool = False, magical_sword_cave_counts: bool = False,
                eleven_screen_recorder_set: bool = False, important_items_in_level_9: bool = False,
                maze_hints_need_book: bool = False, wood_sword_in_pool: bool = False,
                wooden_sword_state: WoodenSwordState = WoodenSwordState.NORMAL,
                expanded_recorder_set: bool = False, offense_pacing: Pacing = Pacing.OFF,
                defense_pacing: Pacing = Pacing.OFF, recorder_warps: bool = False,
                pacing_hearts: PacingHearts | None = None, swordlish_pieces: int = 0,
                start_triforce_pieces: int = 0) -> LogicRules:
    """Plan section 5, the owner's 2.0 overworld gates and ASNB's level-9 entrance: each rule only
    when its flag is on. Every overworld quest but the first (C01 = 1, 2, 3) reads the
    eleven-screen recorder set (OW-MIX-08, OW-QST-02, OW-QST-04: an entry door or the white-sword
    cave there needs the recorder; E4/E5 read the shops' own copy,
    shuffle_shop_items.front_door_failure). Expanded Dungeon Locations reads its two recorder
    spots, 1Q7's lake and 2Q6's graveyard (cave_entries.EXPANDED_RECORDER_SCREENS)."""
    rules = DEFAULT_RULES
    if wood_sword_in_pool:
        rules = replace(rules, wood_sword_in_pool=True)
    if wooden_sword_state is not WoodenSwordState.NORMAL:
        rules = replace(rules, wooden_sword_state=wooden_sword_state)
    if important_items_in_level_9:
        rules = replace(rules, level_9_needs_long_items=False)
    if eleven_screen_recorder_set:
        rules = replace(rules, screen_needs=tuple((MIXED_RECORDER_SCREENS if screens == RECORDER_SCREENS else screens,
                                                   need) for screens, need in rules.screen_needs))
    if expanded_recorder_set:
        rules = replace(rules, screen_needs=tuple((EXPANDED_RECORDER_SCREENS if screens == RECORDER_SCREENS
                                                   else screens, need) for screens, need in rules.screen_needs))
    if level_9_by_swords or offense_pacing is not Pacing.OFF:
        rules = replace(rules, level_9_by_swords=level_9_by_swords, magical_sword_cave_counts=magical_sword_cave_counts)
    if offense_pacing is not Pacing.OFF or defense_pacing is not Pacing.OFF:
        rules = replace(rules, offense_pacing=offense_pacing, defense_pacing=defense_pacing,
                        pacing_hearts=pacing_hearts if offense_pacing is not Pacing.OFF else None)
    if recorder_warps:
        rules = replace(rules, recorder_warps=True)
    if swordlish_pieces:
        rules = replace(rules, swordlish_pieces=swordlish_pieces, start_triforce_pieces=start_triforce_pieces)
    if gates.any:
        rules = replace(rules, screen_needs=(*rules.screen_needs, *gates.screen_needs()),
                        maze_hints=gates.maze_hints(), front_door_barred=gates.gated_screens(),
                        maze_hints_need_book=maze_hints_need_book and bool(gates.maze_hints()))
    if progressive_items:
        # PI-LOGIC-02: Ganon (the "arrow" family) needs the bow and two arrow upgrades
        rules = replace(rules, counts_lines=True,
                        family_lists=_family(rules.family_lists, "arrow", frozenset({Item.BOW, TWO_ARROWS})))
    if shop_items_in_pool:
        # PI-LOGIC-03: Gohma (the "bow" family) needs the bow and an arrow upgrade; PI-LOGIC-04:
        # a burnable screen's entrance needs a candle; PI-LOGIC-05: E4/E5 are skipped; the shop
        # wares join the pool, so no vanilla ware counts toward a line; and the baits join the pool
        # (docs/zora-extras.md section 10), so the bait rule applies.
        rules = replace(rules, counts_lines=True, counts_shop_wares=False, checks_front_doors=False,
                        bait_in_pool=True,
                        family_lists=_family(rules.family_lists, "bow", frozenset({Item.BOW, ONE_ARROW})),
                        screen_needs=(*rules.screen_needs, (BURNABLE_SCREENS, ONE_CANDLE)))
    return rules


class _ClosureReach:
    """HeartReach by the closure's own predicates, for a held set (AcceptanceCheck.hearts_held)."""

    def __init__(self, check: "AcceptanceCheck", held: frozenset[int]) -> None:
        self.check, self.held = check, held

    def reaches(self, place: "PoolPlace") -> bool:
        from .steps.extra_pool_items import (
            CaveSlotPlace,
            ExtraSlotPlace,
            ItemCellarPlace,
            LevelRoomPlace,
            ShopWarePlace,
            is_extra_slot_collected,
        )
        check, held = self.check, self.held
        if isinstance(place, LevelRoomPlace):
            return check.can_enter(place.level.level_num, held) and check.can_reach_room(
                place.level.level_num, place.room.room_num, held)
        if isinstance(place, ItemCellarPlace):
            return check.can_enter(place.level.level_num, held) and check.reaches_cellar(
                place.level.level_num, place.cellar.room_num, held)
        if isinstance(place, CaveSlotPlace):
            if place.slot == "armos":
                return True
            if place.slot == "coast":
                return Item.LADDER in held
            return check.reaches_cave(Destination.WHITE_SWORD_CAVE, held)
        if isinstance(place, ShopWarePlace):
            return check.shop_door_reached(place.shop.destination, held)
        if isinstance(place, ExtraSlotPlace):
            return is_extra_slot_collected(place.slot, check.caves, held, check.rules)
        raise TypeError(place)


def logic_walk_rules(rules: LogicRules) -> LogicRules:
    """The same rules on the logic walk (docs/archipelago.md "The two walks"): Archipelago's
    access rules, FINISH's sanity check and E10 (AcceptanceCheck.reaches_ganon_before_shutters_open);
    generation's walks otherwise stay the spec's."""
    return replace(rules, walk=LOGIC_WALK)


def _screen_needs(screen: int) -> frozenset[int]:
    return DEFAULT_RULES.needs(screen)


@dataclass
class AcceptanceCheck:
    levels: list[Level]              # the nine levels being judged
    item_shuffle_result: ItemShuffleResult
    overworld: Overworld
    caves: CaveShuffle
    rules: LogicRules = DEFAULT_RULES
    # Items held from the start besides the wooden sword: none in ZORA. Archipelago's FINISH grants
    # the items this player receives from other worlds (docs/archipelago.md, R4's second walk).
    granted: frozenset[int] = frozenset()
    # The ZORA extras' caves and joined shop wares, which Offense Item Pacing's heart count reads
    extras: "ExtraPoolItems | None" = None
    _walks: dict[tuple[int, int | None, frozenset[int]], Walk] = field(default_factory=dict)

    def _level(self, level_num: int) -> Level:
        return next(level for level in self.levels if level.level_num == level_num)

    def _walk(self, level: int, target: int | None, held: frozenset[int]) -> Walk:
        """The inventory walk toward a target. It depends on the held set
        only through the family lists and the ladder (VA-REJ-18's rows), and
        on the logic walk through the Triforce of Power (the last-boss shutters)."""
        walk = self.rules.walk
        key = (level, target, held & (family_items(self.rules.family_lists)
                                      | {Item.LADDER, Item.TRIFORCE_OF_POWER, Item.BAIT}))
        if key not in self._walks:
            is_open = walk.triforce_of_power_opens and Item.TRIFORCE_OF_POWER in held
            self._walks[key] = walk_level(self._level(level), held, is_last_boss_open=is_open, uses_families=True,
                                          target=target, family_lists=self.rules.family_lists, walk_rules=walk,
                                          goriya_hungry=self.rules.bait_in_pool and Item.BAIT not in held)
        return self._walks[key]

    # The public checks below are the closure's own tests, each on one target and a held set;
    # Archipelago's access rules are derived from them (logic.py, docs/archipelago.md "Logic").

    def reaches_screen(self, screen: int, held: frozenset[int]) -> bool:
        """VA-REJ-07 (i): a screen's entrance needs are held."""
        return self.rules.needs(screen) <= held

    def can_enter(self, level: int, held: frozenset[int]) -> bool:
        """VA-REJ-07 (i), VA-REJ-08: the level's entry door is reached (level 9: and the long
        items held, and level-9 entry: the eight triforces, or with ASNB four swords)."""
        needs = self.rules.needs(self.caves.entry_door(level))
        if not self.meets_pacing(level, held):
            return False
        if self.rules.recorder_warps and level != LEVEL_9 and Item.RAFT in needs and Item.RAFT not in held:
            # Recorder Warping: the recorder takes Link to the entry door, raft or none
            needs = (needs - {Item.RAFT}) | {Item.RECORDER}
        if level == LEVEL_9:
            # Bug fix (owner decision 2026-10-08, beta 2): a level-9 item is collected only once
            # level 9 can be entered. VA-REJ-07 asked level-9 entry only as E1's target, so an
            # item a triforce needs could sit in level 9 alone and the seed was accepted though
            # unbeatable. Only Shop Items in the Item Pool can make that happen (the arrow Gohma
            # needs, the candle burnable screens need); every other need is a long item, which
            # level 9's own door needs already.
            needs |= self.rules.level_9_entry_needs
        return needs <= held

    def meets_pacing(self, level: int, held: frozenset[int]) -> bool:
        """Offense and Defense Item Pacing: the sword and ring counts the level asks for are held."""
        return self.rules.pacing_needs(level) <= held

    def can_reach_room(self, level: int, room: int, held: frozenset[int]) -> bool:
        """VA-REJ-07 (ii)-(iv) for a target room. The logic walk judges arrival on the walk
        without a target (WalkRules.through_target)."""
        target = self._level(level).block.room(room)
        layout = target.room_type
        walk_target = None if self.rules.walk.through_target else room
        return (self._walk(level, walk_target, held).accepts(self._level(level), room)
                and (not is_family_blocked(target, held, self.rules.family_lists) or layout > FAMILY_EXEMPT_LAYOUT)
                and (Item.LADDER in held or layout not in LADDER_LAYOUTS))

    def reaches_cellar(self, level: int, cellar: int, held: frozenset[int]) -> bool:
        """An item cellar (by its own room number) is one the level's walk enters."""
        return cellar in self._walk(level, None, held).cellars

    def _can_reach_item(self, level: int, item: int, held: frozenset[int]) -> bool:
        """A level item: located as the level's room (then item cellar)
        holding it; none found is unreachable."""
        place = item_room(self._level(level), item)
        if place is not None:
            return self.can_reach_room(level, place, held)
        cellar = item_cellar(self._level(level), item)
        return cellar is not None and self.reaches_cellar(level, cellar, held)

    def completes(self, level: int, held: frozenset[int]) -> bool:
        """The level's Triforce is reached (entry aside): the room holding it, or with Allow
        Triforces in Stairways the item cellar holding it, once the walk enters that cellar from
        the room with its stairs (docs/zora-extras.md section 13)."""
        return self._can_reach_item(level, Item.TRIFORCE, held)

    def reaches_ganon(self, held: frozenset[int]) -> bool:
        """Ganon's room reached (entry aside) and his family list unblocked: the bow and the
        silver arrows, PI-LOGIC-02's two arrow upgrades under Progressive Items."""
        ganon = next(room for room in self._level(LEVEL_9).rooms if room.enemy == GANON_LIST)
        return (self.can_reach_room(LEVEL_9, ganon.room_num, held)
                and not is_family_blocked(ganon, held, self.rules.family_lists))

    def takes_triforce_of_power(self, held: frozenset[int]) -> bool:
        """The logic walk's Triforce of Power, Ganon's fixed drop: level 9 entered (its door, the
        long items and level-9 entry) and Ganon reached."""
        return self.can_enter(LEVEL_9, held) and self.reaches_ganon(held)

    def reaches_ganon_before_shutters_open(self) -> bool:
        """E10, ZORA's own rule (owner, 2026-10-18; docs/deviations.md): with everything E1's closure
        collects held, level 9 is entered and Ganon's room reached while the last-boss shutters are
        shut. Those shutters, on Ganon's room and on the rooms facing Zelda's (VA-REJ-03 step 8),
        open only once Ganon's Triforce of Power is taken (emulator, 2026-10-18), so a Ganon reached
        only through Zelda's room is never reached: the seed is unbeatable. E3 walks with those
        shutters open and E1 never targets Ganon, so the spec accepts such seeds. Judged on the
        logic walk, whose rooms are the emulator's (the spec walk misses Ganon in beatable seeds)."""
        shut = self._with_rules(replace(self.rules, walk=replace(self.rules.walk, triforce_of_power_opens=False)))
        held = frozenset(shut.closure()[0])          # nothing collected past the shutters
        return self._with_rules(logic_walk_rules(self.rules)).takes_triforce_of_power(held)

    def _with_rules(self, rules: LogicRules) -> "AcceptanceCheck":
        """The same check under other rules (itself when they are its own, keeping its walks)."""
        if rules == self.rules:
            return self
        return AcceptanceCheck(self.levels, self.item_shuffle_result, self.overworld, self.caves, rules, self.granted,
                               self.extras)

    def reaches_cave(self, cave: Destination, held: frozenset[int]) -> bool:
        """A one-item cave (the white-sword cave, a ZORA extra's): its first screen's needs are
        held (hearts aside: the heart check's)."""
        screens = self.caves.movable_screens(cave)
        return bool(screens) and self.reaches_screen(screens[0], held)

    def knows_maze_path(self, hint_shop: Destination, held: frozenset[int]) -> bool:
        """A maze's hint: a door of the hint shop that sells its path reached, and with Book to
        Understand NPCs (B48) the book held, without which the shop's text is text 0."""
        return self.shop_door_reached(hint_shop, held) and (not self.rules.maze_hints_need_book
                                                             or Item.BOOK in held)

    def collects(self, place: TrackedPlace, held: frozenset[int]) -> bool:
        """VA-REJ-07: whether the closure collects a tracked item's place with this held set."""
        if place.slot == "armos":
            return True                    # held from the start
        if place.slot == "white_sword":
            return self.reaches_cave(Destination.WHITE_SWORD_CAVE, held)
        if place.slot == "coast":
            return Item.LADDER in held
        if (shop := shop_of_slot(place.slot)) is not None:
            # a joined shop ware (SI-JOIN-01): collected once a door of its shop is reached,
            # and the letter held for the potion shop (Shuffle Blue Potion)
            return self.shop_door_reached(shop, held) and (shop != Destination.POTION_SHOP or Item.LETTER in held)
        if place.slot in EXTRA_SLOT_CAVES:
            # a ZORA extra's cave (docs/zora-extras.md): as the white-sword slot, by its
            # screen needs; the magical-sword cave's hearts are the heart check's
            return self.reaches_cave(EXTRA_SLOT_CAVES[place.slot], held)
        if place.level is not None:
            return self.can_enter(place.level, held) and self._can_reach_item(place.level, place.item, held)
        return False

    def collects_everything(self) -> bool:
        """E1 (VA-REJ-07): the closure reaches every tracked item type and
        level-9 entry; and, ZORA's own rule (owner, 2026-10-15; docs/deviations.md), every
        randomized maze's hint. The cave walk keeps each hint shop off its own maze, but with both
        mazes randomized it can leave the Lost Hills' shop past the Dead Woods while the Dead Woods'
        shop is past the Lost Hills: a loop, neither path ever learned. Every other gate in front
        of a shop is a tracked item, so this target rejects only such loops."""
        return self.target() <= self.closure()[0]

    def target(self) -> set[int]:
        """E1's target: level-9 entry, every tracked item type (the wooden sword too where it is
        part of the target, VA-REJ-22) and every randomized maze's hint."""
        target = {LEVEL9_ENTRY} | {place.item for place in self.item_shuffle_result.tracked}
        if self.rules.level_9_gate.kind is GateKind.ITEM:
            target.add(LEVEL9_ITEM)
        if self.rules.wood_sword_in_target:
            target.add(Item.WOOD_SWORD)
        return target | {hint for hint, _shop in self.rules.maze_hints}

    def closure(self) -> tuple[set[int], set[int]]:
        """VA-REJ-07's closure from the wooden sword (VA-REJ-22: under Normal and Wood Sword Only) and
        the tracked item in the armos slot (0x10D05), if one is there: the held set and the
        completed dungeons when nothing more changes."""
        tracked = self.item_shuffle_result.tracked
        start = {Item.WOOD_SWORD} if self.rules.wood_sword_from_start else set()
        held = start | {place.item for place in tracked if place.slot == "armos"} | self.granted
        completed: set[int] = set()
        swords: set[int] = set()          # ASNB: the tracked sword records collected, by index
        baits: set[int] = set()           # Shuffle Major Shop Items: the bait records collected
        bait_records = sum(place.item == Item.BAIT for place in tracked) if self.rules.bait_in_pool else 0
        changed = True
        brought_by_white_sword = self.rules.wooden_sword_state is WoodenSwordState.NO_WOODEN_SWORD
        while changed:
            changed = False
            if brought_by_white_sword and Item.WHITE_SWORD in held and Item.WOOD_SWORD not in held:
                held.add(Item.WOOD_SWORD)        # VA-REJ-22: No Wood Sword's first sword is the white
            if self.rules.swordlish_pieces and Item.WOOD_SWORD not in held and (
                    Item.WHITE_SWORD in held or self.rules.swordlish_opens(completed)):
                held.add(Item.WOOD_SWORD)        # VA-REJ-23: N pieces held, or the white sword
            frozen = frozenset(held)
            for index, place in enumerate(tracked):
                if self.rules.counts_swords and place.item in SWORD_LINE:
                    if index not in swords and self.collects(place, frozen):
                        swords.add(index)
                        held.add(place.item)
                        changed = True
                elif bait_records and place.item == Item.BAIT:
                    if index not in baits and self.collects(place, frozen):
                        baits.add(index)
                        changed = True
                elif place.item not in held and self.collects(place, frozen):
                    held.add(place.item)
                    changed = True
            if bait_records and Item.BAIT not in held and len(baits) == bait_records:
                held.add(Item.BAIT)              # every bait found: now usable
                changed = True
            for level in DUNGEONS:
                if level not in completed and self.can_enter(level, frozen) \
                        and self.completes(level, frozen):
                    completed.add(level)
                    changed = True
            if LEVEL9_ENTRY not in held and (self.sword_count(swords, frozen) >= SWORDS_FOR_LEVEL_9
                                             if self.rules.level_9_by_swords
                                             else self.rules.opens_level_9(completed)):
                held.add(LEVEL9_ENTRY)
                changed = True
            if (self.rules.level_9_gate.kind is GateKind.ITEM and LEVEL9_ITEM not in held
                    and self.holds_gate_item(frozenset(held))):
                held.add(LEVEL9_ITEM)
                changed = True
            for hint, hint_shop in self.rules.maze_hints:
                if hint not in held and self.knows_maze_path(hint_shop, frozenset(held)):
                    held.add(hint)
                    changed = True
            if (self.rules.walk.triforce_of_power_opens and Item.TRIFORCE_OF_POWER not in held
                    and self.takes_triforce_of_power(frozenset(held))):
                held.add(Item.TRIFORCE_OF_POWER)     # the logic walk's last-boss shutters open
                changed = True
            if self.rules.counts_lines:
                counts = self.line_counts(frozenset(held))
                changed |= not counts <= held
                held |= counts
            if self.rules.paces:
                counts = self.pacing_counts(swords, frozenset(held))
                changed |= not counts <= held
                held |= counts
        return held, completed

    def pacing_counts(self, swords: set[int], held: frozenset[int]) -> set[int]:
        """Offense and Defense Item Pacing: the sword and ring count pseudo-items a held set gives. The
        swords are sword_count's (items, not tiers); the rings the held ring items plus (Shop Items in the
        Item Pool off) the vanilla blue ring ware once a door of its shop is reached, as line_counts
        counts a line. Rupees are not modeled."""
        rings = len(held & RING_LINE)
        if self.rules.counts_shop_wares and self.ware_door_reached(Item.BLUE_RING, held):
            rings += 1
        return {*SWORD_COUNTS[:self.pacing_sword_count(swords, held)], *RING_COUNTS[:rings]}

    def pacing_sword_count(self, swords: set[int], held: frozenset[int]) -> int:
        """sword_count with Offense Item Pacing's heart model (rules.pacing_hearts): a sword that lies in a
        sword cave counts only once the hearts held (the starting hearts, the heart containers reachable with
        `held` and the take-any allowance, as the heart check counts them) meet the cave's requirement.
        Without the model, sword_count itself."""
        model = self.rules.pacing_hearts
        if model is None:
            return self.sword_count(swords, held)
        from .steps.item_shuffle_result import MAGICAL_SWORD_SLOT
        from .steps.randomize_magical_sword import WHITE_SWORD_SLOT
        hearts = self.hearts_held(held, model)
        requirements = {WHITE_SWORD_SLOT: model.white_sword, MAGICAL_SWORD_SLOT: model.magical_sword}
        counted = sum(hearts >= requirements.get(self.item_shuffle_result.tracked[index].slot or "", 0)
                      for index in swords)
        cave = (self.rules.magical_sword_cave_counts and self.reaches_cave(Destination.MAGICAL_SWORD_CAVE, held)
                and hearts >= model.magical_sword)
        from_start = 0 if self.rules.wood_sword_in_pool else HELD_FROM_START_SWORDS
        return from_start + counted + cave + len(self.granted & SWORD_LINE)

    def hearts_held(self, held: frozenset[int], model: PacingHearts) -> int:
        """The hearts a player has with `held`: the starting hearts, the take-any caves' allowance and the
        heart containers of the pool's places reached (check_magical_sword_hearts' count, with the
        closure's own reach); the white-sword cave's own container counts once the others meet its requirement."""
        from .steps.extra_pool_items import ExtraPoolItems
        from .steps.randomize_magical_sword import (
            count_reachable_heart_containers,
            heart_container_places,
            reachable_take_any_hearts,
            take_any_heart_allowance,
        )
        extras = self.extras if self.extras is not None else ExtraPoolItems()
        take_any = take_any_heart_allowance(reachable_take_any_hearts(self.overworld, held, self.rules))
        places = heart_container_places(self.levels, self.item_shuffle_result, extras)
        reachable = count_reachable_heart_containers(places, _ClosureReach(self, held), model.starting + take_any,
                                                     model.white_sword)
        return model.starting + take_any + reachable

    def holds_gate_item(self, held: frozenset[int]) -> bool:
        """FP-TRIF-06: the item level 9's entrance asks for is held. A sword, a candle or an arrow is
        any of its line, or (Shop Items in the Item Pool off) a door reached of a shop selling its
        vanilla ware, as PI-LOGIC-01 counts a line; every other item is a tracked item."""
        item = self.rules.level_9_gate.item
        if item is Item.WOOD_SWORD:
            return bool(held & SWORD_LINE)
        for line, ware, at_least in LINE_SHOP_WARES:
            if item is ware:
                return (bool(held & line) or at_least[0] in held
                        or (self.rules.counts_shop_wares and self.ware_door_reached(ware, held)))
        return item in held

    def sword_count(self, swords: set[int], held: frozenset[int]) -> int:
        """ASNB: the swords held, counted as PI-LOGIC-01 counts a line: the wooden-sword cave's,
        the tracked sword records collected (`swords`), the magical-sword cave's own sword once its
        cave is reached (hearts aside: the heart check's), and the swords granted."""
        cave = self.rules.magical_sword_cave_counts and self.reaches_cave(Destination.MAGICAL_SWORD_CAVE, held)
        # Archipelago's FINISH: the swords this player receives (one of each code at most)
        received = len(self.granted & SWORD_LINE)
        # Shuffle Wood Sword: the wood sword is one of the tracked records, counted in `swords`
        from_start = 0 if self.rules.wood_sword_in_pool else HELD_FROM_START_SWORDS
        return from_start + len(swords) + cave + received

    def line_counts(self, held: frozenset[int]) -> set[int]:
        """PI-LOGIC-01: the line-count pseudo-items a held set gives: the line's held items,
        plus (Shop Items in the Item Pool off) its vanilla shop ware once a door of a shop
        selling it is reached. Rupees are not modeled."""
        counts: set[int] = set()
        for line, ware, at_least in LINE_SHOP_WARES:
            count = len(held & line)
            if self.rules.counts_shop_wares and self.ware_door_reached(ware, held):
                count += 1
            counts.update(at_least[:count])
        return counts

    def ware_door_reached(self, ware: Item, held: frozenset[int]) -> bool:
        """A door of a shop selling the ware is reached."""
        return any(self.shop_door_reached(cave.destination, held) for cave in self.overworld.caves
                   if isinstance(cave, Shop) and any(item.item == ware for item in cave.items))

    def shop_door_reached(self, shop: Destination, held: frozenset[int]) -> bool:
        """A shop's front door is reached: one of its screens' needs are held."""
        return any(self.reaches_screen(screen, held) for screen in self.caves.movable_screens(shop))

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
                     caves: CaveShuffle, rules: LogicRules = DEFAULT_RULES,
                     granted: frozenset[int] = frozenset(), extras: "ExtraPoolItems | None" = None) -> str | None:
    """VA-REJ-12: E1, E3, ZORA's E10, E4, E5, under Swordless E6 (VA-REJ-22), and, last, E9 (VA-REJ-21)
    in order;
    the first failure's label,
    or None when the pass is accepted. levels: the pass's nine staged levels.
    E4/E5 are skipped under Shop Items in the Item Pool (PI-LOGIC-05).
    granted: items held from the start (AcceptanceCheck.granted; none in ZORA)."""
    checks = AcceptanceCheck(levels, item_shuffle_result, overworld, caves, rules, granted, extras)
    if not checks.collects_everything():
        return "E1"
    if not checks.is_zelda_reachable():
        return "E3"
    if not checks.reaches_ganon_before_shutters_open():
        return "E10"
    if rules.checks_front_doors:
        door = front_door_failure(overworld, caves, rules.front_door_barred)
        if door is not None:
            return "E4" if door.startswith("(a)") else "E5"
        if rules.wooden_sword_state is WoodenSwordState.SWORDLESS and bomb_shop_door_failure(
                overworld, caves, rules.front_door_barred):
            return "E6"                    # VA-REJ-22: Swordless's bomb shop needs a plain front door
    if start_room_is_own_door(levels, overworld):
        return "E9"
    return None


def start_room_is_own_door(levels: list[Level], overworld: Overworld) -> bool:
    """VA-REJ-21 (E9), after the shop checks: some level's start-room number, read as an
    overworld screen, holds that level's door. A coincidence of a dungeon room number with a
    screen number (probable bug, kept: a rebuild MUST reject the same seeds); it fires only when
    the start-room swap (B26) puts a start room on a fixed door's screen, or under C05 = 0 or 2."""
    return any(overworld.screens[level.entrance_room].destination == level.level_num
               for level in sorted(levels, key=lambda level: level.level_num))
