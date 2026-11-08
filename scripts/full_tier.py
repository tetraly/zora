"""The batch run's stamp and the release gate (docs/design/test-speed.md 3.2; AGENTS.md
"Verification"; docs/releasing.md).

    python3 scripts/full_tier.py stamp SECONDS     scripts/verify_full.sh, after every check passed
    python3 scripts/full_tier.py quick-stamp [--matrix full|default|skipped]
                                                   scripts/verify.sh, after a quick check passed: with
                                                   all four matrix seeds (--full-matrix), seeds 1-2,
                                                   or no comparison (no output input changed)
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
from is followed only by low-risk changes and the quick check passed on HEAD's tree with all four
matrix seeds (`sh scripts/verify.sh --full-matrix`; owner ruling, 2026-11-07: the release check runs
them all; a plain quick check hashes seeds 1-2, or nothing for a change outside the output's
inputs, and its record does not count here). Low-risk:
Markdown files (docs and notes; a test that reads one is in the quick check's selection), and
zora/version.py when only the ZORA_VERSION string changed, and the page's hero graphic, web/zora-logo.png, when
it is still a PNG of at most HERO_GRAPHIC_LIMIT bytes (owner decision, 2026-10-30: the artist's logo replaces the
placeholder after the batch run; nothing the full tier tests reads it, the site-build test uses its own stand-in,
and the browser check of the staged page covers it), and the per-flag file, zora/flags/flags.json, when it is
still a JSON object (owner ruling, 2026-11-06: marking a flag beta or graduating it; generation never reads it,
tests/test_beta_flags.py proves ROMs do not depend on it, and that test, in the quick check's selection for a
change to the file, refuses an entry the page does not offer). Anything else since the stamp needs a
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
MATRIX_MODES = ("full", "default", "skipped")   # the quick check's matrix: all four seeds, seeds 1-2, none
FULL_MATRIX = "full"
VERSION_FILE = "zora/version.py"
HERO_GRAPHIC = "web/zora-logo.png"         # the page's hero graphic (web/index.html)
HERO_GRAPHIC_LIMIT = 1_000_000             # bytes: it is inlined into the single-file page
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
FLAGS_FILE = "zora/flags/flags.json"      # per-flag settings the page reads: beta status (zora/flags/beta.py)
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


def quick_stamp(matrix: str = FULL_MATRIX) -> int:
    """Record that the quick check passed on a tree that is exactly a commit, and with which matrix
    (MATRIX_MODES); say why not otherwise."""
    try:
        commit, tree = verified_commit()
    except ValueError:
        print("quick check: passed (not recorded for the release gate: uncommitted changes here)")
        return 0
    path = stamp_path(source_repo(), tree, QUICK_FOLDER)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"tree": tree, "commit": commit, "matrix": matrix,
                                "finished": datetime.datetime.now().isoformat(timespec="seconds")}, indent=1))
    gate = "" if matrix == FULL_MATRIX else "; not enough for the release gate: sh scripts/verify.sh --full-matrix"
    print(f"quick check: passed; recorded for {commit[:12]} (tree {tree[:12]}, matrix: {matrix}{gate})")
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
    if path == HERO_GRAPHIC:
        return "the hero graphic" if hero_graphic_ok(repo, head) else None
    if path == FLAGS_FILE:
        return "the per-flag file" if flags_file_ok(repo, head) else None
    return None


def flags_file_ok(repo: Path, head: str) -> bool:
    """HEAD's zora/flags/flags.json is a JSON object (a removed or malformed one is not)."""
    try:
        text = _git(repo, "show", f"{head}:{FLAGS_FILE}")
        return isinstance(json.loads(text), dict)
    except (subprocess.CalledProcessError, ValueError):
        return False


def hero_graphic_ok(repo: Path, head: str) -> bool:
    """HEAD's web/zora-logo.png is a PNG of at most HERO_GRAPHIC_LIMIT bytes (a removed one is not)."""
    environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    found = subprocess.run(["git", "-C", str(repo), "show", f"{head}:{HERO_GRAPHIC}"], capture_output=True,
                           check=False, env=environment)
    return (found.returncode == 0 and found.stdout.startswith(PNG_SIGNATURE)
            and len(found.stdout) <= HERO_GRAPHIC_LIMIT)


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
    quick = stamp_path(repo, tree, QUICK_FOLDER)
    if not quick.is_file():
        print(f"release gate: only low-risk changes since the stamped {base[:12]}, but the quick check has not "
              f"passed on HEAD ({head[:12]}): run sh scripts/verify.sh --full-matrix with nothing uncommitted (or "
              "in a clean copy)")
        return 1
    # A record from before 2026-11-07 has no matrix field: every quick check then hashed all four seeds
    if (matrix := json.loads(quick.read_text()).get("matrix", FULL_MATRIX)) != FULL_MATRIX:
        print(f"release gate: only low-risk changes since the stamped {base[:12]}, but the quick check on HEAD "
              f"({head[:12]}) compared {'nothing' if matrix == 'skipped' else 'seeds 1-2 of the matrix'}: run sh "
              "scripts/verify.sh --full-matrix (all four seeds) with nothing uncommitted (or in a clean copy)")
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
    if command == "quick-stamp" and len(sys.argv) == 2:
        return quick_stamp()
    if command == "quick-stamp" and len(sys.argv) == 4 and sys.argv[2] == "--matrix" and sys.argv[3] in MATRIX_MODES:
        return quick_stamp(sys.argv[3])
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
