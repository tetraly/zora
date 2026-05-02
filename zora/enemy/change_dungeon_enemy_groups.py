"""Redistribute enemies across enemy sprite-set groups, then update rooms.

Reassigns which enemies belong to which sprite-set group (A/B/C, and
optionally OW), repacks sprite tile data, updates tile frame mappings,
expands companion variants, and replaces enemies in dungeon (and optionally
overworld) rooms.

Ported from changeDungeonEnemyGroups (change_dungeon_enemy_groups.cs).

==============================================================================
DEBUG INSTRUMENTATION
==============================================================================
This version is heavily instrumented.  Set the environment variable
ZORA_ENEMY_DEBUG=1 (or pass debug=True to change_dungeon_enemy_groups) to
emit a full forensic trace to stderr and to a log file.  The log captures:

  * Input state: overworld flag, force_wizzrobes_to_9 flag, sorted enemy
    list, start enemy pick, Vire HP check.
  * Per-enemy cached tile data: first 16 bytes of each enemy's vanilla
    sprite data, plus a flag for OW-origin enemies (Lynel/Moblin/Tektite)
    whose offset math is a suspected source of bugs.
  * Per-enemy vanilla column ranges: so you can cross-reference against
    an emulator CHR dump or ROM inspection.
  * Group assignment: every accept/reject, every retry, every constraint
    failure (mutual exclusion, OW forbidden, capacity, wizzrobe coverage).
  * Final group contents + capacity usage per group.
  * Repacking trace: which slot each enemy got, with slot_used[] state
    changes, Wallmaster / Lanmola / start-enemy special handling called
    out explicitly.
  * Per-group per-column hex signatures after packing, so you can
    cross-reference against an emulator CHR dump.
  * tile_frames before/after remap for every enemy, with per-frame trace
    and warnings for frames that can't be resolved.
  * Companion variant duplication trace.
  * Dungeon-room replacement trace: old → new, retries, skips.
  * Overworld replacement trace: per-screen, whether replacement fired
    and why (in_pool / has_conflict / group-decompose), final enemy.
  * Mixed-group member substitution trace: which bytes of
    mixed_enemy_data got rewritten.
  * Sanity assertions: flag anything suspicious (unmapped frames, OW
    enemy offset mismatch vs vanilla sprite set, start enemy picked
    from OW origin, cross-set room decomposition).

Grep the log for ``WARN`` or ``ASSERT`` to find suspicious events.
Grep for ``OW-ORIGIN`` to zero in on Lynel/Moblin/Tektite behavior.
==============================================================================
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from typing import Iterator

from zora.data_model import (
    SCREEN_ENTRANCE_TYPES,
    Enemy,
    EnemyData,
    EnemySpec,
    EnemySpriteSet,
    EntranceType,
    GameWorld,
    RoomType,
    SpriteData,
)
from zora.enemy.safety_checks import is_safe_for_room
from zora.rng import Rng

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_OUTER_RETRIES = 1000
_MAX_ASSIGNMENT_RETRIES = 1000
_MAX_ROOM_RETRIES = 1000


# ---------------------------------------------------------------------------
# Enemy definitions
# ---------------------------------------------------------------------------

_ENEMY_TILE_COLUMNS: dict[Enemy, int] = {
    Enemy.ZOL:            4,
    Enemy.RED_GORIYA:    16,
    Enemy.RED_DARKNUT:   20,
    Enemy.VIRE:           8,
    Enemy.POLS_VOICE:     4,
    Enemy.LIKE_LIKE:      6,
    Enemy.RED_WIZZROBE:  12,
    Enemy.WALLMASTER:     4,
    Enemy.ROPE:           8,
    Enemy.STALFOS:        4,
    Enemy.GIBDO:          4,
    Enemy.RED_LANMOLA:    4,
    Enemy.BLUE_LYNEL:    16,
    Enemy.BLUE_MOBLIN:   16,
    Enemy.BLUE_TEKTITE:   4,
}

_VANILLA_ENEMY_GROUPS: dict[EnemySpriteSet, frozenset[Enemy]] = {
    EnemySpriteSet.A: frozenset({
        Enemy.BLUE_GORIYA, Enemy.RED_GORIYA,
        Enemy.WALLMASTER, Enemy.ROPE, Enemy.STALFOS,
        Enemy.MOLDORM, Enemy.RUPEE_BOSS,
    }),
    EnemySpriteSet.B: frozenset({
        Enemy.RED_DARKNUT, Enemy.BLUE_DARKNUT,
        Enemy.POLS_VOICE, Enemy.GIBDO,
        Enemy.RUPEE_BOSS,
    }),
    EnemySpriteSet.C: frozenset({
        Enemy.VIRE, Enemy.LIKE_LIKE,
        Enemy.RED_WIZZROBE, Enemy.BLUE_WIZZROBE,
        Enemy.RED_LANMOLA, Enemy.BLUE_LANMOLA,
        Enemy.RUPEE_BOSS,
    }),
}
# Note: MOLDORM and RUPEE_BOSS are listed because their sprites empirically
# live in the noted enemy banks (see _BOSS_ENEMIES_IN_ENEMY_SPRITE_SETS in
# shuffle_monsters_between_levels.py — derived from a 50-seed reference
# corpus). Both are filtered out of the per-room replacement loop below by
# the `enemy.is_boss` check, so adding them here has no effect on packing
# logic; the membership is purely a sprite-bank ground-truth claim.

_COMPANION_EXPANSIONS: dict[Enemy, Enemy] = {
    Enemy.RED_GORIYA:    Enemy.BLUE_GORIYA,
    Enemy.RED_DARKNUT:   Enemy.BLUE_DARKNUT,
    Enemy.RED_WIZZROBE:  Enemy.BLUE_WIZZROBE,
    Enemy.RED_LANMOLA:   Enemy.BLUE_LANMOLA,
    Enemy.BLUE_LYNEL:    Enemy.RED_LYNEL,
    Enemy.BLUE_MOBLIN:   Enemy.RED_MOBLIN,
    Enemy.BLUE_TEKTITE:  Enemy.RED_TEKTITE,
    Enemy.BLUE_LEEVER:   Enemy.RED_LEEVER,
}

_FORBIDDEN_FROM_OVERWORLD: frozenset[Enemy] = frozenset({
    Enemy.RED_LANMOLA,
    Enemy.WALLMASTER,
    Enemy.VIRE,
    Enemy.ZOL,
    Enemy.LIKE_LIKE,
})

_SHUFFLEABLE_ENEMIES: frozenset[Enemy] = frozenset(
    set(_ENEMY_TILE_COLUMNS.keys()) | set(_COMPANION_EXPANSIONS.values())
)

_MIXED_GROUP_SPRITE_SET: dict[int, EnemySpriteSet] = {
    0x6D: EnemySpriteSet.B,
    0x6E: EnemySpriteSet.A,
    0x6F: EnemySpriteSet.B,
    0x70: EnemySpriteSet.B,
    0x71: EnemySpriteSet.C,
    0x72: EnemySpriteSet.C,
    0x73: EnemySpriteSet.C,
    0x74: EnemySpriteSet.B,
    0x75: EnemySpriteSet.A,
    0x76: EnemySpriteSet.C,
    0x77: EnemySpriteSet.C,
    0x78: EnemySpriteSet.B,
    0x79: EnemySpriteSet.A,
    0x7A: EnemySpriteSet.A,
    0x7B: EnemySpriteSet.C,
    0x7C: EnemySpriteSet.C,
}

_MUTUALLY_EXCLUSIVE: frozenset[tuple[Enemy, Enemy]] = frozenset({
    (Enemy.RED_LANMOLA, Enemy.WALLMASTER),
    (Enemy.WALLMASTER, Enemy.RED_LANMOLA),
})

_WIZZROBE_COMPAT_BASE: list[Enemy] = [
    Enemy.RED_GORIYA,
    Enemy.RED_DARKNUT,
    Enemy.GIBDO,
    Enemy.RED_WIZZROBE,
    Enemy.BLUE_LYNEL,
    Enemy.BLUE_MOBLIN,
    Enemy.RED_OCTOROK_1,
]


# ---------------------------------------------------------------------------
# Sprite tile layout
# ---------------------------------------------------------------------------

_VANILLA_SPRITE_SET: dict[Enemy, EnemySpriteSet] = {
    Enemy.ZOL:            EnemySpriteSet.B,
    Enemy.RED_GORIYA:     EnemySpriteSet.A,
    Enemy.ROPE:           EnemySpriteSet.A,
    Enemy.STALFOS:        EnemySpriteSet.A,
    Enemy.WALLMASTER:     EnemySpriteSet.A,
    Enemy.RED_DARKNUT:    EnemySpriteSet.B,
    Enemy.POLS_VOICE:     EnemySpriteSet.B,
    Enemy.GIBDO:          EnemySpriteSet.B,
    Enemy.VIRE:           EnemySpriteSet.C,
    Enemy.LIKE_LIKE:      EnemySpriteSet.C,
    Enemy.RED_WIZZROBE:   EnemySpriteSet.C,
    Enemy.RED_LANMOLA:    EnemySpriteSet.C,
    Enemy.BLUE_LYNEL:     EnemySpriteSet.OW,
    Enemy.BLUE_MOBLIN:    EnemySpriteSet.OW,
    Enemy.BLUE_TEKTITE:   EnemySpriteSet.OW,
}

_GROUP_SPRITE_ATTR: dict[EnemySpriteSet, str] = {
    EnemySpriteSet.A:  "enemy_set_a",
    EnemySpriteSet.B:  "enemy_set_b",
    EnemySpriteSet.C:  "enemy_set_c",
    EnemySpriteSet.OW: "ow_sprites",
}

_GROUP_ORDER: list[EnemySpriteSet] = [
    EnemySpriteSet.A, EnemySpriteSet.B, EnemySpriteSet.C, EnemySpriteSet.OW,
]

_GROUP_CAPACITY = 34
_COL_START = 158
_OW_BANK_PREFIX = 0x20

_SPRITE_BANK_BASES: dict[EnemySpriteSet, int] = {
    EnemySpriteSet.A: 0xDDCB,
    EnemySpriteSet.B: 0xD88B,
    EnemySpriteSet.C: 0xDAAB,
}

_STAT_OFFSETS: dict[Enemy, int] = {
    Enemy.ZOL:           39195,
    Enemy.RED_GORIYA:    40667,
    Enemy.RED_DARKNUT:   39259,
    Enemy.VIRE:          39803,
    Enemy.POLS_VOICE:    39067,
    Enemy.LIKE_LIKE:     39643,
    Enemy.RED_WIZZROBE:  39931,
    Enemy.WALLMASTER:    40603,
    Enemy.ROPE:          40411,
    Enemy.STALFOS:       40539,
    Enemy.GIBDO:         39131,
    Enemy.RED_LANMOLA:   39579,
}


def _compute_sprite_offset(enemy: Enemy) -> int:
    sprite_set = _VANILLA_SPRITE_SET[enemy]
    stat_offset = _STAT_OFFSETS[enemy]
    rom_addr = stat_offset + 16400
    bank_base = _SPRITE_BANK_BASES[sprite_set]
    return rom_addr - bank_base


def _compute_sprite_size(enemy: Enemy) -> int:
    return _ENEMY_TILE_COLUMNS[enemy] * 16


_SPRITE_OFFSET: dict[Enemy, int] = {
    e: _compute_sprite_offset(e) for e in _VANILLA_SPRITE_SET if e in _STAT_OFFSETS
}
_SPRITE_SIZE: dict[Enemy, int] = {
    e: _compute_sprite_size(e) for e in _VANILLA_SPRITE_SET
}

_OW_ENEMY_FIRST_COL: dict[Enemy, int] = {
    Enemy.BLUE_LYNEL:    206,
    Enemy.BLUE_MOBLIN:   240,
    Enemy.BLUE_TEKTITE:  202,
}
for _ow_e, _ow_col in _OW_ENEMY_FIRST_COL.items():
    _SPRITE_OFFSET[_ow_e] = _OW_BANK_PREFIX + (_ow_col - _COL_START) * 16

_VANILLA_COLUMNS: dict[Enemy, list[int]] = {}
for _e in _VANILLA_SPRITE_SET:
    if _e in _OW_ENEMY_FIRST_COL:
        _first = _OW_ENEMY_FIRST_COL[_e]
        _VANILLA_COLUMNS[_e] = list(range(_first, _first + _ENEMY_TILE_COLUMNS[_e]))
    else:
        _off = _SPRITE_OFFSET[_e]
        _VANILLA_COLUMNS[_e] = list(range(
            _COL_START + _off // 16,
            _COL_START + _off // 16 + _ENEMY_TILE_COLUMNS[_e],
        ))

_TILE_FRAME_COUNT: dict[Enemy, int] = {
    Enemy.ZOL:            2,
    Enemy.RED_GORIYA:     4,
    Enemy.RED_DARKNUT:    6,
    Enemy.VIRE:           4,
    Enemy.POLS_VOICE:     2,
    Enemy.LIKE_LIKE:      4,
    Enemy.RED_WIZZROBE:   4,
    Enemy.WALLMASTER:     2,
    Enemy.ROPE:           2,
    Enemy.STALFOS:        1,
    Enemy.GIBDO:          1,
    Enemy.RED_LANMOLA:    0,
    Enemy.BLUE_LYNEL:     4,
    Enemy.BLUE_MOBLIN:    4,
    Enemy.BLUE_TEKTITE:   2,
}

_WALLMASTER_SHARED_BLOCK_SIZE = 32
_WALLMASTER_EXTRA_SLOTS: list[int] = [636, 632, 688, 692, 696, 700]
_LANMOLA_RESERVED_SLOTS: list[int] = [161, 160, 159, 158]

_TILE_FRAME_COPIES: list[tuple[Enemy, Enemy]] = [
    (Enemy.RED_GORIYA, Enemy.BLUE_GORIYA),
    (Enemy.RED_DARKNUT, Enemy.BLUE_DARKNUT),
    (Enemy.RED_WIZZROBE, Enemy.BLUE_WIZZROBE),
    (Enemy.BLUE_LYNEL, Enemy.RED_LYNEL),
    (Enemy.BLUE_MOBLIN, Enemy.RED_MOBLIN),
    (Enemy.BLUE_TEKTITE, Enemy.RED_TEKTITE),
    # Leever copy is a no-op post-shuffle (not in _VANILLA_SPRITE_SET) but kept for parity with C# ROM copy.
    (Enemy.BLUE_LEEVER, Enemy.RED_LEEVER),
]

_BAD_FOR_WIZZROBE_SCREENS: frozenset[int] = frozenset({
    5, 6, 7, 8, 114, 2, 29, 30, 23, 26, 56, 68, 85, 63,
})

_OW_WRITABLE_COLUMNS: frozenset[int] = (
    frozenset(range(202, 222)) | frozenset(range(240, 256))
)


# ---------------------------------------------------------------------------
# DEBUG LOGGING INFRASTRUCTURE
# ---------------------------------------------------------------------------

class _DebugLog:
    """Collects forensic trace lines during a single run.

    Same design as the boss-groups _DebugLog: writes to stderr (optional)
    and to an in-memory buffer flushed to a file at the end.
    """

    def __init__(self, enabled: bool, log_path: str | None = None,
                 stream: object | None = None) -> None:
        self.enabled = enabled
        self.lines: list[str] = []
        self.log_path = log_path
        self.stream = stream if stream is not None else sys.stderr
        self._section_depth = 0
        self._warn_count = 0
        self._assert_count = 0

    def log(self, msg: str = "") -> None:
        if not self.enabled:
            return
        indent = "  " * self._section_depth
        line = f"{indent}{msg}"
        self.lines.append(line)
        try:
            print(line, file=self.stream)
        except Exception:
            pass

    def warn(self, msg: str) -> None:
        self._warn_count += 1
        self.log(f"WARN: {msg}")

    def assert_(self, cond: bool, msg: str) -> None:
        if not cond:
            self._assert_count += 1
            self.log(f"ASSERT FAILED: {msg}")

    @contextmanager
    def section(self, title: str) -> Iterator[None]:
        self.log(f"=== {title} ===")
        self._section_depth += 1
        try:
            yield
        finally:
            self._section_depth -= 1
            self.log("")

    def flush(self) -> None:
        if not self.enabled or not self.log_path:
            return
        try:
            with open(self.log_path, "w", encoding="utf-8") as f:
                f.write("\n".join(self.lines))
                f.write("\n")
                f.write(
                    f"\n--- Summary: {self._warn_count} warnings, "
                    f"{self._assert_count} assertion failures ---\n"
                )
        except Exception as e:
            print(f"[debug log] failed to write {self.log_path}: {e}",
                  file=sys.stderr)


def _column_hex_signature(buf: bytes, col_byte_offset: int) -> str:
    """Two-half hex fingerprint of a 16-byte NES tile column."""
    chunk = bytes(buf[col_byte_offset:col_byte_offset + 16])
    if len(chunk) < 16:
        chunk = chunk + b"\x00" * (16 - len(chunk))
    lo = chunk[:8].hex()
    hi = chunk[8:].hex()
    return f"{lo}|{hi}"


def _needs_bracelet(screen_num: int) -> bool:
    entrance = SCREEN_ENTRANCE_TYPES.get(screen_num)
    return entrance in (EntranceType.POWER_BRACELET, EntranceType.POWER_BRACELET_AND_BOMB)


def _screen_has_enemy(screen_enemy: Enemy, target: Enemy,
                      is_group: bool, group_members: list[Enemy] | None) -> bool:
    if not is_group:
        return screen_enemy == target
    if group_members is not None:
        return target in group_members
    return False


# ---------------------------------------------------------------------------
# Sprite packing
# ---------------------------------------------------------------------------

def _read_enemy_tiles(sprites: SpriteData, enemy: Enemy, dbg: _DebugLog | None = None) -> bytes:
    """Extract an enemy's sprite tile data from its vanilla sprite set."""
    sprite_set = _VANILLA_SPRITE_SET[enemy]
    source = getattr(sprites, _GROUP_SPRITE_ATTR[sprite_set])
    offset = _SPRITE_OFFSET[enemy]
    size = _SPRITE_SIZE[enemy]

    is_ow_origin = (sprite_set == EnemySpriteSet.OW)
    tag = " [OW-ORIGIN]" if is_ow_origin else ""

    data = bytes(source[offset:offset + size])

    if dbg is not None:
        dbg.log(
            f"  cached {enemy.name:<20s}{tag} "
            f"set={sprite_set.name:<2} "
            f"offset={offset:5d} "
            f"size={size:4d} "
            f"first16={data[:16].hex() if data else '<empty>'}"
        )

        if data and not any(data):
            dbg.warn(f"{enemy.name} tile cache is ALL ZERO — offset/set wrong?")
        if len(data) < size:
            dbg.warn(
                f"{enemy.name} tile cache is short "
                f"({len(data)} bytes, expected {size}) — "
                f"offset {offset} runs past end of {_GROUP_SPRITE_ATTR[sprite_set]} "
                f"(len={len(source)})"
            )

    # For OW-origin enemies, also log their vanilla column claim for
    # cross-reference against what the code believes their frames refer to.
    if is_ow_origin and dbg is not None:
        vcols = _VANILLA_COLUMNS.get(enemy, [])
        first_col = _OW_ENEMY_FIRST_COL.get(enemy)
        dbg.log(
            f"    OW-ORIGIN detail: _OW_ENEMY_FIRST_COL={first_col}, "
            f"vanilla_cols={vcols[:4]}..{vcols[-1] if vcols else '?'}"
        )

    return data


def _read_wallmaster_shared_block(sprites: SpriteData) -> bytes:
    return bytes(sprites.enemy_set_a[0:_WALLMASTER_SHARED_BLOCK_SIZE])


def _repack_enemy_sprites(
    sprites: SpriteData,
    group_enemies: dict[EnemySpriteSet, list[Enemy]],
    wallmaster_shared_block: bytes,
    start_enemy: Enemy,
    tile_cache: dict[Enemy, bytes],
    dbg: _DebugLog,
) -> dict[Enemy, list[int]]:
    """Rewrite enemy sprite sets to match the new group assignments."""
    column_assignments: dict[Enemy, list[int]] = {}

    with dbg.section("Repack enemy sprites"):
        for sprite_set in [EnemySpriteSet.A, EnemySpriteSet.B, EnemySpriteSet.C, EnemySpriteSet.OW]:
            if sprite_set not in group_enemies:
                continue

            enemies_in_group = group_enemies[sprite_set]
            target = getattr(sprites, _GROUP_SPRITE_ATTR[sprite_set])

            dbg.log(
                f"-- packing {sprite_set.name} "
                f"into {_GROUP_SPRITE_ATTR[sprite_set]} "
                f"(target_len={len(target)}, "
                f"enemies={[e.name for e in enemies_in_group]})"
            )

            slot_used = [False] * 768

            if sprite_set == EnemySpriteSet.OW:
                ow_region_bases = [206, 202, 240]
                ow_region_sizes = [16, 4, 16]
                for s in range(256):
                    slot_used[s] = True
                for base, size in zip(ow_region_bases, ow_region_sizes):
                    for s in range(base, base + size):
                        slot_used[s] = False
                open_cols = [s for s in range(_COL_START, 256) if not slot_used[s]]
                dbg.log(
                    f"   OW slot reservation: initially closed, opened regions "
                    f"{list(zip(ow_region_bases, ow_region_sizes))}, "
                    f"writable_slots={open_cols}"
                )

            if Enemy.WALLMASTER in enemies_in_group:
                for k in range(len(wallmaster_shared_block)):
                    target[k] = wallmaster_shared_block[k]
                dbg.log(
                    f"   WALLMASTER shared block: wrote {len(wallmaster_shared_block)} "
                    f"bytes at bank offset 0 (cols {_COL_START}-"
                    f"{_COL_START + len(wallmaster_shared_block)//16 - 1})"
                )

                wm_data = tile_cache[Enemy.WALLMASTER]
                wm_offset = 224
                for k in range(len(wm_data)):
                    target[wm_offset + k] = wm_data[k]

                wm_start_col = _COL_START + wm_offset // 16
                wm_cols = len(wm_data) // 16
                column_assignments[Enemy.WALLMASTER] = list(
                    range(wm_start_col, wm_start_col + wm_cols)
                )
                dbg.log(
                    f"   WALLMASTER own data: wrote {len(wm_data)} bytes at "
                    f"bank offset {wm_offset} (cols {wm_start_col}-"
                    f"{wm_start_col + wm_cols - 1})"
                )

                shared_cols = len(wallmaster_shared_block) // 16
                for s in range(shared_cols):
                    slot_used[_COL_START + s] = True
                for s in range(wm_start_col, wm_start_col + wm_cols):
                    slot_used[s] = True
                for s in _WALLMASTER_EXTRA_SLOTS:
                    slot_used[s] = True
                dbg.log(
                    f"   WALLMASTER reserved extra slots: {_WALLMASTER_EXTRA_SLOTS}"
                )

            if Enemy.RED_LANMOLA in enemies_in_group:
                lm_data = tile_cache[Enemy.RED_LANMOLA]
                for k in range(len(lm_data)):
                    target[k] = lm_data[k]

                for s in _LANMOLA_RESERVED_SLOTS:
                    slot_used[s] = True
                dbg.log(
                    f"   RED_LANMOLA: wrote {len(lm_data)} bytes at bank "
                    f"offset 0, reserved slots {_LANMOLA_RESERVED_SLOTS}"
                )
                # NOTE: Lanmola doesn't get entered in column_assignments
                # here — its columns are the reserved slots above.  If
                # tile_frames for Lanmola need remapping, this could be a
                # bug.  Flag it.
                if Enemy.RED_LANMOLA in _VANILLA_COLUMNS:
                    dbg.log(
                        f"   RED_LANMOLA vanilla cols were "
                        f"{_VANILLA_COLUMNS[Enemy.RED_LANMOLA]}, but no "
                        f"entry added to column_assignments (relies on "
                        f"_LANMOLA_RESERVED_SLOTS matching frame refs)"
                    )

            if start_enemy in enemies_in_group and start_enemy in tile_cache:
                se_cols = len(tile_cache[start_enemy]) // 16
                se_pos = 192 - se_cols
                for s in range(se_pos, se_pos + se_cols):
                    slot_used[s] = True
                dbg.log(
                    f"   start_enemy={start_enemy.name} reserved slots "
                    f"{se_pos}-{se_pos + se_cols - 1} for later packing by "
                    f"_repack_start_enemy"
                )

            for enemy in enemies_in_group:
                if enemy == Enemy.WALLMASTER:
                    continue
                if enemy == Enemy.RED_LANMOLA:
                    continue
                if enemy == start_enemy:
                    continue
                if enemy not in tile_cache:
                    dbg.log(
                        f"   {enemy.name}: no tile_cache entry (companion?) "
                        f"— skipped during packing"
                    )
                    continue

                data = tile_cache[enemy]
                cols_needed = len(data) // 16
                slot_base = _COL_START
                assigned_cols: list[int] = []

                origin = _VANILLA_SPRITE_SET.get(enemy)
                origin_tag = " [OW-ORIGIN]" if origin == EnemySpriteSet.OW else ""

                for col_idx in range(cols_needed):
                    while slot_base < 256 and slot_used[slot_base]:
                        slot_base += 1

                    if slot_base >= 256:
                        dbg.warn(
                            f"{enemy.name} ran out of slots in "
                            f"{sprite_set.name} after placing {col_idx}/"
                            f"{cols_needed} cols"
                        )
                        break

                    slot_used[slot_base] = True
                    assigned_cols.append(slot_base)

                    rom_offset = (slot_base - _COL_START) * 16
                    if sprite_set == EnemySpriteSet.OW:
                        rom_offset += _OW_BANK_PREFIX
                    src_offset = col_idx * 16
                    for t in range(16):
                        if src_offset + t < len(data):
                            target[rom_offset + t] = data[src_offset + t]

                    slot_base += 1

                if assigned_cols:
                    column_assignments[enemy] = assigned_cols
                    dbg.log(
                        f"   packed {enemy.name:<20s}{origin_tag} "
                        f"@ cols {assigned_cols} ({len(assigned_cols)} slots, "
                        f"contiguous={assigned_cols == list(range(assigned_cols[0], assigned_cols[-1]+1))})"
                    )

        # Per-group per-column hex signature dump.
        with dbg.section("Per-column hex signatures after packing"):
            for sprite_set in [EnemySpriteSet.A, EnemySpriteSet.B,
                               EnemySpriteSet.C, EnemySpriteSet.OW]:
                if sprite_set not in group_enemies:
                    continue
                attr = _GROUP_SPRITE_ATTR[sprite_set]
                buf = getattr(sprites, attr)
                dbg.log(f"  {attr} (len={len(buf)}):")
                # Only show columns that matter: start+len/16 from _COL_START
                max_cols = min(len(buf) // 16, 256 - _COL_START + 10)
                base_offset = 0
                if sprite_set == EnemySpriteSet.OW:
                    base_offset = _OW_BANK_PREFIX
                for i in range(max_cols):
                    byte_off = base_offset + i * 16
                    if byte_off + 16 > len(buf):
                        break
                    sig = _column_hex_signature(buf, byte_off)
                    col_num = _COL_START + i
                    dbg.log(f"    col {col_num:3d} (byte {byte_off:4d}): {sig}")

    return column_assignments


def _repack_start_enemy(
    sprites: SpriteData,
    start_enemy: Enemy,
    group_enemies: dict[EnemySpriteSet, list[Enemy]],
    tile_cache: dict[Enemy, bytes],
    dbg: _DebugLog,
) -> list[int]:
    """Pack the start enemy's sprite data into every group that contains it."""
    data = tile_cache[start_enemy]
    cols = len(data) // 16
    pos_base = 192 - cols

    with dbg.section(f"Repack start enemy ({start_enemy.name})"):
        dbg.log(
            f"  start_enemy={start_enemy.name}, data_len={len(data)}, "
            f"cols={cols}, pos_base={pos_base} (= col {pos_base})"
        )
        origin = _VANILLA_SPRITE_SET.get(start_enemy)
        if origin == EnemySpriteSet.OW:
            dbg.warn(
                f"start_enemy is OW-ORIGIN ({start_enemy.name}) — this "
                f"means its tiles are read from ow_sprites but written "
                f"into enemy_set_b/c at the top of the bank.  Might be "
                f"fine, but it's unusual."
            )

        for sprite_set, enemies in group_enemies.items():
            if start_enemy not in enemies:
                continue
            if sprite_set not in _GROUP_SPRITE_ATTR:
                continue

            target = getattr(sprites, _GROUP_SPRITE_ATTR[sprite_set])
            rom_offset = (pos_base - _COL_START) * 16
            if sprite_set == EnemySpriteSet.OW:
                # If start enemy ends up in OW somehow, we need the prefix.
                # (Today it shouldn't — start_enemy is pre-seeded into B/C
                # only.  Still, be safe.)
                rom_offset += _OW_BANK_PREFIX
                dbg.warn(
                    f"start_enemy packed into OW group — unusual, "
                    f"using OW prefix for offset"
                )
            for k in range(len(data)):
                target[rom_offset + k] = data[k]
            dbg.log(
                f"  wrote into {_GROUP_SPRITE_ATTR[sprite_set]} @ "
                f"byte offset {rom_offset} (cols {pos_base}-{pos_base + cols - 1})"
            )

    return list(range(pos_base, pos_base + cols))


def _update_tile_frames(
    enemies: EnemyData,
    column_assignments: dict[Enemy, list[int]],
    dbg: _DebugLog,
) -> None:
    """Update tile_frames to reflect new sprite set positions."""
    with dbg.section("tile_frames remap"):
        # Sort for deterministic output.
        for enemy in sorted(column_assignments, key=lambda e: e.name):
            assigned_cols = column_assignments[enemy]
            if enemy not in enemies.tile_frames:
                dbg.log(f"  {enemy.name}: not in tile_frames — skipped")
                continue

            frames = enemies.tile_frames[enemy]
            if not frames:
                dbg.log(f"  {enemy.name}: empty tile_frames — skipped")
                continue

            vanilla_cols = _VANILLA_COLUMNS.get(enemy)
            if vanilla_cols is None:
                dbg.warn(
                    f"{enemy.name}: no _VANILLA_COLUMNS entry — frames left unchanged"
                )
                continue

            origin = _VANILLA_SPRITE_SET.get(enemy)
            origin_tag = " [OW-ORIGIN]" if origin == EnemySpriteSet.OW else ""

            col_map: dict[int, int] = {}
            for old_col, new_col in zip(vanilla_cols, assigned_cols):
                col_map[old_col] = new_col

            dbg.log(
                f"  {enemy.name:<20s}{origin_tag} "
                f"vanilla_cols={vanilla_cols} assigned_cols={assigned_cols}"
            )
            dbg.log(f"    col_map: {dict(sorted(col_map.items()))}")
            dbg.log(f"    before:  {list(frames)}")

            trace: list[str] = []
            remapped: list[int] = []
            for f in frames:
                if f in col_map:
                    new_f = col_map[f]
                    remapped.append(new_f)
                    trace.append(f"{f}->{new_f}")
                else:
                    remapped.append(f)
                    # Flag if the frame is in a "bank range" where we'd
                    # expect it to be remapped.  For dungeon groups the
                    # range is roughly 158-255; for OW it's 158-255 too.
                    if _COL_START <= f < 256:
                        # Check whether this frame is in a reserved slot
                        # (Wallmaster extra, Lanmola reserved).  If so,
                        # passthrough is legitimate.
                        if f in _WALLMASTER_EXTRA_SLOTS or f in _LANMOLA_RESERVED_SLOTS:
                            trace.append(f"{f}->{f}(reserved-slot)")
                        else:
                            trace.append(f"{f}->{f}(UNMAPPED)")
                            dbg.warn(
                                f"{enemy.name} frame {f} is in the enemy bank "
                                f"range but has no entry in col_map "
                                f"(vanilla_cols={vanilla_cols})"
                            )
                    else:
                        trace.append(f"{f}->{f}(engine-tile)")
            dbg.log(f"    trace:   {' '.join(trace)}")
            dbg.log(f"    after:   {remapped}")

            enemies.tile_frames[enemy] = remapped


def _duplicate_companion_tile_frames(enemies: EnemyData, dbg: _DebugLog) -> None:
    """Copy tile_frames from primaries to companions."""
    with dbg.section("Duplicate companion tile_frames"):
        for source, dest in _TILE_FRAME_COPIES:
            if enemies.tile_frames.get(source):
                enemies.tile_frames[dest] = list(enemies.tile_frames[source])
                dbg.log(
                    f"  {source.name:<20s} -> {dest.name:<20s} "
                    f"frames={enemies.tile_frames[source]}"
                )
            else:
                dbg.log(
                    f"  {source.name:<20s} -> {dest.name:<20s} "
                    f"SKIPPED (source has no frames)"
                )


# ---------------------------------------------------------------------------
# Sorting and assignment
# ---------------------------------------------------------------------------

def _sort_enemies_by_tile_columns(enemies: list[Enemy], rng: Rng, dbg: _DebugLog) -> list[Enemy]:
    adjusted_columns: dict[Enemy, int] = dict(_ENEMY_TILE_COLUMNS)
    adjusted_columns[Enemy.WALLMASTER] = _ENEMY_TILE_COLUMNS[Enemy.WALLMASTER] + 2

    result = list(enemies)
    for i in range(len(result)):
        for j in range(i + 1, len(result)):
            do_swap: bool
            if adjusted_columns[result[i]] > adjusted_columns[result[j]]:
                do_swap = True
            elif adjusted_columns[result[i]] == adjusted_columns[result[j]]:
                do_swap = (int(rng.random() * 2) == 0)
            else:
                do_swap = False
            if do_swap:
                result[i], result[j] = result[j], result[i]

    dbg.log(
        f"sorted (ascending, with RNG tie-break): "
        f"{[(e.name, adjusted_columns[e]) for e in result]}"
    )
    return result


def _pick_start_enemy(
    sorted_enemies: list[Enemy],
    rng: Rng,
    dbg: _DebugLog,
) -> Enemy:
    candidates = [
        e for e in sorted_enemies
        if _ENEMY_TILE_COLUMNS[e] == 4
        and e != Enemy.RED_LANMOLA
        and e != Enemy.WALLMASTER
    ]
    pick = rng.choice(candidates)
    dbg.log(
        f"start_enemy candidates: {[e.name for e in candidates]}, "
        f"picked: {pick.name}"
    )
    origin = _VANILLA_SPRITE_SET.get(pick)
    if origin == EnemySpriteSet.OW:
        dbg.log(
            f"  NOTE: start_enemy {pick.name} is OW-ORIGIN — its tiles "
            f"will be read from ow_sprites and packed into enemy_set_b/c"
        )
    return pick


def _effective_column_cost(enemy: Enemy) -> int:
    cost = _ENEMY_TILE_COLUMNS[enemy]
    if enemy == Enemy.WALLMASTER:
        cost += _WALLMASTER_SHARED_BLOCK_SIZE // 16
    return cost


def _assign_enemies_to_groups(
    sorted_enemies: list[Enemy],
    start_enemy: Enemy,
    rng: Rng,
    overworld: bool,
    force_wizzrobes_to_9: bool,
    vire_is_wizzrobe_compat: bool,
    dbg: _DebugLog,
    attempt_num: int,
) -> dict[EnemySpriteSet, list[Enemy]] | None:
    num_groups = 4 if overworld else 3

    wizzrobe_compat = set(_WIZZROBE_COMPAT_BASE)
    if vire_is_wizzrobe_compat:
        wizzrobe_compat.add(Enemy.VIRE)

    group_lists: dict[EnemySpriteSet, list[Enemy]] = {
        _GROUP_ORDER[g]: [] for g in range(num_groups)
    }
    capacities: dict[EnemySpriteSet, int] = {
        _GROUP_ORDER[g]: 0 for g in range(num_groups)
    }

    if overworld:
        capacities[EnemySpriteSet.OW] = -2

    start_cost = _effective_column_cost(start_enemy)
    group_lists[EnemySpriteSet.B].append(start_enemy)
    group_lists[EnemySpriteSet.C].append(start_enemy)
    capacities[EnemySpriteSet.B] += start_cost
    capacities[EnemySpriteSet.C] += start_cost

    if force_wizzrobes_to_9:
        group_lists[EnemySpriteSet.C].append(Enemy.RED_WIZZROBE)
        capacities[EnemySpriteSet.C] += _effective_column_cost(Enemy.RED_WIZZROBE)

    # We log this attempt only if it succeeds OR we're on the last attempt —
    # otherwise logs from 1000 failed attempts would drown everything.
    events: list[str] = []

    for enemy in sorted_enemies:
        if enemy == start_enemy:
            continue
        if enemy == Enemy.RED_WIZZROBE and force_wizzrobes_to_9:
            continue

        columns = _effective_column_cost(enemy)
        placed = False

        for _retry in range(_MAX_ASSIGNMENT_RETRIES):
            group_idx = int(rng.random() * num_groups)
            group = _GROUP_ORDER[group_idx]

            exclusion_hit = False
            for a, b in _MUTUALLY_EXCLUSIVE:
                if enemy == a and b in group_lists[group]:
                    exclusion_hit = True
                    break
                if enemy == b and a in group_lists[group]:
                    exclusion_hit = True
                    break
            if exclusion_hit:
                events.append(f"    {enemy.name} -> {group.name} REJECT (exclusion)")
                continue

            if group == EnemySpriteSet.OW and enemy in _FORBIDDEN_FROM_OVERWORLD:
                events.append(f"    {enemy.name} -> {group.name} REJECT (forbidden-OW)")
                continue

            if capacities[group] + columns > _GROUP_CAPACITY:
                events.append(
                    f"    {enemy.name} -> {group.name} REJECT (capacity: "
                    f"{capacities[group]}+{columns}>{_GROUP_CAPACITY})"
                )
                continue

            group_lists[group].append(enemy)
            capacities[group] += columns
            events.append(
                f"    {enemy.name:<20s} -> {group.name} ACCEPT "
                f"(cap_used={capacities[group]})"
            )
            placed = True
            break

        if not placed:
            events.append(f"    {enemy.name} FAILED after {_MAX_ASSIGNMENT_RETRIES} retries")
            # Log only on final outer attempt
            if attempt_num >= _MAX_OUTER_RETRIES - 1:
                with dbg.section(f"FAILED assignment attempt {attempt_num}"):
                    for e in events:
                        dbg.log(e)
            return None

    missing_compat: list[EnemySpriteSet] = []
    for g in range(num_groups):
        group = _GROUP_ORDER[g]
        if not any(e in wizzrobe_compat for e in group_lists[group]):
            missing_compat.append(group)
    if missing_compat:
        events.append(
            f"    wizzrobe-compat check FAILED for groups "
            f"{[g.name for g in missing_compat]}"
        )
        if attempt_num >= _MAX_OUTER_RETRIES - 1:
            with dbg.section(f"FAILED assignment attempt {attempt_num}"):
                for e in events:
                    dbg.log(e)
        return None

    with dbg.section(f"Successful assignment on attempt {attempt_num}"):
        for e in events:
            dbg.log(e)
    return group_lists


# ---------------------------------------------------------------------------
# Overworld replacement
# ---------------------------------------------------------------------------

def _enemy_has_ow_column_conflict(
    enemy: Enemy,
    vanilla_ow_cols: dict[Enemy, set[int]],
) -> bool:
    return enemy in vanilla_ow_cols


_COMPANION_TO_PRIMARY: dict[Enemy, Enemy] = {
    companion: primary for primary, companion in _COMPANION_EXPANSIONS.items()
}


def _is_ow_origin_orphaned(
    enemy: Enemy,
    ow_pool: list[Enemy],
    column_assignments: dict[Enemy, list[int]],
) -> bool:
    """True if enemy is vanilla-OW but got packed into a non-OW bank.

    Such an enemy's global tile_frames have been remapped to dungeon-bank
    columns that don't exist in bank OW, so rendering it on any overworld
    screen produces garbage (see BUG_REPORT_ow_origin_enemy_frames_on_overworld).
    """
    primary = _COMPANION_TO_PRIMARY.get(enemy, enemy)
    if _VANILLA_SPRITE_SET.get(primary) != EnemySpriteSet.OW:
        return False
    if primary in ow_pool:
        return False
    return primary in column_assignments


def _replace_overworld_enemies(
    world: GameWorld,
    rng: Rng,
    group_enemies: dict[EnemySpriteSet, list[Enemy]],
    column_assignments: dict[Enemy, list[int]],
    dbg: _DebugLog,
) -> None:
    ow_pool = group_enemies.get(EnemySpriteSet.OW, [])
    with dbg.section("Overworld enemy replacement"):
        dbg.log(f"  ow_pool: {[e.name for e in ow_pool]}")
        if not ow_pool:
            dbg.log("  (empty ow_pool, nothing to replace)")
            return

        tile_frames = world.enemies.tile_frames

        shuffled = set(column_assignments.keys())
        vanilla_ow_cols: dict[Enemy, set[int]] = {}
        for enemy, frames in tile_frames.items():
            if enemy in shuffled:
                cols = _VANILLA_COLUMNS.get(enemy, [])
            else:
                cols = frames or []
            ow_overlap = _OW_WRITABLE_COLUMNS & frozenset(cols)
            if ow_overlap:
                vanilla_ow_cols[enemy] = ow_overlap

        replaced = 0
        skipped = 0
        no_safe_pick = 0
        decomposed = 0

        for screen in world.overworld.screens:
            enemy = screen.enemy_spec.enemy
            is_group = screen.enemy_spec.is_group
            members = screen.enemy_spec.group_members
            screen_num = getattr(screen, 'screen_num', '?')

            if is_group:
                needs_replacement = False
                reasons: list[str] = []

                has_blue_moblin = _screen_has_enemy(enemy, Enemy.BLUE_MOBLIN, is_group, members)
                if has_blue_moblin and _needs_bracelet(screen_num):
                    needs_replacement = True
                    reasons.append("blue_moblin+bracelet")

                has_wizzrobe = (
                    _screen_has_enemy(enemy, Enemy.RED_WIZZROBE, is_group, members)
                    or _screen_has_enemy(enemy, Enemy.BLUE_WIZZROBE, is_group, members)
                )
                if has_wizzrobe and screen_num in _BAD_FOR_WIZZROBE_SCREENS:
                    needs_replacement = True
                    reasons.append("wizzrobe+bad-screen")

                orphaned_members = [
                    m for m in (members or [])
                    if _is_ow_origin_orphaned(m, ow_pool, column_assignments)
                ]
                if orphaned_members:
                    needs_replacement = True
                    reasons.append(
                        f"ow_origin_orphaned({[m.name for m in orphaned_members]})"
                    )

                if not needs_replacement:
                    skipped += 1
                    continue

                dbg.log(
                    f"  screen {screen_num}: group decompose "
                    f"(reasons={reasons}) members_were={[m.name for m in (members or [])]}"
                )
                screen.enemy_spec = type(screen.enemy_spec)(
                    enemy=Enemy.BLUE_MOBLIN,
                    is_group=False,
                    group_members=None,
                )
                decomposed += 1

            ow_enemy_id = screen.enemy_spec.enemy

            if not is_group and ow_enemy_id in (Enemy.FAIRY, Enemy.GHINI_1):
                skipped += 1
                continue

            in_pool = ow_enemy_id in ow_pool
            has_conflict = _enemy_has_ow_column_conflict(ow_enemy_id, vanilla_ow_cols)
            is_orphaned = _is_ow_origin_orphaned(
                ow_enemy_id, ow_pool, column_assignments
            )

            if not in_pool and not has_conflict and not is_orphaned:
                skipped += 1
                continue

            reason = []
            if in_pool:
                reason.append("in_pool")
            if has_conflict:
                reason.append(
                    f"column_conflict(vanilla_cols={sorted(vanilla_ow_cols.get(ow_enemy_id, set()))})"
                )
            if is_orphaned:
                reason.append("ow_origin_orphaned")

            for _attempt in range(_MAX_ROOM_RETRIES):
                new_enemy = rng.choice(ow_pool)

                if new_enemy == Enemy.BLUE_MOBLIN and _needs_bracelet(screen_num):
                    continue
                if new_enemy in (Enemy.RED_WIZZROBE, Enemy.BLUE_WIZZROBE):
                    if screen_num in _BAD_FOR_WIZZROBE_SCREENS:
                        continue

                dbg.log(
                    f"  screen {screen_num}: {ow_enemy_id.name} -> "
                    f"{new_enemy.name} ({','.join(reason)})"
                )
                screen.enemy_spec.enemy = new_enemy
                replaced += 1
                break
            else:
                no_safe_pick += 1
                dbg.warn(
                    f"screen {screen_num}: could not find safe replacement "
                    f"for {ow_enemy_id.name} in {_MAX_ROOM_RETRIES} attempts "
                    f"— keeping original"
                )

        dbg.log(f"  summary: replaced={replaced} decomposed={decomposed} "
                f"skipped={skipped} no_safe_pick={no_safe_pick}")


# ---------------------------------------------------------------------------
# Mixed enemy group fixup
# ---------------------------------------------------------------------------

def _update_mixed_group_members(
    world: GameWorld,
    group_enemies: dict[EnemySpriteSet, list[Enemy]],
    rng: Rng,
    dbg: _DebugLog,
) -> None:
    with dbg.section("Mixed group member fixup"):
        cross_set_decomposed = 0
        for level in world.levels:
            level_pool = group_enemies.get(level.enemy_sprite_set)
            if not level_pool:
                continue
            level_num = getattr(level, 'number', '?')
            for room in level.rooms:
                if not room.enemy_spec.is_group:
                    continue
                code = room.enemy_spec.enemy.value
                group_owner = _MIXED_GROUP_SPRITE_SET.get(code)
                if group_owner is None or group_owner == level.enemy_sprite_set:
                    continue

                for _attempt in range(_MAX_ROOM_RETRIES):
                    new_enemy = rng.choice(level_pool)
                    if not is_safe_for_room(new_enemy, room.room_type,
                                            has_push_block=room.movable_block):
                        continue
                    dbg.log(
                        f"  L{level_num} room={getattr(room, 'id', '?')}: "
                        f"cross-set decompose (code=0x{code:02X} owner="
                        f"{group_owner.name} level_set="
                        f"{level.enemy_sprite_set.name}) -> {new_enemy.name}"
                    )
                    room.enemy_spec = EnemySpec(enemy=new_enemy)
                    cross_set_decomposed += 1
                    break

        data = world.enemies.mixed_enemy_data
        offsets = world.enemies.mixed_group_offsets
        substitutions_by_group: dict[int, list[str]] = {}
        for code, offset in offsets.items():
            owner_set = _MIXED_GROUP_SPRITE_SET.get(code)
            if owner_set is None:
                continue
            pool = group_enemies.get(owner_set)
            if not pool:
                continue
            substitutions_by_group[code] = []
            for i in range(8):
                member = Enemy(data[offset + i])
                if member in _SHUFFLEABLE_ENEMIES:
                    replacement = rng.choice(pool)
                    substitutions_by_group[code].append(
                        f"[{i}]{member.name}->{replacement.name}"
                    )
                    data[offset + i] = replacement.value
                else:
                    substitutions_by_group[code].append(f"[{i}]{member.name}")

        for code, subs in sorted(substitutions_by_group.items()):
            owner = _MIXED_GROUP_SPRITE_SET.get(code)
            dbg.log(
                f"  group 0x{code:02X} (owner={owner.name if owner else '?'}): "
                f"{' '.join(subs)}"
            )

        for code, offset in offsets.items():
            world.enemies.mixed_groups[code] = [
                Enemy(data[offset + i]) for i in range(8)
            ]

        for level in world.levels:
            for room in level.rooms:
                if not room.enemy_spec.is_group:
                    continue
                code = room.enemy_spec.enemy.value
                updated = world.enemies.mixed_groups.get(code)
                if updated is not None:
                    room.enemy_spec.group_members = list(updated)

        dbg.log(f"  cross-set rooms decomposed: {cross_set_decomposed}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def change_dungeon_enemy_groups(
    world: GameWorld,
    rng: Rng,
    overworld: bool = False,
    force_wizzrobes_to_9: bool = False,
    debug: bool | None = None,
    debug_log_path: str | None = None,
) -> None:
    """Redistribute enemies across the three (or four) enemy sprite-set groups.

    Debug parameters
    ----------------
    debug : bool | None
        If True, emit a full forensic trace. If None, reads ZORA_ENEMY_DEBUG
        env var.
    debug_log_path : str | None
        Where to write the trace. Defaults to ZORA_ENEMY_DEBUG_LOG env var,
        or "enemy_groups_debug.log" in cwd.
    """
    if debug is None:
        debug = bool(os.environ.get("ZORA_ENEMY_DEBUG"))
    if debug_log_path is None:
        debug_log_path = os.environ.get(
            "ZORA_ENEMY_DEBUG_LOG", "enemy_groups_debug.log"
        )

    dbg = _DebugLog(enabled=debug, log_path=debug_log_path)

    try:
        with dbg.section("change_dungeon_enemy_groups: START"):
            dbg.log(f"overworld={overworld} force_wizzrobes_to_9={force_wizzrobes_to_9}")
            seed_repr = None
            for attr in ("seed", "_seed", "initial_seed", "state"):
                if hasattr(rng, attr):
                    try:
                        seed_repr = f"{attr}={getattr(rng, attr)!r}"
                        break
                    except Exception:
                        pass
            dbg.log(f"rng: {seed_repr or '<seed unavailable>'}")

            # Dump derived offset tables so we can cross-reference.
            dbg.log("derived _SPRITE_OFFSET:")
            for e in sorted(_SPRITE_OFFSET, key=lambda x: x.name):
                origin = _VANILLA_SPRITE_SET.get(e)
                tag = " [OW-ORIGIN]" if origin == EnemySpriteSet.OW else ""
                dbg.log(
                    f"  {e.name:<20s}{tag} "
                    f"set={origin.name if origin else '?':<2} "
                    f"offset={_SPRITE_OFFSET[e]:5d} "
                    f"size={_SPRITE_SIZE.get(e, 0):4d} "
                    f"vanilla_cols={_VANILLA_COLUMNS.get(e, [])}"
                )

        safe_enemies = [
            e for e in _ENEMY_TILE_COLUMNS
            if overworld or _VANILLA_SPRITE_SET.get(e) != EnemySpriteSet.OW
        ]
        dbg.log(f"safe_enemies: {[e.name for e in safe_enemies]}")

        sorted_enemies = _sort_enemies_by_tile_columns(safe_enemies, rng, dbg)
        start_enemy = _pick_start_enemy(sorted_enemies, rng, dbg)

        vire_hp = world.enemies.hp.get(Enemy.VIRE, 4)
        vire_is_wizzrobe_compat = (vire_hp <= 4)
        dbg.log(
            f"vire_hp={vire_hp}, vire_is_wizzrobe_compat={vire_is_wizzrobe_compat}"
        )

        with dbg.section("Group assignment"):
            group_enemies: dict[EnemySpriteSet, list[Enemy]] | None = None
            for _outer in range(_MAX_OUTER_RETRIES):
                group_enemies = _assign_enemies_to_groups(
                    sorted_enemies, start_enemy, rng,
                    overworld, force_wizzrobes_to_9,
                    vire_is_wizzrobe_compat, dbg, _outer,
                )
                if group_enemies is not None:
                    dbg.log(f"  (succeeded on attempt {_outer})")
                    break
            else:
                dbg.warn(f"FAILED to assign after {_MAX_OUTER_RETRIES} attempts")
                raise RuntimeError(
                    "change_dungeon_enemy_groups: failed to assign enemies "
                    f"to groups after {_MAX_OUTER_RETRIES} attempts"
                )

        with dbg.section("Final group contents"):
            for ss in [EnemySpriteSet.A, EnemySpriteSet.B,
                       EnemySpriteSet.C, EnemySpriteSet.OW]:
                if ss in group_enemies:
                    es = group_enemies[ss]
                    total = sum(_effective_column_cost(e) for e in es)
                    dbg.log(
                        f"  {ss.name}: {[e.name for e in es]} "
                        f"(total_cols={total})"
                    )

        with dbg.section("Read vanilla tile data"):
            tile_cache: dict[Enemy, bytes] = {}
            for enemy in _VANILLA_SPRITE_SET:
                tile_cache[enemy] = _read_enemy_tiles(world.sprites, enemy, dbg)
            wallmaster_shared_block = _read_wallmaster_shared_block(world.sprites)
            dbg.log(
                f"  wallmaster shared block first16 = "
                f"{wallmaster_shared_block[:16].hex()}"
            )

        column_assignments = _repack_enemy_sprites(
            world.sprites, group_enemies, wallmaster_shared_block,
            start_enemy, tile_cache, dbg,
        )

        start_cols = _repack_start_enemy(
            world.sprites, start_enemy, group_enemies, tile_cache, dbg,
        )
        column_assignments[start_enemy] = start_cols

        with dbg.section("Final column_assignments"):
            for e, cols in sorted(column_assignments.items(), key=lambda kv: kv[0].name):
                origin = _VANILLA_SPRITE_SET.get(e)
                tag = " [OW-ORIGIN]" if origin == EnemySpriteSet.OW else ""
                dbg.log(f"  {e.name:<20s}{tag} -> cols={cols}")

        _update_tile_frames(world.enemies, column_assignments, dbg)
        _duplicate_companion_tile_frames(world.enemies, dbg)

        with dbg.section("UNIMPLEMENTED: Overworld Wizzrobe engine patches"):
            ow_pool = group_enemies.get(EnemySpriteSet.OW, [])
            has_bw = Enemy.BLUE_WIZZROBE in ow_pool
            has_rw = Enemy.RED_WIZZROBE in ow_pool
            dbg.log(f"  OW contains BLUE_WIZZROBE={has_bw} RED_WIZZROBE={has_rw}")
            if has_bw or has_rw:
                dbg.warn(
                    "Wizzrobes are in the OW pool but the engine patches "
                    "(ROM 0x11E4B, 0x13005, 0x13F10, 0x12D2E) are NOT "
                    "implemented — OW Wizzrobes will likely misbehave"
                )

        with dbg.section("Companion variant expansion"):
            for ss, group in group_enemies.items():
                before = list(group)
                additions: list[Enemy] = []
                for enemy in group:
                    if enemy in _COMPANION_EXPANSIONS:
                        additions.append(_COMPANION_EXPANSIONS[enemy])
                group.extend(additions)
                if additions:
                    dbg.log(
                        f"  {ss.name}: {[e.name for e in before]} + "
                        f"{[e.name for e in additions]} -> "
                        f"{[e.name for e in group]}"
                    )
                else:
                    dbg.log(f"  {ss.name}: no variants added")

        world.enemies.cave_groups = dict(group_enemies)

        _update_mixed_group_members(world, group_enemies, rng, dbg)

        _all_vanilla_group_enemies: frozenset[Enemy] = frozenset().union(
            *_VANILLA_ENEMY_GROUPS.values()
        )

        with dbg.section("Per-room replacement (dungeons)"):
            rooms_replaced = 0
            rooms_skipped_staircase = 0
            rooms_skipped_boss = 0
            rooms_zol_start = 0
            rooms_not_in_group = 0
            rooms_empty_pool = 0
            rooms_no_safe_pick = 0

            for level in world.levels:
                level_pool = group_enemies.get(level.enemy_sprite_set)
                level_num = getattr(level, 'number', '?')

                for room in level.rooms:
                    if room.room_type in (RoomType.ITEM_STAIRCASE,
                                           RoomType.TRANSPORT_STAIRCASE):
                        rooms_skipped_staircase += 1
                        continue

                    enemy = room.enemy_spec.enemy

                    if enemy.is_boss and enemy not in (Enemy.RED_LANMOLA,
                                                        Enemy.BLUE_LANMOLA):
                        rooms_skipped_boss += 1
                        continue

                    if enemy == Enemy.ZOL:
                        room.enemy_spec.enemy = start_enemy
                        rooms_zol_start += 1
                        dbg.log(
                            f"  L{level_num} room={getattr(room, 'id', '?')}: "
                            f"ZOL -> start_enemy={start_enemy.name}"
                        )
                        continue

                    if enemy not in _all_vanilla_group_enemies:
                        rooms_not_in_group += 1
                        continue

                    if not level_pool:
                        rooms_empty_pool += 1
                        dbg.warn(
                            f"L{level_num} room={getattr(room, 'id', '?')}: "
                            f"enemy {enemy.name} but level pool for "
                            f"{level.enemy_sprite_set.name} is empty"
                        )
                        continue

                    picked = False
                    for _attempt in range(_MAX_ROOM_RETRIES):
                        new_enemy = rng.choice(level_pool)
                        if not is_safe_for_room(
                            new_enemy, room.room_type,
                            has_push_block=room.movable_block,
                        ):
                            continue
                        room.enemy_spec.enemy = new_enemy
                        picked = True
                        rooms_replaced += 1
                        new_frames = world.enemies.tile_frames.get(new_enemy, [])
                        dbg.log(
                            f"  L{level_num} room={getattr(room, 'id', '?')} "
                            f"type={room.room_type.name:<22} "
                            f"{enemy.name:<16} -> {new_enemy.name:<16} "
                            f"(new_frames={list(new_frames)})"
                        )
                        break
                    if not picked:
                        rooms_no_safe_pick += 1
                        dbg.warn(
                            f"L{level_num} room={getattr(room, 'id', '?')} "
                            f"({room.room_type.name}): no safe pick in "
                            f"{[e.name for e in level_pool]} after "
                            f"{_MAX_ROOM_RETRIES} attempts"
                        )

            dbg.log(f"summary: replaced={rooms_replaced} "
                    f"staircase={rooms_skipped_staircase} "
                    f"boss={rooms_skipped_boss} "
                    f"zol_to_start={rooms_zol_start} "
                    f"not_in_group={rooms_not_in_group} "
                    f"empty_pool={rooms_empty_pool} "
                    f"no_safe_pick={rooms_no_safe_pick}")

        if overworld:
            _replace_overworld_enemies(world, rng, group_enemies, column_assignments, dbg)

        with dbg.section("change_dungeon_enemy_groups: END"):
            dbg.log(f"warnings:          {dbg._warn_count}")
            dbg.log(f"assertion failures: {dbg._assert_count}")

    finally:
        dbg.flush()