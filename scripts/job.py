"""A long command as a job with progress (zora_measure/progress.py; AGENTS.md "Run time").

    python3 scripts/job.py run --name NAME -- COMMAND [ARGS ...]   run COMMAND as job NAME
    python3 scripts/job.py step TEXT                                 the running job's step
    python3 scripts/job.py substep TEXT                              the step within it

`run` passes COMMAND's output through and, at least once a minute, prints the job's progress:
its step, the job running inside it (a pytest run's count of tests, say), its elapsed time and the
time left, from earlier runs of NAME when nothing inside it has a count. scripts/verify.sh and
scripts/verify_full.sh run themselves under it and name their steps with `step` and `substep`.
Its exit status is COMMAND's.

COMMAND runs in a process group of its own. A SIGTERM, SIGHUP or SIGINT to `run` goes on to
that whole group (a lock waiter, a pytest run and its workers), never leaving them running
orphaned; once COMMAND has ended (or, after STOP_GRACE_SECONDS, been killed) the job is marked
stopped by that signal and `run` exits with 128 + its number.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
from pathlib import Path
from types import FrameType

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from zora_measure import progress  # noqa: E402

USAGE = __doc__
FORWARDED_SIGNALS = (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)
STOP_GRACE_SECONDS = 10          # then the group is killed (SIGKILL)
SIGNAL_EXIT_BASE = 128


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


def main(argv: list[str]) -> int:
    if len(argv) >= 4 and argv[0] == "run" and argv[1] == "--name" and argv[3] == "--":
        return run(argv[2], argv[4:])
    if len(argv) == 2 and argv[0] in ("step", "substep"):
        progress.note_step(argv[1], level=1 if argv[0] == "step" else 2)
        return 0
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
