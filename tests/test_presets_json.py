"""presets.json, the presets a race bot (TTPBot) can roll (docs/flags-api.md "Presets"): what
scripts/flags_api.py makes from presets.PRESET_LIST is current, its revision was raised for its presets, and
it passes every rule the bot checks before it uses the file (any failure and the bot uses none of it). The
validator itself is checked against the bot's test vectors: tests/fixtures/flagsets-contract.json (the Z1R
registry's contract, the same format without the zora key; TTPBot's main branch, copied unchanged) and
tests/fixtures/zora-presets-contract.json (its ZORA category's) when present."""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from zora.flags import codec, zora_flags
from zora.flags.presets import ASNB_FLAGS, ASNB_ZORA_FLAGS, PRESET_LIST

REPO = Path(__file__).resolve().parent.parent
GENERATOR = REPO / "scripts" / "flags_api.py"
PRESETS_FILE = REPO / "docs" / "flags-api" / "presets.json"
FIXTURES = REPO / "tests" / "fixtures"
Z1R_CONTRACT = FIXTURES / "flagsets-contract.json"
ZORA_CONTRACT = FIXTURES / "zora-presets-contract.json"

pytestmark = pytest.mark.skipif(not (PRESETS_FILE.exists() and GENERATOR.exists()),
                                reason="presets.json is not part of this tree")


def _generator() -> Any:
    spec = importlib.util.spec_from_file_location("flags_api", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("flags_api", module)
    spec.loader.exec_module(module)
    return module


API: Any = _generator() if GENERATOR.exists() else None


def _contract(path: Path) -> dict[str, Any]:
    contract: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return contract


# --- the canonical list -------------------------------------------------------------------------------------

def test_every_preset_decodes_with_the_real_decoders() -> None:
    for preset in PRESET_LIST:
        assert codec.encode(codec.decode(preset.flags)) == codec.canonicalize(preset.flags), preset.name
        if preset.zora:
            assert zora_flags.encode(zora_flags.decode(preset.zora)) == preset.zora, preset.name


def test_every_shortcut_and_name_is_its_own() -> None:
    """Each key is lowercase letters, digits and hyphens (consternation-noenc), and no key or name reads as
    another preset's."""
    owner: dict[str, str] = {}
    for preset in PRESET_LIST:
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", preset.key), preset.key
        for text in (preset.key, preset.name):
            assert owner.setdefault(API.reduced(text), preset.name) == preset.name, text


def test_all_swords_no_boards_is_listed_once() -> None:
    assert [(p.key, p.flags, p.zora) for p in PRESET_LIST if p.name == "All Swords No Boards"] == [
        ("asnb", ASNB_FLAGS, ASNB_ZORA_FLAGS)]


# --- the generated file -------------------------------------------------------------------------------------

def test_presets_json_is_current_and_its_revision_was_raised() -> None:
    """Fails until python3 scripts/flags_api.py has written it, raising the revision for changed presets."""
    assert API.presets_check() == []


def test_presets_json_passes_every_rule_of_the_bot() -> None:
    snapshot = json.loads(PRESETS_FILE.read_text(encoding="utf-8"))
    reserved = API.RESERVED_SHORTCUTS | set(_contract(Z1R_CONTRACT)["reservedCommands"])
    assert API.validate_presets(snapshot, reserved) == []
    assert snapshot["schemaVersion"] == 1 and isinstance(snapshot["revision"], int)
    datetime.fromisoformat(snapshot["updatedAt"])


def test_presets_json_holds_every_preset_with_a_zora_string_then_the_z1r_ones() -> None:
    snapshot = json.loads(PRESETS_FILE.read_text(encoding="utf-8"))
    assert [(f["name"], f["shortcuts"], [(s["flags"], s["zora"], s["isLatest"]) for s in f["strings"]])
            for f in snapshot["flagsets"]] == [
        (p.name, [p.key], [(p.flags, p.zora, True)])
        for p in [*(p for p in PRESET_LIST if p.zora), *(p for p in PRESET_LIST if not p.zora and not p.hidden)]]
    assert {f["shortcuts"][0] for f in snapshot["flagsets"]} >= {"asnb", "zte1", "zte2", "zte3", "zte4", "zte5",
                                                                  "consternationplus"}
    assert "_" not in PRESETS_FILE.read_text(encoding="utf-8")       # ! is canonical, never _


def test_the_revision_rises_with_the_presets_and_only_then() -> None:
    flagsets = API.presets_flagsets()
    now = datetime(2026, 11, 17, 12, 0, 0, 123456, tzinfo=UTC)
    first = API.next_presets_revision(flagsets, None, now)
    assert (first["revision"], first["updatedAt"]) == (1, "2026-11-17T12:00:00Z")
    assert API.next_presets_revision(flagsets, first, datetime(2027, 1, 1, tzinfo=UTC)) == first
    changed = [*flagsets, {**flagsets[0], "name": "Another"}]
    second = API.next_presets_revision(changed, first, now)
    assert second["revision"] == 2 and second["sha256"] != first["sha256"]


def test_a_publish_never_takes_the_bot_back() -> None:
    def text(revision: int, name: str = "A") -> str:
        return json.dumps({"revision": revision, "flagsets": [{"name": name}]})
    assert API.presets_against(text(1), text(2)) == "write"
    assert API.presets_against(text(2), text(2)) == "keep"
    assert API.presets_against(text(3), text(2)) == "keep"
    with pytest.raises(ValueError, match="already published with other presets"):
        API.presets_against(text(2), text(2, "B"))


# --- the validator against the bot's own test vectors ---------------------------------------------------------

def _vectors(path: Path, kind: str) -> list[Any]:
    if not path.exists():
        return [pytest.param(None, id=f"{path.name} missing", marks=pytest.mark.skip(reason=f"no {path.name}"))]
    return [pytest.param(case, id=case["why"]) for case in _contract(path)[kind]]


@pytest.mark.parametrize("case", _vectors(Z1R_CONTRACT, "valid"))
def test_the_z1r_registry_contracts_valid_files_pass(case: dict[str, Any]) -> None:
    reserved = _contract(Z1R_CONTRACT)["reservedCommands"]
    assert API.validate_presets(case["snapshot"], reserved, zora_required=False) == []


@pytest.mark.parametrize("case", _vectors(Z1R_CONTRACT, "invalid"))
def test_the_z1r_registry_contracts_invalid_files_fail(case: dict[str, Any]) -> None:
    reserved = _contract(Z1R_CONTRACT)["reservedCommands"]
    assert API.validate_presets(case["snapshot"], reserved, zora_required=False) != []


@pytest.mark.parametrize("case", _vectors(ZORA_CONTRACT, "valid"))
def test_the_zora_contracts_valid_files_pass(case: dict[str, Any]) -> None:
    reserved = _contract(ZORA_CONTRACT).get("reservedCommands", API.RESERVED_SHORTCUTS)
    assert API.validate_presets(case["snapshot"], reserved) == []


@pytest.mark.parametrize("case", _vectors(ZORA_CONTRACT, "invalid"))
def test_the_zora_contracts_invalid_files_fail(case: dict[str, Any]) -> None:
    reserved = _contract(ZORA_CONTRACT).get("reservedCommands", API.RESERVED_SHORTCUTS)
    assert API.validate_presets(case["snapshot"], reserved) != []


# Revision 2 (2026-11-21): the seven ZORA presets as revision 1 had them, then ten of a Z1R string alone, in this
# order, each with zora "". Written out so a change to the canonical list cannot move the bot's file unseen.
REVISION_2_FLAGSETS = [
    ("asnb", "8hq4BeR1JXo7yjOOHjbxryVQW!UJ3A", "4.T9Jvg"),
    ("zte1", "143oNtDD4PAvB!U8nSk4yS8L09lgT10vRVe7sx", "10.J2EGOED"),
    ("zte2", "143oNtDD4PAvB!U8nSk4yS8L09lgT10vRVe7sx", "10.J2EkcYg"),
    ("zte3", "143oNtDD4PAvB!U8nSk4m!DgIQ6oraWI4Me7sx", "10.JpkCdvd"),
    ("zte4", "143oNtDD4PAvB!U8nSk4mxFW0br2w5YUspe7sx", "10.JpaUYAv"),
    ("zte5", "143oNtDD4PAvB!U8nSk4mxFW0br2w5YUspe7sx", "13.7Zg4ZxiL"),
    ("consternationplus", "oIbnPfPb01Hll3D29Bc2!etrojQOSjJQZUULH", "18.1DzN7gO9LZ4p"),
    ("consternation", "oIbnPfPb01Hll3D29Bc2!etrojQOSjJQZUJ3A", ""),
    ("remastered", "oIbnPfPb01Hll3D295IGDxxjR4UwfEok8P4MD", ""),
    ("hopla", "oIbnRjuMUKqwdnOXzOMO7PuDtwAvU3boJnaXW", ""),
    ("consternation-noenc", "8hq4BeR1JXo89BJ2!TFpTP02u8UJ3A", ""),
    ("vanilla", "CEERPCkLslB6BApr1Him1SiR28Y", ""),
    ("ohk0hpla", "oIbnRjuQKp1DXiYCys9LwvSpzqZbXk1pRmZzr", ""),
    ("mufflerug", "2487lt0moGMFLRug1ofQdxPuUBWnJVSsi7d202I", ""),
    ("pick5", "p8GIOeYEAonHy5131VdG6b94Ts3EMMvBaQoWR", ""),
    ("uphill", "143oNtDD4Pw3Yw6SRryTCXlqTsRz2fxg4s4pJW", ""),
    ("sglive2026", "12TDBKH6mxLfnSz4T7ME4bcIaaUe9sE7UVmj7RA", ""),
]


def test_presets_json_has_the_seventeen_flagsets_of_revision_2() -> None:
    snapshot = json.loads(PRESETS_FILE.read_text(encoding="utf-8"))
    assert snapshot["schemaVersion"] == 1 and snapshot["revision"] >= 2
    assert len(snapshot["flagsets"]) == 17
    assert [(f["shortcuts"], [(s["flags"], s["zora"], s["isLatest"]) for s in f["strings"]], f["description"])
            for f in snapshot["flagsets"]] == [
        ([shortcut], [(flags, zora, True)], None) for shortcut, flags, zora in REVISION_2_FLAGSETS]
