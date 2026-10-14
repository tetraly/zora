"""Progress for long jobs (zora_measure/progress.py, scripts/job.py, scripts/jobs.py; owner rule,
2026-10-13): a job prints at least once a minute what it is, its percent, its elapsed time and the
time left, keeps the same in a status file, and scripts/jobs.py lists it, nested under the job it
runs in, flagging one that died or went silent. Each test uses a status folder of its own and a
report interval of a fraction of a second."""
import io
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from zora_measure import progress

REPO = Path(__file__).resolve().parent.parent
INTERVAL = "0.2"


@pytest.fixture
def folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """This test's own status folder, outside any job (the suite's own pytest run is one)."""
    monkeypatch.setenv(progress.JOBS_FOLDER_ENV, str(tmp_path))
    monkeypatch.setenv(progress.INTERVAL_ENV, INTERVAL)
    monkeypatch.delenv(progress.JOB_ID_ENV, raising=False)
    return tmp_path


def _environment(folder: Path) -> dict[str, str]:
    environment = {name: value for name, value in os.environ.items() if name != progress.JOB_ID_ENV}
    return {**environment, progress.JOBS_FOLDER_ENV: str(folder), progress.INTERVAL_ENV: INTERVAL,
            "PYTHONPATH": str(REPO)}


def test_a_job_reports_what_it_is_its_percent_elapsed_and_time_left(folder: Path) -> None:
    stream = io.StringIO()
    job = progress.Job("rate scan", total=10, unit="seeds", stream=stream).start()
    for _ in range(4):
        time.sleep(0.12)
        job.advance()
    time.sleep(0.3)
    status = json.loads(job.path.read_text())
    job.finish()
    lines = [line for line in stream.getvalue().splitlines() if line.startswith("progress: rate scan")]
    assert lines, stream.getvalue()
    assert "40% (4/10 seeds)" in lines[-1] and "elapsed" in lines[-1] and "left" in lines[-1]
    assert (status["name"], status["done"], status["total"], status["state"]) == ("rate scan", 4, 10, "running")
    assert status["pid"] == os.getpid() and status["session"]
    assert json.loads(job.path.read_text())["state"] == "finished"


def test_without_a_count_the_time_left_comes_from_earlier_runs(folder: Path) -> None:
    (folder / "history.json").write_text(json.dumps({"verify": [100.0, 120.0, 110.0]}))
    status = {"name": "verify", "started": 1000.0, "updated": 1055.0, "state": "running", "done": 0,
              "total": None, "typical": progress.history_estimate("verify")}
    line = progress.describe(status, now=1055.0)
    assert "50%" in line and "about 0:55 left (from earlier runs)" in line


def test_track_counts_its_items_and_finishes(folder: Path) -> None:
    assert list(progress.track(range(5), "five")) == [0, 1, 2, 3, 4]
    [status] = progress.read_jobs()
    assert (status["done"], status["total"], status["state"]) == (5, 5, "finished")


def test_a_failure_inside_track_marks_the_job_failed(folder: Path) -> None:
    with pytest.raises(ZeroDivisionError):
        for item in progress.track([1, 0], "divide"):
            1 / item
    [status] = progress.read_jobs()
    assert status["state"] == "failed"


def test_a_silent_job_is_probably_hung_and_a_vanished_one_died(folder: Path) -> None:
    now = time.time()
    running = {"state": "running", "pid": os.getpid(), "updated": now, "report_seconds": 60}
    assert progress.health(running, now) == "ok"
    assert progress.health({**running, "updated": now - 181}, now) == "probably hung"
    gone = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True,
                          text=True, check=True).stdout.strip()
    assert progress.health({**running, "pid": int(gone)}, now) == "died"


def test_jobs_lists_a_job_inside_another_and_flags_the_hung(folder: Path) -> None:
    now = time.time()
    outer = {"id": "1-a", "name": "verify.sh (fast tier)", "pid": os.getpid(), "parent": None, "session": "S",
             "started": now - 100, "updated": now, "state": "running", "done": 0, "total": None,
             "report_seconds": 60}
    inner = {**outer, "id": "2-b", "name": "pytest tests", "parent": "1-a", "done": 30, "total": 60,
             "unit": "tests", "updated": now - 400}
    for status in (outer, inner):
        (folder / f"{status['id']}.json").write_text(json.dumps(status))
    (folder / "1-a.step").write_text(json.dumps({"1": "tests"}))
    listing = subprocess.run([sys.executable, str(REPO / "scripts" / "jobs.py")], capture_output=True, text=True,
                             check=True, env=_environment(folder)).stdout
    first, second = listing.splitlines()[:2]
    assert first.startswith("- S, pid") and "verify.sh (fast tier)" in first and "step: tests" in first
    assert second.startswith("    - S, pid") and "50% (30/60 tests)" in second and "PROBABLY HUNG" in second


def test_job_run_keeps_its_commands_status_and_last_line(folder: Path) -> None:
    command = [sys.executable, str(REPO / "scripts" / "job.py"), "run", "--name", "probe", "--",
               sys.executable, "-c", "import time; time.sleep(0.5); print('the verdict'); raise SystemExit(3)"]
    done = subprocess.run(command, capture_output=True, text=True, check=False, env=_environment(folder))
    assert done.returncode == 3
    assert done.stdout.strip().splitlines()[-1] == "the verdict"
    assert any(line.startswith("progress: probe") for line in done.stdout.splitlines())   # reported, on its own line
    [status] = [json.loads(path.read_text()) for path in folder.glob("*.json") if path.name != "history.json"]
    assert status["state"] == "failed"


def test_steps_noted_from_inside_a_job_reach_its_status(folder: Path) -> None:
    job = progress.Job("full tier", stream=io.StringIO()).start()
    for level, text in (("step", "2/4: the slow suite"), ("substep", "tests")):
        subprocess.run([sys.executable, str(REPO / "scripts" / "job.py"), level, text], check=True,
                       env={**_environment(folder), progress.JOB_ID_ENV: job.id})
    job.report(say=False)
    assert json.loads(job.path.read_text())["step"] == "2/4: the slow suite > tests"
    job.finish()


def test_a_pytest_run_reports_its_test_count(tmp_path: Path) -> None:
    """tests/progress_plugin.py, through a probe folder whose conftest takes the plugin's hooks."""
    probe = tmp_path / "probe"
    probe.mkdir()
    (probe / "conftest.py").write_text("pytest_plugins = ['tests.progress_plugin']\n")
    (probe / "test_slow_probe.py").write_text(
        "import time\nimport pytest\n\n\n@pytest.mark.parametrize('n', range(4))\n"
        "def test_wait(n: int) -> None:\n    time.sleep(0.25)\n")
    done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "test_slow_probe.py"],
                          cwd=probe, capture_output=True, text=True, check=False, env=_environment(tmp_path / "jobs"))
    assert done.returncode == 0, done.stdout + done.stderr
    reports = [line for line in done.stdout.splitlines() if line.startswith("progress: pytest ")]
    assert reports and all("test_slow_probe.py" in line and "/4 tests)" in line for line in reports), done.stdout


# --- queued for the suite lock (owner, 2026-10-13): QUEUED, its place, 0%, no estimate ----------

def test_a_queued_job_shows_queued_its_place_and_no_progress(folder: Path) -> None:
    """Even with earlier runs to estimate from, a queued job is at 0% with no time left, however
    long it has waited."""
    (folder / "history.json").write_text(json.dumps({"verify": [100.0]}))
    status = {"name": "verify", "started": 1000.0, "updated": 1300.0, "state": "running", "done": 0,
              "total": None, "typical": progress.history_estimate("verify"), "queued_since": 1000.0,
              "queue_place": 2, "queue_length": 3, "queue_holder": "pid 7, session S, verify_full.sh",
              "waiting": "the suite lock (number 2 of 3), held by pid 7, session S, verify_full.sh"}
    line = progress.describe(status, now=1300.0)
    assert line == ("verify, QUEUED, 0%, number 2 of 3 for the suite lock, held by pid 7, session S, "
                    "verify_full.sh, queued 5:00, 5:00 elapsed")


def test_time_spent_queued_never_counts_toward_progress(folder: Path) -> None:
    """Queued 60 s, then running 50 s of a typical 100 s: 50%, 0:50 left."""
    (folder / "history.json").write_text(json.dumps({"verify": [100.0]}))
    status = {"name": "verify", "started": 1000.0, "updated": 1110.0, "state": "running", "done": 0,
              "total": None, "typical": progress.history_estimate("verify"), "queued_since": None,
              "queued_seconds": 60.0}
    line = progress.describe(status, now=1110.0)
    assert line == "verify, 50%, 1:50 elapsed (1:00 of it queued), about 0:50 left (from earlier runs)"


def test_a_job_noted_queued_then_started(folder: Path) -> None:
    """note_queued (as the suite lock calls it) marks the job; note_waiting(None) ends the queueing,
    keeping its time out of the job's estimate and of the run time its history records."""
    stream = io.StringIO()
    job = progress.Job("queued job", stream=stream).start(tick=False)
    progress.note_queued(1, 2, "pid 7, session S, verify.sh")
    job.report()
    assert "queued job, QUEUED, 0%, number 1 of 2 for the suite lock, held by pid 7" in stream.getvalue()
    [status] = progress.read_jobs()
    assert (status["queue_place"], status["queue_length"]) == (1, 2) and status["queued_since"]
    progress.note_queued(1, 1, "pid 7, session S, verify.sh")      # the run ahead left: its place moves up
    assert progress.read_waiting(job.id).place == 1 and progress.read_waiting(job.id).of == 1
    time.sleep(0.3)
    progress.note_waiting(None)
    waiting = progress.read_waiting(job.id)
    assert not waiting.queued and waiting.queued_seconds >= 0.3
    job.report()
    assert "QUEUED" not in stream.getvalue().splitlines()[-1]
    job.finish()
    recorded = json.loads((folder / "history.json").read_text())["queued job"][0]
    assert recorded <= time.time() - job.started - 0.3


def test_jobs_shows_a_queued_job_the_same_way(folder: Path) -> None:
    now = time.time()
    status = {"id": "1-a", "name": "verify.sh (fast tier)", "pid": os.getpid(), "parent": None, "session": "S",
              "started": now - 100, "updated": now, "state": "running", "done": 0, "total": None,
              "typical": 300.0, "report_seconds": 60}
    (folder / "1-a.json").write_text(json.dumps(status))
    (folder / "1-a.waiting").write_text(json.dumps({"text": "the suite lock (number 1 of 1), held by pid 9",
                                                     "place": 1, "of": 1, "holder": "pid 9", "since": now - 90}))
    listing = subprocess.run([sys.executable, str(REPO / "scripts" / "jobs.py")], capture_output=True, text=True,
                             check=True, env=_environment(folder)).stdout
    first = listing.splitlines()[0]
    assert "verify.sh (fast tier), QUEUED, 0%, number 1 of 1 for the suite lock, held by pid 9, queued 1:30" in first
    assert "left" not in first


def test_an_older_plain_text_waiting_file_still_reads(folder: Path) -> None:
    (folder / "1-a.waiting").write_text("the suite lock, held by pid 9")
    assert progress.read_waiting("1-a") == progress.Waiting(text="the suite lock, held by pid 9")


# --- a job ended by a signal, or gone without a word (owner, 2026-10-13) --------------------------

def _dead_pid() -> int:
    """The pid of a process that has ended (and been reaped)."""
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    return gone.pid


def _start_job(folder: Path, body: str) -> subprocess.Popen[str]:
    """A Python process that starts a job named "signaled", says "started", then runs BODY."""
    script = ("import sys, time\nfrom zora_measure import progress\n"
              "job = progress.Job('signaled').start()\nprint('started', flush=True)\n" + body)
    process = subprocess.Popen([sys.executable, "-c", script], env=_environment(folder), stdout=subprocess.PIPE,
                               text=True)
    assert process.stdout is not None and process.stdout.readline().strip() == "started"
    return process


def test_a_job_stopped_by_sigterm_marks_its_status_file(folder: Path) -> None:
    process = _start_job(folder, "progress.note_step('a step')\nprint('stepped', flush=True)\ntime.sleep(30)")
    assert process.stdout is not None and process.stdout.readline().strip() == "stepped"
    process.send_signal(signal.SIGTERM)
    assert process.wait(timeout=10) == -signal.SIGTERM          # the signal still ends the process
    [status] = progress.read_jobs()
    assert (status["state"], status["signal"]) == ("stopped", "SIGTERM") and status["finished_at"]
    assert sorted(path.name for path in folder.iterdir()) == [f"{status['id']}.json"]       # side files gone
    assert "stopped by SIGTERM" in progress.describe(status)


def test_a_job_that_exits_without_finishing_is_marked_failed(folder: Path) -> None:
    process = _start_job(folder, "sys.exit(3)")
    assert process.wait(timeout=10) == 3
    [status] = progress.read_jobs()
    assert status["state"] == "failed"


def test_jobs_marks_a_job_whose_process_is_gone_died_and_then_lets_it_go(folder: Path) -> None:
    """A job killed outright (SIGKILL: no handler runs) is listed DIED and its file marked so, its
    side files removed; past DIED_SHOWN_SECONDS only --all lists it."""
    now = time.time()
    status = {"id": "9-dead", "name": "verify.sh (fast tier)", "pid": _dead_pid(), "parent": None, "session": "S",
              "started": now - 100, "updated": now - 5, "state": "running", "done": 0, "total": None,
              "report_seconds": 60}
    (folder / "9-dead.json").write_text(json.dumps(status))
    (folder / "9-dead.waiting").write_text(json.dumps({"text": "the suite lock", "place": 1, "of": 1,
                                                        "holder": "pid 1", "since": now - 90}))
    listing = subprocess.run([sys.executable, str(REPO / "scripts" / "jobs.py")], capture_output=True, text=True,
                             check=True, env=_environment(folder)).stdout
    assert "verify.sh (fast tier)" in listing and "DIED" in listing and "QUEUED" not in listing
    marked = json.loads((folder / "9-dead.json").read_text())
    assert marked["state"] == "died" and marked["finished_at"]
    assert not (folder / "9-dead.waiting").exists()
    marked["finished_at"] = now - 3600 + 60                       # died 59 minutes ago
    (folder / "9-dead.json").write_text(json.dumps(marked))
    later = subprocess.run([sys.executable, str(REPO / "scripts" / "jobs.py")], capture_output=True, text=True,
                           check=True, env=_environment(folder)).stdout
    assert later.splitlines()[0] == "no running jobs"
    everything = subprocess.run([sys.executable, str(REPO / "scripts" / "jobs.py"), "--all"], capture_output=True,
                                text=True, check=True, env=_environment(folder)).stdout
    assert "verify.sh (fast tier)" in everything and "DIED" in everything


def test_job_run_passes_sigterm_to_its_command_and_marks_the_job(folder: Path, tmp_path: Path) -> None:
    """SIGTERM to `job.py run` reaches the command's whole process group (here a shell and the
    sleep it started), leaves nothing running, and marks the job stopped."""
    pids = tmp_path / "pids"
    command = f"sleep 30 & echo $$ $! > {pids}; wait"
    run = subprocess.Popen([sys.executable, str(REPO / "scripts" / "job.py"), "run", "--name", "probe", "--",
                            "sh", "-c", command], env=_environment(folder), stdout=subprocess.DEVNULL)
    deadline = time.monotonic() + 10
    while not (pids.exists() and len(pids.read_text().split()) == 2):
        assert time.monotonic() < deadline, "the command never started"
        time.sleep(0.05)
    shell, sleeper = map(int, pids.read_text().split())
    run.send_signal(signal.SIGTERM)
    assert run.wait(timeout=10) == 128 + signal.SIGTERM
    deadline = time.monotonic() + 5
    while progress.alive(shell) or progress.alive(sleeper):
        assert time.monotonic() < deadline, "the command outlived its job"
        time.sleep(0.05)
    [status] = [status for status in progress.read_jobs() if status["name"] == "probe"]
    assert (status["state"], status["signal"]) == ("stopped", "SIGTERM")
