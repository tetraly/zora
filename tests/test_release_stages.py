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


# --- promote reuses the test stage's result for the same commit (owner decision, 2026-10-19) ----

WORLD = {"world version": "0.7.0", "ZORA version": "2.0.0b7", "source hash": "sha256:feed"}


def _tested(make_release: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
            head: str = "a" * 40) -> tuple[Path, Path, dict[str, str]]:
    """A passing "publish to test" record for HEAD, its zora.apworld and notes in TMP_PATH."""
    import hashlib
    monkeypatch.setattr(make_release, "REPO", tmp_path)            # the record's paths are the repo's
    monkeypatch.setattr(make_release, "ASSETS", tmp_path)
    monkeypatch.setattr(make_release, "TEST_STAGE_RECORD", tmp_path / "test-stage.json")
    apworld = tmp_path / make_release.APWORLD_FILE
    apworld.write_bytes(b"the checked world")
    world = {**WORLD, "ZORA version": make_release.ZORA_VERSION,
             "sha256": hashlib.sha256(apworld.read_bytes()).hexdigest()}
    notes = tmp_path / make_release.RELEASE_NOTES
    record = make_release.write_test_stage(head, world, notes)
    return record, apworld, world


def test_promote_reuses_a_passing_test_stage_of_the_same_commit(make_release: ModuleType, tmp_path: Path,
                                                                monkeypatch: pytest.MonkeyPatch) -> None:
    record, _apworld, world = _tested(make_release, tmp_path, monkeypatch)
    assert json.loads(record.read_text())["world"] == world
    assert make_release.reusable_test_stage("a" * 40, record) == world


def test_promote_checks_again_for_another_commit_or_no_result(make_release: ModuleType, tmp_path: Path,
                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    record, apworld, _world = _tested(make_release, tmp_path, monkeypatch)
    assert make_release.reusable_test_stage("b" * 40, record) is None
    assert make_release.reusable_test_stage("a" * 40, tmp_path / "none.json") is None
    apworld.write_bytes(b"another world")              # not the zora.apworld the test stage checked
    assert make_release.reusable_test_stage("a" * 40, record) is None


def test_a_record_without_the_report_reads_it_from_the_notes(make_release: ModuleType, tmp_path: Path,
                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    """A record written before it kept build_apworld's report (beta 7's test stage): the notes the
    test stage wrote list it."""
    record, _apworld, world = _tested(make_release, tmp_path, monkeypatch)
    monkeypatch.setattr(make_release, "CHANGELOG", tmp_path / "CHANGELOG.md")
    (tmp_path / "CHANGELOG.md").write_text(f"## {make_release.PLAYER_VERSION} (2026-10-19)\n\n- a line\n")
    make_release.write_release_notes(world, "2026-10-19", "is published beside the test page")
    saved = json.loads(record.read_text())
    del saved["world"]
    record.write_text(json.dumps(saved))
    assert make_release.reusable_test_stage("a" * 40, record) == world


def test_promote_on_a_tested_commit_runs_no_check_again(make_release: ModuleType, tmp_path: Path,
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    _record, _apworld, world = _tested(make_release, tmp_path, monkeypatch)
    for name in ("check_full_tier", "check_clone"):
        monkeypatch.setattr(make_release, name, lambda *args: None)
    monkeypatch.setattr(make_release, "tested_commit", lambda record=None: "a" * 40)
    monkeypatch.setattr(make_release, "git", lambda *args, **kwargs: "a" * 40 + "\n")     # HEAD
    monkeypatch.setattr(make_release, "build_tree", lambda tree, today: ({}, "a" * 40))
    for name in ("check_world_version", "frozen_strings_problems", "run_checks", "build_world", "check_world"):
        monkeypatch.setattr(make_release, name, lambda *args, name=name: pytest.fail(f"{name} ran again"))
    written: list[tuple[dict[str, str], str]] = []
    committed: list[str] = []

    def write_release_notes(world: dict[str, str], today: str, where: str = "is attached", name: str = "") -> Path:
        written.append((world, name))
        return tmp_path / name

    def commit_release(tree: Path, head: str, today: str, notes: Path) -> int:
        committed.append(head)
        return 0

    monkeypatch.setattr(make_release, "write_release_notes", write_release_notes)
    monkeypatch.setattr(make_release, "commit_release", commit_release)
    assert make_release.release(False, stage="promote") == 0
    # the GitHub release's notes go beside the test stage's, which publish_site.sh --channel test reads
    assert written == [(world, make_release.PROMOTED_NOTES)] and committed == ["a" * 40]
    assert make_release.PROMOTED_NOTES != make_release.RELEASE_NOTES


def test_promote_without_a_result_checks_everything(make_release: ModuleType, tmp_path: Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("check_full_tier", "check_clone"):
        monkeypatch.setattr(make_release, name, lambda *args: None)
    monkeypatch.setattr(make_release, "tested_commit", lambda record=None: "a" * 40)
    monkeypatch.setattr(make_release, "git", lambda *args, **kwargs: "a" * 40 + "\n")     # HEAD
    monkeypatch.setattr(make_release, "build_tree", lambda tree, today: ({}, "a" * 40))
    monkeypatch.setattr(make_release, "reusable_test_stage", lambda head: None)
    monkeypatch.setattr(make_release, "check_world_version",
                        lambda head: make_release.Check("the world version", []))
    monkeypatch.setattr(make_release, "frozen_strings_problems", lambda head: ("beta7", []))

    class ChecksRan(Exception):
        pass

    def run_checks(*args: object) -> None:
        raise ChecksRan

    monkeypatch.setattr(make_release, "run_checks", run_checks)
    with pytest.raises(ChecksRan):
        make_release.release(False, stage="promote")
