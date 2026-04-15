"""Request parsing and flag validation helpers for the ZORA API."""
from __future__ import annotations

import secrets
import sys
from pathlib import Path
from typing import Any

import yaml

# Ensure flags/ is importable regardless of working directory
_FLAGS_DIR = Path(__file__).parent.parent.parent / "flags"
if str(_FLAGS_DIR) not in sys.path:
    sys.path.insert(0, str(_FLAGS_DIR))

from flags_generated import (  # noqa: E402
    BASE64_ALPHABET,
    COSMETIC_FLAG_STRING_LENGTH,
    FLAG_STRING_LENGTH,
    CosmeticFlags as CosmeticFlags,
    Flags,
    _FLAG_DEFS,
    _ITEM_ENUM,
    compute_active_pool,
    decode_cosmetic_flags as decode_cosmetic_flags,
    decode_flags as decode_flags,
    resolve_random_flags as resolve_random_flags,
)

_FLAGS_YAML = _FLAGS_DIR / "flags.yaml"
_CONSTRAINTS: list[dict[str, Any]] = []


def _load_constraints() -> list[dict[str, Any]]:
    global _CONSTRAINTS
    if not _CONSTRAINTS:
        schema = yaml.safe_load(_FLAGS_YAML.read_text())
        _CONSTRAINTS = schema.get("constraints", [])
    return _CONSTRAINTS


# ---------------------------------------------------------------------------
# Flag string validation
# ---------------------------------------------------------------------------

def parse_flag_string(raw: str) -> tuple[str, list[str]]:
    """Validate and normalise a flag string.

    Returns (normalised_string, errors). On success errors is empty.
    Short strings are right-padded with '0'. Strings longer than
    FLAG_STRING_LENGTH or containing invalid characters are rejected.
    """
    if not isinstance(raw, str):
        return "", ["Flag string must be a string"]

    for ch in raw:
        if ch not in BASE64_ALPHABET:
            return "", [f"Flag string contains invalid character {ch!r} (valid: 0-9, A-Z, a-z, -, _)"]

    if len(raw) > FLAG_STRING_LENGTH:
        return "", [
            f"Flag string length {len(raw)} exceeds maximum {FLAG_STRING_LENGTH}"
        ]

    return raw.ljust(FLAG_STRING_LENGTH, "A"), []


def parse_cosmetic_flag_string(raw: str) -> tuple[str, list[str]]:
    """Validate and normalise a cosmetic flag string.

    Returns (normalised_string, errors). On success errors is empty.
    Short strings are right-padded with 'A' (vanilla defaults).
    Strings longer than COSMETIC_FLAG_STRING_LENGTH or containing invalid
    characters are rejected.
    """
    if not isinstance(raw, str):
        return "", ["Cosmetic flag string must be a string"]

    for ch in raw:
        if ch not in BASE64_ALPHABET:
            return "", [f"Cosmetic flag string contains invalid character {ch!r} (valid: 0-9, A-Z, a-z, -, _)"]

    if len(raw) > COSMETIC_FLAG_STRING_LENGTH:
        return "", [
            f"Cosmetic flag string length {len(raw)} exceeds maximum {COSMETIC_FLAG_STRING_LENGTH}"
        ]

    return raw.ljust(COSMETIC_FLAG_STRING_LENGTH, "A"), []


# ---------------------------------------------------------------------------
# Static flag validation — interprets constraints from flags.yaml
# ---------------------------------------------------------------------------

def _get_flag_value(flags: Flags, flag_id: str) -> int:
    """Return the raw integer value of a flag field."""
    return int(getattr(flags, flag_id, 0))


def _tristate_str(val: int) -> str:
    return {0: "off", 1: "on", 2: "random"}.get(val, "off")


def _current_str_for(flag_id: str, raw: int) -> str:
    """Return the string id for a flag value, handling all flag types."""
    flag_def = _FLAG_DEFS[flag_id]
    if flag_def["type"] == "item":
        return _item_id_for_value(raw)
    if flag_def["type"] == "enum":
        for entry in flag_def.get("values", []):
            if entry.get("index") == raw:
                return str(entry["id"])
        return str(flag_def["values"][0]["id"]) if flag_def.get("values") else ""
    return _tristate_str(raw)


_NOT_SHUFFLED_INDEX = next(
    (e["index"] for e in _ITEM_ENUM if e["id"] == "not_shuffled"), 31
)
_RANDOM_INDEX = next(
    (e["index"] for e in _ITEM_ENUM if e["id"] == "random"), 0
)


def _item_id_for_value(val: int) -> str:
    """Return the item id string for an item enum integer value."""
    for entry in _ITEM_ENUM:
        if entry["index"] == val:
            return str(entry["id"])
    return "random"


def _item_is_sentinel(val: int) -> bool:
    """Return True if the item value is random or not_shuffled (not a real item)."""
    return val in (_RANDOM_INDEX, _NOT_SHUFFLED_INDEX)


def _condition_matches(flags: Flags, condition: dict[str, Any]) -> bool:
    flag_id = condition["flag"]
    raw = _get_flag_value(flags, flag_id)
    current_str = _current_str_for(flag_id, raw)

    if "equals" in condition:
        return bool(current_str == condition["equals"])
    if "not_equals" in condition:
        return bool(current_str != condition["not_equals"])
    return False


def _check_heart_container_pool(flags: Flags) -> bool:
    """Return True if heart container is validly available given current flags."""
    sdh = _get_flag_value(flags, "shuffle_dungeon_hearts")
    if sdh != 0:  # on or random — hearts available from dungeons
        return True

    hc_index = next(e["index"] for e in _ITEM_ENUM if e["id"] == "heart_container")
    coast_val = _get_flag_value(flags, "coast_item")
    ws_val = _get_flag_value(flags, "white_sword_item")
    armos_val = _get_flag_value(flags, "armos_item")

    # Coast item is shuffled when not NOT_SHUFFLED — if it's RANDOM or HC, it contributes one HC.
    coast_shuffled = coast_val != _NOT_SHUFFLED_INDEX
    coast_provides_hc = coast_shuffled and coast_val != hc_index  # RANDOM means the vanilla HC enters the pool
    coast_forced_to_hc = coast_val == hc_index

    # Without dungeon hearts the only available HC is the vanilla coast item (when shuffled).
    # Valid iff coast is shuffled and exactly one location forces HC.
    forced_hc_locations = sum(1 for v in (coast_val, ws_val, armos_val) if v == hc_index)

    # HC is in the pool if: coast is shuffled as RANDOM (vanilla HC enters pool)
    # OR exactly one location is forced to HC (that HC comes from the vanilla coast).
    if coast_provides_hc:
        # Coast is shuffled but not forced to HC — vanilla coast HC enters pool freely
        return True
    if coast_forced_to_hc:
        # Coast is forced to HC — that's the one HC, no duplicates allowed
        return forced_hc_locations == 1
    # Coast not shuffled, no dungeon hearts — no HCs in pool
    return False


def validate_flags_static(flags: Flags) -> list[str]:
    """Run all static constraint checks from flags.yaml.

    Returns a list of error message strings. Empty list means valid.
    """
    errors: list[str] = []
    pool = compute_active_pool(flags)

    for constraint in _load_constraints():
        when = constraint.get("when", [])
        if not all(_condition_matches(flags, cond) for cond in when):
            continue

        for action in constraint.get("then", []):
            rule = action.get("rule")
            error_msg = action.get("error", "Validation error").strip()

            if rule is None and "flag" in action:
                # must_be / must_not_be / must_be_one_of
                flag_id = action["flag"]
                raw = _get_flag_value(flags, flag_id)
                current_str = _current_str_for(flag_id, raw)
                if "must_be" in action and current_str != action["must_be"]:
                    errors.append(error_msg)
                elif "must_not_be" in action and current_str == action["must_not_be"]:
                    errors.append(error_msg)
                elif "must_be_one_of" in action and current_str not in action["must_be_one_of"]:
                    errors.append(error_msg)

            elif rule == "item_in_pool":
                flag_id = action["flag"]
                raw = _get_flag_value(flags, flag_id)
                if not _item_is_sentinel(raw):
                    item_id = _item_id_for_value(raw)
                    if item_id not in pool:
                        errors.append(error_msg)

            elif rule == "no_duplicate":
                flag_id = action["flag"]
                raw = _get_flag_value(flags, flag_id)
                if not _item_is_sentinel(raw):
                    for other_id in action.get("among", []):
                        other_raw = _get_flag_value(flags, other_id)
                        if not _item_is_sentinel(other_raw) and other_raw == raw:
                            errors.append(error_msg)
                            break

            elif rule == "heart_container_pool_check":
                if not _check_heart_container_pool(flags):
                    errors.append(error_msg)

    return errors


# ---------------------------------------------------------------------------
# Seed parsing
# ---------------------------------------------------------------------------

_UINT64_MAX = (2 ** 64) - 1


def parse_seed(raw: Any) -> tuple[int | None, str | None]:
    """Parse and validate a seed value from a request.

    Accepts int or string. Returns (seed_int, None) on success,
    (None, error_message) on failure. If raw is None, generates a random seed.
    """
    if raw is None:
        return secrets.randbelow(2 ** 64), None

    try:
        value = int(raw)
    except (ValueError, TypeError):
        return None, "Seed must be a 64-bit unsigned integer (0 to 18446744073709551615)"

    if not (0 <= value <= _UINT64_MAX):
        return None, "Seed must be a 64-bit unsigned integer (0 to 18446744073709551615)"

    return value, None
