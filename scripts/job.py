"""A long command as a job with progress (zora_measure/progress.py; AGENTS.md "Run time").

    python3 scripts/job.py run --name NAME -- COMMAND [ARGS ...]   run COMMAND as job NAME
    python3 scripts/job.py step TEXT                                 the running job's step
    python3 scripts/job.py substep TEXT                              the step within it
    python3 scripts/job.py stop JOB_ID                               stop one of this session's jobs

`run` passes COMMAND's output through and, at least once a minute, prints the job's progress:
its step, the job running inside it (a pytest run's count of tests, say), its elapsed time and the
time left, from earlier runs of NAME when nothing inside it has a count. scripts/verify.sh and
scripts/verify_full.sh run themselves under it and name their steps with `step` and `substep`.
Its exit status is COMMAND's.

COMMAND runs in a process group of its own. A SIGTERM, SIGHUP or SIGINT to `run` goes on to
that whole group (a lock waiter, a pytest run and its workers), never leaving them running
orphaned; once COMMAND has ended (or, after STOP_GRACE_SECONDS, been killed) the job is marked
stopped by that signal and `run` exits with 128 + its number.

`stop` is the one way a session stops a job (AGENTS.md "Run time"): it sends SIGTERM to the job's
process only when the job belongs to the calling session (its status file's session_id is this
session's, CLAUDE_CODE_SESSION_ID) and that process is still the job's (not a later process given
the same pid), then waits for the job to end. Anything else is refused, exit status 3: another
session's job, a job without a recorded session, a caller without one. Exit 0 once stopped, 1 if
it was not stopped (it had ended, its process is gone, or it outlived the wait), 2 for no such job. Find your
jobs' ids with `python3 scripts/jobs.py --mine` (or `--mine --json`), never by reading PIDs off the
shared listing: one taken from the wrong line stops another session's run.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import FrameType

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from zora_measure import progress  # noqa: E402

USAGE = __doc__
FORWARDED_SIGNALS = (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)
STOP_GRACE_SECONDS = 10          # then the group is killed (SIGKILL)
SIGNAL_EXIT_BASE = 128
STOPPED, NOTHING_TO_STOP, NO_SUCH_JOB, REFUSED = 0, 1, 2, 3
STOP_WAIT_SECONDS = STOP_GRACE_SECONDS + 5   # a `run` job's command gets its grace period, then SIGKILL
# ps prints a process's start to the second, rounded down: a process started more than this after
# the job's own start is a later one that was given the job's pid
PID_REUSE_SLACK_SECONDS = 1.0


def _signal_group(group: int, number: int) -> None:
    """Signal COMMAND's process group; nothing if it is gone (macOS says EPERM for a group left
    with only its unreaped leader)."""
    try:
        os.killpg(group, number)
    except (ProcessLookupError, PermissionError):
        pass


def run(name: str, command: list[str]) -> int:
    """COMMAND as job NAME; its exit status."""
    job = progress.Job(name, stream=sys.stdout).start()
    child = subprocess.Popen(command, start_new_session=True)
    received: list[int] = []
    last_resort = threading.Timer(STOP_GRACE_SECONDS, _signal_group, (child.pid, signal.SIGKILL))
    last_resort.daemon = True

    def on_signal(number: int, frame: FrameType | None) -> None:
        # Only pass it on: the wait below reaps COMMAND (a wait here could not: the interrupted
        # one holds Popen's wait lock), and the timer kills what outlives the grace period
        if not received:
            last_resort.start()
        received.append(number)
        _signal_group(child.pid, number)

    for number in FORWARDED_SIGNALS:          # after the job's own handlers: these take over
        signal.signal(number, on_signal)
    status = child.wait()
    last_resort.cancel()
    if received:
        job.stop(received[0])
        return SIGNAL_EXIT_BASE + received[0]
    job.finish(ok=status == 0)
    # No closing line: COMMAND's own last line (verify's verdict) stays the last
    return status


def process_started_at(pid: int) -> float | None:
    """When process PID started (ps's lstart), or None if there is no such process."""
    done = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, check=False,
                          env={**os.environ, "LC_ALL": "C"})
    text = done.stdout.strip()
    return time.mktime(time.strptime(text, "%a %b %d %H:%M:%S %Y")) if text else None


def ended(job_id: str, pid: int) -> bool:
    """Whether the job has ended: its status file says so (its process may linger unreaped, which
    a check of the pid alone counts as running), or its process is gone."""
    status = next((status for status in progress.read_jobs() if status["id"] == job_id), {})
    return status.get("state") in progress.ENDED or not progress.alive(pid)


def refuse(text: str) -> int:
    print(f"job.py stop: REFUSED: {text}", file=sys.stderr)
    return REFUSED


def stop(job_id: str) -> int:
    """Stop JOB_ID if it is the calling session's (the module docstring); its exit status."""
    status = next((status for status in progress.read_jobs() if status["id"] == job_id), None)
    if status is None:
        print(f"job.py stop: no job {job_id} (python3 scripts/jobs.py --mine lists this session's)", file=sys.stderr)
        return NO_SUCH_JOB
    label = f"job {job_id} ({status['name']}, {status.get('session', 'no session')})"
    if progress.session_id() is None:
        return refuse(f"this shell names no session ({progress.SESSION_ID_ENV} is unset), so it owns no job; "
                      f"{label} was left running")
    if not progress.is_mine(status):
        return refuse(f"{label} belongs to another session (or records none); only its own session may stop it")
    if status.get("state") in progress.ENDED:
        print(f"job.py stop: {label} already ended ({status['state']})")
        return NOTHING_TO_STOP
    pid = int(status["pid"])
    started = process_started_at(pid)
    if started is None:
        progress.mark_died(status)
        print(f"job.py stop: {label}: its process {pid} is gone; marked died")
        return NOTHING_TO_STOP
    if started > status["started"] + PID_REUSE_SLACK_SECONDS:
        return refuse(f"{label}: pid {pid} now belongs to a later process, not the job's")
    if parent := next((other for other in progress.read_jobs() if other["id"] == status.get("parent")), None):
        print(f"job.py stop: note: {label} runs inside job {parent['id']} ({parent['name']}), which goes on; "
              f"stop that one to end the whole run")
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + STOP_WAIT_SECONDS
    while not ended(job_id, pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    if not ended(job_id, pid):
        print(f"job.py stop: {label}: sent SIGTERM to pid {pid}, still running after {STOP_WAIT_SECONDS} s",
              file=sys.stderr)
        return NOTHING_TO_STOP
    print(f"job.py stop: stopped {label} (SIGTERM to pid {pid})")
    return STOPPED


def main(argv: list[str]) -> int:
    if len(argv) >= 4 and argv[0] == "run" and argv[1] == "--name" and argv[3] == "--":
        return run(argv[2], argv[4:])
    if len(argv) == 2 and argv[0] in ("step", "substep"):
        progress.note_step(argv[1], level=1 if argv[0] == "step" else 2)
        return 0
    if len(argv) == 2 and argv[0] == "stop":
        return stop(argv[1])
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
