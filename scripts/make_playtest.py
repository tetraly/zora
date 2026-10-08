"""Generate playable ZORA test ROMs from a flag string for human playtesting.

- writes ROMs to temp/playtest/ (git-ignored; ROMs are never committed), or
  to --outdir
- verifies each: parse→serialize→apply byte-identity round-trip, every spec
  check (incl. the raw checks where applicable); with level encoding on,
  these run on the seed's plain twin and the encoded ROM's level data must
  decode back to the twin's
- emits per-level text maps + door/key tallies into the report
  (default temp/playtest_report.md)

Usage: python3 scripts/make_playtest.py [--seeds 1 2 3 4 5] [--flags STRING]
                                        [--outdir DIR] [--report FILE]
"""
import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from zora.measure.checks import run_checks  # noqa: E402
from zora.model.enums import Enemy, Item, RoomType, Side, WallType  # noqa: E402
from zora.model.game_world import GameWorld
from zora.model.levels import Level

from dataclasses import replace  # noqa: E402

from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF  # noqa: E402
from zora.rom import level_encoding
from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom  # noqa: E402
from zora.generate.pipeline import FlagsRefused, generate_world, plan  # noqa: E402
from zora.rom.parse.rom_file import load_rom, parse_rom  # noqa: E402
from zora.rom.serialize.rom_file import serialize_to_rom
from zora.rom.player_settings import PlayerSettingError, parse_player_settings  # noqa: E402
from zora.model.room_grid import neighbour  # noqa: E402
from zora.generate.shapes.tables import PERSON_LIST_DEFAULT, L9_PERSON_LISTS, EXTRA_PERSON_5_7  # noqa: E402

PERSON_LISTS = {0x4B, 0x4C, 0x4D, 0x4E, 0x4F, 0x50, 0x51, 0x52}

def level_map_text(gw: GameWorld, lvl: Level, owners: dict[int, int]) -> str:
    cell_char: dict[int, str] = {}
    stair_cells = {s.room_num for s in lvl.staircase_rooms}
    for r in lvl.rooms:
        e = r.enemy
        if r.room_num == lvl.entrance_room:
            ch = "E"
        elif r.room_type == RoomType.TRIFORCE_ROOM:
            ch = "T"
        elif r.room_type == RoomType.GANON_ROOM:
            ch = "G"
        elif r.room_type == RoomType.ZELDA_ROOM:
            ch = "Z"
        elif e.value == Enemy.HUNGRY_GORIYA:
            ch = "g"
        elif r.room_type == RoomType.BLACK_ROOM or e.value in PERSON_LISTS:
            ch = "P"
        elif r.room_num in {s.left_exit for s in lvl.staircase_rooms} | \
                {s.right_exit for s in lvl.staircase_rooms} | \
                {s.return_dest for s in lvl.staircase_rooms}:
            ch = "s"
        else:
            ch = "#"
        cell_char[r.room_num] = ch
    for s in stair_cells:
        cell_char[s] = "S"
    lines = []
    lines.append("    ." + "----" * 16)
    for row in range(8):
        cells = []
        for col in range(16):
            rn = row * 16 + col
            if rn in cell_char:
                cells.append(cell_char[rn])
            else:
                cells.append(".")
        lines.append("    | " + " ".join(cells) + " |")
    lines.append("    " + "'" + "----" * 16)
    return "\n".join(lines)


def level_tallies(lvl: Level) -> dict[str, int]:
    rooms = {r.room_num: r for r in lvl.rooms}
    door_keys = door_bombs = 0
    seen_pairs: set[tuple[int, int]] = set()
    for rn, room in rooms.items():
        for side in Side:
            nb = neighbour(rn, side)
            if nb is None or nb not in rooms:
                continue
            pair = (min(rn, nb), max(rn, nb))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            wa = room.walls[side]
            wb = rooms[nb].walls[side.opposite]
            if WallType.LOCKED_DOOR_1 in (wa, wb) or WallType.LOCKED_DOOR_2 in (wa, wb):
                door_keys += 1
            if WallType.BOMB_HOLE in (wa, wb):
                door_bombs += 1
    keys = sum(1 for r in lvl.rooms if r.item == Item.KEY)
    bombs = sum(1 for r in lvl.rooms if r.item == Item.BOMBS)
    hcs = sum(1 for r in lvl.rooms if r.item == Item.HEART_CONTAINER)
    return {"key_doors": door_keys, "keys": keys, "bomb_walls": door_bombs,
            "bomb_items": bombs, "heart_containers": hcs}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    ap.add_argument("--flags", default=MVP_BASELINE_LEVEL_ENCODING_OFF,
                    help="flag string (default: the MVP baseline, level encoding off)")
    ap.add_argument("--outdir", type=Path, default=REPO / "temp" / "playtest")
    ap.add_argument("--report", type=Path, default=REPO / "temp" / "playtest_report.md")
    ap.add_argument("--setting", action="append", default=[], metavar="NAME=VALUE",
                    help="a player setting (zora/rom/player_settings.py), e.g. music=off or "
                         "heart_colour=0x21; repeat for more; the defaults otherwise")
    args = ap.parse_args()
    try:
        settings = parse_player_settings(args.setting)
    except PlayerSettingError as exc:
        print(exc, file=sys.stderr)
        return 1

    vanilla_path = BASE_ROM_PATH
    if not vanilla_path.exists():
        print("vanilla ROM not found", file=sys.stderr)
        return 1
    verify_base_rom(vanilla_path)
    rom = load_rom(vanilla_path)
    outdir = args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    report: list[str] = []
    for seed in args.seeds:
        try:
            chosen = plan(args.flags, seed)
        except (FlagsRefused, level_encoding.LevelEncodingUnavailable) as exc:
            print(exc, file=sys.stderr)
            return 1
        gw, result = generate_world(chosen, rom)
        # The checks read plain level data: with level encoding on they run on
        # the seed's plain twin (the same world, encoding off).
        plain_config = replace(chosen.config, level_encoding=None)
        plain = serialize_to_rom(gw, rom, config=plain_config)
        out = serialize_to_rom(gw, rom, config=chosen.config, player_settings=settings)
        # round-trip verification on the plain output
        gw2 = parse_rom(plain)
        rt_ok = serialize_to_rom(gw2, plain, config=plain_config) == plain
        decode_ok = True
        if chosen.config.level_encoding is not None:
            decode_ok = (level_encoding.decode_level_data(out, chosen.config.level_encoding)
                         == level_encoding.plain_level_data(plain))
        checks = run_checks(gw2)
        failed = [c for c in checks if not c.passed]
        suffix = "-encoded" if chosen.encode_level_data else ""
        res_name = f"zora-playtest-seed{seed}{suffix}.nes"
        (outdir / res_name).write_bytes(out)
        owners: dict[int, int] = {}
        lines = [f"### seed {seed} — {res_name}",
                 f"- flags: {chosen.flag_string}",
                 f"- level encoding: {'on (decodes to the plain twin: ' + str(decode_ok) + ')' if chosen.encode_level_data else 'off'}",
                 f"- attempts: {result.attempts}",
                 f"- round-trip parse→serialize: {'byte-identical' if rt_ok else 'MISMATCH'}",
                 f"- spec checks: {len(checks) - len(failed)}/{len(checks)} pass"
                 + (f" (failed: {[f.check_id for f in failed]})" if failed else ""),
                 f"- map: E=entrance T=triforce P=person g=grumble Z=zelda G=ganon "
                 f"s=staircase house room S=stairway cell #=room .=nothing"]
        for lvl in gw2.levels:
            t = level_tallies(lvl)
            warn = ""
            if t["keys"] < t["key_doors"]:
                warn = "  <-- keys < key doors: possible shortfall"
            cellars = [(hex(s.room_num), s.return_dest, s.item)
                       for s in lvl.staircase_rooms
                       if s.room_type == RoomType.ITEM_STAIRCASE]
            trans = [(s.left_exit, s.right_exit)
                     for s in lvl.staircase_rooms
                     if s.room_type == RoomType.TRANSPORT_STAIRCASE]
            lines.append(f"- L{lvl.level_num}: entrance {lvl.entrance_room:#04x}, "
                         f"{len(lvl.rooms)} rooms, boss cell {lvl.boss_room:#04x}, "
                         f"cellars {[(c, d) for c, d, _ in cellars]}, "
                         f"transports {[(a, b) for a, b in trans]}")
            lines.append(f"  key doors {t['key_doors']} / keys {t['keys']} | "
                         f"bomb walls {t['bomb_walls']} / bomb items {t['bomb_items']} | "
                         f"heart containers {t['heart_containers']}{warn}")
            lines.append(level_map_text(gw2, lvl, owners))
        report.append("\n".join(lines))
        print(f"seed {seed}: flags {chosen.flag_string} rt_ok={rt_ok} decode_ok={decode_ok} "
              f"checks={len(checks) - len(failed)}/{len(checks)} -> {outdir / res_name}")
        if not rt_ok or not decode_ok or failed:
            return 2

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        "# ZORA playtest ROMs — generation report\n\n" + "\n\n".join(report) + "\n")
    print(f"wrote {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
