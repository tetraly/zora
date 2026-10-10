"""Cross-version reproducibility (slow): the same seeds must give
byte-identical ROMs on every CPython found locally, and under different
hash seeds. Each interpreter hashes seeds 0..N-1 with scripts/output_hash.py's
seed_hash (post-shapes passes on and off; tests/cross_version_hashes.py) and
writes per-seed SHA-1s; any difference fails. The Pyodide half of the check
is manual: docs/packaging.md.

The runs go in chunks of seeds, PROCESSES at a time, rather than through
output_hash.py's own pool of one process per core for each interpreter in
turn: beside the xdist workers that pool would oversubscribe the machine.

Interpreters: python3.11 / python3.12 / python3.13 / python3.14 on PATH, every pyenv
version, and the paths in ZORA_PYTHONS (colon-separated). Duplicates of the
same full version are run once.
"""
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from zora.rom.base_rom import BASE_ROM_PATH

pytestmark = pytest.mark.slow

REPO = Path(__file__).resolve().parent.parent
CHUNK_HASHES = REPO / "tests" / "cross_version_hashes.py"
SCRATCH = REPO / "temp" / "cross_version"
SEEDS = 50
MINORS = ("3.11", "3.12", "3.13", "3.14")
HASH_SEEDS = ("0", "12345")
PROCESSES = 4                        # interpreter runs at once, beside the xdist workers
CHUNK = 10                           # seeds per run


def _version(python: str) -> str | None:
    try:
        out = subprocess.run([python, "-c", "import sys; print(sys.version.split()[0])"],
                             capture_output=True, text=True, timeout=30, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip()


def interpreters() -> dict[str, str]:
    """Full version -> interpreter path, one per version."""
    candidates = [sys.executable]
    # every PATH directory, not just the first hit: two installs of one
    # minor version (framework and Homebrew, say) are both checked
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidates += [p for minor in MINORS
                       if (p := shutil.which(f"python{minor}", path=directory))]
    pyenv_root = Path(os.environ.get("PYENV_ROOT", Path.home() / ".pyenv")) / "versions"
    if pyenv_root.is_dir():
        candidates += [str(p) for p in sorted(pyenv_root.glob("*/bin/python3"))]
    candidates += [p for p in os.environ.get("ZORA_PYTHONS", "").split(":") if p]
    found: dict[str, str] = {}
    for python in candidates:
        version = _version(python)
        if version and version.startswith(MINORS) and version not in found:
            found[version] = python
    return found


def _chunk(python: str, label: str, hash_seed: str, first: int) -> dict[str, list[str]]:
    end = min(first + CHUNK, SEEDS)
    out = SCRATCH / f"{label}-h{hash_seed}-{first}.json"
    env = {**os.environ, "PYTHONHASHSEED": hash_seed, "ZORA_CODE_DIR": str(REPO)}
    subprocess.run([python, str(CHUNK_HASHES), str(first), str(end), str(out)],
                   cwd=REPO, env=env, check=True, capture_output=True, timeout=1800)
    hashes: dict[str, list[str]] = json.loads(out.read_text())
    return hashes


def _all_hashes(runs: dict[str, tuple[str, str, str]]) -> dict[str, dict[str, list[str]]]:
    """Run label -> mode -> per-seed hashes, for runs given as label -> (interpreter, its
    version label, hash seed); each run's seeds in chunks, PROCESSES chunks at a time."""
    jobs = [(name, first) for name in runs for first in range(0, SEEDS, CHUNK)]
    with ThreadPoolExecutor(PROCESSES) as pool:
        chunks = list(pool.map(lambda job: _chunk(*runs[job[0]], job[1]), jobs))
    hashes: dict[str, dict[str, list[str]]] = {name: {} for name in runs}
    for (name, _), chunk in zip(jobs, chunks, strict=True):
        for mode, per_seed in chunk.items():
            hashes[name].setdefault(mode, []).extend(per_seed)
    return hashes


def test_outputs_identical_across_interpreters_and_hash_seeds() -> None:
    if not BASE_ROM_PATH.exists():
        pytest.skip("vanilla ROM missing")
    SCRATCH.mkdir(parents=True, exist_ok=True)
    found = interpreters()
    wanted = {f"{version} h{HASH_SEEDS[0]}": (python, version, HASH_SEEDS[0])
              for version, python in sorted(found.items())}
    running = sys.version.split()[0]
    wanted[f"{running} h{HASH_SEEDS[1]}"] = (sys.executable, running, HASH_SEEDS[1])
    runs = _all_hashes(wanted)
    reference_label, reference = next(iter(runs.items()))
    for label, hashes in runs.items():
        for mode, per_seed in reference.items():
            differing = [seed for seed, (a, b) in enumerate(zip(per_seed, hashes[mode])) if a != b]
            assert not differing, (f"{label} differs from {reference_label} in {mode} "
                                   f"on seeds {differing[:10]}")
    print(f"identical: {sorted(runs)}")
