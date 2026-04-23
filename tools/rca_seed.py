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
from zora.data_model import Direction, Item, RoomType, WallType
from zora.game_validator import GameValidator, DungeonLocation
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


def _get_connectivity_reached_rooms(level: object) -> set[int]:
    """Run _is_level_connected's flood fill and return the set of reached room_nums."""
    from zora.dungeon.shuffle_dungeon_rooms import (
        _is_path_obstructed, _OPPOSITE_DIR, _DIR_OFFSETS,
        _room_has_stairway,
    )
    level_room_nums = frozenset(r.room_num for r in level.rooms)
    room_by_num = {r.room_num: r for r in level.rooms}

    visited_states: set[tuple[int, Direction]] = set()
    reached_rooms: set[int] = set()
    queue: list[tuple[int, Direction]] = [
        (level.entrance_room, level.entrance_direction),
    ]

    def _expand(rn: int, entry_dir: Direction) -> None:
        state = (rn, entry_dir)
        if state in visited_states:
            return
        visited_states.add(state)
        reached_rooms.add(rn)
        if rn not in room_by_num:
            return
        room = room_by_num[rn]
        row, col = rn >> 4, rn & 0xF
        for exit_dir, offset in _DIR_OFFSETS:
            if exit_dir == Direction.NORTH and row == 0:
                continue
            if exit_dir == Direction.SOUTH and row == 7:
                continue
            if exit_dir == Direction.WEST and col == 0:
                continue
            if exit_dir == Direction.EAST and col == 15:
                continue
            if room.walls[exit_dir] == WallType.SOLID_WALL:
                continue
            if _is_path_obstructed(room.room_type, entry_dir, exit_dir):
                continue
            neighbor = rn + offset
            if neighbor not in level_room_nums:
                continue
            neighbor_entry = _OPPOSITE_DIR[exit_dir]
            if (neighbor, neighbor_entry) not in visited_states:
                queue.append((neighbor, neighbor_entry))

    while queue:
        rn, entry_dir = queue.pop()
        _expand(rn, entry_dir)

    changed = True
    while changed:
        changed = False
        for sr in level.staircase_rooms:
            if sr.room_num in reached_rooms:
                continue
            if sr.room_type != RoomType.TRANSPORT_STAIRCASE:
                continue
            can_enter = False
            for exit_rn in (sr.left_exit, sr.right_exit):
                if exit_rn in reached_rooms and exit_rn in room_by_num:
                    if _room_has_stairway(room_by_num[exit_rn]):
                        can_enter = True
                        break
            if can_enter:
                reached_rooms.add(sr.room_num)
                for exit_rn in (sr.left_exit, sr.right_exit):
                    state = (exit_rn, Direction.STAIRCASE)
                    if state not in visited_states:
                        queue.append(state)
                        changed = True
                while queue:
                    rn, entry_dir = queue.pop()
                    _expand(rn, entry_dir)

    return reached_rooms


def _print_l9_diagnostics(game_world: object) -> None:
    """Print L9 key economy and major item placement."""
    level = game_world.levels[8]  # L9 is index 8

    # Count locked doors
    locked_walls = 0
    locked_rooms: list[str] = []
    for room in level.rooms:
        for d in (Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST):
            if room.walls[d] in (WallType.LOCKED_DOOR_1, WallType.LOCKED_DOOR_2):
                locked_walls += 1
                locked_rooms.append(f"R{room.room_num:#04x} {d.name}")

    # Count key drops (rooms where enemies drop keys)
    key_rooms = [r for r in level.rooms if r.item == Item.KEY]

    print(f"\n L9 KEY ECONOMY", flush=True)
    print(f"  Locked door sides: {locked_walls} (unique doors ~ {locked_walls // 2})", flush=True)
    print(f"  Key-drop rooms: {len(key_rooms)}", flush=True)
    for r in locked_rooms:
        print(f"    {r}", flush=True)

    # Check where MAGICAL_KEY ended up
    magical_key_loc = None
    for room in level.rooms:
        if room.item == Item.MAGICAL_KEY:
            magical_key_loc = f"L9 R{room.room_num:#04x}"
    for sr in level.staircase_rooms:
        if sr.item == Item.MAGICAL_KEY:
            magical_key_loc = f"L9 staircase R{sr.room_num:#04x}"
    if magical_key_loc is None:
        for lv in game_world.levels:
            if lv.level_num == 9:
                continue
            for room in lv.rooms:
                if room.item == Item.MAGICAL_KEY:
                    magical_key_loc = f"L{lv.level_num} R{room.room_num:#04x}"
            for sr in lv.staircase_rooms:
                if sr.item == Item.MAGICAL_KEY:
                    magical_key_loc = f"L{lv.level_num} staircase R{sr.room_num:#04x}"
    if magical_key_loc is None:
        for cave in game_world.overworld.caves:
            if hasattr(cave, 'item') and cave.item == Item.MAGICAL_KEY:
                magical_key_loc = f"Cave {cave.destination.name}"
            elif hasattr(cave, 'items'):
                for ci in cave.items:
                    if hasattr(ci, 'item') and ci.item == Item.MAGICAL_KEY:
                        magical_key_loc = f"Cave {cave.destination.name}"
    print(f"  MAGICAL_KEY placed at: {magical_key_loc or 'not placed yet'}", flush=True)

    # Run validator to see what L9 rooms are reachable with full inventory
    from zora.inventory import Inventory
    validator = GameValidator(game_world, avoid_required_hard_combat=False)
    full_inv = Inventory()
    for item in Item:
        full_inv.items.add(item)
    full_inv.num_keys = 20
    for lvl in range(1, 9):
        full_inv.levels_with_triforce_obtained.append(lvl)
    reachable = validator.get_reachable_locations(assumed_inventory=full_inv)
    reachable_l9 = {loc for loc in reachable
                    if isinstance(loc, DungeonLocation) and loc.level_num == 9}
    all_l9_locs = set()
    for room in level.rooms:
        all_l9_locs.add(DungeonLocation(9, room.room_num))
    for sr in level.staircase_rooms:
        all_l9_locs.add(DungeonLocation(9, sr.room_num))
    unreachable_l9 = all_l9_locs - reachable_l9
    sr_nums = {sr.room_num for sr in level.staircase_rooms}
    room_nums = {r.room_num for r in level.rooms}
    if unreachable_l9:
        print(f"  L9 rooms unreachable even with full inventory ({len(unreachable_l9)}):", flush=True)
        for loc in sorted(unreachable_l9, key=lambda l: l.room_num):
            kind = "staircase" if loc.room_num in sr_nums else "room"
            if loc.room_num in sr_nums:
                sr = next(s for s in level.staircase_rooms if s.room_num == loc.room_num)
                if sr.room_type.name == "ITEM_STAIRCASE":
                    print(f"    R{loc.room_num:#04x} ({kind}, item={sr.item.name if sr.item else 'None'}, "
                          f"return_dest=R{sr.return_dest:#04x})", flush=True)
                else:
                    print(f"    R{loc.room_num:#04x} ({kind}, transport, "
                          f"exits=R{sr.left_exit:#04x}<->R{sr.right_exit:#04x})", flush=True)
            elif loc.room_num in room_nums:
                r = next(rm for rm in level.rooms if rm.room_num == loc.room_num)
                print(f"    R{loc.room_num:#04x} ({kind}, type={r.room_type.name}, item={r.item.name})", flush=True)
            else:
                print(f"    R{loc.room_num:#04x} (unknown — not in rooms or staircase_rooms!)", flush=True)
    else:
        print(f"  All L9 rooms reachable with full inventory", flush=True)

    # Show all staircase rooms
    print(f"\n  L9 STAIRCASE ROOMS ({len(level.staircase_rooms)}):", flush=True)
    for sr in level.staircase_rooms:
        reachable_str = "REACHABLE" if DungeonLocation(9, sr.room_num) in reachable_l9 else "UNREACHABLE"
        if sr.room_type.name == "ITEM_STAIRCASE":
            print(f"    R{sr.room_num:#04x} ITEM item={sr.item.name if sr.item else 'None'} "
                  f"return_dest=R{sr.return_dest:#04x} [{reachable_str}]", flush=True)
        else:
            print(f"    R{sr.room_num:#04x} TRANSPORT "
                  f"R{sr.left_exit:#04x}<->R{sr.right_exit:#04x} [{reachable_str}]", flush=True)

    # Compare connectivity check vs validator
    conn_reached = _get_connectivity_reached_rooms(level)
    val_reached = {loc.room_num for loc in reachable_l9}
    conn_only = conn_reached - val_reached
    val_only = val_reached - conn_reached
    if conn_only:
        print(f"\n  CONNECTIVITY-ONLY rooms (reached by conn check but NOT validator):", flush=True)
        for rn in sorted(conn_only):
            if rn in sr_nums:
                sr = next(s for s in level.staircase_rooms if s.room_num == rn)
                print(f"    R{rn:#04x} (staircase, {sr.room_type.name})", flush=True)
            elif rn in room_nums:
                r = next(rm for rm in level.rooms if rm.room_num == rn)
                print(f"    R{rn:#04x} (room, type={r.room_type.name})", flush=True)
            else:
                print(f"    R{rn:#04x} (unknown)", flush=True)
    if val_only:
        print(f"\n  VALIDATOR-ONLY rooms (reached by validator but NOT conn check):", flush=True)
        for rn in sorted(val_only):
            print(f"    R{rn:#04x}", flush=True)
    if not conn_only and not val_only:
        print(f"\n  Connectivity check and validator agree on reachable rooms.", flush=True)

    print(render_level_map(level), flush=True)


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
    _print_l9_diagnostics(gw)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    flags_set = {a for a in sys.argv[1:] if a.startswith("-")}
    verbose = "--verbose" in flags_set or "-v" in flags_set

    if len(args) < 2:
        print(f"Usage: python {sys.argv[0]} [-v|--verbose] <flag_string> <seed> [max_attempts]", flush=True)
        sys.exit(1)

    flag_string = args[0]
    seed = int(args[1])
    max_attempts = int(args[2]) if len(args) > 2 else MAX_ATTEMPTS

    if verbose:
        logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
        logging.getLogger("zora.item_randomizer").setLevel(logging.INFO)

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
