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

Waiters queue first come, first served (owner rule, 2026-10-13): each registers in a folder beside
the lock and takes it only when it is the earliest live waiter. While waiting, a run says every
minute who holds the lock (session, command, process, since when) and its own place in the queue,
and tells the job it runs in (zora_measure/progress.py) what it is waiting for.
"""
import fcntl
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any, TypedDict

REPO = Path(__file__).resolve().parent.parent
LOCK_SETTING = "ZORA_SUITE_LOCK"
LOCK_NAME = "test-suite.lock"
HELD_ENV = "ZORA_SUITE_LOCK_HELD"
LIGHT_WORKERS = 2                   # the most workers a test run may use while the lock is held
QUEUE_NAME = "test-suite-queue"     # beside the lock: one file per waiting run
POLL_SECONDS = 0.5
INTERVAL_ENV = "ZORA_PROGRESS_SECONDS"     # as zora_measure/progress.py; tests shorten it
REPORT_SECONDS = 60.0


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


def _session() -> str:
    """The session running this (as zora_measure/progress.py names it)."""
    session = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    return os.environ.get("ZORA_SESSION_NAME") or (f"session {session[:8]}" if session else "no session")


def _progress() -> Any:
    """The progress module, or None where it is not (a lone copy of this file, as tests make)."""
    try:
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        from zora_measure import progress
    except ImportError:
        return None
    return progress


def _note_queued(place: int, of: int, holder_text: str) -> None:
    """Tell the job this run is inside that it is queued: QUEUED, its place, 0% until it starts."""
    if progress := _progress():
        progress.note_queued(place, of, holder_text)


class JobEnded(SystemExit):
    """The job this waiting run belongs to has ended: it gives up its place, never to start later."""


def _job_ended() -> str | None:
    """Why this waiting run should give up: the job it is inside (ZORA_JOB_ID) has ended or its
    process is gone (killed outright, as SIGKILL leaves its command orphaned), or None."""
    job_id = os.environ.get("ZORA_JOB_ID")
    if not job_id or not (progress := _progress()):
        return None
    alive = progress.job_alive(job_id)
    return f"the job it belongs to ({job_id}) has ended" if alive is False else None


def _note_started() -> None:
    """Tell the job this run is inside that it is no longer queued."""
    if progress := _progress():
        progress.note_waiting(None)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def one_line(label: str, limit: int = 120) -> str:
    """A command line as one short line: a holder's or waiter's label in the lock's reports."""
    flat = " ".join(label.split())
    return flat if len(flat) <= limit else flat[:limit - 3] + "..."


class Waiter(TypedDict):
    """A run waiting for the lock: its file in the queue folder."""
    pid: int
    label: str
    session: str
    since: float


def queue_folder() -> Path:
    return LOCK_PATH.parent / QUEUE_NAME


def waiting_runs() -> list[Waiter]:
    """The live waiters, earliest first; a waiter whose process is gone is cleared."""
    runs: list[Waiter] = []
    for path in queue_folder().glob("*.json"):
        try:
            entry: Waiter = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if _alive(entry["pid"]):
            runs.append(entry)
        else:
            path.unlink(missing_ok=True)
    return sorted(runs, key=lambda entry: (entry["since"], entry["pid"]))


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
        _take(lock, label, say)
        lock.seek(0)
        lock.truncate()
        lock.write(f"pid {os.getpid()}, {_session()}, {one_line(label)}, since {time.strftime('%H:%M:%S')}\n")
        lock.flush()
        os.environ[HELD_ENV] = "1"
        try:
            yield
        finally:
            os.environ.pop(HELD_ENV, None)
            fcntl.flock(lock, fcntl.LOCK_UN)


def _take(lock: IO[str], label: str, say: Callable[[str], None]) -> None:
    """Take the lock in queue order, saying every minute who holds it and where this run stands."""
    entry = queue_folder() / f"{os.getpid()}.json"
    queue_folder().mkdir(parents=True, exist_ok=True)
    entry.write_text(json.dumps({"pid": os.getpid(), "label": one_line(label), "session": _session(),
                                 "since": time.time()}))
    started = time.monotonic()
    next_report = started + float(os.environ.get(INTERVAL_ENV) or REPORT_SECONDS)
    waited = False
    noted: tuple[int, int, str] | None = None      # the place last told to the job
    try:
        while True:
            waiters = waiting_runs()
            first = not waiters or waiters[0]["pid"] == os.getpid()
            if first:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    pass
            if ended := _job_ended():
                say(f"not waiting any longer: {ended}")
                raise JobEnded(1)
            place = next((n for n, run in enumerate(waiters, 1) if run["pid"] == os.getpid()), 1)
            queue = (place, max(len(waiters), place), holder() or "another run")
            if not waited:
                waited = True
                say(f"waiting for the test suite already running ({queue[2]}) to finish")
            if queue != noted:
                noted = queue
                _note_queued(*queue)
            if time.monotonic() >= next_report:
                next_report += float(os.environ.get(INTERVAL_ENV) or REPORT_SECONDS)
                ahead = "; ahead of it: " + "; ".join(f"{run['session']}, pid {run['pid']}, {run['label']}"
                                                      for run in waiters[:place - 1]) if place > 1 else ""
                say(f"still waiting after {time.monotonic() - started:.0f} s: held by {holder() or 'another run'}; "
                    f"this run is number {place} of {len(waiters)} waiting{ahead}")
            time.sleep(POLL_SECONDS)
    finally:
        entry.unlink(missing_ok=True)
        if waited:          # started, or given up: no longer queued either way
            _note_started()
    if waited:
        say(f"waited {time.monotonic() - started:.0f} s; starting")


def main(command: list[str]) -> int:
    with suite_lock(" ".join(command)):
        return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
