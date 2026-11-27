"""One full suite at a time on the machine (tests/suite_lock.py): a second run waits for the first, a
slow test run without xdist takes the lock too, every checkout and clean copy takes the one machine
lock whatever its verify.env says, and a run in one checkout waits for a run in another, naming the
holder's checkout, command and start time. Each test uses a lock file of its own in tmp_path (or a
home folder of its own), never the machine's (the suite running these tests may hold that one)."""
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SUITE_LOCK = REPO / "tests" / "suite_lock.py"
# A holder keeps the lock until its test releases it (docs/design/test-speed.md 3.4): when the
# probe says it is waiting, or when the probe has finished; never past this, if a test fails
HOLD_LIMIT_SECONDS = 60
WAITING = "waiting for the test suite already running"


def _environment(lock: Path | None) -> dict[str, str]:
    """This run's lock settings removed (it holds the checkout's lock), the test's own set. Its job
    settings go too: a waiter here must never mark this pytest run's own job queued."""
    environment = {name: value for name, value in os.environ.items()
                   if name not in ("ZORA_TEST_SUITE_LOCK", "ZORA_SUITE_LOCK", "ZORA_SUITE_LOCK_HELD", "ZORA_JOB_ID",
                                   "ZORA_JOBS_FOLDER")}
    if lock is not None:
        environment["ZORA_TEST_SUITE_LOCK"] = str(lock)
    return environment


def _hold(lock: Path, done: Path, limit_seconds: float = HOLD_LIMIT_SECONDS) -> subprocess.Popen[str]:
    """A run holding the lock until `done`.release exists (or LIMIT_SECONDS pass), then writing the time
    it ended to `done`."""
    release = done.with_suffix(".release")
    holder = subprocess.Popen(
        [sys.executable, str(SUITE_LOCK), sys.executable, "-c",
         f"import os, time; end = time.monotonic() + {limit_seconds}\n"
         f"while not os.path.exists({str(release)!r}) and time.monotonic() < end: time.sleep(0.02)\n"
         f"open({str(done)!r}, 'w').write(str(time.time()))"],
        env=_environment(lock), stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 10
    while "pid" not in (lock.read_text() if lock.exists() else ""):
        assert time.monotonic() < deadline, "the holder never took the lock"
        time.sleep(0.05)
    return holder


def _beside(holder: subprocess.Popen[str], done: Path, command: list[str], *, stderr: bool = False,
            cwd: Path | None = None, env: dict[str, str] | None = None) -> tuple[int, str]:
    """Run COMMAND while HOLDER holds the lock: released when COMMAND says it is waiting (or ends).
    Its exit status and its output (stdout, or stderr)."""
    probe = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd, env=env)
    stream = probe.stderr if stderr else probe.stdout
    assert stream is not None
    output = []
    for line in stream:
        output.append(line)
        if WAITING in line:
            done.with_suffix(".release").touch()
    probe.wait(timeout=HOLD_LIMIT_SECONDS)
    done.with_suffix(".release").touch()
    holder.wait(timeout=30)
    return probe.returncode, "".join(output)


def test_a_second_run_waits_for_the_first(tmp_path: Path) -> None:
    lock, first_done, second_start = tmp_path / "lock", tmp_path / "first", tmp_path / "second"
    holder = _hold(lock, first_done)
    status, errors = _beside(holder, first_done, [sys.executable, str(SUITE_LOCK), sys.executable, "-c",
                             f"import time; open({str(second_start)!r}, 'w').write(str(time.time()))"],
                             stderr=True, env=_environment(lock))
    assert status == 0, errors
    assert WAITING in errors
    assert float(second_start.read_text()) >= float(first_done.read_text())


@pytest.mark.slow
def test_slow_probe() -> None:
    """Selected only by test_a_serial_slow_run_takes_the_lock's own run."""


def test_a_serial_slow_run_takes_the_lock(tmp_path: Path) -> None:
    """`pytest -m slow` without xdist waits for a held lock (it used to run straight away)."""
    lock, done = tmp_path / "lock", tmp_path / "done"
    holder = _hold(lock, done)
    status, output = _beside(holder, done, [sys.executable, "-m", "pytest", "-q", "-m", "slow", "-p",
                                            "no:cacheprovider", f"{Path(__file__).relative_to(REPO)}::test_slow_probe"],
                             cwd=REPO, env=_environment(lock))
    assert status == 0, output
    assert f"suite lock: {WAITING}" in output


def _targeted_run(lock: Path, *options: str, test: str = "test_every_checkout_takes_the_machines_lock",
                  inside_the_lock: bool = False) -> str:
    """A pytest run of one test of this file while another run holds `lock` (or, inside_the_lock,
    as that run's own child, the way verify.sh runs pytest); its output."""
    done = lock.with_suffix(".done")
    holder = _hold(lock, done)
    environment = _environment(lock) | ({"ZORA_SUITE_LOCK_HELD": "1"} if inside_the_lock else {})
    status, output = _beside(holder, done, [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *options,
                                            f"{Path(__file__).relative_to(REPO)}::{test}"],
                             cwd=REPO, env=environment)
    assert status == 0, output
    return output


@pytest.mark.parametrize("workers", [[], ["-n", "1"], ["-n", "2"]], ids=["serial", "1 worker", "2 workers"])
def test_a_light_run_runs_beside_a_held_lock(tmp_path: Path, workers: list[str]) -> None:
    """Owner rule: while a run holds the lock, other test runs use at most two workers; those
    runs take no lock."""
    assert "suite lock" not in _targeted_run(tmp_path / "lock", *workers)


def test_a_heavier_run_warns_and_waits(tmp_path: Path) -> None:
    output = _targeted_run(tmp_path / "lock", "-n", "3")
    assert "WARNING" in output and "at most 2 workers" in output and "asks for 3" in output
    assert f"suite lock: {WAITING}" in output


def test_a_run_inside_the_held_lock_neither_warns_nor_waits(tmp_path: Path) -> None:
    """verify.sh's own `pytest -n auto` runs under the lock verify holds."""
    assert "suite lock" not in _targeted_run(tmp_path / "lock", "-n", "3", inside_the_lock=True)


def test_a_light_slow_run_still_takes_the_lock(tmp_path: Path) -> None:
    output = _targeted_run(tmp_path / "lock", "-n", "2", "-m", "slow", test="test_slow_probe")
    assert f"suite lock: {WAITING}" in output
    assert "WARNING" not in output


def _lock_path_in(checkout: Path, **settings: str) -> Path:
    found = subprocess.run([sys.executable, "-c", "from tests.suite_lock import LOCK_PATH; print(LOCK_PATH)"],
                           cwd=checkout, env=_environment(None) | settings, capture_output=True, text=True, check=True)
    return Path(found.stdout.strip()).resolve()


def _checkout(root: Path, settings: str = "") -> Path:
    """A checkout holding only tests/suite_lock.py, and a verify.env of SETTINGS."""
    (root / "tests").mkdir(parents=True)
    shutil.copy2(SUITE_LOCK, root / "tests" / "suite_lock.py")
    (root / "verify.env").write_text(settings)
    return root


def test_every_checkout_takes_the_machines_lock(tmp_path: Path) -> None:
    """A checkout, a clean copy inside one, and a release worktree whose verify.env still names its old lock (as
    verify.sh exports it) all take the one lock under ~/.cache: a checkout's own lock let two checkouts' suites
    run together."""
    from tests.suite_lock import MACHINE_LOCK
    checkout = _checkout(tmp_path / "checkout")
    copy = _checkout(checkout / "temp" / "x-copy")
    worktree = _checkout(tmp_path / "release-worktree", "ZORA_SUITE_LOCK=/main/temp/test-suite.lock\n")
    assert MACHINE_LOCK == Path.home() / ".cache" / "zora" / "test-suite.lock"
    found = {_lock_path_in(checkout), _lock_path_in(copy),
             _lock_path_in(worktree, ZORA_SUITE_LOCK="/main/temp/test-suite.lock")}
    assert found == {MACHINE_LOCK.resolve()}


def test_a_run_in_one_checkout_waits_for_a_run_in_another(tmp_path: Path) -> None:
    """Neither run names a lock: both take the machine's (here a home folder of the test's own). The waiter
    names the holder's checkout, its command and when it started."""
    first, second = _checkout(tmp_path / "checkout"), _checkout(tmp_path / "second-checkout")
    environment = _environment(None) | {"HOME": str(tmp_path / "home")}
    lock = tmp_path / "home" / ".cache" / "zora" / "test-suite.lock"
    release, first_done, second_start = tmp_path / "release", tmp_path / "first", tmp_path / "second"
    holder = subprocess.Popen(
        [sys.executable, str(first / "tests" / "suite_lock.py"), sys.executable, "-c",
         f"import os, time; end = time.monotonic() + {HOLD_LIMIT_SECONDS}\n"
         f"while not os.path.exists({str(release)!r}) and time.monotonic() < end: time.sleep(0.02)\n"
         f"open({str(first_done)!r}, 'w').write(str(time.time()))"],
        env=environment, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 10
    while "pid" not in (lock.read_text() if lock.exists() else ""):
        assert time.monotonic() < deadline, "the holder never took the machine's lock"
        time.sleep(0.05)
    waiter = subprocess.Popen([sys.executable, str(second / "tests" / "suite_lock.py"), sys.executable, "-c",
                               f"import time; open({str(second_start)!r}, 'w').write(str(time.time()))"],
                              env=environment, stderr=subprocess.PIPE, text=True)
    assert waiter.stderr is not None
    said = ""
    for line in waiter.stderr:
        if WAITING in line:
            said = line
            release.touch()
            break
    release.touch()
    assert waiter.wait(timeout=30) == 0 and holder.wait(timeout=30) == 0
    assert f"pid {holder.pid}" in said and f"in {first.resolve()}: " in said, said
    assert "time.monotonic()" in said                                        # the holder's command
    assert re.search(r"since \d{4}-\d\d-\d\d \d\d:\d\d:\d\d", said), said
    assert float(second_start.read_text()) >= float(first_done.read_text())


def test_a_nested_run_refuses_its_ancestors_lock_at_once(tmp_path: Path) -> None:
    """A run started inside the held lock that drops ZORA_SUITE_LOCK_HELD (tests/test_compare_revision.py's copy
    runs, once) would wait for its own ancestor forever: it stops at once, naming both, and the holder ends."""
    lock = tmp_path / "lock"
    nested = textwrap.dedent(f"""
        import os, subprocess, sys
        environment = dict(os.environ)
        environment.pop("ZORA_SUITE_LOCK_HELD")
        done = subprocess.run([sys.executable, {str(SUITE_LOCK)!r}, sys.executable, "-c", "print('ran')"],
                              env=environment, capture_output=True, text=True, timeout={HOLD_LIMIT_SECONDS})
        print("nested exit", done.returncode)
        print(done.stdout + done.stderr)
        """)
    started = time.monotonic()
    holder = subprocess.run([sys.executable, str(SUITE_LOCK), sys.executable, "-c", nested], env=_environment(lock),
                            capture_output=True, text=True, timeout=HOLD_LIMIT_SECONDS)
    assert holder.returncode == 0, holder.stdout + holder.stderr
    assert time.monotonic() - started < HOLD_LIMIT_SECONDS / 2
    output = holder.stdout
    assert "nested exit 1" in output and "\nran\n" not in output, output       # the nested command never ran
    assert "held by its own ancestor (pid " in output and "would never start" in output, output
    assert "this run (pid " in output and str(lock) in output, output


def test_a_run_beside_the_holder_still_waits(tmp_path: Path) -> None:
    """Not an ancestor: the guard leaves an ordinary waiter waiting (test_a_second_run_waits_for_the_first)."""
    from tests import suite_lock
    assert os.getpid() not in suite_lock.ancestors()
    assert os.getppid() in suite_lock.ancestors()


# --- reports while waiting, and the queue (owner rule, 2026-10-13) ------------------------------

def _waiter(lock: Path, name: str, out: Path) -> subprocess.Popen[str]:
    """A run of the lock's command line, as session NAME, writing when it got the lock to OUT."""
    environment = _environment(lock) | {"ZORA_SESSION_NAME": name, "ZORA_PROGRESS_SECONDS": "0.3"}
    return subprocess.Popen([sys.executable, str(SUITE_LOCK), sys.executable, "-c",
                             f"import time; open({str(out)!r}, 'w').write(str(time.time())); time.sleep(0.3)"],
                            env=environment, stderr=subprocess.PIPE, text=True)


def _queued(lock: Path, count: int) -> None:
    deadline = time.monotonic() + 10
    while len(list((lock.parent / "test-suite-queue").glob("*.json"))) < count:
        assert time.monotonic() < deadline, "the waiters never queued"
        time.sleep(0.05)


def test_a_waiting_run_says_who_holds_the_lock_and_its_place(tmp_path: Path) -> None:
    lock, done = tmp_path / "lock", tmp_path / "done"
    holder = _hold(lock, done)
    waiter = _waiter(lock, "waiting session", tmp_path / "got")
    assert waiter.stderr is not None
    report = ""
    for line in waiter.stderr:
        if "still waiting" in line:
            report = line
            break
    done.with_suffix(".release").touch()
    waiter.wait(timeout=30)
    holder.wait(timeout=30)
    assert f"held by pid {holder.pid}" in report and f"in {REPO}: " in report and "since" in report, report
    assert "this run is number 1 of 1 waiting" in report


def test_waiting_runs_take_the_lock_in_the_order_they_came(tmp_path: Path) -> None:
    lock, done = tmp_path / "lock", tmp_path / "done"
    holder = _hold(lock, done)
    first = _waiter(lock, "first session", tmp_path / "first")
    _queued(lock, 1)
    second = _waiter(lock, "second session", tmp_path / "second")
    _queued(lock, 2)
    assert second.stderr is not None
    report = ""
    for line in second.stderr:
        if "still waiting" in line:
            report = line
            break
    done.with_suffix(".release").touch()
    for run in (first, second, holder):
        run.wait(timeout=30)
    assert "this run is number 2 of 2 waiting; ahead of it: first session" in report, report
    assert float((tmp_path / "first").read_text()) < float((tmp_path / "second").read_text())


def test_a_run_inside_a_job_marks_it_queued_until_it_starts(tmp_path: Path) -> None:
    """The job a waiting run is inside shows QUEUED with the run's place (zora_measure/progress.py)
    while it waits, and stops being queued once it has the lock, keeping the time it queued."""
    lock, done, jobs = tmp_path / "lock", tmp_path / "done", tmp_path / "jobs"
    holder = _hold(lock, done)
    environment = _environment(lock) | {"ZORA_JOB_ID": "1-job", "ZORA_JOBS_FOLDER": str(jobs),
                                        "ZORA_PROGRESS_SECONDS": "0.3"}
    waiter = subprocess.Popen([sys.executable, str(SUITE_LOCK), sys.executable, "-c", "pass"],
                              env=environment, stderr=subprocess.PIPE, text=True)
    waiting = jobs / "1-job.waiting"
    deadline = time.monotonic() + 10
    while not (waiting.exists() and '"since": null' not in waiting.read_text()):
        assert time.monotonic() < deadline, "the run never marked its job queued"
        time.sleep(0.05)
    queued = json.loads(waiting.read_text())
    done.with_suffix(".release").touch()
    waiter.wait(timeout=30)
    holder.wait(timeout=30)
    assert (queued["place"], queued["of"]) == (1, 1) and f"pid {holder.pid}" in queued["holder"]
    after = json.loads(waiting.read_text())
    assert after["since"] is None and after["queued_seconds"] > 0


def test_a_waiting_run_whose_job_has_gone_gives_up(tmp_path: Path) -> None:
    """A run left waiting after its job's process was killed outright (SIGKILL, so nothing passed
    the signal on) gives up its place instead of running later."""
    lock, done, jobs = tmp_path / "lock", tmp_path / "done", tmp_path / "jobs"
    jobs.mkdir()
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    (jobs / "1-gone.json").write_text(json.dumps({"id": "1-gone", "pid": gone.pid, "state": "running"}))
    holder = _hold(lock, done)
    environment = _environment(lock) | {"ZORA_JOB_ID": "1-gone", "ZORA_JOBS_FOLDER": str(jobs)}
    waiter = subprocess.run([sys.executable, str(SUITE_LOCK), sys.executable, "-c", "print('ran')"],
                            env=environment, capture_output=True, text=True, timeout=30)
    done.with_suffix(".release").touch()
    holder.wait(timeout=30)
    assert waiter.returncode == 1 and "ran" not in waiter.stdout
    assert "not waiting any longer: the job it belongs to (1-gone) has ended" in waiter.stderr
    assert not list((lock.parent / "test-suite-queue").glob("*.json"))
