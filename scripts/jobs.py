"""Every running job across sessions, with its progress (zora_measure/progress.py; AGENTS.md "Run time").

    python3 scripts/jobs.py            the running jobs, the suite lock and its queue
    python3 scripts/jobs.py --all      ... and the jobs that ended in the last hour

Each job shows its session, what it is, its percent, elapsed time and time left, its step, what
it waits for, and when it last reported. A job whose process is gone without finishing is DIED:
its status file is marked so (its side files removed), it is listed as DIED for 10 minutes, and
then only with --all, like a job stopped by a signal (SIGTERM, SIGHUP), which marks its own file. A
running one silent for three report intervals (3 minutes) is PROBABLY HUNG. Jobs inside another
(a pytest run inside verify) are indented under it. Status files more than a day old are removed.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tests import suite_lock  # noqa: E402
from zora_measure import progress  # noqa: E402

RECENT_SECONDS = 3600
KEEP_SECONDS = 86400
DIED_SHOWN_SECONDS = 600         # a job that died stays in the default listing this long


def flag(state: str) -> str:
    return {"ok": "", progress.DIED: "  ** DIED: its process is gone **",
            "probably hung": "  ** PROBABLY HUNG: no report for 3 intervals **"}.get(state, f"  ({state})")


def tidy(jobs: list[dict[str, Any]], now: float) -> list[dict[str, Any]]:
    """Drop status files more than a day old (and their side files)."""
    kept = []
    for status in jobs:
        if now - status.get("updated", 0) > KEEP_SECONDS:
            for path in (progress.jobs_folder() / f"{status['id']}.json", progress.step_file(status["id"]),
                         progress.waiting_file(status["id"])):
                path.unlink(missing_ok=True)
        else:
            kept.append(status)
    return kept


def shown_by_default(status: dict[str, Any], now: float) -> bool:
    """Running jobs, and for DIED_SHOWN_SECONDS a job that died."""
    if status.get("state") == progress.DIED:
        return now - (status.get("finished_at") or 0) < DIED_SHOWN_SECONDS
    return status.get("state") not in progress.ENDED


def lines(jobs: list[dict[str, Any]], show_ended: bool, now: float) -> list[str]:
    shown = [status for status in jobs
             if shown_by_default(status, now)
             or (show_ended and now - (status.get("finished_at") or 0) < RECENT_SECONDS)]
    ids = {status["id"] for status in shown}
    children: dict[str | None, list[dict[str, Any]]] = {}
    for status in sorted(shown, key=lambda status: status["started"]):
        parent = status.get("parent") if status.get("parent") in ids else None
        children.setdefault(parent, []).append(status)
    out: list[str] = []

    def add(parent: str | None, depth: int) -> None:
        for status in children.get(parent, []):
            state = progress.health(status, now)
            reported = f"last report {progress.clock(now - status.get('updated', now))} ago"
            out.append(f"{'    ' * depth}- {status['session']}, pid {status['pid']}: {progress.describe(status, now)}; "
                       f"{reported}{flag(state)}")
            add(status["id"], depth + 1)
    add(None, 0)
    return out


def lock_lines() -> list[str]:
    holder = suite_lock.holder()
    out = [f"suite lock: {'held by ' + holder if holder else 'free'}"]
    for place, run in enumerate(suite_lock.waiting_runs(), 1):
        out.append(f"  waiting {place}: {run['session']}, pid {run['pid']}, {run['label']}, "
                   f"for {progress.clock(time.time() - run['since'])}")
    return out


def main(argv: list[str]) -> int:
    now = time.time()
    jobs = [progress.mark_died(status, now) for status in tidy(progress.read_jobs(), now)]
    listing = lines(jobs, "--all" in argv, now)
    print("\n".join(listing) if listing else "no running jobs")
    print("\n".join(lock_lines()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
