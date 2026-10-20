"""Every pytest run as a job with progress (zora_measure/progress.py; AGENTS.md "Run time"): at
least once a minute it prints how many tests have run of how many, its elapsed time and the time
left, and keeps the same in its status file for scripts/jobs.py. The controller reports (or the one
process, without xdist): it learns the tests from collection, a worker's when xdist runs, and
counts each test when its teardown reports.

The time left weighs each test by its duration recorded in earlier runs (temp/jobs/
test-durations.json; a test without one counts as the mean of those with one), at the pace this
run's done tests actually took: a run whose slow tests come last no longer estimates from the
fast ones' average (owner request, 2026-10-16). Each passing test's duration (setup, call and
teardown) is recorded when the run ends, with whether it is heavy (marked slow or full_tier),
which the quick check's selection cap reads (scripts/affected_tests.py). tests/conftest.py loads
this plugin."""
from collections.abc import Iterable
from typing import Any

import pytest

from zora_measure import progress

HEAVY_MARKS = ("slow", "full_tier")

_job: list[progress.Job] = []
_expected: dict[str, float] = {}
_ran: dict[str, list[Any]] = {}          # node id: [seconds so far, heavy, its call passed, a phase failed]


class _PastCapture:
    """A stream for the job's lines that pytest's output capture does not swallow."""

    def __init__(self, config: pytest.Config) -> None:
        self.config = config

    def write(self, text: str) -> None:
        capture = self.config.pluginmanager.getplugin("capturemanager")
        if capture is None:
            print(text, end="", flush=True)
            return
        with capture.global_and_fixture_disabled():
            print(text, end="", flush=True)

    def flush(self) -> None:
        pass


def _controller(config: pytest.Config) -> bool:
    return not hasattr(config, "workerinput")


def pytest_sessionstart(session: pytest.Session) -> None:
    config = session.config
    if not _controller(config) or config.option.collectonly:
        return
    arguments = " ".join(config.invocation_params.args) or "tests"
    _job.append(progress.Job(f"pytest {arguments}"[:100], unit="tests", stream=_PastCapture(config)).start())


def _collected(tests: Iterable[str]) -> None:
    """The run's tests are known: the total, and their expected work when any is recorded."""
    job = _job[0]
    tests = list(tests)
    job.total = len(tests)
    expected = progress.expected_work(tests, progress.read_durations())
    if expected:
        _expected.clear()
        _expected.update(expected)
        job.work_total = sum(expected.values())


def pytest_collection_finish(session: pytest.Session) -> None:
    if _job and _job[0].total is None and session.items:
        _collected(item.nodeid for item in session.items)


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_node_collection_finished(node: Any, ids: list[str]) -> None:
    """Every worker collects the same tests; the first to report gives them."""
    if _job and _job[0].total is None:
        _collected(ids)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if not _job:
        return
    heavy = any(mark in report.keywords for mark in HEAVY_MARKS)
    seconds, heavy, called, failed = _ran.get(report.nodeid, [0.0, heavy, False, False])
    _ran[report.nodeid] = [seconds + report.duration, heavy, called or (report.when == "call" and report.passed),
                           failed or report.failed]
    if report.when == "teardown":
        _job[0].advance(work=_expected.get(report.nodeid, 0.0))


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if _job:
        # Only passing tests: a skipped one's moment says nothing of its run time
        progress.record_durations({test: (seconds, heavy) for test, (seconds, heavy, called, failed) in _ran.items()
                                   if called and not failed})
        _ran.clear()
        _job.pop().finish(ok=exitstatus in (0, 5))      # 5: nothing collected, not a failure
