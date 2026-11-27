"""scripts/make_release.py's steps in the release tree (2026-11-24, after a test stage stopped at its fixed time
limit, 88% through a slow but live suite, and lost every result it held in memory): each step's output streams
to its log in STEP_LOGS; a step is stopped only once its output stops growing (STALL_SECONDS), as a failed check
that keeps its output, never an exception; and a pytest step's failures (tests/progress_plugin.py) are echoed
the moment they happen and listed in full, so a step stopped at any point still names every failure so far."""
import importlib.util
import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parent.parent
MAKE_RELEASE = REPO / "scripts" / "make_release.py"

# a release leaves out make_release.py (release/allowlist.txt)
pytestmark = pytest.mark.skipif(not MAKE_RELEASE.exists(), reason="no release scripts here")

STALL = 1.5                             # seconds: these steps' stall limit
LIMIT = 30                              # seconds: no step here may take longer


@pytest.fixture
def make_release(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ModuleType:
    """make_release, its step logs in tmp_path."""
    monkeypatch.syspath_prepend(str(REPO))
    spec = importlib.util.spec_from_file_location("make_release_for_steps", MAKE_RELEASE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)          # its dataclasses look their module up
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "STEP_LOGS", tmp_path / "logs")
    monkeypatch.setattr(module, "disassembly_clone", lambda: tmp_path / "disassembly")
    return module


def python(code: str) -> list[str]:
    return [sys.executable, "-c", textwrap.dedent(code)]


def gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


def test_a_step_streams_its_whole_output_to_its_log(make_release: ModuleType, tmp_path: Path) -> None:
    passed, output = make_release.run_in(tmp_path, python("for n in range(40): print('line', n)"),
                                         stall_seconds=STALL)
    logs = sorted(make_release.STEP_LOGS.glob("*.log"))
    assert passed and output.splitlines() == [f"line {n}" for n in range(28, 40)]       # the last 12
    assert len(logs) == 1 and logs[0].read_text().splitlines() == [f"line {n}" for n in range(40)]


def test_a_slow_step_that_keeps_printing_runs_to_its_end(make_release: ModuleType, tmp_path: Path) -> None:
    """Twice the stall limit in all, never quiet for half of it: a slow step, not a hung one."""
    passed, output = make_release.run_in(tmp_path, python(f"""
        import time
        for n in range(12):
            print(n, flush=True)
            time.sleep({STALL / 4})
        """), stall_seconds=STALL)
    assert passed and "STOPPED" not in output and output.splitlines()[-1] == "11"


def test_a_stalled_step_is_stopped_with_everything_it_started_and_keeps_its_output(make_release: ModuleType,
                                                                                    tmp_path: Path) -> None:
    child = tmp_path / "child.pid"
    started = time.monotonic()
    passed, output = make_release.run_in(tmp_path, python(f"""
        import subprocess, sys, time
        worker = subprocess.Popen([sys.executable, "-c", "import time; time.sleep({LIMIT})"])
        open({str(child)!r}, "w").write(str(worker.pid))
        print("before the hang", flush=True)
        time.sleep({LIMIT})
        """), stall_seconds=STALL)
    assert time.monotonic() - started < LIMIT / 2
    assert not passed
    assert output.startswith(f"STOPPED: no output for {STALL:.0f} s") and "before the hang" in output
    log = next(make_release.STEP_LOGS.glob("*.log"))
    assert str(log) in output and "before the hang" in log.read_text()
    deadline = time.monotonic() + 10
    while not gone(int(child.read_text())):                     # the worker, in the step's process group
        assert time.monotonic() < deadline, "the stalled step's worker was left running"
        time.sleep(0.05)


def test_a_failing_step_fails_with_its_output(make_release: ModuleType, tmp_path: Path) -> None:
    passed, output = make_release.run_in(tmp_path, python("import sys; print('no'); sys.exit(3)"), stall_seconds=STALL)
    assert not passed and output == "no"


# --- a pytest step's failures as they happen (tests/progress_plugin.py) ------------------------------------------

def pytest_tree(root: Path, body: str) -> Path:
    """A tree whose checks/test_steps.py holds BODY; run with the progress plugin from this repository."""
    (root / "checks").mkdir(parents=True)
    (root / "checks" / "test_steps.py").write_text(textwrap.dedent(body))
    return root


def pytest_step(tree: Path) -> list[str]:
    return [sys.executable, "-m", "pytest", "checks", "-q", "-p", "progress_plugin", "-p", "no:cacheprovider"]


@pytest.fixture
def plugin_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The step's pytest finds the progress plugin and zora_measure here, and reports its job in tmp_path."""
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([str(REPO / "tests"), str(REPO)]))
    monkeypatch.setenv("ZORA_JOBS_FOLDER", str(tmp_path / "jobs"))
    monkeypatch.delenv("ZORA_JOB_ID", raising=False)


@pytest.mark.usefixtures("plugin_environment")
def test_a_pytest_steps_failures_are_echoed_and_listed(make_release: ModuleType, tmp_path: Path,
                                                       capsys: pytest.CaptureFixture[str]) -> None:
    tree = pytest_tree(tmp_path / "tree", """
        import pytest

        @pytest.fixture
        def broken():
            raise RuntimeError("the fixture broke")

        def test_passes():
            pass

        def test_fails():
            assert 1 == 2, "one is not two"

        def test_setup_fails(broken):
            pass
        """)
    passed, output = make_release.run_in(tree, pytest_step(tree), stall_seconds=10)
    echoed = capsys.readouterr().out
    assert not passed
    for failure in ("checks/test_steps.py::test_fails (call)", "checks/test_steps.py::test_setup_fails (setup)"):
        assert f"... FAILED {failure}" in echoed
        assert f"FAILED {failure}" in output
    assert "one is not two" in output and "the fixture broke" in output
    assert "test_passes" not in echoed
    failures = next(make_release.STEP_LOGS.glob("*.failures"))
    assert f"failures (also in {failures}):" in output


@pytest.mark.usefixtures("plugin_environment")
def test_a_step_stopped_by_a_hang_still_names_the_failures_before_it(make_release: ModuleType, tmp_path: Path,
                                                                     capsys: pytest.CaptureFixture[str]) -> None:
    """The case that lost a stage's results: a failure, then the step stopped before pytest's summary."""
    tree = pytest_tree(tmp_path / "tree", f"""
        import time

        def test_a_fails():
            assert False, "failed before the hang"

        def test_b_hangs():
            time.sleep({LIMIT})
        """)
    passed, output = make_release.run_in(tree, pytest_step(tree), stall_seconds=3)
    assert not passed and output.startswith("STOPPED")
    assert "FAILED checks/test_steps.py::test_a_fails (call)" in output and "failed before the hang" in output
    assert "... FAILED checks/test_steps.py::test_a_fails (call)" in capsys.readouterr().out


def test_without_the_setting_a_run_writes_no_failures_file(tmp_path: Path) -> None:
    """Only a run given ZORA_FAILURES_FILE writes one; the failure still counts on the progress line."""
    tree = pytest_tree(tmp_path / "tree", "def test_fails():\n    assert False\n")
    environment = {name: value for name, value in os.environ.items() if name not in ("ZORA_FAILURES_FILE", "ZORA_JOB_ID")}
    environment |= {"PYTHONPATH": os.pathsep.join([str(REPO / "tests"), str(REPO)]),
                    "ZORA_JOBS_FOLDER": str(tmp_path / "jobs")}
    done = subprocess.run(pytest_step(tree), cwd=tree, env=environment, capture_output=True, text=True, check=False,
                          timeout=LIMIT)
    assert done.returncode == 1, done.stdout + done.stderr
    assert not list(tree.rglob("*.failures"))
    steps = [json.loads(path.read_text()).get("step", "") for path in (tmp_path / "jobs").glob("*.json")]
    assert "1 failed so far" in steps, steps                    # the job's last status keeps it


def test_each_run_starts_with_fresh_step_logs(make_release: ModuleType, tmp_path: Path) -> None:
    make_release.STEP_LOGS.mkdir(parents=True)
    (make_release.STEP_LOGS / "01-old.log").write_text("the last run's")
    make_release.run_in(tmp_path, python("print('a')"), stall_seconds=STALL)
    make_release.run_in(tmp_path, python("print('b')"), stall_seconds=STALL)
    assert [path.name.split("-")[0] for path in sorted(make_release.STEP_LOGS.glob("*.log"))] == ["01", "02"]


def test_stopping_the_run_stops_its_step(tmp_path: Path) -> None:
    """job.py stop's SIGTERM to make_release: the step, in a session of its own that the signal never reaches, and
    the worker it started go too, not left running orphaned."""
    worker = tmp_path / "worker.pid"
    step = textwrap.dedent(f"""
        import subprocess, sys, time
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep({LIMIT})"])
        open({str(worker)!r}, "w").write(str(child.pid))
        print("running", flush=True)
        time.sleep({LIMIT})
        """)
    runner = textwrap.dedent(f"""
        import importlib.util, sys
        from pathlib import Path
        sys.path.insert(0, {str(REPO)!r})
        spec = importlib.util.spec_from_file_location("make_release_stopped", {str(MAKE_RELEASE)!r})
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        module.STEP_LOGS = Path({str(tmp_path / "logs")!r})
        module.disassembly_clone = lambda: Path({str(tmp_path)!r})
        module.run_in(Path({str(tmp_path)!r}), [sys.executable, "-c", {step!r}])
        """)
    run = subprocess.Popen([sys.executable, "-c", runner], cwd=tmp_path)
    deadline = time.monotonic() + LIMIT / 2
    while not worker.exists() or not worker.read_text():
        assert time.monotonic() < deadline and run.poll() is None, "the step never started"
        time.sleep(0.05)
    run.terminate()
    assert run.wait(timeout=LIMIT) != 0
    deadline = time.monotonic() + 10
    while not gone(int(worker.read_text())):
        assert time.monotonic() < deadline, "the step's worker outlived the stopped run"
        time.sleep(0.05)
