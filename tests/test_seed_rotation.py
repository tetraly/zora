"""The batch run's tractability (owner decision, 2026-10-16): the slow seed sweeps check a rotated
block of 20 seeds per run (tests/seed_rotation.py), and the release-tree check of a dry run runs
only the tests that reached the private encoder, not the whole suite again (scripts/make_release.py).
"""
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from tests import seed_rotation
from tests.seed_rotation import BLOCK_SETTING, chunk_id, chunks, sweep_seeds

REPO = Path(__file__).resolve().parent.parent
MAKE_RELEASE = REPO / "scripts" / "make_release.py"


@pytest.mark.parametrize(("block", "expected"), [
    ("0", range(0, 20)), ("1", range(20, 40)), ("4", range(80, 100)), ("5", range(0, 20)), ("7", range(40, 60)),
    ("all", range(100)),
])
def test_each_block_is_the_next_20_seeds_of_the_range(monkeypatch: pytest.MonkeyPatch, block: str,
                                                      expected: range) -> None:
    monkeypatch.setenv(BLOCK_SETTING, block)
    assert list(sweep_seeds(range(100))) == list(expected)


def test_without_a_block_the_first_and_a_short_range_whole(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(BLOCK_SETTING, raising=False)
    assert list(sweep_seeds(range(1, 41))) == list(range(1, 21))
    monkeypatch.setenv(BLOCK_SETTING, "3")
    assert list(sweep_seeds(range(1, 41))) == list(range(21, 41))
    assert list(sweep_seeds(range(4, 16))) == list(range(4, 16))       # 20 or fewer: unchanged


def test_every_seed_is_covered_once_per_rotation(monkeypatch: pytest.MonkeyPatch) -> None:
    covered = []
    for block in range(5):
        monkeypatch.setenv(BLOCK_SETTING, str(block))
        covered += list(sweep_seeds(range(100)))
    assert sorted(covered) == list(range(100))


def test_chunks_name_their_seeds() -> None:
    assert [chunk_id(chunk) for chunk in chunks(range(40, 60))] == ["seeds 40-49", "seeds 50-59"]
    assert seed_rotation.SEEDS_PER_SWEEP == 20


@pytest.fixture
def make_release(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ModuleType:
    if not MAKE_RELEASE.exists():
        pytest.skip("scripts/make_release.py is not released")
    monkeypatch.syspath_prepend(str(REPO))
    spec = importlib.util.spec_from_file_location("make_release_for_rotation", MAKE_RELEASE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ENCODER_RECORD", tmp_path / "encoder-record")
    monkeypatch.setattr(module, "progress", lambda message: None)
    return module


def _commands(make_release: ModuleType, monkeypatch: pytest.MonkeyPatch, whole_suite: bool) -> list[list[str]]:
    """The commands release_tree_tests runs (none really runs): collection lists two tests."""
    commands: list[list[str]] = []

    def run_in(tree: Path, command: list[str], timeout: int = 0, output_lines: int | None = 12) -> tuple[bool, str]:
        commands.append(command)
        return True, "tests/test_a.py::test_one\ntests/test_b.py::test_two\n"
    monkeypatch.setattr(make_release, "run_in", run_in)
    make_release.release_tree_tests(Path("tree"), whole_suite)
    return commands


def test_a_dry_run_runs_only_the_encoder_set_in_the_release_tree(make_release: ModuleType,
                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    record = make_release.ENCODER_RECORD
    record.mkdir()
    (record / "gw0.txt").write_text("/copy\ttests/test_a.py::test_one\n/copy\ttests/test_private.py::test_gone\n")
    collect, run = _commands(make_release, monkeypatch, whole_suite=False)
    assert "--collect-only" in collect and "tests" in collect
    assert run[-1] == "tests/test_a.py::test_one" and "tests/test_private.py::test_gone" not in run
    assert "tests" not in run and "auto" not in run


def test_a_release_or_a_missing_record_runs_the_whole_suite(make_release: ModuleType,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    for whole_suite in (True, False):           # a release; a dry run without a record
        _, run = _commands(make_release, monkeypatch, whole_suite)
        assert run[-4:] == ["-n", "auto", "-p", "no:cacheprovider"] and "tests" in run
