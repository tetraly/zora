"""Every pytest run as a job with progress (zora_measure/progress.py; AGENTS.md "Run time"): at
least once a minute it prints how many tests have run of how many, its elapsed time and the time
left, and keeps the same in its status file for scripts/jobs.py. The controller reports (or the one
process, without xdist): it learns the total from collection, a worker's when xdist runs, and
counts each test when its teardown reports. tests/conftest.py loads this plugin."""
from typing import Any

import pytest

from zora_measure import progress

_job: list[progress.Job] = []


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


def pytest_collection_finish(session: pytest.Session) -> None:
    if _job and _job[0].total is None and session.items:
        _job[0].total = len(session.items)


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_node_collection_finished(node: Any, ids: list[str]) -> None:
    """Every worker collects the same tests; the first to report gives the total."""
    if _job and _job[0].total is None:
        _job[0].total = len(ids)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if _job and report.when == "teardown":
        _job[0].advance()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if _job:
        _job.pop().finish(ok=exitstatus in (0, 5))      # 5: nothing collected, not a failure
