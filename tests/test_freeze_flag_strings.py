"""scripts/freeze_flag_strings.py: a release's file name, and what separates a fresh freeze from the
frozen file (AGENTS.md "Flag strings"; make_release.py's stages refuse any difference)."""
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "freeze_flag_strings.py"

# a release leaves out the script (release/allowlist.txt)
pytestmark = pytest.mark.skipif(not SCRIPT.exists(), reason="scripts/freeze_flag_strings.py is not released")


@pytest.fixture(scope="module")
def freeze() -> ModuleType:
    spec = importlib.util.spec_from_file_location("freeze_flag_strings", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def frozen(commit: str, *entries: dict) -> str:
    return json.dumps({"release": "2.0 beta 6", "commit": commit, "strings": list(entries)})


def entry(name: str, z1r: str = "0", **zora: object) -> dict:
    return {"name": name, "z1r": z1r, "zora": "", "z1r_settings": {"C01": 0}, "zora_flags": dict(zora)}


def test_release_names(freeze: ModuleType) -> None:
    assert (freeze.release_name("2.0.0b6"), freeze.release_name("2.0.0b12"), freeze.release_name("2.0.0")) == (
        "beta6", "beta12", "2.0.0")


def test_only_the_decoding_commit_may_differ(freeze: ModuleType) -> None:
    assert freeze.differences(frozen("aaaaaaa", entry("a", pegasus=0)), frozen("bbbbbbb", entry("a", pegasus=0))) == []


def test_every_kind_of_difference_is_named(freeze: ModuleType) -> None:
    old = frozen("f5a3859", entry("kept", progressive=0, retired=0), entry("changed", progressive=0),
                 entry("respelled"), entry("dropped"))
    new = frozen("1234567", entry("kept", progressive=0, boots=0), entry("changed", progressive=1),
                 entry("respelled", z1r="1"), entry("added"))
    assert freeze.differences(new, old) == [
        "new string: added", "string gone: dropped", "decodes differently: changed: progressive 0 -> 1",
        "another string: respelled", "settings added since: boots",
        "settings removed since (their place kept, ignored): retired"]


def test_the_beta_6_file_matches_its_own_commit(freeze: ModuleType) -> None:
    """The committed file is beta 6's own decoding of its commit (f5a3859 until the release re-freezes it)."""
    commit = json.loads((freeze.FROZEN_FOLDER / "beta6.json").read_text())["commit"]
    assert freeze.check(commit, "beta6") == []
