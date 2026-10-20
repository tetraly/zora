"""The batch run's failure report (scripts/batch_run.py): every failed test id read whole from the
pytest summaries, a parametrized id with spaces included, and a trace command the shell runs as
printed."""
import importlib.util
import shlex
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parent.parent
BATCH_RUN = REPO / "scripts" / "batch_run.py"

# Summary lines as the 18c9940 batch run's log has them (2026-10-17)
SUMMARY = """\
FAILED tests/test_gate_hints.py::test_the_reported_seed - assert False
FAILED tests/test_gate_hints.py::test_a_door_behind_a_maze_needs_what_its_hint_needs[the report's flags-320-1-113-no raft]
FAILED tests/test_coop_page.py::test_a_played_session_leaves_the_coop_page_alone[every owner flag on, screen off-False]
FAILED tests/test_coop_page.py::test_a_played_session_leaves_the_coop_page_alone[every owner flag on, screen off-True]
FAILED tests/test_item_shuffle_values.py::test_the_extras_pool_hearts_only_under_full_scope[1-False]
ERROR tests/test_seed_document.py::test_the_sample_log_is_current - Assertio...
FAILED tests/test_gate_hints.py::test_the_reported_seed - assert False
13 failed, 7828 passed, 1 skipped in 726.16s (0:12:06)
"""
IDS = [
    "tests/test_gate_hints.py::test_the_reported_seed",
    "tests/test_gate_hints.py::test_a_door_behind_a_maze_needs_what_its_hint_needs[the report's flags-320-1-113-no raft]",
    "tests/test_coop_page.py::test_a_played_session_leaves_the_coop_page_alone[every owner flag on, screen off-False]",
    "tests/test_coop_page.py::test_a_played_session_leaves_the_coop_page_alone[every owner flag on, screen off-True]",
    "tests/test_item_shuffle_values.py::test_the_extras_pool_hearts_only_under_full_scope[1-False]",
    "tests/test_seed_document.py::test_the_sample_log_is_current",
]


@pytest.fixture
def batch_run(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """scripts/batch_run.py, loaded from its path (as tests/test_seed_rotation.py loads make_release)."""
    if not BATCH_RUN.exists():
        pytest.skip("scripts/batch_run.py is not released")
    monkeypatch.syspath_prepend(str(REPO))
    spec = importlib.util.spec_from_file_location("batch_run_for_report", BATCH_RUN)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def test_failed_ids_are_read_whole_and_once(batch_run: ModuleType, tmp_path: Path) -> None:
    log = tmp_path / "batch.log"
    log.write_text(SUMMARY)
    assert batch_run.failed_tests(log) == IDS


def test_the_trace_command_names_every_test_as_the_shell_reads_it(batch_run: ModuleType) -> None:
    command = batch_run.trace_command(IDS, "18c99403733e", 0)
    assert shlex.split(command) == ["python3", "scripts/batch_run.py", "trace", *IDS,
                                    "--rev", "18c99403733e", "--sweep-block", "0"]


# The end of a batch run's log (the be53e6e run, 2026-10-17), as scripts/verify_full.sh writes it
FAILED_RUN = """\
batch run: be53e6e is be53e6eb5878 (Swords (C07)); seed sweeps: block 2 (ZORA_SWEEP_BLOCK=2, tests/seed_rotation.py)
FAILED tests/test_flag_invariants.py::test_invariants[101-starting_hearts=1,start_triforce_pieces=33]
2 failed, 1446 passed in 1465.59s (0:24:25)
compare_revision: output DIFFERS from 15e329339571b293ae433030afdde32254405cc6
full tier: FAILED, not stamped. Failed steps:
  {steps}

batch run: FAILED on be53e6eb5878; log temp/batch/be53e6eb5878.log
"""


def test_a_slow_suite_failure_allows_a_fixup(batch_run: ModuleType) -> None:
    log = FAILED_RUN.format(steps="2/4: the slow suite")
    assert batch_run.failed_steps(log) == ["2/4: the slow suite"]
    assert batch_run.fixup_refusal(log) is None
    assert batch_run.SWEEP_BLOCK_IN_HEADER.search(log.splitlines()[0])[1] == "2"


@pytest.mark.parametrize("steps", [
    "1/4: the fast suite's checks (the tests, the encoder check or the comparison)",
    "2/4: the slow suite\n  3/4: the release-tree checks",
])
def test_other_failed_steps_refuse_a_fixup(batch_run: ModuleType, steps: str) -> None:
    refusal = batch_run.fixup_refusal(FAILED_RUN.format(steps=steps))
    assert refusal is not None and "elsewhere too" in refusal


def test_a_passed_or_stopped_run_refuses_a_fixup(batch_run: ModuleType) -> None:
    assert batch_run.fixup_refusal("batch run: PASSED on be53e6eb5878\n") is not None
    no_test = FAILED_RUN.format(steps="2/4: the slow suite").replace("FAILED tests/", "passed tests/")
    assert batch_run.fixup_refusal(no_test) == "the log names no failed test"


def test_a_test_a_commit_lacks_is_not_found(batch_run: ModuleType) -> None:
    collected = {"tests/test_a.py::test_one[1-x]", "tests/test_a.py::test_two"}
    tests = ["tests/test_a.py::test_one[1-x]", "tests/test_a.py::test_one[2-y]", "tests/test_a.py::test_two",
             "tests/test_a.py::test_one", "tests/test_b.py::test_gone"]
    assert batch_run.present(tests, collected) == ["tests/test_a.py::test_one[1-x]", "tests/test_a.py::test_two",
                                                   "tests/test_a.py::test_one"]


def test_the_fixup_quick_check_is_the_fix_on_its_parent(batch_run: ModuleType, tmp_path: Path) -> None:
    """b8ebd42 (the fix for the be53e6e run): the copy's identity names be53e6e and the 3 files it changed."""
    try:
        batch_run._git("rev-parse", "--verify", "b8ebd42^{commit}")
    except subprocess.CalledProcessError:
        pytest.skip("not this repository's history")
    (tmp_path / "verify.env").write_text("ZORA_CORPORA=x\nZORA_COPY_REVISION=b8ebd42\nZORA_COPY_ADDED=\n")
    assert batch_run.as_change_on_parent(str(tmp_path), "b8ebd42").startswith("be53e6e")
    settings = (tmp_path / "verify.env").read_text().splitlines()
    assert settings[0] == "ZORA_CORPORA=x"
    assert [line.partition("=")[0] for line in settings].count("ZORA_COPY_REVISION") == 1
    assert ("ZORA_COPY_ADDED=tests/test_starting_hearts.py:zora/rom/serialize/features.py:"
            "zora/rom/serialize/game_world.py") in settings
