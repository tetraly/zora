"""Builds the data-level ZTracker probe (ztracker_probe/) against the pinned ZTracker commit and runs it on a save.

ZTracker's model and save classes (Z1R_Tracker/Z1R_Tracker/*.fs, no UI code) are read from `git archive` of the pinned
commit into the ignored cache folder and compiled for .NET 10 together with the probe; nothing of ZTracker is
copied into this repo. Its WPF window, and the file's room, monster and floor-drop names (which live in its WPF
project), do not run on a Mac: the names are read from its source text (DungeonRoomState.fs) instead.
"""
import io
import json
import re
import shutil
import subprocess
import tarfile
from functools import cache
from pathlib import Path
from typing import Any

from . import harness, pin

PROBE = Path(__file__).resolve().parent / "ztracker_probe"
MODEL = "Z1R_Tracker/Z1R_Tracker"
NAMES_SOURCE = "Z1R_Tracker/Z1R_WPF/DungeonRoomState.fs"


def available() -> str | None:
    reason = harness.available()
    if reason is not None:
        return reason
    have = subprocess.run(["git", "-C", str(pin.ZTRACKER_REPO), "cat-file", "-e", f"{pin.ZTRACKER_COMMIT}^{{commit}}"],
                          capture_output=True, check=False)
    return None if have.returncode == 0 else f"needs ZTracker commit {pin.ZTRACKER_COMMIT[:8]} in {pin.ZTRACKER_REPO}"


@cache
def source() -> Path:
    folder = harness.CACHE / f"ZTracker-{pin.ZTRACKER_COMMIT[:12]}"
    if not (folder / MODEL).exists():
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True)
        command = ["git", "-C", str(pin.ZTRACKER_REPO), "archive", pin.ZTRACKER_COMMIT, MODEL, NAMES_SOURCE]
        archive = subprocess.run(command, capture_output=True, check=True)
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
            tar.extractall(folder, filter="data")
    return folder


@cache
def build() -> Path:
    out = harness.CACHE / f"ztracker-probe-{pin.ZTRACKER_COMMIT[:12]}"
    stamp = out / "ZTrackerProbe.dll"
    if not stamp.exists() or stamp.stat().st_mtime < max(p.stat().st_mtime for p in PROBE.glob("*.fs*")):
        # (built from a copy in the cache, so no obj/ or bin/ folders appear in the repo)
        work = harness.CACHE / f"ztracker-probe-src-{pin.ZTRACKER_COMMIT[:12]}"
        shutil.rmtree(work, ignore_errors=True)
        shutil.copytree(PROBE, work)
        built = subprocess.run(["dotnet", "build", str(work / "ZTrackerProbe.fsproj"), "-c", "Release", "-v", "q",
                                f"-p:ZTrackerSrc={source() / MODEL}", "-o", str(out)],
                               capture_output=True, text=True, timeout=harness.BUILD_SECONDS, check=False)
        assert built.returncode == 0, built.stdout[-3000:] + built.stderr[-1000:]
    return stamp


def run_probe(save: Path) -> dict[str, Any]:
    done = subprocess.run(["dotnet", str(build()), str(save)], capture_output=True, text=True,
                          timeout=harness.RUN_SECONDS, check=False)
    assert done.returncode == 0, done.stdout[-1500:] + done.stderr[-1500:]
    return dict(json.loads(done.stdout.strip().splitlines()[-1]))


@cache
def names() -> dict[str, set[str]]:
    """The room-type, monster and floor-drop names ZTracker's loader knows (anything else it loads as "unmarked")."""
    text = (source() / NAMES_SOURCE).read_text(encoding="utf-8-sig")
    found: dict[str, set[str]] = {"RoomType": set(), "MonsterDetail": set(), "FloorDropDetail": set()}
    for kind, name in re.findall(r'"(RoomType|MonsterDetail|FloorDropDetail)_(\w+)"', text):
        found[kind].add(f"{kind}_{name}")
    return found
