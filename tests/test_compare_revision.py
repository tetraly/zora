"""`verify.sh REV`'s comparison (scripts/compare_revision.py) is real in a clean copy: REV is
resolved in the checkout the copy was made from, a different revision is reported as
different, an identical one passes, and an unknown one fails before anything runs, never
"identical" by hashing the copy against itself (the bug: the copy's one-commit repository has
no REV, `git archive REV | tar` failed quietly, and output_hash.py --code fell back to the
copy's own zora).

The source checkout is a throwaway git repository in tmp_path: this checkout's files at
revision "same", and a revision "different" whose version number (on the title screen,
FP-TITLE-01) changes every ROM. Its clean copy is made with its own scripts/clean_copy.py.
One seed and one matrix ROM per side, one process each.
"""
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from zora.rom.base_rom import BASE_ROM_PATH

REPO = Path(__file__).resolve().parent.parent
OUTPUT_HASH = REPO / "scripts" / "output_hash.py"
VERSION_FILE = Path("zora") / "version.py"
COPY = "temp/compare-copy"
DIFFERENT_COPY = "temp/different-copy"          # made from "different", while the source's HEAD is "same"
SMALL = ["--seeds", "1", "--matrix-jobs", "1", "--workers", "1"]
# This run's settings the source checkout must set for itself: its own source and code, and its
# own suite lock (the outer suite's lock is held while these tests run).
UNINHERITED = ("ZORA_SOURCE_REPO", "ZORA_CODE_DIR", "ZORA_SUITE_LOCK", "ZORA_SUITE_LOCK_HELD", "ZORA_COPY_REVISION",
               "ZORA_COPY_ADDED")

# A release leaves the clean-copy script out (release/allowlist.txt): these tests then skip
NEEDED = [REPO / "scripts" / "clean_copy.py", REPO / "scripts" / "compare_revision.py"]
pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")


def _environment() -> dict[str, str]:
    """Without this run's own copy settings or git steering: the source repository decides."""
    return {name: value for name, value in os.environ.items()
            if not name.startswith("GIT_") and name not in UNINHERITED}


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=test", "-c", "user.email=test@example.invalid",
                    "-c", "commit.gpgsign=false", *args], check=True, capture_output=True, env=_environment())


@pytest.fixture(scope="module")
def source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A checkout with revisions "same" (its working tree) and "different", and a clean copy."""
    if not all(path.exists() for path in NEEDED):
        pytest.skip("scripts/clean_copy.py or scripts/compare_revision.py is not here")
    repo = tmp_path_factory.mktemp("source")
    # The working tree's files, new ones included: the code under test, committed or not
    files = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                           capture_output=True, check=True, env=_environment()).stdout.decode().split("\0")
    for name in filter(None, files):
        if (REPO / name).is_file():
            (repo / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, repo / name)
    shutil.copy2(BASE_ROM_PATH, repo / BASE_ROM_PATH.name)
    _git(repo, "init", "--quiet")
    _git(repo, "add", "--all")
    _git(repo, "commit", "--quiet", "--no-verify", "-m", "same")
    _git(repo, "tag", "same")
    version = (repo / VERSION_FILE).read_text()
    major = re.search(r'ZORA_VERSION = "(\d+)\.', version)
    assert major
    (repo / VERSION_FILE).write_text(version.replace(major[0], f'ZORA_VERSION = "{int(major[1]) + 1}.'))
    _git(repo, "commit", "--quiet", "--no-verify", "-am", "different")
    _git(repo, "tag", "different")
    _git(repo, "reset", "--quiet", "--hard", "same")
    for copy, revision in ((COPY, "HEAD"), (DIFFERENT_COPY, "different")):
        subprocess.run([sys.executable, "scripts/clean_copy.py", "build", copy, "--rev", revision], cwd=repo,
                       check=True, capture_output=True, env=_environment())
    return repo


def _in_copy(source: Path, *command: str, copy: str = COPY) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "scripts/clean_copy.py", "run", copy, *command], cwd=source,
                          capture_output=True, text=True, check=False, env=_environment())


def test_a_different_revision_is_reported_as_different(source: Path) -> None:
    done = _in_copy(source, sys.executable, "scripts/compare_revision.py", "different", *SMALL)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "b1_on: 1 of 1 differ" in done.stdout
    assert "matrix: 1 of 1 differ" in done.stdout
    assert "output DIFFERS from different" in done.stdout


def test_an_identical_revision_passes(source: Path) -> None:
    done = _in_copy(source, sys.executable, "scripts/compare_revision.py", "same", *SMALL)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "output identical to same" in done.stdout


def test_a_missing_revision_fails(source: Path) -> None:
    done = _in_copy(source, sys.executable, "scripts/compare_revision.py", "no-such-revision", *SMALL)
    assert done.returncode == 2
    assert "no comparison made" in done.stderr
    assert "identical" not in done.stdout


def test_verify_stops_on_a_missing_revision_before_the_suite(source: Path) -> None:
    done = _in_copy(source, "sh", "scripts/verify.sh", "no-such-revision")
    assert done.returncode != 0
    assert "revision no-such-revision is not a commit in" in done.stderr
    assert "passed" not in done.stdout


def test_the_copy_resolves_revisions_in_its_source(source: Path) -> None:
    """The copy's own repository has one commit; "different" exists only in the source."""
    done = _in_copy(source, sys.executable, "scripts/compare_revision.py", "different", "--resolve-only")
    assert done.returncode == 0, done.stderr
    assert str(source) in done.stdout


def test_a_copy_without_its_source_refuses_to_compare_with_itself(source: Path) -> None:
    """Run in the copy directly (not through clean_copy.py run): HEAD would be the copied tree."""
    copy = source / COPY
    done = subprocess.run([sys.executable, "scripts/compare_revision.py", "HEAD", *SMALL], cwd=copy,
                          capture_output=True, text=True, check=False, env=_environment())
    assert done.returncode == 2
    assert "is a clean copy and ZORA_SOURCE_REPO is not set" in done.stderr
    assert "identical" not in done.stdout


def test_hashing_a_folder_without_zora_fails(tmp_path: Path) -> None:
    done = subprocess.run([sys.executable, str(OUTPUT_HASH), "--seeds", "1", "--code", str(tmp_path)],
                          capture_output=True, text=True, check=False, env=_environment())
    assert done.returncode == 2
    assert "holds no zora package" in done.stderr


@pytest.mark.parametrize(("base", "head"), [
    ({"b1_on": ["a"]}, {"b1_on": ["a"], "b1_off": ["b"]}),          # different modes
    ({"b1_on": ["a"]}, {"b1_on": ["a", "b"]}),                      # different seed counts
    ({"matrix": {"x": {}}}, {"matrix": {"y": {}}}),                 # different matrix entries
    ({}, {}),                                                       # nothing hashed
])
def test_runs_that_cover_different_things_are_not_compared(tmp_path: Path, base: dict, head: dict) -> None:
    (tmp_path / "base.json").write_text(json.dumps(base))
    (tmp_path / "head.json").write_text(json.dumps(head))
    done = subprocess.run([sys.executable, str(OUTPUT_HASH), "--compare", str(tmp_path / "base.json"),
                           str(tmp_path / "head.json")], capture_output=True, text=True, check=False)
    assert done.returncode == 2
    assert "identical" not in done.stdout


# --- the parent and the base-hash cache (docs/design/test-speed.md 3.2) -------------------------

def _commit(source: Path, revision: str) -> str:
    return subprocess.run(["git", "-C", str(source), "rev-parse", revision], capture_output=True, text=True,
                          check=True, env=_environment()).stdout.strip()


def test_the_parent_is_the_revision_the_copy_was_made_from(source: Path) -> None:
    """Not the source checkout's HEAD ("same"): the copy of "different" sits on "different"."""
    done = _in_copy(source, sys.executable, "scripts/compare_revision.py", "parent", "--resolve-only",
                    copy=DIFFERENT_COPY)
    assert done.returncode == 0, done.stderr
    assert f"parent is {_commit(source, 'different')[:12]}" in done.stdout


def test_the_parent_comparison_names_the_parent(source: Path) -> None:
    done = _in_copy(source, sys.executable, "scripts/compare_revision.py", "parent", *SMALL)
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.strip().splitlines()[-1] == \
        f"compare_revision: output identical to {_commit(source, 'same')[:12]} (the parent)"


def test_a_second_comparison_reuses_the_cached_hashes(source: Path) -> None:
    """The second run of the same comparison hashes only this checkout, with the same verdict."""
    first = _in_copy(source, sys.executable, "scripts/compare_revision.py", "different", *SMALL)
    second = _in_copy(source, sys.executable, "scripts/compare_revision.py", "different", *SMALL)
    assert (first.returncode, second.returncode) == (1, 1), first.stdout + second.stdout
    assert "different (" in second.stdout and "from the cache" in second.stdout
    assert "== matrix at different" not in second.stdout        # REV was not hashed again
    assert second.stdout.splitlines()[-1] == first.stdout.splitlines()[-1] == \
        "compare_revision: output DIFFERS from different"


def _compare_revision_module() -> Any:
    spec = importlib.util.spec_from_file_location("compare_revision_under_test", NEEDED[1])
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


KEY_PARTS = {"revision tree", "output_hash.py", "matrix cases", "seeds", "matrix jobs", "base ROM",
             "private module", "interpreter"}


@pytest.fixture(scope="module")
def key_parts() -> dict[str, str]:
    if not all(path.exists() for path in NEEDED):
        pytest.skip("scripts/compare_revision.py is not here")
    module = _compare_revision_module()
    parts: dict[str, str] = module.base_hash_key_parts(module.resolve(module.PARENT), 20, None)
    return parts


def test_the_key_names_everything_the_base_hashes_depend_on(key_parts: dict[str, str]) -> None:
    assert set(key_parts) == KEY_PARTS
    assert key_parts["output_hash.py"] == hashlib.sha256(OUTPUT_HASH.read_bytes()).hexdigest()
    assert key_parts["base ROM"] == hashlib.sha256(BASE_ROM_PATH.read_bytes()).hexdigest()
    assert key_parts["interpreter"] == sys.version
    assert (key_parts["seeds"], key_parts["matrix jobs"]) == ("20", "None")


@pytest.mark.parametrize("part", sorted(KEY_PARTS))
def test_changing_any_part_of_the_key_misses_the_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                        key_parts: dict[str, str], part: str) -> None:
    module = _compare_revision_module()
    monkeypatch.setenv(module.SOURCE_REPO_SETTING, str(tmp_path))     # the cache lives in the source checkout
    hashes = {"seeds": "{}", "matrix": "{}"}
    module.store_base(key_parts, hashes)
    assert module.cached_base(key_parts) == hashes
    assert module.cached_base({**key_parts, part: key_parts[part] + " changed"}) is None
