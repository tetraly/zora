"""The flag string's base-63 encoding (FL-ENC-01 to FL-ENC-03): decode, encode, canonicalize."""
from __future__ import annotations

from zora.flags.fields import OPTION_FIELDS, TOGGLE_FIELDS, Settings, ThreeState

# ---------------------------------------------------------------------------
# FL-ENC-01: the base-63 alphabet
# ---------------------------------------------------------------------------

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!"
RADIX = len(ALPHABET)
DIGIT_VALUE = {digit: value for value, digit in enumerate(ALPHABET)}
THREE_STATE_SLOTS = 3


class FlagStringError(ValueError):
    """A flag string that FL-ENC-03 rejects: empty, or a character outside the alphabet."""


# ---------------------------------------------------------------------------
# FL-ENC-01 to FL-ENC-03: decode and encode
# ---------------------------------------------------------------------------

def _parse_base63(flag_string: str) -> int:
    """FL-ENC-01 and FL-ENC-03 rules 1 and 2: most significant digit first; leading `0` changes nothing."""
    if not flag_string:
        raise FlagStringError("empty string")
    number = 0
    for character in flag_string:
        if character not in DIGIT_VALUE:
            raise FlagStringError(f"invalid character {character!r}")
        number = number * RADIX + DIGIT_VALUE[character]
    return number


def _format_base63(number: int) -> str:
    """FL-ENC-03 encoding: no leading `0`; the number zero is written `0`."""
    digits = []
    while number:
        number, digit = divmod(number, RADIX)
        digits.append(ALPHABET[digit])
    return "".join(reversed(digits)) or ALPHABET[0]


def decode(flag_string: str) -> Settings:
    """FL-ENC-02: C01 is the least significant field and B91 the most significant.

    FL-ENC-03: a slot value at or above the field's Count decodes as its last option (rule 3) and
    whatever is left of the number after B91 is ignored (rule 4).
    """
    number = _parse_base63(flag_string)
    options: dict[str, int] = {}
    for option in OPTION_FIELDS:
        number, slot = divmod(number, option.slots)
        options[option.id] = min(slot, option.last_index)
    toggles: dict[str, ThreeState] = {}
    for toggle in TOGGLE_FIELDS:
        number, state = divmod(number, THREE_STATE_SLOTS)
        toggles[toggle.id] = ThreeState(state)
    return Settings(options, toggles)


def encode(settings: Settings) -> str:
    """FL-ENC-02 and FL-ENC-03: the canonical string of the settings (clamped indices, no left-over part)."""
    number = 0
    for toggle in reversed(TOGGLE_FIELDS):
        number = number * THREE_STATE_SLOTS + settings.toggle(toggle)
    for option in reversed(OPTION_FIELDS):
        number = number * option.slots + settings.option(option)
    return _format_base63(number)


def canonicalize(flag_string: str) -> str:
    """The canonical spelling of a string (FL-ENC-03; FL-SEED-01 lets the rebuild use it)."""
    return encode(decode(flag_string))


def distinct_string_count() -> int:
    """FL-ENC-04 Check: the product of the 27 slot counts times 3 to the power 91."""
    product: int = THREE_STATE_SLOTS ** len(TOGGLE_FIELDS)
    for option in OPTION_FIELDS:
        product *= option.slots
    return product
