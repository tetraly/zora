"""One full test suite at a time (tasks/test-speed-2.md).

Several sessions share this checkout and each runs whole suites in parallel; run together they
oversubscribe the machine and every one of them crawls (load averages of 100 on 10 cores). A
full suite takes an exclusive lock on a file in temp/ and holds it until it ends; another waits
for it and says so. The operating system releases the lock when its process ends, however it
ends, so a crashed run never leaves it held.

Who takes it: scripts/verify.sh for its whole run (through main() below), any pytest run with
more than LIGHT_WORKERS xdist workers, such as `pytest -n auto`, any pytest run that selects a
slow test (tests/conftest.py), and scripts/compare_revision.py; a run already inside a held
lock (ZORA_SUITE_LOCK_HELD) does not take it again. A clean copy's runs take this checkout's
lock (lock_path). A light run (owner rule, 2026-10-11: at most LIGHT_WORKERS workers while
any run holds the lock) takes no lock and runs beside the suite.

    python3 tests/suite_lock.py COMMAND [ARGS...]    run COMMAND holding the lock
"""
import fcntl
import os
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOCK_SETTING = "ZORA_SUITE_LOCK"
LOCK_NAME = "test-suite.lock"
HELD_ENV = "ZORA_SUITE_LOCK_HELD"
LIGHT_WORKERS = 2                   # the most workers a test run may use while the lock is held


def lock_path() -> Path:
    """ZORA_SUITE_LOCK when set (scripts/clean_copy.py sets it for a copy's runs). Otherwise, in a
    clean copy (temp/NAME-copy inside a checkout) the checkout's own lock, so a copy run without
    its settings still waits for the checkout's suites, not a lock of its own nobody else takes;
    otherwise this checkout's."""
    if setting := os.environ.get(LOCK_SETTING):
        return Path(setting)
    if REPO.parent.name == "temp" and (REPO.parent.parent / "tests" / "suite_lock.py").is_file():
        return REPO.parent / LOCK_NAME
    return REPO / "temp" / LOCK_NAME


LOCK_PATH = lock_path()


def _say(message: str) -> None:
    print(f"suite lock: {message}", file=sys.stderr, flush=True)


def holder() -> str | None:
    """Who holds the lock now (its label), or None if nobody does; takes nothing."""
    if not LOCK_PATH.exists():
        return None
    with LOCK_PATH.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.seek(0)
            return lock.read().strip() or "another run"
        fcntl.flock(lock, fcntl.LOCK_UN)
    return None


@contextmanager
def suite_lock(label: str, say: Callable[[str], None] = _say) -> Iterator[None]:
    """Hold the lock (waiting for it if another suite holds it) while the block runs."""
    if os.environ.get(HELD_ENV):
        yield
        return
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.seek(0)
            holder = lock.read().strip() or "another run"
            say(f"waiting for the test suite already running ({holder}) to finish")
            started = time.monotonic()
            fcntl.flock(lock, fcntl.LOCK_EX)
            say(f"waited {time.monotonic() - started:.0f} s; starting")
        lock.seek(0)
        lock.truncate()
        lock.write(f"pid {os.getpid()}, {label}, since {time.strftime('%H:%M:%S')}\n")
        lock.flush()
        os.environ[HELD_ENV] = "1"
        try:
            yield
        finally:
            os.environ.pop(HELD_ENV, None)
            fcntl.flock(lock, fcntl.LOCK_UN)


def main(command: list[str]) -> int:
    with suite_lock(" ".join(command)):
        return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
