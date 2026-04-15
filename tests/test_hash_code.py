"""Tests for hash code generation."""
from zora.hash_code import CodeItem, apply_hash_code, hash_code_display_names
from zora.serializer import Patch


def test_hash_is_four_bytes():
    patch = Patch()
    patch.add(0x1000, b"\x01\x02\x03")
    result = apply_hash_code(patch)
    assert len(result) == 4


def test_hash_values_are_valid_item_codes():
    patch = Patch()
    patch.add(0x1000, b"\xAB\xCD\xEF")
    result = apply_hash_code(patch)
    # Every value must be a known CodeItem
    assert all(b in CodeItem._value2member_map_ for b in result)
    assert 0x02 not in result  # duplicate SWORD slot, not in enum
    assert 0x07 not in result  # duplicate CANDLE slot, not in enum
    assert 0x17 not in result  # duplicate LETTER slot (Map), not in enum


def test_hash_is_deterministic():
    patch1 = Patch()
    patch1.add(0x1000, b"\x01\x02\x03")
    patch2 = Patch()
    patch2.add(0x1000, b"\x01\x02\x03")
    assert apply_hash_code(patch1) == apply_hash_code(patch2)


def test_hash_changes_with_patch_content():
    patch1 = Patch()
    patch1.add(0x1000, b"\x01\x02\x03")
    patch2 = Patch()
    patch2.add(0x1000, b"\x04\x05\x06")
    h1 = apply_hash_code(patch1)
    h2 = apply_hash_code(patch2)
    assert h1 != h2


def test_display_names_returns_four_strings():
    patch = Patch()
    patch.add(0x1000, b"\x00")
    hash_bytes = apply_hash_code(patch)
    names = hash_code_display_names(hash_bytes)
    assert len(names) == 4
    assert all(isinstance(n, str) for n in names)


def test_all_code_items_have_display_names():
    for item in CodeItem:
        name = item.display_name()
        assert isinstance(name, str) and len(name) > 0
