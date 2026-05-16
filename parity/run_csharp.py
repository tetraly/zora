"""Subprocess wrapper for the C# ParityRunner.

Prefers the self-contained binary (publish/parity-runner) for speed.
Falls back to `dotnet run` if the binary hasn't been built yet.

Build the self-contained binary once with:
    cd parity/csharp/ParityRunner
    dotnet publish -r osx-arm64 --self-contained true -o ./publish
"""

import json
import subprocess
from pathlib import Path

_RUNNER_DIR = Path(__file__).parent / "csharp" / "ParityRunner"
_BINARY = _RUNNER_DIR / "publish" / "parity-runner"
_CSPROJ = _RUNNER_DIR / "ParityRunner.csproj"


def _build_cmd(
    rom_path: Path | str,
    stub_rng: bool,
    quest: int,
    hash_rng: bool = False,
    hash_seed: int = 12345,
) -> list[str]:
    args = ["remap-rooms", str(rom_path)]
    if stub_rng:
        args.append("--stub-rng")
    if hash_rng:
        args += ["--hash-rng", str(hash_seed)]
    args += ["--quest", str(quest)]

    if _BINARY.exists():
        return [str(_BINARY)] + args
    # Fall back to dotnet run (slower, requires matching runtime).
    return ["dotnet", "run", "--project", str(_CSPROJ), "--"] + args


def run_remap_rooms(
    rom_path: Path | str,
    *,
    stub_rng: bool = False,
    hash_rng: bool = False,
    hash_seed: int = 12345,
    quest: int = 1,
) -> dict:
    """Run RemapDungeonRooms via the C# parity runner.

    Returns the parsed JSON output dict with keys:
      success   - bool, whether RemapDungeonRooms returned True
      stub_rng  - bool, echo of the flag
      quest     - int, echo of the quest param
      bins      - dict mapping bin filename to lowercase hex string
                  keys: level_1_6_data.bin, level_7_9_data.bin, level_info.bin
    """
    cmd = _build_cmd(rom_path, stub_rng, quest, hash_rng=hash_rng, hash_seed=hash_seed)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"parity-runner failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return json.loads(result.stdout)
