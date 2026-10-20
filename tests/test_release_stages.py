"""scripts/make_release.py's two stages (owner design, 2026-10-18; docs/releasing.md "Channels"):
"publish to test" ends with the commands that put the site and zora.apworld on https://zora.gg/test/
(no tag, no GitHub release), and "promote" releases only the commit published to test, ending with
the tag, the push, the GitHub release with zora.apworld, the root site and the test channel's two
choices. Each stage stops at its commands; neither runs one."""
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"

# a release leaves out make_release.py (release/allowlist.txt)
pytestmark = pytest.mark.skipif(not (SCRIPTS / "make_release.py").exists(), reason="no release scripts here")


@pytest.fixture(scope="module")
def make_release() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("make_release", SCRIPTS / "make_release.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["make_release"] = module                # its dataclasses look their module up
    spec.loader.exec_module(module)
    return module


def test_publish_to_test_lists_the_test_channel_commands_only(make_release: ModuleType, tmp_path: Path) -> None:
    clone = tmp_path / "zora"
    commands = make_release.test_stage_commands(clone)
    assert commands == ["sh scripts/publish_site.sh --channel test", f"git -C {clone} push origin gh-pages"]
    assert not any(word in " ".join(commands) for word in ("tag", "gh release", "push origin main"))


def test_promote_lists_the_release_then_the_test_channels_choices(make_release: ModuleType, tmp_path: Path) -> None:
    clone, notes = tmp_path / "zora", tmp_path / "release-notes.md"
    steps = make_release.promote_commands("v2.0.0b6", notes, clone)
    assert list(steps) == ["release", "test channel: keep the same build", "test channel: clear it"]
    release = steps["release"]
    assert release[:2] == [f"git -C {clone} tag v2.0.0b6", f"git -C {clone} push origin main v2.0.0b6"]
    assert release[2].startswith("gh release create v2.0.0b6 ") and "zora.apworld" in release[2] \
        and f"--notes-file {notes}" in release[2]
    # the root page links the GitHub release's zora.apworld, so the site comes after the release
    assert release[3:] == ["sh scripts/publish_site.sh", f"git -C {clone} push origin gh-pages"]
    assert steps["test channel: keep the same build"] == []
    assert steps["test channel: clear it"] == ["sh scripts/publish_site.sh --clear-test",
                                                f"git -C {clone} push origin gh-pages"]


def test_the_test_stage_record_names_its_commit_and_assets(make_release: ModuleType, tmp_path: Path,
                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    """publish_site.sh --channel test reads the record's commit, apworld and notes (repo paths)."""
    record = tmp_path / "test-stage.json"
    monkeypatch.setattr(make_release, "TEST_STAGE_RECORD", record)
    notes = make_release.ASSETS / make_release.RELEASE_NOTES
    make_release.write_test_stage("abc1234" * 5 + "abcde", {"world version": "0.6.0"}, notes)
    written = json.loads(record.read_text())
    assert written["commit"] == "abc1234" * 5 + "abcde"
    assert (written["apworld"], written["notes"]) == ("temp/release/assets/zora.apworld",
                                                      "temp/release/assets/release-notes.md")
    assert make_release.tested_commit(record) == written["commit"]
    assert make_release.tested_commit(tmp_path / "none.json") is None
    publish_site = (SCRIPTS / "publish_site.sh").read_text()
    assert 'print(stage["commit"], stage["apworld"], stage["notes"])' in publish_site
    assert "stage=temp/release/test-stage.json" in publish_site


def test_promote_refuses_a_commit_not_published_to_test(make_release: ModuleType, monkeypatch: pytest.MonkeyPatch,
                                                        capsys: pytest.CaptureFixture[str]) -> None:
    """Refused before any build: the tested build is what becomes the release."""
    monkeypatch.setattr(make_release, "check_full_tier", lambda: None)
    monkeypatch.setattr(make_release, "check_clone", lambda clone: None)
    monkeypatch.setattr(make_release, "tested_commit", lambda record=None: "0" * 40)
    monkeypatch.setattr(make_release, "build_tree", lambda *args: pytest.fail("built before refusing"))
    assert make_release.release(False, stage="promote") == 1
    assert "promote releases the commit published to test" in capsys.readouterr().out


def test_a_stage_or_dry_run_is_required(make_release: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["make_release.py"])
    with pytest.raises(SystemExit) as stopped:
        make_release.main()
    assert stopped.value.code == 2


@pytest.mark.parametrize(("argv", "call"), [
    (["--dry-run"], (True, False, None, False)),             # the batch run's release-tree step (verify_full.sh)
    (["--dry-run", "--whole-suite"], (True, True, None, False)),
    (["--stage", "test"], (False, True, "test", False)),
    (["--stage", "test", "--without-batch-stamp"], (False, True, "test", True)),
    (["--stage", "promote"], (False, True, "promote", False))])
def test_each_way_in_reaches_the_release(make_release: ModuleType, monkeypatch: pytest.MonkeyPatch,
                                         argv: list[str], call: tuple[bool, bool, str | None, bool]) -> None:
    calls: list[tuple[bool, bool, str | None, bool]] = []

    def release(dry_run: bool, whole_suite: bool = True, stage: str | None = None, without_stamp: bool = False) -> int:
        calls.append((dry_run, whole_suite, stage, without_stamp))
        return 0
    monkeypatch.setattr(make_release, "release", release)
    monkeypatch.setattr(sys, "argv", ["make_release.py", *argv])
    assert make_release.main() == 0 and calls == [call]
    assert 'python3 scripts/make_release.py --dry-run || failed' in (SCRIPTS / "verify_full.sh").read_text()


def _up_to_the_frozen_strings(make_release: ModuleType, monkeypatch: pytest.MonkeyPatch, problems: list[str]) -> None:
    """release() with everything before the frozen strings' check stubbed, and the long builds failing the test."""
    monkeypatch.setattr(make_release, "check_full_tier", lambda: None)
    monkeypatch.setattr(make_release, "build_tree", lambda dest, today: ({}, "f" * 40))
    monkeypatch.setattr(make_release, "check_world_version", lambda head: make_release.Check("world version", []))
    monkeypatch.setattr(make_release, "frozen_strings_problems", lambda head: ("beta6", problems))
    monkeypatch.setattr(make_release, "run_checks", lambda *args, **kwargs: pytest.fail("built past a refusal"))


def test_publish_to_test_refuses_strings_frozen_from_another_commit(
        make_release: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """The compatibility promise is frozen from the commit that ships: the stage stops before any build and
    says how to re-freeze."""
    _up_to_the_frozen_strings(make_release, monkeypatch, ["new string: preset TTP5: Pick 5"])
    assert make_release.release(False, stage="test") == 1
    out = capsys.readouterr().out
    assert "new string: preset TTP5: Pick 5" in out
    assert "python3 scripts/freeze_flag_strings.py HEAD beta6 --replace" in out


def test_only_the_test_stage_may_go_without_the_batch_stamp(make_release: ModuleType, monkeypatch: pytest.MonkeyPatch,
                                                            capsys: pytest.CaptureFixture[str]) -> None:
    """Owner decision, 2026-10-18: the test channel may be published before the batch run passes;
    promotion to zora.gg always needs it."""
    for argv in (["--stage", "promote", "--without-batch-stamp"], ["--dry-run", "--without-batch-stamp"]):
        monkeypatch.setattr(sys, "argv", ["make_release.py", *argv])
        with pytest.raises(SystemExit) as stopped:
            make_release.main()
        assert stopped.value.code == 2
    with pytest.raises(SystemExit, match="only the test stage"):
        make_release.release(False, stage="promote", without_stamp=True)
    # the test stage skips the gate, says so, and goes on (here to the frozen strings' refusal)
    _up_to_the_frozen_strings(make_release, monkeypatch, ["new string: x"])
    monkeypatch.setattr(make_release, "check_full_tier", lambda: pytest.fail("the gate ran"))
    assert make_release.release(False, stage="test", without_stamp=True) == 1
    assert "skipped for the TEST channel" in capsys.readouterr().out


def test_the_record_says_whether_the_stamp_was_waived(make_release: ModuleType, tmp_path: Path,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    record = tmp_path / "test-stage.json"
    monkeypatch.setattr(make_release, "TEST_STAGE_RECORD", record)
    notes = make_release.ASSETS / make_release.RELEASE_NOTES
    make_release.write_test_stage("a" * 40, {"world version": "0.6.0"}, notes, batch_stamp=False)
    assert json.loads(record.read_text())["batch stamp"] is False
