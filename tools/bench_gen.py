"""Benchmark seed generation with per-attempt retry diagnostics.

Usage:
    python tools/bench_gen.py <flag_string> [num_seeds] [start_seed]
    python tools/bench_gen.py --diag <flag_string> [seeds...]

Default mode: benchmark num_seeds (default 10) starting from start_seed (default 1).
Diag mode:    run specific seeds with verbose per-attempt error logging.

Output streams in real time (flush=True on all prints).
"""

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
from zora.generate_game import _RANDOMIZERS
from zora.game_config import resolve_game_config
from zora.parser import load_bin_files, parse_game_world
from zora.level_gen.orchestrator import generate_dungeon_shapes
from zora.rng import SeededRng

ROM_DATA = Path(__file__).resolve().parent.parent / "rom_data"

NUM_SEEDS = 10
START_SEED = 1
MAX_ATTEMPTS = 10
DIAG_TIMEOUT = 30


def _resolve(flag_string: str, seed: int) -> Flags:
    return resolve_random_flags(decode_flags(flag_string), random.Random(seed))


def _run_seed(flags: Flags, seed: int, verbose: bool = False) -> dict:
    """Run one seed through the pipeline with retry logging.

    Returns dict with keys: seed, total, ok, attempts (list of dicts).
    """
    bins = load_bin_files(ROM_DATA)
    rng = SeededRng(seed)
    config = resolve_game_config(flags, rng)

    attempts: list[dict] = []
    total_t0 = time.monotonic()

    for attempt in range(MAX_ATTEMPTS):
        game_world = parse_game_world(bins)
        attempt_t0 = time.monotonic()
        try:
            generate_dungeon_shapes(game_world, bins, config, rng)
            phase_times: dict[str, float] = {}
            for step in _RANDOMIZERS:
                t0 = time.monotonic()
                step(game_world, config, rng)
                phase_times[step.__name__] = time.monotonic() - t0

            elapsed = time.monotonic() - attempt_t0
            attempts.append({"attempt": attempt, "ok": True, "elapsed": elapsed, "phases": phase_times})
            total = time.monotonic() - total_t0
            return {"seed": seed, "total": total, "ok": True, "attempts": attempts}

        except RuntimeError as e:
            elapsed = time.monotonic() - attempt_t0
            attempts.append({"attempt": attempt, "ok": False, "elapsed": elapsed, "error": str(e)})
            if verbose:
                print(f"    attempt {attempt}: FAIL after {elapsed:.2f}s — {e}", flush=True)

        if verbose and time.monotonic() - total_t0 > DIAG_TIMEOUT:
            print(f"    GIVING UP after {time.monotonic() - total_t0:.1f}s", flush=True)
            total = time.monotonic() - total_t0
            return {"seed": seed, "total": total, "ok": False, "attempts": attempts}

    total = time.monotonic() - total_t0
    return {"seed": seed, "total": total, "ok": False, "attempts": attempts}


def _print_seed_result(result: dict) -> None:
    """Print a single seed's result with retry breakdown."""
    seed = result["seed"]
    total = result["total"]
    attempts = result["attempts"]

    if result["ok"]:
        n_retries = len(attempts) - 1
        retry_str = f" ({n_retries} retries)" if n_retries > 0 else ""
        print(f"Seed {seed:>5}: {total:>6.2f}s  OK{retry_str}", flush=True)

        if n_retries > 0:
            error_counts: dict[str, int] = {}
            retry_time = sum(a["elapsed"] for a in attempts if not a["ok"])
            for a in attempts:
                if not a["ok"]:
                    err = a["error"]
                    error_counts[err] = error_counts.get(err, 0) + 1
            for err, count in error_counts.items():
                print(f"           retry errors: {err} (x{count})", flush=True)
            print(f"           retry time:  {retry_time:.2f}s wasted", flush=True)

        last = attempts[-1]
        slow_phases = sorted(last["phases"].items(), key=lambda kv: kv[1], reverse=True)
        for name, elapsed in slow_phases:
            if elapsed >= 0.01:
                bar = "#" * int(min(elapsed, 15) * 4)
                print(f"           {name:<30} {elapsed:>6.3f}s  {bar}", flush=True)
    else:
        error_counts = {}
        for a in attempts:
            if not a["ok"]:
                err = a["error"]
                error_counts[err] = error_counts.get(err, 0) + 1
        print(f"Seed {seed:>5}: {total:>6.1f}s  FAIL after {len(attempts)} attempts", flush=True)
        for err, count in error_counts.items():
            print(f"           {err} (x{count})", flush=True)
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

    total_retries = sum(len(r["attempts"]) - 1 for r in ok)
    total_retry_time = sum(
        sum(a["elapsed"] for a in r["attempts"] if not a["ok"])
        for r in results
    )
    if total_retries > 0:
        print(f"\nRetries:       {total_retries} across {sum(1 for r in ok if len(r['attempts']) > 1)} seeds", flush=True)
        print(f"Retry time:    {total_retry_time:.1f}s wasted total", flush=True)

        all_errors: dict[str, int] = {}
        for r in results:
            for a in r["attempts"]:
                if not a["ok"]:
                    err = a["error"]
                    all_errors[err] = all_errors.get(err, 0) + 1
        print(f"\nRetry error breakdown:", flush=True)
        for err, count in sorted(all_errors.items(), key=lambda kv: -kv[1]):
            print(f"  {count:>3}x  {err}", flush=True)

    if ok:
        print(f"\nPhase averages (successful seeds):", flush=True)
        all_phase_names: list[str] = []
        for r in ok:
            last = r["attempts"][-1]
            for name in last["phases"]:
                if name not in all_phase_names:
                    all_phase_names.append(name)
        for name in all_phase_names:
            phase_times = [r["attempts"][-1]["phases"].get(name, 0) for r in ok]
            avg = statistics.mean(phase_times)
            mx = max(phase_times)
            if avg >= 0.005:
                print(f"  {name:<30} avg={avg:.3f}s  max={mx:.3f}s", flush=True)

    slow = [r for r in results if r["total"] > 5]
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
        result = _run_seed(flags, seed)
        results.append(result)
        _print_seed_result(result)

    _print_summary(results)


def diag_mode(flag_string: str, seeds: list[int]) -> None:
    print(f"Flagset: {flag_string}", flush=True)
    print(f"Diagnosing seeds: {seeds}", flush=True)
    print("=" * 70, flush=True)

    for seed in seeds:
        flags = _resolve(flag_string, seed)
        print(f"\nSeed {seed}:", flush=True)
        result = _run_seed(flags, seed, verbose=True)
        if result["ok"]:
            n_retries = len(result["attempts"]) - 1
            print(f"    SUCCESS on attempt {n_retries} ({result['total']:.2f}s total)", flush=True)
        else:
            print(f"    ALL ATTEMPTS FAILED ({result['total']:.1f}s)", flush=True)


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
