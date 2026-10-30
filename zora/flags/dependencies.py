"""The dependency rules (FL-DEP-01 to FL-DEP-06): refusals, prerequisites, and the
values resolved per seed."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from ..generate.rng import IntRng
from .fields import (
    BOMB_UPGRADE_PERSON_SHUFFLE,
    BOSS_HIT_POINTS,
    CAVE_SHUFFLE,
    COAST_PIN,
    DUNGEON_LAYOUT_SOURCE,
    DUNGEON_MONSTER_SHUFFLE,
    DUNGEON_ROOM_SHUFFLE,
    ENCODE_LEVEL_DATA,
    ENEMY_HIT_POINTS,
    GANON_AND_ZELDA_SHUFFLE,
    GANON_HIT_POINTS_ZERO,
    GANON_MUST_BE_BEATEN,
    HUNGRY_GORIYA_SHUFFLE,
    IMPORTANT_ITEMS_IN_LEVEL_9,
    INERT_TOGGLES,
    LEVEL_9_FIRST_PIN,
    LEVEL_9_REQUIREMENT,
    LEVEL_9_SECOND_PIN,
    MAGICAL_SWORD_HIGHEST,
    MAGICAL_SWORD_HIGHEST_BASE,
    MAGICAL_SWORD_LOWEST,
    MAGICAL_SWORD_LOWEST_BASE,
    MAX_TRIFORCE_PIECES,
    MAXIMUM_BOSS_HEALTH,
    MONSTERS_BETWEEN_LEVELS,
    OPTION_FIELDS,
    PIECE_RANGE_HIGH,
    PIECE_RANGE_LOW,
    PIN_FIELDS,
    START_ITEM_FIELDS,
    START_ITEM_LIMIT,
    START_ITEM_LIMIT_ALL_CHOSEN,
    START_ROOM_MAY_MOVE,
    STARTING_HEARTS,
    STARTING_PIECES,
    TAKE_ANY_ROAD_SHUFFLE,
    TOGGLE_FIELDS,
    WHITE_SWORD_HIGHEST,
    WHITE_SWORD_HIGHEST_BASE,
    WHITE_SWORD_LOWEST,
    WHITE_SWORD_LOWEST_BASE,
    WOODEN_SWORD_CAVE_MOVES,
    WOODEN_SWORD_STATE,
    CaveShuffle,
    DungeonRoomShuffle,
    HitPointChange,
    Level9Requirement,
    OptionField,
    PinnedItem,
    Settings,
    ThreeState,
    ToggleField,
    WoodenSwordState,
)
from .support import DUNGEON_QUESTS_WITHOUT_PERSON_MOVES

# ---------------------------------------------------------------------------
# FL-DEP-01 and FL-DEP-02: refusals and prerequisites
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Refusal:
    """One reason a string is refused: the spec rule and a message for the player."""
    rule: str
    message: str


def refusals(settings: Settings) -> list[Refusal]:
    """FL-DEP-01: the combinations that are refused with a message."""
    found: list[Refusal] = []
    if settings.option(COAST_PIN) == PinnedItem.LADDER:
        found.append(Refusal("FL-DEP-01 rule 1", "the Ladder cannot be pinned to the coast cave"))
    for first, second in combinations(PIN_FIELDS, 2):
        item = PinnedItem(settings.option(first))
        if item.is_item and item == settings.option(second):
            found.append(Refusal("FL-DEP-01 rule 2",
                                 f"{first.setting} and {second.setting} both name the {item.name}"))
    if all(settings.toggle(field) is ThreeState.ON for field in (GANON_HIT_POINTS_ZERO, MAXIMUM_BOSS_HEALTH)):
        found.append(Refusal("FL-DEP-01 rule 3", BOSS_HEALTH_RULE_TEXT))
    if settings.toggle(IMPORTANT_ITEMS_IN_LEVEL_9) is ThreeState.OFF:
        for pin in LEVEL_9_PIN_FIELDS:
            if level_9_pin_needs_entry(settings, pin):
                item_name = PinnedItem(settings.option(pin)).name.replace("_", " ").title()
                found.append(Refusal("FL-DEP-01 rule 5", LEVEL_9_PIN_RULE_TEXT.format(pin=pin.setting,
                                                                                      item=item_name)))
    return found


# FL-DEP-01 rule 5 (the 2026-10-22 export; for C27 an owner-ruled extension): a level-9 pin at an item
# the five-item rule (VA-REJ-08) needs, or at the Wand under Swordless or Random (VA-REJ-22), needs
# Allow Important Items in 9 (B25): with B25 off the item could never be collected.
LEVEL_9_PIN_FIELDS = (LEVEL_9_FIRST_PIN, LEVEL_9_SECOND_PIN)
FIVE_ITEM_RULE_PINS = frozenset({PinnedItem.BOW, PinnedItem.LADDER, PinnedItem.POWER_BRACELET, PinnedItem.RAFT,
                                 PinnedItem.RECORDER})
WAND_RULE_SWORD_STATES = frozenset({WoodenSwordState.SWORDLESS, WoodenSwordState.RANDOM})
LEVEL_9_PIN_RULE_TEXT = "{pin} names the {item}, which needs Allow Important Items in 9 (B25) on"


def level_9_pin_needs_entry(settings: Settings, pin: OptionField) -> bool:
    """FL-DEP-01 rule 5: the pin names an item the walk needs before level 9 (the five-item rule's,
    or the Wand while the swords are Swordless or Random)."""
    item = settings.option(pin)
    return item in FIVE_ITEM_RULE_PINS or (item == PinnedItem.WAND
                                            and settings.option(WOODEN_SWORD_STATE) in WAND_RULE_SWORD_STATES)


# FL-DEP-01 rule 3 (ZORA's rule, owner-ruled deviation 2026-10-22): Set Ganon HP to 0 and Maximum
# Boss Health never both apply. Rule 4 (B47 beside a Book pin) is not applied: ZORA's B47 leaves the
# Book in the pool and the shop alone (owner, 2026-10-22; docs/deviations.md), so a pin may name it.
BOSS_HEALTH_RULE_TEXT = "Set Ganon HP to 0 and Maximum Boss Health cannot both be on"


def without_both_boss_health_rules(asked: Settings, resolved: Settings) -> Settings:
    """FL-DEP-04's rule after resolving for FL-DEP-01 rule 3: B41 and B46 never both come out on.
    B41 is resolved first: on it (as given, or a "?" come up on) turns a possible B46 off; B46 on as
    given turns a possible B41 off. With both "?" and B41 off, B46 keeps its coin. (Both on as given
    is refused.)"""
    if not (resolved.is_on(GANON_HIT_POINTS_ZERO) and resolved.is_on(MAXIMUM_BOSS_HEALTH)):
        return resolved
    loser = GANON_HIT_POINTS_ZERO if asked.toggle(MAXIMUM_BOSS_HEALTH) is ThreeState.ON else MAXIMUM_BOSS_HEALTH
    return resolved.updated(toggles={loser: ThreeState.OFF})


# FL-DEP-02 rule 1: the prerequisite is a cave shuffle that moves non-dungeon caves; the coin's
# one side turns that part on (OW-CAVE-10: C05 = 0 then runs as 2, and 1 as 3).
CAVE_SHUFFLE_MOVES_NON_DUNGEON_CAVES = (CaveShuffle.NON_DUNGEON_CAVES_ONLY, CaveShuffle.ALL_CAVES)
CAVE_SHUFFLE_LEAVES_NON_DUNGEON_CAVES = (CaveShuffle.VANILLA, CaveShuffle.DUNGEON_DOORS_ONLY)
WITH_NON_DUNGEON_PART = {CaveShuffle.VANILLA: CaveShuffle.NON_DUNGEON_CAVES_ONLY,
                         CaveShuffle.DUNGEON_DOORS_ONLY: CaveShuffle.ALL_CAVES}
CAVE_DEPENDENTS = (WOODEN_SWORD_CAVE_MOVES, TAKE_ANY_ROAD_SHUFFLE)
# FL-DEP-02 rule 4: these layout sources turn the two person shuffles off; shapes (3) does not.
LAYOUT_SOURCES_WITHOUT_PERSON_SHUFFLES = DUNGEON_QUESTS_WITHOUT_PERSON_MOVES


def missing_prerequisites(settings: Settings) -> list[Refusal]:
    """The FL-DEP-02 prerequisites that refuse a string: none. Rules 1, 2 and 3 have their coins
    specified (OW-CAVE-10; rule 3 by the 2026-10-22 export, rule 2 by beta 8's) and flipped per seed
    (meet_cave_prerequisite, meet_room_prerequisite, meet_monster_prerequisite), never refused."""
    return []


ROOM_DEPENDENTS = (HUNGRY_GORIYA_SHUFFLE, START_ROOM_MAY_MOVE, GANON_MUST_BE_BEATEN)


def needs_room_prerequisite(settings: Settings) -> bool:
    """FL-DEP-02 rule 2: the hungry-goriya shuffle, the start-room move or Force Ganon Fight (B28,
    B26, B18) on while the dungeon room shuffle is off (C14 = 0, also when C14 = 3 resolved to 0)."""
    return (settings.option(DUNGEON_ROOM_SHUFFLE) == DungeonRoomShuffle.VANILLA
            and any(settings.is_on(dependent) for dependent in ROOM_DEPENDENTS))


def meet_room_prerequisite(settings: Settings, rng: IntRng) -> Settings:
    """FL-DEP-02 rule 2 (beta 8 export): one equal-chance coin per seed, flipped only when the rule
    applies, on resolved settings: C14 becomes 1 (within each dungeon), or B18, B26 and B28 are
    turned off. The side each coin value stands for is this rebuild's own (not normative)."""
    if not needs_room_prerequisite(settings):
        return settings
    if rng.choice((True, False)):
        return settings.updated(options={DUNGEON_ROOM_SHUFFLE: DungeonRoomShuffle.WITHIN_EACH_DUNGEON})
    return settings.updated(toggles=dict.fromkeys(ROOM_DEPENDENTS, ThreeState.OFF))


def needs_cave_prerequisite(settings: Settings) -> bool:
    """FL-DEP-02 rule 1: the wooden-sword or take-any-road cave shuffle (B02, B04) on while Cave
    Shuffle has no non-dungeon part (C05 = 0 or 1). It reads C05 alone (OW-MIX-07)."""
    return (any(settings.is_on(dependent) for dependent in CAVE_DEPENDENTS)
            and settings.option(CAVE_SHUFFLE) in CAVE_SHUFFLE_LEAVES_NON_DUNGEON_CAVES)


def meet_cave_prerequisite(settings: Settings, rng: IntRng) -> Settings:
    """FL-DEP-02 rule 1 (OW-CAVE-10): one equal-chance coin per seed, flipped only when the rule
    applies, on resolved settings (C05 = 4 drawn first). One side turns C05's non-dungeon part on (0
    runs as 2, 1 as 3); the other turns B02 and B04 off, which changes no byte under C05 = 0 or 1
    but does under a mixed overworld quest, whose walk has the non-dungeon part anyway (OW-MIX-07).
    The side each coin value stands for is this rebuild's own (not normative)."""
    if not needs_cave_prerequisite(settings):
        return settings
    if rng.choice((True, False)):
        with_part = WITH_NON_DUNGEON_PART[CaveShuffle(settings.option(CAVE_SHUFFLE))]
        return settings.updated(options={CAVE_SHUFFLE: with_part})
    return settings.updated(toggles=dict.fromkeys(CAVE_DEPENDENTS, ThreeState.OFF))


MONSTER_DEPENDENTS = (MONSTERS_BETWEEN_LEVELS, GANON_AND_ZELDA_SHUFFLE)


def needs_monster_prerequisite(settings: Settings) -> bool:
    """FL-DEP-02 rule 3: moving monsters between levels (B36) or shuffling Ganon and Zelda (B33) on
    while the dungeon monster shuffle (B32) is off."""
    return settings.toggle(DUNGEON_MONSTER_SHUFFLE) is ThreeState.OFF and any(
        settings.is_on(dependent) for dependent in MONSTER_DEPENDENTS)


def meet_monster_prerequisite(settings: Settings, rng: IntRng) -> Settings:
    """FL-DEP-02 rule 3 (the 2026-10-22 export): one equal-chance coin per seed, flipped only when the
    rule applies, on resolved settings: B32 turned on (B33 and B36 keep their values), or B33 and B36
    turned off. So afterwards B32 off always comes with B33 and B36 off (PS-MONRD-06). The side each
    coin value stands for is this rebuild's own (not normative)."""
    if not needs_monster_prerequisite(settings):
        return settings
    if rng.choice((True, False)):
        return settings.updated(toggles={DUNGEON_MONSTER_SHUFFLE: ThreeState.ON})
    return settings.updated(toggles=dict.fromkeys(MONSTER_DEPENDENTS, ThreeState.OFF))


def apply_dependencies(settings: Settings) -> Settings:
    """FL-DEP-02 rules 4 and 5, the (not random) rules.

    Rule 4: with second-quest dungeons, mixed, or mixed with shapes (C02 = 1, 2 or 4), the
    hungry-goriya shuffle (B28) and the bomb-upgrade-person shuffle (B29) are turned off.
    Rule 5: level 9 open (C08 = 8) and an item instead of pieces (C08 = 11) are two values of one
    field, so the spec's rule canceling both when both hold never fires; nothing to apply.
    """
    if settings.option(DUNGEON_LAYOUT_SOURCE) in LAYOUT_SOURCES_WITHOUT_PERSON_SHUFFLES:
        return settings.updated(toggles={HUNGRY_GORIYA_SHUFFLE: ThreeState.OFF,
                                         BOMB_UPGRADE_PERSON_SHUFFLE: ThreeState.OFF})
    return settings


def check_dependencies(settings: Settings) -> list[Refusal]:
    """Every reason generation is refused: FL-DEP-01 and the FL-DEP-02 prerequisites."""
    return refusals(settings) + missing_prerequisites(settings)


# ---------------------------------------------------------------------------
# FL-DEP-03: fields whose index is not the value
# ---------------------------------------------------------------------------

class UnresolvedError(ValueError):
    """A derived value was asked of a field still at its random index (resolve it first, FL-DEP-04)."""


def _resolved_index(settings: Settings, option: OptionField) -> int:
    index = settings.option(option)
    if option.is_random(index):
        raise UnresolvedError(f"{option.id} ({option.setting}) is at its random index {index}")
    return index


def _ordered(lowest: int, highest: int) -> tuple[int, int]:
    """FL-DEP-03: if a lowest value is above its highest the two are swapped."""
    return (highest, lowest) if lowest > highest else (lowest, highest)


def white_sword_hearts(settings: Settings) -> tuple[int, int]:
    """FL-DEP-03: the white sword's (lowest, highest) heart requirement, 4 + C20 and 6 - C21."""
    return _ordered(WHITE_SWORD_LOWEST_BASE + settings.option(WHITE_SWORD_LOWEST),
                    WHITE_SWORD_HIGHEST_BASE - settings.option(WHITE_SWORD_HIGHEST))


def magical_sword_hearts(settings: Settings) -> tuple[int, int]:
    """FL-DEP-03: the magical sword's (lowest, highest) heart requirement, 10 + C22 and 14 - C23."""
    return _ordered(MAGICAL_SWORD_LOWEST_BASE + settings.option(MAGICAL_SWORD_LOWEST),
                    MAGICAL_SWORD_HIGHEST_BASE - settings.option(MAGICAL_SWORD_HIGHEST))


def piece_count_range(settings: Settings) -> tuple[int, int]:
    """FL-DEP-03: (low, high) = (C24, 8 - C25), swapped if low is above high; used when C08 is 9 or 10."""
    return _ordered(settings.option(PIECE_RANGE_LOW), MAX_TRIFORCE_PIECES - settings.option(PIECE_RANGE_HIGH))


def pieces_needed(settings: Settings) -> int | None:
    """FL-DEP-03: C08 = i for i from 0 to 7 needs 8 - i pieces; None when level 9 is not gated by a count."""
    index = _resolved_index(settings, LEVEL_9_REQUIREMENT)
    if index <= Level9Requirement.ONE_PIECE:
        return MAX_TRIFORCE_PIECES - index
    return None


def starting_hearts(settings: Settings) -> int:
    """FL-DEP-03: C16 = i for i from 0 to 15 gives i + 1 hearts."""
    return _resolved_index(settings, STARTING_HEARTS) + 1


def starting_pieces(settings: Settings) -> int:
    """FL-ENC-04: C18 = i for i from 0 to 8 gives i pieces."""
    return _resolved_index(settings, STARTING_PIECES)


def start_item_limit(settings: Settings) -> int | None:
    """FL-DEP-03: C17 = 0 allows every chosen start item (None); i from 1 to 21 allows at most i - 1."""
    index = _resolved_index(settings, START_ITEM_LIMIT)
    if index == START_ITEM_LIMIT_ALL_CHOSEN:
        return None
    return index - 1


def chosen_start_items(settings: Settings) -> tuple[ToggleField, ...]:
    """FL-DEP-03: the start items whose fields (B57 to B78 and B85) are on."""
    return tuple(item for item in START_ITEM_FIELDS if settings.is_on(item))


def enemy_hit_point_change(settings: Settings) -> HitPointChange:
    """FL-DEP-03: C09, 1 or 2 move each value by up to 2 or 4 (PS-HP-01); 3 sets all to zero."""
    return HitPointChange(_resolved_index(settings, ENEMY_HIT_POINTS))


def boss_hit_point_change(settings: Settings) -> HitPointChange:
    """FL-DEP-03: C10, as the enemy field (PS-HP-02)."""
    return HitPointChange(_resolved_index(settings, BOSS_HIT_POINTS))


# ---------------------------------------------------------------------------
# FL-DEP-04: random and possible values are resolved per seed
# ---------------------------------------------------------------------------

def is_resolved(settings: Settings) -> bool:
    """Whether no option field is at a random index and no three-state field is possible."""
    return (all(not option.is_random(settings.option(option)) for option in OPTION_FIELDS)
            and all(settings.toggle(toggle) is not ThreeState.POSSIBLE for toggle in TOGGLE_FIELDS))


# The three-state fields whose "?" is resolved: every one but Encode level data (B82), a plain
# on/off setting that never takes "?" (owner ruling, 2026-10-06; generation refuses it).
RESOLVED_TOGGLES = tuple(toggle for toggle in TOGGLE_FIELDS if toggle != ENCODE_LEVEL_DATA)


def resolve(settings: Settings, rng: IntRng) -> Settings:
    """FL-DEP-04: pick each random index uniformly among its alternatives and flip one fair coin per
    possible field. Afterwards, when the wooden-sword state is swordless or a level-9 pin names one of
    the five-item rule's items (FL-DEP-01 rule 5), and B25 was possible, B25 is on whatever its coin
    said. The order of the draws is this rebuild's own (not normative)."""
    options = dict(settings.options)
    for option in OPTION_FIELDS:
        index = options[option.id]
        if option.is_random(index):
            options[option.id] = rng.choice(option.random_choices[index])
    toggles = dict(settings.toggles)
    for toggle in RESOLVED_TOGGLES:
        if toggles[toggle.id] is ThreeState.POSSIBLE:
            toggles[toggle.id] = rng.choice((ThreeState.OFF, ThreeState.ON))
    swordless = options[WOODEN_SWORD_STATE.id] == WoodenSwordState.SWORDLESS
    long_item_pinned = any(options[pin.id] in FIVE_ITEM_RULE_PINS for pin in LEVEL_9_PIN_FIELDS)
    if (swordless or long_item_pinned) and settings.toggle(IMPORTANT_ITEMS_IN_LEVEL_9) is ThreeState.POSSIBLE:
        # FL-DEP-04's rules after resolving: swordless, or a level-9 pin at a five-item-rule item
        # (FL-DEP-01 rule 5; a pinned Wand needs it only when swordless, the rule before)
        toggles[IMPORTANT_ITEMS_IN_LEVEL_9.id] = ThreeState.ON
    return Settings(options, toggles)


# ---------------------------------------------------------------------------
# FL-DEP-05: two three-state fields select no generation setting
# ---------------------------------------------------------------------------

def generation_settings(settings: Settings) -> Settings:
    """FL-DEP-05: the settings as the generator sees them, with B14 and B16 off whatever they decoded to.

    Both fields are still decoded and displayed from the original settings; heart containers join the
    item pool through the item scope (C06 = 3, PS-ITEM-02), not through B16.
    """
    return settings.updated(toggles=dict.fromkeys(INERT_TOGGLES, ThreeState.OFF))
