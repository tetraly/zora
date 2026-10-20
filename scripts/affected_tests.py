"""The tests most likely affected by a change (AGENTS.md "Verification"): the small selection the
quick check (`sh scripts/verify.sh`) runs before a commit, and, for a session tracing a failure,
the slow or fast tests a change most likely affects.

    python3 scripts/affected_tests.py               the slow tests the working tree's changes against
                                                    HEAD (tracked and untracked files) affect
    python3 scripts/affected_tests.py PATH ...      ... these files' changes only (in a shared
                                                    checkout, name your own; others' edits count
                                                    otherwise)
    python3 scripts/affected_tests.py --base REV    ... the changes since REV, committed or not
    python3 scripts/affected_tests.py --fast        the fast tests (not marked slow) instead, by file
    python3 scripts/affected_tests.py --ids         only the selection, one pytest argument a line
                                                    ("tests" for every test; nothing for none)
    python3 scripts/affected_tests.py --quick       the quick check's selection: the fast tests of the
                                                    files most likely affected, capped (below)

A test is likely affected when its file was changed, imports a changed module directly, or names a
changed file's path. A changed file that is not Python (patch sources, data) counts as the modules
that name it. It prints those tests, the pytest command that runs them, the test files a change
reaches only through imports (left to the full tier, scripts/verify_full.sh), and any changed file
no test reaches. A change to the test-wide setup (tests/conftest.py) selects every test. A
Markdown file counts only where a test's code names it, not a comment or docstring citing it.
Slow tests are marked `slow` (a decorator, or the module's `pytestmark`).

Static and quick (no collection): parametrized tests are listed once, by function.

The quick check's selection (--quick; owner decision, 2026-10-16: commit after quick checks, test
in batches) is the fast-test files picked as above, but never every test for a change to the
test-wide setup, capped at QUICK_BUDGET_SECONDS of recorded test time (each test's last passing
duration, temp/jobs/test-durations.json, written by tests/progress_plugin.py; a file without a
record counts its tests at the record's median, or UNRECORDED_TEST_SECONDS while it holds too few). Changed test files come first, then the files
importing a changed module, then those naming a changed file; a file that does not fit is left to
the batch run and listed, and a smaller one after it may still fit.
"""
import argparse
import ast
import os
import subprocess
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PACKAGES = ("zora", "zora_export", "zora_measure", "zora_web", "tests")
SOURCE_FOLDERS = (*PACKAGES, "scripts")
SLOW_MARK = "slow"
TEST_WIDE = ("tests/conftest.py",)
IGNORED_FOLDERS = ("temp/",)
# The quick check's test budget, in recorded seconds of test time: at its 2 workers about a minute
# and a half of tests, which with the static checks and the output comparison keeps it within the
# owner's 3-5 minutes (measured: docs/design/test-speed.md "The quick check").
QUICK_BUDGET_SECONDS = 150.0
UNRECORDED_TEST_SECONDS = 1.0       # a test's cost while too little is recorded for a median
RECORDED_FOR_MEDIAN = 200           # fast tests recorded before their median stands in for the others


@dataclass
class TestFile:
    """A test file with tests of the kind asked for: their names, and what it imports and mentions."""
    path: str
    tests: list[str]
    imports: set[str]
    text: str
    strings: str
    reasons: list[str] = field(default_factory=list)


COPY_ADDED_SETTING = "ZORA_COPY_ADDED"      # scripts/clean_copy.py: a clean copy's --add paths
COPY_ADDED_SEPARATOR = ":"


def changed_files(base: str | None) -> list[str]:
    """The tracked files that differ from BASE (HEAD by default) and the untracked ones; in a clean
    copy without BASE, its --add paths (its one commit already holds them)."""
    if base is None and (added := os.environ.get(COPY_ADDED_SETTING)):
        return sorted(filter(None, added.split(COPY_ADDED_SEPARATOR)))
    def git(*args: str) -> list[str]:
        return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True,
                              check=True).stdout.splitlines()
    files = set(git("diff", "--name-only", base or "HEAD")) | set(git("ls-files", "--others", "--exclude-standard"))
    return sorted(name for name in files if not name.startswith(IGNORED_FOLDERS))


def module_name(path: str) -> str | None:
    """The dotted module a repo file is (a package's __init__ is the package), or None."""
    parts = Path(path).with_suffix("").parts
    if not path.endswith(".py") or not parts or parts[0] not in PACKAGES:
        return None
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def repo_modules() -> dict[str, Path]:
    modules = {}
    for package in PACKAGES:
        for path in (REPO / package).rglob("*.py"):
            name = module_name(path.relative_to(REPO).as_posix())
            if name:
                modules[name] = path
    return modules


def imported_modules(path: Path, modules: dict[str, Path]) -> set[str]:
    """The repo modules PATH imports, with the packages each import runs on the way."""
    tree = ast.parse(path.read_text(), str(path))
    own = module_name(path.relative_to(REPO).as_posix()) or ""
    package = own if path.name == "__init__.py" else own.rpartition(".")[0]
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:                                  # relative, inside zora/
                anchor = package.split(".")[:len(package.split(".")) - node.level + 1]
                base = ".".join([*anchor, *([node.module] if node.module else [])])
            else:
                base = node.module or ""
            found.add(base)
            found.update(f"{base}.{alias.name}" for alias in node.names)  # `from package import module`
    with_parents = {".".join(name.split(".")[:end]) for name in found for end in range(1, name.count(".") + 2)}
    return with_parents & modules.keys()


def is_slow_mark(node: ast.expr) -> bool:
    """`pytest.mark.slow` (or a list holding it, as a module's pytestmark may be)."""
    if isinstance(node, (ast.List, ast.Tuple)):
        return any(map(is_slow_mark, node.elts))
    return isinstance(node, ast.Attribute) and node.attr == SLOW_MARK and ast.unparse(node.value) == "pytest.mark"


def marked_tests(tree: ast.Module, slow: bool) -> list[str]:
    """The test functions marked slow (or, SLOW false, the others), as pytest names them
    (Class::test for a class's)."""
    whole_module = any(isinstance(node, ast.Assign) and is_slow_mark(node.value)
                       and any(ast.unparse(target) == "pytestmark" for target in node.targets) for node in tree.body)

    def tests_in(body: list[ast.stmt], prefix: str, marked: bool) -> Iterator[str]:
        for node in body:
            node_marked = marked or any(map(is_slow_mark, getattr(node, "decorator_list", [])))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                if node_marked == slow:
                    yield prefix + node.name
            elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                yield from tests_in(node.body, f"{prefix}{node.name}::", node_marked)
    return list(tests_in(tree.body, "", whole_module))


def slow_tests(tree: ast.Module) -> list[str]:
    return marked_tests(tree, slow=True)


def test_files(modules: dict[str, Path], slow: bool) -> list[TestFile]:
    """The test files holding slow tests (or, SLOW false, fast ones)."""
    files = []
    for path in sorted((REPO / "tests").glob("test_*.py")):
        text = path.read_text()
        if slow and SLOW_MARK not in text:
            continue
        tree = ast.parse(text, str(path))
        names = marked_tests(tree, slow)
        if names:
            files.append(TestFile(path.relative_to(REPO).as_posix(), names, imported_modules(path, modules), text,
                                  "\n".join(code_strings(tree))))
    return files


def closure(start: Iterable[str], imports: dict[str, set[str]]) -> set[str]:
    reached, todo = set(start), list(start)
    while todo:
        for name in imports.get(todo.pop(), ()):
            if name not in reached:
                reached.add(name)
                todo.append(name)
    return reached


def code_strings(tree: ast.Module) -> list[str]:
    """The string constants of a module's code: not its docstrings (comments are not in the tree)."""
    docstrings = {id(node.body[0].value) for node in ast.walk(tree)
                  if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                  and node.body and isinstance(node.body[0], ast.Expr)}
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings]


def readers(path: str) -> list[str]:
    """The repo modules and scripts whose code names a file that is not Python, or its folder below
    the top level (asm/fp-stats-01/, say): its name in a string, not a comment or docstring."""
    names = {Path(path).name}
    if len(Path(path).parts) > 2:
        names.add(Path(path).parent.name)
    found = []
    for folder in SOURCE_FOLDERS:
        for source in (REPO / folder).rglob("*.py"):
            relative = source.relative_to(REPO).as_posix()
            if relative.startswith("tests/") or source == Path(__file__).resolve():
                continue
            if any(name in text for text in code_strings(ast.parse(source.read_text(), str(source))) for name in names):
                found.append(relative)
    return sorted(found)


@dataclass
class Selection:
    """What a change selects: the tests it most likely affects, the files it reaches only through
    imports, and the changed files no test reaches."""
    changed: list[str]
    test_wide: list[str]
    direct: list[TestFile]
    indirect: list[TestFile]
    unreached: list[str]


def select(changed: list[str], slow: bool) -> Selection:
    """The matching (module docstring) of CHANGED against the slow test files (or the fast ones)."""
    modules = repo_modules()
    imports = {name: imported_modules(path, modules) for name, path in modules.items()}
    files = test_files(modules, slow)
    reachable = {test.path: closure(test.imports, imports) for test in files}
    test_wide = [path for path in changed if path in TEST_WIDE]
    unreached, indirect = [], set()
    for path in changed:
        if path in test_wide:
            continue
        module = module_name(path)
        if module is None and not path.endswith(".py"):
            stand_ins = readers(path)
        else:
            stand_ins = [path]                              # a module, or a script tests name by path
        stand_in_modules = {module_name(source) for source in stand_ins} - {None}
        # a test may name the file, its folder below the top level, or a script that reads it
        mentions = [path, *(source for source in stand_ins if module_name(source) is None)]
        if len(Path(path).parts) > 2:
            mentions.append(Path(path).parent.as_posix())
        label = path if stand_ins in ([], [path]) else f"{path} (read by {', '.join(stand_ins[:3])})"
        reached = False
        for test in files:
            if test.path == path:
                test.reasons.append("changed")
            elif test.imports & stand_in_modules:
                test.reasons.append(f"imports {label}")
            elif any(name in (test.strings if path.endswith(".md") else test.text) for name in mentions):
                test.reasons.append(f"names {label}")
            elif reachable[test.path] & stand_in_modules:
                indirect.add(test.path)
            else:
                continue
            reached = True
        if not reached:
            unreached.append(path)
    direct = files if test_wide else [test for test in files if test.reasons]
    chosen = {test.path for test in direct}
    return Selection(changed, test_wide, direct, [test for test in files if test.path in indirect - chosen],
                     unreached)


def pytest_selection(selection: Selection, slow: bool) -> list[str]:
    """The pytest arguments that run the selection: the slow tests by name, the fast ones by file
    (verify's -m leaves their slow tests out); "tests" for every test."""
    if selection.test_wide:
        return ["tests"]
    if slow:
        return [f"{test.path}::{name}" for test in selection.direct for name in test.tests]
    return [test.path for test in selection.direct]


def report(selection: Selection, slow: bool) -> None:
    kind = "Slow tests" if slow else "Fast tests"
    wide = f" (test-wide setup: {', '.join(selection.test_wide)})" if selection.test_wide else ""
    print(f"Changed: {len(selection.changed)} files{wide}")
    if selection.direct:
        count = sum(len(test.tests) for test in selection.direct)
        print(f"\n{kind} most likely affected: {count} in {len(selection.direct)} files")
        for test in selection.direct:
            why = "test-wide setup" if selection.test_wide else "; ".join(dict.fromkeys(test.reasons))
            print(f"  {test.path} ({why})")
            for name in test.tests if slow else ():
                print(f"    {name}")
        arguments = " ".join(pytest_selection(selection, slow))
        if slow:
            print("\nRun them (they take the suite lock; tests/conftest.py):")
            print(f"  python3 -m pytest -q -m slow -n auto {arguments}")
        else:
            print("\nRun them (at most 2 workers, beside a held suite lock):")
            print(f'  python3 -m pytest -q -m "not slow and not full_tier" -n 2 {arguments}')
    else:
        print(f"\nNo {kind.lower()[:-1]} imports or names a changed file.")
    if selection.indirect:
        count = sum(len(test.tests) for test in selection.indirect)
        tier = "the full tier" if slow else "verify"
        print(f"\nReached only through imports, left to {tier}: {count} {kind.lower()} "
              f"in {len(selection.indirect)} files")
        for test in selection.indirect:
            print(f"  {test.path}")
    if selection.unreached:
        print(f"\nNo {kind.lower()[:-1]} reaches these changed files:")
        for path in selection.unreached:
            print(f"  {path}")


@dataclass
class QuickSelection:
    """The quick check's test files, each with its expected seconds, and those left to the batch."""
    chosen: list[tuple[str, float]]
    left: list[tuple[str, float]]
    test_wide: list[str]
    budget: float

    @property
    def seconds(self) -> float:
        return sum(cost for _, cost in self.chosen)


def file_costs(files: list[TestFile], record: dict[str, list[object]]) -> dict[str, float]:
    """Each file's expected seconds for its fast tests: the recorded ones' durations, or, for a file
    with nothing recorded, its tests at the record's median."""
    fast = [float(str(seconds)) for seconds, heavy in record.values() if not heavy]
    typical = sorted(fast)[len(fast) // 2] if len(fast) >= RECORDED_FOR_MEDIAN else UNRECORDED_TEST_SECONDS
    costs = {}
    for test in files:
        recorded = [float(str(seconds)) for test_id, (seconds, heavy) in record.items()
                    if test_id.startswith(f"{test.path}::") and not heavy]
        costs[test.path] = sum(recorded) if recorded else len(test.tests) * typical
    return costs


def quick_priority(test: TestFile) -> int:
    """Changed test files first, then importers of a changed module, then those naming a file."""
    if "changed" in test.reasons:
        return 0
    return 1 if any(reason.startswith("imports") for reason in test.reasons) else 2


def quick_select(changed: list[str], record: dict[str, list[object]],
                 budget: float = QUICK_BUDGET_SECONDS) -> QuickSelection:
    """The quick check's selection (module docstring): the direct fast-test files, capped at BUDGET."""
    test_wide = [path for path in changed if path in TEST_WIDE]
    selection = select([path for path in changed if path not in TEST_WIDE], slow=False)
    costs = file_costs(selection.direct, record)
    chosen, left, spent = [], [], 0.0
    for test in sorted(selection.direct, key=quick_priority):
        cost = costs[test.path]
        if spent + cost <= budget:
            chosen.append((test.path, cost))
            spent += cost
        else:
            left.append((test.path, cost))
    return QuickSelection(chosen, left, test_wide, budget)


def quick_report(quick: QuickSelection) -> None:
    print(f"Quick check: {len(quick.chosen)} test files, about {quick.seconds:.0f} s of recorded test time "
          f"(cap {quick.budget:.0f} s)")
    for path, cost in quick.chosen:
        print(f"  {path} ({cost:.1f} s)")
    if quick.left:
        print(f"Over the cap, left to the batch run: {len(quick.left)} files")
        for path, cost in quick.left:
            print(f"  {path} ({cost:.1f} s)")
    if quick.test_wide:
        print(f"The test-wide setup changed ({', '.join(quick.test_wide)}): every test runs in the batch run")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("paths", nargs="*", help="the changed files (default: the working tree's changes)")
    parser.add_argument("--base", help="compare with this revision instead of HEAD")
    parser.add_argument("--fast", action="store_true", help="the fast tests (not marked slow) instead, by file")
    parser.add_argument("--ids", action="store_true", help="print only the pytest selection, one argument a line")
    parser.add_argument("--quick", action="store_true", help="the quick check's capped selection of fast tests")
    parser.add_argument("--budget", type=float, default=QUICK_BUDGET_SECONDS,
                        help="--quick's cap, in recorded seconds of test time")
    arguments = parser.parse_args()
    slow = not arguments.fast
    changed = sorted(set(arguments.paths)) if arguments.paths else changed_files(arguments.base)
    if not changed:
        if not arguments.ids:
            print("No changes: no test to run.")
        return 0
    if arguments.quick:
        sys.path.insert(0, str(REPO))
        from zora_measure.progress import read_durations
        quick = quick_select(changed, read_durations(), arguments.budget)
        if arguments.ids:
            for path, _ in quick.chosen:
                print(path)
        else:
            quick_report(quick)
        return 0
    selection = select(changed, slow)
    if arguments.ids:
        for argument in pytest_selection(selection, slow):
            print(argument)
    else:
        report(selection, slow)
    return 0


if __name__ == "__main__":
    sys.exit(main())
