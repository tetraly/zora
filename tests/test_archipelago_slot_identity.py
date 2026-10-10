"""Archipelago Phase 4c, item 1: the slot identity in the ROM (zora/rom/slot_identity.py;
docs/archipelago.md "Interface", docs/rom-map.md "Archipelago slot identity").
  - finish(..., ap_name) differs from the same assignment without it only in the 32 reserved
    bytes and the seed's code (which hashes the finished ROM, so each slot's code differs);
  - rom_identity reads back the marker's version and the name, and None for a ZORA-mode ROM or
    an External-mode ROM without a name; a name the record cannot hold is refused;
  - the recipe carries apName, and its round trip still gives the same ROM byte for byte.
Its range is clear of z1rr-coop's blocks and the level encoding's sites: test_coop_reserved.py."""
import json
from functools import cache

import pytest

from tests.archipelago_cases import FLAG_CASES
from tests.test_archipelago_recipe import accepted_assignment
from zora import archipelago
from zora.generate.pipeline import finish as zora_mode_finish
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.code_patches import SEED_CODE_ADDRESS, SEED_CODE_LENGTH
from zora.rom.slot_identity import (
    MARKER,
    MAX_NAME_LENGTH,
    SLOT_IDENTITY_ADDRESS,
    SLOT_IDENTITY_SIZE,
)

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")

SLOT = range(SLOT_IDENTITY_ADDRESS, SLOT_IDENTITY_ADDRESS + SLOT_IDENTITY_SIZE)
SEED_CODE = range(SEED_CODE_ADDRESS, SEED_CODE_ADDRESS + SEED_CODE_LENGTH)
NAMES = (b"Link", "Zelda-été".encode(), b"X" * MAX_NAME_LENGTH)


@cache
def built(case: str, seed: int) -> archipelago.BuildResult:
    return archipelago.build_from_strings(*FLAG_CASES[case], seed, remember_repo_base_rom())


@cache
def assignment(case: str, seed: int) -> tuple[dict[str, str | archipelago.Foreign], tuple[str, ...]]:
    chosen, received = accepted_assignment(built(case, seed), seed)
    return chosen, tuple(received)


def finished(case: str, seed: int, ap_name: bytes | None) -> bytes:
    chosen, received = assignment(case, seed)
    return archipelago.finish(built(case, seed), chosen, received, ap_name=ap_name)


@pytest.mark.parametrize("name", NAMES, ids=["short", "utf-8", "longest"])
@pytest.mark.parametrize("case", ["baseline", "every ZORA flag on"])
def test_only_the_reserved_bytes_and_the_seed_code_differ(case: str, name: bytes) -> None:
    plain, named = finished(case, 1, None), finished(case, 1, name)
    changed = {offset for offset, (old, new) in enumerate(zip(plain, named, strict=True)) if old != new}
    assert changed & set(SLOT)
    assert changed <= set(SLOT) | set(SEED_CODE)
    assert archipelago.rom_identity(named) == archipelago.RomIdentity((1, 1), name)
    assert named[SLOT_IDENTITY_ADDRESS:SLOT_IDENTITY_ADDRESS + len(MARKER)] == MARKER


def test_no_identity_without_a_name_or_in_zora_mode() -> None:
    base = remember_repo_base_rom()
    assert archipelago.rom_identity(finished("baseline", 1, None)) is None
    zora_mode = zora_mode_finish(built("baseline", 1).state, base)
    assert archipelago.rom_identity(zora_mode) is None
    assert zora_mode[SLOT_IDENTITY_ADDRESS:SLOT_IDENTITY_ADDRESS + SLOT_IDENTITY_SIZE] == \
        base[SLOT_IDENTITY_ADDRESS:SLOT_IDENTITY_ADDRESS + SLOT_IDENTITY_SIZE]


@pytest.mark.parametrize("name", [b"", b"X" * (MAX_NAME_LENGTH + 1), b"Li\x00nk"], ids=["empty", "long", "zero"])
def test_a_name_the_record_cannot_hold_is_refused(name: bytes) -> None:
    chosen, received = assignment("baseline", 1)
    with pytest.raises(archipelago.SlotNameRefused):
        archipelago.finish(built("baseline", 1), chosen, received, ap_name=name)
    with pytest.raises(archipelago.SlotNameRefused):
        archipelago.recipe(built("baseline", 1), chosen, received, ap_name=name)


@pytest.mark.parametrize("seed", [1, 2])
@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_the_recipe_carries_the_name_and_rebuilds_the_rom(case: str, seed: int) -> None:
    chosen, received = assignment(case, seed)
    name = NAMES[seed % len(NAMES)]
    settings = {"music": "off"}
    rom = archipelago.finish(built(case, seed), chosen, received, settings, ap_name=name)
    data = json.loads(json.dumps(archipelago.recipe(built(case, seed), chosen, received, settings, ap_name=name)))
    assert data["formatVersion"] == "1.1" and bytes.fromhex(data["apName"]) == name
    assert archipelago.rom_from_recipe(data, remember_repo_base_rom()) == rom
    without = json.loads(json.dumps(archipelago.recipe(built(case, seed), chosen, received, settings)))
    assert without["apName"] is None
    assert archipelago.rom_identity(archipelago.rom_from_recipe(without, remember_repo_base_rom())) is None
