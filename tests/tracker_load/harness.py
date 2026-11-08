"""Builds the pinned ZoraTracker into an ignored cache folder and runs its --load/--dump switch on a save file.

Nothing of ZoraTracker is committed here: the source of the pinned commit is exported with `git archive` into
artifacts/tracker-load-cache/ (ignored by git) and built there with `dotnet build`. The tests are opt-in:
`available()` says why they can't run, or None.
"""
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from functools import cache
from pathlib import Path
from typing import Any

from . import pin

OPT_IN = "ZORA_TRACKER_LOAD"
CACHE = Path(__file__).resolve().parents[2] / "artifacts" / "tracker-load-cache"
PROJECT = "Z1R_Avalonia_Desktop/Z1R_Avalonia_Desktop.csproj"
EXE = "ZoraTracker.CrossPlatform"
RUN_SECONDS = 120
BUILD_SECONDS = 540
# What the tracker leaves behind next to the program, cleared before each run so one run can't change the next
LEFTOVERS = ("Z1R_Tracker_settings.json", "Z1R_Tracker_recent_loads.txt", "Z1R_Tracker_crash_log.txt", "Saves")


def git(*args: str, **kw: Any) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", "-C", str(pin.REPO), *args], capture_output=True, check=False, **kw)


def available() -> str | None:
    """None when the ZoraTracker check can run; else why not (the reason a test skips with)."""
    if os.environ.get(OPT_IN) != "1":
        return f"opt-in: set {OPT_IN}=1 to run the tracker load tests (tests/tracker_load/README.md)"
    if shutil.which("dotnet") is None:
        return "needs .NET (dotnet is not on the path)"
    sdks = subprocess.run(["dotnet", "--list-sdks"], capture_output=True, text=True, check=False).stdout
    if not any(line.startswith("10.") for line in sdks.splitlines()):
        return "needs the .NET 10 SDK"
    if git("cat-file", "-e", f"{pin.COMMIT}^{{commit}}").returncode != 0:
        return f"needs ZoraTracker commit {pin.COMMIT[:8]} in {pin.REPO} (tests/tracker_load/pin.py)"
    return None


@cache
def build() -> Path:
    """The pinned commit built in the cache, as a folder holding the program (built once per commit)."""
    source = CACHE / f"ZoraTracker-{pin.COMMIT[:12]}"
    output = source / "Z1R_Avalonia_Desktop" / "bin" / "Release" / "net10.0"
    if not (output / EXE).exists():
        if source.exists():
            shutil.rmtree(source)
        source.mkdir(parents=True)
        archive = git("archive", pin.COMMIT)
        assert archive.returncode == 0, archive.stderr.decode()
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
            tar.extractall(source, filter="data")
        built = subprocess.run(["dotnet", "build", PROJECT, "-c", "Release", "-v", "q"], cwd=source,
                               capture_output=True, text=True, timeout=BUILD_SECONDS, check=False)
        assert built.returncode == 0, built.stdout[-3000:] + built.stderr[-1000:]
    return output


@cache
def program_folder() -> Path:
    """A copy of the build to run from (the tracker writes its settings next to itself); one per test session."""
    folder = Path(tempfile.mkdtemp(prefix="tracker-load-run-"))
    run = folder / "run"
    shutil.copytree(build(), run, symlinks=True)
    return run


def run_dump(save: Path, dump: Path) -> dict[str, Any]:
    """Loads SAVE in the tracker and returns its dump (warning, error, setProblems, save)."""
    run = program_folder()
    for name in LEFTOVERS:
        target = run / name
        shutil.rmtree(target) if target.is_dir() else target.unlink(missing_ok=True)
    dump.unlink(missing_ok=True)
    (run / "Z1R_Tracker_settings.json").write_text('{"Volume": 0}')      # the tracker's own volume setting: silent
    quiet = {**os.environ, "SDL_AUDIODRIVER": "dummy"}                  # and SDL (its sound library) plays nothing
    done = subprocess.run([str(run / EXE), f"--load={save}", f"--dump={dump}"], cwd=run, capture_output=True,
                          text=True, timeout=RUN_SECONDS, check=False, env=quiet)
    assert dump.exists(), f"no dump written (exit {done.returncode}): {done.stdout[-1500:]} {done.stderr[-1500:]}"
    return dict(json.loads(dump.read_text()))
