"""Benchmark a specific flagset: 10 seeds, 15s timeout, per-phase timing."""

import multiprocessing
import random
import signal
import sys
import time
import statistics
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "flags"))

from flags.flags_generated import (
    CosmeticFlags,
    Flags,
    decode_flags,
    resolve_random_flags,
)
from zora.generate_game import _RANDOMIZERS, _CRITICAL_STEPS
from zora.game_config import resolve_game_config
from zora.integrity_check import integrity_check
from zora.parser import load_bin_files, parse_game_world
from zora.level_gen.orchestrator import generate_dungeon_shapes
from zora.serializer import serialize_game_world
from zora.patch import build_ips_patch
from zora.patches import build_behavior_patch
from zora.hash_code import apply_hash_code
from zora.spoilers import build_spoiler_data, build_spoiler_log
from zora.rng import SeededRng

ROM_DATA = Path(__file__).resolve().parent.parent / "rom_data"

TIMEOUT = 15
NUM_SEEDS = 10
START_SEED = 1


def _run_seed(flags: Flags, seed: int) -> dict[str, Any]:
    """Run one seed and return phase timings. Executed in a subprocess."""
    bins = load_bin_files(ROM_DATA)
    rng = SeededRng(seed)
    config = resolve_game_config(flags, rng)

    original_bins_bytes = {
        "level_1_6_data.bin": bins.level_1_6_data,
        "level_7_9_data.bin": bins.level_7_9_data,
        "level_info.bin": bins.level_info,
        "overworld_data.bin": bins.overworld_data,
        "armos_item.bin": bins.armos_item,
        "coast_item.bin": bins.coast_item,
        "white_sword_requirement.bin": bins.white_sword_requirement,
        "magical_sword_requirement.bin": bins.magical_sword_requirement,
    }

    phases: dict[str, float] = {}
    retries: list[dict[str, Any]] = []
    total_t0 = time.monotonic()

    max_pipeline_attempts = 10
    for attempt in range(max_pipeline_attempts):
        game_world = parse_game_world(bins)
        phases.clear()
        try:
            t0 = time.monotonic()
            generate_dungeon_shapes(game_world, bins, config, rng)
            phases["dungeon_shapes"] = time.monotonic() - t0

            for step in _RANDOMIZERS:
                t0 = time.monotonic()
                step(game_world, config, rng)
                phases[step.__name__] = time.monotonic() - t0
                if step in _CRITICAL_STEPS:
                    integrity_check(game_world, step.__name__)
            break
        except RuntimeError as e:
            elapsed = time.monotonic() - total_t0
            retries.append({"attempt": attempt, "elapsed": elapsed, "error": str(e)[:80]})
            phases[f"retry_{attempt}"] = elapsed
            if attempt == max_pipeline_attempts - 1:
                raise

    t0 = time.monotonic()
    data_patch = serialize_game_world(
        game_world,
        original_bins_bytes,
        hint_mode=config.hint_mode,
        change_dungeon_nothing_code=config.shuffle_magical_sword and not config.progressive_items,
    )
    asm_patch = build_behavior_patch(config)
    final_patch = data_patch.merge(asm_patch)
    apply_hash_code(final_patch)
    build_spoiler_log(game_world, config, seed, "")
    build_spoiler_data(game_world, config, seed, "")
    phases["serialize_and_patch"] = time.monotonic() - t0

    total = time.monotonic() - total_t0
    return {"seed": seed, "total": total, "phases": phases, "ok": True,
            "retries": retries, "attempts": len(retries) + 1}


def _run_seed_in_process(flags: Flags, seed: int, timeout: int) -> dict[str, Any]:
    """Run _run_seed in a subprocess with a timeout."""
    ctx = multiprocessing.get_context("fork")
    parent_conn, child_conn = ctx.Pipe()

    def _target() -> None:
        try:
            result = _run_seed(flags, seed)
            child_conn.send(result)
        except Exception as e:
            child_conn.send({"seed": seed, "total": -1, "phases": {}, "ok": False, "error": str(e)})

    proc = ctx.Process(target=_target)
    proc.start()
    proc.join(timeout)

    if proc.is_alive():
        proc.kill()
        proc.join()
        return {"seed": seed, "total": timeout, "phases": {}, "ok": False, "error": "TIMEOUT"}

    if parent_conn.poll():
        return parent_conn.recv()
    return {"seed": seed, "total": timeout, "phases": {}, "ok": False, "error": "NO_RESULT"}


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

        result = _run_seed_in_process(resolved, seed, TIMEOUT)
        results.append(result)

        status = "OK" if result["ok"] else f"FAIL ({result.get('error', '?')})"
        total_str = f"{result['total']:.2f}s" if result["ok"] else f"{TIMEOUT:.0f}s"
        attempts = result.get("attempts", 1)
        retry_str = f"  ({attempts} attempts)" if attempts > 1 else ""
        print(f"Seed {seed:>5}: {total_str:>8}  {status}{retry_str}", flush=True)

        if result["ok"] and result["phases"]:
            slow_phases = sorted(
                result["phases"].items(), key=lambda kv: kv[1], reverse=True
            )
            for name, elapsed in slow_phases:
                if elapsed >= 0.01:
                    bar = "#" * int(min(elapsed, 15) * 4)
                    print(f"           {name:<30} {elapsed:>6.3f}s  {bar}", flush=True)
        print(flush=True)

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    ok_results = [r for r in results if r["ok"]]
    fail_results = [r for r in results if not r["ok"]]
    times = [r["total"] for r in results]  # failures count as TIMEOUT

    print(f"Seeds tested:  {num_seeds}")
    print(f"Successes:     {len(ok_results)}")
    print(f"Failures:      {len(fail_results)}")

    if times:
        print(f"Min:           {min(times):.2f}s")
        print(f"Max:           {max(times):.2f}s")
        print(f"Mean:          {statistics.mean(times):.2f}s")
        print(f"Median:        {statistics.median(times):.2f}s")
        if len(times) > 1:
            print(f"Stdev:         {statistics.stdev(times):.2f}s")
        print(f"Total:         {sum(times):.2f}s")

    if ok_results:
        print()
        print("Phase averages (successful seeds):")
        all_phase_names: list[str] = []
        for r in ok_results:
            for name in r["phases"]:
                if name not in all_phase_names:
                    all_phase_names.append(name)

        for name in all_phase_names:
            phase_times = [r["phases"].get(name, 0) for r in ok_results]
            avg = statistics.mean(phase_times)
            mx = max(phase_times)
            if avg >= 0.005:
                print(f"  {name:<30} avg={avg:.3f}s  max={mx:.3f}s")

    slow = [r for r in results if r["total"] > 5]
    print(f"\nSeeds > 5s:    {len(slow)}")
    timeout_seeds = [r for r in results if not r["ok"]]
    if timeout_seeds:
        print(f"Timed out:     {[r['seed'] for r in timeout_seeds]}")

    retry_results = [r for r in results if r.get("attempts", 1) > 1]
    if retry_results:
        print(f"Seeds retried: {len(retry_results)}")
        error_counts: dict[str, int] = {}
        for r in retry_results:
            for retry in r.get("retries", []):
                err = retry["error"]
                error_counts[err] = error_counts.get(err, 0) + 1
        if error_counts:
            print("\nRetry error breakdown:")
            for err, count in sorted(error_counts.items(), key=lambda kv: -kv[1]):
                print(f"  {count:>3}x  {err}")

    # RCA candidates: slowest seeds and failures, with ready-to-run commands
    rca_candidates = sorted(results, key=lambda r: r["total"], reverse=True)[:5]
    rca_candidates = [r for r in rca_candidates if r["total"] > 5 or not r["ok"]]
    if rca_candidates:
        print(f"\nRCA candidates (top {len(rca_candidates)} slowest/failed):")
        for r in rca_candidates:
            status = "FAIL" if not r["ok"] else f"{r['total']:.1f}s"
            attempts = r.get("attempts", 1)
            retry_info = f", {attempts} attempts" if attempts > 1 else ""
            errs = [rt["error"] for rt in r.get("retries", [])]
            err_summary = f" [{'; '.join(errs)}]" if errs else ""
            print(f"  Seed {r['seed']:>5} ({status}{retry_info}){err_summary}")
        print(f"\nRCA commands:")
        for r in rca_candidates:
            print(f"  python tools/rca_seed.py -v {flag_string} {r['seed']}")


if __name__ == "__main__":
    main()
