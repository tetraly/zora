"""The ZORA flag string: ZORA-only flags, kept apart from the Z1R flag string.

docs/zora-extras.md is the design record. In short:

  - The string is ``<version>.<payload>``: a decimal version number, a dot,
    and one whole number in the Z1R codec's base-63 alphabet (FL-ENC-01).
    The dot is outside that alphabet, so a ZORA string can never be read as
    a Z1R string, nor a Z1R string as a ZORA string.
  - The payload holds the version's fields as mixed-radix digits, the first
    field least significant (as C01 is in the Z1R string). A later version
    only appends fields, so every older string keeps its meaning.
  - The empty string means every ZORA flag at its default. Canonical
    spelling: empty when every field is at its default; otherwise the lowest
    version that holds every field away from its default, then the payload
    without leading zeros.
  - Decoding is strict, unlike the Z1R codec's clamping (FL-ENC-03): an
    unknown version, a character outside the alphabet or a payload too big
    for its version's fields is refused, so a mistyped string never turns
    into different flags silently.

The Z1R string keeps exactly its meaning: nothing here reads or changes how
it decodes. With the ZORA string at its default, generation_seed() and
level_encoding_text() return today's values, so all output is unchanged.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from dataclasses import dataclass, fields, replace
from enum import Enum, IntEnum

from .codec import ALPHABET, DIGIT_VALUE, RADIX
from .dependencies import UnresolvedError, magical_sword_hearts, starting_hearts
from .fields import (
    BOOK_TO_UNDERSTAND_NPCS,
    LEVEL_9_FIRST_PIN,
    LEVEL_9_REQUIREMENT,
    LEVEL_9_SECOND_PIN,
    MAGICAL_SWORD_HIGHEST,
    MAGICAL_SWORD_LOWEST,
    OPTIONS_BY_ID,
    STARTING_HEARTS_RANDOM_CHOICES,
    TOGGLES_BY_ID,
    CaveShuffle,
    DungeonLayoutSource,
    ItemShuffleScope,
    Level9Requirement,
    OverworldQuest,
    Settings,
    ThreeState,
    WoodenSwordState,
)

# ---------------------------------------------------------------------------
# The fields, by version
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ZoraField:
    """One ZORA flag: its attribute name on ZoraFlags, its radix and the
    version of the string format that introduced it."""
    name: str
    slots: int
    version: int


# The magical-sword hearts field: index 0 follows the Z1R string, index i
# (1 to 5) caps the highest requirement at 9 + i hearts (10 to 14).
HEARTS_FOLLOW_Z1R = 0
HEARTS_CAP_BASE = 9
HEARTS_CAP_CHOICES = range(10, 15)

# Version 3 (owner's 2.0 flags, docs/design/zora-flags-2.0.md): each is On / Off / ?, a base-3
# digit holding a ThreeState (0 off, 1 on, 2 "?" decided per seed). Off is the default, so every
# older string keeps its meaning and its spelling. In payload order, retired slots included.
THREE_STATE_SLOTS = 3
OWNER_2_0_SLOTS = (
    "shuffle_blue_potion",                 # §1, merged with plan §13's Phase 2B
    "add_l4_sword",                        # §2 (owner design: a level-9 room)
    "extra_raft_blocks",                   # §3
    "extra_power_bracelet_blocks",         # §4
    "speed_up_dungeon_transitions",        # §5
    "speed_up_heart_fill",                 # §6, credit: snarfblam
    "recorder_kills_pols_voice",           # §7, credit: Stratoform
    "four_potion_inventory",               # §8
    "auto_show_letter",                    # §9
    "like_like_eats_rupees",               # §10
    "magical_boomerang_damage",            # §11
    "randomize_lost_hills",                # §12
    "randomize_dead_woods",                # §13
)
# Fields that are no longer settings: their payload slot stays, so every string decodes as before;
# decode reads and drops its digit, encode writes its default, and ZoraFlags has no attribute for
# it. Auto Show Letter: always on (owner, 2026-10-17; owner_patches.ALWAYS_WRITTEN).
RETIRED_FIELDS = frozenset({"auto_show_letter"})
# The owner's 2.0 flags that are settings, in payload order.
OWNER_2_0_FIELDS = tuple(name for name in OWNER_2_0_SLOTS if name not in RETIRED_FIELDS)
# Version 6: three ZORA 1.0 flags recreated as ZORA extras (owner design, 2026-10-17; docs/
# zora-extras.md section 13), each On / Off / ? like version 3's, a "?" decided by the same coins
# after version 3's. In payload order.
ZORA_1_0_FIELDS = (
    "allow_triforces_in_stairways",        # each Triforce takes a spot of its level before the shuffle
    "shuffle_wood_sword",                  # the wood sword joins the pool; a weapon in an open cave
)
# Version 7: Pegasus Boots (owner spec, 2026-10-17), On / Off / ? like version 3's, a "?" decided
# by the same coins after version 6's; written by its asm/flags2 patch (zora/rom/owner_patches.py).
PEGASUS_BOOTS_FIELDS = (
    "pegasus_boots",                       # the wooden and magical boomerangs become L1 and L2 boots
)
# Version 8: Expanded Dungeon Locations (owner and Bogie, 2026-10-18; private design
# expanded-dungeon-locations.md), On / Off / ? like version 3's, a "?" decided by the same coins after
# version 7's. Built for a 1st or 2nd Quest overworld with Dungeons Only or All Caves
# (expanded_dungeon_locations_conflicts).
EXPANDED_DUNGEON_LOCATIONS_FIELDS = (
    "expanded_dungeon_locations",          # the nine dungeons dealt onto 9 of 15 first- and second-quest spots
)
# Version 9: Highlight No-Drop Rooms (owner decision, 2026-10-18; the research doc "Highlight No-Drop
# Rooms: Research and Implementation Plan"), On / Off / ? like version 3's, a "?" decided by the same
# coins after version 8's. Inert when Allow Universal Drops In Shapes (B91) resolves on.
HIGHLIGHT_NO_DROP_ROOMS_FIELDS = (
    "highlight_no_drop_rooms",             # block rooms that can never hold an item use inner palette 3
)
# Version 10: Do Not Segment Dungeons (owner, 2026-10-22; tetraly/zora#6 and #7, the design of
# docs/reports/research-candles-and-segments.md section 2), On / Off / ? like version 3's, a "?"
# decided by the same coins after version 9's. Acts on shapes levels only.
DO_NOT_SEGMENT_DUNGEONS_FIELDS = (
    "do_not_segment_dungeons",                  # a shapes level's rooms are all joined by doors, stairways shortcuts
)
# Version 11: Disable Custom Music (owner, 2026-10-22; docs/design/music-settings.md section 7), a
# switch for races: with it On, the player setting Music offers only Off and Vanilla. It rules the
# player settings only, never the game, so it is kept out of the game's random streams and level
# encoding key (game_string): the same seed is the same game with it on or off.
PLAYER_SETTING_RULES = frozenset({"disable_custom_music"})
# Every On / Off / ? field, in payload order: the "?" coins are drawn in this order.
THREE_STATE_FIELDS = (*OWNER_2_0_FIELDS, *ZORA_1_0_FIELDS, *PEGASUS_BOOTS_FIELDS,
                      *EXPANDED_DUNGEON_LOCATIONS_FIELDS, *HIGHLIGHT_NO_DROP_ROOMS_FIELDS,
                      *DO_NOT_SEGMENT_DUNGEONS_FIELDS)



class OopsAllEnemies(IntEnum):
    """Oops All Enemies: the family every regular dungeon room's enemies are drawn from, per room
    (docs/design/oops-all.md section 3)."""
    OFF = 0
    WIZZROBES = 1          # red and blue
    KEESE = 2              # blue, red and dark
    BOUNCERS = 3           # Pols Voice and Vire (the owner's name: both hop)


class OopsAllBosses(IntEnum):
    """Oops All Bosses: the boss every level 1-8 boss room holds where its layout allows."""
    OFF = 0
    DODONGOS = 1           # triple and single


# Fields whose digit is an enum's value
ENUM_FIELDS: dict[str, type[IntEnum]] = {"oops_all_enemies": OopsAllEnemies, "oops_all_bosses": OopsAllBosses}

# Every field ever defined, in payload order (least significant first).
# Append only: a field's position and radix never change once released.
FIELDS: tuple[ZoraField, ...] = (
    ZoraField("randomize_magical_sword", 2, version=1),
    ZoraField("randomize_letter", 2, version=1),
    ZoraField("magical_sword_hearts_highest", 1 + len(HEARTS_CAP_CHOICES), version=1),
    # PI-FLAG-01 (docs/design/progressive-items-plan.md): version 2. Both off by default, so the
    # empty string and every version-1 string keep their meaning.
    ZoraField("progressive_items", 2, version=2),
    ZoraField("shop_items_in_pool", 2, version=2),
    *(ZoraField(name, THREE_STATE_SLOTS, version=3) for name in OWNER_2_0_SLOTS),
    # Version 4: All Swords No Boards (docs/design/asnb.md section 1). Add L4 Sword's released
    # three-state field keeps its radix; this one moves its sword to level 2 (the two shown as one
    # Off / Level 2 / Level 9 control). And the level-9 entrance: triforce pieces, or a level-4
    # sword. Neither has a random option. Both off by default, so every older string keeps its
    # meaning and its spelling.
    ZoraField("l4_sword_in_level_2", 2, version=4),
    ZoraField("level_9_entrance_sword", 2, version=4),
    # Version 5: Oops All Enemies and Oops All Bosses (docs/design/oops-all.md section 3). Off is
    # 0 in both, so every older string keeps its meaning and its spelling. No random value yet.
    ZoraField("oops_all_enemies", len(OopsAllEnemies), version=5),
    ZoraField("oops_all_bosses", len(OopsAllBosses), version=5),
    # Version 6: the ZORA 1.0 flags (ZORA_1_0_FIELDS), Off by default, so every older string keeps
    # its meaning and its spelling.
    *(ZoraField(name, THREE_STATE_SLOTS, version=6) for name in ZORA_1_0_FIELDS),
    # Version 7: Pegasus Boots (PEGASUS_BOOTS_FIELDS), Off by default, so every older string keeps
    # its meaning and its spelling.
    *(ZoraField(name, THREE_STATE_SLOTS, version=7) for name in PEGASUS_BOOTS_FIELDS),
    # Version 8: Expanded Dungeon Locations (EXPANDED_DUNGEON_LOCATIONS_FIELDS), Off by default, so
    # every older string keeps its meaning and its spelling.
    *(ZoraField(name, THREE_STATE_SLOTS, version=8) for name in EXPANDED_DUNGEON_LOCATIONS_FIELDS),
    # Version 9: Highlight No-Drop Rooms (HIGHLIGHT_NO_DROP_ROOMS_FIELDS), Off by default, so every
    # older string keeps its meaning and its spelling.
    *(ZoraField(name, THREE_STATE_SLOTS, version=9) for name in HIGHLIGHT_NO_DROP_ROOMS_FIELDS),
    # Version 10: Do Not Segment Dungeons (DO_NOT_SEGMENT_DUNGEONS_FIELDS), Off by default, so every older
    # string keeps its meaning and its spelling.
    *(ZoraField(name, THREE_STATE_SLOTS, version=10) for name in DO_NOT_SEGMENT_DUNGEONS_FIELDS),
    # Version 11: Disable Custom Music (PLAYER_SETTING_RULES), Off by default, so every older string
    # keeps its meaning and its spelling.
    ZoraField("disable_custom_music", 2, version=11),
)
CURRENT_VERSION = max(field.version for field in FIELDS)
VERSION_SEPARATOR = "."
_STRING_PATTERN = re.compile(r"([1-9][0-9]*)\.(.+)")


class ZoraFlagStringError(ValueError):
    """A ZORA flag string that decode() refuses."""


@dataclass(frozen=True)
class ZoraFlags:
    """The decoded ZORA flags. The defaults are today's generator."""
    randomize_magical_sword: bool = False
    randomize_letter: bool = False
    # The highest heart count the magical-sword cave may ask for; None
    # follows the Z1R string (FL-DEP-03's 14 - C23 with B10 on).
    magical_sword_hearts_highest: int | None = None
    # Each sword, candle, arrow, ring or boomerang gives the next level the player lacks (§2, §5).
    progressive_items: bool = False
    # The wooden arrows, blue candle and blue ring join the major-item shuffle (§5, §6).
    shop_items_in_pool: bool = False
    # Version 3: the owner's 2.0 flags, each On / Off / ? (OWNER_2_0_FIELDS).
    shuffle_blue_potion: ThreeState = ThreeState.OFF
    add_l4_sword: ThreeState = ThreeState.OFF
    extra_raft_blocks: ThreeState = ThreeState.OFF
    extra_power_bracelet_blocks: ThreeState = ThreeState.OFF
    speed_up_dungeon_transitions: ThreeState = ThreeState.OFF
    speed_up_heart_fill: ThreeState = ThreeState.OFF
    recorder_kills_pols_voice: ThreeState = ThreeState.OFF
    four_potion_inventory: ThreeState = ThreeState.OFF
    like_like_eats_rupees: ThreeState = ThreeState.OFF
    magical_boomerang_damage: ThreeState = ThreeState.OFF
    randomize_lost_hills: ThreeState = ThreeState.OFF
    randomize_dead_woods: ThreeState = ThreeState.OFF
    # Version 4 (ASNB): Add L4 Sword's sword in a new level-2 item cellar instead of level 9; and
    # level 9 opening for a level-4 sword instead of the triforce pieces.
    l4_sword_in_level_2: bool = False
    level_9_entrance_sword: bool = False
    # Version 5: Oops All Enemies and Oops All Bosses.
    oops_all_enemies: OopsAllEnemies = OopsAllEnemies.OFF
    oops_all_bosses: OopsAllBosses = OopsAllBosses.OFF
    # Version 6: the ZORA 1.0 flags, each On / Off / ? (ZORA_1_0_FIELDS).
    allow_triforces_in_stairways: ThreeState = ThreeState.OFF
    shuffle_wood_sword: ThreeState = ThreeState.OFF
    # Version 7: Pegasus Boots, On / Off / ? (PEGASUS_BOOTS_FIELDS).
    pegasus_boots: ThreeState = ThreeState.OFF
    # Version 8: Expanded Dungeon Locations, On / Off / ? (EXPANDED_DUNGEON_LOCATIONS_FIELDS).
    expanded_dungeon_locations: ThreeState = ThreeState.OFF
    # Version 9: Highlight No-Drop Rooms, On / Off / ? (HIGHLIGHT_NO_DROP_ROOMS_FIELDS).
    highlight_no_drop_rooms: ThreeState = ThreeState.OFF
    # Version 10: Do Not Segment Dungeons, On / Off / ? (DO_NOT_SEGMENT_DUNGEONS_FIELDS).
    do_not_segment_dungeons: ThreeState = ThreeState.OFF
    # Version 11: Disable Custom Music (PLAYER_SETTING_RULES): Music offers only Off and Vanilla.
    disable_custom_music: bool = False

    def __post_init__(self) -> None:
        cap = self.magical_sword_hearts_highest
        if cap is not None and cap not in HEARTS_CAP_CHOICES:
            raise ValueError(f"magical_sword_hearts_highest must be None or in "
                             f"{HEARTS_CAP_CHOICES.start}..{HEARTS_CAP_CHOICES.stop - 1}, got {cap}")

    @property
    def is_default(self) -> bool:
        return self == ZoraFlags()

    def is_on(self, name: str) -> bool:
        """An On / Off / ? field resolved on (call on resolved flags: a "?" is not on)."""
        return getattr(self, name) is ThreeState.ON

    @property
    def is_resolved(self) -> bool:
        return all(getattr(self, name) is not ThreeState.POSSIBLE for name in THREE_STATE_FIELDS)

    @property
    def l4_sword(self) -> L4Sword:
        """Add L4 Sword's three-way setting (call on resolved flags: a released "?" shows as Off)."""
        if self.add_l4_sword is not ThreeState.ON:
            return L4Sword.OFF
        return L4Sword.LEVEL_2 if self.l4_sword_in_level_2 else L4Sword.LEVEL_9


class L4Sword(Enum):
    """Add L4 Sword's setting (docs/design/asnb.md section 1): the page's one three-way control
    over the released field add_l4_sword and the version-4 field l4_sword_in_level_2."""
    OFF = "off"
    LEVEL_2 = "level 2"
    LEVEL_9 = "level 9"


DEFAULT = ZoraFlags()


def _index_of(flags: ZoraFlags, field: ZoraField) -> int:
    """A field's digit in the payload (a retired field's: its default, Off)."""
    if field.name in RETIRED_FIELDS:
        return int(ThreeState.OFF)
    value = getattr(flags, field.name)
    if field.name == "magical_sword_hearts_highest":
        return HEARTS_FOLLOW_Z1R if value is None else value - HEARTS_CAP_BASE
    return int(value)


def _value_of(field: ZoraField, index: int) -> bool | int | ThreeState | None:
    """A field's value from its digit."""
    if field.name in ENUM_FIELDS:
        return ENUM_FIELDS[field.name](index)
    if field.name == "magical_sword_hearts_highest":
        return None if index == HEARTS_FOLLOW_Z1R else HEARTS_CAP_BASE + index
    if field.slots == THREE_STATE_SLOTS:
        return ThreeState(index)
    return bool(index)


def _fields_of(version: int) -> tuple[ZoraField, ...]:
    return tuple(field for field in FIELDS if field.version <= version)


# ---------------------------------------------------------------------------
# Decode, encode, canonical form
# ---------------------------------------------------------------------------

def _parse_payload(payload: str) -> int:
    number = 0
    for character in payload:
        if character not in DIGIT_VALUE:
            raise ZoraFlagStringError(f"invalid character {character!r}")
        number = number * RADIX + DIGIT_VALUE[character]
    return number


def _format_payload(number: int) -> str:
    digits = []
    while number:
        number, digit = divmod(number, RADIX)
        digits.append(ALPHABET[digit])
    return "".join(reversed(digits)) or ALPHABET[0]


def decode(flag_string: str) -> ZoraFlags:
    """The flags a ZORA string holds; the empty string is every default."""
    if flag_string == "":
        return DEFAULT
    match = _STRING_PATTERN.fullmatch(flag_string)
    if match is None:
        raise ZoraFlagStringError(f"not a ZORA flag string (expected <version>{VERSION_SEPARATOR}<flags>): "
                                  f"{flag_string!r}")
    version = int(match.group(1))
    if version > CURRENT_VERSION:
        raise ZoraFlagStringError(f"version {version} is newer than this ZORA (knows up to {CURRENT_VERSION})")
    number = _parse_payload(match.group(2))
    values: dict[str, bool | int | ThreeState | None] = {}
    for field in _fields_of(version):
        number, index = divmod(number, field.slots)
        if field.name not in RETIRED_FIELDS:
            values[field.name] = _value_of(field, index)
    if number:
        raise ZoraFlagStringError(f"flags beyond version {version}'s fields: {flag_string!r}")
    return ZoraFlags(**values)  # type: ignore[arg-type]


def encode(flags: ZoraFlags) -> str:
    """The canonical string: empty for the defaults, else the lowest version
    holding every field away from its default."""
    changed = [field for field in FIELDS if _index_of(flags, field) != _index_of(DEFAULT, field)]
    if not changed:
        return ""
    version = max(field.version for field in changed)
    number = 0
    for field in reversed(_fields_of(version)):
        number = number * field.slots + _index_of(flags, field)
    return f"{version}{VERSION_SEPARATOR}{_format_payload(number)}"


def canonicalize(flag_string: str) -> str:
    return encode(decode(flag_string))


def game_string(flags: ZoraFlags) -> str:
    """The canonical string of the flags that shape the game: every PLAYER_SETTING_RULES field at
    its default. The game's random streams and level encoding key take this one, so a flag that
    only rules the player settings never changes the game."""
    return encode(replace(flags, **{name: getattr(DEFAULT, name) for name in PLAYER_SETTING_RULES}))


# Every ZoraFlags attribute has exactly one field; the other fields are retired.
assert {field.name for field in FIELDS} - RETIRED_FIELDS == {field.name for field in fields(ZoraFlags)}


# ---------------------------------------------------------------------------
# Validation against the Z1R settings
# ---------------------------------------------------------------------------

# The Z1R field that re-draws the sword heart requirements (FP-SWORD-01).
REDRAW_SWORD_HEARTS = TOGGLES_BY_ID["B10"]
# PRG0's requirement when B10 is off: the engine's $B0 heart value (12
# containers; Z_01 cave code, "$C is the minimum otherwise").
VANILLA_MAGICAL_SWORD_HEARTS = 12
# Owner requirement B: with Randomize Magical Sword on, the cave asks for at most 12 hearts.
RANDOMIZED_MAGICAL_SWORD_MAX_HEARTS = 12


def magical_sword_heart_range(flags: ZoraFlags, z1r: Settings) -> range:
    """The heart counts the magical-sword cave may ask for: the Z1R string's
    (FL-DEP-03, 10 + C22 to 14 - C23 with B10 on; PRG0's 12 with it off),
    capped by the ZORA field. Empty when the cap is below the lowest."""
    if z1r.is_on(REDRAW_SWORD_HEARTS):
        lowest, highest = magical_sword_hearts(z1r)
    else:
        lowest = highest = VANILLA_MAGICAL_SWORD_HEARTS
    if flags.magical_sword_hearts_highest is not None:
        highest = min(highest, flags.magical_sword_hearts_highest)
    return range(lowest, highest + 1)


def starting_heart_containers(z1r: Settings) -> int:
    """M of owner requirement B: the heart containers Link starts with
    (FL-DEP-03, C16 + 1). A random C16 counts as its fewest, 1, so a check
    made before the draw holds for every outcome."""
    try:
        return starting_hearts(z1r)
    except UnresolvedError:
        return min(STARTING_HEARTS_RANDOM_CHOICES) + 1


def _redrawn_if_random(z1r: Settings) -> Settings:
    """The Z1R settings with a "?" on B10 counted as on, for a check made before the "?" values
    are resolved (with the settings as they are, a "?" counts as off)."""
    if z1r.toggle(REDRAW_SWORD_HEARTS) is ThreeState.POSSIBLE:
        return z1r.updated(toggles={REDRAW_SWORD_HEARTS.id: ThreeState.ON})
    return z1r


def highest_magical_sword_hearts(flags: ZoraFlags, z1r: Settings) -> int:
    """The most hearts the magical-sword cave may ask for under these strings, before the "?"
    values are resolved: a "?" on B10 counts as on, so every outcome is covered."""
    hearts = magical_sword_heart_range(flags, _redrawn_if_random(z1r))
    return hearts[-1] if hearts else hearts.start


def sword_hearts_cap_conflict(flags: ZoraFlags, z1r: Settings) -> str | None:
    """The ZORA cap below the Z1R string's lowest magical-sword requirement leaves the cave no
    count to ask for (an empty magical_sword_heart_range, which change_sword_hearts cannot draw
    from). Judged before the "?" values are resolved, a "?" on B10 counted as on: a Random Change
    Sword Hearts that drew on used to pass the check and crash generation (the 2026-10-18
    Archipelago scan). Refused, never changed, as every conflict is: clamping would ask for fewer
    hearts than the Z1R string's lowest."""
    for settings in (z1r, _redrawn_if_random(z1r)):
        hearts = magical_sword_heart_range(flags, settings)
        if not hearts:
            return (f"Magical-sword hearts, highest: the cap of {flags.magical_sword_hearts_highest} hearts is "
                    f"below the {hearts.start} hearts the Z1R flags ask for at least (Magical Sword Hearts "
                    f"(min) and (max) with Change Sword Hearts on or Random). Raise the cap to {hearts.start} "
                    f"or more, lower Magical Sword Hearts (min), or turn Change Sword Hearts off.")
    return None


def sword_hearts_conflict(flags: ZoraFlags, z1r: Settings) -> str | None:
    """Owner requirement: with Randomize Magical Sword on, the sword-hearts settings must not
    allow more than 12 hearts. Refused, never changed: the player resolves it by hand, with
    B10 (Change sword hearts) off or the ZORA heart cap at 12 or lower."""
    highest = highest_magical_sword_hearts(flags, z1r)
    if not flags.randomize_magical_sword or highest <= RANDOMIZED_MAGICAL_SWORD_MAX_HEARTS:
        return None
    return (f"Randomize Magical Sword: the magical-sword cave may ask for up to {highest} hearts "
            f"(at most {RANDOMIZED_MAGICAL_SWORD_MAX_HEARTS} allowed). Turn Change Sword Hearts off, "
            f"or set the magical-sword hearts cap to {RANDOMIZED_MAGICAL_SWORD_MAX_HEARTS} or lower.")


# The settings a sword-hearts conflict names, where the page shows it: the ZORA fields and the
# Z1R field that re-draws the requirement.
SWORD_HEARTS_CONFLICT_FIELDS = ("randomize_magical_sword", "magical_sword_hearts_highest",
                                REDRAW_SWORD_HEARTS.id)
# The settings the cap conflict names: the cap, and the Z1R fields that set the lowest requirement.
SWORD_HEARTS_CAP_CONFLICT_FIELDS = ("magical_sword_hearts_highest", REDRAW_SWORD_HEARTS.id,
                                    MAGICAL_SWORD_LOWEST.id, MAGICAL_SWORD_HIGHEST.id)


# The owner's 2.0 dependencies (owner decisions, 2026-10-07). An explicit conflict (both sides set,
# neither "?") is refused and shown in red; when a "?" would make one, the "?" side resolves to off
# (resolve_owner_dependencies), never an explicit choice.
L4_SWORD_CONFLICT = "Add L4 Sword needs Progressive Items: turn Progressive Items on, or Add L4 Sword off."
L4_SWORD_CONFLICT_FIELDS = ("add_l4_sword", "progressive_items")
# The Z1R field for the old app's "Include Any Road Caves": B04, Shuffle "Take Any Road" Caves.
TAKE_ANY_ROAD_CAVES = TOGGLES_BY_ID["B04"]
# Randomize Dead Woods forces Add Lost Woods Shortcut (B88; FP-WOODS-01) on (owner rule, beta 7): its
# sequences end with a step south, so the solved maze lets Link out south, never west, and without
# the shortcut (or the bridges, B87, or the ladder) the river's west side cannot be reached on foot.
LOST_WOODS_SHORTCUT = TOGGLES_BY_ID["B88"]
DEAD_WOODS_FIELD = "randomize_dead_woods"
SHORTCUT_FORCED_NOTE = ("On while Randomize Dead Woods is on: its maze lets you out to the south, never west, "
                        "so the shortcut is the way west without the ladder.")
SHORTCUT_RANDOM_NOTE = ("On in every seed where Randomize Dead Woods (Random) comes up on: its maze lets you out to "
                        "the south, never west.")
BRACELET_BLOCKS_CONFLICT = ('Extra Power Bracelet Blocks cannot be used with Shuffle "Take Any Road" Caves '
                            "on: turn one of them off.")
BRACELET_BLOCKS_CONFLICT_FIELDS = ("extra_power_bracelet_blocks", TAKE_ANY_ROAD_CAVES.id)
# Extra Raft Blocks (§3) puts screen $34 behind the raft, and on a 2nd Quest overworld $34 is level
# 3's entrance. With the items not shuffled, the dungeons left in place and a Dungeon Quest that keeps
# the raft in level 3 (1st Quest dungeons and shapes do; 2nd Quest dungeons keep it in level 5, and
# Mixed Quest redraws the levels each attempt), the raft is inside the one level that needs it: the
# acceptance check rejects nearly every attempt (96-100% of them, 2026-10-23; the rest only by a
# rare other entrance), and a seed fails after 2,000. Each Random value that can come up into the
# combination counts, as for the other refusals.
RAFT_TRAP_OVERWORLDS = frozenset({OverworldQuest.SECOND_QUEST, OverworldQuest.MIXED_SECOND_QUEST_VARIANT,
                                  OverworldQuest.RANDOM})
RAFT_TRAP_ITEM_SHUFFLES = frozenset({ItemShuffleScope.NONE, ItemShuffleScope.RANDOM})
RAFT_TRAP_CAVE_SHUFFLES = frozenset({CaveShuffle.VANILLA, CaveShuffle.NON_DUNGEON_CAVES_ONLY, CaveShuffle.RANDOM})
RAFT_FREE_DUNGEON_QUESTS = frozenset({DungeonLayoutSource.SECOND_QUEST, DungeonLayoutSource.MIXED})
OVERWORLD_QUEST, CAVE_SHUFFLE, ITEM_SHUFFLE = OPTIONS_BY_ID["C01"], OPTIONS_BY_ID["C05"], OPTIONS_BY_ID["C06"]
DUNGEON_QUEST = OPTIONS_BY_ID["C02"]
RAFT_BLOCKS_CONFLICT = (
    "Extra Raft Blocks cannot be used with a 2nd Quest overworld (Overworld Quest 2nd Quest or Mixed Quest - 2nd), "
    "Item Shuffle None, a Cave Shuffle that leaves the dungeons in place (Vanilla or Non-dungeons Only) and a "
    "Dungeon Quest other than 2nd Quest or Mixed Quest, Random included in each: level 3's entrance then needs the "
    "raft, which stays inside level 3. Turn Extra Raft Blocks off, or change one of the others.")
RAFT_BLOCKS_CONFLICT_FIELDS = ("extra_raft_blocks", OVERWORLD_QUEST.id, ITEM_SHUFFLE.id, CAVE_SHUFFLE.id,
                               DUNGEON_QUEST.id)


def keeps_raft_behind_raft(z1r: Settings) -> bool:
    """Whether the Z1R settings (asked, Random values counted, or resolved) can leave the raft in level
    3 behind its own raft-blocked entrance under Extra Raft Blocks."""
    return (z1r.option(OVERWORLD_QUEST) in RAFT_TRAP_OVERWORLDS
            and z1r.option(ITEM_SHUFFLE) in RAFT_TRAP_ITEM_SHUFFLES
            and z1r.option(CAVE_SHUFFLE) in RAFT_TRAP_CAVE_SHUFFLES
            and z1r.option(DUNGEON_QUEST) not in RAFT_FREE_DUNGEON_QUESTS)


def raft_blocks_conflict(flags: ZoraFlags, z1r: Settings) -> str | None:
    if flags.extra_raft_blocks is ThreeState.ON and keeps_raft_behind_raft(z1r):
        return RAFT_BLOCKS_CONFLICT
    return None


def l4_sword_conflict(flags: ZoraFlags) -> str | None:
    if flags.add_l4_sword is ThreeState.ON and not flags.progressive_items:
        return L4_SWORD_CONFLICT
    return None


# All Swords No Boards (docs/design/asnb.md section 2): each refused, never changed for the player.
SHAPES_ONLY = DungeonLayoutSource.GENERATED_SHAPES
DUNGEON_LAYOUT_SOURCE = OPTIONS_BY_ID["C02"]
WOODEN_SWORD_STATE = OPTIONS_BY_ID["C07"]
# Owner ruling (2026-10-08): released strings keep working. Beta 1's "?" on Add L4 Sword's released
# field keeps its meaning, Off or Level 9 decided per seed by its coin (resolve_question_marks), and
# the page does not offer it; only with Level 2 or the level-4-sword entrance is it refused.
L4_SWORD_RANDOM_WITH_ASNB = ("Add L4 Sword's random setting (Off or Level 9, from released flag strings) cannot "
                             "be combined with Level 2 or Level 9 Entrance = Level 4 sword: choose Off, Level 2 "
                             "or Level 9.")
L4_SWORD_RANDOM_WITH_ASNB_FIELDS = ("add_l4_sword", "level_9_entrance_sword")
LEVEL_2_WITHOUT_L4_SWORD = ("The ZORA string asks for Add L4 Sword's level-2 sword with Add L4 Sword off: "
                            "choose Off, Level 2 or Level 9.")
LEVEL_2_WITHOUT_L4_SWORD_FIELDS = ("add_l4_sword",)
ENTRANCE_NEEDS_LEVEL_2 = ("Level 9 Entrance = Level 4 sword needs Add L4 Sword = Level 2: a level-9 sword "
                          "would sit behind its own gate.")
ENTRANCE_NEEDS_LEVEL_2_FIELDS = ("level_9_entrance_sword", "add_l4_sword")
LEVEL_2_NEEDS_SHAPES = ("Add L4 Sword = Level 2 needs generated dungeon shapes (Dungeon layout source = "
                        "Generated shapes): only a generated level 2 can get a new item staircase.")
LEVEL_2_NEEDS_SHAPES_FIELDS = ("add_l4_sword", DUNGEON_LAYOUT_SOURCE.id)
ENTRANCE_NEEDS_NORMAL_SWORD = ("Level 9 Entrance = Level 4 sword needs the wooden sword in its cave (Wooden-sword "
                               "state = Normal): the other states remove swords.")
ENTRANCE_NEEDS_NORMAL_SWORD_FIELDS = ("level_9_entrance_sword", WOODEN_SWORD_STATE.id)
# Level 9 Entry (C08 = 1 to 12, FP-TRIF-02 to FP-TRIF-06) rewrites the same entrance check as the
# level-4-sword entrance (asm/asnb/level-9-gate), so the two never go together.
ENTRANCE_NEEDS_EIGHT_PIECES = ("Level 9 Entrance = Level 4 sword needs Level 9 Entry = 8 triforces: both choose "
                               "what level 9's entrance asks for.")
ENTRANCE_NEEDS_EIGHT_PIECES_FIELDS = ("level_9_entrance_sword", LEVEL_9_REQUIREMENT.id)


def asnb_conflicts(flags: ZoraFlags, z1r: Settings) -> list[tuple[str, tuple[str, ...]]]:
    """Section 2's refusals, and the two the encoding allows but the control cannot show: the
    released "?" on Add L4 Sword with Level 2 or the level-4-sword entrance, and its level-2 field
    set with it off. (Add L4 Sword without Progressive Items is l4_sword_conflict.)"""
    found: list[tuple[str, tuple[str, ...]]] = []
    random_l4 = flags.add_l4_sword is ThreeState.POSSIBLE
    if random_l4 and (flags.l4_sword_in_level_2 or flags.level_9_entrance_sword):
        found.append((L4_SWORD_RANDOM_WITH_ASNB, L4_SWORD_RANDOM_WITH_ASNB_FIELDS))
    elif flags.l4_sword_in_level_2 and flags.add_l4_sword is ThreeState.OFF:
        found.append((LEVEL_2_WITHOUT_L4_SWORD, LEVEL_2_WITHOUT_L4_SWORD_FIELDS))
    if flags.level_9_entrance_sword and not random_l4 and flags.l4_sword is not L4Sword.LEVEL_2:
        found.append((ENTRANCE_NEEDS_LEVEL_2, ENTRANCE_NEEDS_LEVEL_2_FIELDS))
    if flags.l4_sword is L4Sword.LEVEL_2 and z1r.option(DUNGEON_LAYOUT_SOURCE) != SHAPES_ONLY:
        found.append((LEVEL_2_NEEDS_SHAPES, LEVEL_2_NEEDS_SHAPES_FIELDS))
    if flags.level_9_entrance_sword and z1r.option(WOODEN_SWORD_STATE) != WoodenSwordState.NORMAL:
        found.append((ENTRANCE_NEEDS_NORMAL_SWORD, ENTRANCE_NEEDS_NORMAL_SWORD_FIELDS))
    if flags.level_9_entrance_sword and z1r.option(LEVEL_9_REQUIREMENT) != Level9Requirement.EIGHT_PIECES:
        found.append((ENTRANCE_NEEDS_EIGHT_PIECES, ENTRANCE_NEEDS_EIGHT_PIECES_FIELDS))
    return found


# Level 9 Item 1 and 2 (C26, C27; PS-ITEM-12): two pins that put an item in level 9 that level 9's
# own door needs first, so no pass is ever accepted (the 2026-10-18 Archipelago scan: 5-12% of
# seeds failed after 2,000 attempts, every rejection E1's). Refused, as the spec refuses the pins
# the long items (VA-REJ-08) would need to collect themselves (support.LEVEL_9_PINS). The values
# are FORCED_ITEM_OPTIONS' indices (zora/generate/steps/shuffle_items.py).
# Each pin with its name on the page (form.field_label; tests/test_pinned_items.py checks them)
LEVEL_9_PIN_NAMES = {LEVEL_9_FIRST_PIN: "Level 9 Item 1", LEVEL_9_SECOND_PIN: "Level 9 Item 2"}
BOOK_PIN = 1
WHITE_SWORD_PIN = 15
# Level 9 Entrance = Level 4 sword opens level 9 on four swords (wood, white, magical and Add L4
# Sword's level-2 one): a white sword in level 9 never counts toward it.
WHITE_SWORD_PIN_CONFLICT = ("{pin} = White Sword cannot be used with Level 9 Entrance = Level 4 sword: level 9 "
                            "opens on four swords, the White Sword among them, so it cannot wait inside. Choose "
                            "another item for {pin}, or set Level 9 Entrance to Triforce pieces.")
# Book to Understand NPCs (B48) hides a randomized maze's path until the book is held
# (AcceptanceCheck.knows_maze_path), and a dungeon door can lie past either maze (level 5's at $0B,
# past the Lost Hills, on the 1st Quest overworld; under a dungeon shuffle, some door past the Lost
# Hills or the Dead Woods in 3 to 24 of 40 seeds): its Triforce, which level 9 needs, then waits
# for a book that waits in level 9.
BOOK_PIN_CONFLICT = ("{pin} = Book cannot be used with Book to Understand NPCs on or Random and Randomize Lost "
                     "Hills or Randomize Dead Woods on or Random: a maze's path is sold only to a player with the "
                     "Book, and a dungeon past the maze may hold a Triforce level 9 needs. Choose another item "
                     "for {pin}, or turn one of the others off.")


def level_9_pin_conflicts(flags: ZoraFlags, z1r: Settings) -> list[tuple[str, tuple[str, ...]]]:
    """The pins of Level 9 Item 1 and 2 that put level 9's own key inside it (a "?" or Random
    counted as on, so every outcome is covered)."""
    found: list[tuple[str, tuple[str, ...]]] = []
    book_hides_a_maze = (z1r.toggle(BOOK_TO_UNDERSTAND_NPCS) is not ThreeState.OFF
                         and (flags.randomize_lost_hills is not ThreeState.OFF
                              or flags.randomize_dead_woods is not ThreeState.OFF))
    for pin, name in LEVEL_9_PIN_NAMES.items():
        value = z1r.option(pin)
        if value == WHITE_SWORD_PIN and flags.level_9_entrance_sword:
            found.append((WHITE_SWORD_PIN_CONFLICT.format(pin=name), (pin.id, "level_9_entrance_sword")))
        if value == BOOK_PIN and book_hides_a_maze:
            found.append((BOOK_PIN_CONFLICT.format(pin=name),
                          (pin.id, BOOK_TO_UNDERSTAND_NPCS.id, "randomize_lost_hills", "randomize_dead_woods")))
    return found


def bracelet_blocks_conflict(flags: ZoraFlags, z1r: Settings) -> str | None:
    if flags.extra_power_bracelet_blocks is ThreeState.ON and z1r.toggle(TAKE_ANY_ROAD_CAVES) is ThreeState.ON:
        return BRACELET_BLOCKS_CONFLICT
    return None


# Pegasus Boots (owner spec, 2026-10-17) replaces both boomerangs, so Magical Boomerang Does 1 HP
# Damage would do nothing: both on is refused; a "?" that comes up into it resolves off
# (resolve_owner_dependencies).
PEGASUS_BOOTS_CONFLICT = ("Pegasus Boots cannot be used with Magical Boomerang Does 1 HP Damage: the boots replace "
                          "both boomerangs. Turn one of them off.")
PEGASUS_BOOTS_CONFLICT_FIELDS = ("pegasus_boots", "magical_boomerang_damage")


def pegasus_boots_conflict(flags: ZoraFlags) -> str | None:
    if flags.is_on("pegasus_boots") and flags.is_on("magical_boomerang_damage"):
        return PEGASUS_BOOTS_CONFLICT
    return None


# Expanded Dungeon Locations (owner and Bogie, 2026-10-18): its mode follows Cave Shuffle, Dungeons
# Only giving "Expanded Brackets" and All Caves "Expanded + shuffle everything else", over the 1st
# Quest or (phase 2) the 2nd Quest overworld. Refused (on or "?"), never changed: Overworld Quest Mixed
# Quest - 1st, Mixed Quest - 2nd or Random (Mixed waits for Bogie's confirmation of its rules), and
# Cave Shuffle Vanilla, Non-dungeons Only or Random. Warned, not
# refused: Dungeons Only with Shuffle Wood Sword Cave or Shuffle Take Any Road Caves on or "?", whose
# coin turns about half those seeds into All Caves (FL-DEP-02 rule 1).
EXPANDED_DUNGEON_LOCATIONS_FIELD = "expanded_dungeon_locations"
OVERWORLD_QUEST = OPTIONS_BY_ID["C01"]
CAVE_SHUFFLE = OPTIONS_BY_ID["C05"]
WOOD_SWORD_CAVE_SHUFFLE = TOGGLES_BY_ID["B02"]
EXPANDED_CAVE_SHUFFLES = frozenset({CaveShuffle.DUNGEON_DOORS_ONLY, CaveShuffle.ALL_CAVES})
EXPANDED_QUESTS = frozenset({OverworldQuest.FIRST_QUEST, OverworldQuest.SECOND_QUEST})
EXPANDED_QUEST_CONFLICT = ("Expanded Dungeon Locations needs Overworld Quest: 1st Quest or 2nd Quest for now "
                           "(Mixed Quest - 1st, Mixed Quest - 2nd and Random are refused).")
EXPANDED_CAVES_CONFLICT = ("Expanded Dungeon Locations needs Cave Shuffle: Dungeons Only (Expanded Brackets) or "
                           "All Caves (Expanded + shuffle everything else); Vanilla, Non-dungeons Only and Random "
                           "are refused.")
EXPANDED_COIN_WARNING = ("With Cave Shuffle: Dungeons Only, Shuffle Wood Sword Cave or Shuffle Take Any Road Caves "
                         "on (or Random) makes about half the seeds shuffle every other cave too, as All Caves "
                         "does. Turn both off for Expanded Brackets in every seed.")


def expanded_dungeon_locations_conflicts(flags: ZoraFlags, z1r: Settings) -> list[tuple[str, tuple[str, ...]]]:
    """The settings Expanded Dungeon Locations (on or "?") is refused with, each with the fields it names."""
    if flags.expanded_dungeon_locations is ThreeState.OFF:
        return []
    found: list[tuple[str, tuple[str, ...]]] = []
    if z1r.option(OVERWORLD_QUEST) not in EXPANDED_QUESTS:
        found.append((EXPANDED_QUEST_CONFLICT, (EXPANDED_DUNGEON_LOCATIONS_FIELD, OVERWORLD_QUEST.id)))
    if z1r.option(CAVE_SHUFFLE) not in EXPANDED_CAVE_SHUFFLES:
        found.append((EXPANDED_CAVES_CONFLICT, (EXPANDED_DUNGEON_LOCATIONS_FIELD, CAVE_SHUFFLE.id)))
    return found


def warnings(flags: ZoraFlags, z1r: Settings) -> list[tuple[str, tuple[str, ...]]]:
    """Settings the page warns about but generation accepts, with the fields each names: Expanded
    Dungeon Locations (on or "?") with Dungeons Only and B02 or B04 on or "?"; Randomize Dead Woods
    "?" with Add Lost Woods Shortcut not on (on in the seeds where the maze comes up on)."""
    found: list[tuple[str, tuple[str, ...]]] = []
    expanded = flags.expanded_dungeon_locations is not ThreeState.OFF
    coin = any(z1r.toggle(toggle) is not ThreeState.OFF for toggle in (WOOD_SWORD_CAVE_SHUFFLE, TAKE_ANY_ROAD_CAVES))
    if expanded and coin and z1r.option(CAVE_SHUFFLE) == CaveShuffle.DUNGEON_DOORS_ONLY:
        found.append((EXPANDED_COIN_WARNING, (EXPANDED_DUNGEON_LOCATIONS_FIELD, WOOD_SWORD_CAVE_SHUFFLE.id,
                                              TAKE_ANY_ROAD_CAVES.id)))
    if flags.randomize_dead_woods is ThreeState.POSSIBLE and z1r.toggle(LOST_WOODS_SHORTCUT) is not ThreeState.ON:
        found.append((SHORTCUT_RANDOM_NOTE, (LOST_WOODS_SHORTCUT.id,)))
    return found


# Swords (C07; features-behavior.md FP-WOOD-01 to FP-WOOD-04) at any value but Normal, Random
# included, changes or removes swords, so the ZORA flags that place, add or upgrade swords are
# refused with it (owner decision, 2026-10-17): each named with its own message at both settings.
SWORD_FLAG_LABELS = {"add_l4_sword": "Add L4 Sword", "randomize_magical_sword": "Randomize Magical Sword",
                     "shuffle_wood_sword": "Shuffle Wood Sword", "progressive_items": "Progressive Items"}


def sword_state_conflicts(flags: ZoraFlags, z1r: Settings) -> list[tuple[str, tuple[str, ...]]]:
    """Each of Add L4 Sword (on or random), Randomize Magical Sword, Shuffle Wood Sword (on or
    random) and Progressive Items (its sword upgrades) with Swords at any value but Normal."""
    if z1r.option(WOODEN_SWORD_STATE) == WoodenSwordState.NORMAL:
        return []
    asked = {"add_l4_sword": flags.add_l4_sword is not ThreeState.OFF,
             "randomize_magical_sword": flags.randomize_magical_sword,
             "shuffle_wood_sword": flags.shuffle_wood_sword is not ThreeState.OFF,
             "progressive_items": flags.progressive_items}
    return [(sword_state_message(label), (name, WOODEN_SWORD_STATE.id))
            for name, label in SWORD_FLAG_LABELS.items() if asked[name]]


def sword_state_message(label: str) -> str:
    return (f"{label} cannot be used with Swords set to anything but Normal (Random included): Swords changes "
            f"or removes the swords {label} works with. Set Swords to Normal, or turn {label} off.")


def conflicts(flags: ZoraFlags, z1r: Settings) -> list[tuple[str, tuple[str, ...]]]:
    """Every conflict between the strings, with the settings it names (the page shows each in
    red at them). Never resolved for the player."""
    cap = sword_hearts_cap_conflict(flags, z1r)
    found = [(cap, SWORD_HEARTS_CAP_CONFLICT_FIELDS),
             (None if cap else sword_hearts_conflict(flags, z1r), SWORD_HEARTS_CONFLICT_FIELDS),
             (l4_sword_conflict(flags), L4_SWORD_CONFLICT_FIELDS),
             (bracelet_blocks_conflict(flags, z1r), BRACELET_BLOCKS_CONFLICT_FIELDS),
             (raft_blocks_conflict(flags, z1r), RAFT_BLOCKS_CONFLICT_FIELDS),
             (pegasus_boots_conflict(flags), PEGASUS_BOOTS_CONFLICT_FIELDS)]
    return ([(message, names) for message, names in found if message is not None] + asnb_conflicts(flags, z1r)
            + sword_state_conflicts(flags, z1r) + expanded_dungeon_locations_conflicts(flags, z1r)
            + level_9_pin_conflicts(flags, z1r))


def validate(flags: ZoraFlags, z1r: Settings) -> list[str]:
    """Every reason the pair of strings is refused (empty when accepted)."""
    reasons = []
    if (cap := sword_hearts_cap_conflict(flags, z1r)) is not None:
        reasons.append(cap)
    elif (sword := sword_hearts_conflict(flags, z1r)) is not None:
        reasons.append(sword)
    reasons.extend(owner_conflict for owner_conflict in (l4_sword_conflict(flags), bracelet_blocks_conflict(flags, z1r),
                                                         raft_blocks_conflict(flags, z1r),
                                                         pegasus_boots_conflict(flags))
                   if owner_conflict is not None)
    reasons.extend(message for message, _names in asnb_conflicts(flags, z1r))
    reasons.extend(message for message, _names in sword_state_conflicts(flags, z1r))
    reasons.extend(message for message, _names in expanded_dungeon_locations_conflicts(flags, z1r))
    reasons.extend(message for message, _names in level_9_pin_conflicts(flags, z1r))
    return reasons


# ---------------------------------------------------------------------------
# The "?" values (versions 3 and 6): their own stream, then the dependencies
# ---------------------------------------------------------------------------

QUESTION_MARK_STREAM = b"zora ZORA ? vals"      # 16 bytes at most (BLAKE2b's person)


def question_mark_draws(seed: int, z1r_canonical: str, zora_canonical: str) -> Iterator[int]:
    """The coins that decide the "?" values of the On / Off / ? fields: derived only from the seed number and both
    canonical strings, separate from the generation's stream and from FL-DEP-04's (the Z1R
    "?" values), so neither changes. Each coin is one bit of a BLAKE2b counter stream."""
    counter = 0
    while True:
        message = KEY_SEPARATOR.join((str(seed), z1r_canonical, zora_canonical, str(counter))).encode("utf-8")
        digest = hashlib.blake2b(message, digest_size=SEED_BITS // 8, person=QUESTION_MARK_STREAM).digest()
        number = int.from_bytes(digest, "little")
        for _ in range(SEED_BITS):
            yield number & 1
            number >>= 1
        counter += 1


def resolve_question_marks(flags: ZoraFlags, seed: int, z1r_canonical: str, zora_canonical: str) -> ZoraFlags:
    """Each "?" of an On / Off / ? field decided for this seed by a fair coin, in payload order
    (THREE_STATE_FIELDS: version 3's, then version 6's, 7's, 8's, 9's and 10's, so an older "?" keeps its coin). The
    resolved values are never shown to the page."""
    if flags.is_resolved:
        return flags
    coins = question_mark_draws(seed, z1r_canonical, zora_canonical)
    decided = {name: ThreeState.ON if next(coins) else ThreeState.OFF
               for name in THREE_STATE_FIELDS if getattr(flags, name) is ThreeState.POSSIBLE}
    return replace(flags, **decided)  # type: ignore[arg-type]


def resolve_owner_dependencies(resolved: ZoraFlags, asked: ZoraFlags, resolved_z1r: Settings,
                               asked_z1r: Settings) -> tuple[ZoraFlags, Settings]:
    """The owner's 2.0 dependencies after both strings' "?" values are drawn (explicit conflicts
    were refused before): a "?" that comes up into a conflict resolves to off.
      - Add L4 Sword without Progressive Items: Add L4 Sword is off.
      - Extra Power Bracelet Blocks with B04 on: the side that was "?" is off (Bracelet Blocks
        when both were).
    (Allow Triforces in Stairways has had no dependency since the owner's redesign, 2026-10-18:
    its Triforces take their spots before any Item Shuffle.)
    And Pegasus Boots' (owner spec, 2026-10-17):
      - Pegasus Boots with Magical Boomerang Does 1 HP Damage: the side that was "?" is off
        (Magical Boomerang Does 1 HP Damage when both were: it would do nothing with the boots).
    And beta 8's:
      - Extra Raft Blocks with a 2nd Quest overworld, Item Shuffle None, the dungeons left in place and
        the raft kept in level 3 (keeps_raft_behind_raft, on the resolved settings): Extra Raft Blocks is off.
    And beta 7's (owner rule):
      - Randomize Dead Woods on: Add Lost Woods Shortcut (B88) is on, whatever the Z1R string asks
        (shortcut_forced_on)."""
    if resolved.is_on("pegasus_boots") and resolved.is_on("magical_boomerang_damage"):
        if asked.pegasus_boots is ThreeState.POSSIBLE and asked.magical_boomerang_damage is ThreeState.ON:
            resolved = replace(resolved, pegasus_boots=ThreeState.OFF)
        else:
            resolved = replace(resolved, magical_boomerang_damage=ThreeState.OFF)
    if resolved.is_on("add_l4_sword") and not resolved.progressive_items:
        resolved = replace(resolved, add_l4_sword=ThreeState.OFF)
    if resolved.is_on("extra_power_bracelet_blocks") and resolved_z1r.is_on(TAKE_ANY_ROAD_CAVES):
        if asked.extra_power_bracelet_blocks is ThreeState.POSSIBLE:
            resolved = replace(resolved, extra_power_bracelet_blocks=ThreeState.OFF)
        else:
            assert asked_z1r.toggle(TAKE_ANY_ROAD_CAVES) is ThreeState.POSSIBLE
            resolved_z1r = resolved_z1r.updated(toggles={TAKE_ANY_ROAD_CAVES.id: ThreeState.OFF})
    if resolved.is_on("extra_raft_blocks") and keeps_raft_behind_raft(resolved_z1r):
        # asked on with these settings is refused (raft_blocks_conflict), so only a "?" gets here
        resolved = replace(resolved, extra_raft_blocks=ThreeState.OFF)
    if shortcut_forced_on(resolved):
        resolved_z1r = resolved_z1r.updated(toggles={LOST_WOODS_SHORTCUT.id: ThreeState.ON})
    return resolved, resolved_z1r


def shortcut_forced_on(flags: ZoraFlags) -> bool:
    """Whether Randomize Dead Woods (resolved, or asked on) forces Add Lost Woods Shortcut on."""
    return flags.randomize_dead_woods is ThreeState.ON


def forced_z1r_values(flags: ZoraFlags) -> list[tuple[str, ThreeState, str]]:
    """The Z1R fields the ZORA flags as asked set whatever the Z1R string holds, each with its
    value and the page's note: Add Lost Woods Shortcut on while Randomize Dead Woods is on."""
    if shortcut_forced_on(flags):
        return [(LOST_WOODS_SHORTCUT.id, ThreeState.ON, SHORTCUT_FORCED_NOTE)]
    return []


# The version-3 and version-7 fields whose behavior this build produces; any other one on or "?" is
# refused (FlagsRefused), never ignored.
PRODUCED_OWNER_FIELDS: frozenset[str] = frozenset((*OWNER_2_0_FIELDS, *PEGASUS_BOOTS_FIELDS))
PATCHED_OWNER_FIELDS = (*OWNER_2_0_FIELDS, *PEGASUS_BOOTS_FIELDS)


# Fields refused on or "?" until their generation is built (none now: Expanded Dungeon Locations'
# unbuilt settings are refused as conflicts, expanded_dungeon_locations_conflicts).
UNBUILT_FIELDS: tuple[str, ...] = ()


def unproduced_fields(flags: ZoraFlags) -> list[str]:
    return [name for name in (*PATCHED_OWNER_FIELDS, *UNBUILT_FIELDS)
            if getattr(flags, name) is not ThreeState.OFF and name not in PRODUCED_OWNER_FIELDS]



# ---------------------------------------------------------------------------
# Seed derivation and the level-encoding key
# ---------------------------------------------------------------------------

SEED_BITS = 64
SEED_DOMAIN = b"ZORA flags v1"
# Joins the two strings in the level-encoding key: outside both alphabets
# (the Z1R string's has no space, the ZORA string's none either).
KEY_SEPARATOR = " "


def generation_seed(seed: int, z1r_canonical: str, zora_canonical: str) -> int:
    """The number the generator's Rng is seeded with.

    Today the Rng takes the seed number as it is (the Z1R string reaches
    generation through its decoded settings only), and with the ZORA string
    at its default that stays so exactly. Any other ZORA string mixes both
    canonical strings and the seed through BLAKE2b into a new 64-bit seed,
    so turning on a ZORA flag moves the whole random stream (and with it the
    finished ROM and its file-select code, FP-HASH-01)."""
    if zora_canonical == "":
        return seed
    message = KEY_SEPARATOR.join((str(seed), z1r_canonical, zora_canonical)).encode("utf-8")
    digest = hashlib.blake2b(message, digest_size=SEED_BITS // 8, person=SEED_DOMAIN).digest()
    return int.from_bytes(digest, "little")


OOPS_ALL_STREAM = b"zora oops all"         # 16 bytes at most (BLAKE2b's person)


def oops_all_seed(seed: int, z1r_canonical: str, zora_canonical: str) -> int:
    """The key of Oops All's own random stream (docs/design/oops-all.md 2.8): derived only from
    the seed number and both canonical strings, so its draws move nothing in the generation's
    stream. (Turning Oops on still changes the whole seed: its fields are in generation_seed's
    key like every ZORA flag, owner decision 1.)"""
    message = KEY_SEPARATOR.join((str(seed), z1r_canonical, zora_canonical)).encode("utf-8")
    digest = hashlib.blake2b(message, digest_size=SEED_BITS // 8, person=OOPS_ALL_STREAM).digest()
    return int.from_bytes(digest, "little")


def level_encoding_text(z1r_canonical: str, zora_canonical: str) -> str:
    """The flag text of the level-encoding key (FP-TOURNEY-01's settings
    bytes, LevelEncodingKey.flag_string): the Z1R string alone while the
    ZORA string is at its default, else both, so the key covers both."""
    if zora_canonical == "":
        return z1r_canonical
    return f"{z1r_canonical}{KEY_SEPARATOR}{zora_canonical}"
