"""Python side of the dungeon-room-shuffle parity harness.

Two entry points:

  run_python_remap_rooms(rom_path, rng) -> GameWorld
      Runs shuffle_dungeon_rooms() and returns the resulting GameWorld.

  parse_world_from_cs_output(cs_result, rom_path) -> GameWorld
      Takes the JSON dict from run_csharp.run_remap_rooms(), patches the
      three mutated bin-file slices into the original ROM bytes, and calls
      parse_game_world() to produce a GameWorld on the same semantic basis.

  diff_worlds(py_world, cs_world) -> list[dict]
      Compares two GameWorlds at the Level/Room level and returns structured
      field-level diffs.
"""

from pathlib import Path

from zora.data_model import GameWorld, Level, Room, StaircaseRoom
from zora.dungeon.shuffle_dungeon_rooms import shuffle_dungeon_rooms
from zora.parser import load_bin_files_from_rom, parse_game_world
from zora.rng import Rng
from zora.rom_layout import (
    LEVEL_1_6_DATA_ADDRESS,
    LEVEL_7_9_DATA_ADDRESS,
    LEVEL_INFO_ADDRESS,
)


def run_python_remap_rooms(
    rom_path: Path | str,
    rng: Rng,
    *,
    must_beat_ganon: bool = True,
) -> tuple[bool, GameWorld]:
    """Run Python shuffle_dungeon_rooms() and return (success, GameWorld).

    Args:
        rom_path: Path to a ZORA-randomized Zelda 1 ROM.
        rng: RNG instance. Pass StubRng() for deterministic stub output.
        must_beat_ganon: Forwarded to shuffle_dungeon_rooms().

    Returns:
        (success, world) where success mirrors the return value of
        shuffle_dungeon_rooms() and world is the post-shuffle GameWorld.
    """
    rom_bytes = Path(rom_path).read_bytes()
    bins = load_bin_files_from_rom(rom_bytes)
    world = parse_game_world(bins)
    success = shuffle_dungeon_rooms(world, rng, must_beat_gannon=must_beat_ganon)
    return success, world


def parse_world_from_cs_output(cs_result: dict, rom_path: Path | str) -> GameWorld:
    """Reconstruct a GameWorld from the C# parity runner's JSON output.

    Takes the three mutated bin-file slices from cs_result['bins'], patches
    them into the original ROM bytes, and calls parse_game_world() on the
    result — the same parse path used by the Python side.

    Args:
        cs_result: Dict returned by run_csharp.run_remap_rooms().
        rom_path:  Path to the original ROM (supplies all unmutated slices).
    """
    rom_bytes = bytearray(Path(rom_path).read_bytes())

    bins = cs_result["bins"]

    # Patch the three slices that RemapDungeonRooms can mutate.
    _patch(rom_bytes, LEVEL_1_6_DATA_ADDRESS, bins["level_1_6_data.bin"])
    _patch(rom_bytes, LEVEL_7_9_DATA_ADDRESS, bins["level_7_9_data.bin"])
    _patch(rom_bytes, LEVEL_INFO_ADDRESS,     bins["level_info.bin"])

    raw_bins = load_bin_files_from_rom(bytes(rom_bytes))
    return parse_game_world(raw_bins)


def _patch(rom: bytearray, address: int, hex_str: str) -> None:
    data = bytes.fromhex(hex_str)
    rom[address: address + len(data)] = data


# ---------------------------------------------------------------------------
# Semantic diff
# ---------------------------------------------------------------------------

def diff_worlds(py_world: GameWorld, cs_world: GameWorld) -> list[dict]:
    """Compare two GameWorlds at the Level/Room/field level.

    Returns a list of diff dicts. Each dict has:
      level     - level number (1-9)
      room_num  - room number, or None for level-level fields
      field     - field name that differs
      py        - Python value
      cs        - C# value

    Only compares the dungeon levels (not overworld, sprites, enemies, quotes)
    since those are not touched by RemapDungeonRooms.
    """
    diffs: list[dict] = []

    for py_level, cs_level in zip(py_world.levels, cs_world.levels):
        lvl = py_level.level_num

        # Level-level fields that RemapDungeonRooms can change.
        for field in ("entrance_room", "boss_room"):
            pv = getattr(py_level, field)
            cv = getattr(cs_level, field)
            if pv != cv:
                diffs.append({"level": lvl, "room_num": None, "field": field, "py": pv, "cs": cv})

        # Index rooms by room_num for stable comparison.
        py_rooms = {r.room_num: r for r in py_level.rooms}
        cs_rooms = {r.room_num: r for r in cs_level.rooms}

        all_room_nums = sorted(py_rooms.keys() | cs_rooms.keys())
        for rn in all_room_nums:
            py_room = py_rooms.get(rn)
            cs_room = cs_rooms.get(rn)

            if py_room is None:
                diffs.append({"level": lvl, "room_num": rn, "field": "<room>",
                              "py": "missing", "cs": "present"})
                continue
            if cs_room is None:
                diffs.append({"level": lvl, "room_num": rn, "field": "<room>",
                              "py": "present", "cs": "missing"})
                continue

            _diff_rooms(lvl, rn, py_room, cs_room, diffs)

    return diffs


_ROOM_FIELDS = (
    "room_type", "walls", "enemy_spec", "enemy_quantity",
    "item", "item_position", "room_action",
    "is_dark", "boss_cry_1", "boss_cry_2", "movable_block",
)


def _diff_rooms(lvl: int, rn: int, py_r: Room, cs_r: Room, out: list[dict]) -> None:
    for field in _ROOM_FIELDS:
        pv = getattr(py_r, field)
        cv = getattr(cs_r, field)
        if pv != cv:
            out.append({"level": lvl, "room_num": rn, "field": field, "py": pv, "cs": cv})
