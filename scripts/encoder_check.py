"""The encoder check (docs/design/test-speed.md 3.2 item 3): every test that reached the private
level encoder must pass or skip without it, as in a release tree.

    python3 scripts/encoder_check.py RECORD_DIR

RECORD_DIR holds what a pytest run recorded with ZORA_ENCODER_RECORD=RECORD_DIR
(tests/encoder_check.py); scripts/verify.sh sets it. This reruns exactly those tests with the
encoder hidden (ZORA_HIDE_LEVEL_ENCODING=1), at two workers, which run beside a held suite lock.
A recorded test that is not even collected without the encoder is guarded at collection (its
cases are made only when the encoder is there), which is correct.

Exit status 0 when every rerun test passed or skipped, 1 when any failed (fix: guard it with
@pytest.mark.skipif(not level_encoding.is_available(), reason="level encoding is not installed")),
2 when the rerun could not be made.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tests.encoder_check import HIDE_ENV, RECORD_ENV, read_records  # noqa: E402

PLUGIN = ["-p", "tests.encoder_check"]
# No marker filter: pyproject's "not slow" would drop a recorded slow test, which would then
# pass as "not collected"
EVERY_MARK = ["-m", ""]
WORKERS = ["-n", "2"]                   # a light run (tests/suite_lock.py LIGHT_WORKERS)
PASSED, FAILED, NOT_RUN = 0, 1, 2


def hidden_environment() -> dict[str, str]:
    environment = {name: value for name, value in os.environ.items() if name != RECORD_ENV}
    environment[HIDE_ENV] = "1"
    # The plugin is imported as tests.encoder_check, from this checkout, whatever the rootdir
    environment["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), environment.get("PYTHONPATH")]))
    return environment


def pytest(root: str, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *PLUGIN, *EVERY_MARK, *arguments]
    return subprocess.run(command, cwd=root, env=hidden_environment(), capture_output=True, text=True, check=False)


def collected(root: str, ids: list[str]) -> list[str]:
    """Those of IDS that exist with the encoder hidden. Their files are collected, not the ids:
    pytest refuses, and lists nothing, when a named id is missing."""
    files = sorted({nodeid.partition("::")[0] for nodeid in ids})
    listing = pytest(root, ["--collect-only", "-q", *files])
    if listing.returncode not in (0, 5):        # 5: nothing collected
        raise RuntimeError(f"collecting {len(files)} files failed (pytest exit {listing.returncode}):\n"
                           f"{listing.stdout}{listing.stderr}")
    present = set(listing.stdout.splitlines())
    return [nodeid for nodeid in ids if nodeid in present]


def check(record: Path) -> int:
    records = read_records(record)
    if not records:
        print("encoder check: no test reached the level encoder (or it is not installed): nothing to check")
        return PASSED
    status = PASSED
    for root, ids in records.items():
        try:
            present = collected(root, ids)
        except RuntimeError as error:
            print(f"encoder check: {error}")
            return NOT_RUN
        guarded = len(ids) - len(present)
        if not present:
            print(f"encoder check: {len(ids)} tests reached the encoder; without it none is collected (guarded)")
            continue
        run = pytest(root, [*WORKERS, "-q", "-rfE", *present])
        summary = run.stdout.strip().splitlines()[-1] if run.stdout.strip() else "(no output)"
        print(f"encoder check: {len(ids)} tests reached the encoder; without it: {summary}"
              + (f"; {guarded} not collected (guarded at collection)" if guarded else ""))
        if run.returncode == 1:
            failed = [line for line in run.stdout.splitlines() if line.startswith(("FAILED", "ERROR"))]
            print("encoder check: FAILED: these tests need the private encoder but do not skip without it; "
                  "guard each with @pytest.mark.skipif(not level_encoding.is_available(), ...):")
            for line in failed:
                print(f"  {line}")
            status = FAILED
        elif run.returncode != 0:
            print(f"encoder check: the rerun could not be made (pytest exit {run.returncode}):")
            print(run.stdout + run.stderr)
            return NOT_RUN
    return status


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return NOT_RUN
    return check(Path(sys.argv[1]))


if __name__ == "__main__":
    sys.exit(main())
