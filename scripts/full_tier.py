"""The full verification tier's stamp (docs/design/test-speed.md 3.2; AGENTS.md "Verification").

    python3 scripts/full_tier.py stamp SECONDS     scripts/verify_full.sh, after every check passed
    python3 scripts/full_tier.py last-release      the previous release's source commit, if any
    python3 scripts/full_tier.py check             whether HEAD's tree has a passing stamp

A stamp says the full tier passed on one tree: temp/verify/full-tier/<tree>.json in the source
checkout (this one, or the one a clean copy was made from: ZORA_SOURCE_REPO), so a run in a
clean copy stamps for the checkout that releases. Only a tree that is exactly a commit is
stamped: a clean copy without --add paths (scripts/clean_copy.py checks that it holds exactly
its commit's tree), or a checkout with nothing uncommitted. scripts/make_release.py refuses a
HEAD whose tree has no stamp.
"""
from __future__ import annotations

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
RELEASE_LOG = Path("release") / "published.log"


def _git(repo: Path, *args: str) -> str:
    environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True,
                          env=environment).stdout.strip()


def source_repo() -> Path:
    return Path(os.environ.get(SOURCE_REPO_SETTING) or REPO)


def stamp_path(repo: Path, tree: str) -> Path:
    return repo / STAMP_FOLDER / f"{tree}.json"


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
