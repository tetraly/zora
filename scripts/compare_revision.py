"""Compare this checkout's output with revision REV's: the 20-seed hashes and the ROM matrix
(scripts/output_hash.py, the same script and inputs for both). scripts/verify.sh REV runs it.

    python3 scripts/compare_revision.py REV [--seeds N] [--matrix-jobs N] [--workers N]
                                            [--head-hashes FILE] [--no-lock]
    python3 scripts/compare_revision.py REV --resolve-only

REV is resolved in the source checkout: this one, or, in a clean copy (scripts/clean_copy.py),
the checkout the copy was made from (ZORA_SOURCE_REPO, which the copy's verify.env names). A
copy's own repository holds one commit, the copied tree, so REV must never be looked up there.
REV "parent" is the commit a change sits on: in a clean copy the commit it was made from
(ZORA_COPY_REVISION), here HEAD. scripts/verify.sh compares with it every time.

REV's committed files are exported into temp/verify/base with the base ROM and the private
level-encoding module beside them, as a checkout has them, and output_hash.py hashes them
with --code. --head-hashes reuses this checkout's 20-seed hashes from a run already made.

REV's hashes are cached in the source checkout's temp/verify/base-cache/
(docs/design/test-speed.md 3.2). The key is everything they depend on (base_hash_key_parts:
REV's tree, this checkout's output_hash.py and matrix cases, the seed count, the base ROM, the
private module and the interpreter), so a change to any of them hashes REV afresh. This
checkout's own hashes are stored under the same key for its working tree (the tree a commit of
every file here would have; `git write-tree` from a private index), when the tree did not change
while they were made: after a commit of exactly what was checked, the next check finds its
parent's hashes already made.

It takes the suite lock (its hashing runs use every core) unless --no-lock: the quick check
(scripts/verify.sh) runs it with --no-lock --workers 2, beside any held lock.

Exit status: 0 identical, 1 the output differs, 2 no comparison was made (REV unknown, or
either side's output could not be produced). Never "identical" without both sides hashed.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
from contextlib import nullcontext
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tests.suite_lock import suite_lock  # noqa: E402 - the path above finds this checkout's tests

OUT = REPO / "temp" / "verify"
BASE_ROM = REPO / "Legend of Zelda, The (USA).nes"
PRIVATE_MODULE = Path("private") / "level_encoding"
SOURCE_REPO_SETTING = "ZORA_SOURCE_REPO"
COPY_REVISION_SETTING = "ZORA_COPY_REVISION"    # scripts/clean_copy.py
PARENT = "parent"
OUTPUT_HASH = REPO / "scripts" / "output_hash.py"
CACHE_FOLDER = Path("temp") / "verify" / "base-cache"     # in the source checkout
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


def parent_revision() -> str:
    """The commit a change sits on: a clean copy's own revision, else this checkout's HEAD."""
    return os.environ.get(COPY_REVISION_SETTING) or "HEAD"


def resolve(rev: str) -> str:
    """REV's commit in the source checkout, or NotCompared."""
    if rev == PARENT:
        rev = parent_revision()
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


def _git_output(*args: str) -> str:
    return subprocess.run(["git", "-C", str(source_repo()), *args], capture_output=True, text=True, check=True,
                          env=_git_environment()).stdout.strip()


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "absent"


def _folder_digest(folder: Path) -> str:
    """Every file under FOLDER (its path and bytes), caches aside."""
    if not folder.is_dir():
        return "absent"
    digest = hashlib.sha256()
    for path in sorted(folder.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            digest.update(str(path.relative_to(folder)).encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def _matrix_cases() -> str:
    """This checkout's matrix inputs, as output_hash.py reads them (its cases, not REV's)."""
    spec = importlib.util.spec_from_file_location("output_hash_for_key", OUTPUT_HASH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return json.dumps(module.matrix_jobs())


def working_tree() -> str | None:
    """The tree a commit of every file in this checkout would have (tracked and untracked, ignored
    files aside), from a private copy of the index, so the shared one is untouched; None when git
    cannot say."""
    index = OUT / f"working-tree.{os.getpid()}.index"
    OUT.mkdir(parents=True, exist_ok=True)
    git_dir = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--absolute-git-dir"], capture_output=True,
                             text=True, check=False, env=_git_environment()).stdout.strip()
    try:
        if git_dir and (Path(git_dir) / "index").is_file():
            shutil.copyfile(Path(git_dir) / "index", index)    # its file stats spare rehashing every file
        environment = {**_git_environment(), "GIT_INDEX_FILE": str(index)}
        for command in (["add", "--all"], ["write-tree"]):
            done = subprocess.run(["git", "-C", str(REPO), *command], capture_output=True, text=True, check=False,
                                  env=environment)
            if done.returncode != 0:
                return None
        return done.stdout.strip() or None
    finally:
        index.unlink(missing_ok=True)


def base_hash_key_parts(commit: str, seeds: int, matrix_jobs: int | None) -> dict[str, str]:
    """Everything REV's hashes depend on: a cached result is reused only when all of it matches."""
    return tree_hash_key_parts(_git_output("rev-parse", f"{commit}^{{tree}}"), seeds, matrix_jobs)


def tree_hash_key_parts(tree: str, seeds: int, matrix_jobs: int | None) -> dict[str, str]:
    """base_hash_key_parts for a tree: a commit's, or this checkout's working tree."""
    return {
        "revision tree": tree,
        "output_hash.py": _file_digest(OUTPUT_HASH),
        "matrix cases": hashlib.sha256(_matrix_cases().encode()).hexdigest(),
        "seeds": str(seeds),
        "matrix jobs": str(matrix_jobs),
        "base ROM": _file_digest(BASE_ROM),
        "private module": _folder_digest(REPO / PRIVATE_MODULE),
        "interpreter": sys.version,
    }


def cache_path(parts: dict[str, str]) -> Path:
    key = hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()
    return source_repo() / CACHE_FOLDER / f"{key}.json"


def cached_base(parts: dict[str, str]) -> dict[str, str] | None:
    """REV's two hash files (seeds, matrix) from an earlier run with the same key, or None."""
    path = cache_path(parts)
    if not path.is_file():
        return None
    stored = json.loads(path.read_text())
    return stored["hashes"] if stored.get("parts") == parts else None


def store_base(parts: dict[str, str], hashes: dict[str, str]) -> None:
    path = cache_path(parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f"{path.name}.{os.getpid()}.part")
    partial.write_text(json.dumps({"parts": parts, "hashes": hashes}))
    os.replace(partial, path)                   # concurrent runs: whole files only


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
    worktree_before = working_tree()
    common = [*(["--workers", str(workers)] if workers else [])]
    matrix = ["--matrix", *(["--matrix-jobs", str(matrix_jobs)] if matrix_jobs else []), *common]
    seed_options = ["--seeds", str(seeds), *common]
    base_files = {"seeds": OUT / "base.json", "matrix": OUT / "base-matrix.json"}
    parts = base_hash_key_parts(commit, seeds, matrix_jobs)
    if (cached := cached_base(parts)) is not None:
        print(f"== seeds and matrix at {rev} ({commit[:12]}): from the cache ({cache_path(parts).name[:12]})",
              flush=True)
        OUT.mkdir(parents=True, exist_ok=True)
        for name, path in base_files.items():
            path.write_text(cached[name])
    else:
        base_tree = OUT / "base"
        export(commit, base_tree)
        try:
            hash_run(f"seeds at {rev} ({commit[:12]})", base_files["seeds"], [*seed_options, "--code", str(base_tree)])
            hash_run(f"matrix at {rev} ({commit[:12]})", base_files["matrix"], [*matrix, "--code", str(base_tree)])
        finally:
            shutil.rmtree(base_tree, ignore_errors=True)
        store_base(parts, {name: path.read_text() for name, path in base_files.items()})
    hashed_here = head_hashes is None       # both of this checkout's hash files made by this run
    if head_hashes is None:
        head_hashes = OUT / "head.json"
        hash_run("seeds, this checkout", head_hashes, seed_options)
    hash_run("matrix, this checkout", OUT / "head-matrix.json", matrix)
    if worktree_before and hashed_here and working_tree() == worktree_before:
        # This checkout's hashes, for the check whose parent is a commit of exactly these files
        store_base(tree_hash_key_parts(worktree_before, seeds, matrix_jobs),
                   {"seeds": head_hashes.read_text(), "matrix": (OUT / "head-matrix.json").read_text()})
    seeds_same = compare(f"seeds: {rev} vs this checkout", base_files["seeds"], head_hashes)
    matrix_same = compare(f"matrix: {rev} vs this checkout", base_files["matrix"], OUT / "head-matrix.json")
    return seeds_same and matrix_same


def revision_label(rev: str, commit: str) -> str:
    """How the verdict names REV: "parent" by its commit."""
    return f"{commit[:12]} (the parent)" if rev == PARENT else rev


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("rev")
    parser.add_argument("--resolve-only", action="store_true", help="only check that REV resolves")
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--matrix-jobs", type=int, help="only the first N matrix ROMs")
    parser.add_argument("--workers", type=int, help="processes per hashing run (default one per core)")
    parser.add_argument("--head-hashes", type=Path, help="this checkout's seed hashes, already made")
    parser.add_argument("--no-lock", action="store_true",
                        help="take no suite lock (the quick check, with --workers 2)")
    args = parser.parse_args()
    try:
        commit = resolve(args.rev)
        if args.resolve_only:
            print(f"compare_revision: {args.rev} is {commit[:12]} in {source_repo()}")
            return IDENTICAL
        # Up to four hashing runs across every core: one heavy run at a time (inside verify.sh's fast
        # suite, already held); the quick check's runs, at 2 workers, take none
        with nullcontext() if args.no_lock else suite_lock(f"compare_revision.py {args.rev}"):
            same = compare_revision(args.rev, args.seeds, args.matrix_jobs, args.workers, args.head_hashes)
    except NotCompared as error:
        print(f"compare_revision: FAILED, no comparison made: {error}", file=sys.stderr)
        return NOT_COMPARED
    print(f"compare_revision: output {'identical to' if same else 'DIFFERS from'} {revision_label(args.rev, commit)}")
    return IDENTICAL if same else DIFFERENT


if __name__ == "__main__":
    sys.exit(main())
