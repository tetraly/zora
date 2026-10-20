"""The support matrix (FL-SUP-01 to FL-SUP-04, FL-OFF-07, FL-ALT-02 to FL-ALT-04): which values ZORA
produces."""
from __future__ import annotations

from enum import Enum

from .fields import (
    ARMOS_PIN,
    BOOK_TO_UNDERSTAND_NPCS,
    BOSS_HIT_POINTS,
    CAVE_SHUFFLE,
    DO_NOT_SORT_SHAPES,
    DUNGEON_LAYOUT_SOURCE,
    DUNGEON_ROOM_SHUFFLE,
    ENCODE_LEVEL_DATA,
    ENEMY_HIT_POINTS,
    FORCE_OVERWORLD_BLOCK,
    GANON_HIT_POINTS_ZERO,
    HINT_STYLE,
    IMPORTANT_ITEMS_IN_LEVEL_9,
    ITEM_SHUFFLE_SCOPE,
    LEVEL_9_FIRST_PIN,
    LEVEL_9_SECOND_PIN,
    LOST_WOODS_SHORTCUT,
    MAGICAL_SWORD_HIGHEST,
    MAGICAL_SWORD_LOWEST,
    MONEY_OR_LIFE_ROOMS,
    MONEY_OR_LIFE_TOLL,
    MOST_OPEN_STAIRS_REMOVED,
    ONE_HIT_KNOCK_OUT,
    OPTION_FIELDS,
    OVERWORLD_QUEST,
    PERMANENT_SWORD_BEAM,
    PIECE_RANGE_HIGH,
    PIECE_RANGE_LOW,
    RIVER_BRIDGES,
    START_ITEM_LIMIT,
    START_ROOM_MAY_MOVE,
    START_SCREEN,
    STARTING_HEARTS,
    STARTING_PIECES,
    TOGGLE_FIELDS,
    UNIVERSAL_DROPS_IN_SHAPES,
    WHITE_SWORD_CAVE_PIN,
    WHITE_SWORD_FROM_FIVE_HEARTS,
    WHITE_SWORD_HIGHEST,
    WHITE_SWORD_LOWEST,
    WOOD_SWORD_CAVE_BEHIND_BLOCKS,
    WOODEN_SWORD_STATE,
    CaveShuffle,
    DungeonLayoutSource,
    DungeonRoomShuffle,
    HintStyle,
    HitPointChange,
    ItemShuffleScope,
    OptionField,
    OverworldQuest,
    Settings,
    StartScreen,
    ThreeState,
    ToggleField,
    WoodenSwordState,
)

# ---------------------------------------------------------------------------
# FL-SUP-01 to FL-SUP-04: the support matrix
# ---------------------------------------------------------------------------

class Support(Enum):
    """Whether the MVP produces a field's value (FL-SUP-01: "supported" / "not supported in MVP")."""
    SUPPORTED = "supported"
    NOT_PRODUCED = "not produced"


MVP_BASELINE_STARTING_HEARTS = 2          # C16: 3 hearts (FP-START-01)
# PS-ITEM-12: the pins level 9's places may take: the Book, both boomerangs, a Heart Container, the
# Magical Key, the red candle, the red ring, the silver arrow, the White Sword and Non-Heart
LEVEL_9_PINS = frozenset({1, 2, 4, 6, 7, 11, 12, 13, 15, 16})
# FL-SUP-02: the MVP baseline index of each option field not at index 0 (10 of 27).
MVP_BASELINE_OPTIONS: dict[str, int] = {
    DUNGEON_LAYOUT_SOURCE.id: DungeonLayoutSource.GENERATED_SHAPES,
    HINT_STYLE.id: HintStyle.MIXED,
    START_SCREEN.id: StartScreen.EASY_SHUFFLE,
    CAVE_SHUFFLE.id: CaveShuffle.ALL_CAVES,
    ITEM_SHUFFLE_SCOPE.id: ItemShuffleScope.FULL,
    ENEMY_HIT_POINTS.id: HitPointChange.UP_TO_2,
    BOSS_HIT_POINTS.id: HitPointChange.UP_TO_2,
    DUNGEON_ROOM_SHUFFLE.id: DungeonRoomShuffle.FULL,
    STARTING_HEARTS.id: MVP_BASELINE_STARTING_HEARTS,
    START_ITEM_LIMIT.id: 1,                # at most 0 start items
}
# FL-SUP-03: the three-state fields on in the MVP baseline (32 of 91); every other field is off.
MVP_BASELINE_ON: tuple[str, ...] = (
    "B01", "B02", "B04", "B08", "B09", "B10", "B11", "B12", "B13", "B14", "B15", "B16", "B18", "B19", "B20",
    "B22", "B23", "B27", "B28", "B29", "B31", "B32", "B33", "B34", "B35", "B36", "B40", "B42", "B43", "B49",
    "B54", "B82",
)


def mvp_baseline_settings() -> Settings:
    """FL-SUP-02 and FL-SUP-03: the one supported value of every field (level encoding on)."""
    return Settings.zero().updated(options=MVP_BASELINE_OPTIONS, toggles=dict.fromkeys(MVP_BASELINE_ON, ThreeState.ON))


# FL-OFF-07: the three-state fields with a turn-off value (off; 23 fields).
TURN_OFF_TOGGLES: tuple[str, ...] = (
    "B01", "B08", "B09", "B10", "B11", "B12", "B13", "B14", "B15", "B16", "B19", "B22", "B23", "B27", "B28",
    "B29", "B31", "B34", "B36", "B40", "B42", "B49", "B54",
)
# FL-SUP-03's further off values: Shuffle Wood Sword Cave (B02) off (OW-CAVE-12; beta 6).
SPEC_TURN_OFF_TOGGLES: tuple[str, ...] = ("B02",)
# Turn-off fields whose "?" is not produced, though their off is: Shuffle Bomb Upgraders (B29)
# (FL-SUP-01: FL-DEP-02 rule 4 meets its "?" under supported values; owner, beta 5) and Shuffle Wood
# Sword Cave (B02) (FL-SUP-03: FL-DEP-02 rule 1 meets its "?" under supported values).
TURN_OFF_TOGGLES_NOT_RANDOM: tuple[str, ...] = ("B29", "B02")
# ZORA's own off values for fields the spec gives none (owner rulings), beside FL-OFF-07's:
#   B04 (2026-10-07): the four take-any-road caves keep their PRG0 screens, so that Extra Power
#   Bracelet Blocks, which conflicts with B04 on, can be used.
OWNER_TURN_OFF_TOGGLES: tuple[str, ...] = ("B04",)
# FL-OFF-07: the option fields with turn-off values, and those values (5 fields, 26 values).
TURN_OFF_OPTIONS: dict[str, frozenset[int]] = {
    START_SCREEN.id: frozenset({StartScreen.NORMAL}),
    ENEMY_HIT_POINTS.id: frozenset({HitPointChange.NORMAL}),
    BOSS_HIT_POINTS.id: frozenset({HitPointChange.NORMAL}),
    DUNGEON_ROOM_SHUFFLE.id: frozenset({DungeonRoomShuffle.WITHIN_EACH_DUNGEON}),
    START_ITEM_LIMIT.id: frozenset(range(START_ITEM_LIMIT.count)) - {MVP_BASELINE_OPTIONS[START_ITEM_LIMIT.id]},
}
# The start-item fields FL-SUP-03 supports on: all twenty-three, B57 to B78 and B85 (FP-START-02 to
# FP-START-05; the last fourteen from the 2026-10-15 export). A start Book lifts the maze hints'
# need for the book under Book to Understand NPCs (B48; pipeline.extra_options).
START_ITEM_TOGGLES: tuple[str, ...] = (*(f"B{number}" for number in range(57, 79)), "B85")
# FL-SUP-03's further three-state values (2026-10-10 export): Force Overworld Block (B81) on and
# "?" (OW-CAVE-08; "?" is a coin per seed, FL-DEP-04), Allow OW Blocks of Wood Sword (B03) on.
ALTERNATIVE_TOGGLES: dict[str, frozenset[ThreeState]] = {
    FORCE_OVERWORLD_BLOCK.id: frozenset({ThreeState.ON, ThreeState.POSSIBLE}),
    # Allow OW Blocks of Wood Sword (B03) on (OW-CAVE-07), and so "?" (owner ruling 2026-10-04)
    WOOD_SWORD_CAVE_BEHIND_BLOCKS.id: frozenset({ThreeState.ON, ThreeState.POSSIBLE}),
    # FL-SUP-03: every start item on, and "?" (a coin per seed, FL-DEP-04): Hopla's three (B57, B60,
    # B64; F12 export), Random%'s six (B59, B61, B63, B73, B77, B78; FP-START-05) and the other
    # fourteen (B58, B62, B65-B72, B74-B76, B85; FP-START-02 to FP-START-04, 2026-10-15 export)
    **{field_id: frozenset({ThreeState.ON, ThreeState.POSSIBLE}) for field_id in START_ITEM_TOGGLES},
    # Allow Important Items in 9 (B25) on (VA-REJ-08), and so "?" (owner ruling 2026-10-11: Random
    # is supported where on and off both are)
    IMPORTANT_ITEMS_IN_LEVEL_9.id: frozenset({ThreeState.ON, ThreeState.POSSIBLE}),
    # Shuffle Dungeon Start Room (B26) on (PS-START), and "?" (FL-SUP-03, L36)
    START_ROOM_MAY_MOVE.id: frozenset({ThreeState.ON, ThreeState.POSSIBLE}),
    # Remove Most Open Stairs (B30) on (PS-OSTAIR), and "?" (FL-SUP-03, L25; FL-DEP-04)
    MOST_OPEN_STAIRS_REMOVED.id: frozenset({ThreeState.ON, ThreeState.POSSIBLE}),
    # Book to Understand NPCs (B48) on (HT-BOOK-01, HT-BOOK-02), and "?" (FL-SUP-03, L26; FL-DEP-04)
    BOOK_TO_UNDERSTAND_NPCS.id: frozenset({ThreeState.ON, ThreeState.POSSIBLE}),
    # Allow Universal Drops In Shapes (B91) on (SH-ROOM-16: the merged T5 list), and "?" (FL-SUP-03;
    # a coin per seed, FL-DEP-04)
    UNIVERSAL_DROPS_IN_SHAPES.id: frozenset({ThreeState.ON, ThreeState.POSSIBLE}),
    # The November tournament's settings (FL-SUP-03, 2026-10-17 export): Set Ganon HP to 0 (B41,
    # PS-HP-06), Permanent Sword Beam (B52, FP-BEAM-01) and OHKO (B53, FP-OHKO-01) on, and "?" (a coin
    # per seed, FL-DEP-04)
    GANON_HIT_POINTS_ZERO.id: frozenset({ThreeState.ON, ThreeState.POSSIBLE}),
    PERMANENT_SWORD_BEAM.id: frozenset({ThreeState.ON, ThreeState.POSSIBLE}),
    ONE_HIT_KNOCK_OUT.id: frozenset({ThreeState.ON, ThreeState.POSSIBLE}),
    # Do Not Sort Shapes (B86) on, each set's level numbers a uniform shuffle (SH-NUM-02, SH-NUM-04),
    # and "?" (a coin per seed, FL-DEP-04); the 2026-10-17 export, for Muffle Rug
    DO_NOT_SORT_SHAPES.id: frozenset({ThreeState.ON, ThreeState.POSSIBLE}),
    # Add Bridges to the River (B87, FP-BRIDGE-01) and Add Lost Woods Shortcut (B88, FP-WOODS-01)
    # on, and "?" (a coin per seed, FL-DEP-04); the 2026-10-19 export (2a68977), for beta 7
    RIVER_BRIDGES.id: frozenset({ThreeState.ON, ThreeState.POSSIBLE}),
    LOST_WOODS_SHORTCUT.id: frozenset({ThreeState.ON, ThreeState.POSSIBLE}),
}
# FL-DEP-02 item 4: the dungeon quests that turn the hungry-goriya and bomb-upgrade moves off
# (dependencies.LAYOUT_SOURCES_WITHOUT_PERSON_SHUFFLES applies the rule)
DUNGEON_QUESTS_WITHOUT_PERSON_MOVES = frozenset({DungeonLayoutSource.SECOND_QUEST, DungeonLayoutSource.MIXED,
                                                 DungeonLayoutSource.MIXED_WITH_SHAPES})
# FL-ALT-02 to FL-ALT-04: the alternative values ZORA produces. Owner ruling (2026-10-05): supported
# after the MVP, in place of FL-ALT-01's "not supported in MVP". FL-SUP-02's "Also supported" column
# (spec change L15, 2026-10-09) adds C01 = 2 (OW-MIX) and C06 = 2 (PS-ITW).
ALTERNATIVE_OPTIONS: dict[str, frozenset[int]] = {
    # FL-ALT-02 (4 hearts) and FL-ALT-07: every starting-hearts value, 1 to 16 hearts and 16, random
    # over 1 to 5 (FL-DEP-04)
    STARTING_HEARTS.id: frozenset(range(STARTING_HEARTS.count)) - {MVP_BASELINE_STARTING_HEARTS},
    # FL-ALT-03 and FL-ALT-05: the sword caves' heart ranges at every value (swapped when the
    # lowest is above the highest, FL-DEP-03)
    WHITE_SWORD_LOWEST.id: frozenset({WHITE_SWORD_FROM_FIVE_HEARTS, 2}),
    WHITE_SWORD_HIGHEST.id: frozenset({1, 2}),
    MAGICAL_SWORD_LOWEST.id: frozenset(range(1, 5)),
    MAGICAL_SWORD_HIGHEST.id: frozenset(range(1, 5)),
    # FL-ALT-06: the start pieces at every value (C18 = 1 to 8, and 9, random over 0 to 8), and the
    # piece-count range (C24, C25), inert under the supported C08 = 0
    STARTING_PIECES.id: frozenset(range(1, 10)),
    PIECE_RANGE_LOW.id: frozenset(range(1, 9)),
    PIECE_RANGE_HIGH.id: frozenset(range(1, 9)),
    # PS-ITEM-12: the pins at their values, the Armos slot and the white-sword cave at every item and
    # Non-Heart; level 9's two places not at the Bow, the Ladder, the Power Bracelet, the Raft, the
    # Recorder or the Wand, which the five-item rule (VA-REJ-08) or the wand rule (VA-REJ-22) would
    # need to collect themselves. The coast pin (C12) stays at 0.
    # FP-WOOD-01 to FP-WOOD-04 and VA-REJ-22: Swords at Wood Sword Only, No Wood Sword, Swordless and
    # Random (FL-DEP-04; under Swordless a possible B25 is on, dependencies.resolve)
    WOODEN_SWORD_STATE.id: frozenset({WoodenSwordState.WOODEN_SWORD_ONLY, WoodenSwordState.NO_WOODEN_SWORD,
                                      WoodenSwordState.SWORDLESS}),
    ARMOS_PIN.id: frozenset(range(1, 17)),
    WHITE_SWORD_CAVE_PIN.id: frozenset(range(1, 17)),
    LEVEL_9_FIRST_PIN.id: LEVEL_9_PINS,
    LEVEL_9_SECOND_PIN.id: LEVEL_9_PINS,
    HINT_STYLE.id: frozenset({HintStyle.COMMUNITY, HintStyle.HELPFUL}),  # FL-ALT-04; HT-HINT-04
    # FL-SUP-02 (L15): PS-ITW; and Item Shuffle's other values, None (C06 = 0, PS-ITEM-10) and Item Only
    # (C06 = 1, PS-ITEM-09); its random index (PS-ITEM-11) then follows, all its outcomes being produced
    ITEM_SHUFFLE_SCOPE.id: frozenset({ItemShuffleScope.NONE, ItemShuffleScope.DUNGEON_ITEMS_ONLY,
                                      ItemShuffleScope.WITHIN_EACH_DUNGEON}),
    # FL-SUP-02 (L15 and the 2026-10-10 export): OW-QST-03 to -05, OW-MIX, OW-QST-01 and -02; the
    # random index (OW-QST-06) then follows, all its outcomes being produced
    OVERWORLD_QUEST.id: frozenset({OverworldQuest.SECOND_QUEST, OverworldQuest.MIXED_FIRST_QUEST_VARIANT,
                                   OverworldQuest.MIXED_SECOND_QUEST_VARIANT}),
    # FL-SUP-02 (2026-10-10 export): OW-START-02 and OW-START-03
    START_SCREEN.id: frozenset({StartScreen.FULL_SHUFFLE, StartScreen.WOODEN_SWORD_SCREEN}),
    # FL-SUP-02 (eca85cc export): Dungeon Quest's values (SH-SRC-07 to SH-SRC-10, PS-VAN); Mixed +
    # Shapes (C02 = 4, SH-SRC-01 to SH-SRC-06), Hopla's; Mixed Quest (C02 = 2, SH-SRC-09). Its two
    # random indices, Random No Shapes (5) and Random (6, SH-SRC-10), then follow, all their
    # outcomes being produced
    DUNGEON_LAYOUT_SOURCE.id: frozenset({DungeonLayoutSource.FIRST_QUEST, DungeonLayoutSource.SECOND_QUEST,
                                         DungeonLayoutSource.MIXED, DungeonLayoutSource.MIXED_WITH_SHAPES}),
    # FL-SUP-02: Cave Shuffle's other values (OW-CAVE-09 to OW-CAVE-11; beta 6), with FL-DEP-02 rule
    # 1's coin (OW-CAVE-10); its random index (OW-CAVE-11) then follows, all its outcomes being produced
    CAVE_SHUFFLE.id: frozenset({CaveShuffle.VANILLA, CaveShuffle.DUNGEON_DOORS_ONLY,
                                CaveShuffle.NON_DUNGEON_CAVES_ONLY}),
    # FL-SUP-02 (2026-10-17 export): "Most" Enemy HP and Boss HP at every value, a walk of up to 4 and
    # all zero (PS-HP-01, PS-HP-02, PS-HP-04, PS-HP-05); their random index then follows (FL-DEP-04)
    ENEMY_HIT_POINTS.id: frozenset({HitPointChange.UP_TO_4, HitPointChange.ALL_ZERO}),
    BOSS_HIT_POINTS.id: frozenset({HitPointChange.UP_TO_4, HitPointChange.ALL_ZERO}),
}


def support(settings: Settings) -> dict[str, Support]:
    """FL-SUP-01: each field is supported at its MVP baseline value, at its turn-off values
    (FL-OFF-07) and at its alternative values (FL-ALT-02 to FL-ALT-04, owner ruling); level
    encoding (B82) at on and off, never "?" (owner ruling, 2026-10-06: a plain on/off setting).

    B23's off value is supported only with B22 off; B22's off with B23 at any value, which is kept
    as given (FL-DEP-06).

    "?" (possible) values, owner ruling (2026-10-04, in place of FL-SUP-03's "Possible is not
    supported for any field"): a "?" is supported where both of its outcomes are, that is on a
    field whose off is supported, except B82 (ENCODE_LEVEL_DATA_NOT_RANDOM). An option field's random index is
    supported only where every index it resolves to is (C17's, index 22; not C03's or C16's,
    whose random indices also resolve to values that are not produced).
    """
    baseline = mvp_baseline_settings()
    matrix: dict[str, Support] = {}
    for option in OPTION_FIELDS:
        matrix[option.id] = _judge(_option_supported(option, settings.option(option), baseline.option(option)))
    for toggle in TOGGLE_FIELDS:
        matrix[toggle.id] = _judge(_toggle_supported(settings, toggle, baseline.toggle(toggle)))
    return matrix


def _option_supported(option: OptionField, index: int, baseline: int) -> bool:
    """An option index ZORA produces: the baseline, a turn-off or an alternative value, or a random
    index all of whose outcomes are one of those."""
    if option.is_random(index):
        return all(_option_supported(option, choice, baseline) for choice in option.random_choices[index])
    return (index == baseline or index in TURN_OFF_OPTIONS.get(option.id, frozenset())
            or index in ALTERNATIVE_OPTIONS.get(option.id, frozenset()))


def _toggle_supported(settings: Settings, toggle: ToggleField, baseline: ThreeState) -> bool:
    value = settings.toggle(toggle)
    if toggle == ENCODE_LEVEL_DATA:
        return value is not ThreeState.POSSIBLE
    if value == baseline:
        return True
    if value in ALTERNATIVE_TOGGLES.get(toggle.id, frozenset()):
        return True
    if value is ThreeState.POSSIBLE and toggle.id in TURN_OFF_TOGGLES_NOT_RANDOM:
        return False
    if toggle.id not in (*TURN_OFF_TOGGLES, *SPEC_TURN_OFF_TOGGLES, *OWNER_TURN_OFF_TOGGLES):
        return False
    if toggle == MONEY_OR_LIFE_TOLL:
        # FL-DEP-06: B23 off (and so a "?", which may come up off) only with B22 off
        return settings.toggle(MONEY_OR_LIFE_ROOMS) is ThreeState.OFF
    return True                         # off, or a "?" whose off is supported


def _judge(supported: bool) -> Support:
    return Support.SUPPORTED if supported else Support.NOT_PRODUCED


# Owner ruling (2026-10-06): Encode level data (B82) is a plain on/off setting and never takes "?".
ENCODE_LEVEL_DATA_NOT_RANDOM = "Encode level data is on or off; it cannot be random"


def encode_level_data_is_random(settings: Settings) -> bool:
    """A "?" on B82, which generation refuses with ENCODE_LEVEL_DATA_NOT_RANDOM."""
    return settings.toggle(ENCODE_LEVEL_DATA) is ThreeState.POSSIBLE


def unsupported_fields(settings: Settings) -> list[str]:
    """The labels of the fields the MVP does not produce, in field order."""
    return [field_id for field_id, state in support(settings).items() if state is Support.NOT_PRODUCED]


def is_fully_supported(settings: Settings) -> bool:
    """FL-SUP-01: the rebuild MUST NOT generate a seed from a string that has any unsupported field."""
    return not unsupported_fields(settings)
