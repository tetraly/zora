"""The full verification tier's stamp (scripts/full_tier.py; docs/design/test-speed.md 3.2): a
tree is stamped only when it is exactly a commit, a release needs HEAD's tree stamped, and any
change to the tree needs the full tier again. A throwaway git repository with the script."""
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FULL_TIER = REPO / "scripts" / "full_tier.py"
MAKE_RELEASE = REPO / "scripts" / "make_release.py"
SETTINGS = ("ZORA_SOURCE_REPO", "ZORA_COPY_REVISION", "ZORA_COPY_ADDED")

pytestmark = pytest.mark.skipif(not FULL_TIER.exists(), reason="scripts/full_tier.py is not here")


def _environment(**settings: str) -> dict[str, str]:
    base = {name: value for name, value in os.environ.items() if not name.startswith("GIT_") and name not in SETTINGS}
    return {**base, **settings}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=test", "-c", "user.email=test@example.invalid",
                           "-c", "commit.gpgsign=false", *args], capture_output=True, text=True, check=True,
                          env=_environment()).stdout.strip()


def _full_tier(repo: Path, *args: str, **settings: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "scripts/full_tier.py", *args], cwd=repo, capture_output=True,
                          text=True, check=False, env=_environment(**settings))


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "scripts").mkdir()
    shutil.copy2(FULL_TIER, tmp_path / "scripts" / "full_tier.py")
    (tmp_path / ".gitignore").write_text("temp/\n")
    (tmp_path / "game.txt").write_text("one\n")
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "add", "--all")
    _git(tmp_path, "commit", "--quiet", "--no-verify", "-m", "first")
    return tmp_path


def test_a_clean_commit_is_stamped_and_checked(repo: Path) -> None:
    assert _full_tier(repo, "check").returncode == 1
    done = _full_tier(repo, "stamp", "7")
    assert "stamped" in done.stdout and "NOT" not in done.stdout
    assert (repo / "temp" / "verify" / "full-tier" / f"{_git(repo, 'rev-parse', 'HEAD^{tree}')}.json").is_file()
    assert _full_tier(repo, "check").returncode == 0


def test_uncommitted_changes_are_not_stamped(repo: Path) -> None:
    (repo / "game.txt").write_text("two\n")
    done = _full_tier(repo, "stamp", "7")
    assert "NOT stamped" in done.stdout
    assert _full_tier(repo, "check").returncode == 1


def test_a_new_commit_needs_the_full_tier_again(repo: Path) -> None:
    _full_tier(repo, "stamp", "7")
    (repo / "game.txt").write_text("two\n")
    _git(repo, "commit", "--quiet", "--no-verify", "-am", "second")
    assert _full_tier(repo, "check").returncode == 1


def test_a_copy_with_added_paths_is_not_stamped(repo: Path) -> None:
    head = _git(repo, "rev-parse", "HEAD")
    done = _full_tier(repo, "stamp", "7", ZORA_SOURCE_REPO=str(repo), ZORA_COPY_REVISION=head,
                      ZORA_COPY_ADDED="game.txt")
    assert "NOT stamped" in done.stdout and "adds working-tree paths" in done.stdout


def test_a_copy_whose_tree_is_not_its_commit_is_not_stamped(repo: Path) -> None:
    """A copy claiming to be the first commit while holding other files."""
    first = _git(repo, "rev-parse", "HEAD")
    (repo / "game.txt").write_text("two\n")
    _git(repo, "commit", "--quiet", "--no-verify", "-am", "second")
    done = _full_tier(repo, "stamp", "7", ZORA_SOURCE_REPO=str(repo), ZORA_COPY_REVISION=first)
    assert "NOT stamped" in done.stdout and "is not" in done.stdout


def test_the_last_release_is_the_logs_last_source_commit(repo: Path) -> None:
    (repo / "release").mkdir()
    (repo / "release" / "published.log").write_text("# comment\naaaa 1111 2026-10-07 one\nbbbb 2222 2026-10-12 two\n")
    assert _full_tier(repo, "last-release").stdout.strip() == "2222"


@pytest.mark.skipif(not MAKE_RELEASE.exists(), reason="scripts/make_release.py is not released")
def test_a_release_without_the_stamp_is_refused(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """make_release.py checks the stamp before anything else (its --dry-run is part of the tier)."""
    monkeypatch.syspath_prepend(str(REPO))              # make_release imports zora from the repo root
    spec = importlib.util.spec_from_file_location("make_release_under_test", MAKE_RELEASE)
    assert spec and spec.loader
    make_release = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, make_release)     # its dataclasses look themselves up
    spec.loader.exec_module(make_release)
    for name in SETTINGS:                       # make_release runs in the checkout it releases
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(make_release, "REPO", repo)
    with pytest.raises(SystemExit, match="release refused: full tier: HEAD's tree .* has NO stamp"):
        make_release.check_full_tier()
    _full_tier(repo, "stamp", "7")
    make_release.check_full_tier()
