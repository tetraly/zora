"""Visualize dungeon layouts from the level generator.

Usage:
    python tools/visualize_dungeon_shapes.py [seed]

Generates new dungeon shapes for the given seed (default: 42) and prints
ASCII maps of all 9 levels.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flags.flags_generated import Flags, Tristate
from zora.game_config import resolve_game_config
from zora.level_gen.orchestrator import generate_dungeon_shapes
from zora.parser import load_bin_files, parse_game_world
from zora.rng import SeededRng
from tools.dungeon_map import render_level_map

ROM_DATA = Path(__file__).resolve().parent.parent / "rom_data"


def main() -> None:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 42

    bins = load_bin_files(ROM_DATA)

    flags = Flags()
    flags.dungeon_shapes = Tristate.ON
    rng = SeededRng(seed)
    config = resolve_game_config(flags, rng)

    game_world = parse_game_world(bins)
    generate_dungeon_shapes(game_world, bins, config, rng)

    print(f"Seed: {seed}\n")
    for lv in game_world.levels:
        print(f"{'=' * 60}")
        print(f"Level {lv.level_num}: {len(lv.rooms)} rooms, "
              f"{len(lv.staircase_rooms)} staircases, "
              f"boss=0x{lv.boss_room:02X}, entrance=0x{lv.entrance_room:02X}")
        items = [r for r in lv.rooms if r.item.name != "NOTHING"]
        stair_items = [s for s in lv.staircase_rooms if s.item and s.item.name != "NOTHING"]
        print(f"  Items in rooms: {len(items)}, items in staircases: {len(stair_items)}")
        print(render_level_map(lv))
        print()


if __name__ == "__main__":
    main()
