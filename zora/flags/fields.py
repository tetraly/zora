"""The flag fields (FL-ENC-04, FL-ENC-05): the 27 option fields, the 91
three-state fields, and Settings, which holds a value for each."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import IntEnum


class ThreeState(IntEnum):
    """The value of a three-state field (FL-ENC-05): off, on, or decided per seed."""
    OFF = 0
    ON = 1
    POSSIBLE = 2


# ---------------------------------------------------------------------------
# FL-ENC-04: the 27 option fields
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OptionField:
    """One option field: its spec label, name, radix ("Slots") and number of valid options ("Count").

    ``random_choices`` maps each index that means "random" to the indices it
    resolves to, uniformly, per seed (FL-DEP-04).
    """
    id: str
    setting: str
    slots: int
    count: int
    random_choices: Mapping[int, tuple[int, ...]] = field(default_factory=dict, hash=False, compare=False)

    @property
    def last_index(self) -> int:
        return self.count - 1

    def is_random(self, index: int) -> bool:
        return index in self.random_choices


def _indices(stop: int, start: int = 0) -> tuple[int, ...]:
    return tuple(range(start, stop + 1))


class OverworldQuest(IntEnum):
    """C01 index meanings."""
    FIRST_QUEST = 0
    SECOND_QUEST = 1
    MIXED_FIRST_QUEST_VARIANT = 2
    MIXED_SECOND_QUEST_VARIANT = 3
    RANDOM = 4


class DungeonLayoutSource(IntEnum):
    """C02 index meanings."""
    FIRST_QUEST = 0
    SECOND_QUEST = 1
    MIXED = 2
    GENERATED_SHAPES = 3
    MIXED_WITH_SHAPES = 4
    RANDOM_WITHOUT_SHAPES = 5
    RANDOM = 6


class CaveShuffle(IntEnum):
    """C05 index meanings."""
    VANILLA = 0
    DUNGEON_DOORS_ONLY = 1
    NON_DUNGEON_CAVES_ONLY = 2
    ALL_CAVES = 3
    RANDOM = 4


class ItemShuffleScope(IntEnum):
    """C06 index meanings."""
    NONE = 0
    DUNGEON_ITEMS_ONLY = 1
    WITHIN_EACH_DUNGEON = 2
    FULL = 3
    RANDOM = 4


class WoodenSwordState(IntEnum):
    """C07 index meanings."""
    NORMAL = 0
    WOODEN_SWORD_ONLY = 1
    NO_WOODEN_SWORD = 2
    SWORDLESS = 3
    RANDOM = 4


class Level9Requirement(IntEnum):
    """C08 index meanings beyond the piece counts (indices 0 to 7 need 8 - i pieces)."""
    EIGHT_PIECES = 0
    ONE_PIECE = 7
    OPEN = 8
    RANDOM_COUNT_IN_RANGE = 9
    SPECIFIC_PIECES = 10
    ITEM_INSTEAD_OF_PIECES = 11
    RANDOM = 12


class HintStyle(IntEnum):
    """C03 index meanings."""
    NORMAL = 0
    HELPFUL = 1
    COMMUNITY = 2
    DECEPTIVE = 3
    MIXED = 4
    BLANK = 5
    RANDOM = 6


class StartScreen(IntEnum):
    """C04 index meanings."""
    NORMAL = 0
    EASY_SHUFFLE = 1
    FULL_SHUFFLE = 2
    WOODEN_SWORD_SCREEN = 3


class HitPointChange(IntEnum):
    """C09 and C10 index meanings."""
    NORMAL = 0
    UP_TO_2 = 1
    UP_TO_4 = 2
    ALL_ZERO = 3
    RANDOM = 4

    @property
    def max_shift(self) -> int | None:
        """The largest move per value; None for the all-zero and random indices."""
        return {HitPointChange.NORMAL: 0, HitPointChange.UP_TO_2: 2, HitPointChange.UP_TO_4: 4}.get(self)


class PinnedItem(IntEnum):
    """The item list shared by C11, C12, C13, C26 and C27 (under the FL-ENC-04 table)."""
    NONE_PINNED = 0
    BOOK_OF_MAGIC = 1
    WOODEN_BOOMERANG = 2
    BOW = 3
    HEART_CONTAINER = 4
    LADDER = 5
    MAGICAL_BOOMERANG = 6
    MAGICAL_KEY = 7
    POWER_BRACELET = 8
    RAFT = 9
    RECORDER = 10
    RED_CANDLE = 11
    RED_RING = 12
    SILVER_ARROW = 13
    WAND = 14
    WHITE_SWORD = 15
    ANY_ITEM_EXCEPT_HEART_CONTAINER = 16

    @property
    def is_item(self) -> bool:
        """Whether the index names one item (FL-DEP-01: 0 and 16 never count as a duplicate)."""
        return self not in (PinnedItem.NONE_PINNED, PinnedItem.ANY_ITEM_EXCEPT_HEART_CONTAINER)


class DungeonRoomShuffle(IntEnum):
    """C14 index meanings."""
    VANILLA = 0
    WITHIN_EACH_DUNGEON = 1
    FULL = 2
    RANDOM = 3


class ItemAppearance(IntEnum):
    """C15 index meanings."""
    NORMAL = 0
    FUN_PERCENTAGE = 1
    SPRITE_SHUFFLE = 2
    RANDOM = 3


class RedBubble(IntEnum):
    """C19 index meanings."""
    VANILLA = 0
    INVERTED_CONTROLS = 1
    SLOW_SPEED = 2
    RANDOM = 3


# Index-to-value arithmetic of FL-DEP-03.
STARTING_HEARTS_RANDOM = 16          # C16: index 16 is a random number from 1 to 5
STARTING_HEARTS_RANDOM_CHOICES = _indices(4)   # indices 0 to 4 give 1 to 5 hearts
FOUR_STARTING_HEARTS = 3             # C16: index i gives i + 1 hearts (FL-ALT-02's value)
START_ITEM_LIMIT_ALL_CHOSEN = 0      # C17: index 0 allows every chosen start item
START_ITEM_LIMIT_RANDOM = 22         # C17: index 22 is a random limit from 0 to 20
START_ITEM_LIMIT_RANDOM_CHOICES = _indices(21, start=1)   # indices 1 to 21 give limits 0 to 20
STARTING_PIECES_RANDOM = 9           # C18: index 9 is a random number from 0 to 8
MAX_TRIFORCE_PIECES = 8
WHITE_SWORD_LOWEST_BASE = 4          # C20: lowest requirement is 4 + index
WHITE_SWORD_FROM_FIVE_HEARTS = 1     # C20: index 1, lowest requirement 5 (FL-ALT-03's value)
WHITE_SWORD_HIGHEST_BASE = 6         # C21: highest requirement is 6 - index
MAGICAL_SWORD_LOWEST_BASE = 10       # C22: lowest requirement is 10 + index
MAGICAL_SWORD_HIGHEST_BASE = 14      # C23: highest requirement is 14 - index

_PINNED_ITEM_SLOTS = 20
_PINNED_ITEM_COUNT = len(PinnedItem)

OVERWORLD_QUEST = OptionField("C01", "Overworld quest", 8, 5, {OverworldQuest.RANDOM: _indices(3)})
DUNGEON_LAYOUT_SOURCE = OptionField("C02", "Dungeon layout source", 10, 7, {
    DungeonLayoutSource.RANDOM: _indices(DungeonLayoutSource.MIXED_WITH_SHAPES),
    DungeonLayoutSource.RANDOM_WITHOUT_SHAPES: _indices(DungeonLayoutSource.MIXED),
})
HINT_STYLE = OptionField("C03", "Hint style", 10, 7, {HintStyle.RANDOM: _indices(HintStyle.BLANK)})
START_SCREEN = OptionField("C04", "Start screen", 7, 4)
CAVE_SHUFFLE = OptionField("C05", "Cave shuffle", 8, 5, {CaveShuffle.RANDOM: _indices(3)})
ITEM_SHUFFLE_SCOPE = OptionField("C06", "Item shuffle scope", 8, 5, {ItemShuffleScope.RANDOM: _indices(3)})
WOODEN_SWORD_STATE = OptionField("C07", "Wooden-sword state", 8, 5, {WoodenSwordState.RANDOM: _indices(3)})
LEVEL_9_REQUIREMENT = OptionField("C08", "Triforce pieces needed for level 9", 15, 13, {
    Level9Requirement.RANDOM: (
        Level9Requirement.EIGHT_PIECES, Level9Requirement.OPEN, Level9Requirement.RANDOM_COUNT_IN_RANGE,
        Level9Requirement.SPECIFIC_PIECES, Level9Requirement.ITEM_INSTEAD_OF_PIECES,
    ),
})
ENEMY_HIT_POINTS = OptionField("C09", "Enemy hit-point change", 8, 5, {HitPointChange.RANDOM: _indices(3)})
BOSS_HIT_POINTS = OptionField("C10", "Boss hit-point change", 8, 5, {HitPointChange.RANDOM: _indices(3)})
ARMOS_PIN = OptionField("C11", "Item pinned to the secret Armos spot", _PINNED_ITEM_SLOTS, _PINNED_ITEM_COUNT)
COAST_PIN = OptionField("C12", "Item pinned to the coast cave", _PINNED_ITEM_SLOTS, _PINNED_ITEM_COUNT)
WHITE_SWORD_CAVE_PIN = OptionField("C13", "Item pinned to the white-sword cave", _PINNED_ITEM_SLOTS,
                                   _PINNED_ITEM_COUNT)
DUNGEON_ROOM_SHUFFLE = OptionField("C14", "Dungeon room shuffle", 7, 4, {DungeonRoomShuffle.RANDOM: _indices(2)})
ITEM_APPEARANCE = OptionField("C15", "Item and sprite appearance", 7, 4, {ItemAppearance.RANDOM: _indices(2)})
STARTING_HEARTS = OptionField("C16", "Starting hearts", 20, 17,
                              {STARTING_HEARTS_RANDOM: STARTING_HEARTS_RANDOM_CHOICES})
START_ITEM_LIMIT = OptionField("C17", "Limit on starting items", 26, 23,
                               {START_ITEM_LIMIT_RANDOM: START_ITEM_LIMIT_RANDOM_CHOICES})
STARTING_PIECES = OptionField("C18", "Starting triforce pieces", 13, 10,
                              {STARTING_PIECES_RANDOM: _indices(MAX_TRIFORCE_PIECES)})
RED_BUBBLE = OptionField("C19", "Red bubble behaviour", 7, 4, {RedBubble.RANDOM: _indices(2)})
WHITE_SWORD_LOWEST = OptionField("C20", "White-sword hearts, lowest", 6, 3)
WHITE_SWORD_HIGHEST = OptionField("C21", "White-sword hearts, highest", 6, 3)
MAGICAL_SWORD_LOWEST = OptionField("C22", "Magical-sword hearts, lowest", 8, 5)
MAGICAL_SWORD_HIGHEST = OptionField("C23", "Magical-sword hearts, highest", 8, 5)
PIECE_RANGE_LOW = OptionField("C24", "Piece-count range, low end", 12, 9)
PIECE_RANGE_HIGH = OptionField("C25", "Piece-count range, high end", 12, 9)
LEVEL_9_FIRST_PIN = OptionField("C26", "First item pinned inside level 9", _PINNED_ITEM_SLOTS, _PINNED_ITEM_COUNT)
LEVEL_9_SECOND_PIN = OptionField("C27", "Second item pinned inside level 9", _PINNED_ITEM_SLOTS,
                                 _PINNED_ITEM_COUNT)

OPTION_FIELDS: tuple[OptionField, ...] = (
    OVERWORLD_QUEST, DUNGEON_LAYOUT_SOURCE, HINT_STYLE, START_SCREEN, CAVE_SHUFFLE, ITEM_SHUFFLE_SCOPE,
    WOODEN_SWORD_STATE, LEVEL_9_REQUIREMENT, ENEMY_HIT_POINTS, BOSS_HIT_POINTS, ARMOS_PIN, COAST_PIN,
    WHITE_SWORD_CAVE_PIN, DUNGEON_ROOM_SHUFFLE, ITEM_APPEARANCE, STARTING_HEARTS, START_ITEM_LIMIT,
    STARTING_PIECES, RED_BUBBLE, WHITE_SWORD_LOWEST, WHITE_SWORD_HIGHEST, MAGICAL_SWORD_LOWEST,
    MAGICAL_SWORD_HIGHEST, PIECE_RANGE_LOW, PIECE_RANGE_HIGH, LEVEL_9_FIRST_PIN, LEVEL_9_SECOND_PIN,
)
PIN_FIELDS: tuple[OptionField, ...] = (ARMOS_PIN, COAST_PIN, WHITE_SWORD_CAVE_PIN, LEVEL_9_FIRST_PIN,
                                       LEVEL_9_SECOND_PIN)


# ---------------------------------------------------------------------------
# FL-ENC-05: the 91 three-state fields
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ToggleField:
    """One three-state field: its spec label and what it does when on."""
    id: str
    setting: str


_TOGGLE_SETTINGS = (
    "Recorder warps to the new dungeon entrances",                  # B01
    "The wooden-sword cave may move to any hidden cave position",   # B02
    "Allow the wooden-sword cave behind blocks",                    # B03
    "Shuffle the take-any-road caves",                              # B04
    "Move the secret-entrance tiles",                               # B05
    "Mirror the overworld",                                         # B06
    "Recorder warps to unbeaten dungeons",                          # B07
    "Shuffle shop wares",                                           # B08
    "Add extra candle wares",                                       # B09
    "Re-draw the sword heart requirements",                         # B10
    "Re-draw the money-making game amounts",                        # B11
    "Re-draw the bomb-upgrade person",                              # B12
    "Shuffle the secret Armos item",                                # B13
    "(No effect; FL-DEP-05)",                                       # B14
    "Shuffle dungeon room items within each level",                 # B15
    "(No effect; FL-DEP-05)",                                       # B16
    "Let bombs, rupees and keys join the item pool",                # B17
    "Ganon must be beaten to finish",                               # B18
    "Shuffle the dungeon hint texts",                               # B19
    "Add second-quest rooms to the shape tables",                   # B20
    "Add second-quest door weights",                                # B21
    "Turn person rooms into life-or-money merchants",               # B22
    "Re-draw the merchants' toll",                                  # B23
    "Hide the dungeon numbers",                                     # B24
    "Allow important items inside level 9",                         # B25
    "Allow the dungeon start room to move",                         # B26
    "Shuffle dungeon colours",                                      # B27
    "Shuffle the hungry goriya",                                    # B28
    "Shuffle the bomb-upgrade persons",                             # B29
    "Remove most open stairs",                                      # B30
    "Shuffle the overworld monsters",                               # B31
    "Shuffle dungeon monsters within each level",                   # B32
    "Let Ganon and Zelda take part in the shuffles",                # B33
    "Shuffle the bosses",                                           # B34
    "Include level 9 in the monster moves",                         # B35
    "Move monsters between levels",                                 # B36
    "Add second-quest monsters",                                    # B37
    "Shuffle the enemy drop groups",                                # B38
    "Make important items enemy drops",                             # B39
    "Randomize the boss groups",                                    # B40
    "Set Ganon's hit points to zero",                               # B41
    "Shuffle the enemy groups",                                     # B42
    "Redraw overworld screens from the overworld group",            # B43
    "Randomize the item drop rate",                                 # B44
    "Maximum enemy health",                                         # B45
    "Maximum boss health",                                          # B46
    "Replace the Book's fire with an explosion",                    # B47
    "The Book lets the player understand old men",                  # B48
    "The Book counts as the map of every level",                    # B49
    "Blackout",                                                     # B50
    "Print quest information",                                      # B51
    "Permanent sword beam",                                         # B52
    "One-hit knock-out",                                            # B53
    "Speed up person text",                                         # B54
    "Hide health",                                                  # B55
    "Killable drop items",                                          # B56
    "Start with the Raft",                                          # B57
    "Start with the Bow",                                           # B58
    "Start with 8 bombs",                                           # B59
    "Start with the Recorder",                                      # B60
    "Start with the Bait",                                          # B61
    "Start with the Magical Key",                                   # B62
    "Start with the Letter",                                        # B63
    "Start with the Power Bracelet",                                # B64
    "Start with the Ladder",                                        # B65
    "Start with the Wand",                                          # B66
    "Start with the Book of Magic",                                 # B67
    "Start with the wooden sword",                                  # B68
    "Start with the white sword",                                   # B69
    "Start with the magical sword",                                 # B70
    "Start with the wooden arrow",                                  # B71
    "Start with the Silver Arrow",                                  # B72
    "Start with the blue candle",                                   # B73
    "Start with the red candle",                                    # B74
    "Start with the blue ring",                                     # B75
    "Start with the red ring",                                      # B76
    "Start with the wooden Boomerang",                              # B77
    "Start with the Magical Boomerang",                             # B78
    "Add extra bosses",                                             # B79
    "Rupees affect speed",                                          # B80
    "Force an overworld block for an item",                         # B81
    "Encode level data",                                            # B82 (FP-TOURNEY-01)
    "Hide numbers",                                                 # B83
    "Prevent screen-scroll clipping",                               # B84
    "Start with the magical shield",                                # B85
    "Do not sort the shapes by size",                               # B86
    "Add bridges over the river",                                   # B87
    "Add a Lost Woods shortcut",                                    # B88
    "Change hidden overworld tiles",                                # B89
    "Increase the bomb capacity upgrade",                           # B90
    "Allow universal drops in shapes",                              # B91
)
TOGGLE_FIELDS: tuple[ToggleField, ...] = tuple(
    ToggleField(f"B{number:02d}", setting) for number, setting in enumerate(_TOGGLE_SETTINGS, start=1)
)
TOGGLES_BY_ID = {toggle.id: toggle for toggle in TOGGLE_FIELDS}
OPTIONS_BY_ID = {option.id: option for option in OPTION_FIELDS}

# The three-state fields the dependency rules and the support matrix name.
WOODEN_SWORD_CAVE_MOVES = TOGGLES_BY_ID["B02"]
TAKE_ANY_ROAD_SHUFFLE = TOGGLES_BY_ID["B04"]
SHUFFLE_DUNGEON_ITEMS_INERT = TOGGLES_BY_ID["B14"]
SHUFFLE_DUNGEON_HEARTS_INERT = TOGGLES_BY_ID["B16"]
GANON_MUST_BE_BEATEN = TOGGLES_BY_ID["B18"]
MONEY_OR_LIFE_ROOMS = TOGGLES_BY_ID["B22"]
MONEY_OR_LIFE_TOLL = TOGGLES_BY_ID["B23"]
IMPORTANT_ITEMS_IN_LEVEL_9 = TOGGLES_BY_ID["B25"]
START_ROOM_MAY_MOVE = TOGGLES_BY_ID["B26"]
HUNGRY_GORIYA_SHUFFLE = TOGGLES_BY_ID["B28"]
BOMB_UPGRADE_PERSON_SHUFFLE = TOGGLES_BY_ID["B29"]
DUNGEON_MONSTER_SHUFFLE = TOGGLES_BY_ID["B32"]
GANON_AND_ZELDA_SHUFFLE = TOGGLES_BY_ID["B33"]
MONSTERS_BETWEEN_LEVELS = TOGGLES_BY_ID["B36"]
ENCODE_LEVEL_DATA = TOGGLES_BY_ID["B82"]
# FL-DEP-03: the chosen start items are B57 to B78 and B85.
START_ITEM_FIELDS: tuple[ToggleField, ...] = (*(TOGGLES_BY_ID[f"B{n:02d}"] for n in range(57, 79)),
                                              TOGGLES_BY_ID["B85"])
# FL-DEP-05: decoded and displayed, but neither selects a generation setting.
INERT_TOGGLES: tuple[ToggleField, ...] = (SHUFFLE_DUNGEON_ITEMS_INERT, SHUFFLE_DUNGEON_HEARTS_INERT)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

FieldRef = OptionField | ToggleField | str


def _field_id(ref: FieldRef) -> str:
    return ref if isinstance(ref, str) else ref.id


@dataclass(frozen=True)
class Settings:
    """The decoded values of all 118 fields, keyed by the spec labels C01 to C27 and B01 to B91.

    Option values are clamped indices (FL-ENC-03 rule 3), never raw slot values.
    """
    options: Mapping[str, int]
    toggles: Mapping[str, ThreeState]

    def __post_init__(self) -> None:
        unknown = (set(self.options) - set(OPTIONS_BY_ID)) | (set(self.toggles) - set(TOGGLES_BY_ID))
        missing = (set(OPTIONS_BY_ID) - set(self.options)) | (set(TOGGLES_BY_ID) - set(self.toggles))
        if unknown or missing:
            raise ValueError(f"unknown fields {sorted(unknown)}, missing fields {sorted(missing)}")
        options = {option.id: int(self.options[option.id]) for option in OPTION_FIELDS}
        for option in OPTION_FIELDS:
            if not 0 <= options[option.id] <= option.last_index:
                raise ValueError(f"{option.id} index {options[option.id]} is outside 0 to {option.last_index}")
        toggles = {toggle.id: ThreeState(self.toggles[toggle.id]) for toggle in TOGGLE_FIELDS}
        object.__setattr__(self, "options", options)
        object.__setattr__(self, "toggles", toggles)

    @classmethod
    def zero(cls) -> Settings:
        """FL-ENC-06: the string `0`, every option at index 0 and every three-state field off."""
        return cls({option.id: 0 for option in OPTION_FIELDS}, {toggle.id: ThreeState.OFF for toggle in TOGGLE_FIELDS})

    def option(self, ref: FieldRef) -> int:
        return self.options[_field_id(ref)]

    def toggle(self, ref: FieldRef) -> ThreeState:
        return self.toggles[_field_id(ref)]

    def is_on(self, ref: FieldRef) -> bool:
        """Whether a three-state field is on. A possible field is not on until it is resolved (FL-DEP-04)."""
        return self.toggle(ref) is ThreeState.ON

    def updated(self, options: Mapping[str, int] | Mapping[OptionField, int] | None = None,
                toggles: Mapping[str, ThreeState | int] | Mapping[ToggleField, ThreeState | int] | None = None,
                ) -> Settings:
        """A copy with the given fields changed."""
        new_options = dict(self.options)
        new_toggles = dict(self.toggles)
        for option_ref, index in (options or {}).items():
            new_options[_field_id(option_ref)] = index
        for toggle_ref, state in (toggles or {}).items():
            new_toggles[_field_id(toggle_ref)] = ThreeState(state)
        return Settings(new_options, new_toggles)
