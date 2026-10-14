"""The fast tier's selection (tests/conftest.py; docs/design/test-speed.md 3.2): seeds 2 and up of a
seed sweep (a parametrize over `seed` alone) are marked full_tier, and nothing else is. A probe
folder whose conftest takes only that hook from tests/conftest.py, collected in a subprocess."""
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROBE_CONFTEST = "from tests.conftest import pytest_collection_modifyitems  # noqa: F401\n"
PROBE = '''import pytest


@pytest.mark.parametrize("seed", [3, 1, 2])
def test_sweep(seed: int) -> None:
    pass


@pytest.mark.parametrize("seed", [pytest.param(7, id="seven"), 8])
def test_sweep_of_params(seed: int) -> None:
    pass


@pytest.mark.parametrize("case", ["a", "b"])
@pytest.mark.parametrize("seed", [1, 2])
def test_cases_by_seed(case: str, seed: int) -> None:
    pass


@pytest.mark.parametrize(("seed", "room"), [(1, 2), (5, 6)])
def test_scenarios(seed: int, room: int) -> None:
    pass


@pytest.mark.parametrize("seed", [4])
def test_one_seed(seed: int) -> None:
    pass


@pytest.mark.parametrize("level", [1, 2])
def test_not_seeds(level: int) -> None:
    pass
'''
FULL_TIER = {"test_probe.py::test_sweep[1]", "test_probe.py::test_sweep[2]", "test_probe.py::test_sweep_of_params[8]",
             "test_probe.py::test_cases_by_seed[2-a]", "test_probe.py::test_cases_by_seed[2-b]"}


def collect(tmp_path: Path, expression: str) -> set[str]:
    (tmp_path / "conftest.py").write_text(PROBE_CONFTEST)
    (tmp_path / "test_probe.py").write_text(PROBE)
    environment = {**os.environ, "PYTHONPATH": str(REPO)}
    done = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider",
                           "-W", "ignore::pytest.PytestUnknownMarkWarning", "-m", expression, "test_probe.py"],
                          cwd=tmp_path, env=environment, capture_output=True, text=True, check=False)
    assert done.returncode in (0, 5), done.stdout + done.stderr
    return {line for line in done.stdout.splitlines() if "::" in line}


def test_later_seeds_of_sweeps_are_the_full_tiers(tmp_path: Path) -> None:
    assert collect(tmp_path, "full_tier") == FULL_TIER


def test_the_fast_tier_keeps_every_first_seed_scenario_and_other_parameter(tmp_path: Path) -> None:
    fast = collect(tmp_path, "not full_tier")
    assert len(fast) == 14 - len(FULL_TIER) and not fast & FULL_TIER
    assert {"test_probe.py::test_sweep[3]", "test_probe.py::test_sweep_of_params[seven]",
            "test_probe.py::test_scenarios[5-6]", "test_probe.py::test_one_seed[4]",
            "test_probe.py::test_not_seeds[2]"} <= fast
