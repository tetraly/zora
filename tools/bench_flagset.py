"""Benchmark a specific flagset: 10 seeds, 15s timeout, subprocess isolation.

Runs each seed through the same generate_game codepath as the API/CLI to
ensure benchmark results reflect real user-facing behavior.
"""

import multiprocessing
import random
import sys
import time
import statistics
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "flags"))

from flags.flags_generated import (
    Flags,
    decode_flags,
    resolve_random_flags,
)
from zora.generate_game import generate_game

TIMEOUT = 15
NUM_SEEDS = 10
START_SEED = 1


def _run_seed(flags: Flags, seed: int, flag_string: str) -> dict[str, Any]:
    """Run one seed through generate_game. Executed in a subprocess."""
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
            "error": str(e)[:200],
        }


def _run_seed_in_process(
    flags: Flags, seed: int, flag_string: str, timeout: int,
) -> dict[str, Any]:
    """Run _run_seed in a subprocess with a timeout."""
    ctx = multiprocessing.get_context("fork")
    parent_conn, child_conn = ctx.Pipe()

    def _target() -> None:
        try:
            result = _run_seed(flags, seed, flag_string)
            child_conn.send(result)
        except Exception as e:
            child_conn.send({
                "seed": seed, "total": -1, "ok": False,
                "error": str(e)[:200],
            })

    proc = ctx.Process(target=_target)
    proc.start()
    proc.join(timeout)

    if proc.is_alive():
        proc.kill()
        proc.join()
        return {"seed": seed, "total": timeout, "ok": False, "error": "TIMEOUT"}

    if parent_conn.poll():
        return parent_conn.recv()
    return {"seed": seed, "total": timeout, "ok": False, "error": "NO_RESULT"}


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <flag_string> [num_seeds] [start_seed]")
        print(f"  Default: {NUM_SEEDS} seeds starting at seed {START_SEED}, {TIMEOUT}s timeout")
        sys.exit(1)

    flag_string = sys.argv[1]
    num_seeds = int(sys.argv[2]) if len(sys.argv) > 2 else NUM_SEEDS
    start_seed = int(sys.argv[3]) if len(sys.argv) > 3 else START_SEED

    base_flags = decode_flags(flag_string)
    print(f"Flagset: {flag_string}", flush=True)
    print(f"Seeds: {start_seed}..{start_seed + num_seeds - 1}  |  Timeout: {TIMEOUT}s", flush=True)
    print("=" * 70, flush=True)
    print(flush=True)

    results: list[dict[str, Any]] = []

    for i in range(num_seeds):
        seed = start_seed + i
        rng = random.Random(seed)
        resolved = resolve_random_flags(base_flags, rng)

        result = _run_seed_in_process(resolved, seed, flag_string, TIMEOUT)
        results.append(result)

        if result["ok"]:
            patch_info = f"  ({result.get('patch_size', '?')} bytes)"
            print(f"Seed {seed:>5}: {result['total']:>8.2f}s  OK{patch_info}", flush=True)
        else:
            err = result.get("error", "?")
            print(f"Seed {seed:>5}: {TIMEOUT:>8.0f}s  FAIL ({err})", flush=True)
        print(flush=True)

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    ok_results = [r for r in results if r["ok"]]
    fail_results = [r for r in results if not r["ok"]]

    print(f"Seeds tested:  {num_seeds}")
    print(f"Successes:     {len(ok_results)}")
    print(f"Failures:      {len(fail_results)}")

    if ok_results:
        ok_times = [r["total"] for r in ok_results]
        print(f"Min:           {min(ok_times):.2f}s")
        print(f"Max:           {max(ok_times):.2f}s")
        print(f"Mean:          {statistics.mean(ok_times):.2f}s")
        print(f"Median:        {statistics.median(ok_times):.2f}s")
        if len(ok_times) > 1:
            print(f"Stdev:         {statistics.stdev(ok_times):.2f}s")
        print(f"Total:         {sum(ok_times):.2f}s")

    slow = [r for r in ok_results if r["total"] > 5]
    print(f"\nSeeds > 5s:    {len(slow)}")
    if fail_results:
        print(f"Failed seeds:  {[r['seed'] for r in fail_results]}")

        error_counts: dict[str, int] = {}
        for r in fail_results:
            err = r.get("error", "unknown")
            error_counts[err] = error_counts.get(err, 0) + 1
        print("\nFailure breakdown:")
        for err, count in sorted(error_counts.items(), key=lambda kv: -kv[1]):
            print(f"  {count:>3}x  {err}")

    if fail_results:
        print(f"\nRCA commands:")
        for r in fail_results:
            print(f"  python tools/rca_seed.py -v {flag_string} {r['seed']}")


if __name__ == "__main__":
    main()
