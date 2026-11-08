"""Compare this checkout's output with revision REV's: the 20-seed hashes and the ROM matrix
(scripts/output_hash.py, the same script and inputs for both). scripts/verify.sh REV runs it.

    python3 scripts/compare_revision.py REV [--seeds N] [--matrix-seeds N] [--matrix-jobs N] [--workers N]
                                            [--head-hashes FILE] [--no-lock] [--skip-unchanged]
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
(scripts/verify.sh) runs it with --no-lock and --workers 8 when the lock is free, 2 when another run holds it.
--workers is the total: when REV's hashes are not cached, REV and this checkout are hashed at the same time,
each with half (owner ruling, 2026-11-07; docs/reports/quick-check-speed.md option D).

--matrix-seeds N hashes seeds 1-N of each matrix case (output_hash.py --matrix-seeds; the quick check: 2,
the batch run and --full-matrix: all 4). --skip-unchanged (the quick check) compares nothing when no file
changed since REV is an output input (scripts/output_inputs.py), and says so: "output not compared (no
output input changed)", never "identical".

The verdict, the last line: "output identical to REV", or "output DIFFERS from REV: ROMs N of M
(seeds ..., matrix ...), seed documents N of M, spoiler logs N of M", each field counted apart, so a
change to the documents and logs alone shows as ROMs 0. A matrix case REV cannot make (it needs a
ZORA flag REV lacks; output_hash.py's matrix_jobs) is new: listed and counted after REV's name in
the verdict, never compared or counted as a difference.

Exit status: 0 identical, 1 the output differs (any field), 2 no comparison was made (REV unknown, or
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
import threading
from contextlib import nullcontext
from pathlib import Path
from typing import Any

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
NOT_NEEDED_VERDICT = "compare_revision: output not compared (no output input changed)"
SCRIPTS = REPO / "scripts"
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


def _output_hash() -> Any:
    """This checkout's scripts/output_hash.py as a module (a script, not a package)."""
    spec = importlib.util.spec_from_file_location("output_hash_for_key", OUTPUT_HASH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _matrix_cases(matrix_seeds: int | None = None) -> str:
    """This checkout's matrix inputs, as output_hash.py reads them (its cases, not REV's), at matrix_seeds
    seeds a case (default all)."""
    module = _output_hash()
    return json.dumps(module.matrix_jobs(matrix_seeds or module.MATRIX_SEED_COUNT))


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


def base_hash_key_parts(commit: str, seeds: int, matrix_jobs: int | None,
                        matrix_seeds: int | None = None) -> dict[str, str]:
    """Everything REV's hashes depend on: a cached result is reused only when all of it matches."""
    return tree_hash_key_parts(_git_output("rev-parse", f"{commit}^{{tree}}"), seeds, matrix_jobs, matrix_seeds)


def tree_hash_key_parts(tree: str, seeds: int, matrix_jobs: int | None,
                        matrix_seeds: int | None = None) -> dict[str, str]:
    """base_hash_key_parts for a tree: a commit's, or this checkout's working tree. The matrix's cases
    are listed at the seed count asked for, so a 2-seed matrix never meets a 4-seed one."""
    return {
        "revision tree": tree,
        "output_hash.py": _file_digest(OUTPUT_HASH),
        "matrix cases": hashlib.sha256(_matrix_cases(matrix_seeds).encode()).hexdigest(),
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


HashRun = tuple[str, Path, list[str]]        # (label, the JSON file it writes, output_hash.py's options)


def hash_run(label: str, json_path: Path, options: list[str], prefix: str = "") -> None:
    """One output_hash.py run; with PREFIX, each line it prints carries it (two sides at once)."""
    print(f"{prefix}== {label}", flush=True)
    json_path.unlink(missing_ok=True)
    command = [sys.executable, str(OUTPUT_HASH), *options, "--json", str(json_path)]
    if prefix:
        with subprocess.Popen(command, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as run:
            assert run.stdout is not None
            for line in run.stdout:
                print(f"{prefix}{line}", end="", flush=True)
        status = run.returncode
    else:
        status = subprocess.run(command, cwd=REPO, check=False).returncode
    if status != 0 or not json_path.is_file():
        raise NotCompared(f"{label}: output_hash.py failed (exit {status})")


def hash_sides(sides: dict[str, list[HashRun]]) -> None:
    """Each side's runs in order; two sides at the same time, each line marked with its side. The first
    failure (NotCompared) is raised once both have ended."""
    if len(sides) == 1:
        for run in next(iter(sides.values())):
            hash_run(*run)
        return
    failures: list[NotCompared] = []

    def side(name: str, runs: list[HashRun]) -> None:
        try:
            for label, json_path, options in runs:
                hash_run(label, json_path, options, prefix=f"[{name}] ")
        except NotCompared as failure:
            failures.append(failure)

    threads = [threading.Thread(target=side, args=item) for item in sides.items()]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    if failures:
        raise failures[0]


def compare(label: str, base: Path, head: Path) -> bool:
    """True if identical; NotCompared if the two runs do not cover the same seeds or entries."""
    print(f"== {label}", flush=True)
    status = subprocess.run([sys.executable, str(OUTPUT_HASH), "--compare", str(base), str(head)],
                            cwd=REPO, check=False).returncode
    if status not in (IDENTICAL, DIFFERENT):
        raise NotCompared(f"{label}: the two runs could not be compared (exit {status})")
    return status == IDENTICAL


def split_workers(workers: int | None, sides: int) -> list[str]:
    """output_hash.py's --workers for each of SIDES runs at once: WORKERS in all (default one per core)."""
    total = workers or os.cpu_count() or 1
    return ["--workers", str(max(1, total // sides))]


def compare_revision(rev: str, seeds: int, matrix_jobs: int | None, workers: int | None,
                     head_hashes: Path | None, matrix_seeds: int | None = None) -> tuple[str | None, int]:
    """None if the output is identical, else field_tally's count of what differs; and the number of
    new matrix entries (cases REV cannot make), never counted as differences."""
    commit = resolve(rev)
    worktree_before = working_tree()
    base_files = {"seeds": OUT / "base.json", "matrix": OUT / "base-matrix.json"}
    parts = base_hash_key_parts(commit, seeds, matrix_jobs, matrix_seeds)
    cached = cached_base(parts)
    common = split_workers(workers, 1 if cached is not None else 2)
    matrix = ["--matrix", *(["--matrix-jobs", str(matrix_jobs)] if matrix_jobs else []),
              *(["--matrix-seeds", str(matrix_seeds)] if matrix_seeds else []), *common]
    seed_options = ["--seeds", str(seeds), *common]
    hashed_here = head_hashes is None       # both of this checkout's hash files made by this run
    head_runs: list[HashRun] = []
    if head_hashes is None:
        head_hashes = OUT / "head.json"
        head_runs.append(("seeds, this checkout", head_hashes, seed_options))
    head_runs.append(("matrix, this checkout", OUT / "head-matrix.json", matrix))
    base_tree = OUT / "base"
    if cached is not None:
        print(f"== seeds and matrix at {rev} ({commit[:12]}): from the cache ({cache_path(parts).name[:12]})",
              flush=True)
        OUT.mkdir(parents=True, exist_ok=True)
        for name, path in base_files.items():
            path.write_text(cached[name])
        hash_sides({"this checkout": head_runs})
    else:
        # Not cached: REV and this checkout at the same time, each with half the workers
        export(commit, base_tree)
        code = ["--code", str(base_tree)]
        base_runs: list[HashRun] = [(f"seeds at {rev} ({commit[:12]})", base_files["seeds"], [*seed_options, *code]),
                                    (f"matrix at {rev} ({commit[:12]})", base_files["matrix"], [*matrix, *code])]
        print(f"== {rev} ({commit[:12]}) is not cached: hashing it and this checkout at the same time", flush=True)
        try:
            hash_sides({rev: base_runs, "this checkout": head_runs})
        finally:
            shutil.rmtree(base_tree, ignore_errors=True)
        store_base(parts, {name: path.read_text() for name, path in base_files.items()})
    if worktree_before and hashed_here and working_tree() == worktree_before:
        # This checkout's hashes, for the check whose parent is a commit of exactly these files
        store_base(tree_hash_key_parts(worktree_before, seeds, matrix_jobs, matrix_seeds),
                   {"seeds": head_hashes.read_text(), "matrix": (OUT / "head-matrix.json").read_text()})
    seeds_same = compare(f"seeds: {rev} vs this checkout", base_files["seeds"], head_hashes)
    matrix_same = compare(f"matrix: {rev} vs this checkout", base_files["matrix"], OUT / "head-matrix.json")
    differences = None if seeds_same and matrix_same else \
        field_tally(base_files["seeds"], head_hashes, base_files["matrix"], OUT / "head-matrix.json")
    return differences, new_matrix_entries(base_files["matrix"], OUT / "head-matrix.json")


def _script_module(name: str) -> Any:
    """One of this checkout's scripts/ modules (scripts, not a package)."""
    spec = importlib.util.spec_from_file_location(f"{name}_for_compare", SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def changed_since(commit: str) -> list[str]:
    """The files that differ between COMMIT and this checkout: its changes against its parent (in a
    clean copy, its --add paths), and, for a COMMIT other than the parent, the commits between them."""
    changed = set(_script_module("affected_tests").changed_files(None))
    parent = resolve(PARENT)
    if commit != parent:
        changed |= set(filter(None, _git_output("diff", "--name-only", commit, parent).splitlines()))
    return sorted(changed)


def output_inputs_changed(commit: str) -> list[str]:
    """The files changed since COMMIT that are output inputs (scripts/output_inputs.py)."""
    inputs: list[str] = _script_module("output_inputs").output_inputs_among(changed_since(commit))
    return inputs


def new_matrix_entries(base_matrix: Path, head_matrix: Path) -> int:
    """How many matrix entries REV could not make (a ZORA flag it lacks): new, not compared."""
    output_hash = _output_hash()
    return len(output_hash.new_entries(json.loads(base_matrix.read_text())[output_hash.MATRIX],
                                       json.loads(head_matrix.read_text())[output_hash.MATRIX]))


def field_tally(base_seeds: Path, head_seeds: Path, base_matrix: Path, head_matrix: Path) -> str:
    """The verdict's count of what differs, each field apart: ROMs (the 20 seeds' in each mode and the
    matrix's), then the matrix's seed documents and spoiler logs. A changed document or log alone is
    not a changed ROM (a new flag listed as off changes every document and log, no ROM)."""
    seeds_base, seeds_head = json.loads(base_seeds.read_text()), json.loads(head_seeds.read_text())
    output_hash = _output_hash()
    matrix_base = json.loads(base_matrix.read_text())[output_hash.MATRIX]
    matrix_head = json.loads(head_matrix.read_text())[output_hash.MATRIX]
    seed_roms = sum(len(hashes) for hashes in seeds_head.values())
    seed_changes = sum(ours != theirs for mode, hashes in seeds_head.items()
                       for ours, theirs in zip(seeds_base[mode], hashes, strict=True))
    counts = output_hash.field_differences(matrix_base, matrix_head)
    entries = len(matrix_head) - len(output_hash.new_entries(matrix_base, matrix_head))   # new: not compared
    return (f"ROMs {seed_changes + counts['rom']} of {seed_roms + entries} "
            f"(seeds {seed_changes} of {seed_roms}, matrix {counts['rom']} of {entries}), "
            f"seed documents {counts['document']} of {entries}, spoiler logs {counts['log']} of {entries}")


def revision_label(rev: str, commit: str) -> str:
    """How the verdict names REV: "parent" by its commit."""
    return f"{commit[:12]} (the parent)" if rev == PARENT else rev


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("rev")
    parser.add_argument("--resolve-only", action="store_true", help="only check that REV resolves")
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--matrix-jobs", type=int, help="only the first N matrix ROMs")
    parser.add_argument("--matrix-seeds", type=int, help="seeds 1-N of each matrix case (default all 4)")
    parser.add_argument("--workers", type=int, help="processes in all (default one per core)")
    parser.add_argument("--skip-unchanged", action="store_true",
                        help="compare nothing when no output input changed since REV (the quick check)")
    parser.add_argument("--head-hashes", type=Path, help="this checkout's seed hashes, already made")
    parser.add_argument("--no-lock", action="store_true",
                        help="take no suite lock (the quick check: --workers 8, or 2 beside a held lock)")
    args = parser.parse_args()
    try:
        commit = resolve(args.rev)
        if args.resolve_only:
            print(f"compare_revision: {args.rev} is {commit[:12]} in {source_repo()}")
            return IDENTICAL
        if args.skip_unchanged and not (inputs := output_inputs_changed(commit)):
            print(f"compare_revision: no file changed since {revision_label(args.rev, commit)} is an output input "
                  "(scripts/output_inputs.py): nothing to compare")
            print(NOT_NEEDED_VERDICT)
            return IDENTICAL
        if args.skip_unchanged:
            shown = ", ".join(inputs[:5]) + (f" and {len(inputs) - 5} more" if len(inputs) > 5 else "")
            print(f"compare_revision: output inputs changed since {revision_label(args.rev, commit)}: {shown}")
        # Up to four hashing runs across every core: one heavy run at a time (inside verify.sh's fast
        # suite, already held); the quick check's runs, at 2 workers, take none
        with nullcontext() if args.no_lock else suite_lock(f"compare_revision.py {args.rev}"):
            differences, new = compare_revision(args.rev, args.seeds, args.matrix_jobs, args.workers,
                                                args.head_hashes, args.matrix_seeds)
    except NotCompared as error:
        print(f"compare_revision: FAILED, no comparison made: {error}", file=sys.stderr)
        return NOT_COMPARED
    added = f" ({new} new matrix entries, cases it cannot make, not compared)" if new else ""
    if differences is None:
        print(f"compare_revision: output identical to {revision_label(args.rev, commit)}{added}")
        return IDENTICAL
    print(f"compare_revision: output DIFFERS from {revision_label(args.rev, commit)}{added}: {differences}")
    return DIFFERENT


if __name__ == "__main__":
    sys.exit(main())
