"""scripts/check_world_version.py: a release whose Archipelago world changed its options or recipe
format under the last final release's world version is refused (owner, 2026-10-17), and a beta never raises
the world version (owner rule, 2026-11-12, replacing 2026-10-18's 0.N.x for beta N)."""
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
    monkeypatch.setattr(script, "last_final_release", lambda: ("release", "ZORA 2.0.0 (2.0.0)"))
    monkeypatch.setattr(script, "interface", lambda commit, scratch, repo=REPO: OLD if commit == "release" else new)
    monkeypatch.setattr(script, "world_version",
                        lambda commit, repo=REPO: old_version if commit == "release" else new_version)
    monkeypatch.setattr(script, "zora_version", lambda commit: "2.1.0")      # a final release
    passed, verdict, _changes = script.check(head)
    assert passed is passes
    if not passes:
        assert "raise world_version in archipelago/archipelago.json" in verdict


@pytest.mark.parametrize(("new", "new_version", "passes"), [
    (OLD, "2.0.0", True),                                                          # nothing changed
    (changed(**{"hidden options": ["item_counter"]}), "2.0.0", True),             # changed, carried to the final
    (OLD, "2.0.1", False),                                                         # raised: refused
    (changed(**{"hidden options": ["item_counter"]}), "2.1.0", False),
])
def test_a_beta_keeps_the_last_final_releases_world_version(script: ModuleType, monkeypatch: pytest.MonkeyPatch,
                                                            new: dict[str, Any], new_version: str,
                                                            passes: bool) -> None:
    """Owner rule, 2026-11-12: betas never raise the world version, whatever changed; the next final release does."""
    monkeypatch.setattr(script, "last_final_release", lambda: ("release", "ZORA 2.0.0 (2.0.0)"))
    monkeypatch.setattr(script, "interface", lambda commit, scratch, repo=REPO: OLD if commit == "release" else new)
    monkeypatch.setattr(script, "world_version",
                        lambda commit, repo=REPO: "2.0.0" if commit == "release" else new_version)
    monkeypatch.setattr(script, "zora_version", lambda commit: "2.0.1b1")
    passed, verdict, _changes = script.check("HEAD")
    assert passed is passes
    assert ("set world_version in archipelago/archipelago.json back" in verdict) is not passes


def test_the_last_final_release_skips_betas(script: ModuleType, tmp_path: Path) -> None:
    log = tmp_path / "published.log"
    log.write_text("# comment\naaa bbb 2026-10-12 ZORA 2.0 beta 1 (2.0.0b1; amended)\n"
                   "ccc ddd 2026-11-08 ZORA 2.0.0 (2.0.0)\n"
                   "eee fff 2026-11-20 ZORA 2.0.1 beta 1 (2.0.1b1)\nggg hhh 2026-11-25 ZORA 2.0.1 beta 2 (2.0.1b2)\n")
    assert script.last_final_release(log) == ("ddd", "ZORA 2.0.0 (2.0.0)")
    assert script.last_release(log) == ("hhh", "ZORA 2.0.1 beta 2 (2.0.1b2)")


def test_the_last_release_is_the_logs_last_line(script: ModuleType, tmp_path: Path) -> None:
    log = tmp_path / "published.log"
    log.write_text("# comment\naaa bbb 2026-10-12 ZORA 2.0 beta 4 (2.0.0b4)\n"
                   "ccc ddd 2026-10-14 ZORA 2.0 beta 5 (2.0.0b5)\n")
    assert script.last_release(log) == ("ddd", "ZORA 2.0 beta 5 (2.0.0b5)")


def test_heads_interface_is_read(script: ModuleType, tmp_path: Path) -> None:
    """The isolated interpreter reads this commit's options, settings, hidden options and formats."""
    found = script.interface("HEAD", tmp_path)
    assert found["options"]["starting_hearts"]["id"] == "C16"
    assert found["player settings"]["green_tunic"]["kind"] == "color"
    # (Universal Drops v2.0 and Item Counter are real options since 2026-11-21, beta values in Archipelago)
    assert found["hidden options"] == ["detailed_spoiler_log", "disable_custom_music", "gatekeeper_bosses",
                                       "item_shuffle_no_vanilla", "shuffle_wood_sword"]
    assert found["recipe format"][0] == "zora-ap-recipe"


def test_this_checkout_keeps_a_betas_world_version(script: ModuleType) -> None:
    """While ZORA_VERSION is a beta, the committed world version is the last final release's."""
    import json

    from zora.version import ZORA_VERSION
    if not script.BETA.fullmatch(ZORA_VERSION):
        pytest.skip(f"ZORA {ZORA_VERSION} is not a beta")
    world = json.loads((REPO / "archipelago" / "archipelago.json").read_text())["world_version"]
    assert world == script.world_version(script.last_final_release()[0])
