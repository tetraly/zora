"""Parity tests: confirm Python shuffle_dungeon_rooms() matches C# RemapDungeonRooms().

Run with:
    cd /Users/em/Desktop/zora2
    pytest parity/test_parity.py -v

Requirements:
  - A ZORA-randomized Zelda 1 ROM at the path in ROM_PATH (or set PARITY_ROM env var).
  - dotnet 9+ on PATH, or a pre-built publish/parity-runner binary.
"""

import os
from pathlib import Path

import pytest

ROM_PATH = Path(os.environ.get("PARITY_ROM", "rom_data/zelda-prg1_1234_3Ax8k4g.nes"))

pytestmark = pytest.mark.skipif(
    not ROM_PATH.exists(),
    reason=f"Parity ROM not found at {ROM_PATH}. Set PARITY_ROM env var.",
)

_HASH_SEED = 12345


def _run_both(rom_path: Path, hash_seed: int = _HASH_SEED, quest: int = 1):
    """Run both sides with HashRng and return (py_success, cs_success, py_world, cs_world, diffs)."""
    from parity.harness import diff_worlds, parse_world_from_cs_output, run_python_remap_rooms
    from parity.hash_rng import HashRng
    from parity.run_csharp import run_remap_rooms

    rng = HashRng(seed=hash_seed)
    py_success, py_world = run_python_remap_rooms(rom_path, rng)
    cs_result = run_remap_rooms(rom_path, hash_rng=True, hash_seed=hash_seed, quest=quest)
    cs_world = parse_world_from_cs_output(cs_result, rom_path)

    diffs = diff_worlds(py_world, cs_world)
    return py_success, cs_result["success"], py_world, cs_world, diffs


class TestHashRngParity:
    """Parity tests using HashRng (SHA-256-based deterministic RNG).

    Both sides use abs(SHA-256(seed||counter)) % N for each draw, so any
    divergence is a pure logic bug rather than an arithmetic mismatch.
    """

    def test_worlds_match(self):
        py_ok, cs_ok, py_world, cs_world, diffs = _run_both(ROM_PATH)
        if diffs:
            lines = [f"\nParity FAIL — {len(diffs)} field(s) differ with hash RNG (seed={_HASH_SEED}):"]
            by_level: dict[int, list[dict]] = {}
            for d in diffs:
                by_level.setdefault(d["level"], []).append(d)
            for lvl, lvl_diffs in sorted(by_level.items()):
                lines.append(f"\n  Level {lvl} ({len(lvl_diffs)} diff(s)):")
                for d in lvl_diffs[:15]:
                    rn = d["room_num"]
                    loc = f"room {rn}" if rn is not None else "level"
                    lines.append(f"    {loc}.{d['field']}: py={d['py']!r}  cs={d['cs']!r}")
                if len(lvl_diffs) > 15:
                    lines.append(f"    ... and {len(lvl_diffs) - 15} more")
            pytest.fail("\n".join(lines))

    def test_both_sides_report_success(self):
        py_ok, cs_ok, *_ = _run_both(ROM_PATH)
        assert py_ok is True, "Python shuffle_dungeon_rooms returned False"
        assert cs_ok is True, "C# RemapDungeonRooms returned False"
