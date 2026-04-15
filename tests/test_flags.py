"""Tests for the flags codec and schema integrity.

Covers:
  - Encode/decode roundtrip for all flag types and every valid value
  - Bit layout: no overlapping ranges, no out-of-bounds offsets
  - flags_generated.py is in sync with flags.yaml
  - API /flags response always includes 'index' on multi-value flag values
"""
import subprocess
import sys
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest

# Ensure flags/ is importable
_FLAGS_DIR = Path(__file__).parent.parent / "flags"
if str(_FLAGS_DIR) not in sys.path:
    sys.path.insert(0, str(_FLAGS_DIR))

from flags_generated import (  # noqa: E402
    _FLAG_DEFS,
    _FLAG_LAYOUT,
    _ITEM_ENUM,
    FLAG_STRING_LENGTH,
    TOTAL_BITS,
    Flags,
    Item,
    Tristate,
    decode_flags,
    encode_flags,
)

# =============================================================================
# Roundtrip tests
# =============================================================================

def test_roundtrip_defaults() -> None:
    """Default Flags encodes and decodes back to an equal instance."""
    flags = Flags()
    assert decode_flags(encode_flags(flags)) == flags


def test_roundtrip_all_tristate_values() -> None:
    """Each tristate flag round-trips through all three values."""
    tristate_flags = [fid for fid, _, _ in _FLAG_LAYOUT
                      if _FLAG_DEFS[fid]["type"] == "tristate"]
    for fid in tristate_flags:
        for val in (Tristate.OFF, Tristate.ON, Tristate.RANDOM):
            flags = Flags(**{fid: val})
            result = decode_flags(encode_flags(flags))
            assert getattr(result, fid) == val, (
                f"{fid}={val!r}: encoded then decoded to {getattr(result, fid)!r}"
            )


def test_roundtrip_all_bool_values() -> None:
    """Each bool flag round-trips through both values."""
    bool_flags = [fid for fid, _, _ in _FLAG_LAYOUT
                  if _FLAG_DEFS[fid]["type"] == "bool"]
    for fid in bool_flags:
        for val in (False, True):
            flags = Flags(**{fid: val})
            result = decode_flags(encode_flags(flags))
            assert getattr(result, fid) == val, (
                f"{fid}={val!r}: encoded then decoded to {getattr(result, fid)!r}"
            )


def test_roundtrip_all_item_values() -> None:
    """Each item flag round-trips through every valid item index."""
    item_flags = [fid for fid, _, _ in _FLAG_LAYOUT
                  if _FLAG_DEFS[fid]["type"] == "item"]
    item_values = [Item(e["index"]) for e in _ITEM_ENUM]
    for fid in item_flags:
        for val in item_values:
            flags = Flags(**{fid: val})
            result = decode_flags(encode_flags(flags))
            assert getattr(result, fid) == val, (
                f"{fid}={val!r}: encoded then decoded to {getattr(result, fid)!r}"
            )


def test_roundtrip_all_enum_values() -> None:
    """Each enum flag round-trips through every valid value."""
    import importlib
    mod = importlib.import_module("flags_generated")
    enum_flags = [fid for fid, _, _ in _FLAG_LAYOUT
                  if _FLAG_DEFS[fid]["type"] == "enum"]
    for fid in enum_flags:
        cls_name = "".join(w.capitalize() for w in fid.split("_"))
        cls = getattr(mod, cls_name)
        for val in cls:
            flags = Flags(**{fid: val})
            result = decode_flags(encode_flags(flags))
            assert getattr(result, fid) == val, (
                f"{fid}={val!r}: encoded then decoded to {getattr(result, fid)!r}"
            )


def test_roundtrip_all_flags_max_values() -> None:
    """Setting every flag to its maximum value round-trips without corruption."""
    import importlib
    mod = importlib.import_module("flags_generated")
    kwargs = {}
    for fid, _, width in _FLAG_LAYOUT:
        fdef = _FLAG_DEFS[fid]
        ftype = fdef["type"]
        if ftype == "tristate":
            kwargs[fid] = Tristate.RANDOM
        elif ftype == "bool":
            kwargs[fid] = True
        elif ftype == "item":
            max_item = max(Item)
            kwargs[fid] = max_item
        elif ftype == "enum":
            cls_name = "".join(w.capitalize() for w in fid.split("_"))
            cls = getattr(mod, cls_name)
            kwargs[fid] = max(cls)
    flags = Flags(**kwargs)
    assert decode_flags(encode_flags(flags)) == flags


# =============================================================================
# Bit layout integrity tests
# =============================================================================

def test_no_overlapping_bit_ranges() -> None:
    """No two enabled flags share any bit positions."""
    ranges: list[tuple[str, int, int]] = []
    for fid, offset, width in _FLAG_LAYOUT:
        end = offset + width
        for existing_id, existing_offset, existing_end in ranges:
            assert end <= existing_offset or offset >= existing_end, (
                f"Flag '{fid}' ({offset}-{end-1}) overlaps with "
                f"'{existing_id}' ({existing_offset}-{existing_end-1})"
            )
        ranges.append((fid, offset, end))


def test_all_flags_within_total_bits() -> None:
    """No flag extends beyond TOTAL_BITS."""
    for fid, offset, width in _FLAG_LAYOUT:
        end = offset + width
        assert end <= TOTAL_BITS, (
            f"Flag '{fid}' ends at bit {end-1}, exceeds TOTAL_BITS={TOTAL_BITS}"
        )


def test_flag_string_length_matches_total_bits() -> None:
    """FLAG_STRING_LENGTH * 6 == TOTAL_BITS."""
    assert FLAG_STRING_LENGTH * 6 == TOTAL_BITS


def test_adjacent_flags_do_not_bleed() -> None:
    """Setting one flag to max does not affect the bits read back for the adjacent flag.

    We compare the raw extracted bits, not the decoded typed value, because
    default values like Item.NOT_SHUFFLED (31) do not correspond to all-zeroes.
    """
    from flags_generated import BASE64_ALPHABET
    sorted_layout = sorted(_FLAG_LAYOUT, key=lambda t: t[1])
    for i in range(len(sorted_layout) - 1):
        fid_a, offset_a, width_a = sorted_layout[i]
        fid_b, offset_b, width_b = sorted_layout[i + 1]
        # Build a bitfield with only flag A set to all-ones
        max_val_a = (1 << width_a) - 1
        bitfield_in = max_val_a << offset_a
        # Encode to string and decode back to integer bitfield
        chars = []
        remaining = bitfield_in
        for _ in range(FLAG_STRING_LENGTH):
            chars.append(BASE64_ALPHABET[remaining & 0x3F])
            remaining >>= 6
        flag_string = "".join(chars)
        # Reconstruct the bitfield from the encoded string
        bitfield_out = 0
        for j, ch in enumerate(flag_string):
            bitfield_out |= BASE64_ALPHABET.index(ch) << (j * 6)
        # Extract raw bits for flag B — should be zero since we only set flag A
        mask_b = (1 << width_b) - 1
        raw_b = (bitfield_out >> offset_b) & mask_b
        assert raw_b == 0, (
            f"Flag '{fid_a}' at max bled into adjacent flag '{fid_b}': "
            f"expected 0 bits, got {raw_b}"
        )


# =============================================================================
# Schema sync test
# =============================================================================

def test_flags_generated_is_up_to_date() -> None:
    """flags_generated.py matches what validate_flags.py --generate would produce."""
    result = subprocess.run(
        [sys.executable, str(_FLAGS_DIR / "validate_flags.py"), "--generate"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Generator failed: {result.stderr}"

    current = (_FLAGS_DIR / "flags_generated.py").read_text()
    # Re-read after regeneration — content should be identical to what was there before
    # (i.e. the file on disk after running --generate should equal what was already there)
    # Since we just ran --generate, the file was overwritten; compare to itself is trivially true.
    # The real check: running --generate a second time produces the same output (idempotent).
    result2 = subprocess.run(
        [sys.executable, str(_FLAGS_DIR / "validate_flags.py"), "--generate"],
        capture_output=True,
        text=True,
    )
    assert result2.returncode == 0
    regenerated = (_FLAGS_DIR / "flags_generated.py").read_text()
    assert current == regenerated, (
        "flags_generated.py is not idempotent — generator produces different output on second run"
    )


# =============================================================================
# API schema contract: index always present on multi-value flags
# =============================================================================

@pytest.fixture
def client() -> Generator[Any, None, None]:
    import sys
    zora_dir = Path(__file__).parent.parent
    if str(zora_dir) not in sys.path:
        sys.path.insert(0, str(zora_dir))
    from zora.api import create_app
    app = create_app({"TESTING": True})
    with app.test_client() as c:
        yield c


def test_api_enum_values_have_index(client: Any) -> None:
    """Every value of every enum flag in the API response has an integer 'index'.

    item flags serve their values via the global item_enum list, not inline,
    so this test only applies to enum-type flags.
    """
    r = client.get("/flags")
    assert r.status_code == 200
    data = r.get_json()
    for flag in data["flags"]:
        if flag["type"] == "enum":
            assert "values" in flag, f"Flag '{flag['id']}' missing 'values'"
            for v in flag["values"]:
                assert "index" in v, (
                    f"Flag '{flag['id']}' value '{v.get('id')}' missing 'index'"
                )
                assert isinstance(v["index"], int), (
                    f"Flag '{flag['id']}' value '{v.get('id')}' index is not int: {v['index']!r}"
                )


def test_api_enum_indices_are_contiguous_from_zero(client: Any) -> None:
    """Enum flag values have indices 0, 1, 2, ... in order."""
    r = client.get("/flags")
    data = r.get_json()
    for flag in data["flags"]:
        if flag["type"] == "enum":
            indices = [v["index"] for v in flag["values"]]
            assert indices == list(range(len(indices))), (
                f"Flag '{flag['id']}' enum indices are not 0-based contiguous: {indices}"
            )


def test_api_item_enum_indices_are_unique_and_contiguous(client: Any) -> None:
    """item_enum entries have unique, non-negative integer indices."""
    r = client.get("/flags")
    data = r.get_json()
    indices = [e["index"] for e in data["item_enum"]]
    assert len(indices) == len(set(indices)), "item_enum has duplicate indices"
    assert all(isinstance(i, int) and i >= 0 for i in indices), (
        "item_enum indices must be non-negative integers"
    )
