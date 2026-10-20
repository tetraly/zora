"""Progress for long jobs (owner rule, 2026-10-13; AGENTS.md "Run time"): what is running, how far
along it is, and whether it is still alive.

A job prints at least once a minute what it is, its percent done, its elapsed time and an estimate
of the time left, and keeps the same in a status file, temp/jobs/<id>.json in the source checkout
(this one, or the one a clean copy was made from), which scripts/jobs.py lists across sessions.

    from zora_measure.progress import track
    for seed in track(range(1000), "rate scan", unit="seeds"):        # the one-line helper
        ...
    results = list(track(pool.imap(work, items), "corpus", total=len(items)))

    with Job("make_release") as job:           # steps, a total, or both
        job.step("building the release tree")
        ...

A job started inside another (ZORA_JOB_ID, set for its children) records its parent, so a verify
run shows the pytest run inside it. A process that cannot hold a Job object (a shell script's
steps, a lock waiter) annotates the running job through side files: step_file and waiting_file.
Without a total, the percent and time left come from the job's earlier runs of the same name
(temp/jobs/history.json), when there are any. A job whose items differ in length (a pytest run)
can weigh each one by its recorded duration (`work_total`, `advance(work=...)`): the time left is
then the recorded work still to do at the pace the done work actually took, so slow tests that
come last no longer leave the estimate stuck low (tests/progress_plugin.py; owner request,
2026-10-16). Each test's last passing duration is kept in temp/jobs/test-durations.json.

A job records its session's full id (session_id), so a session can list its own jobs
(scripts/jobs.py --mine) and stop only those (scripts/job.py stop).

A job ended by SIGTERM or SIGHUP marks its status file stopped (with the signal) and removes its
side files before the signal takes its course; one whose process exits without finishing is
marked failed. scripts/jobs.py marks a job whose process is gone without either as died.

A job queued for the suite lock (note_queued, from tests/suite_lock.py) shows "QUEUED", its place
in the queue and 0%, with no estimate, until it starts; the time it spent queued never counts
toward its percent, its time left or the run time its history keeps.
"""
from __future__ import annotations

import atexit
import json
import os
import signal
import statistics
import sys
import threading
import time
import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

REPO = Path(__file__).resolve().parent.parent
SOURCE_REPO_SETTING = "ZORA_SOURCE_REPO"         # scripts/clean_copy.py
JOB_ID_ENV = "ZORA_JOB_ID"                       # the running job, for its children
JOBS_FOLDER_ENV = "ZORA_JOBS_FOLDER"             # its status folder, for its children
SESSION_NAME_ENV = "ZORA_SESSION_NAME"           # a readable session name, if the session sets one
SESSION_ID_ENV = "CLAUDE_CODE_SESSION_ID"        # otherwise the session's id
INTERVAL_ENV = "ZORA_PROGRESS_SECONDS"           # tests shorten it
REPORT_SECONDS = 60.0                            # at least once a minute
HISTORY_RUNS = 5                                 # earlier durations kept per job name
FINISHED, FAILED, RUNNING, WAITING = "finished", "failed", "running", "waiting"
STOPPED, DIED = "stopped", "died"                 # ended by a signal; gone without a word (jobs.py says so)
ENDED = (FINISHED, FAILED, STOPPED, DIED)
STOP_SIGNALS = (signal.SIGTERM, signal.SIGHUP)    # SIGINT is KeyboardInterrupt: finish() runs as it unwinds

T = TypeVar("T")


def jobs_folder() -> Path:
    """temp/jobs/ in the source checkout: a clean copy's jobs show beside its checkout's, and a job
    started inside another, even in another tree (make_release's release tree), uses its parent's."""
    if folder := os.environ.get(JOBS_FOLDER_ENV):
        return Path(folder)
    return Path(os.environ.get(SOURCE_REPO_SETTING) or REPO) / "temp" / "jobs"


def report_seconds() -> float:
    return float(os.environ.get(INTERVAL_ENV) or REPORT_SECONDS)


def session_label() -> str:
    name = os.environ.get(SESSION_NAME_ENV)
    session = os.environ.get(SESSION_ID_ENV, "")
    return name or (f"session {session[:8]}" if session else "no session")


def session_id() -> str | None:
    """This session's full id, which a job records as its owner (the label above is for reading
    and may be shared); None outside a session."""
    return os.environ.get(SESSION_ID_ENV) or None


def is_mine(status: dict[str, Any]) -> bool:
    """Whether the job belongs to the calling session: its recorded session id is this one's. A job
    without one (an older status file) or a caller without one belongs to no caller."""
    own = session_id()
    return own is not None and status.get("session_id") == own


def clock(seconds: float) -> str:
    """3:07, or 1:02:03 past an hour."""
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    return f"{hours}:{rest // 60:02d}:{rest % 60:02d}" if hours else f"{rest // 60}:{rest % 60:02d}"


def _write_json(path: Path, data: dict[str, Any]) -> None:
    """Whole files only: readers never see a half-written status."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f"{path.name}.{os.getpid()}.part")
    partial.write_text(json.dumps(data, indent=1))
    os.replace(partial, path)


def step_file(job_id: str) -> Path:
    return jobs_folder() / f"{job_id}.step"


def waiting_file(job_id: str) -> Path:
    return jobs_folder() / f"{job_id}.waiting"


def note_step(text: str, job_id: str | None = None, level: int = 1) -> None:
    """Name the running job's current step (level 1) or the step within it (level 2), from any
    process inside it; nothing outside a job."""
    job_id = job_id or os.environ.get(JOB_ID_ENV)
    if not job_id:
        return
    path = step_file(job_id)
    steps = json.loads(path.read_text()) if path.is_file() else {}
    steps = {"1": text} if level == 1 else {**steps, "2": text}
    _write_json(path, steps)


@dataclass
class Waiting:
    """What a job waits for (its waiting file): `text`; while it is queued for the suite lock, its
    place in the queue (`place` of `of`), the `holder` and when the queueing began (`since`);
    and the seconds it spent queued before (`queued_seconds`), which its progress leaves out."""
    text: str = ""
    place: int | None = None
    of: int | None = None
    holder: str = ""
    since: float | None = None
    queued_seconds: float = 0.0

    @property
    def queued(self) -> bool:
        return self.since is not None

    def queued_until(self, now: float) -> float:
        """Every second spent queued up to NOW."""
        return self.queued_seconds + (now - self.since if self.since is not None else 0.0)


def read_waiting(job_id: str) -> Waiting:
    """The job's waiting file; a plain-text one (an older writer) is only its text."""
    path = waiting_file(job_id)
    try:
        text = path.read_text()
    except OSError:
        return Waiting()
    try:
        data = json.loads(text)
    except ValueError:
        return Waiting(text=text.strip())
    if not isinstance(data, dict):
        return Waiting(text=text.strip())
    known = {name: data[name] for name in Waiting.__dataclass_fields__ if name in data}
    return Waiting(**known)


def _write_waiting(job_id: str, waiting: Waiting) -> None:
    _write_json(waiting_file(job_id), waiting.__dict__)


def note_waiting(text: str | None, job_id: str | None = None) -> None:
    """Say what the running job is waiting for (None: no longer waiting, and no longer queued:
    the time queued is added to what its progress leaves out)."""
    job_id = job_id or os.environ.get(JOB_ID_ENV)
    if not job_id:
        return
    waiting = read_waiting(job_id)
    if text is None:
        _write_waiting(job_id, Waiting(queued_seconds=waiting.queued_until(time.time())))
    else:
        waiting.text = text
        _write_waiting(job_id, waiting)


def note_queued(place: int, of: int, holder: str, job_id: str | None = None) -> None:
    """The running job is queued for the suite lock: number PLACE of OF waiting, HOLDER holding
    it. Until note_waiting(None) it shows QUEUED at 0%, and the time does not count as running."""
    job_id = job_id or os.environ.get(JOB_ID_ENV)
    if not job_id:
        return
    waiting = read_waiting(job_id)
    _write_waiting(job_id, Waiting(text=f"the suite lock (number {place} of {of}), held by {holder}", place=place,
                                   of=of, holder=holder, since=waiting.since if waiting.queued else time.time(),
                                   queued_seconds=waiting.queued_seconds))


def read_side_files(job_id: str) -> tuple[str, Waiting]:
    """The step text ("step > substep") and what the job waits for, from the side files."""
    step = ""
    if (path := step_file(job_id)).is_file():
        try:
            steps = json.loads(path.read_text())
            step = " > ".join(steps[level] for level in ("1", "2") if steps.get(level))
        except (ValueError, OSError):
            pass
    return step, read_waiting(job_id)


def _waiting_fields(waiting: Waiting) -> dict[str, Any]:
    """A status file's waiting fields."""
    return {"waiting": waiting.text, "queue_place": waiting.place, "queue_length": waiting.of,
            "queue_holder": waiting.holder, "queued_since": waiting.since, "queued_seconds": waiting.queued_seconds}


def history_estimate(name: str) -> float | None:
    """The median of this job name's last finished runs, in seconds, or None."""
    path = jobs_folder() / "history.json"
    try:
        runs = json.loads(path.read_text()).get(name, [])
    except (OSError, ValueError):
        return None
    return statistics.median(runs) if runs else None


def _record_history(name: str, seconds: float) -> None:
    path = jobs_folder() / "history.json"
    try:
        history = json.loads(path.read_text())
    except (OSError, ValueError):
        history = {}
    history[name] = [*history.get(name, []), round(seconds, 1)][-HISTORY_RUNS:]
    _write_json(path, history)


def durations_path() -> Path:
    return jobs_folder() / "test-durations.json"


def read_durations() -> dict[str, list[Any]]:
    """Each test's last passing duration: {node id: [seconds, heavy]}, heavy when it is marked slow
    or full_tier (the quick check never runs those); {} without a record."""
    try:
        data = json.loads(durations_path().read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def record_durations(durations: dict[str, tuple[float, bool]]) -> None:
    """Merge one run's passing tests into the record (their latest duration replaces the old)."""
    if not durations:
        return
    record = read_durations()
    record.update({test: [round(seconds, 3), heavy] for test, (seconds, heavy) in durations.items()})
    _write_json(durations_path(), record)


def expected_work(tests: Iterable[str], record: dict[str, list[Any]]) -> dict[str, float] | None:
    """Each test's expected seconds: its recorded duration, else the mean of the recorded ones
    among TESTS (the run's own pace). None when none is recorded: the count alone estimates."""
    tests = list(tests)
    known = {test: float(record[test][0]) for test in tests if test in record}
    if not known:
        return None
    fallback = sum(known.values()) / len(known)
    return {test: known.get(test, fallback) for test in tests}


@dataclass
class Estimate:
    percent: float | None
    left: float | None
    basis: str                  # "work", "count", "earlier runs" or ""


def estimate(elapsed: float, done: int, total: int | None, typical: float | None,
             work_done: float | None = None, work_total: float | None = None) -> Estimate:
    """From the recorded work when there is some (each item weighed by its recorded duration, at the
    pace the done work took); else from the count; else from the job's earlier runs (capped below
    100 %)."""
    if work_total and work_done:
        left_work = max(0.0, work_total - work_done)
        return Estimate(min(100.0, 100.0 * work_done / work_total), elapsed / work_done * left_work, "work")
    if total:
        percent = 100.0 * done / total
        left = elapsed / done * (total - done) if done else None
        return Estimate(percent, left, "count")
    if typical:
        return Estimate(min(99.0, 100.0 * elapsed / typical), max(0.0, typical - elapsed), "earlier runs")
    return Estimate(None, None, "")


def describe(status: dict[str, Any], now: float | None = None) -> str:
    """One line: what it is, percent, elapsed, time left, step, what it waits for. A job queued for
    the suite lock is QUEUED at 0%, with its place and no estimate; the time it spent queued is
    left out of every estimate."""
    now = now or time.time()
    end = status["finished_at"] if status.get("finished_at") else now
    elapsed = end - status["started"]
    queued_since = status.get("queued_since")
    if queued_since is not None and status.get("state") in (RUNNING, WAITING):
        place, length = status.get("queue_place"), status.get("queue_length")
        where = f"number {place} of {length}" if place and length else "in the queue"
        holder = f", held by {status['queue_holder']}" if status.get("queue_holder") else ""
        parts = [status["name"], "QUEUED, 0%", f"{where} for the suite lock{holder}",
                 f"queued {clock(now - queued_since)}", f"{clock(elapsed)} elapsed"]
        return ", ".join(parts)
    queued = status.get("queued_seconds") or 0.0
    # The count is as of the job's last report: estimate from then, shown less the time since
    reported = status.get("updated", now) - status["started"] - queued
    guess = estimate(max(0.0, reported), status.get("done", 0), status.get("total"), status.get("typical"),
                     status.get("work_done"), status.get("work_total"))
    if guess.left is not None:
        guess.left = max(0.0, guess.left - (elapsed - queued - reported))
    parts = [status["name"]]
    if guess.percent is not None:
        count = (f" ({status.get('done', 0)}/{status['total']} {status.get('unit', 'items')})"
                 if status.get("total") else "")
        parts.append(f"{guess.percent:.0f}%{count}")
    parts.append(f"{clock(elapsed)} elapsed" + (f" ({clock(queued)} of it queued)" if queued >= 1 else ""))
    if guess.left is not None and status.get("state") in (RUNNING, WAITING):
        basis = {"earlier runs": " (from earlier runs)", "work": " (from recorded test times)"}.get(guess.basis, "")
        parts.append(f"about {clock(guess.left)} left{basis}")
    elif status.get("state") in (RUNNING, WAITING):
        parts.append("time left unknown")
    if status.get("step"):
        parts.append(f"step: {status['step']}")
    if status.get("waiting") and status.get("state") in (RUNNING, WAITING):
        parts.append(f"WAITING: {status['waiting']}")
    if status.get("signal"):
        parts.append(f"stopped by {status['signal']}")
    return ", ".join(parts)


class Job:
    """A long job's progress: printed every report_seconds() and kept in its status file."""

    def __init__(self, name: str, total: int | None = None, unit: str = "items",
                 stream: Any = None) -> None:
        self.name, self.total, self.unit = name, total, unit
        self.done = 0
        self.work_done = 0.0                          # recorded seconds, when items are weighed
        self.work_total: float | None = None
        self.stream = stream or sys.stderr
        self.id = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.parent = os.environ.get(JOB_ID_ENV)
        self.started = time.time()
        self.state = RUNNING
        self.typical = None if total else history_estimate(name)
        self.signal_name: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._previous_handlers: dict[int, Any] = {}

    @property
    def path(self) -> Path:
        return jobs_folder() / f"{self.id}.json"

    def status(self) -> dict[str, Any]:
        step, waiting = read_side_files(self.id)
        return {"id": self.id, "name": self.name, "pid": os.getpid(), "parent": self.parent,
                "session": session_label(), "session_id": session_id(),
                "command": " ".join(sys.argv)[:300], "cwd": os.getcwd(),
                "started": self.started, "updated": time.time(), "state": self.state,
                "done": self.done, "total": self.total, "unit": self.unit, "typical": self.typical,
                "work_done": self.work_done, "work_total": self.work_total,
                "step": step, **_waiting_fields(waiting), "report_seconds": report_seconds(),
                "signal": self.signal_name, "finished_at": time.time() if self.state in ENDED else None}

    def report(self, say: bool = True) -> None:
        """Write the status file; with SAY, print it, with the innermost job running inside this one
        (a pytest run inside verify, the release tree's suite inside make_release)."""
        with self._lock:
            status = self.status()
            _write_json(self.path, status)
        if say:
            line = describe(status)
            if child := innermost_child(self.id):
                line += f"; inside it: {describe(child)}"
            # On a line of its own, even after a test run's row of dots
            print(f"\nprogress: {line}", file=self.stream, flush=True)

    def start(self, tick: bool = True) -> Job:
        """Begin; with TICK, a thread reports every report_seconds() (without, the caller does)."""
        os.environ[JOB_ID_ENV] = self.id              # children (subprocesses) are inside it
        os.environ[JOBS_FOLDER_ENV] = str(jobs_folder())
        self.report(say=False)
        if tick:
            self._thread = threading.Thread(target=self._tick, name=f"progress {self.name}", daemon=True)
            self._thread.start()
        self._watch_for_the_end()
        return self

    def _watch_for_the_end(self) -> None:
        """Mark the status file if the process is signaled (SIGTERM, SIGHUP) or exits without
        finish(). Signal handlers can only be set from the main thread; elsewhere only the exit."""
        atexit.register(self._at_exit)
        if threading.current_thread() is not threading.main_thread():
            return
        for number in STOP_SIGNALS:
            self._previous_handlers[number] = signal.getsignal(number)
            signal.signal(number, self._on_signal)

    def _forget_the_end(self) -> None:
        atexit.unregister(self._at_exit)
        for number, previous in self._previous_handlers.items():
            if signal.getsignal(number) == self._on_signal:
                signal.signal(number, previous)
        self._previous_handlers.clear()

    def _at_exit(self) -> None:
        if self.state == RUNNING:
            self.finish(ok=False)

    def _on_signal(self, number: int, frame: Any) -> None:
        """Stopped: mark it, then let the signal do what it did before (an outer job's handler,
        or the default, which ends the process)."""
        previous = self._previous_handlers.get(number, signal.SIG_DFL)
        self.stop(number)
        if callable(previous):
            previous(number, frame)
        elif previous != signal.SIG_IGN:
            signal.signal(number, signal.SIG_DFL)
            os.kill(os.getpid(), number)

    def stop(self, number: int) -> None:
        """Ended by signal NUMBER: the status file says so; no history (it did not run to the end)."""
        self.signal_name = signal.Signals(number).name
        self._end(STOPPED)

    def _tick(self) -> None:
        while not self._stop.wait(report_seconds()):
            self.report()

    def advance(self, count: int = 1, work: float = 0.0) -> None:
        """COUNT more items done, weighing WORK recorded seconds (when work_total is set)."""
        self.done += count
        self.work_done += work

    def step(self, text: str) -> None:
        note_step(text, self.id)
        print(f"progress: {self.name}: {text}", file=self.stream, flush=True)

    def finish(self, ok: bool = True) -> None:
        self._end(FINISHED if ok else FAILED)

    def _end(self, state: str) -> None:
        if self.state in ENDED:
            return
        self._stop.set()
        self._forget_the_end()
        self.state = state
        self.report(say=False)
        if state == FINISHED:       # its run time: the time it spent queued for the suite lock is no measure of it
            _record_history(self.name, time.time() - self.started - read_waiting(self.id).queued_until(time.time()))
        for side in (step_file(self.id), waiting_file(self.id)):
            side.unlink(missing_ok=True)
        if os.environ.get(JOB_ID_ENV) == self.id:
            if self.parent:
                os.environ[JOB_ID_ENV] = self.parent
            else:
                os.environ.pop(JOB_ID_ENV, None)

    def __enter__(self) -> Job:
        return self.start()

    def __exit__(self, kind: object, value: object, traceback: object) -> None:
        self.finish(ok=kind is None)


def track(items: Iterable[T], name: str, total: int | None = None, unit: str = "items") -> Iterator[T]:
    """The one-line helper: yield ITEMS while reporting progress (a total from len() when it has one)."""
    if total is None and hasattr(items, "__len__"):
        total = len(items)  # type: ignore[arg-type]
    job = Job(name, total=total, unit=unit).start()
    ok = False
    try:
        for item in items:
            yield item
            job.advance()
        ok = True
    finally:
        job.finish(ok)


def read_jobs() -> list[dict[str, Any]]:
    """Every status file, with its side files' step and waiting folded in."""
    jobs = []
    for path in sorted(jobs_folder().glob("*.json")):
        if path.name in ("history.json", durations_path().name):
            continue
        try:
            status = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(status, dict) or "id" not in status:      # not a job's status file
            continue
        if status.get("state") in (RUNNING, WAITING):
            step, waiting = read_side_files(status["id"])
            status["step"] = step or status.get("step", "")
            status |= _waiting_fields(waiting)
        jobs.append(status)
    return jobs


def mark_died(status: dict[str, Any], now: float | None = None) -> dict[str, Any]:
    """A running job whose process is gone: its status file says died, when it was noticed, and
    its side files go (scripts/jobs.py calls it). A job is never marked while its process lives."""
    if status.get("state") in ENDED or alive(status["pid"]):
        return status
    died = {**status, "state": DIED, "finished_at": now or time.time()}
    _write_json(jobs_folder() / f"{status['id']}.json", died)
    for side in (step_file(status["id"]), waiting_file(status["id"])):
        side.unlink(missing_ok=True)
    return died


def job_alive(job_id: str) -> bool | None:
    """Whether the job's process is alive; None without a status file to tell."""
    try:
        status = json.loads((jobs_folder() / f"{job_id}.json").read_text())
    except (OSError, ValueError):
        return None
    return status.get("state") not in ENDED and alive(int(status["pid"]))


def innermost_child(job_id: str) -> dict[str, Any] | None:
    """The deepest running job started inside JOB_ID, or None."""
    running = [status for status in read_jobs() if status.get("state") in (RUNNING, WAITING)]
    by_parent = {status.get("parent"): status for status in running}
    found = None
    while job_id in by_parent:
        found = by_parent[job_id]
        job_id = found["id"]
    return found


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def health(status: dict[str, Any], now: float | None = None) -> str:
    """ok, finished, failed, stopped, "died" (its process is gone without a word) or "probably
    hung" (silent too long)."""
    now = now or time.time()
    if (state := str(status.get("state"))) in ENDED:
        return state
    if not alive(status["pid"]):
        return DIED
    silent = now - status.get("updated", 0)
    if silent > 3 * max(status.get("report_seconds") or REPORT_SECONDS, 1.0):
        return "probably hung"
    return "ok"
