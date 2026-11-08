"""The output comparison's inputs (scripts/output_inputs.py; owner ruling, 2026-11-07): the list is worked
out from the code, and a hashing worker never reads a repository file outside it. Each audit runs
output_hash.py's own worker functions (seed_hash, matrix_hash) in a fresh process with an audit hook on
every file opened, as a hashing worker would; the base ROM and private/ are untracked, outside any
commit's change, and covered by the hash cache's key instead."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.needs import needs_base_rom

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
UNTRACKED_INPUTS = ("Legend of Zelda, The (USA).nes", "private/")
# A fresh worker: the hook first, then output_hash.py as its pool imports it, then the jobs; prints the
# repository files it opened (a cached module's .pyc counted as its source)
AUDIT = """
import json, os, sys
from pathlib import Path
repo = Path(sys.argv[1]).resolve()
opened = set()
def hook(event, args):
    if event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
        path = Path(os.fsdecode(args[0]))
        path = path if path.is_absolute() else Path.cwd() / path
        try:
            relative = path.resolve().relative_to(repo)
        except ValueError:
            return
        if "__pycache__" in relative.parts:
            relative = relative.parent.parent / (relative.name.split(".")[0] + ".py")
        opened.add(relative.as_posix())
sys.addaudithook(hook)
sys.path.insert(0, str(repo / "scripts"))
import output_hash
for kind, *job in json.loads(sys.argv[2]):
    if kind == "seed":
        output_hash.seed_hash(tuple(job))
    elif kind == "open":
        open(repo / job[0]).close()
    else:
        output_hash.matrix_hash(tuple(job))
print(json.dumps(sorted(opened)))
"""


def _script(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


INPUTS = _script("output_inputs")


def outside_the_inputs(jobs: list[list[Any]]) -> list[str]:
    """The repository files the jobs opened that are not output inputs."""
    done = subprocess.run([sys.executable, "-c", AUDIT, str(REPO), json.dumps(jobs)], cwd=REPO,
                          capture_output=True, text=True, check=True)
    opened = json.loads(done.stdout.strip().splitlines()[-1])
    assert "scripts/output_hash.py" in opened and any(path.startswith("zora/") for path in opened)
    candidates = [path for path in opened if not path.startswith(UNTRACKED_INPUTS)]
    inputs = set(INPUTS.output_inputs_among(candidates))
    return [path for path in candidates if path not in inputs]


def matrix_job_list(names: tuple[str, ...] | None, seed: int) -> list[list[Any]]:
    jobs = _script("output_hash").matrix_jobs()
    return [["matrix", *job] for job in jobs if job[3] == seed and (names is None or job[0] in names)]


SAMPLE_CASES = ("baseline", "MVP baseline (encoded)", "every ZORA flag on", "every owner flag on",
                "universal drops v2.0, L4 sword and highlight", "start room swap, second quest dungeons")


@needs_base_rom
def test_a_sample_of_the_workers_reads_only_output_inputs() -> None:
    jobs = [["seed", 0, True], ["seed", 0, False], *matrix_job_list(SAMPLE_CASES, 1)]
    assert len(jobs) == 2 + len(SAMPLE_CASES)
    assert outside_the_inputs(jobs) == []


@needs_base_rom
@pytest.mark.slow
@pytest.mark.parametrize("seed", [1, 2])
def test_every_matrix_case_reads_only_output_inputs(seed: int) -> None:
    """Seeds 1 and 2 of every case, the quick check's matrix."""
    assert outside_the_inputs(matrix_job_list(None, seed)) == []


@needs_base_rom
def test_a_read_outside_the_inputs_fails_the_audit() -> None:
    assert outside_the_inputs([["seed", 0, False], ["open", "docs/CHANGELOG.md"]]) == ["docs/CHANGELOG.md"]


def test_the_inputs_are_generation_and_the_comparison() -> None:
    inputs = INPUTS.output_inputs()
    assert {"scripts/output_hash.py", "scripts/compare_revision.py", "scripts/output_inputs.py",
            "tests/archipelago_cases.py", "zora/version.py", "zora_export/spoiler_log.py"} <= set(inputs)
    assert any(path.startswith("zora/") and not path.endswith(".py") for path in inputs)    # package data
    # The matrix's cases, not everything they import: the case list is hashed on both sides alike
    assert "tests/conftest.py" not in inputs and not any(path.startswith(("docs/", "web/")) for path in inputs)


@pytest.mark.parametrize(("paths", "inputs"), [
    (["docs/CHANGELOG.md", "web/zora-web.js", "tests/test_tracker_file.py"], []),
    (["docs/CHANGELOG.md", "zora/version.py"], ["zora/version.py"]),
    (["zora/removed_module.py"], ["zora/removed_module.py"]),           # a deleted file of an input package
    (["tests/archipelago_cases.py", "scripts/output_hash.py"], ["tests/archipelago_cases.py", "scripts/output_hash.py"]),
])
def test_which_changes_run_the_comparison(paths: list[str], inputs: list[str]) -> None:
    assert INPUTS.output_inputs_among(paths) == inputs
