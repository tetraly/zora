"""scripts/encoder_check.py catches a test that needs the private encoder but does not skip
without it (docs/design/test-speed.md 3.2 item 3), and passes a guarded one.

A probe module in a temporary folder holds one guarded and one unguarded test that each plan
an encoded seed. It runs with the encoder installed and recorded, then the check reruns what was
recorded with the encoder hidden."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.encoder_check import HIDE_ENV, RECORD_ENV, read_records
from zora.rom import level_encoding

REPO = Path(__file__).resolve().parent.parent
PROBE = '''import pytest

from zora.flags.presets import MVP_BASELINE
from zora.generate.pipeline import plan
from zora.rom import level_encoding


def test_unguarded() -> None:
    assert plan(MVP_BASELINE, 1).config.level_encoding is not None


@pytest.mark.skipif(not level_encoding.is_available(), reason="level encoding is not installed")
def test_guarded() -> None:
    assert plan(MVP_BASELINE, 1).config.level_encoding is not None
'''

UNGUARDED = "def test_unguarded() -> None:\n    assert plan(MVP_BASELINE, 1).config.level_encoding is not None\n"
assert UNGUARDED in PROBE

pytestmark = pytest.mark.skipif(not level_encoding.is_available(), reason="level encoding is not installed")


def environment(**settings: str) -> dict[str, str]:
    base = {name: value for name, value in os.environ.items() if name not in (RECORD_ENV, HIDE_ENV)}
    return {**base, "PYTHONPATH": str(REPO), **settings}


def record_probe(tmp_path: Path, probe: str) -> Path:
    (tmp_path / "probe").mkdir()
    (tmp_path / "probe" / "test_probe.py").write_text(probe)
    record = tmp_path / "record"
    subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "tests.encoder_check",
                    "probe/test_probe.py"], cwd=tmp_path, env=environment(**{RECORD_ENV: str(record)}),
                   capture_output=True, text=True, check=True)
    return record


def encoder_check(record: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(REPO / "scripts" / "encoder_check.py"), str(record)],
                          cwd=REPO, env=environment(), capture_output=True, text=True, check=False)


def test_an_unguarded_test_fails_the_check(tmp_path: Path) -> None:
    record = record_probe(tmp_path, PROBE)
    [ids] = read_records(record).values()        # pytest picks the probe's rootdir
    assert [nodeid.rpartition("test_probe.py::")[2] for nodeid in ids] == ["test_guarded", "test_unguarded"]
    done = encoder_check(record)
    assert done.returncode == 1, done.stdout
    failures = done.stdout.split("encoder check: FAILED")[1]
    assert "test_probe.py::test_unguarded" in failures and "test_guarded" not in failures


def test_guarded_tests_pass_the_check(tmp_path: Path) -> None:
    done = encoder_check(record_probe(tmp_path, PROBE.replace(UNGUARDED, "")))
    assert done.returncode == 0, done.stdout
    assert "1 skipped" in done.stdout


COLLECTION_GUARDED = """

@pytest.mark.parametrize("case", ["encoded"] if level_encoding.is_available() else ["plain"])
def test_cases_made_only_with_the_encoder(case: str) -> None:
    if case == "encoded":
        assert plan(MVP_BASELINE, 1).config.level_encoding is not None
"""


def test_a_test_made_only_with_the_encoder_is_guarded_and_the_others_still_run(tmp_path: Path) -> None:
    """A recorded test that is not collected without the encoder is guarded; the rest still rerun."""
    done = encoder_check(record_probe(tmp_path, PROBE + COLLECTION_GUARDED))
    assert done.returncode == 1, done.stdout
    assert "1 not collected (guarded at collection)" in done.stdout
    assert "test_probe.py::test_unguarded" in done.stdout.split("encoder check: FAILED")[1]


def test_nothing_recorded_is_nothing_to_check(tmp_path: Path) -> None:
    done = encoder_check(tmp_path / "empty")
    assert done.returncode == 0 and "nothing to check" in done.stdout
