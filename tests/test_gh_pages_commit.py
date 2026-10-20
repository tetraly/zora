"""scripts/gh_pages_commit.sh, publish_site.sh's commit step (docs/site-build.md, "Publishing the
site"): the published gh-pages branch always keeps the custom domain's CNAME (zora.gg). GitHub
commits it to origin's gh-pages when the domain is set, so the step builds on origin's branch,
keeps GitHub's CNAME (or writes one), and refuses a diverged branch. Throwaway repositories in
tmp_path: an "origin" and the clone the step commits in."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "gh_pages_commit.sh"

# a release leaves out the publish scripts (release/allowlist.txt)
pytestmark = pytest.mark.skipif(not SCRIPT.exists() or shutil.which("git") is None, reason="no publish script here")


def git(root: Path, *args: str, stdin: str | None = None) -> str:
    environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    return subprocess.run(["git", "-C", str(root), "-c", "user.name=test", "-c", "user.email=test@example.invalid",
                           "-c", "commit.gpgsign=false", *args], input=stdin, capture_output=True, text=True,
                          check=True, env=environment).stdout.strip()


def commit_files(root: Path, files: dict[str, str], parent: str | None, ref: str) -> str:
    """A commit of exactly FILES on PARENT, set as REF (plumbing, as GitHub's own commit would be)."""
    blobs = {name: git(root, "hash-object", "-w", "--stdin", stdin=text) for name, text in files.items()}
    tree = git(root, "mktree", stdin="".join(f"100644 blob {blob}\t{name}\n" for name, blob in blobs.items()))
    commit = git(root, "commit-tree", tree, *(["-p", parent] if parent else []), "-m", "commit")
    git(root, "update-ref", ref, commit)
    return commit


@pytest.fixture
def repos(tmp_path: Path) -> tuple[Path, Path]:
    origin, clone = tmp_path / "origin.git", tmp_path / "clone"
    git(tmp_path, "init", "-q", "--bare", str(origin))
    git(tmp_path, "init", "-q", str(clone))
    git(clone, "remote", "add", "origin", str(origin))
    return origin, clone


@pytest.fixture
def built(tmp_path: Path) -> tuple[Path, Path]:
    page, guide = tmp_path / "zora-2.0-beta-5-2026-10-14-abc1234.html", tmp_path / "guide.html"
    page.write_text("<!doctype html>\nnew page\n")
    guide.write_text("<!doctype html>\nguide\n")
    return page, guide


def publish(clone: Path, built: tuple[Path, Path]) -> subprocess.CompletedProcess[str]:
    environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    return subprocess.run(["sh", str(SCRIPT), str(clone), *map(str, built)], capture_output=True, text=True,
                          check=False, env=environment)


def branch_file(clone: Path, name: str) -> str:
    return git(clone, "cat-file", "-p", f"refs/heads/gh-pages:{name}")


def test_it_builds_on_githubs_cname_commit_and_keeps_it(repos: tuple[Path, Path], built: tuple[Path, Path]) -> None:
    """Today's case: the clone's gh-pages is a commit behind origin's, where GitHub added CNAME."""
    origin, clone = repos
    old = {"index.html": "old page\n", "zora-2.0-beta-4.html": "old page\n", ".nojekyll": ""}
    published = commit_files(origin, old, None, "refs/heads/gh-pages")
    githubs = commit_files(origin, {**old, "CNAME": "zora.gg"}, published, "refs/heads/gh-pages")
    git(clone, "fetch", "-q", "origin", "gh-pages:gh-pages")
    git(clone, "update-ref", "refs/heads/gh-pages", published)
    done = publish(clone, built)
    assert done.returncode == 0, done.stderr
    assert git(clone, "rev-parse", "refs/heads/gh-pages^") == githubs
    assert branch_file(clone, "CNAME") == "zora.gg"                       # GitHub's blob, as it wrote it
    assert git(clone, "rev-parse", "refs/heads/gh-pages:CNAME") == git(origin, "rev-parse", f"{githubs}:CNAME")
    assert branch_file(clone, "index.html") == built[0].read_text().strip()
    assert branch_file(clone, built[0].name) == built[0].read_text().strip()
    assert branch_file(clone, "archipelago-guide.html") == built[1].read_text().strip()
    assert branch_file(clone, "zora-2.0-beta-4.html") == "old page"        # earlier dated copies stay
    assert publish(clone, built).stdout.strip().endswith("nothing to commit")


def test_a_missing_cname_is_written(repos: tuple[Path, Path], built: tuple[Path, Path]) -> None:
    origin, clone = repos
    commit_files(origin, {"index.html": "old page\n", ".nojekyll": ""}, None, "refs/heads/gh-pages")
    assert publish(clone, built).returncode == 0
    assert branch_file(clone, "CNAME") == "zora.gg"


def test_the_first_publish_writes_the_cname_too(repos: tuple[Path, Path], built: tuple[Path, Path]) -> None:
    _origin, clone = repos
    assert publish(clone, built).returncode == 0
    assert sorted(git(clone, "ls-tree", "--name-only", "refs/heads/gh-pages").splitlines()) == sorted(
        [".nojekyll", "CNAME", "archipelago-guide.html", "index.html", built[0].name])


def test_a_diverged_branch_is_refused(repos: tuple[Path, Path], built: tuple[Path, Path]) -> None:
    origin, clone = repos
    base = commit_files(origin, {"index.html": "old\n"}, None, "refs/heads/gh-pages")
    git(clone, "fetch", "-q", "origin", "gh-pages:gh-pages")
    commit_files(origin, {"index.html": "theirs\n", "CNAME": "zora.gg"}, base, "refs/heads/gh-pages")
    mine = commit_files(clone, {"index.html": "mine\n"}, base, "refs/heads/gh-pages")
    done = publish(clone, built)
    assert done.returncode == 1 and "diverged" in done.stderr
    assert git(clone, "rev-parse", "refs/heads/gh-pages") == mine           # left as it was


def test_publish_site_uses_the_step() -> None:
    publish_site = (REPO / "scripts" / "publish_site.sh").read_text()
    assert 'sh scripts/gh_pages_commit.sh "$target" "$repo/$page" "$repo/$guide"' in publish_site


# --- the test channel (docs/releasing.md "Channels"): gh-pages' test/ folder only --------------------

ROOT = {"index.html": "regular page\n", "zora-2.0-beta-5.html": "regular page\n", "archipelago-guide.html": "guide\n",
        ".nojekyll": "", "CNAME": "zora.gg"}


def run_step(clone: Path, *args: str) -> subprocess.CompletedProcess[str]:
    environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    return subprocess.run(["sh", str(SCRIPT), *args, str(clone)] if args[:1] == ("--clear-test",) else
                          ["sh", str(SCRIPT), *args[:2], str(clone), *args[2:]],
                          capture_output=True, text=True, check=False, env=environment)


def channel_build(tmp_path: Path) -> list[str]:
    files = {"zora-2.0-beta-6-2026-10-18-abc1234-test.html": "<!doctype html>\ntest page\n",
             "guide-test.html": "<!doctype html>\ntest guide\n", "zora.apworld": "world\n", "release-notes.md": "notes\n"}
    for name, text in files.items():
        (tmp_path / name).write_text(text)
    return [str(tmp_path / name) for name in files]


def outside_test(clone: Path) -> str:
    return "\n".join(line for line in git(clone, "ls-tree", "-r", "refs/heads/gh-pages").splitlines()
                     if "\ttest/" not in line)


def test_test_publishing_writes_only_test_and_keeps_the_root_and_cname(repos: tuple[Path, Path],
                                                                      tmp_path: Path) -> None:
    origin, clone = repos
    published = commit_files(origin, ROOT, None, "refs/heads/gh-pages")
    before = git(origin, "ls-tree", "-r", published)
    page, guide, apworld, notes = channel_build(tmp_path)
    done = run_step(clone, "--channel", "test", page, guide, apworld, notes)
    assert done.returncode == 0, done.stderr
    assert outside_test(clone) == before                                     # every root file, CNAME included
    assert sorted(git(clone, "ls-tree", "-r", "--name-only", "refs/heads/gh-pages", "test").splitlines()) == [
        "test/archipelago-guide.html", "test/index.html", f"test/{Path(page).name}", "test/zora-apworld-notes.txt",
        "test/zora.apworld"]
    assert branch_file(clone, "test/index.html") == "<!doctype html>\ntest page"
    assert branch_file(clone, "test/zora.apworld") == "world"
    assert branch_file(clone, "CNAME") == "zora.gg"
    # the regular channel afterwards keeps the test channel
    regular = publish(clone, (Path(page), Path(guide)))
    assert regular.returncode == 0, regular.stderr
    assert branch_file(clone, "test/zora.apworld") == "world"


def test_test_publishing_is_refused_without_the_root_cname(repos: tuple[Path, Path], tmp_path: Path) -> None:
    """It never writes a root file, so a branch without zora.gg's CNAME (or none at all) is refused."""
    origin, clone = repos
    done = run_step(clone, "--channel", "test", *channel_build(tmp_path))
    assert done.returncode == 1 and "publish the regular channel first" in done.stderr
    commit_files(origin, {key: value for key, value in ROOT.items() if key != "CNAME"}, None, "refs/heads/gh-pages")
    done = run_step(clone, "--channel", "test", *channel_build(tmp_path))
    assert done.returncode == 1 and "publish the regular channel first" in done.stderr


def commit_with_test_folder(root: Path, files: dict[str, str], test_files: dict[str, str], ref: str) -> str:
    """A commit of FILES with TEST_FILES in its test/ folder (mktree takes one level at a time)."""
    def blob(text: str) -> str:
        return git(root, "hash-object", "-w", "--stdin", stdin=text)
    test_tree = git(root, "mktree", stdin="".join(f"100644 blob {blob(text)}\t{name}\n" for name, text in test_files.items()))
    tree = git(root, "mktree", stdin="".join(f"100644 blob {blob(text)}\t{name}\n" for name, text in files.items())
               + f"040000 tree {test_tree}\ttest\n")
    commit = git(root, "commit-tree", tree, "-m", "commit")
    git(root, "update-ref", ref, commit)
    return commit


def test_clearing_the_test_channel_removes_test_only(repos: tuple[Path, Path], tmp_path: Path) -> None:
    origin, clone = repos
    published = commit_with_test_folder(origin, ROOT, {"index.html": "old test\n", "zora.apworld": "old\n"},
                                        "refs/heads/gh-pages")
    done = run_step(clone, "--clear-test")
    assert done.returncode == 0, done.stderr
    assert git(clone, "ls-tree", "-r", "refs/heads/gh-pages") == "\n".join(
        line for line in git(origin, "ls-tree", "-r", published).splitlines() if "\ttest/" not in line)
    assert git(clone, "rev-parse", "refs/heads/gh-pages^") == published


def test_publish_site_passes_the_channel() -> None:
    publish_site = (REPO / "scripts" / "publish_site.sh").read_text()
    assert 'sh scripts/gh_pages_commit.sh --channel test "$target" "$repo/$page" "$repo/$guide" "$apworld" "$notes"' \
        in publish_site
    assert "sh scripts/gh_pages_commit.sh --clear-test" in publish_site
    assert 'build_site.py --single-file --with-private --channel "$channel"' in publish_site
