"""The support matrix (FL-SUP-01 to FL-SUP-04, FL-OFF-07, FL-ALT-02 to FL-ALT-04): which values ZORA
produces."""
from __future__ import annotations

from enum import Enum

from .fields import (
    BOSS_HIT_POINTS,
    CAVE_SHUFFLE,
    DUNGEON_LAYOUT_SOURCE,
    DUNGEON_ROOM_SHUFFLE,
    ENCODE_LEVEL_DATA,
    ENEMY_HIT_POINTS,
    FOUR_STARTING_HEARTS,
    HINT_STYLE,
    ITEM_SHUFFLE_SCOPE,
    MONEY_OR_LIFE_ROOMS,
    MONEY_OR_LIFE_TOLL,
    OPTION_FIELDS,
    START_ITEM_LIMIT,
    START_SCREEN,
    STARTING_HEARTS,
    TOGGLE_FIELDS,
    WHITE_SWORD_FROM_FIVE_HEARTS,
    WHITE_SWORD_LOWEST,
    CaveShuffle,
    DungeonLayoutSource,
    DungeonRoomShuffle,
    HintStyle,
    HitPointChange,
    ItemShuffleScope,
    OptionField,
    Settings,
    StartScreen,
    ThreeState,
    ToggleField,
)

# ---------------------------------------------------------------------------
# FL-SUP-01 to FL-SUP-04: the support matrix
# ---------------------------------------------------------------------------

class Support(Enum):
    """Whether the MVP produces a field's value (FL-SUP-01: "supported" / "not supported in MVP")."""
    SUPPORTED = "supported"
    NOT_PRODUCED = "not produced"


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
    STARTING_HEARTS.id: 2,                 # 3 hearts
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


# FL-OFF-07: the three-state fields with a turn-off value (off; 22 fields).
TURN_OFF_TOGGLES: tuple[str, ...] = (
    "B01", "B08", "B09", "B10", "B11", "B12", "B13", "B14", "B15", "B16", "B19", "B22", "B23", "B27", "B28",
    "B31", "B34", "B36", "B40", "B42", "B49", "B54",
)
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
# FL-ALT-02 to FL-ALT-04: the alternative values ZORA produces. Owner ruling (2026-10-05): supported
# after the MVP, in place of FL-ALT-01's "not supported in MVP".
ALTERNATIVE_OPTIONS: dict[str, frozenset[int]] = {
    STARTING_HEARTS.id: frozenset({FOUR_STARTING_HEARTS}),             # FL-ALT-02: 4 hearts
    WHITE_SWORD_LOWEST.id: frozenset({WHITE_SWORD_FROM_FIVE_HEARTS}),  # FL-ALT-03: 5 hearts
    HINT_STYLE.id: frozenset({HintStyle.COMMUNITY}),                   # FL-ALT-04
}


def support(settings: Settings) -> dict[str, Support]:
    """FL-SUP-01: each field is supported at its MVP baseline value, at its turn-off values
    (FL-OFF-07) and at its alternative values (FL-ALT-02 to FL-ALT-04, owner ruling); level
    encoding (B82) at on and off, never "?" (owner ruling, 2026-10-06: a plain on/off setting).

    B23's off value is supported only with B22 off (FL-DEP-06): a string with B22 off is judged
    after B23 is forced off (dependencies.correct_merchant_toll).

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
    if toggle.id not in TURN_OFF_TOGGLES and toggle.id not in OWNER_TURN_OFF_TOGGLES:
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
