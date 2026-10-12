"""Compare this checkout's output with revision REV's: the 20-seed hashes and the ROM matrix
(scripts/output_hash.py, the same script and inputs for both). scripts/verify.sh REV runs it.

    python3 scripts/compare_revision.py REV [--seeds N] [--matrix-jobs N] [--workers N]
                                            [--head-hashes FILE]
    python3 scripts/compare_revision.py REV --resolve-only

REV is resolved in the source checkout: this one, or, in a clean copy (scripts/clean_copy.py),
the checkout the copy was made from (ZORA_SOURCE_REPO, which the copy's verify.env names). A
copy's own repository holds one commit, the copied tree, so REV must never be looked up there.
REV's committed files are exported into temp/verify/base with the base ROM and the private
level-encoding module beside them, as a checkout has them, and output_hash.py hashes them
with --code. --head-hashes reuses this checkout's 20-seed hashes from a run already made.

Exit status: 0 identical, 1 the output differs, 2 no comparison was made (REV unknown, or
either side's output could not be produced). Never "identical" without both sides hashed.
"""
from __future__ import annotations

import argparse
import io
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tests.suite_lock import suite_lock  # noqa: E402 - the path above finds this checkout's tests

OUT = REPO / "temp" / "verify"
BASE_ROM = REPO / "Legend of Zelda, The (USA).nes"
PRIVATE_MODULE = Path("private") / "level_encoding"
SOURCE_REPO_SETTING = "ZORA_SOURCE_REPO"
OUTPUT_HASH = REPO / "scripts" / "output_hash.py"
IDENTICAL, DIFFERENT, NOT_COMPARED = 0, 1, 2
CLEAN_COPY_COMMIT = "Clean copy of "        # scripts/clean_copy.py make_repository's message


class NotCompared(RuntimeError):
    pass


def _git_environment() -> dict[str, str]:
    """Without GIT_* variables: a caller's GIT_INDEX_FILE or GIT_DIR must not steer this git."""
    return {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}


def source_repo() -> Path:
    return Path(os.environ.get(SOURCE_REPO_SETTING) or REPO)


def is_clean_copy(repo: Path) -> bool:
    """A clean copy's repository: its one commit is scripts/clean_copy.py's."""
    message = subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%s"], capture_output=True, text=True,
                             check=False, env=_git_environment()).stdout
    return message.startswith(CLEAN_COPY_COMMIT)


def resolve(rev: str) -> str:
    """REV's commit in the source checkout, or NotCompared."""
    if is_clean_copy(source_repo()):
        # Its own repository would resolve HEAD to the copied tree, a comparison with itself
        raise NotCompared(f"{source_repo()} is a clean copy and {SOURCE_REPO_SETTING} is not set: run it with "
                          "`python3 scripts/clean_copy.py run`, or rebuild the copy so its verify.env names it")
    found = subprocess.run(["git", "-C", str(source_repo()), "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}"],
                           capture_output=True, text=True, check=False, env=_git_environment())
    if found.returncode != 0 or not found.stdout.strip():
        raise NotCompared(f"revision {rev} is not a commit in {source_repo()}")
    return found.stdout.strip()


def export(commit: str, tree: Path) -> None:
    """REV's committed files, plus the base ROM and the private module this checkout has."""
    if tree.exists():
        shutil.rmtree(tree)
    tree.mkdir(parents=True)
    archive = subprocess.run(["git", "-C", str(source_repo()), "archive", "--format=tar", commit],
                             capture_output=True, check=False, env=_git_environment())
    if archive.returncode != 0:
        raise NotCompared(f"git archive {commit[:12]} failed: {archive.stderr.decode(errors='replace').strip()}")
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        tar.extractall(tree, filter="data")
    if not (tree / "zora" / "__init__.py").is_file():
        raise NotCompared(f"{commit[:12]}'s files hold no zora package")
    if BASE_ROM.exists():
        shutil.copy2(BASE_ROM, tree / BASE_ROM.name)
    if (REPO / PRIVATE_MODULE).is_dir():
        shutil.copytree(REPO / PRIVATE_MODULE, tree / PRIVATE_MODULE, ignore=shutil.ignore_patterns("__pycache__"))


def hash_run(label: str, json_path: Path, options: list[str]) -> None:
    print(f"== {label}", flush=True)
    done = subprocess.run([sys.executable, str(OUTPUT_HASH), *options, "--json", str(json_path)], cwd=REPO, check=False)
    if done.returncode != 0 or not json_path.is_file():
        raise NotCompared(f"{label}: output_hash.py failed (exit {done.returncode})")


def compare(label: str, base: Path, head: Path) -> bool:
    """True if identical; NotCompared if the two runs do not cover the same seeds or entries."""
    print(f"== {label}", flush=True)
    status = subprocess.run([sys.executable, str(OUTPUT_HASH), "--compare", str(base), str(head)],
                            cwd=REPO, check=False).returncode
    if status not in (IDENTICAL, DIFFERENT):
        raise NotCompared(f"{label}: the two runs could not be compared (exit {status})")
    return status == IDENTICAL


def compare_revision(rev: str, seeds: int, matrix_jobs: int | None, workers: int | None,
                     head_hashes: Path | None) -> bool:
    commit = resolve(rev)
    base_tree = OUT / "base"
    export(commit, base_tree)
    try:
        common = [*(["--workers", str(workers)] if workers else [])]
        matrix = ["--matrix", *(["--matrix-jobs", str(matrix_jobs)] if matrix_jobs else []), *common]
        seed_options = ["--seeds", str(seeds), *common]
        if head_hashes is None:
            head_hashes = OUT / "head.json"
            hash_run("seeds, this checkout", head_hashes, seed_options)
        hash_run(f"seeds at {rev} ({commit[:12]})", OUT / "base.json", [*seed_options, "--code", str(base_tree)])
        hash_run("matrix, this checkout", OUT / "head-matrix.json", matrix)
        hash_run(f"matrix at {rev} ({commit[:12]})", OUT / "base-matrix.json", [*matrix, "--code", str(base_tree)])
        seeds_same = compare(f"seeds: {rev} vs this checkout", OUT / "base.json", head_hashes)
        matrix_same = compare(f"matrix: {rev} vs this checkout", OUT / "base-matrix.json", OUT / "head-matrix.json")
    finally:
        shutil.rmtree(base_tree, ignore_errors=True)
    return seeds_same and matrix_same


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("rev")
    parser.add_argument("--resolve-only", action="store_true", help="only check that REV resolves")
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--matrix-jobs", type=int, help="only the first N matrix ROMs")
    parser.add_argument("--workers", type=int, help="processes per hashing run (default one per core)")
    parser.add_argument("--head-hashes", type=Path, help="this checkout's seed hashes, already made")
    args = parser.parse_args()
    try:
        if args.resolve_only:
            print(f"compare_revision: {args.rev} is {resolve(args.rev)[:12]} in {source_repo()}")
            return IDENTICAL
        # Four hashing runs across every core: one heavy run at a time (inside verify.sh, already held)
        with suite_lock(f"compare_revision.py {args.rev}"):
            same = compare_revision(args.rev, args.seeds, args.matrix_jobs, args.workers, args.head_hashes)
    except NotCompared as error:
        print(f"compare_revision: FAILED, no comparison made: {error}", file=sys.stderr)
        return NOT_COMPARED
    print(f"compare_revision: output {'identical to' if same else 'DIFFERS from'} {args.rev}")
    return IDENTICAL if same else DIFFERENT


if __name__ == "__main__":
    sys.exit(main())
