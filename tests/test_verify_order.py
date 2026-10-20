"""verify fails fast and cheap (owner requests, 2026-10-14 and 2026-10-16; AGENTS.md "Verification"):
the quick check, plain `sh scripts/verify.sh`, runs the static checks (scripts/verify_static.sh),
the capped selection of fast tests a change most likely affects (scripts/affected_tests.py
--quick) and the output comparison, all without the suite lock, so it never queues; a planted type
error fails it in seconds; the tests stop at the first failure unless --all-failures asks for them
all; the fast suite (--fast-suite) and the full tier run the static checks before their lock.

Each runs the real scripts in a throwaway checkout in tmp_path: this checkout's files (committed
or not), the base ROMs and a one-commit git repository, with a suite lock of its own that a
holder process keeps taken. A run that queued for it would wait until its time limit ends it, and
fail; none may.

These tests run verify, whose tests could run these tests again: the throwaway checkout leaves
this file out, and the runs it starts carry NESTED_SETTING, which skips this whole file, so a
nested run never starts verify again (it once did, recursively, until stopped by hand).
"""
import os
import shutil
import signal
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.test_suite_lock import WAITING, _hold
from zora.rom.base_rom import BASE_ROM_PATH

REPO = Path(__file__).resolve().parent.parent
PRG1_ROM = BASE_ROM_PATH.with_name("Legend of Zelda, The (USA) (Rev 1).nes")
NEEDED = [REPO / "scripts" / "verify.sh", REPO / "scripts" / "verify_static.sh", REPO / "scripts" / "affected_tests.py"]
TIME_LIMIT_SECONDS = 180
MATRIX_JOBS = "4"           # the quick check's matrix, shortened to fit the time limit
NESTED_SETTING = "ZORA_VERIFY_ORDER_NESTED"
# This run's own settings (its job, lock, copy and encoder record), which the throwaway checkout
# must not inherit
UNINHERITED = ("ZORA_JOB_ID", "ZORA_JOBS_FOLDER", "ZORA_SUITE_LOCK", "ZORA_SUITE_LOCK_HELD", "ZORA_VERIFY_STATIC_DONE",
               "ZORA_VERIFY_TIER", "ZORA_SOURCE_REPO", "ZORA_CODE_DIR", "ZORA_COPY_REVISION", "ZORA_COPY_ADDED",
               "ZORA_ENCODER_RECORD", "ZORA_HIDE_LEVEL_ENCODING", "PYTEST_XDIST_WORKER", "PYTEST_ADDOPTS")
PLANTED_TYPE_ERROR = 'PLANTED: int = "not a number"\n'
PLANTED_FAILURES = 6
PLANTED_TESTS = "".join(f"def test_planted_{n}() -> None:\n    assert False, 'planted failure {n}'\n\n\n"
                        for n in range(PLANTED_FAILURES))

pytestmark = [
    pytest.mark.skipif(not all(path.exists() for path in NEEDED) or not BASE_ROM_PATH.exists()
                       or shutil.which("git") is None, reason="no verify scripts, base ROM or git here"),
    pytest.mark.skipif(bool(os.environ.get(NESTED_SETTING)), reason="inside a verify these tests started"),
]


def _environment(lock: Path) -> dict[str, str]:
    environment = {name: value for name, value in os.environ.items()
                   if not name.startswith("GIT_") and name not in UNINHERITED}
    environment["ZORA_SUITE_LOCK"] = str(lock)
    environment[NESTED_SETTING] = "1"
    environment["ZORA_VERIFY_MATRIX_JOBS"] = MATRIX_JOBS
    return environment


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=test", "-c", "user.email=test@example.invalid",
                    "-c", "commit.gpgsign=false", *args], check=True, capture_output=True,
                   env={name: value for name, value in os.environ.items() if not name.startswith("GIT_")})


@pytest.fixture(scope="module")
def checkout(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """This checkout's working tree (new files included: the code under test) as one commit, but
    this file: it names the paths these tests change, so a precheck there would run it again."""
    repo = tmp_path_factory.mktemp("verify-order")
    files = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                           capture_output=True, check=True).stdout.decode().split("\0")
    for name in filter(None, files):
        if (REPO / name).is_file() and Path(name).name != Path(__file__).name:
            (repo / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, repo / name)
    assert not (repo / "tests" / Path(__file__).name).exists()
    for rom in (BASE_ROM_PATH, PRG1_ROM):
        if rom.exists():
            shutil.copy2(rom, repo / rom.name)
    _git(repo, "init", "--quiet")
    _git(repo, "add", "--all")
    _git(repo, "commit", "--quiet", "--no-verify", "-m", "checkout")
    return repo


@pytest.fixture
def held_lock(tmp_path: Path) -> Iterator[Path]:
    """The throwaway checkout's suite lock, taken by another process for the whole test."""
    lock, done = tmp_path / "suite.lock", tmp_path / "holder.done"
    holder = _hold(lock, done)
    yield lock
    done.with_suffix(".release").touch()
    holder.wait(timeout=30)


def _verify(checkout: Path, lock: Path, *arguments: str) -> tuple[int, str, float]:
    """`sh scripts/verify.sh ARGUMENTS` in CHECKOUT: its status, its output and its run time. One
    that outlives the time limit (waiting for the held lock, say) is stopped, with its group."""
    start = time.monotonic()
    run = subprocess.Popen(["sh", "scripts/verify.sh", *arguments], cwd=checkout, env=_environment(lock),
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        output, _ = run.communicate(timeout=TIME_LIMIT_SECONDS)
    except subprocess.TimeoutExpired:
        os.killpg(run.pid, signal.SIGTERM)
        output, _ = run.communicate(timeout=30)
        pytest.fail(f"verify ran past {TIME_LIMIT_SECONDS} s (queued for the lock?):\n{output[-3000:]}")
    return run.returncode, output, time.monotonic() - start


def test_a_type_error_fails_before_the_lock(checkout: Path, held_lock: Path) -> None:
    planted = checkout / "zora" / "planted_type_error.py"
    planted.write_text(PLANTED_TYPE_ERROR)
    try:
        status, output, seconds = _verify(checkout, held_lock, "HEAD")
    finally:
        planted.unlink()
    assert status == 1, output
    assert "planted_type_error.py" in output and "FAILED a static check: the type check" in output
    assert WAITING not in output and "suite lock:" not in output and " passed" not in output
    assert seconds < TIME_LIMIT_SECONDS


def test_the_quick_check_runs_the_selection_and_the_comparison_without_the_lock(checkout: Path,
                                                                              held_lock: Path) -> None:
    """Beside a held lock it never waits: the selected tests at 2 workers, then the output."""
    touched = checkout / "scripts" / "guide_page.py"
    original = touched.read_text()
    touched.write_text(original + "# touched\n")
    try:
        status, output, _ = _verify(checkout, held_lock)
    finally:
        touched.write_text(original)
    assert status == 0, output
    assert "tests/test_guide_page.py (" in output and "Quick check: " in output
    assert "verify: static checks passed" in output and WAITING not in output and "suite lock:" not in output
    assert "THE FULL SUITE RUNS IN THE BATCH RUN" in output
    assert "compare_revision: output identical to" in output.splitlines()[-1]


def test_the_tests_stop_at_the_first_failure(checkout: Path, held_lock: Path) -> None:
    """A failing selected test ends the quick check before the comparison."""
    planted = checkout / "tests" / "test_planted_failures.py"
    planted.write_text(PLANTED_TESTS)
    try:
        status, output, _ = _verify(checkout, held_lock)
        every_status, every_output, _ = _verify(checkout, held_lock, "--all-failures")
    finally:
        planted.unlink()
    assert status == 1 and "stopping after 1 failures" in output, output
    assert f"{PLANTED_FAILURES} failed" not in output and "compare_revision" not in output.split("static checks passed")[-1]
    assert every_status == 1 and f"{PLANTED_FAILURES} failed" in every_output, every_output


def test_precheck_is_gone() -> None:
    done = subprocess.run(["sh", "scripts/verify.sh", "--precheck"], cwd=REPO, capture_output=True, text=True,
                          check=False, env={**_environment(REPO / "temp" / "unused.lock"), "ZORA_JOB_ID": "x"})
    assert done.returncode == 2 and "the quick check" in done.stderr


def test_verify_and_the_full_tier_run_the_static_checks_before_the_lock() -> None:
    for script in ("verify.sh", "verify_full.sh"):
        lines = (REPO / "scripts" / script).read_text().splitlines()
        static = lines.index("        sh scripts/verify_static.sh" if script == "verify.sh"
                             else "    sh scripts/verify_static.sh")
        lock = next(n for n, line in enumerate(lines) if "exec python3 tests/suite_lock.py" in line)
        assert static < lock, script
    verify = (REPO / "scripts" / "verify.sh").read_text()
    assert 'python3 -m pytest tests -q -m "$SELECTION" $PYTEST_WORKERS $MAXFAIL' in verify
    # The quick check's part ends before the lock is taken: it never reaches it
    assert verify.index("compare_output --workers 2 --no-lock") < verify.index("exec python3 tests/suite_lock.py")
    assert "-m slow -n auto $MAXFAIL" in (REPO / "scripts" / "verify_full.sh").read_text()
