"""Benchmark seed generation through the full generate_game codepath.

Usage:
    python tools/bench_gen.py <flag_string> [num_seeds] [start_seed]
    python tools/bench_gen.py --diag <flag_string> [seeds...]

Default mode: benchmark num_seeds (default 10) starting from start_seed (default 1).
Diag mode:    run specific seeds with verbose logging.

Uses the same generate_game function as the API/CLI to ensure results
reflect real user-facing behavior.
"""

import logging
import random
import sys
import time
import statistics
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "flags"))

from flags.flags_generated import (
    Flags,
    decode_flags,
    resolve_random_flags,
)
from zora.generate_game import generate_game

NUM_SEEDS = 10
START_SEED = 1
DIAG_TIMEOUT = 30


def _resolve(flag_string: str, seed: int) -> Flags:
    return resolve_random_flags(decode_flags(flag_string), random.Random(seed))


def _run_seed(flags: Flags, seed: int, flag_string: str) -> dict:
    """Run one seed through generate_game.

    Returns dict with keys: seed, total, ok, error (on failure), patch_size (on success).
    """
    t0 = time.monotonic()
    try:
        patch_bytes, hash_code, spoiler_log, spoiler_data = generate_game(
            flags, seed, flag_string=flag_string,
        )
        elapsed = time.monotonic() - t0
        return {
            "seed": seed, "total": elapsed, "ok": True,
            "patch_size": len(patch_bytes),
        }
    except RuntimeError as e:
        elapsed = time.monotonic() - t0
        return {
            "seed": seed, "total": elapsed, "ok": False,
            "error": str(e),
        }


def _print_seed_result(result: dict) -> None:
    """Print a single seed's result."""
    seed = result["seed"]
    total = result["total"]

    if result["ok"]:
        patch_info = f" ({result.get('patch_size', '?')} bytes)"
        print(f"Seed {seed:>5}: {total:>6.2f}s  OK{patch_info}", flush=True)
    else:
        print(f"Seed {seed:>5}: {total:>6.2f}s  FAIL", flush=True)
        print(f"           {result['error']}", flush=True)
    print(flush=True)


def _print_summary(results: list[dict]) -> None:
    print("=" * 70, flush=True)
    print("SUMMARY", flush=True)
    print("=" * 70, flush=True)

    ok = [r for r in results if r["ok"]]
    fail = [r for r in results if not r["ok"]]

    print(f"Seeds tested:  {len(results)}", flush=True)
    print(f"Successes:     {len(ok)}", flush=True)
    print(f"Failures:      {len(fail)}", flush=True)

    if ok:
        ok_times = [r["total"] for r in ok]
        print(f"Min:           {min(ok_times):.2f}s", flush=True)
        print(f"Max:           {max(ok_times):.2f}s", flush=True)
        print(f"Mean:          {statistics.mean(ok_times):.2f}s", flush=True)
        print(f"Median:        {statistics.median(ok_times):.2f}s", flush=True)
        if len(ok_times) > 1:
            print(f"Stdev:         {statistics.stdev(ok_times):.2f}s", flush=True)

    slow = [r for r in ok if r["total"] > 5]
    print(f"\nSeeds > 5s:    {len(slow)}", flush=True)
    if fail:
        print(f"Failed seeds:  {[r['seed'] for r in fail]}", flush=True)
    print(flush=True)


def bench_mode(flag_string: str, num_seeds: int, start_seed: int) -> None:
    print(f"Flagset: {flag_string}", flush=True)
    print(f"Seeds: {start_seed}..{start_seed + num_seeds - 1}", flush=True)
    print("=" * 70, flush=True)
    print(flush=True)

    results: list[dict] = []
    for i in range(num_seeds):
        seed = start_seed + i
        flags = _resolve(flag_string, seed)
        result = _run_seed(flags, seed, flag_string)
        results.append(result)
        _print_seed_result(result)

    _print_summary(results)


def diag_mode(flag_string: str, seeds: list[int]) -> None:
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

    print(f"Flagset: {flag_string}", flush=True)
    print(f"Diagnosing seeds: {seeds}", flush=True)
    print("=" * 70, flush=True)

    for seed in seeds:
        flags = _resolve(flag_string, seed)
        print(f"\nSeed {seed}:", flush=True)
        result = _run_seed(flags, seed, flag_string)
        if result["ok"]:
            print(f"    SUCCESS ({result['total']:.2f}s, {result.get('patch_size', '?')} bytes)", flush=True)
        else:
            print(f"    FAILED ({result['total']:.2f}s): {result['error']}", flush=True)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage:", flush=True)
        print(f"  python {sys.argv[0]} <flag_string> [num_seeds] [start_seed]", flush=True)
        print(f"  python {sys.argv[0]} --diag <flag_string> [seed1 seed2 ...]", flush=True)
        sys.exit(1)

    if sys.argv[1] == "--diag":
        flag_string = sys.argv[2]
        seeds = [int(s) for s in sys.argv[3:]] if len(sys.argv) > 3 else list(range(1, 11))
        diag_mode(flag_string, seeds)
    else:
        flag_string = sys.argv[1]
        num_seeds = int(sys.argv[2]) if len(sys.argv) > 2 else NUM_SEEDS
        start_seed = int(sys.argv[3]) if len(sys.argv) > 3 else START_SEED
        bench_mode(flag_string, num_seeds, start_seed)


if __name__ == "__main__":
    main()
