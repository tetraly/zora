"""The output comparison's inputs (owner ruling, 2026-11-07; docs/reports/quick-check-speed.md option A):
the repository files whose change could make the comparison's verdict anything but "identical", worked
out from scripts/output_hash.py's code, so the quick check can skip the comparison for a change that
touches none of them.

    python3 scripts/output_inputs.py                    list the inputs, one path a line
    python3 scripts/output_inputs.py --check PATH ...   which of PATHS are inputs (exit 1 if none)

scripts/compare_revision.py hashes two revisions with this checkout's output_hash.py: everything the
hashing workers import comes from the hashed revision's own files (output_hash.py --code), everything
else (the script, the matrix's cases) from this checkout, the same for both sides. So the inputs are:
- the generation the workers run: the modules output_hash.py's worker functions import (every function
  but CASE_FUNCTIONS and NOT_HASHING), every repository module those import at any depth, and every file
  in the top-level package folder of each module reached, for the package data it reads through
  importlib.resources (zora/ and zora_export/ today);
- the comparison itself: STARTS, and the files of the modules CASE_FUNCTIONS import (the matrix's cases:
  a changed case list is hashed on both sides, but the change still runs the comparison).

Files git does not track (the base ROM, private/) are no commit's change; the hash cache's key covers
them. tests/test_output_inputs.py runs output_hash.py's own jobs with an audit hook and fails if a worker
opens a repository file outside this list.
"""
from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from functools import cache
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUTPUT_HASH = "scripts/output_hash.py"
STARTS = (OUTPUT_HASH, "scripts/compare_revision.py", "scripts/output_inputs.py")
CASE_FUNCTIONS = ("matrix_jobs",)       # output_hash.py's: the matrix's cases, in this checkout's main process
NOT_HASHING = ("main",)                 # output_hash.py's: arguments and progress, in the main process
IGNORED = ("temp/",)


@cache
def tracked_files() -> frozenset[str]:
    listed = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                            capture_output=True, check=True).stdout.decode().split("\0")
    return frozenset(name for name in listed if name and not name.startswith(IGNORED))


def module_file(name: str) -> Path | None:
    """The repository file of dotted module NAME, or None (the standard library, an installed package)."""
    parts = name.split(".")
    for candidate in (REPO.joinpath(*parts).with_suffix(".py"), REPO.joinpath(*parts, "__init__.py")):
        if candidate.is_file():
            return candidate
    return None


def imported_names(nodes: list[ast.AST], path: Path) -> set[str]:
    """Every module name an import among NODES (and inside them) could load, with the packages on the way."""
    package = list(path.relative_to(REPO).parent.parts)
    found: set[str] = set()
    for node in (inner for outer in nodes for inner in ast.walk(outer)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                anchor = package[:len(package) - node.level + 1]
                base = ".".join([*anchor, *([node.module] if node.module else [])])
            else:
                base = node.module or ""
            found.add(base)
            found.update(f"{base}.{alias.name}" for alias in node.names)     # `from package import module`
    return {".".join(name.split(".")[:end]) for name in found if name for end in range(1, name.count(".") + 2)}


def _functions(tree: ast.Module, names: tuple[str, ...], wanted: bool) -> list[ast.AST]:
    return [node for node in tree.body
            if isinstance(node, ast.FunctionDef) and (node.name in names) == wanted]


def _closure(names: set[str]) -> set[Path]:
    """The repository modules NAMES load, with everything they import, at any depth."""
    queue = [path for name in names if (path := module_file(name))]
    seen: set[Path] = set()
    while queue:
        path = queue.pop()
        if path in seen:
            continue
        seen.add(path)
        tree = ast.parse(path.read_text(), str(path))
        queue.extend(module for name in imported_names([tree], path) if (module := module_file(name)))
    return seen


@cache
def output_inputs() -> tuple[str, ...]:
    """Every tracked file whose change runs the comparison (the module docstring), sorted."""
    script = REPO / OUTPUT_HASH
    tree = ast.parse(script.read_text(), str(script))
    workers = _functions(tree, CASE_FUNCTIONS + NOT_HASHING, wanted=False)
    generation = _closure(imported_names(workers, script))
    packages = {path.relative_to(REPO).parts[0] for path in generation}
    inputs = {file for file in tracked_files() if file.split("/")[0] in packages}
    inputs |= {path.relative_to(REPO).as_posix() for path in generation}
    cases = imported_names(_functions(tree, CASE_FUNCTIONS, wanted=True), script)
    inputs |= {path.relative_to(REPO).as_posix() for name in cases if (path := module_file(name))}
    return tuple(sorted(inputs | set(STARTS)))


def output_inputs_among(paths: list[str]) -> list[str]:
    """The PATHS whose change runs the comparison; a deleted file of an input package counts too."""
    inputs = set(output_inputs())
    packages = {name.split("/")[0] for name in inputs if not name.startswith(("scripts/", "tests/"))}
    return [path for path in paths if path in inputs or path.split("/")[0] in packages]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", nargs="+", metavar="PATH", help="which of these paths are inputs")
    args = parser.parse_args()
    if args.check:
        among = output_inputs_among(args.check)
        print("\n".join(among) if among else "none of these is an output input")
        return 0 if among else 1
    print("\n".join(output_inputs()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
