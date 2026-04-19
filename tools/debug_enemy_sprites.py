"""Debug tool: generate a full seed and report enemy and boss sprite state per room.

Runs the exact same generation pipeline (same seed + flag string) that a
player would get, then dumps every dungeon room showing:
  - what enemy/boss is placed there
  - what enemy sprite set (A/B/C) and boss sprite set (A/B/C) the NES
    will load for that level
  - what tile frame column codes the engine will use for that enemy/boss
  - whether those tile columns contain actual sprite data in the loaded bank

This is a diagnostic tool — it makes no assumptions about whether the
randomizer logic is correct.  It reports raw facts so you can compare
them against what you see on screen.

Usage:
    python3 tools/debug_enemy_sprites.py --seed 12345 --flags "AbCdE..."
    python3 tools/debug_enemy_sprites.py --seed 12345 --flags "AbCdE..." --level 3
    python3 tools/debug_enemy_sprites.py --seed 12345 --flags "AbCdE..." --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "flags"))

from flags.flags_generated import (
    Flags,
    decode_flags,
)
from zora.api.validation import parse_flag_string
from zora.data_model import (
    BossSpriteSet,
    Enemy,
    EnemySpriteSet,
    GameWorld,
    SpriteData,
)
from zora.game_config import resolve_game_config
from zora.generate_game import _RANDOMIZERS
from zora.parser import load_bin_files, parse_game_world
from zora.rng import SeededRng

ROM_DATA = _ROOT / "rom_data"

_COL_START = 158
_COL_END = 191  # inclusive: 34 columns (158-191) = 544 bytes = 0x220

# The OW bank is 0x640 bytes with a non-contiguous column layout:
#   [0x000-0x01F]: 0x20-byte prefix (2 columns of "additional" header data)
#   [0x020-0x41F]: 0x400 bytes = cols 192-255 (OW-specific: Octoroks, Leevers, etc.)
#   [0x420-0x63F]: 0x220 bytes = cols 158-191 (standard enemy columns, same as dungeons)
# The sprite set pointer for OW ($965B → file 0xD66B) points to offset 0x420,
# where the engine loads 34 columns (158-191) just like dungeon sets.
_OW_COL_END = 255
_OW_ENEMY_REGION_OFFSET = 0x420
_OW_ADDITIONAL_OFFSET = 0x20
_OW_ADDITIONAL_COL_START = 192

_SPRITE_SET_ATTR: dict[EnemySpriteSet, str] = {
    EnemySpriteSet.A: "enemy_set_a",
    EnemySpriteSet.B: "enemy_set_b",
    EnemySpriteSet.C: "enemy_set_c",
    EnemySpriteSet.OW: "ow_sprites",
}


def _get_bank_bytes(sprites: SpriteData, sprite_set: EnemySpriteSet) -> bytearray:
    result: bytearray = getattr(sprites, _SPRITE_SET_ATTR[sprite_set])
    return result


def _ow_column_offset(col: int) -> int | None:
    """Return byte offset within the OW bank for a given column, or None if out of range."""
    if 192 <= col <= 255:
        return _OW_ADDITIONAL_OFFSET + (col - 192) * 16
    if 158 <= col <= 191:
        return _OW_ENEMY_REGION_OFFSET + (col - 158) * 16
    return None


def _column_has_data(
    bank: bytearray, col: int, col_start: int, is_ow: bool = False,
) -> bool:
    """Check if an engine tile column has any non-zero bytes in the bank."""
    if is_ow:
        off = _ow_column_offset(col)
        if off is None or off + 16 > len(bank):
            return False
        return any(b != 0 for b in bank[off:off + 16])
    offset = (col - col_start) * 16
    if offset < 0 or offset + 16 > len(bank):
        return False
    return any(b != 0 for b in bank[offset:offset + 16])


def _column_byte_range(col: int) -> str:
    offset = (col - _COL_START) * 16
    return f"0x{offset:03X}-0x{offset + 15:03X}"


def _col_in_enemy_bank(col: int, is_ow: bool = False) -> bool:
    """Check if a tile column falls within the swappable enemy sprite bank range."""
    end = _OW_COL_END if is_ow else _COL_END
    return _COL_START <= col <= end


# ---------------------------------------------------------------------------
# Boss sprite bank constants
# ---------------------------------------------------------------------------

_BOSS_COL_START = 192
_BOSS_COL_END = 255  # inclusive: 64 columns (192-255) = 1024 bytes = 0x400
_BOSS_EXP_COL_START = 48
_BOSS_EXP_COL_END = 79  # inclusive: 32 columns (48-79) = 512 bytes = 0x200

_BOSS_SPRITE_SET_ATTR: dict[BossSpriteSet, str] = {
    BossSpriteSet.A: "boss_set_a",
    BossSpriteSet.B: "boss_set_b",
    BossSpriteSet.C: "boss_set_c",
}


def _get_boss_bank_bytes(sprites: SpriteData, boss_set: BossSpriteSet) -> bytearray:
    result: bytearray = getattr(sprites, _BOSS_SPRITE_SET_ATTR[boss_set])
    return result


def _col_in_boss_bank(col: int) -> bool:
    """Check if a tile column falls within a boss sprite bank range."""
    return (_BOSS_COL_START <= col <= _BOSS_COL_END
            or _BOSS_EXP_COL_START <= col <= _BOSS_EXP_COL_END)


def _tile_frame_detail(
    game_world: GameWorld,
    enemy: Enemy,
    bank: bytearray,
    is_ow: bool = False,
) -> dict[str, Any]:
    """Get tile frame info for an enemy, checked against actual bank data.

    For dungeon banks, only columns 158-191 are checked.
    For the OW bank, columns 158-255 are checked (the full OW sprite region).
    Other columns come from fixed banks and aren't affected by sprite set swapping.
    """
    frames = game_world.enemies.tile_frames.get(enemy)
    if frames is None:
        return {"frames": None, "enemy_bank_cols": [], "empty_count": 0}

    col_details: list[dict[str, Any]] = []
    for col in frames:
        in_enemy_bank = _col_in_enemy_bank(col, is_ow)
        has_data: bool | None = None
        if in_enemy_bank:
            has_data = _column_has_data(bank, col, _COL_START, is_ow=is_ow)
        col_details.append({
            "col": col,
            "in_enemy_bank": in_enemy_bank,
            "has_data": has_data,
        })

    enemy_bank_cols = [c for c in col_details if c["in_enemy_bank"]]
    empty_cols = [c for c in enemy_bank_cols if not c["has_data"]]
    return {
        "frames": [c["col"] for c in col_details],
        "columns": col_details,
        "enemy_bank_cols": [c["col"] for c in enemy_bank_cols],
        "empty_count": len(empty_cols),
    }


def _boss_tile_frame_detail(
    game_world: GameWorld,
    enemy: Enemy,
    boss_bank: bytearray,
    expansion_bank: bytearray,
) -> dict[str, Any]:
    """Get tile frame info for a boss, checked against boss sprite bank data.

    Columns in the main boss range (192-255) are checked against the
    level's boss bank.  Columns in the expansion range (48-79) are
    checked against the shared boss_set_expansion bank.  Other columns
    come from fixed banks and aren't affected by boss sprite set swapping.
    """
    frames = game_world.enemies.tile_frames.get(enemy)
    if frames is None:
        return {"frames": None, "boss_bank_cols": [], "empty_count": 0}

    col_details: list[dict[str, Any]] = []
    for col in frames:
        in_main = _BOSS_COL_START <= col <= _BOSS_COL_END
        in_exp = _BOSS_EXP_COL_START <= col <= _BOSS_EXP_COL_END
        in_boss_bank = in_main or in_exp
        has_data: bool | None = None
        if in_main:
            has_data = _column_has_data(boss_bank, col, _BOSS_COL_START)
        elif in_exp:
            has_data = _column_has_data(expansion_bank, col, _BOSS_EXP_COL_START)
        col_details.append({
            "col": col,
            "in_boss_bank": in_boss_bank,
            "has_data": has_data,
        })

    boss_bank_cols = [c for c in col_details if c["in_boss_bank"]]
    empty_cols = [c for c in boss_bank_cols if not c["has_data"]]
    return {
        "frames": [c["col"] for c in col_details],
        "columns": col_details,
        "boss_bank_cols": [c["col"] for c in boss_bank_cols],
        "empty_count": len(empty_cols),
    }


def _uses_enemy_bank(game_world: GameWorld, enemy: Enemy, is_ow: bool = False) -> bool:
    """Check if an enemy has any tile frames in the enemy sprite bank range."""
    frames = game_world.enemies.tile_frames.get(enemy)
    if frames is None:
        return False
    return any(_col_in_enemy_bank(col, is_ow) for col in frames)


def _enemy_in_cave_group(
    game_world: GameWorld,
    enemy: Enemy,
    sprite_set: EnemySpriteSet,
) -> bool | None:
    """Check if enemy is in the cave_groups list for this sprite set.

    Returns None if cave_groups wasn't populated (enemy groups not shuffled).
    """
    if not game_world.enemies.cave_groups:
        return None
    members = game_world.enemies.cave_groups.get(sprite_set, [])
    return enemy in members


def _uses_boss_bank(game_world: GameWorld, enemy: Enemy) -> bool:
    """Check if an enemy has any tile frames in a boss sprite bank range."""
    frames = game_world.enemies.tile_frames.get(enemy)
    if frames is None:
        return False
    return any(_col_in_boss_bank(col) for col in frames)


def _build_boss_column_occupant_map(
    game_world: GameWorld,
    boss_set: BossSpriteSet,
    boss_bank: bytearray,
    expansion_bank: bytearray,
) -> dict[int, list[str]]:
    """Build a map of which bosses have tile data at each column in a boss set.

    Scans all boss enemies for tile frames in the boss bank range and checks
    whether the column actually contains non-zero data.
    """
    col_map: dict[int, list[str]] = {}
    for enemy in Enemy:
        if not enemy.is_boss:
            continue
        frames = game_world.enemies.tile_frames.get(enemy)
        if frames is None:
            continue
        for col in frames:
            in_main = _BOSS_COL_START <= col <= _BOSS_COL_END
            in_exp = _BOSS_EXP_COL_START <= col <= _BOSS_EXP_COL_END
            if in_main and _column_has_data(boss_bank, col, _BOSS_COL_START):
                col_map.setdefault(col, []).append(enemy.name)
            elif in_exp and _column_has_data(expansion_bank, col, _BOSS_EXP_COL_START):
                col_map.setdefault(col, []).append(enemy.name)
    return col_map


def _build_column_occupant_map(
    game_world: GameWorld,
    sprite_set: EnemySpriteSet,
) -> dict[int, list[str]]:
    """Build a map of which enemies claim each tile column in a sprite set.

    Uses cave_groups if available. Returns {col: [enemy_name, ...]}.
    """
    col_map: dict[int, list[str]] = {}
    if not game_world.enemies.cave_groups:
        return col_map
    is_ow = sprite_set == EnemySpriteSet.OW
    members = game_world.enemies.cave_groups.get(sprite_set, [])
    for enemy in members:
        frames = game_world.enemies.tile_frames.get(enemy)
        if frames is None:
            continue
        for col in frames:
            if _col_in_enemy_bank(col, is_ow):
                col_map.setdefault(col, []).append(enemy.name)
    return col_map


def generate_and_inspect(
    seed: int,
    flag_string: str,
    level_filter: int | None = None,
    screen_filter: int | None = None,
) -> tuple[GameWorld, list[dict[str, Any]]]:
    """Run full generation pipeline and collect per-room enemy/sprite info."""
    normalized, errors = parse_flag_string(flag_string)
    if errors:
        raise ValueError(f"Invalid flag string: {errors[0]}")

    flags: Flags = decode_flags(normalized)
    rng = SeededRng(seed)
    config = resolve_game_config(flags, rng)

    bins = load_bin_files(ROM_DATA)

    max_attempts = 10
    game_world: GameWorld | None = None
    for attempt in range(max_attempts):
        game_world = parse_game_world(bins)
        try:
            for step in _RANDOMIZERS:
                step(game_world, config, rng)
            break
        except RuntimeError:
            if attempt == max_attempts - 1:
                raise
    assert game_world is not None

    report: list[dict[str, Any]] = []

    # --- Dungeon levels ---
    show_dungeons = screen_filter is None
    if show_dungeons:
        for level in game_world.levels:
            if level_filter is not None and level.level_num != level_filter:
                continue

            sprite_set = level.enemy_sprite_set
            bank = _get_bank_bytes(game_world.sprites, sprite_set)

            boss_set = level.boss_sprite_set
            boss_bank = _get_boss_bank_bytes(game_world.sprites, boss_set)
            expansion_bank = game_world.sprites.boss_set_expansion

            level_info: dict[str, Any] = {
                "level": level.level_num,
                "kind": "dungeon",
                "enemy_sprite_set": sprite_set.name,
                "boss_sprite_set": boss_set.name,
                "bank_size": f"0x{len(bank):X} ({len(bank)} bytes)",
                "boss_bank_size": f"0x{len(boss_bank):X} ({len(boss_bank)} bytes)",
                "rooms": [],
            }

            col_occupants = _build_column_occupant_map(game_world, sprite_set)
            level_info["column_occupants"] = col_occupants

            boss_col_occupants = _build_boss_column_occupant_map(
                game_world, boss_set, boss_bank, expansion_bank,
            )
            level_info["boss_column_occupants"] = boss_col_occupants

            for room in level.rooms:
                enemy = room.enemy_spec.enemy
                frame_detail = _tile_frame_detail(game_world, enemy, bank)
                uses_bank = _uses_enemy_bank(game_world, enemy)
                in_group = _enemy_in_cave_group(game_world, enemy, sprite_set)

                uses_boss = _uses_boss_bank(game_world, enemy)
                boss_frames = _boss_tile_frame_detail(
                    game_world, enemy, boss_bank, expansion_bank,
                )

                room_info: dict[str, Any] = {
                    "room_num": f"0x{room.room_num:02X}",
                    "enemy": enemy.name,
                    "enemy_id": f"0x{enemy.value:02X}",
                    "quantity": room.enemy_quantity,
                    "room_type": room.room_type.name,
                    "is_group": room.enemy_spec.is_group,
                    "uses_enemy_bank": uses_bank,
                    "in_cave_group": in_group,
                    "tile_frames": frame_detail,
                    "uses_boss_bank": uses_boss,
                    "boss_tile_frames": boss_frames,
                }

                if room.enemy_spec.is_group and room.enemy_spec.group_members:
                    members_info: list[dict[str, Any]] = []
                    for m in room.enemy_spec.group_members:
                        m_frames = _tile_frame_detail(game_world, m, bank)
                        m_uses_bank = _uses_enemy_bank(game_world, m)
                        m_in_group = _enemy_in_cave_group(game_world, m, sprite_set)
                        members_info.append({
                            "enemy": m.name,
                            "enemy_id": f"0x{m.value:02X}",
                            "uses_enemy_bank": m_uses_bank,
                            "in_cave_group": m_in_group,
                            "tile_frames": m_frames,
                        })
                    room_info["group_members"] = members_info

                level_info["rooms"].append(room_info)

            report.append(level_info)

    # --- Overworld screens ---
    show_overworld = level_filter is None
    if show_overworld:
        ow = game_world.overworld
        sprite_set = EnemySpriteSet.OW
        bank = _get_bank_bytes(game_world.sprites, sprite_set)

        ow_info: dict[str, Any] = {
            "level": "OW",
            "kind": "overworld",
            "enemy_sprite_set": sprite_set.name,
            "bank_size": f"0x{len(bank):X} ({len(bank)} bytes)",
            "rooms": [],
        }

        col_occupants = _build_column_occupant_map(game_world, sprite_set)
        ow_info["column_occupants"] = col_occupants

        for screen in ow.screens:
            if screen_filter is not None and screen.screen_num != screen_filter:
                continue

            enemy = screen.enemy_spec.enemy
            frame_detail = _tile_frame_detail(game_world, enemy, bank, is_ow=True)
            uses_bank = _uses_enemy_bank(game_world, enemy, is_ow=True)
            in_group = _enemy_in_cave_group(game_world, enemy, sprite_set)

            screen_info: dict[str, Any] = {
                "room_num": f"0x{screen.screen_num:02X}",
                "enemy": enemy.name,
                "enemy_id": f"0x{enemy.value:02X}",
                "quantity": screen.enemy_quantity,
                "is_group": screen.enemy_spec.is_group,
                "uses_enemy_bank": uses_bank,
                "in_cave_group": in_group,
                "tile_frames": frame_detail,
            }

            if screen.enemy_spec.is_group and screen.enemy_spec.group_members:
                members_info = []
                for m in screen.enemy_spec.group_members:
                    m_frames = _tile_frame_detail(game_world, m, bank, is_ow=True)
                    m_uses_bank = _uses_enemy_bank(game_world, m, is_ow=True)
                    m_in_group = _enemy_in_cave_group(game_world, m, sprite_set)
                    members_info.append({
                        "enemy": m.name,
                        "enemy_id": f"0x{m.value:02X}",
                        "uses_enemy_bank": m_uses_bank,
                        "in_cave_group": m_in_group,
                        "tile_frames": m_frames,
                    })
                screen_info["group_members"] = members_info

            ow_info["rooms"].append(screen_info)

        report.append(ow_info)

    return game_world, report


def format_text_report(
    seed: int,
    flag_string: str,
    report: list[dict[str, Any]],
    game_world: GameWorld,
) -> str:
    """Format the inspection report as human-readable text."""
    lines: list[str] = []
    lines.append("Enemy & Boss Sprite Debug Report")
    lines.append(f"Seed: {seed}")
    lines.append(f"Flags: {flag_string}")
    lines.append("")

    lines.append("=== Sprite Set Assignments ===")
    for level in game_world.levels:
        lines.append(
            f"  Level {level.level_num}: "
            f"enemy bank {level.enemy_sprite_set.name}, "
            f"boss bank {level.boss_sprite_set.name}"
        )
    lines.append("")

    if game_world.enemies.cave_groups:
        lines.append("=== Enemy Sprite Bank Contents (from cave_groups) ===")
        for ss in [EnemySpriteSet.A, EnemySpriteSet.B, EnemySpriteSet.C, EnemySpriteSet.OW]:
            members = game_world.enemies.cave_groups.get(ss, [])
            if members:
                names = sorted(e.name for e in members)
                lines.append(f"  {ss.name}: {', '.join(names)}")
        lines.append("")

    # Scan for empty-column issues in enemy banks
    enemy_empty_warnings: list[str] = []
    for lv in report:
        for rm in lv["rooms"]:
            tf = rm["tile_frames"]
            if tf["empty_count"] > 0:
                empty_cols = [
                    c["col"] for c in tf["columns"]
                    if c["in_enemy_bank"] and not c["has_data"]
                ]
                enemy_empty_warnings.append(
                    f"  Level {lv['level']} room {rm['room_num']}: "
                    f"{rm['enemy']} references enemy bank columns {empty_cols} "
                    f"which are empty in bank {lv['enemy_sprite_set']}"
                )
            if "group_members" in rm:
                for mi, ms in enumerate(rm["group_members"]):
                    mtf = ms["tile_frames"]
                    if mtf["empty_count"] > 0:
                        empty_cols = [
                            c["col"] for c in mtf["columns"]
                            if c["in_enemy_bank"] and not c["has_data"]
                        ]
                        enemy_empty_warnings.append(
                            f"  Level {lv['level']} room {rm['room_num']}: "
                            f"group member #{mi} {ms['enemy']} references enemy bank columns {empty_cols} "
                            f"which are empty in bank {lv['enemy_sprite_set']}"
                        )

    if enemy_empty_warnings:
        lines.append(f"=== {len(enemy_empty_warnings)} EMPTY ENEMY TILE COLUMN WARNING(S) ===")
        for w in enemy_empty_warnings:
            lines.append(w)
        lines.append("")
    else:
        lines.append("=== All referenced enemy tile columns contain data ===")
        lines.append("")

    # Scan for empty-column issues in boss banks (dungeons only)
    boss_empty_warnings: list[str] = []
    for lv in report:
        if lv.get("kind") != "dungeon":
            continue
        for rm in lv["rooms"]:
            btf = rm.get("boss_tile_frames")
            if btf and btf["empty_count"] > 0:
                empty_cols = [
                    c["col"] for c in btf["columns"]
                    if c["in_boss_bank"] and not c["has_data"]
                ]
                boss_empty_warnings.append(
                    f"  Level {lv['level']} room {rm['room_num']}: "
                    f"{rm['enemy']} references boss bank columns {empty_cols} "
                    f"which are empty in boss bank {lv['boss_sprite_set']}"
                )

    if boss_empty_warnings:
        lines.append(f"=== {len(boss_empty_warnings)} EMPTY BOSS TILE COLUMN WARNING(S) ===")
        for w in boss_empty_warnings:
            lines.append(w)
        lines.append("")
    else:
        lines.append("=== All referenced boss tile columns contain data ===")
        lines.append("")

    for lv in report:
        is_ow = lv.get("kind") == "overworld"

        if is_ow:
            lines.append(f"=== Overworld (enemy bank {lv['enemy_sprite_set']}) ===")
        else:
            lines.append(
                f"=== Level {lv['level']} "
                f"(enemy bank {lv['enemy_sprite_set']}, "
                f"boss bank {lv['boss_sprite_set']}) ==="
            )

        col_occ = lv.get("column_occupants", {})
        if col_occ:
            lines.append(f"  Enemy column occupants in bank {lv['enemy_sprite_set']}:")
            for col in sorted(col_occ.keys()):
                lines.append(f"    col {col}: {', '.join(col_occ[col])}")

        if not is_ow:
            boss_col_occ = lv.get("boss_column_occupants", {})
            if boss_col_occ:
                lines.append(f"  Boss column occupants in boss bank {lv['boss_sprite_set']}:")
                for col in sorted(boss_col_occ.keys()):
                    lines.append(f"    col {col}: {', '.join(boss_col_occ[col])}")
        lines.append("")

        label = "Screen" if is_ow else "Room"
        for rm in lv["rooms"]:
            tf = rm["tile_frames"]
            frames_str = str(tf["frames"]) if tf["frames"] is not None else "n/a"

            flags: list[str] = []
            if tf["empty_count"] > 0:
                flags.append(f"EMPTY x{tf['empty_count']}")
            if rm["uses_enemy_bank"] and rm["in_cave_group"] is False:
                flags.append("NOT IN CAVE GROUP")

            btf = rm.get("boss_tile_frames")
            if btf and btf["empty_count"] > 0:
                flags.append(f"BOSS EMPTY x{btf['empty_count']}")
            flag_str = f"  ** {', '.join(flags)}" if flags else ""

            boss_info = ""
            if rm.get("uses_boss_bank") and btf:
                boss_cols = btf.get("boss_bank_cols", [])
                boss_info = f"  boss_cols={boss_cols}"

            if is_ow:
                lines.append(
                    f"    {label} {rm['room_num']}  {rm['enemy']:20s}  "
                    f"qty={rm['quantity']}  "
                    f"frames={frames_str}{flag_str}"
                )
            else:
                lines.append(
                    f"    {label} {rm['room_num']}  {rm['enemy']:20s}  "
                    f"qty={rm['quantity']}  type={rm['room_type']:20s}  "
                    f"frames={frames_str}{boss_info}{flag_str}"
                )
            if "group_members" in rm:
                for mi, ms in enumerate(rm["group_members"]):
                    mtf = ms["tile_frames"]
                    mframes_str = str(mtf["frames"]) if mtf["frames"] is not None else "n/a"
                    mflags: list[str] = []
                    if mtf["empty_count"] > 0:
                        mflags.append(f"EMPTY x{mtf['empty_count']}")
                    if ms["uses_enemy_bank"] and ms["in_cave_group"] is False:
                        mflags.append("NOT IN CAVE GROUP")
                    mflag_str = f"  ** {', '.join(mflags)}" if mflags else ""
                    lines.append(
                        f"        member #{mi}: {ms['enemy']:20s}  "
                        f"frames={mframes_str}{mflag_str}"
                    )
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a seed and report enemy/boss sprite data per room"
    )
    parser.add_argument("--seed", type=int, required=True, help="Generation seed")
    parser.add_argument("--flags", type=str, required=True, help="Flag string")
    parser.add_argument("--level", type=int, default=None,
                        help="Only show a specific dungeon level (1-9)")
    parser.add_argument("--screen", type=str, default=None,
                        help="Only show a specific overworld screen (decimal or 0xHH)")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON instead of text")
    args = parser.parse_args()

    screen_filter: int | None = None
    if args.screen is not None:
        screen_filter = int(args.screen, 0)

    game_world, report = generate_and_inspect(
        args.seed, args.flags, args.level, screen_filter,
    )

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        text = format_text_report(args.seed, args.flags, report, game_world)
        print(text)


if __name__ == "__main__":
    main()
