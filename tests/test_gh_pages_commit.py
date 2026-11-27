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


# --- the flags spec (docs/flags-api.md "Where to get it") ------------------------------------------------------

def spec_files(tmp_path: Path, text: str) -> list[str]:
    spec, schema = tmp_path / "zora-flags-2.0.1.json", tmp_path / "zora-flags.schema.json"
    spec.write_text(text)
    schema.write_text('{"schema": 1}\n')
    return [str(spec), str(schema), "2.0.1"]


def test_the_regular_channel_writes_the_spec_once_per_version(repos: tuple[Path, Path], built: tuple[Path, Path],
                                                              tmp_path: Path) -> None:
    """flags/<version>.json is written once and never replaced; latest.json is that file, so it is always a
    published version's; the schema beside them."""
    origin, clone = repos
    commit_files(origin, ROOT, None, "refs/heads/gh-pages")
    environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}

    def publish_with(text: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["sh", str(SCRIPT), str(clone), *map(str, built), *spec_files(tmp_path, text)],
                              capture_output=True, text=True, check=False, env=environment)

    first = publish_with('{"zora_version": "2.0.1"}\n')
    assert first.returncode == 0, first.stderr
    assert branch_file(clone, "flags/2.0.1.json") == '{"zora_version": "2.0.1"}'
    assert branch_file(clone, "flags/latest.json") == '{"zora_version": "2.0.1"}'
    assert branch_file(clone, "flags/zora-flags.schema.json") == '{"schema": 1}'
    again = publish_with('{"zora_version": "2.0.1", "changed": true}\n')
    assert again.returncode == 0, again.stderr
    assert "already published and differs" in again.stdout
    assert branch_file(clone, "flags/2.0.1.json") == '{"zora_version": "2.0.1"}'
    assert branch_file(clone, "flags/latest.json") == '{"zora_version": "2.0.1"}'
    assert branch_file(clone, "CNAME") == "zora.gg"


def test_the_test_channel_writes_only_its_own_latest_spec(repos: tuple[Path, Path], tmp_path: Path) -> None:
    origin, clone = repos
    published = commit_files(origin, ROOT, None, "refs/heads/gh-pages")
    before = git(origin, "ls-tree", "-r", published)
    spec = spec_files(tmp_path, '{"zora_version": "2.0.2"}\n')[0]
    done = run_step(clone, "--channel", "test", *channel_build(tmp_path), spec)
    assert done.returncode == 0, done.stderr
    assert branch_file(clone, "test/flags/latest.json") == '{"zora_version": "2.0.2"}'
    assert outside_test(clone) == before                  # no root flags/ file: latest.json stays a release's


def test_publish_site_passes_the_spec() -> None:
    publish_site = (REPO / "scripts" / "publish_site.sh").read_text()
    assert 'python3 scripts/flags_api.py --published "$flags"' in publish_site
    assert '"$apworld" "$notes" "$spec"' in publish_site
    assert '"$spec" "$repo/$flags/zora-flags.schema.json"' in publish_site


# --- presets.json, the presets a race bot can roll (docs/flags-api.md "Presets") ------------------------------

def presets_file(tmp_path: Path, revision: int, name: str = "Week 1") -> Path:
    path = tmp_path / f"presets-{revision}-{len(name)}.json"
    path.write_text(f'{{"schemaVersion": 1, "revision": {revision}, "updatedAt": "2026-11-17T00:00:00Z", '
                    f'"flagsets": [{{"name": "{name}"}}]}}\n')
    return path


def publish_presets(clone: Path, presets: Path) -> subprocess.CompletedProcess[str]:
    environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    return subprocess.run(["sh", str(SCRIPT), "--presets", str(clone), str(presets)], capture_output=True, text=True,
                          check=False, env=environment)


def test_presets_alone_writes_only_presets_json(repos: tuple[Path, Path], tmp_path: Path) -> None:
    origin, clone = repos
    published = commit_files(origin, ROOT, None, "refs/heads/gh-pages")
    before = git(origin, "ls-tree", "-r", published)
    done = publish_presets(clone, presets_file(tmp_path, 1))
    assert done.returncode == 0, done.stderr
    assert '"revision": 1' in branch_file(clone, "presets.json")
    assert "\n".join(line for line in git(clone, "ls-tree", "-r", "refs/heads/gh-pages").splitlines()
                     if not line.endswith("\tpresets.json")) == before
    assert git(clone, "log", "-1", "--format=%s", "refs/heads/gh-pages") == "Presets revision 1"


def test_presets_alone_is_refused_without_the_root_cname(repos: tuple[Path, Path], tmp_path: Path) -> None:
    done = publish_presets(repos[1], presets_file(tmp_path, 1))
    assert done.returncode == 1 and "publish the regular channel first" in done.stderr


def test_presets_only_move_forward(repos: tuple[Path, Path], tmp_path: Path) -> None:
    """A higher revision replaces the site's file; an older one (a publish from an older commit) keeps it; the
    same revision with other presets is refused, since the bot would never reread it."""
    origin, clone = repos
    commit_files(origin, ROOT, None, "refs/heads/gh-pages")
    assert publish_presets(clone, presets_file(tmp_path, 2)).returncode == 0
    older = publish_presets(clone, presets_file(tmp_path, 1))
    assert older.returncode == 0 and "kept as it is" in older.stdout
    assert '"revision": 2' in branch_file(clone, "presets.json")
    clash = publish_presets(clone, presets_file(tmp_path, 2, "Another name"))
    assert clash.returncode == 1 and "already published with other presets" in clash.stderr
    assert publish_presets(clone, presets_file(tmp_path, 3)).returncode == 0
    assert '"revision": 3' in branch_file(clone, "presets.json")


def test_both_channels_write_presets(repos: tuple[Path, Path], built: tuple[Path, Path], tmp_path: Path) -> None:
    origin, clone = repos
    published = commit_files(origin, ROOT, None, "refs/heads/gh-pages")
    before = git(origin, "ls-tree", "-r", published)
    presets = str(presets_file(tmp_path, 4))
    spec = spec_files(tmp_path, '{"zora_version": "2.0.2"}\n')[0]
    done = run_step(clone, "--channel", "test", *channel_build(tmp_path), spec, presets)
    assert done.returncode == 0, done.stderr
    assert '"revision": 4' in branch_file(clone, "test/presets.json")
    assert outside_test(clone) == before
    environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    regular = subprocess.run(["sh", str(SCRIPT), str(clone), *map(str, built), *spec_files(tmp_path, "{}\n"), presets],
                             capture_output=True, text=True, check=False, env=environment)
    assert regular.returncode == 0, regular.stderr
    assert '"revision": 4' in branch_file(clone, "presets.json")


def test_publish_site_passes_the_presets() -> None:
    publish_site = (REPO / "scripts" / "publish_site.sh").read_text()
    assert "presets=docs/flags-api/presets.json" in publish_site
    assert publish_site.count('"$repo/$presets"') == 3          # both channels and --presets
    assert "python3 scripts/flags_api.py --check" in publish_site


# --- --archive VERSION: a release kept at its own address, https://zora.gg/VERSION/ ---------------------------

OLD_PAGE = "zora-2.0.0-2026-11-08-78ee155.html"


def publish_two_releases(origin: Path) -> str:
    """2.0.0 published with its guide, then 2.0.1 over it (its dated copy stays): origin's gh-pages."""
    first = commit_files(origin, {"index.html": "page 2.0.0\n", OLD_PAGE: "page 2.0.0\n", ".nojekyll": "",
                                  "archipelago-guide.html": "guide 2.0.0\n", "CNAME": "zora.gg"},
                         None, "refs/heads/gh-pages")
    return commit_files(origin, {"index.html": "page 2.0.1\n", OLD_PAGE: "page 2.0.0\n", ".nojekyll": "",
                                 "zora-2.0.1-2026-11-18-73a591d.html": "page 2.0.1\n",
                                 "archipelago-guide.html": "guide 2.0.1\n", "CNAME": "zora.gg"},
                        first, "refs/heads/gh-pages")


def archive(clone: Path, version: str) -> subprocess.CompletedProcess[str]:
    environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    return subprocess.run(["sh", str(SCRIPT), "--archive", str(clone), version], capture_output=True, text=True,
                          check=False, env=environment)


def outside(clone: Path, ref: str, folder: str) -> list[str]:
    return [line for line in git(clone, "ls-tree", "-r", ref).splitlines() if f"\t{folder}/" not in line]


def test_archive_keeps_the_release_page_and_its_own_guide(repos: tuple[Path, Path]) -> None:
    """VERSION/ holds the root's dated page, as published, and the guide published with it (not today's);
    nothing else changes, and archiving again commits nothing."""
    origin, clone = repos
    latest = publish_two_releases(origin)
    done = archive(clone, "2.0.0")
    assert done.returncode == 0, done.stderr
    assert git(clone, "rev-parse", "refs/heads/gh-pages^") == latest
    assert branch_file(clone, "2.0.0/index.html") == "page 2.0.0"
    assert git(clone, "rev-parse", "refs/heads/gh-pages:2.0.0/index.html") == git(origin, "rev-parse",
                                                                                  f"{latest}:{OLD_PAGE}")
    assert branch_file(clone, "2.0.0/archipelago-guide.html") == "guide 2.0.0"
    assert outside(clone, "refs/heads/gh-pages", "2.0.0") == outside(origin, latest, "2.0.0")
    assert git(clone, "log", "-1", "--format=%s", "refs/heads/gh-pages") == f"Archive 2.0.0: {OLD_PAGE}"
    assert archive(clone, "2.0.0").stdout.strip().endswith("nothing to commit")


@pytest.mark.parametrize(("version", "message"), [
    ("1.9.9", "found: none"),
    ("../x", "is not a version"),
    ("test", "is not a version"),
])
def test_archive_refuses_a_version_it_cannot_keep(repos: tuple[Path, Path], version: str, message: str) -> None:
    origin, clone = repos
    publish_two_releases(origin)
    done = archive(clone, version)
    assert done.returncode != 0 and message in done.stderr
    assert git(clone, "branch", "--list", "gh-pages") == ""                 # nothing committed


def test_archive_refuses_two_pages_of_a_version(repos: tuple[Path, Path]) -> None:
    origin, clone = repos
    latest = publish_two_releases(origin)
    tree = git(origin, "ls-tree", latest)
    extra = git(origin, "hash-object", "-w", "--stdin", stdin="another 2.0.0\n")
    second = git(origin, "mktree", stdin=tree + f"\n100644 blob {extra}\tzora-2.0.0-2026-11-09-abc1234.html\n")
    git(origin, "update-ref", "refs/heads/gh-pages", git(origin, "commit-tree", second, "-p", latest, "-m", "two"))
    done = archive(clone, "2.0.0")
    assert done.returncode == 1 and "exactly one" in done.stderr


def test_archive_never_changes_a_published_folder(repos: tuple[Path, Path]) -> None:
    origin, clone = repos
    latest = publish_two_releases(origin)
    page = git(origin, "hash-object", "-w", "--stdin", stdin="something else\n")
    folder = git(origin, "mktree", stdin=f"100644 blob {page}\tindex.html\n")
    tree = git(origin, "mktree", stdin=git(origin, "ls-tree", latest) + f"\n040000 tree {folder}\t2.0.0\n")
    git(origin, "update-ref", "refs/heads/gh-pages", git(origin, "commit-tree", tree, "-p", latest, "-m", "folder"))
    done = archive(clone, "2.0.0")
    assert done.returncode == 1 and "an archive never changes" in done.stderr


def test_archive_is_refused_without_the_root_cname(repos: tuple[Path, Path]) -> None:
    origin, clone = repos
    commit_files(origin, {"index.html": "page 2.0.0\n", OLD_PAGE: "page 2.0.0\n", "archipelago-guide.html": "g\n"},
                 None, "refs/heads/gh-pages")
    done = archive(clone, "2.0.0")
    assert done.returncode == 1 and "CNAME" in done.stderr


def test_publish_site_passes_the_archive() -> None:
    publish_site = (REPO / "scripts" / "publish_site.sh").read_text()
    assert 'sh scripts/gh_pages_commit.sh --archive "$target" "$version"' in publish_site
