"""
Tests for the behavior patch system.

test_behavior_patch_old_bytes: verifies that RomEdit.old_bytes matches the
actual bytes in a verified base ROM (skipped if ROM not available or wrong version).

test_no_behavior_patch_conflicts: verifies no two patches write to the same
offset, regardless of config (runs unconditionally).
"""
import hashlib
from collections.abc import Generator
from pathlib import Path

import pytest

from zora.patches import _REGISTRY
from zora.patches.base import BehaviorPatch, RomEdit, VariableBehaviorPatch

KNOWN_ROM_MD5 = "f4095791987351be68674a9355b266bc"
ROM_PATH = Path("rom_data/base.nes")


@pytest.fixture(scope="session")
def verified_rom() -> bytes | None:
    if not ROM_PATH.exists():
        return None
    rom = ROM_PATH.read_bytes()
    if hashlib.md5(rom).hexdigest() != KNOWN_ROM_MD5:
        return None
    return rom


def _all_edits(bp: BehaviorPatch) -> Generator[RomEdit, None, None]:
    """Yield all RomEdits for a patch across all config variants."""
    if isinstance(bp, VariableBehaviorPatch):
        yield from bp.test_only_get_all_variant_edits()
    else:
        yield from bp.get_edits()


def test_behavior_patch_old_bytes(verified_rom):
    if verified_rom is None:
        pytest.skip("Verified base ROM not available")

    failures = []
    for bp in _REGISTRY:
        for edit in _all_edits(bp):
            if edit.old_bytes is None:
                continue
            actual = verified_rom[edit.offset:edit.offset + len(edit.old_bytes)]
            if actual != edit.old_bytes:
                failures.append(
                    f"{bp.name} @ {edit.offset:#x}: "
                    f"expected {edit.old_bytes.hex(' ')}, "
                    f"got {actual.hex(' ')}"
                )

    assert not failures, "Behavior patch old_bytes mismatches:\n" + "\n".join(failures)


def test_no_behavior_patch_conflicts() -> None:
    """Ensure no two patches write to the same offset for any single config variant.

    Non-variable patches are always co-active, so they are checked together.
    Variable patches are mutually exclusive per mode — each variant's edits are
    checked against the non-variable baseline, not against other variants of the
    same patch.
    """
    conflicts = []

    # Build baseline from all non-variable patches (always co-active).
    baseline: dict[int, str] = {}
    for bp in _REGISTRY:
        if isinstance(bp, VariableBehaviorPatch):
            continue
        for edit in bp.get_edits():
            if edit.offset in baseline:
                conflicts.append(f"{edit.offset:#x}: {baseline[edit.offset]} and {bp.name}")
            else:
                baseline[edit.offset] = bp.name

    # Check each variable patch variant against the baseline and each other variable patch.
    for bp in _REGISTRY:
        if not isinstance(bp, VariableBehaviorPatch):
            continue
        for edit in bp.test_only_get_all_variant_edits():
            if edit.offset in baseline:
                conflicts.append(f"{edit.offset:#x}: {baseline[edit.offset]} and {bp.name}")

    assert not conflicts, "Patch conflicts:\n" + "\n".join(conflicts)
