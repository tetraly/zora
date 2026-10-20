"""The batch run's stamp and the release gate (docs/design/test-speed.md 3.2; AGENTS.md
"Verification"; docs/releasing.md).

    python3 scripts/full_tier.py stamp SECONDS     scripts/verify_full.sh, after every check passed
    python3 scripts/full_tier.py quick-stamp       scripts/verify.sh, after a quick check passed
    python3 scripts/full_tier.py last-release      the previous release's source commit, if any
    python3 scripts/full_tier.py check             whether HEAD's tree has a passing stamp
    python3 scripts/full_tier.py release-check     whether HEAD may be released (below)

A stamp says the full tier passed on one tree: temp/verify/full-tier/<tree>.json in the source
checkout (this one, or the one a clean copy was made from: ZORA_SOURCE_REPO), so a run in a
clean copy stamps for the checkout that releases. Only a tree that is exactly a commit is
stamped: a clean copy without --add paths (scripts/clean_copy.py checks that it holds exactly
its commit's tree), or a checkout with nothing uncommitted. A quick check that passes on such a
tree records it the same way, in temp/verify/quick-check/.

The release gate (release-check, which scripts/make_release.py runs; owner decision, 2026-10-16):
HEAD may be released when its tree has a stamp, or when the newest stamped commit HEAD descends
from is followed only by low-risk changes and the quick check passed on HEAD's tree. Low-risk:
Markdown files (docs and notes; a test that reads one is in the quick check's selection), and
zora/version.py when only the ZORA_VERSION string changed. Anything else since the stamp needs a
new batch run. (The docs/ folder's other files are data that tests and code read, manifests and
tables, so they are not low-risk.)
"""
from __future__ import annotations

import ast
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOURCE_REPO_SETTING = "ZORA_SOURCE_REPO"            # scripts/clean_copy.py
COPY_REVISION_SETTING = "ZORA_COPY_REVISION"
COPY_ADDED_SETTING = "ZORA_COPY_ADDED"
STAMP_FOLDER = Path("temp") / "verify" / "full-tier"
QUICK_FOLDER = Path("temp") / "verify" / "quick-check"
VERSION_FILE = "zora/version.py"
VERSION_NAME = "ZORA_VERSION"
RELEASE_LOG = Path("release") / "published.log"


def _git(repo: Path, *args: str) -> str:
    environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True,
                          env=environment).stdout.strip()


def source_repo() -> Path:
    return Path(os.environ.get(SOURCE_REPO_SETTING) or REPO)


def stamp_path(repo: Path, tree: str, folder: Path = STAMP_FOLDER) -> Path:
    return repo / folder / f"{tree}.json"


def verified_commit() -> tuple[str, str]:
    """(commit, tree) of what this run verified, or ValueError when it is not exactly a commit."""
    if _git(REPO, "status", "--porcelain"):
        raise ValueError("the verified files differ from their commit (uncommitted changes); run the full tier "
                         "in a clean copy of a commit")
    copy_revision = os.environ.get(COPY_REVISION_SETTING)
    if copy_revision:
        if os.environ.get(COPY_ADDED_SETTING):
            raise ValueError("this clean copy adds working-tree paths; commit them and run the full tier on a "
                             "copy of the commit")
        tree = _git(REPO, "rev-parse", "HEAD^{tree}")
        if tree != _git(source_repo(), "rev-parse", f"{copy_revision}^{{tree}}"):
            raise ValueError(f"this clean copy's tree is not {copy_revision[:12]}'s")
        return copy_revision, tree
    return _git(REPO, "rev-parse", "HEAD"), _git(REPO, "rev-parse", "HEAD^{tree}")


def stamp(seconds: int) -> int:
    try:
        commit, tree = verified_commit()
    except ValueError as error:
        print(f"full tier: passed, NOT stamped: {error}")
        return 0
    path = stamp_path(source_repo(), tree)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"tree": tree, "commit": commit, "seconds": seconds,
                                "finished": datetime.datetime.now().isoformat(timespec="seconds")}, indent=1))
    print(f"full tier: passed in {seconds} s; stamped {commit[:12]} (tree {tree[:12]})")
    return 0


def stamped(repo: Path, tree: str) -> bool:
    """Whether the full tier passed on TREE (scripts/make_release.py)."""
    return stamp_path(repo, tree).is_file()


def quick_stamp() -> int:
    """Record that the quick check passed on a tree that is exactly a commit; say why not otherwise."""
    try:
        commit, tree = verified_commit()
    except ValueError:
        print("quick check: passed (not recorded for the release gate: uncommitted changes here)")
        return 0
    path = stamp_path(source_repo(), tree, QUICK_FOLDER)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"tree": tree, "commit": commit,
                                "finished": datetime.datetime.now().isoformat(timespec="seconds")}, indent=1))
    print(f"quick check: passed; recorded for {commit[:12]} (tree {tree[:12]})")
    return 0


def stamped_commits(repo: Path) -> list[str]:
    """The commits of every batch-run stamp."""
    commits = []
    for path in sorted((repo / STAMP_FOLDER).glob("*.json")):
        try:
            commits.append(json.loads(path.read_text())["commit"])
        except (OSError, ValueError, KeyError):
            continue
    return commits


def newest_stamped_ancestor(repo: Path, head: str) -> str | None:
    """The stamped commit HEAD descends from with the fewest commits between them, or None."""
    found = []
    for commit in set(stamped_commits(repo)):
        ancestor = subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", commit, head],
                                  capture_output=True, check=False,
                                  env={name: value for name, value in os.environ.items()
                                       if not name.startswith("GIT_")})
        if ancestor.returncode == 0:
            found.append((int(_git(repo, "rev-list", "--count", f"{commit}..{head}")), commit))
    return min(found)[1] if found else None


def _without_version(source: str) -> str | None:
    """SOURCE's syntax tree with the ZORA_VERSION string blanked, or None when it has no such string."""
    tree = ast.parse(source)
    found = False
    for node in tree.body:
        if (isinstance(node, ast.Assign) and [ast.unparse(target) for target in node.targets] == [VERSION_NAME]
                and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            node.value.value = ""
            found = True
    return ast.dump(tree) if found else None


def only_version_changed(old: str, new: str) -> bool:
    """Whether two versions of zora/version.py differ in nothing but the ZORA_VERSION string."""
    try:
        before, after = _without_version(old), _without_version(new)
    except SyntaxError:
        return False
    return before is not None and before == after


def low_risk_reason(repo: Path, path: str, stamped_commit: str, head: str) -> str | None:
    """Why PATH's change since STAMPED_COMMIT is low-risk (the module docstring), or None."""
    if path.endswith(".md"):
        return "Markdown"
    if path == VERSION_FILE:
        try:
            old = _git(repo, "show", f"{stamped_commit}:{path}")
            new = _git(repo, "show", f"{head}:{path}")
        except subprocess.CalledProcessError:
            return None
        return "the version bump" if only_version_changed(old, new) else None
    return None


def release_check() -> int:
    """Whether HEAD may be released: its tree stamped, or the relaxation (the module docstring)."""
    repo = source_repo()
    head, tree = _git(REPO, "rev-parse", "HEAD"), _git(REPO, "rev-parse", "HEAD^{tree}")
    if stamped(repo, tree):
        print(f"release gate: HEAD's tree {tree[:12]} has a batch-run stamp")
        return 0
    base = newest_stamped_ancestor(repo, head)
    if base is None:
        print(f"release gate: NO batch-run stamp on HEAD ({head[:12]}) or any commit it descends from")
        return 1
    changed = [line for line in _git(repo, "diff", "--name-only", base, head).splitlines() if line]
    risky = [path for path in changed if low_risk_reason(repo, path, base, head) is None]
    if risky:
        print(f"release gate: changed since the stamped {base[:12]}, not low-risk (a new batch run is needed): "
              + ", ".join(risky))
        return 1
    if not stamp_path(repo, tree, QUICK_FOLDER).is_file():
        print(f"release gate: only low-risk changes since the stamped {base[:12]}, but the quick check has not "
              f"passed on HEAD ({head[:12]}): run sh scripts/verify.sh with nothing uncommitted (or in a clean copy)")
        return 1
    print(f"release gate: the stamped {base[:12]} plus only low-risk changes ("
          + "; ".join(f"{path}: {low_risk_reason(repo, path, base, head)}" for path in changed)
          + f"), and the quick check passed on HEAD ({head[:12]})")
    return 0


def last_release() -> str:
    """The source commit of the latest release (release/published.log), or "" without one."""
    log = REPO / RELEASE_LOG
    lines = [line.split() for line in log.read_text().splitlines() if line.strip() and not line.startswith("#")] \
        if log.is_file() else []
    return lines[-1][1] if lines else ""


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "stamp" and len(sys.argv) == 3:
        return stamp(int(sys.argv[2]))
    if command == "quick-stamp":
        return quick_stamp()
    if command == "release-check":
        return release_check()
    if command == "last-release":
        print(last_release())
        return 0
    if command == "check":
        tree = _git(REPO, "rev-parse", "HEAD^{tree}")
        found = stamped(source_repo(), tree)
        print(f"full tier: HEAD's tree {tree[:12]} {'has a passing stamp' if found else 'has NO stamp'}")
        return 0 if found else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
