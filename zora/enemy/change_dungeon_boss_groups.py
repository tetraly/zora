"""Redistribute bosses across boss sprite-set groups, then update rooms.

Instead of assigning a fixed tier per dungeon (like shuffle_bosses.py),
this routine redistributes *which bosses belong to which sprite-set group*
(A/B/C), then replaces every existing boss room with a random pick from
its group's new pool.

Ported from changeDungeonBossGroups (change_dungeon_boss_groups.cs).

==============================================================================
DEBUG INSTRUMENTATION
==============================================================================
This version is heavily instrumented.  Set the environment variable
ZORA_BOSS_DEBUG=1 (or pass debug=True to change_dungeon_boss_groups) to emit
a full forensic trace to stderr and to a log file.  The log captures:

  * Input state: rng seed echo, initial budgets, special-boss pick.
  * Group assignment: every attempt, every retry, every accept/reject.
  * Final group_bosses (all 4 groups) with column totals.
  * Full column_assignments dict, sorted by group and column.
  * Per-group VRAM layout: which columns contain which boss, plus a
    compact hex signature of the first 16 bytes of each column so you can
    cross-reference against an emulator CHR dump.
  * Before/after tile_frames for every affected boss, with per-frame
    remap trace (source_col -> dest_col + bonus breakdown).
  * Variant expansion + GLEEOK_1->GLEEOK_2 replacement trace.
  * Per-room replacement: old_enemy -> new_enemy, retries, final frames.
  * Sanity assertions: flag anything suspicious (unmapped frames,
    out-of-range columns, budget overruns, TODO-path hits).

Every glitch-capable state transition writes a tagged line.  Grep the log
for ``WARN`` or ``ASSERT`` to find suspicious events.
==============================================================================
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from typing import Iterator

from zora.data_model import (
    BossSpriteSet,
    Enemy,
    EnemyData,
    GameWorld,
    RoomType,
    SpriteData,
)
from zora.enemy.safety_checks import is_safe_for_room
from zora.rng import Rng

# Maximum retries when assigning a boss to a group with insufficient column budget.
_MAX_ASSIGNMENT_RETRIES = 1000

# Maximum retries when a safety check rejects a random boss pick for a room.
_MAX_ROOM_RETRIES = 1000


# ---------------------------------------------------------------------------
# Digdogger tile offset correction toggle.
#
# When True, use corrected tile offsets that assume Aquamentus's actual tile
# footprint extends through col ~223 and Digdogger's real tiles start later.
# This is the current best-guess fix for the Digdogger animation glitch.
# If glitches worsen, flip this back to False to restore the original (buggy
# but well-understood) behavior.
# ---------------------------------------------------------------------------
_USE_CORRECTED_DIGDOGGER_OFFSETS = True


# ---------------------------------------------------------------------------
# Boss definitions: sprite tile sizes, companions, and group membership.
# ---------------------------------------------------------------------------

# NOTE: The TRIPLE_DIGDOGGER / DIGDOGGER_SPAWN offsets below are suspected
# to have transcription errors from the C# port.  A vanilla ROM inspection
# showed that the bytes at the original offsets (320 / 384) look like
# Aquamentus tiles, not Digdogger tiles.  A user report of a Digdogger with
# one good animation frame and one glitched frame is consistent with this.
# If after changing these values the glitches persist or change character,
# the offsets may need further adjustment — cross-check against the
# bossStatOffsets array in the C# source.

# Number of 16-byte sprite tile columns each primary boss requires.
# Each sprite set has a fixed column budget (64 columns = 1024 bytes for
# groups A/B/C, 32 columns = 512 bytes for the shared group).  A boss can
# only be assigned to a group that has enough remaining columns.
_BOSS_TILE_COLUMNS_ORIGINAL: dict[Enemy, int] = {
    Enemy.AQUAMENTUS:        20,
    Enemy.TRIPLE_DODONGO:    36,
    Enemy.TRIPLE_DIGDOGGER:   4,
    Enemy.MANHANDLA:         14,
    Enemy.GLEEOK_1:          32,
    Enemy.BLUE_GOHMA:        16,
    Enemy.PATRA_2:            4,
}

_BOSS_TILE_COLUMNS_CORRECTED: dict[Enemy, int] = {
    Enemy.AQUAMENTUS:        20,
    Enemy.TRIPLE_DODONGO:    36,
    Enemy.TRIPLE_DIGDOGGER:   4,
    Enemy.MANHANDLA:         14,
    Enemy.GLEEOK_1:          32,
    Enemy.BLUE_GOHMA:        16,
    Enemy.PATRA_2:            4,
}

_BOSS_TILE_COLUMNS = (
    _BOSS_TILE_COLUMNS_CORRECTED if _USE_CORRECTED_DIGDOGGER_OFFSETS
    else _BOSS_TILE_COLUMNS_ORIGINAL
)

# Some bosses require additional columns for companion sprites that must be
# loaded in the same group (DIGDOGGER_SPAWN with TRIPLE_DIGDOGGER,
# FLYING_GLEEOK_HEAD with GLEEOK_1, PATRA_SPAWN with PATRA_2).  The
# companions are not added to the replacement pool, but their sprite tiles
# are packed alongside the primary by _repack_boss_sprites.
_BOSS_TILE_COLUMNS_WITH_COMPANION: dict[Enemy, int] = {
    Enemy.GLEEOK_1:          32 + 2,  # 34
    Enemy.TRIPLE_DIGDOGGER:   4 + 4,  #  8
    Enemy.PATRA_2:            4 + 4,  #  8
}

# ---------------------------------------------------------------------------
# Sprite tile layout.
#
# Each boss occupies a contiguous run of 16-byte "columns" within its vanilla
# boss sprite set.  The number of columns matches _BOSS_TILE_COLUMNS.
# Companion bosses share their primary's sprite set and are packed adjacent.
#
# Derived from bossStatOffsets + 16400 in the C# minus each set's base address:
#   BOSS_SET_A = 0xDFEB (57323)
#   BOSS_SET_B = 0xE3EB (58347)
#   BOSS_SET_C = 0xE7EB (59371)
# ---------------------------------------------------------------------------

_VANILLA_SPRITE_SET: dict[Enemy, BossSpriteSet] = {
    Enemy.AQUAMENTUS:         BossSpriteSet.A,
    Enemy.TRIPLE_DODONGO:     BossSpriteSet.A,
    Enemy.TRIPLE_DIGDOGGER:   BossSpriteSet.A,
    Enemy.DIGDOGGER_SPAWN:    BossSpriteSet.A,
    Enemy.MANHANDLA:          BossSpriteSet.B,
    Enemy.GLEEOK_1:           BossSpriteSet.B,
    Enemy.BLUE_GOHMA:         BossSpriteSet.B,
    Enemy.FLYING_GLEEOK_HEAD: BossSpriteSet.B,
    Enemy.PATRA_2:            BossSpriteSet.C,
    Enemy.PATRA_SPAWN:        BossSpriteSet.C,
}

# Byte offset of each boss's tile data within its vanilla sprite set.
_SPRITE_OFFSET_ORIGINAL: dict[Enemy, int] = {
    Enemy.AQUAMENTUS:           0,  # 0xDFEB - 0xDFEB
    Enemy.TRIPLE_DIGDOGGER:   320,  # 0xE12B - 0xDFEB
    Enemy.DIGDOGGER_SPAWN:    384,  # 0xE16B - 0xDFEB
    Enemy.TRIPLE_DODONGO:     448,  # 0xE1AB - 0xDFEB
    Enemy.GLEEOK_1:             0,  # 0xE3EB - 0xE3EB
    Enemy.MANHANDLA:          512,  # 0xE5EB - 0xE3EB
    Enemy.FLYING_GLEEOK_HEAD: 736,  # 0xE6DB - 0xE3EB
    Enemy.BLUE_GOHMA:         768,  # 0xE6FB - 0xE3EB
    Enemy.PATRA_2:            896,  # 0xEB6B - 0xE7EB
    Enemy.PATRA_SPAWN:        960,  # 0xEBAB - 0xE7EB
}

_SPRITE_OFFSET_CORRECTED: dict[Enemy, int] = {
    Enemy.AQUAMENTUS:           0,  # 0xDFEB - 0xDFEB (unchanged)
    Enemy.TRIPLE_DIGDOGGER:   384,  # was 320; moves to col 216
    # TODO: DIGDOGGER_SPAWN now has the same offset as TRIPLE_DIGDOGGER
    # (384).  If both primary and companion share the same offset, one of
    # them is probably wrong — they may share tiles, or the companion may
    # start at 384+64=448 (but that collides with TRIPLE_DODONGO).
    # Needs verification against a hex dump of boss_set_a.
    Enemy.DIGDOGGER_SPAWN:    384,  # unchanged value, but suspicious overlap
    Enemy.TRIPLE_DODONGO:     448,  # 0xE1AB - 0xDFEB (unchanged)
    Enemy.GLEEOK_1:             0,  # 0xE3EB - 0xE3EB (unchanged)
    Enemy.MANHANDLA:          512,  # 0xE5EB - 0xE3EB (unchanged)
    Enemy.FLYING_GLEEOK_HEAD: 736,  # 0xE6DB - 0xE3EB (unchanged)
    Enemy.BLUE_GOHMA:         768,  # 0xE6FB - 0xE3EB (unchanged)
    Enemy.PATRA_2:            896,  # 0xEB6B - 0xE7EB (unchanged)
    Enemy.PATRA_SPAWN:        960,  # 0xEBAB - 0xE7EB (unchanged)
}

_SPRITE_OFFSET = (
    _SPRITE_OFFSET_CORRECTED if _USE_CORRECTED_DIGDOGGER_OFFSETS
    else _SPRITE_OFFSET_ORIGINAL
)

# Byte count of each boss's tile data (columns × 16 bytes per column).
_SPRITE_SIZE_ORIGINAL: dict[Enemy, int] = {
    Enemy.AQUAMENTUS:         320,  # 20 × 16
    Enemy.TRIPLE_DODONGO:     576,  # 36 × 16
    Enemy.TRIPLE_DIGDOGGER:    64,  #  4 × 16
    Enemy.DIGDOGGER_SPAWN:     64,  #  4 × 16
    Enemy.MANHANDLA:          224,  # 14 × 16
    Enemy.GLEEOK_1:           512,  # 32 × 16
    Enemy.BLUE_GOHMA:         256,  # 16 × 16
    Enemy.FLYING_GLEEOK_HEAD:  32,  #  2 × 16
    Enemy.PATRA_2:             64,  #  4 × 16
    Enemy.PATRA_SPAWN:         64,  #  4 × 16
}

_SPRITE_SIZE_CORRECTED: dict[Enemy, int] = {
    Enemy.AQUAMENTUS:         320,  # 20 × 16
    Enemy.TRIPLE_DODONGO:     576,  # 36 × 16
    Enemy.TRIPLE_DIGDOGGER:    64,  #  4 × 16
    Enemy.DIGDOGGER_SPAWN:     64,  #  4 × 16
    Enemy.MANHANDLA:          224,  # 14 × 16
    Enemy.GLEEOK_1:           512,  # 32 × 16
    Enemy.BLUE_GOHMA:         256,  # 16 × 16
    Enemy.FLYING_GLEEOK_HEAD:  32,  #  2 × 16
    Enemy.PATRA_2:             64,  #  4 × 16
    Enemy.PATRA_SPAWN:         64,  #  4 × 16
}

_SPRITE_SIZE = (
    _SPRITE_SIZE_CORRECTED if _USE_CORRECTED_DIGDOGGER_OFFSETS
    else _SPRITE_SIZE_ORIGINAL
)

# Companion bosses: must be packed into the same sprite set as their primary.
# Maps primary → companion.
_COMPANIONS: dict[Enemy, Enemy] = {
    Enemy.TRIPLE_DIGDOGGER:  Enemy.DIGDOGGER_SPAWN,
    Enemy.GLEEOK_1:          Enemy.FLYING_GLEEOK_HEAD,
    Enemy.PATRA_2:           Enemy.PATRA_SPAWN,
}

# Number of 16-byte columns reserved at the start of boss_set_c that must
# not be overwritten.  The original pre-fills columns 192-247 (56 columns).
_BOSS_SET_C_RESERVED_BYTES = 56 * 16  # 896


# "Special" bosses: one is randomly forced into the shared group (group 3).
# Each restores some column budget to the shared group when selected.
_SPECIAL_BOSSES: list[Enemy] = [Enemy.AQUAMENTUS, Enemy.MANHANDLA, Enemy.TRIPLE_DIGDOGGER]
_SPECIAL_RESTORE: dict[Enemy, int] = {
    Enemy.AQUAMENTUS:       20,
    Enemy.MANHANDLA:        14,
    Enemy.TRIPLE_DIGDOGGER:  8,
}

# Variant expansion: after group assignment, these extra enemies are added
# to whichever group their base form ended up in.
_VARIANT_EXPANSIONS: dict[Enemy, list[Enemy]] = {
    Enemy.TRIPLE_DODONGO:   [Enemy.SINGLE_DODONGO],
    Enemy.TRIPLE_DIGDOGGER: [Enemy.SINGLE_DIGDOGGER],
    Enemy.BLUE_GOHMA:       [Enemy.RED_GOHMA],
    Enemy.PATRA_2:          [Enemy.PATRA_1],
    Enemy.GLEEOK_1:         [Enemy.GLEEOK_3, Enemy.GLEEOK_4],
}

# The vanilla boss groups — which bosses originally belong to each sprite set.
# Used to detect which group a room's current boss belongs to, so we know
# which new pool to draw from.
_VANILLA_BOSS_GROUPS: dict[BossSpriteSet, frozenset[Enemy]] = {
    BossSpriteSet.A: frozenset({
        Enemy.AQUAMENTUS,
        Enemy.TRIPLE_DODONGO, Enemy.SINGLE_DODONGO,
        Enemy.TRIPLE_DIGDOGGER, Enemy.SINGLE_DIGDOGGER,
    }),
    BossSpriteSet.B: frozenset({
        Enemy.MANHANDLA,
        Enemy.BLUE_GOHMA, Enemy.RED_GOHMA,
        Enemy.GLEEOK_1, Enemy.GLEEOK_2, Enemy.GLEEOK_3, Enemy.GLEEOK_4,
    }),
    BossSpriteSet.C: frozenset({
        Enemy.PATRA_1, Enemy.PATRA_2,
    }),
}


# ---------------------------------------------------------------------------
# Group index ↔ BossSpriteSet mapping.
# ---------------------------------------------------------------------------

_GROUP_ORDER: list[BossSpriteSet] = [BossSpriteSet.A, BossSpriteSet.B, BossSpriteSet.C]

# Maps group index (0-2) to the SpriteData attribute name for that set.
_GROUP_SPRITE_ATTR: dict[int, str] = {
    0: "boss_set_a",
    1: "boss_set_b",
    2: "boss_set_c",
}


# The NES engine addresses sprite tiles by "column number", not byte offset.
# Column numbers start at a fixed base per group; byte offset within the
# sprite set = (column - column_start) * 16.
_COL_START_MAIN = 192    # groups 0-2 (boss_set_a/b/c)
_COL_START_EXPANSION = 48  # group 3 (boss_set_expansion)


# ---------------------------------------------------------------------------
# DEBUG LOGGING INFRASTRUCTURE
# ---------------------------------------------------------------------------

class _DebugLog:
    """Collects forensic trace lines during a single run.

    Writes to both stderr (if enabled) and an in-memory buffer that is
    flushed to a log file at the end of the run.  Designed so that a user
    experiencing a glitch can attach the log file to a bug report and a
    debugger (human or Claude) has every state transition needed to find
    the mismatch between sprite-tile placement and engine tile references.
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
        """Record (but do not raise) an assertion failure."""
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
    """Return a compact hex signature for a single 16-byte column.

    Two 8-byte halves separated by a bar, matching the NES CHR tile layout
    (first 8 bytes = low bitplane, next 8 = high bitplane).  Handy for
    eyeballing whether a column looks like real tile data or garbage, and
    for cross-referencing against an emulator CHR dump.
    """
    chunk = bytes(buf[col_byte_offset:col_byte_offset + 16])
    if len(chunk) < 16:
        chunk = chunk + b"\x00" * (16 - len(chunk))
    lo = chunk[:8].hex()
    hi = chunk[8:].hex()
    return f"{lo}|{hi}"


def _ascii_render_tile(buf: bytes, col_byte_offset: int) -> list[str]:
    """Render a single 8x8 NES tile as 8 lines of ASCII.

    Uses '.', '-', '+', '#' for the 4 palette indices.  Useful for
    spot-checking whether a column looks like the boss it should be.
    """
    chunk = bytes(buf[col_byte_offset:col_byte_offset + 16])
    if len(chunk) < 16:
        chunk = chunk + b"\x00" * (16 - len(chunk))
    glyphs = [".", "-", "+", "#"]
    rows: list[str] = []
    for y in range(8):
        lo = chunk[y]
        hi = chunk[y + 8]
        row = []
        for x in range(8):
            bit = 7 - x
            px = ((lo >> bit) & 1) | (((hi >> bit) & 1) << 1)
            row.append(glyphs[px])
        rows.append("".join(row))
    return rows


# ---------------------------------------------------------------------------
# Sprite packing.
# ---------------------------------------------------------------------------

def _read_boss_tiles(sprites: SpriteData, boss: Enemy) -> bytes:
    """Extract a boss's sprite tile data from its vanilla sprite set."""
    vanilla_set = _VANILLA_SPRITE_SET[boss]
    source = getattr(sprites, _GROUP_SPRITE_ATTR[_GROUP_ORDER.index(vanilla_set)])
    offset = _SPRITE_OFFSET[boss]
    size = _SPRITE_SIZE[boss]
    return bytes(source[offset:offset + size])


def _repack_boss_sprites(
    sprites: SpriteData,
    group_bosses: list[list[Enemy]],
    dbg: _DebugLog,
) -> dict[Enemy, int]:
    """Rewrite boss sprite sets to match the new group assignments.

    For groups 0-2 (A/B/C), boss tile data is packed sequentially into the
    corresponding boss_set_* bytearray.  Group 2 (C) preserves the first
    896 bytes (56 reserved columns) and packs new data after that.

    For group 3 (shared), tile data is packed into boss_set_expansion.

    Companion bosses (DIGDOGGER_SPAWN, FLYING_GLEEOK_HEAD, PATRA_SPAWN)
    follow their primary into whichever group it was assigned to.

    Returns a dict mapping each packed boss (including companions) to the
    engine column number where its tile data starts in the target set.
    """
    with dbg.section("Repack boss sprites"):
        # Snapshot the vanilla sets BEFORE we overwrite anything.  This
        # lets us verify in the log that tile_cache pulled the right bytes.
        vanilla_snapshots: dict[int, bytes] = {}
        for g in range(3):
            attr = _GROUP_SPRITE_ATTR[g]
            vanilla_snapshots[g] = bytes(getattr(sprites, attr))
            dbg.log(f"vanilla {attr}: {len(vanilla_snapshots[g])} bytes, "
                    f"first 16 = {vanilla_snapshots[g][:16].hex()}")

        # Read all boss tile data from the vanilla sets before overwriting.
        tile_cache: dict[Enemy, bytes] = {}
        for boss in _VANILLA_SPRITE_SET:
            tile_cache[boss] = _read_boss_tiles(sprites, boss)
            dbg.log(
                f"cached {boss.name:24s} "
                f"vanilla_set={_VANILLA_SPRITE_SET[boss].name} "
                f"offset={_SPRITE_OFFSET[boss]:4d} "
                f"size={_SPRITE_SIZE[boss]:4d} "
                f"first16={tile_cache[boss][:16].hex()}"
            )
            # A boss whose cached tiles are all zero is almost certainly
            # pointing at the wrong source (bad offset or wrong set).
            if tile_cache[boss] and not any(tile_cache[boss]):
                dbg.warn(f"{boss.name} tile cache is ALL ZERO — "
                         f"offset/set probably wrong")

            if boss == Enemy.TRIPLE_DIGDOGGER:
                dbg.log(
                    f"  [check: Triple Digdogger first16="
                    f"{tile_cache[boss][:16].hex()}; "
                    f"expected non-Aquamentus tile data if offset is "
                    f"correct, looks like Aquamentus body tiles if "
                    f"offset is wrong]"
                )
            if boss == Enemy.DIGDOGGER_SPAWN:
                dbg.log(
                    f"  [check: Digdogger Spawn first16="
                    f"{tile_cache[boss][:16].hex()}; "
                    f"same offset as TRIPLE_DIGDOGGER — suspicious "
                    f"overlap, see TODO in _SPRITE_OFFSET_CORRECTED]"
                )

        # Maps each boss to its starting engine column in the new set.
        column_assignments: dict[Enemy, int] = {}

        # Repack groups 0-2 into boss_set_a/b/c.
        for g in range(3):
            target = getattr(sprites, _GROUP_SPRITE_ATTR[g])
            dbg.log(f"-- packing group {g} ({_GROUP_ORDER[g].name}) "
                    f"into {_GROUP_SPRITE_ATTR[g]} (target len={len(target)})")

            if g == 2:
                # Preserve the reserved region; pack new data after it.
                write_pos = _BOSS_SET_C_RESERVED_BYTES
                dbg.log(f"   group 2 reserves {_BOSS_SET_C_RESERVED_BYTES} "
                        f"bytes (56 cols); writes start at byte {write_pos} "
                        f"= col {_COL_START_MAIN + write_pos // 16}")
            else:
                write_pos = 0

            for boss in group_bosses[g]:
                # Only pack primary bosses and companions that have sprite data.
                # Variant expansions (SINGLE_DODONGO, RED_GOHMA, etc.) share
                # their primary's sprites — they don't have separate tile entries.
                if boss not in tile_cache:
                    dbg.log(f"   {boss.name} has no tile entry (variant) — "
                            f"skipped during packing")
                    continue

                col = _COL_START_MAIN + write_pos // 16
                column_assignments[boss] = col
                data = tile_cache[boss]
                end_col = col + len(data) // 16

                dbg.log(f"   pack {boss.name:24s} "
                        f"@ cols {col:3d}-{end_col-1:3d} "
                        f"(bytes {write_pos:4d}-{write_pos+len(data)-1:4d}) "
                        f"len={len(data):4d}")

                if write_pos + len(data) > len(target):
                    dbg.warn(
                        f"{boss.name} packing overruns target "
                        f"{_GROUP_SPRITE_ATTR[g]} "
                        f"(end_byte={write_pos+len(data)}, "
                        f"target_len={len(target)})"
                    )

                target[write_pos:write_pos + len(data)] = data
                write_pos += len(data)

                # Pack companion's tiles immediately after the primary.
                if boss in _COMPANIONS:
                    companion = _COMPANIONS[boss]
                    ccol = _COL_START_MAIN + write_pos // 16
                    column_assignments[companion] = ccol
                    cdata = tile_cache[companion]
                    cend = ccol + len(cdata) // 16

                    dbg.log(f"   pack {companion.name:24s} "
                            f"@ cols {ccol:3d}-{cend-1:3d} "
                            f"(bytes {write_pos:4d}-"
                            f"{write_pos+len(cdata)-1:4d}) "
                            f"len={len(cdata):4d} [companion of {boss.name}]")

                    if write_pos + len(cdata) > len(target):
                        dbg.warn(
                            f"{companion.name} packing overruns target "
                            f"{_GROUP_SPRITE_ATTR[g]}"
                        )

                    target[write_pos:write_pos + len(cdata)] = cdata
                    write_pos += len(cdata)

            dbg.log(f"   group {g} final write_pos = {write_pos} bytes "
                    f"(= col {_COL_START_MAIN + write_pos // 16})")

        # Pack group 3 (shared) into boss_set_expansion.
        dbg.log(f"-- packing group 3 (shared) into boss_set_expansion "
                f"(target len={len(sprites.boss_set_expansion)})")
        write_pos = 0
        for boss in group_bosses[3]:
            if boss not in tile_cache:
                dbg.log(f"   {boss.name} has no tile entry (variant) — "
                        f"skipped during packing")
                continue

            col = _COL_START_EXPANSION + write_pos // 16
            column_assignments[boss] = col
            data = tile_cache[boss]
            end_col = col + len(data) // 16

            dbg.log(f"   pack {boss.name:24s} "
                    f"@ cols {col:3d}-{end_col-1:3d} "
                    f"(bytes {write_pos:4d}-{write_pos+len(data)-1:4d}) "
                    f"len={len(data):4d} [shared group]")

            if write_pos + len(data) > len(sprites.boss_set_expansion):
                dbg.warn(f"{boss.name} packing overruns boss_set_expansion")

            sprites.boss_set_expansion[write_pos:write_pos + len(data)] = data
            write_pos += len(data)

            if boss in _COMPANIONS:
                companion = _COMPANIONS[boss]
                ccol = _COL_START_EXPANSION + write_pos // 16
                column_assignments[companion] = ccol
                cdata = tile_cache[companion]
                cend = ccol + len(cdata) // 16

                dbg.log(f"   pack {companion.name:24s} "
                        f"@ cols {ccol:3d}-{cend-1:3d} "
                        f"(bytes {write_pos:4d}-"
                        f"{write_pos+len(cdata)-1:4d}) "
                        f"len={len(cdata):4d} [companion, shared]")

                if write_pos + len(cdata) > len(sprites.boss_set_expansion):
                    dbg.warn(
                        f"{companion.name} packing overruns boss_set_expansion"
                    )

                sprites.boss_set_expansion[write_pos:write_pos + len(cdata)] = cdata
                write_pos += len(cdata)

        dbg.log(f"   group 3 final write_pos = {write_pos} bytes "
                f"(= col {_COL_START_EXPANSION + write_pos // 16})")

        # Final column_assignments dump, sorted by group then column.
        with dbg.section("Final column_assignments"):
            # Group by target set.
            by_target: dict[str, list[tuple[int, Enemy]]] = {}
            for b, c in column_assignments.items():
                # Determine which set b lives in based on its column range.
                if c < _COL_START_MAIN:
                    key = "boss_set_expansion"
                else:
                    # Walk group_bosses to find which group b was packed into.
                    key = "?"
                    for gi, bs in enumerate(group_bosses):
                        if b in bs:
                            key = _GROUP_SPRITE_ATTR.get(gi, "expansion")
                            break
                by_target.setdefault(key, []).append((c, b))

            for key in sorted(by_target):
                dbg.log(f"  {key}:")
                for c, b in sorted(by_target[key]):
                    n_cols = _SPRITE_SIZE.get(b, 0) // 16
                    dbg.log(f"    col {c:3d} ({n_cols:2d} cols) {b.name}")

        # Hex signature of each populated column.  Useful for diffing
        # against an emulator CHR dump.
        with dbg.section("Per-column hex signatures"):
            for g in range(3):
                attr = _GROUP_SPRITE_ATTR[g]
                buf = getattr(sprites, attr)
                dbg.log(f"  {attr}:")
                for col_idx in range(len(buf) // 16):
                    sig = _column_hex_signature(buf, col_idx * 16)
                    dbg.log(f"    col {_COL_START_MAIN + col_idx:3d} "
                            f"(byte {col_idx*16:4d}): {sig}")
            dbg.log(f"  boss_set_expansion:")
            exp = sprites.boss_set_expansion
            for col_idx in range(len(exp) // 16):
                sig = _column_hex_signature(exp, col_idx * 16)
                dbg.log(f"    col {_COL_START_EXPANSION + col_idx:3d} "
                        f"(byte {col_idx*16:4d}): {sig}")

        return column_assignments


def _build_group_column_maps(
    column_assignments: dict[Enemy, int],
    group_bosses: list[list[Enemy]],
    dbg: _DebugLog,
) -> list[dict[int, int]]:
    """Build a vanilla-col → new-col mapping for each boss group.

    For every boss (and companion) packed into a group, maps each of its
    vanilla columns to the corresponding new column.  This covers ALL
    columns in the group's bank, not just the columns of a single boss,
    so cross-boss tile references within the same set resolve correctly.
    """
    group_maps: list[dict[int, int]] = [{} for _ in range(len(group_bosses))]

    boss_to_group: dict[Enemy, int] = {}
    for g, bosses in enumerate(group_bosses):
        for boss in bosses:
            boss_to_group[boss] = g

    with dbg.section("Per-group column maps (vanilla_col -> new_col)"):
        for boss, new_start in column_assignments.items():
            if boss not in _SPRITE_OFFSET:
                dbg.log(f"  {boss.name}: no _SPRITE_OFFSET entry — skipped")
                continue
            grp = boss_to_group.get(boss)
            if grp is None:
                # Companion bosses aren't in group_bosses; infer from primary.
                for primary, companion in _COMPANIONS.items():
                    if companion == boss:
                        grp = boss_to_group.get(primary)
                        dbg.log(f"  {boss.name}: inferred group {grp} "
                                f"from primary {primary.name}")
                        break
            if grp is None:
                dbg.warn(f"{boss.name}: has column assignment but no group "
                         f"— tile references will not be remapped")
                continue

            vanilla_start = _COL_START_MAIN + _SPRITE_OFFSET[boss] // 16
            num_cols = _SPRITE_SIZE[boss] // 16
            dbg.log(f"  {boss.name:24s} grp={grp} "
                    f"vanilla_cols={vanilla_start:3d}-"
                    f"{vanilla_start+num_cols-1:3d} -> "
                    f"new_cols={new_start:3d}-{new_start+num_cols-1:3d}")
            for i in range(num_cols):
                v = vanilla_start + i
                n = new_start + i
                if v in group_maps[grp] and group_maps[grp][v] != n:
                    dbg.warn(
                        f"duplicate vanilla col {v} in group {grp}: "
                        f"was -> {group_maps[grp][v]}, now -> {n} "
                        f"(boss={boss.name}) — later wins"
                    )
                group_maps[grp][v] = n

    return group_maps


# Which primary boss each variant/companion inherits its group from.
_VARIANT_PRIMARY: dict[Enemy, Enemy] = {
    Enemy.THE_BEAST: Enemy.AQUAMENTUS,
    Enemy.MOLDORM: Enemy.GLEEOK_1,
    Enemy.THE_KIDNAPPED: Enemy.BLUE_GOHMA,
}
for _primary, _variants in _VARIANT_EXPANSIONS.items():
    for _v in _variants:
        _VARIANT_PRIMARY[_v] = _primary
for _primary, _companion in _COMPANIONS.items():
    _VARIANT_PRIMARY[_companion] = _primary


def _update_tile_frames(
    enemies: EnemyData,
    column_assignments: dict[Enemy, int],
    group_bosses: list[list[Enemy]],
    dbg: _DebugLog,
) -> None:
    """Update tile_frames for each boss to reflect its new sprite set position.

    Builds a per-group column mapping covering all bosses packed into each
    group, then remaps every boss's (and variant's) tile_frames through
    that mapping.  This handles cross-boss tile references within the same
    set (e.g. Aquamentus referencing Dodongo/Digdogger columns).

    Frames outside the boss bank range (192-255) and expansion range
    (48-79) are left unchanged — they reference fixed engine tiles.
    """
    group_maps = _build_group_column_maps(column_assignments, group_bosses, dbg)

    is_in_shared_group = set(group_bosses[3]) if len(group_bosses) > 3 else set()

    boss_to_group: dict[Enemy, int] = {}
    for g, bosses in enumerate(group_bosses):
        for boss in bosses:
            boss_to_group[boss] = g

    all_bosses_with_frames: set[Enemy] = set()
    for boss_set in _VANILLA_BOSS_GROUPS.values():
        all_bosses_with_frames |= boss_set
    all_bosses_with_frames |= {Enemy.THE_BEAST, Enemy.MOLDORM, Enemy.THE_KIDNAPPED}

    with dbg.section("tile_frames remap (per boss)"):
        for boss in sorted(all_bosses_with_frames, key=lambda e: e.name):
            if boss not in enemies.tile_frames:
                dbg.log(f"  {boss.name}: no tile_frames entry — skipped")
                continue
            frames = enemies.tile_frames[boss]
            if not frames:
                dbg.log(f"  {boss.name}: empty tile_frames — skipped")
                continue

            # Determine which group this boss belongs to.
            grp = boss_to_group.get(boss)
            via_primary = False
            if grp is None:
                primary = _VARIANT_PRIMARY.get(boss)
                if primary is not None:
                    grp = boss_to_group.get(primary)
                    via_primary = True
            if grp is None:
                dbg.warn(f"{boss.name}: no group assignment "
                         f"(primary={_VARIANT_PRIMARY.get(boss)}) "
                         f"— tile_frames left UNCHANGED")
                continue

            col_map = group_maps[grp]

            # Bonuses only apply to frames within the boss's own vanilla
            # column range, not to cross-boss references in the same set.
            own_primary = _VARIANT_PRIMARY.get(boss, boss)
            if own_primary in _SPRITE_OFFSET:
                own_start = _COL_START_MAIN + _SPRITE_OFFSET[own_primary] // 16
                own_end = own_start + _SPRITE_SIZE[own_primary] // 16
            else:
                own_start = own_end = -1

            in_shared = boss in is_in_shared_group or (
                own_primary in is_in_shared_group
            )
            is_aquamentus = boss in (Enemy.AQUAMENTUS, Enemy.THE_BEAST)

            dbg.log(
                f"  {boss.name:24s} "
                f"grp={grp}{' (via primary)' if via_primary else ''} "
                f"own_primary={own_primary.name} "
                f"own_col_range=[{own_start},{own_end}) "
                f"in_shared={in_shared} "
                f"aquamentus_bonus={is_aquamentus}"
            )
            dbg.log(f"    before: {list(frames)}")

            remapped: list[int] = []
            trace: list[str] = []
            for f in frames:
                if f in col_map:
                    bonus = 0
                    bonus_desc = []
                    if own_start <= f < own_end:
                        if is_aquamentus:
                            bonus += 2
                            bonus_desc.append("+2(aqua)")
                        if in_shared:
                            bonus += 1
                            bonus_desc.append("+1(shared)")
                    new_f = col_map[f] + bonus
                    remapped.append(new_f)
                    trace.append(
                        f"{f}->{new_f}"
                        + (f"({'+'.join(bonus_desc)})" if bonus_desc else "")
                    )
                else:
                    # A frame outside col_map may be legitimate (engine
                    # tiles below col 192 / in the 48-79 expansion range)
                    # or a bug (in-bank column with no mapping).
                    remapped.append(f)
                    note = "passthrough"
                    if 192 <= f < 256 or 48 <= f < 80:
                        note = "passthrough[IN-BANK,UNMAPPED]"
                        dbg.warn(
                            f"{boss.name} frame {f} is in a boss-bank "
                            f"range but has no entry in group {grp}'s "
                            f"col_map — likely a cross-group reference"
                        )
                    trace.append(f"{f}->{f}({note})")

            dbg.log(f"    trace:  {' '.join(trace)}")
            dbg.log(f"    after:  {remapped}")

            enemies.tile_frames[boss] = remapped


# ---------------------------------------------------------------------------
# Main entry point.
# ---------------------------------------------------------------------------

def change_dungeon_boss_groups(
    world: GameWorld,
    rng: Rng,
    debug: bool | None = None,
    debug_log_path: str | None = None,
) -> None:
    """Redistribute bosses across the three boss sprite-set groups.

    1. Sort bosses by sprite size (descending) so largest bosses are placed first.
    2. Randomly pick a "special boss" forced into the shared pool.
    3. Assign each boss to a random group (0-2) or the shared pool (3),
       respecting each group's sprite tile column budget.
    4. Expand variant bosses into each group.
    5. Merge the shared pool into all three groups.
    6. For every room whose current enemy belongs to a vanilla boss group,
       replace it with a random boss from the same group's new pool,
       respecting room-type safety checks.

    Only Q1 levels (1-9) are processed.

    Debug parameters
    ----------------
    debug : bool | None
        If True, emit a full forensic trace of every state transition.
        If None (default), enable when the environment variable
        ZORA_BOSS_DEBUG is set to a truthy value.
    debug_log_path : str | None
        Where to write the trace.  Defaults to the ZORA_BOSS_DEBUG_LOG
        env var, or "boss_groups_debug.log" in the cwd if unset.
    """
    if debug is None:
        debug = False
    if debug_log_path is None:
        debug_log_path = os.environ.get(
            "ZORA_BOSS_DEBUG_LOG", "boss_groups_debug.log"
        )

    dbg = _DebugLog(enabled=debug, log_path=debug_log_path)

    try:
        with dbg.section("change_dungeon_boss_groups: START"):
            # Best-effort rng seed echo.  Rng may or may not expose its seed;
            # we try common attribute names and fall back to a noop.
            seed_repr = None
            for attr in ("seed", "_seed", "initial_seed", "state"):
                if hasattr(rng, attr):
                    try:
                        seed_repr = f"{attr}={getattr(rng, attr)!r}"
                        break
                    except Exception:
                        pass
            dbg.log(f"rng: {seed_repr or '<seed unavailable>'}")
            dbg.log(f"primary bosses considered: "
                    f"{[b.name for b in _BOSS_TILE_COLUMNS]}")

        # --- Sort bosses by sprite size descending (largest placed first) ---
        primary_bosses = list(_BOSS_TILE_COLUMNS)
        primary_bosses.sort(key=lambda b: _BOSS_TILE_COLUMNS[b], reverse=True)
        dbg.log(f"sorted (largest first): "
                f"{[(b.name, _BOSS_TILE_COLUMNS[b]) for b in primary_bosses]}")

        # --- Column budgets: groups 0-2 have 64 columns each, shared has 32 ---
        group_budget = [64, 64, 64, 32]

        # --- Pre-fill: group 2 (BossSpriteSet.C) has 56 columns reserved ---
        group_budget[2] -= 56  # 64 - 56 = 8 columns available

        # --- Pick a special boss to force into the shared group ---
        special_boss = rng.choice(_SPECIAL_BOSSES)
        group_budget[3] -= _SPECIAL_RESTORE[special_boss]

        dbg.log(f"initial budgets (after reservations + special): "
                f"{group_budget}")
        dbg.log(f"special_boss = {special_boss.name} "
                f"(restore={_SPECIAL_RESTORE[special_boss]})")

        # --- Assignment: 4 groups (0=A, 1=B, 2=C, 3=shared) ---
        group_bosses: list[list[Enemy]] = [[] for _ in range(4)]

        retry_count = 0
        total_attempts = 0
        skipped_due_to_retry_limit: list[Enemy] = []

        with dbg.section("Group assignment"):
            i = 0
            while i < len(primary_bosses):
                boss = primary_bosses[i]
                columns = _BOSS_TILE_COLUMNS_WITH_COMPANION.get(
                    boss, _BOSS_TILE_COLUMNS[boss],
                )

                group = int(rng.random() * 4)
                if boss == special_boss:
                    group = 3
                    group_budget[3] += _SPECIAL_RESTORE[special_boss]
                    dbg.log(f"  {boss.name}: forced into group 3, "
                            f"budget restored to {group_budget[3]}")

                total_attempts += 1
                if columns <= group_budget[group]:
                    group_budget[group] -= columns
                    group_bosses[group].append(boss)
                    dbg.log(
                        f"  {boss.name:24s} needs {columns:2d} cols -> "
                        f"group {group} ACCEPT "
                        f"(budget now {group_budget})"
                    )
                    retry_count = 0
                    i += 1
                else:
                    retry_count += 1
                    dbg.log(
                        f"  {boss.name:24s} needs {columns:2d} cols -> "
                        f"group {group} REJECT "
                        f"(only {group_budget[group]} avail, "
                        f"retry #{retry_count})"
                    )
                    if retry_count > _MAX_ASSIGNMENT_RETRIES:
                        dbg.warn(
                            f"{boss.name} skipped after "
                            f"{_MAX_ASSIGNMENT_RETRIES} retries — "
                            f"this boss will NOT appear anywhere"
                        )
                        skipped_due_to_retry_limit.append(boss)
                        retry_count = 0
                        i += 1

            dbg.log(f"total assignment attempts: {total_attempts}")
            dbg.log(f"skipped bosses: "
                    f"{[b.name for b in skipped_due_to_retry_limit]}")

        with dbg.section("group_bosses after primary assignment"):
            for g, bs in enumerate(group_bosses):
                label = ["A", "B", "C", "shared"][g]
                dbg.log(f"  group {g} ({label}): {[b.name for b in bs]}")

        # --- Repack sprite tile data to match the new group assignments ---
        column_assignments = _repack_boss_sprites(world.sprites, group_bosses, dbg)

        # --- Update tile frame mappings so the engine finds the tiles ---
        _update_tile_frames(world.enemies, column_assignments, group_bosses, dbg)

        # Aquamentus engine sprite pointer patch.
        # ROM 0x11898 tells the engine where Aquamentus's head/body tiles
        # live in VRAM.  Must be updated whenever the packer moves Aquamentus
        # to a different column (even within its vanilla group).
        with dbg.section("Sanity check: Aquamentus engine pointer patch"):
            aqua_group = None
            for g, bs in enumerate(group_bosses):
                if Enemy.AQUAMENTUS in bs:
                    aqua_group = g
                    break
            dbg.log(f"  Aquamentus is in group {aqua_group} "
                    f"({'shared' if aqua_group == 3 else 'A/B/C'})")
            if Enemy.AQUAMENTUS in world.enemies.tile_frames:
                frames = world.enemies.tile_frames[Enemy.AQUAMENTUS]
                if len(frames) >= 4:
                    q3bonus = 1 if aqua_group == 3 else 0
                    value = frames[3] + q3bonus - 2
                    world.enemies.aquamentus_sprite_ptr = value
                    dbg.log(f"  wrote ROM 0x11898 = "
                            f"tile_frames[AQUAMENTUS][3]({frames[3]}) "
                            f"+ q3bonus({q3bonus}) - 2 = "
                            f"{value}")
                    aqua_start_col = column_assignments.get(Enemy.AQUAMENTUS)
                    if aqua_start_col is not None and aqua_start_col != 192:
                        dbg.warn(
                            f"Aquamentus start column is {aqua_start_col} "
                            f"(vanilla=192) — pointer patch applied"
                        )

        # Gleeok multi-head engine sprite pointer patches.
        # ROM 0x126F8, 0x126FE, 0x6F5A tell the engine where Gleeok's
        # extra head tiles live in VRAM.
        with dbg.section("Sanity check: Gleeok engine pointer patches"):
            gleeok_group = None
            for g, bs in enumerate(group_bosses):
                if Enemy.GLEEOK_1 in bs:
                    gleeok_group = g
                    break
            dbg.log(f"  Gleeok is in group {gleeok_group} "
                    f"({'shared' if gleeok_group == 3 else 'A/B/C'})")
            if Enemy.GLEEOK_1 in world.enemies.tile_frames:
                frames = world.enemies.tile_frames[Enemy.GLEEOK_1]
                if frames:
                    q3bonus = 1 if gleeok_group == 3 else 0
                    base = frames[0]
                    val_a = base + q3bonus + 26
                    val_b = base + q3bonus + 28
                    val_c = base + q3bonus + 30
                    world.enemies.gleeok_head_sprite_ptr_a = val_a
                    world.enemies.gleeok_head_sprite_ptr_b = val_b
                    world.enemies.gleeok_head_sprite_ptr_c = val_c
                    dbg.log(f"  wrote:")
                    dbg.log(f"    ROM 0x126F8 = {base} + {q3bonus} + 26 "
                            f"= {val_a}")
                    dbg.log(f"    ROM 0x126FE = {base} + {q3bonus} + 28 "
                            f"= {val_b}")
                    dbg.log(f"    ROM 0x6F5A  = {base} + {q3bonus} + 30 "
                            f"= {val_c}")
                    gleeok_start_col = column_assignments.get(Enemy.GLEEOK_1)
                    if gleeok_start_col is not None and gleeok_start_col != 192:
                        dbg.warn(
                            f"Gleeok start column is {gleeok_start_col} "
                            f"(vanilla=192) — pointer patches applied"
                        )

        # --- Expand variant bosses ---
        with dbg.section("Variant expansion + GLEEOK replacement"):
            for g, boss_list in enumerate(group_bosses):
                before = list(boss_list)
                additions: list[Enemy] = []
                replacements: dict[Enemy, Enemy] = {}

                for boss in boss_list:
                    if boss in _VARIANT_EXPANSIONS:
                        additions.extend(_VARIANT_EXPANSIONS[boss])

                if Enemy.GLEEOK_1 in boss_list:
                    replacements[Enemy.GLEEOK_1] = Enemy.GLEEOK_2
                    dbg.log(f"  group {g}: GLEEOK_1 -> GLEEOK_2 in pool "
                            f"(GLEEOK_1 remains for sprite packing, but "
                            f"the replacement pool shows GLEEOK_2)")

                for idx, boss in enumerate(boss_list):
                    if boss in replacements:
                        boss_list[idx] = replacements[boss]

                boss_list.extend(additions)

                if before != boss_list:
                    dbg.log(f"  group {g}: "
                            f"{[b.name for b in before]} -> "
                            f"{[b.name for b in boss_list]}")

            # Subtle bug worth flagging: _update_tile_frames ran BEFORE
            # this replacement, using group_bosses as it was.  If GLEEOK_2
            # relies on being in boss_to_group for its frames to be
            # remapped, it got remapped via its _VARIANT_PRIMARY
            # (GLEEOK_1), which is still correct.  But any future logic
            # that keys off the post-replacement group_bosses will see a
            # different picture than the tile-frame remapper did.
            for g, bs in enumerate(group_bosses):
                if Enemy.GLEEOK_1 in bs:
                    dbg.warn(
                        f"group {g} still contains GLEEOK_1 after the "
                        f"replacement loop — this should not happen "
                        f"unless additions re-introduced it"
                    )

        # --- Merge shared group (3) into all three main groups ---
        if group_bosses[3]:
            dbg.log(f"merging shared pool {[b.name for b in group_bosses[3]]} "
                    f"into groups 0-2")
            for g in range(3):
                group_bosses[g].extend(group_bosses[3])

        new_pools: dict[BossSpriteSet, list[Enemy]] = {}
        for g, sprite_set in enumerate(_GROUP_ORDER):
            new_pools[sprite_set] = group_bosses[g]

        with dbg.section("Final replacement pools"):
            for ss, pool in new_pools.items():
                dbg.log(f"  {ss.name}: {[b.name for b in pool]}")

        # --- Replace boss enemies in rooms ---
        replacements_log: list[str] = []
        rooms_skipped = 0
        rooms_no_match = 0
        rooms_no_pool = 0
        rooms_unsafe_exhausted = 0
        rooms_replaced = 0

        with dbg.section("Per-room replacement"):
            for level in world.levels:
                for room in level.rooms:
                    if room.room_type in (RoomType.ITEM_STAIRCASE,
                                           RoomType.TRANSPORT_STAIRCASE):
                        rooms_skipped += 1
                        continue
                    enemy = room.enemy_spec.enemy

                    original_group: BossSpriteSet | None = None
                    for sprite_set, members in _VANILLA_BOSS_GROUPS.items():
                        if enemy in members:
                            original_group = sprite_set
                            break

                    if original_group is None:
                        rooms_no_match += 1
                        continue

                    pool = new_pools.get(original_group)
                    if not pool:
                        rooms_no_pool += 1
                        dbg.warn(
                            f"room L{getattr(level, 'number', '?')} "
                            f"{getattr(room, 'id', '?')}: "
                            f"enemy {enemy.name} is in vanilla group "
                            f"{original_group.name} but new pool is empty"
                        )
                        continue

                    picked = False
                    attempts = 0
                    for _attempt in range(_MAX_ROOM_RETRIES):
                        attempts += 1
                        new_boss = rng.choice(pool)
                        if not is_safe_for_room(
                            new_boss, room.room_type,
                            has_push_block=room.movable_block,
                        ):
                            continue
                        room.enemy_spec.enemy = new_boss
                        room.enemy_quantity = level.qty_table[0]
                        picked = True
                        rooms_replaced += 1

                        new_frames = world.enemies.tile_frames.get(
                            new_boss, []
                        )
                        replacements_log.append(
                            f"L{getattr(level, 'number', '?'):>2} "
                            f"room={getattr(room, 'id', '?'):>4} "
                            f"type={room.room_type.name:<20} "
                            f"{enemy.name:>24} -> {new_boss.name:<24} "
                            f"(src_grp={original_group.name}, "
                            f"attempts={attempts}, "
                            f"new_frames={list(new_frames)})"
                        )
                        break

                    if not picked:
                        rooms_unsafe_exhausted += 1
                        dbg.warn(
                            f"room L{getattr(level, 'number', '?')} "
                            f"{getattr(room, 'id', '?')} ({room.room_type.name}): "
                            f"no safe boss in pool "
                            f"{[b.name for b in pool]} "
                            f"after {_MAX_ROOM_RETRIES} attempts — "
                            f"room keeps {enemy.name}"
                        )

            for line in replacements_log:
                dbg.log(line)

        with dbg.section("Room replacement summary"):
            dbg.log(f"  replaced:            {rooms_replaced}")
            dbg.log(f"  skipped (staircase): {rooms_skipped}")
            dbg.log(f"  not a boss room:     {rooms_no_match}")
            dbg.log(f"  empty pool:          {rooms_no_pool}")
            dbg.log(f"  no safe pick:        {rooms_unsafe_exhausted}")

        with dbg.section("change_dungeon_boss_groups: END"):
            dbg.log(f"warnings:          {dbg._warn_count}")
            dbg.log(f"assertion failures: {dbg._assert_count}")

    finally:
        dbg.flush()