"""Test-wide setup.

The patches' original bytes come from the player's PRG0 ROM, which generation remembers
when it is given one (zora/rom/base_rom.py); player_rom() refuses when none was. Tests that
parse finished or corpus ROMs before generating anything need it remembered, so every test
process (each xdist worker too) starts with the repo-root ROM remembered, when it is there.
The generation path's own remembering is tested in fresh processes, where this does not run
(tests/test_player_rom.py, tests/test_package_copy.py).

Every process of a session shares its builds through one folder (tests/shared_builds.py),
made here before the xdist workers start and removed at the end.

A run with xdist workers is a full suite: it waits for any other full suite on this checkout
to finish (tests/suite_lock.py). Running alone, it is fastest with `-n auto` at one worker per
core (AUTO_WORKER_SHARE; measured in tasks/test-speed-2.md: 7, 9 and 10 workers on 10 cores).
"""
import os
import shutil
import uuid
from collections.abc import Generator
from contextlib import ExitStack
from pathlib import Path

import pytest

from tests import shared_builds
from tests.suite_lock import suite_lock
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom

SHARED_BUILDS_ROOT = Path(__file__).resolve().parent.parent / "temp" / "test-builds"
_SHARED_BUILDS_FOLDER = pytest.StashKey[Path]()
_SUITE_LOCK = pytest.StashKey[ExitStack]()
AUTO_WORKER_SHARE = 1.0
_shared_builds = shared_builds.install()


@pytest.fixture(autouse=True, scope="session")
def _remember_repo_base_rom() -> None:
    if BASE_ROM_PATH.exists():
        remember_repo_base_rom()


def pytest_xdist_auto_num_workers(config: pytest.Config) -> int:
    return max(2, int((os.cpu_count() or 2) * AUTO_WORKER_SHARE))


def pytest_configure(config: pytest.Config) -> None:
    """The controller (or a run without xdist) makes the session's folder; workers inherit it.
    The controller of an xdist run first takes the suite lock, held until the run ends."""
    if not hasattr(config, "workerinput") and config.getoption("numprocesses", None):
        held = ExitStack()
        capture = config.pluginmanager.getplugin("capturemanager")

        def say(message: str) -> None:
            if capture is None:              # -p no:capture
                print(f"suite lock: {message}", flush=True)
                return
            with capture.global_and_fixture_disabled():
                print(f"suite lock: {message}", flush=True)
        held.enter_context(suite_lock("pytest " + " ".join(config.invocation_params.args), say))
        config.stash[_SUITE_LOCK] = held
    if not hasattr(config, "workerinput") and shared_builds.FOLDER_ENV not in os.environ:
        folder = SHARED_BUILDS_ROOT / uuid.uuid4().hex
        folder.mkdir(parents=True)
        os.environ[shared_builds.FOLDER_ENV] = str(folder)
        config.stash[_SHARED_BUILDS_FOLDER] = folder


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
    """Setup, call and teardown: a monkeypatched test's fixtures may be patched too."""
    _shared_builds.patched_test = "monkeypatch" in getattr(item, "fixturenames", ())
    try:
        return (yield)
    finally:
        _shared_builds.patched_test = False
