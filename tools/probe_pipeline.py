"""Trace a seed through generate_game's pipeline-retry loop, showing per-attempt
L9 reachability transitions, integrity-check status, and final fault.

Usage:
    python tools/probe_pipeline.py <flag_string> <seed> [max_attempts]

Example:
    python tools/probe_pipeline.py FUBRVAAASKh8eKCIG6QBRVRCVV 12313
    python tools/probe_pipeline.py FUBRVAAASKh8eKCIG6QBRVRCVV 12313 50
"""
from __future__ import annotations
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "flags"))

from flags.flags_generated import decode_flags, resolve_random_flags
from zora.api.validation import parse_flag_string
from zora.parser import load_bin_files, parse_game_world
from zora.level_gen.orchestrator import generate_dungeon_shapes, _l9_fully_reachable
from zora.game_config import resolve_game_config
from zora.rng import SeededRng
from zora.integrity_check import integrity_check, IntegrityError
from zora.generate_game import _RANDOMIZERS, _CRITICAL_STEPS, _clear_boss_cry_bits
from zora.dungeon.shuffle_dungeon_rooms import _fix_special_rooms


def main() -> None:
    if len(sys.argv) not in (3, 4):
        print(f"Usage: python {sys.argv[0]} <flag_string> <seed> [max_attempts]")
        sys.exit(1)

    raw_flag_string = sys.argv[1]
    seed = int(sys.argv[2])
    max_attempts = int(sys.argv[3]) if len(sys.argv) == 4 else 10

    flag_string, errs = parse_flag_string(raw_flag_string)
    if errs:
        print(f"Flag-string errors: {errs}")
        sys.exit(1)

    flags_random = random.Random(seed)
    flags = decode_flags(flag_string)
    resolved = resolve_random_flags(flags, flags_random)

    bins = load_bin_files(Path(__file__).resolve().parent.parent / "rom_data")
    rng = SeededRng(seed)
    config = resolve_game_config(resolved, rng)

    print(f"Flagset: {flag_string}")
    print(f"Seed:    {seed}")

    summary: list[str] = []

    for attempt in range(max_attempts):
        print(f"\n--- Attempt {attempt} ---", flush=True)
        gw = parse_game_world(bins)
        try:
            generate_dungeon_shapes(gw, bins, config, rng)
        except RuntimeError as e:
            print(f"  shapes raised: {e}")
            summary.append(f"  {attempt}: shapes raised")
            continue

        # Replicate the post-shapes fix that generate_game does
        _clear_boss_cry_bits(gw)
        for level in gw.levels:
            _fix_special_rooms(level, gw)

        print(f"  after shapes+fix: L9 reach = {_l9_fully_reachable(gw)}")
        try:
            integrity_check(gw, "generate_dungeon_shapes")
        except IntegrityError as e:
            print(f"  integrity post-shapes FAIL: {str(e)[:200]}")
            summary.append(f"  {attempt}: integrity after shapes")
            continue

        # Run all randomizers, checking after each
        broke_at: str | None = None
        for step in _RANDOMIZERS:
            before = _l9_fully_reachable(gw)
            try:
                step(gw, config, rng)
            except RuntimeError as e:
                print(f"  {step.__name__} raised: {e}")
                broke_at = f"{step.__name__} raised"
                break
            after = _l9_fully_reachable(gw)
            marker = "  <-- BROKE" if before and not after else ""
            if step in _CRITICAL_STEPS:
                try:
                    integrity_check(gw, step.__name__)
                    ic = "ok"
                except IntegrityError as e:
                    ic = f"FAIL: {str(e)[:120]}"
                print(f"  {step.__name__}: reach {before}->{after}, integrity={ic}{marker}")
                if "FAIL" in ic:
                    broke_at = f"integrity after {step.__name__}"
                    break
            else:
                if before and not after:
                    print(f"  {step.__name__}: reach {before}->{after}{marker}")

        if broke_at is None:
            print("  PIPELINE OK")
            summary.append(f"  {attempt}: OK")
            print("\n=== SUMMARY ===")
            for s in summary:
                print(s)
            return
        else:
            summary.append(f"  {attempt}: {broke_at}")

    print("\n=== SUMMARY ===")
    for s in summary:
        print(s)
    print(f"All {max_attempts} attempts exhausted, no successful generation.")


if __name__ == "__main__":
    main()
