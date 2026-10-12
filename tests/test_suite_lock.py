"""One full suite at a time (tests/suite_lock.py): a second run waits for the first, a slow test
run without xdist takes the lock too, and a clean copy run without its settings still takes
its checkout's lock. Each test uses a lock file of its own in tmp_path, never the checkout's
(the suite running these tests holds that one)."""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SUITE_LOCK = REPO / "tests" / "suite_lock.py"
HOLD_SECONDS = 6                    # long enough for a pytest run to start under load


def _environment(lock: Path | None) -> dict[str, str]:
    """This run's lock settings removed (it holds the checkout's lock), the test's own set."""
    environment = {name: value for name, value in os.environ.items()
                   if name not in ("ZORA_SUITE_LOCK", "ZORA_SUITE_LOCK_HELD")}
    if lock is not None:
        environment["ZORA_SUITE_LOCK"] = str(lock)
    return environment


def _hold(lock: Path, done: Path) -> subprocess.Popen[str]:
    """A run holding the lock for HOLD_SECONDS, then writing the time it ended to `done`."""
    holder = subprocess.Popen(
        [sys.executable, str(SUITE_LOCK), sys.executable, "-c",
         f"import time; time.sleep({HOLD_SECONDS}); open({str(done)!r}, 'w').write(str(time.time()))"],
        env=_environment(lock), stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 10
    while "pid" not in (lock.read_text() if lock.exists() else ""):
        assert time.monotonic() < deadline, "the holder never took the lock"
        time.sleep(0.05)
    return holder


def test_a_second_run_waits_for_the_first(tmp_path: Path) -> None:
    lock, first_done, second_start = tmp_path / "lock", tmp_path / "first", tmp_path / "second"
    holder = _hold(lock, first_done)
    second = subprocess.run(
        [sys.executable, str(SUITE_LOCK), sys.executable, "-c",
         f"import time; open({str(second_start)!r}, 'w').write(str(time.time()))"],
        env=_environment(lock), capture_output=True, text=True, check=True)
    holder.wait(timeout=30)
    assert "waiting for the test suite already running" in second.stderr
    assert float(second_start.read_text()) >= float(first_done.read_text())


@pytest.mark.slow
def test_slow_probe() -> None:
    """Selected only by test_a_serial_slow_run_takes_the_lock's own run."""


def test_a_serial_slow_run_takes_the_lock(tmp_path: Path) -> None:
    """`pytest -m slow` without xdist waits for a held lock (it used to run straight away)."""
    lock = tmp_path / "lock"
    holder = _hold(lock, tmp_path / "done")
    probe = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-m", "slow", "-p", "no:cacheprovider",
         f"{Path(__file__).relative_to(REPO)}::test_slow_probe"],
        cwd=REPO, env=_environment(lock), capture_output=True, text=True, check=False)
    holder.wait(timeout=30)
    assert probe.returncode == 0, probe.stdout + probe.stderr
    assert "suite lock: waiting for the test suite already running" in probe.stdout


def _targeted_run(lock: Path, *options: str, test: str = "test_lock_path_without_settings_outside_a_copy",
                  inside_the_lock: bool = False) -> str:
    """A pytest run of one test of this file while another run holds `lock` (or, inside_the_lock,
    as that run's own child, the way verify.sh runs pytest); its output."""
    holder = _hold(lock, lock.with_suffix(".done"))
    environment = _environment(lock) | ({"ZORA_SUITE_LOCK_HELD": "1"} if inside_the_lock else {})
    probe = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *options,
         f"{Path(__file__).relative_to(REPO)}::{test}"],
        cwd=REPO, env=environment, capture_output=True, text=True, check=False, timeout=HOLD_SECONDS * 10)
    holder.wait(timeout=30)
    assert probe.returncode == 0, probe.stdout + probe.stderr
    return probe.stdout


@pytest.mark.parametrize("workers", [[], ["-n", "1"], ["-n", "2"]], ids=["serial", "1 worker", "2 workers"])
def test_a_light_run_runs_beside_a_held_lock(tmp_path: Path, workers: list[str]) -> None:
    """Owner rule: while a run holds the lock, other test runs use at most two workers; those
    runs take no lock."""
    assert "suite lock" not in _targeted_run(tmp_path / "lock", *workers)


def test_a_heavier_run_warns_and_waits(tmp_path: Path) -> None:
    output = _targeted_run(tmp_path / "lock", "-n", "3")
    assert "WARNING" in output and "at most 2 workers" in output and "asks for 3" in output
    assert "suite lock: waiting for the test suite already running" in output


def test_a_run_inside_the_held_lock_neither_warns_nor_waits(tmp_path: Path) -> None:
    """verify.sh's own `pytest -n auto` runs under the lock verify holds."""
    assert "suite lock" not in _targeted_run(tmp_path / "lock", "-n", "3", inside_the_lock=True)


def test_a_light_slow_run_still_takes_the_lock(tmp_path: Path) -> None:
    output = _targeted_run(tmp_path / "lock", "-n", "2", "-m", "slow", test="test_slow_probe")
    assert "suite lock: waiting for the test suite already running" in output
    assert "WARNING" not in output


def _lock_path_in(checkout: Path) -> Path:
    found = subprocess.run([sys.executable, "-c", "from tests.suite_lock import LOCK_PATH; print(LOCK_PATH)"],
                           cwd=checkout, env=_environment(None), capture_output=True, text=True, check=True)
    return Path(found.stdout.strip()).resolve()


def test_a_copy_without_its_settings_takes_its_checkouts_lock(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    copy = checkout / "temp" / "x-copy"
    for tree in (checkout, copy):
        (tree / "tests").mkdir(parents=True)
        shutil.copy2(SUITE_LOCK, tree / "tests" / "suite_lock.py")
    assert _lock_path_in(copy) == (checkout / "temp" / "test-suite.lock").resolve()


def test_lock_path_without_settings_outside_a_copy(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    shutil.copy2(SUITE_LOCK, tmp_path / "tests" / "suite_lock.py")
    assert _lock_path_in(tmp_path) == (tmp_path / "temp" / "test-suite.lock").resolve()
