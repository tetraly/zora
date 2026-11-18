"""The released-files check (owner decision, 2026-11-07; recommendation 4 of
docs/reports/release-process-review.md): a released test may use only repository files a release ships.

A release tree holds only what release/allowlist.txt takes. A released test that opens, imports or runs a
tracked file the allowlist leaves out passes here and fails in the release tree, as c095c13's two scripts
and 6c9c626's CSV did, each found only by a batch run or the test stage. This plugin finds that here, with
the test: scripts/verify.sh loads it (`-p tests.released_files`) for the quick check's selection and the
batch run's fast suite.

- **Released test:** a test whose file the allowlist ships.
- **What counts as using a file:** an audit hook records each repository file the test opens (`open`,
  which covers `Path.read_text`, `importlib`'s source reads and `exec_module`), each module it imports
  (`import`, resolved to its file once loaded), and the program each command it starts runs (the first two
  words of a `subprocess.Popen` command, as in `sh scripts/publish_site.sh`; a path given as an argument
  is not read by the test itself). Collection counts for the module: an import at the top of a test file
  is checked, with every module or function the test module holds.
- **A guarded test may use them:** one whose own code (its test file, at import or in the test, or a
  helper module under tests/) checked whether an unreleased file exists (`Path.exists`, `is_file`,
  `is_dir`, the `os.path` ones), or loaded a module through `pytest.importorskip`. A release tree lacks
  every unreleased file at once, so a test that skips when one is missing (`scripts/make_release.py`, say)
  skips there before it reaches the others. Files under a folder the test listed (`os.listdir`,
  `os.scandir`, `Path.glob`) count as not used: in the release tree the listing is just shorter.
  Untracked files (the base ROM, private/, temp/) are no release's concern.
- **The verdict:** an unguarded test that passed but used such a file fails, naming the files. A test
  module whose collection did fails to collect.

Limits: an import of a module some earlier test already loaded raises no `import` event, so an import
inside a test function can be missed (a top-level one never is: the module's globals are checked). A file
read by a process the test starts is not seen, only the program it runs. A test that checks one unreleased
file and then uses another without skipping counts as guarded. The check is off where there is no
release/allowlist.txt (a release tree) or no git checkout.
"""
from __future__ import annotations

import importlib
import os
import subprocess
import sys
from collections import defaultdict
from collections.abc import Callable, Generator
from functools import cache
from pathlib import Path
from types import FrameType, ModuleType
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
TESTS = REPO / "tests"
ALLOWLIST = REPO / "release" / "allowlist.txt"
EXISTENCE_CHECKS = ((os.path, ("exists", "isfile", "isdir", "lexists")), (Path, ("exists", "is_file", "is_dir")))
LISTING_EVENTS = ("os.listdir", "os.scandir", "glob.glob")
PROGRAM_WORDS = 2               # a command's program: `python3 scripts/x.py`, `sh scripts/x.sh`, or the file itself


@cache
def unreleased_files() -> frozenset[str]:
    """Tracked repository files (relative, POSIX) that release/allowlist.txt leaves out; empty when off."""
    if not ALLOWLIST.is_file():
        return frozenset()
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        # by name, not an import statement: a release tree leaves scripts/make_release.py out, and its
        # type check (verify_static.sh's mypy) must not need it
        make_release = importlib.import_module("make_release")
    except ImportError:
        return frozenset()
    finally:
        sys.path.remove(str(REPO / "scripts"))
    listed = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z", "--cached"], capture_output=True,
                            check=False).stdout.decode().split("\0")
    tracked = [name for name in listed if name]
    shipped = set(make_release.selected(tracked, make_release.read_allowlist(ALLOWLIST)).values())
    return frozenset(name for name in tracked if name not in shipped)


def released_test_file(path: Path) -> bool:
    relative = _relative(path)
    return relative is not None and relative.startswith("tests/") and relative not in unreleased_files()


def _relative(path: Any) -> str | None:
    """PATH relative to the repository, POSIX, or None when it is outside it (or not a path)."""
    if isinstance(path, int):
        return None
    try:
        resolved = Path(os.fsdecode(path)).resolve()
    except (TypeError, ValueError, OSError):
        return None
    if not resolved.is_relative_to(REPO):
        return None
    return resolved.relative_to(REPO).as_posix()


def _calling_test_files() -> set[str]:
    """The tests/ files (not this one) on the call stack: a test file and the helper modules it called."""
    found: set[str] = set()
    frame: FrameType | None = sys._getframe(2)
    while frame is not None:
        name = frame.f_code.co_filename
        if name.startswith(str(TESTS)) and name != __file__:
            found.add(name)
        frame = frame.f_back
    return found


class Recorder:
    """What the current test (or test module being collected) used, listed and imported, and every existence
    check each test file's own code made (a check at import time counts for its file, whoever imported it)."""

    def __init__(self) -> None:
        self.active = False
        self.used: set[str] = set()
        self.listed: set[str] = set()
        self.imported: set[str] = set()
        self.checks_by_file: defaultdict[str, set[str]] = defaultdict(set)

    def start(self) -> None:
        self.active = True
        self.used, self.imported, self.listed = set(), set(), set()

    def stop(self) -> None:
        self.active = False

    def audit(self, event: str, args: tuple[Any, ...]) -> None:
        if not self.active:
            return
        if event == "open":
            if (relative := _relative(args[0])) is not None:
                self.used.add(relative)
        elif event == "import":
            self.imported.add(args[0])
        elif event in LISTING_EVENTS:
            if args and (relative := _relative(args[0] if args[0] is not None else ".")) is not None:
                self.listed.add(relative)
        elif event == "subprocess.Popen":
            self._command(args)

    def _command(self, args: tuple[Any, ...]) -> None:
        """(executable, args, cwd, env): the program's words, a relative one under the command's own folder."""
        commands = args[1] if len(args) > 1 else ()
        folder = Path(os.fsdecode(args[2])) if len(args) > 2 and args[2] is not None else Path.cwd()
        words = [commands] if isinstance(commands, (str, bytes)) else list(commands or ())
        for word in words[:PROGRAM_WORDS]:
            if isinstance(word, (str, bytes, os.PathLike)) and (relative := _relative(folder / os.fsdecode(word))):
                self.used.add(relative)

    def existence_checked(self, path: Any) -> None:
        callers = _calling_test_files()
        if callers and (relative := _relative(path)) is not None:
            for caller in callers:
                self.checks_by_file[caller].add(relative)

    def problems(self, test_file: Path, module: ModuleType | None = None) -> list[str]:
        """The unreleased files an unguarded test used, sorted (the module docstring)."""
        unreleased = unreleased_files()
        if any(checked in unreleased for checked in self.checks_by_file.get(str(test_file), ())):
            return []
        files = set(self.used)
        files.update(path for name in self.imported if (path := _module_file(sys.modules.get(name))))
        if module is not None:
            files.update(path for value in vars(module).values() if (path := _defining_file(value)))
        return sorted(path for path in files if path in unreleased
                      and not any(path.startswith(f"{folder}/") or folder == "." for folder in self.listed))


def _module_file(module: ModuleType | None) -> str | None:
    file = getattr(module, "__file__", None)
    return _relative(file) if file else None


def _defining_file(value: Any) -> str | None:
    """The repository file of a module object, or of the module that defines a function or class."""
    if isinstance(value, ModuleType):
        return _module_file(value)
    name = getattr(value, "__module__", None)
    return _module_file(sys.modules.get(name)) if isinstance(name, str) else None


RECORDER = Recorder()
ON = pytest.StashKey[bool]()


def _watching(original: Callable[..., Any]) -> Callable[..., Any]:
    def watched(path: Any, *args: Any, **kwargs: Any) -> Any:
        RECORDER.existence_checked(path)
        return original(path, *args, **kwargs)
    watched.__wrapped__ = original           # type: ignore[attr-defined]
    return watched


def _import_or_skip(original: Callable[..., ModuleType]) -> Callable[..., ModuleType]:
    """pytest.importorskip: a test that loads a module through it skips where the module is missing."""
    def watched(name: str, *args: Any, **kwargs: Any) -> ModuleType:
        module = original(name, *args, **kwargs)
        if (path := _module_file(module)) is not None:
            for caller in _calling_test_files():
                RECORDER.checks_by_file[caller].add(path)
        return module
    watched.__wrapped__ = original           # type: ignore[attr-defined]
    return watched


def pytest_configure(config: pytest.Config) -> None:
    if not unreleased_files():
        return
    config.stash[ON] = True
    sys.addaudithook(RECORDER.audit)
    for owner, functions in EXISTENCE_CHECKS:
        for function in functions:
            setattr(owner, function, _watching(getattr(owner, function)))
    pytest.importorskip = _import_or_skip(pytest.importorskip)


def _message(problems: list[str]) -> str:
    return ("released-files check (tests/released_files.py): this released test uses repository files "
            "release/allowlist.txt leaves out, so it fails in the release tree: " + ", ".join(problems)
            + ". Release them (release/allowlist.txt), or skip the test when they are missing (check that "
            "one exists first, or load it with pytest.importorskip).")


def _checked(config: pytest.Config, path: Path) -> bool:
    return config.stash.get(ON, False) and released_test_file(path)


@pytest.hookimpl(hookwrapper=True)
def pytest_make_collect_report(collector: pytest.Collector) -> Generator[None, Any, None]:
    module = isinstance(collector, pytest.Module) and _checked(collector.config, collector.path)
    if module:
        RECORDER.start()
    outcome = yield
    if not module:
        return
    RECORDER.stop()
    report = outcome.get_result()
    if report.passed and (problems := RECORDER.problems(collector.path, getattr(collector, "_obj", None))):
        report.outcome = "failed"
        report.longrepr = _message(problems)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item: pytest.Item, nextitem: pytest.Item | None) -> Generator[None, Any, None]:
    if _checked(item.config, item.path):
        RECORDER.start()
    yield
    RECORDER.stop()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]) -> Generator[None, Any, None]:
    outcome = yield
    if call.when != "call" or not RECORDER.active:
        return
    report = outcome.get_result()
    if report.passed and (problems := RECORDER.problems(item.path)):
        report.outcome = "failed"
        report.longrepr = _message(problems)
