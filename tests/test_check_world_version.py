"""scripts/check_world_version.py: a release whose Archipelago world changed its options or recipe
format under the last release's world version is refused (owner, 2026-10-17), and so is a world version
off the beta rule: 0.N.x for ZORA 2.0 beta N (owner, 2026-10-18)."""
import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "check_world_version.py"

# a release leaves out the script (release/allowlist.txt)
pytestmark = pytest.mark.skipif(not SCRIPT.exists(), reason="scripts/check_world_version.py is not released")

OLD: dict[str, Any] = {
    "options": {"starting_hearts": {"id": "C16", "kind": "choice", "values": [[3, "hearts_3"]], "default": 3},
                "extra_candles": {"id": "B09", "kind": "three_state", "values": [[0, "off"], [1, "on"]], "default": 1}},
    "player settings": {"green_tunic": {"kind": "color", "values": [[41, "0x29"]], "default": 41, "word rule": None}},
    "hidden options": [],
    "recipe format": ["zora-ap-recipe", "1.1"],
    "client tables format": ["zora-ap-client-tables", 1],
}


@pytest.fixture(scope="module")
def script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_world_version", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def changed(**sections: Any) -> dict[str, Any]:
    new = {key: (dict(value) if isinstance(value, dict) else value) for key, value in OLD.items()}
    new.update(sections)
    return new


def test_no_differences(script: ModuleType) -> None:
    assert script.differences(OLD, changed()) == []


def test_each_kind_of_change_is_named(script: ModuleType) -> None:
    options = dict(OLD["options"])
    options["starting_hearts"] = {**options["starting_hearts"], "values": [[3, "hearts_3"], [4, "hearts_4"]]}
    del options["extra_candles"]
    options["add_l4_sword"] = {"id": "add_l4_sword", "kind": "choice", "values": [[0, "off"]], "default": 0}
    new = changed(options=options, **{"hidden options": ["shuffle_wood_sword"],
                                      "recipe format": ["zora-ap-recipe", "1.2"]})
    assert script.differences(OLD, new) == [
        "options: add_l4_sword added",
        "options: extra_candles removed",
        "options: starting_hearts's values changed",
        "hidden options: [] -> ['shuffle_wood_sword']",
        "recipe format: ['zora-ap-recipe', '1.1'] -> ['zora-ap-recipe', '1.2']",
    ]


@pytest.mark.parametrize(("new", "old_version", "new_version", "passes"), [
    (OLD, "0.4.0", "0.4.0", True),                        # nothing changed
    (changed(**{"recipe format": ["zora-ap-recipe", "1.2"]}), "0.4.0", "0.5.0", True),
    (changed(**{"recipe format": ["zora-ap-recipe", "1.2"]}), "0.4.0", "0.4.0", False),
])
def test_a_change_needs_a_new_world_version(script: ModuleType, monkeypatch: pytest.MonkeyPatch,
                                            new: dict[str, Any], old_version: str, new_version: str,
                                            passes: bool) -> None:
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()
    monkeypatch.setattr(script, "last_release", lambda: ("release", "ZORA 2.0 beta 5 (2.0.0b5)"))
    monkeypatch.setattr(script, "interface", lambda commit, scratch, repo=REPO: OLD if commit == "release" else new)
    monkeypatch.setattr(script, "world_version",
                        lambda commit, repo=REPO: old_version if commit == "release" else new_version)
    monkeypatch.setattr(script, "zora_version", lambda commit: "2.0.0")      # a final release: no beta rule
    passed, verdict, _changes = script.check(head)
    assert passed is passes
    if not passes:
        assert "raise world_version in archipelago/archipelago.json" in verdict


def test_check_refuses_a_world_version_off_the_beta_rule(script: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(script, "world_version", lambda commit, repo=REPO: "0.5.0")
    monkeypatch.setattr(script, "zora_version", lambda commit: "2.0.0b6")
    passed, verdict, changes = script.check("HEAD")
    assert (passed, changes) == (False, [])
    assert "must be 0.6.x" in verdict


def test_the_last_release_is_the_logs_last_line(script: ModuleType, tmp_path: Path) -> None:
    log = tmp_path / "published.log"
    log.write_text("# comment\naaa bbb 2026-10-12 ZORA 2.0 beta 4 (2.0.0b4)\nccc ddd 2026-10-14 ZORA 2.0 beta 5 (2.0.0b5)\n")
    assert script.last_release(log) == ("ddd", "ZORA 2.0 beta 5 (2.0.0b5)")


def test_heads_interface_is_read(script: ModuleType, tmp_path: Path) -> None:
    """The isolated interpreter reads this commit's options, settings, hidden options and formats."""
    found = script.interface("HEAD", tmp_path)
    assert found["options"]["starting_hearts"]["id"] == "C16"
    assert found["player settings"]["green_tunic"]["kind"] == "color"
    assert found["hidden options"] == ["disable_custom_music", "gatekeeper_bosses", "item_shuffle_no_vanilla",
                                       "shuffle_wood_sword"]
    assert found["recipe format"][0] == "zora-ap-recipe"


@pytest.mark.parametrize(("world", "zora", "holds"), [
    ("0.6.0", "2.0.0b6", True), ("0.6.3", "2.0.0b6", True), ("0.5.0", "2.0.0b6", False),
    ("0.7.0", "2.0.0b6", False), ("1.6.0", "2.0.0b6", False), ("0.6", "2.0.0b6", False),
    ("0.12.1", "2.0.0b12", True), ("1.0.0", "2.0.0", True)])
def test_the_beta_rule(script: ModuleType, world: str, zora: str, holds: bool) -> None:
    """Owner, 2026-10-18: for ZORA 2.0 beta N the world version is 0.N.x, the last number counting
    fixes within the beta; a final release is not held to it."""
    problem = script.beta_rule_problem(world, zora)
    assert (problem is None) == holds
    if not holds:
        assert "0." in problem and "archipelago/archipelago.json" in problem


def test_this_checkout_keeps_the_beta_rule(script: ModuleType) -> None:
    """The committed manifest and ZORA_VERSION agree (world 0.11.0 for 2.0 beta 11): a version bump
    raises both."""
    import json

    from zora.version import ZORA_VERSION
    world = json.loads((REPO / "archipelago" / "archipelago.json").read_text())["world_version"]
    assert script.beta_rule_problem(world, ZORA_VERSION) is None
