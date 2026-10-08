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

from zora.flags.codec import ALPHABET, DIGIT_VALUE, RADIX
from zora.flags.dependencies import UnresolvedError, magical_sword_hearts, starting_hearts
from zora.flags.fields import STARTING_HEARTS_RANDOM_CHOICES, TOGGLES_BY_ID, Settings, ThreeState

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
# older string keeps its meaning and its spelling. In payload order.
THREE_STATE_SLOTS = 3
OWNER_2_0_FIELDS = (
    "shuffle_blue_potion",                 # §1, merged with plan §13's Phase 2B
    "add_l4_sword",                        # §2 (owner design: sold in the potion shop)
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
    *(ZoraField(name, THREE_STATE_SLOTS, version=3) for name in OWNER_2_0_FIELDS),
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
    auto_show_letter: ThreeState = ThreeState.OFF
    like_like_eats_rupees: ThreeState = ThreeState.OFF
    magical_boomerang_damage: ThreeState = ThreeState.OFF
    randomize_lost_hills: ThreeState = ThreeState.OFF
    randomize_dead_woods: ThreeState = ThreeState.OFF

    def __post_init__(self) -> None:
        cap = self.magical_sword_hearts_highest
        if cap is not None and cap not in HEARTS_CAP_CHOICES:
            raise ValueError(f"magical_sword_hearts_highest must be None or in "
                             f"{HEARTS_CAP_CHOICES.start}..{HEARTS_CAP_CHOICES.stop - 1}, got {cap}")

    @property
    def is_default(self) -> bool:
        return self == ZoraFlags()

    def is_on(self, name: str) -> bool:
        """A version-3 field resolved on (call on resolved flags: a "?" is not on)."""
        return getattr(self, name) is ThreeState.ON

    @property
    def is_resolved(self) -> bool:
        return all(getattr(self, name) is not ThreeState.POSSIBLE for name in OWNER_2_0_FIELDS)


DEFAULT = ZoraFlags()


def _index_of(flags: ZoraFlags, field: ZoraField) -> int:
    """A field's digit in the payload."""
    value = getattr(flags, field.name)
    if field.name == "magical_sword_hearts_highest":
        return HEARTS_FOLLOW_Z1R if value is None else value - HEARTS_CAP_BASE
    return int(value)


def _value_of(field: ZoraField, index: int) -> bool | int | ThreeState | None:
    """A field's value from its digit."""
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


# Every ZoraFlags attribute has exactly one field.
assert {field.name for field in FIELDS} == {field.name for field in fields(ZoraFlags)}


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


def highest_magical_sword_hearts(flags: ZoraFlags, z1r: Settings) -> int:
    """The most hearts the magical-sword cave may ask for under these strings, before the "?"
    values are resolved: a "?" on B10 counts as on, so every outcome is covered."""
    if z1r.toggle(REDRAW_SWORD_HEARTS) is ThreeState.POSSIBLE:
        z1r = z1r.updated(toggles={REDRAW_SWORD_HEARTS.id: ThreeState.ON})
    hearts = magical_sword_heart_range(flags, z1r)
    return hearts[-1] if hearts else hearts.start


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


# The Z1R field Progressive Items refuses (PI-FLAG-03).
EXTRA_CANDLES = TOGGLES_BY_ID["B09"]
EXTRA_CANDLES_CONFLICT = ("Progressive Items cannot be used with Extra Candles: the two extra candles would "
                          "give the red candle at the start.")
# The settings that conflict names, where the page shows it.
EXTRA_CANDLES_CONFLICT_FIELDS = ("progressive_items", EXTRA_CANDLES.id)


def extra_candles_conflict(flags: ZoraFlags, z1r: Settings) -> str | None:
    """PI-FLAG-03: Progressive Items refuses B09 (Add extra candle wares) on. A "?" on B09 is not
    refused: it resolves to off (without_extra_candles)."""
    if flags.progressive_items and z1r.toggle(EXTRA_CANDLES) is ThreeState.ON:
        return EXTRA_CANDLES_CONFLICT
    return None


def without_extra_candles(flags: ZoraFlags, resolved: Settings, asked: Settings) -> Settings:
    """PI-FLAG-03: with Progressive Items on, a "?" on B09 resolves to off. Applied after the
    "?" values are drawn, so every other draw keeps its outcome."""
    if flags.progressive_items and asked.toggle(EXTRA_CANDLES) is ThreeState.POSSIBLE:
        return resolved.updated(toggles={EXTRA_CANDLES.id: ThreeState.OFF})
    return resolved


# The owner's 2.0 dependencies (owner decisions, 2026-10-07). An explicit conflict (both sides set,
# neither "?") is refused and shown in red; when a "?" would make one, the "?" side resolves to off
# (resolve_owner_dependencies), never an explicit choice.
L4_SWORD_CONFLICT = "Add L4 Sword needs Progressive Items: turn Progressive Items on, or Add L4 Sword off."
L4_SWORD_CONFLICT_FIELDS = ("add_l4_sword", "progressive_items")
# The Z1R field for the old app's "Include Any Road Caves": B04, Shuffle "Take Any Road" Caves.
TAKE_ANY_ROAD_CAVES = TOGGLES_BY_ID["B04"]
BRACELET_BLOCKS_CONFLICT = ('Extra Power Bracelet Blocks cannot be used with Shuffle "Take Any Road" Caves '
                            "on: turn one of them off.")
BRACELET_BLOCKS_CONFLICT_FIELDS = ("extra_power_bracelet_blocks", TAKE_ANY_ROAD_CAVES.id)


def l4_sword_conflict(flags: ZoraFlags) -> str | None:
    if flags.add_l4_sword is ThreeState.ON and not flags.progressive_items:
        return L4_SWORD_CONFLICT
    return None


def bracelet_blocks_conflict(flags: ZoraFlags, z1r: Settings) -> str | None:
    if flags.extra_power_bracelet_blocks is ThreeState.ON and z1r.toggle(TAKE_ANY_ROAD_CAVES) is ThreeState.ON:
        return BRACELET_BLOCKS_CONFLICT
    return None


def conflicts(flags: ZoraFlags, z1r: Settings) -> list[tuple[str, tuple[str, ...]]]:
    """Every conflict between the strings, with the settings it names (the page shows each in
    red at them). Never resolved for the player."""
    found = [(sword_hearts_conflict(flags, z1r), SWORD_HEARTS_CONFLICT_FIELDS),
             (extra_candles_conflict(flags, z1r), EXTRA_CANDLES_CONFLICT_FIELDS),
             (l4_sword_conflict(flags), L4_SWORD_CONFLICT_FIELDS),
             (bracelet_blocks_conflict(flags, z1r), BRACELET_BLOCKS_CONFLICT_FIELDS)]
    return [(message, names) for message, names in found if message is not None]


def validate(flags: ZoraFlags, z1r: Settings) -> list[str]:
    """Every reason the pair of strings is refused (empty when accepted)."""
    reasons = []
    hearts = magical_sword_heart_range(flags, z1r)
    if not hearts:
        reasons.append(f"magical-sword hearts: the ZORA cap {flags.magical_sword_hearts_highest} is below "
                       f"the Z1R string's lowest requirement {hearts.start}")
    elif (sword := sword_hearts_conflict(flags, z1r)) is not None:
        reasons.append(sword)
    if (candles := extra_candles_conflict(flags, z1r)) is not None:
        reasons.append(candles)
    reasons.extend(owner_conflict for owner_conflict in (l4_sword_conflict(flags), bracelet_blocks_conflict(flags, z1r))
                   if owner_conflict is not None)
    return reasons


# ---------------------------------------------------------------------------
# The version-3 "?" values: their own stream, then the dependencies
# ---------------------------------------------------------------------------

QUESTION_MARK_STREAM = b"zora ZORA ? vals"      # 16 bytes at most (BLAKE2b's person)


def question_mark_draws(seed: int, z1r_canonical: str, zora_canonical: str) -> Iterator[int]:
    """The coins that decide the version-3 "?" values: derived only from the seed number and both
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
    """Each version-3 "?" decided for this seed by a fair coin, in field order. The resolved
    values are never shown to the page."""
    if flags.is_resolved:
        return flags
    coins = question_mark_draws(seed, z1r_canonical, zora_canonical)
    decided = {name: ThreeState.ON if next(coins) else ThreeState.OFF
               for name in OWNER_2_0_FIELDS if getattr(flags, name) is ThreeState.POSSIBLE}
    return replace(flags, **decided)  # type: ignore[arg-type]


def resolve_owner_dependencies(resolved: ZoraFlags, asked: ZoraFlags, resolved_z1r: Settings,
                               asked_z1r: Settings) -> tuple[ZoraFlags, Settings]:
    """The owner's 2.0 dependencies after both strings' "?" values are drawn (explicit conflicts
    were refused before): a "?" that comes up into a conflict resolves to off.
      - Add L4 Sword without Progressive Items: Add L4 Sword is off.
      - Extra Power Bracelet Blocks with B04 on: the side that was "?" is off (Bracelet Blocks
        when both were)."""
    if resolved.is_on("add_l4_sword") and not resolved.progressive_items:
        resolved = replace(resolved, add_l4_sword=ThreeState.OFF)
    if resolved.is_on("extra_power_bracelet_blocks") and resolved_z1r.is_on(TAKE_ANY_ROAD_CAVES):
        if asked.extra_power_bracelet_blocks is ThreeState.POSSIBLE:
            resolved = replace(resolved, extra_power_bracelet_blocks=ThreeState.OFF)
        else:
            assert asked_z1r.toggle(TAKE_ANY_ROAD_CAVES) is ThreeState.POSSIBLE
            resolved_z1r = resolved_z1r.updated(toggles={TAKE_ANY_ROAD_CAVES.id: ThreeState.OFF})
    return resolved, resolved_z1r


# The version-3 fields whose behaviour this build produces; any other one on or "?" is refused
# (FlagsRefused), never ignored.
PRODUCED_OWNER_FIELDS: frozenset[str] = frozenset(OWNER_2_0_FIELDS)


def unproduced_fields(flags: ZoraFlags) -> list[str]:
    return [name for name in OWNER_2_0_FIELDS
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


def level_encoding_text(z1r_canonical: str, zora_canonical: str) -> str:
    """The flag text of the level-encoding key (FP-TOURNEY-01's settings
    bytes, LevelEncodingKey.flag_string): the Z1R string alone while the
    ZORA string is at its default, else both, so the key covers both."""
    if zora_canonical == "":
        return z1r_canonical
    return f"{z1r_canonical}{KEY_SEPARATOR}{zora_canonical}"
