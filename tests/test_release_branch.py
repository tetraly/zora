"""scripts/release_branch.py (docs/releasing.md "Release branch"): in a throwaway repository beside a throwaway
worktree, never the real ones; nothing here publishes anything."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
# Joined at run time: this file is released too, and the release scan must not find the private checkout's name in it
CHECKOUT = "-".join(("zora", "ng"))
WORKTREE = f"{CHECKOUT}-release"
SCRIPTS = ("release_branch.py", "full_tier.py")
ROMS = ("Legend of Zelda, The (USA).nes", "Legend of Zelda, The (USA) (Rev 1).nes")
LOCK_SETTING, JOBS_SETTING = "ZORA_SUITE_LOCK", "ZORA_JOBS_FOLDER"
ROTATION = Path("temp") / "batch" / "sweep-rotation.json"
STAMPS = Path("temp") / "verify" / "full-tier"
SETTINGS = ("ZORA_SOURCE_REPO", "ZORA_COPY_REVISION", "ZORA_COPY_ADDED", LOCK_SETTING, JOBS_SETTING)

pytestmark = pytest.mark.skipif(not (REPO / "scripts" / "release_branch.py").exists(), reason="no release scripts here")


def _environment() -> dict[str, str]:
    return {name: value for name, value in os.environ.items() if not name.startswith("GIT_") and name not in SETTINGS}


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=test", "-c", "user.email=test@example.invalid",
                           "-c", "commit.gpgsign=false", *args], capture_output=True, text=True, check=True,
                          env=_environment()).stdout.strip()


def tool(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "scripts/release_branch.py", *args], cwd=repo, capture_output=True, text=True,
                          check=False, env=_environment())


def commit(repo: Path, path: str, text: str, message: str) -> str:
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_text(text)
    git(repo, "add", path)
    git(repo, "commit", "--quiet", "--no-verify", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def stamp(repo: Path, commit_id: str) -> None:
    tree = git(repo, "rev-parse", f"{commit_id}^{{tree}}")
    (repo / STAMPS).mkdir(parents=True, exist_ok=True)
    (repo / STAMPS / f"{tree}.json").write_text(json.dumps({"tree": tree, "commit": commit_id}))


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A main checkout under tmp_path with the ignored inputs, and one stamped commit."""
    root = tmp_path / CHECKOUT
    (root / "scripts").mkdir(parents=True)
    for script in SCRIPTS:
        shutil.copy2(REPO / "scripts" / script, root / "scripts" / script)
    (root / ".gitignore").write_text("temp/\n*.nes\nprivate/\nmusic/\nverify.env\n")
    (root / "release").mkdir()
    (root / "release" / "published.log").write_text("aaa bbb 2026-01-01 ZORA 1.0\n")
    git(root, "init", "--quiet", "--initial-branch=main")
    git(root, "add", "--all")
    git(root, "commit", "--quiet", "--no-verify", "-m", "first")
    for name in ROMS:
        (root / name).write_text("rom")
    for folder in ("private", "music"):
        (root / folder).mkdir()
        (root / folder / "file").write_text(folder)
    (root / "verify.env").write_text("ZORA_CORPORA=../corpora\nZORA_SUITE_LOCK=/old\n")
    (root / ROTATION).parent.mkdir(parents=True)
    (root / ROTATION).write_text('{"next": 32}')
    stamp(root, git(root, "rev-parse", "HEAD"))
    return root


def settings_of(worktree: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in (worktree / "verify.env").read_text().splitlines())


def test_start_cuts_the_branch_from_the_stamped_commit_with_its_inputs(repo: Path) -> None:
    stamped = git(repo, "rev-parse", "HEAD")
    commit(repo, "later.txt", "later\n", "after the stamp, generation")
    done = tool(repo, "start", "2.0.1")
    assert done.returncode == 0, done.stdout + done.stderr
    worktree = repo.parent / WORKTREE
    assert git(worktree, "branch", "--show-current") == "release/2.0.1"
    assert git(worktree, "rev-parse", "HEAD") == stamped                 # the newest stamped, not main's HEAD
    assert all((worktree / name).read_text() == "rom" for name in ROMS)
    assert (worktree / "private" / "file").exists() and (worktree / "music" / "file").exists()
    assert (worktree / ROTATION).read_text() == '{"next": 32}' and len(list((worktree / STAMPS).glob("*.json"))) == 1
    temp = repo.resolve() / "temp"
    expected = {"ZORA_CORPORA": "../corpora", JOBS_SETTING: f"{temp}/jobs"}     # the old lock line dropped
    assert settings_of(worktree) == expected


@pytest.mark.parametrize("name", [ROMS[1], "private", "music"])
def test_start_refuses_without_an_input_a_release_needs(repo: Path, name: str) -> None:
    path = repo / name
    shutil.rmtree(path) if path.is_dir() else path.unlink()
    done = tool(repo, "start", "2.0.1")
    assert done.returncode == 1 and name in done.stderr and not (repo.parent / WORKTREE).exists()


def test_start_refuses_a_commit_without_a_stamp(repo: Path) -> None:
    unstamped = commit(repo, "later.txt", "later\n", "no stamp")
    done = tool(repo, "start", "2.0.1", unstamped)
    assert done.returncode == 1 and "no batch-run stamp" in done.stderr
    assert not (repo.parent / WORKTREE).exists() and not git(repo, "branch", "--list", "release/*")


def test_start_refuses_a_second_release_and_a_bad_version(repo: Path) -> None:
    assert tool(repo, "start", "2.0.1").returncode == 0
    second = tool(repo, "start", "2.0.2")
    assert second.returncode == 1 and "one release at a time" in second.stderr
    assert "not a version" in tool(repo, "start", "two").stderr


def test_status_names_the_branch_and_what_is_left(repo: Path) -> None:
    assert "none" in tool(repo, "status").stdout
    tool(repo, "start", "2.0.1")
    done = tool(repo, "status")
    assert "release/2.0.1" in done.stdout and "has a batch-run stamp" in done.stdout
    assert "test stage: none yet" in done.stdout and "promoted: not yet" in done.stdout


def test_a_worktrees_verify_env_names_the_job_list_and_not_the_lock(tmp_path: Path,
                                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    """Jobs started in a release worktree without the settings on their command line show in main's list; its heavy
    runs take the machine's lock, whatever an old verify.env says (tests/suite_lock.py)."""
    from tests import suite_lock
    from zora_measure import corpora, progress
    (tmp_path / "verify.env").write_text(f"{LOCK_SETTING}=/main/temp/test-suite.lock\n{JOBS_SETTING}=/main/temp/jobs\n")
    monkeypatch.delenv(LOCK_SETTING, raising=False)
    monkeypatch.delenv(JOBS_SETTING, raising=False)
    monkeypatch.setattr(suite_lock, "REPO", tmp_path)
    monkeypatch.setattr(corpora, "SETTINGS_FILE", tmp_path / "verify.env")
    assert suite_lock.lock_path() == suite_lock.MACHINE_LOCK
    assert progress.jobs_folder() == Path("/main/temp/jobs")


@pytest.fixture
def promoted(repo: Path) -> Path:
    """A started branch with one commit of its own and its release recorded (no real promotion); origin is up to date."""
    origin = repo.parent / "origin.git"
    git(repo.parent, "init", "--quiet", "--bare", str(origin))
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "--quiet", "origin", "main")
    tool(repo, "start", "2.0.1")
    worktree = repo.parent / WORKTREE
    built = commit(worktree, "CHANGELOG.md", "2.0.1\n", "the release's own change")
    log = (worktree / "release" / "published.log").read_text() + f"ccc {built} 2026-11-09 ZORA 2.0.1 (2.0.1)\n"
    commit(worktree, "release/published.log", log, "Release log")
    return worktree


def test_finish_merges_carries_back_and_removes(repo: Path, promoted: Path) -> None:
    (promoted / ROTATION).write_text('{"next": 52}')
    tree = git(promoted, "rev-parse", "HEAD^{tree}")
    (promoted / STAMPS / f"{tree}.json").write_text(json.dumps({"tree": tree, "commit": "x"}))
    built = git(promoted, "rev-parse", "HEAD~1")
    main_side = commit(repo, "feature.txt", "meanwhile\n", "a feature on main meanwhile")
    git(repo, "push", "--quiet", "origin", "main")
    done = tool(repo, "finish")
    assert done.returncode == 0, done.stdout + done.stderr
    parents = git(repo, "log", "-1", "--format=%P").split()
    assert len(parents) == 2 and parents[0] == main_side                     # a merge commit, main first
    assert git(repo, "log", "-1", "--format=%s") == "Merge release/2.0.1: ZORA 2.0.1 (2.0.1), published 2026-11-09"
    subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", built, "HEAD"], check=True, env=_environment())
    assert (repo / ROTATION).read_text() == '{"next": 52}' and (repo / STAMPS / f"{tree}.json").exists()
    assert not promoted.exists() and not git(repo, "branch", "--list", "release/*")
    assert "git push origin main" in done.stdout
    assert git(repo, "rev-parse", "origin/main") == main_side                # nothing was pushed


def test_finish_refuses_before_promotion(repo: Path) -> None:
    tool(repo, "start", "2.0.1")
    done = tool(repo, "finish")
    assert done.returncode == 1 and "not been promoted" in done.stderr and (repo.parent / WORKTREE).exists()


def test_finish_refuses_uncommitted_changes(repo: Path, promoted: Path) -> None:
    (promoted / "CHANGELOG.md").write_text("changed\n")
    done = tool(repo, "finish")
    assert done.returncode == 1 and "uncommitted" in done.stderr and promoted.exists()


def test_finish_refuses_while_main_has_unpushed_commits(repo: Path, promoted: Path) -> None:
    commit(repo, "feature.txt", "unpushed\n", "someone's unpushed commit")
    done = tool(repo, "finish")
    assert done.returncode == 1 and "not yet pushed" in done.stderr and promoted.exists()


def test_a_conflict_leaves_main_alone_and_a_merge_by_hand_finishes(repo: Path, promoted: Path) -> None:
    head = commit(repo, "CHANGELOG.md", "main's line\n", "main's change to the same file")
    git(repo, "push", "--quiet", "origin", "main")
    done = tool(repo, "finish")
    assert done.returncode == 1 and "merge by hand" in done.stderr and git(repo, "rev-parse", "HEAD") == head
    assert not (repo / ".git" / "MERGE_HEAD").exists() and promoted.exists()
    subprocess.run(["git", "-C", str(repo), "merge", "--no-ff", "release/2.0.1"], capture_output=True, env=_environment())
    (repo / "CHANGELOG.md").write_text("both\n")
    git(repo, "add", "CHANGELOG.md")
    git(repo, "commit", "--quiet", "--no-verify", "-m", "the merge, by hand")
    git(repo, "push", "--quiet", "origin", "main")
    again = tool(repo, "finish")
    assert again.returncode == 0, again.stdout + again.stderr
    assert not promoted.exists() and git(repo, "log", "-1", "--format=%s") == "the merge, by hand"


def test_main_keeps_a_rotation_it_moved_itself(repo: Path, promoted: Path) -> None:
    (promoted / ROTATION).write_text('{"next": 52}')
    (repo / ROTATION).write_text('{"next": 72}')
    assert tool(repo, "finish").returncode == 0
    assert (repo / ROTATION).read_text() == '{"next": 72}'
