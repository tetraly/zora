"""Test-wide setup.

The patches' original bytes come from the player's PRG0 ROM, which generation remembers
when it is given one (zora/rom/base_rom.py); player_rom() refuses when none was. Tests that
parse finished or corpus ROMs before generating anything need it remembered, so every test
process (each xdist worker too) starts with the repo-root ROM remembered, when it is there.
The generation path's own remembering is tested in fresh processes, where this does not run
(tests/test_player_rom.py, tests/test_package_copy.py).

Every process of a session shares its builds through one folder (tests/shared_builds.py),
made here before the xdist workers start and removed at the end; each test may load a stored
build once (docs/design/test-speed.md 3.1).

A run with more than two xdist workers (suite_lock.LIGHT_WORKERS) is a full suite: it waits
for any other full suite on this checkout to finish (tests/suite_lock.py), and warns when it
has to (owner rule: while a run holds the lock, other test runs use at most two workers).
Running alone, it is fastest with `-n auto` at one worker per core (AUTO_WORKER_SHARE; measured
in tasks/test-speed-2.md: 7, 9 and 10 workers on 10 cores). A run that selects a slow test
(`-m slow`, or one slow test) takes the lock whatever its workers; without xdist, once its
tests are collected. A light run, serial or at most two workers, runs beside a suite.

Every run loads tests/encoder_check.py, which records the tests that reach the level encoder
(ZORA_ENCODER_RECORD) or hides it (ZORA_HIDE_LEVEL_ENCODING) for scripts/encoder_check.py, and
tests/progress_plugin.py, which reports the run's progress at least once a minute.
"""
import os
import shutil
import uuid
from collections.abc import Generator
from contextlib import ExitStack
from pathlib import Path

import pytest
from _pytest.mark.structures import ParameterSet

from tests import shared_builds
from tests.suite_lock import HELD_ENV, LIGHT_WORKERS, holder, suite_lock
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom

SHARED_BUILDS_ROOT = Path(__file__).resolve().parent.parent / "temp" / "test-builds"
_SHARED_BUILDS_FOLDER = pytest.StashKey[Path]()
_SUITE_LOCK = pytest.StashKey[ExitStack]()
AUTO_WORKER_SHARE = 1.0
ENCODER_CHECK_PLUGIN = "tests.encoder_check"
PROGRESS_PLUGIN = "tests.progress_plugin"
SEED_PARAMETER = "seed"
FULL_TIER = pytest.mark.full_tier
_shared_builds = shared_builds.install()


@pytest.fixture(autouse=True, scope="session")
def _remember_repo_base_rom() -> None:
    if BASE_ROM_PATH.exists():
        remember_repo_base_rom()


def pytest_xdist_auto_num_workers(config: pytest.Config) -> int:
    return max(2, int((os.cpu_count() or 2) * AUTO_WORKER_SHARE))


def pytest_configure(config: pytest.Config) -> None:
    """The controller (or a run without xdist) makes the session's folder; workers inherit it.
    The controller of a heavy xdist run first takes the suite lock, held until the run ends."""
    for plugin in (ENCODER_CHECK_PLUGIN, PROGRESS_PLUGIN):       # tests/encoder_check.py, tests/progress_plugin.py
        if not config.pluginmanager.has_plugin(plugin):
            config.pluginmanager.import_plugin(plugin)
    workers = 0 if hasattr(config, "workerinput") else _requested_workers(config)
    if workers > LIGHT_WORKERS or (workers and _selects_slow(config)):
        # Inside a held lock (verify's own pytest) the holder is this run's parent: no warning
        if workers > LIGHT_WORKERS and not os.environ.get(HELD_ENV) and (running := holder()):
            _say(config, f"WARNING: {running} holds the lock; while it does, other test runs use at most "
                         f"{LIGHT_WORKERS} workers (AGENTS.md), and this one asks for {workers}. Waiting for "
                         f"it (use -n {LIGHT_WORKERS} to run beside it).")
        _take_suite_lock(config)
    if not hasattr(config, "workerinput") and shared_builds.FOLDER_ENV not in os.environ:
        folder = SHARED_BUILDS_ROOT / uuid.uuid4().hex
        folder.mkdir(parents=True)
        os.environ[shared_builds.FOLDER_ENV] = str(folder)
        config.stash[_SHARED_BUILDS_FOLDER] = folder


def _requested_workers(config: pytest.Config) -> int:
    """The xdist workers this run asks for (0 without xdist)."""
    requested = config.getoption("numprocesses", None)
    if not requested:
        return 0
    if requested in ("auto", "logical"):
        return pytest_xdist_auto_num_workers(config)
    return int(requested)


def _selects_slow(config: pytest.Config) -> bool:
    """Whether the -m expression asks for slow tests (an xdist controller collects nothing)."""
    expression = config.getoption("markexpr", "") or ""
    return "slow" in expression and "not slow" not in expression


def _say(config: pytest.Config, message: str) -> None:
    """Print past pytest's output capture."""
    capture = config.pluginmanager.getplugin("capturemanager")
    if capture is None:                  # -p no:capture
        print(f"suite lock: {message}", flush=True)
        return
    with capture.global_and_fixture_disabled():
        print(f"suite lock: {message}", flush=True)


def _take_suite_lock(config: pytest.Config) -> None:
    """Wait for the suite lock and hold it until the run ends (pytest_unconfigure)."""
    held = ExitStack()
    held.enter_context(suite_lock("pytest " + " ".join(config.invocation_params.args),
                                  lambda message: _say(config, message)))
    config.stash[_SUITE_LOCK] = held


@pytest.hookimpl(tryfirst=True)          # before -m deselects by marker
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Seeds 2 and up of a seed sweep are the full tier's (docs/design/test-speed.md 3.2; owner
    decision, 2026-10-13): scripts/verify.sh deselects them with -m "not full_tier"."""
    for item in items:
        if _later_swept_seed(item):
            item.add_marker(FULL_TIER)


def _later_swept_seed(item: pytest.Item) -> bool:
    """Whether ITEM runs a seed after the first of a parametrize over `seed` alone. Seeds chosen
    with other values (`("seed", "level_num", ...)`) pick a scenario, not a sweep, and stay."""
    seed = getattr(getattr(item, "callspec", None), "params", {}).get(SEED_PARAMETER)
    if seed is None:
        return False
    for mark in item.iter_markers("parametrize"):
        names = mark.args[0] if mark.args else mark.kwargs.get("argnames", ())
        if isinstance(names, str):
            names = [name.strip() for name in names.split(",")]
        if list(names or ()) == [SEED_PARAMETER]:
            values = mark.args[1] if len(mark.args) > 1 else mark.kwargs["argvalues"]
            first = next(iter(values))
            first = first.values[0] if isinstance(first, ParameterSet) else first
            return bool(seed != first)
    return False


def pytest_collection_finish(session: pytest.Session) -> None:
    """A run without xdist that selected a slow test takes the lock before running it: slow
    suites run serially are the longest runs of all, and must not overlap a verify run."""
    config = session.config
    if hasattr(config, "workerinput") or _SUITE_LOCK in config.stash:
        return
    if any(item.get_closest_marker("slow") for item in session.items):
        _take_suite_lock(config)


def pytest_unconfigure(config: pytest.Config) -> None:
    folder = config.stash.get(_SHARED_BUILDS_FOLDER, None)
    if folder is not None:
        shutil.rmtree(folder, ignore_errors=True)
        os.environ.pop(shared_builds.FOLDER_ENV, None)
    held = config.stash.get(_SUITE_LOCK, None)
    if held is not None:
        held.close()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(item: pytest.Item) -> Generator[None, object, object]:
    """Setup, call and teardown: a monkeypatched test's fixtures may be patched too. Each test
    starts with no stored build handed out, so its first request for a plan may load one."""
    _shared_builds.begin_test("monkeypatch" in getattr(item, "fixturenames", ()))
    try:
        return (yield)
    finally:
        _shared_builds.begin_test(False)
