"""RCA diagnostic tool for failed/slow seed generation.

Usage:
    python tools/rca_seed.py <flag_string> <seed> [max_attempts]

Runs a single seed through the pipeline with detailed per-attempt diagnostics:
- Timeline table of all attempts with phase timing
- On failure: identifies the problematic level/room and renders ASCII dungeon maps
- On success: shows total time and retry breakdown

Designed for root-cause analysis of slow or failing seeds.
"""

from __future__ import annotations

import logging
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "flags"))

from flags.flags_generated import decode_flags, resolve_random_flags
from zora.generate_game import _RANDOMIZERS
from zora.game_config import resolve_game_config
from zora.parser import load_bin_files, parse_game_world
from zora.level_gen.orchestrator import generate_dungeon_shapes
from zora.rng import SeededRng
from zora.dungeon.shuffle_dungeon_rooms import _is_level_connected
from tools.dungeon_map import render_level_map

ROM_DATA = Path(__file__).resolve().parent.parent / "rom_data"

MAX_ATTEMPTS = 10


def _run_attempt(
    bins: dict,
    config: object,
    rng: object,
) -> dict:
    """Run one pipeline attempt. Returns attempt result dict."""
    game_world = parse_game_world(bins)
    t0 = time.monotonic()
    phase_times: dict[str, float] = {}
    try:
        pt = time.monotonic()
        generate_dungeon_shapes(game_world, bins, config, rng)
        phase_times["generate_dungeon_shapes"] = time.monotonic() - pt

        for step in _RANDOMIZERS:
            pt = time.monotonic()
            step(game_world, config, rng)
            phase_times[step.__name__] = time.monotonic() - pt

        return {
            "ok": True,
            "elapsed": time.monotonic() - t0,
            "phases": phase_times,
            "game_world": game_world,
        }
    except RuntimeError as e:
        return {
            "ok": False,
            "elapsed": time.monotonic() - t0,
            "error": str(e),
            "phases": phase_times,
            "game_world": game_world,
        }


def _print_timeline(attempts: list[dict]) -> None:
    """Print a timeline table of all attempts."""
    print("\n TIMELINE", flush=True)
    print("-" * 70, flush=True)
    print(f"{'#':>3}  {'Time':>7}  {'Result':<6}  {'Details'}", flush=True)
    print("-" * 70, flush=True)
    for i, a in enumerate(attempts):
        status = "OK" if a["ok"] else "FAIL"
        details = ""
        if not a["ok"]:
            details = a["error"]
        else:
            slow = sorted(a["phases"].items(), key=lambda kv: -kv[1])
            top = [f"{n}={t:.2f}s" for n, t in slow[:3] if t >= 0.01]
            details = ", ".join(top)
        print(f"{i:>3}  {a['elapsed']:>6.2f}s  {status:<6}  {details}", flush=True)
    print("-" * 70, flush=True)
    total = sum(a["elapsed"] for a in attempts)
    wasted = sum(a["elapsed"] for a in attempts if not a["ok"])
    print(f"Total: {total:.2f}s  (wasted on retries: {wasted:.2f}s)", flush=True)


def _print_connectivity(game_world: object) -> None:
    """Check and print connectivity status for all levels."""
    print("\n CONNECTIVITY CHECK", flush=True)
    all_ok = True
    for level in game_world.levels:
        connected = _is_level_connected(level)
        if not connected:
            all_ok = False
            print(f"  L{level.level_num}: NOT CONNECTED", flush=True)
            print(render_level_map(level), flush=True)
    if all_ok:
        print("  All levels connected", flush=True)


def _print_failed_attempt_details(attempt: dict, attempt_num: int) -> None:
    """Print detailed diagnostics for a failed attempt."""
    print(f"\n ATTEMPT {attempt_num} DETAILS (FAILED)", flush=True)
    print(f"  Error: {attempt['error']}", flush=True)

    if attempt["phases"]:
        print(f"  Phase timing:", flush=True)
        for name, elapsed in sorted(attempt["phases"].items(), key=lambda kv: -kv[1]):
            if elapsed >= 0.01:
                print(f"    {name:<35} {elapsed:.3f}s", flush=True)

    gw = attempt.get("game_world")
    if gw is None:
        return

    _print_connectivity(gw)


def main() -> None:
    if len(sys.argv) < 3:
        print(f"Usage: python {sys.argv[0]} <flag_string> <seed> [max_attempts]", flush=True)
        sys.exit(1)

    flag_string = sys.argv[1]
    seed = int(sys.argv[2])
    max_attempts = int(sys.argv[3]) if len(sys.argv) > 3 else MAX_ATTEMPTS

    print(f"RCA Diagnostic: seed {seed}", flush=True)
    print(f"Flagset: {flag_string}", flush=True)
    print(f"Max attempts: {max_attempts}", flush=True)
    print("=" * 70, flush=True)

    flags = resolve_random_flags(decode_flags(flag_string), random.Random(seed))
    bins = load_bin_files(ROM_DATA)
    rng = SeededRng(seed)
    config = resolve_game_config(flags, rng)

    attempts: list[dict] = []
    for i in range(max_attempts):
        print(f"\nAttempt {i}...", end="", flush=True)
        result = _run_attempt(bins, config, rng)
        attempts.append(result)
        if result["ok"]:
            print(f" OK ({result['elapsed']:.2f}s)", flush=True)
            break
        else:
            print(f" FAIL ({result['elapsed']:.2f}s): {result['error']}", flush=True)

    _print_timeline(attempts)

    failed = [a for a in attempts if not a["ok"]]
    if failed:
        slowest = max(failed, key=lambda a: a["elapsed"])
        idx = attempts.index(slowest)
        _print_failed_attempt_details(slowest, idx)

    if attempts[-1]["ok"]:
        print(f"\n SEED SUCCEEDED on attempt {len(attempts) - 1}", flush=True)
    else:
        print(f"\n SEED FAILED after {len(attempts)} attempts", flush=True)


if __name__ == "__main__":
    main()
