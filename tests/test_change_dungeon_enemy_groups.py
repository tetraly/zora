"""
Tests for change_dungeon_enemy_groups.

Uses a real GameWorld parsed from vanilla ROM bin files to verify that the
enemy group shuffler runs correctly and maintains structural invariants.

Run with:
    python3 -m pytest zora/enemy/test_change_dungeon_enemy_groups.py -v
    or: python3 -m pytest zora/enemy/test_change_dungeon_enemy_groups.py -v -x
"""

import copy
import signal
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from zora.parser import load_bin_files, parse_game_world
from zora.rng import SeededRng
from zora.data_model import Enemy, RoomType
from zora.enemy.change_dungeon_enemy_groups import (
    change_dungeon_enemy_groups,
    _VANILLA_ENEMY_GROUPS,
    _COMPANION_EXPANSIONS,
    _BAD_FOR_WIZZROBE_SCREENS,
    _ENEMY_TILE_COLUMNS,
    _TILE_FRAME_COUNT,
    _STAT_OFFSETS,
    _GROUP_SPRITE_ATTR,
    _SPRITE_BANK_BASES,
    _read_enemy_tiles,
)
from zora.data_model import EnemySpriteSet

BIN_DIR = Path(__file__).resolve().parents[1] / 'rom_data'
TIMEOUT = 30


def _timeout_handler(signum, frame):
    raise TimeoutError("test exceeded timeout")


def _load_game_world():
    bins = load_bin_files(BIN_DIR)
    return parse_game_world(bins)


def _all_shuffleable_ids():
    """Enemy IDs that appear in _VANILLA_ENEMY_GROUPS (candidates for replacement)."""
    ids = set()
    for group in _VANILLA_ENEMY_GROUPS.values():
        ids.update(e.value for e in group)
    return ids


def _snapshot_rooms(gw):
    """Capture (level_index, room_index) -> Enemy before shuffling."""
    snap = {}
    for li, level in enumerate(gw.levels):
        for ri, room in enumerate(level.rooms):
            snap[(li, ri)] = room.enemy_spec.enemy
    return snap


def _snapshot_overworld(gw):
    snap = {}
    for si, screen in enumerate(gw.overworld.screens):
        snap[si] = screen.enemy_spec.enemy
    return snap


class TestChangeDungeonEnemyGroups(unittest.TestCase):

    def setUp(self):
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(TIMEOUT)

    def tearDown(self):
        signal.alarm(0)

    # ------------------------------------------------------------------
    # Basic: runs without crashing across multiple seeds
    # ------------------------------------------------------------------

    def test_runs_without_error_multiple_seeds(self):
        for seed in [1, 42, 100, 999, 12345, 99999]:
            with self.subTest(seed=seed):
                gw = _load_game_world()
                change_dungeon_enemy_groups(gw, SeededRng(seed))

    def test_runs_with_overworld_multiple_seeds(self):
        for seed in [1, 42, 100, 999, 12345]:
            with self.subTest(seed=seed):
                gw = _load_game_world()
                change_dungeon_enemy_groups(gw, SeededRng(seed), overworld=True)

    def test_runs_with_include_level_9(self):
        for seed in [42, 999]:
            with self.subTest(seed=seed):
                gw = _load_game_world()
                change_dungeon_enemy_groups(gw, SeededRng(seed))

    # ------------------------------------------------------------------
    # Sprite banks are modified
    # ------------------------------------------------------------------

    def test_sprite_banks_modified(self):
        gw = _load_game_world()
        orig_a = bytes(gw.sprites.enemy_set_a)
        orig_b = bytes(gw.sprites.enemy_set_b)
        orig_c = bytes(gw.sprites.enemy_set_c)
        change_dungeon_enemy_groups(gw, SeededRng(42))
        # At least one sprite bank should have changed
        changed = (
            gw.sprites.enemy_set_a != orig_a
            or gw.sprites.enemy_set_b != orig_b
            or gw.sprites.enemy_set_c != orig_c
        )
        self.assertTrue(changed, "No sprite banks were modified")

    # ------------------------------------------------------------------
    # Dungeon room enemy replacements
    # ------------------------------------------------------------------

    def test_some_dungeon_rooms_changed(self):
        gw = _load_game_world()
        orig_rooms = _snapshot_rooms(gw)
        change_dungeon_enemy_groups(gw, SeededRng(42))

        shuffleable = _all_shuffleable_ids()
        changed = 0
        eligible = 0
        for li, level in enumerate(gw.levels):
            for ri, room in enumerate(level.rooms):
                orig = orig_rooms[(li, ri)]
                if orig.value < 0x40 and (orig.value & 0x3F) in shuffleable:
                    if room.room_type not in (
                        RoomType.ITEM_STAIRCASE,
                        RoomType.TRANSPORT_STAIRCASE,
                    ):
                        eligible += 1
                        if room.enemy_spec.enemy != orig:
                            changed += 1

        self.assertGreater(eligible, 0, "No eligible rooms found in vanilla data")
        self.assertGreater(changed, 0, "No rooms were changed")

    def test_boss_rooms_untouched(self):
        gw = _load_game_world()
        orig_rooms = _snapshot_rooms(gw)
        change_dungeon_enemy_groups(gw, SeededRng(42))

        for li, level in enumerate(gw.levels):
            for ri, room in enumerate(level.rooms):
                orig = orig_rooms[(li, ri)]
                if orig.value >= 0x40 or orig.is_boss:
                    self.assertEqual(
                        room.enemy_spec.enemy, orig,
                        f"Boss room changed: L{li+1} room {room.room_num}: "
                        f"{orig.name} -> {room.enemy_spec.enemy.name}",
                    )

    def test_special_rooms_untouched(self):
        gw = _load_game_world()
        orig_rooms = _snapshot_rooms(gw)
        change_dungeon_enemy_groups(gw, SeededRng(42))

        for li, level in enumerate(gw.levels):
            for ri, room in enumerate(level.rooms):
                if room.room_type in (
                    RoomType.ITEM_STAIRCASE,
                    RoomType.TRANSPORT_STAIRCASE,
                ):
                    self.assertEqual(
                        room.enemy_spec.enemy, orig_rooms[(li, ri)],
                        f"Special room changed: L{li+1} room {room.room_num}",
                    )

    # ------------------------------------------------------------------
    # Determinism: same seed -> same result
    # ------------------------------------------------------------------

    def test_deterministic(self):
        gw1 = _load_game_world()
        gw2 = _load_game_world()
        change_dungeon_enemy_groups(gw1, SeededRng(42))
        change_dungeon_enemy_groups(gw2, SeededRng(42))

        for li in range(len(gw1.levels)):
            for ri in range(len(gw1.levels[li].rooms)):
                e1 = gw1.levels[li].rooms[ri].enemy_spec.enemy
                e2 = gw2.levels[li].rooms[ri].enemy_spec.enemy
                self.assertEqual(e1, e2, f"Non-deterministic: L{li+1} room {ri}")

        self.assertEqual(
            bytes(gw1.sprites.enemy_set_a),
            bytes(gw2.sprites.enemy_set_a),
        )

    def test_different_seeds_differ(self):
        gw1 = _load_game_world()
        gw2 = _load_game_world()
        change_dungeon_enemy_groups(gw1, SeededRng(1))
        change_dungeon_enemy_groups(gw2, SeededRng(9999))

        any_diff = False
        for li in range(len(gw1.levels)):
            for ri in range(len(gw1.levels[li].rooms)):
                if gw1.levels[li].rooms[ri].enemy_spec.enemy != gw2.levels[li].rooms[ri].enemy_spec.enemy:
                    any_diff = True
                    break
            if any_diff:
                break
        self.assertTrue(any_diff, "Two different seeds produced identical results")

    # ------------------------------------------------------------------
    # Overworld-specific invariants
    # ------------------------------------------------------------------

    def test_overworld_no_wizzrobe_on_banned_screens(self):
        gw = _load_game_world()
        change_dungeon_enemy_groups(gw, SeededRng(42), overworld=True)

        wizzrobe_ids = {Enemy.RED_WIZZROBE.value, Enemy.BLUE_WIZZROBE.value}
        for screen in gw.overworld.screens:
            if screen.screen_num in _BAD_FOR_WIZZROBE_SCREENS:
                self.assertNotIn(
                    screen.enemy_spec.enemy.value, wizzrobe_ids,
                    f"Wizzrobe on banned screen {screen.screen_num}",
                )


    # ------------------------------------------------------------------
    # Group constraint validation
    # ------------------------------------------------------------------

    def _get_cave_groups(self, gw):
        """Get cave_groups as a dict mapping group index to set of enemy IDs.

        Reads from the typed cave_groups dict on EnemyData and converts
        to {int: set[int]} for easy constraint checking.
        """
        set_to_idx = {
            EnemySpriteSet.A: 0, EnemySpriteSet.B: 1,
            EnemySpriteSet.C: 2, EnemySpriteSet.OW: 3,
        }
        return {
            set_to_idx[ss]: {e.value for e in enemies}
            for ss, enemies in gw.enemies.cave_groups.items()
        }

    def test_group_lanmola_wallmaster_mutual_exclusion(self):
        """RED_LANMOLA (0x3A) and WALLMASTER (0x27) must never be in the same group."""
        for seed in [1, 42, 100, 999, 12345, 99999]:
            with self.subTest(seed=seed):
                gw = _load_game_world()
                change_dungeon_enemy_groups(gw, SeededRng(seed))
                groups = self._get_cave_groups(gw)
                for g, members in groups.items():
                    self.assertFalse(
                        58 in members and 39 in members,
                        f"Seed {seed}, group {g}: enemies 58 and 39 "
                        f"both assigned (mutual exclusion violated)",
                    )

    def test_group_capacity_within_budget(self):
        """Each group's total tile column budget must not exceed 34."""
        # Build enemy_id -> column count lookup from the constants
        id_to_columns = {e.value: cols for e, cols in _ENEMY_TILE_COLUMNS.items()}
        for seed in [1, 42, 100, 999, 12345]:
            with self.subTest(seed=seed):
                gw = _load_game_world()
                change_dungeon_enemy_groups(gw, SeededRng(seed))
                groups = self._get_cave_groups(gw)
                for g, members in groups.items():
                    total = sum(
                        id_to_columns.get(eid, 0) for eid in members
                    )
                    # Budget is 34; companion expansion adds IDs not in
                    # the budget table, so we only sum IDs present.
                    self.assertLessEqual(
                        total, 34,
                        f"Seed {seed}, group {g}: capacity {total} > 34",
                    )

    def test_wizzrobe_compat_coverage(self):
        """Every group must contain at least one wizzrobe-compatible enemy."""
        wizzrobe_compat_base = {6, 11, 48, 35, 1, 3, 7}
        # Enemy 18 may also be compat depending on ZOL HP, but since we're
        # testing vanilla ROM where ZOL HP is likely <= 4, include it.
        # The real check: at least one member of each group is in the
        # wizzrobe compat list (possibly with 18).
        for seed in [1, 42, 100, 999, 12345]:
            with self.subTest(seed=seed):
                gw = _load_game_world()
                wizzrobe_compat = set(wizzrobe_compat_base)
                zol_hp = gw.enemies.hp.get(Enemy.ZOL, 0) if hasattr(Enemy, 'ZOL') else 99
                if zol_hp <= 4:
                    wizzrobe_compat.add(18)
                change_dungeon_enemy_groups(gw, SeededRng(seed))
                groups = self._get_cave_groups(gw)
                for g, members in groups.items():
                    has_compat = bool(members & wizzrobe_compat)
                    self.assertTrue(
                        has_compat,
                        f"Seed {seed}, group {g}: no wizzrobe-compatible "
                        f"enemy. Members: {members}",
                    )

    def test_overworld_banned_enemies_not_in_group_3(self):
        """Enemies {58, 39, 18, 19, 23} must not be in group 3 (overworld)."""
        banned_in_ow = {58, 39, 18, 19, 23}
        for seed in [1, 42, 100, 999]:
            with self.subTest(seed=seed):
                gw = _load_game_world()
                change_dungeon_enemy_groups(gw, SeededRng(seed), overworld=True)
                groups = self._get_cave_groups(gw)
                if 3 in groups:
                    violators = groups[3] & banned_in_ow
                    self.assertFalse(
                        violators,
                        f"Seed {seed}: banned enemies {violators} in "
                        f"overworld group 3",
                    )

    def test_companion_expansion(self):
        """When a primary enemy is in a group, its companion must be too."""
        for seed in [1, 42, 100, 999]:
            with self.subTest(seed=seed):
                gw = _load_game_world()
                change_dungeon_enemy_groups(gw, SeededRng(seed))
                groups = self._get_cave_groups(gw)
                for g, members in groups.items():
                    for primary, companion in _COMPANION_EXPANSIONS.items():
                        if primary.value in members:
                            self.assertIn(
                                companion.value, members,
                                f"Seed {seed}, group {g}: primary {primary.name} "
                                f"present but companion {companion.name} missing",
                            )

    # ------------------------------------------------------------------
    # Tile frame cross-verification
    # ------------------------------------------------------------------

    def test_tile_frames_point_to_valid_bank_slots(self):
        """After shuffling, each assigned enemy's tile_frames values must
        fall within the valid slot range (158-255) for its sprite bank.

        Enemy 39 (WALLMASTER) is excluded: it has special-case sprite writes
        and its tile frames are not updated by the normal obj45 writeback
        (the writeback explicitly skips eid==39). Its vanilla frame values
        may be outside the 158-255 range.
        """
        # Safe enemy IDs that go through the normal obj45 path (exclude 39/WALLMASTER)
        normal_safe_ids = {
            e.value for e in _ENEMY_TILE_COLUMNS if e != Enemy.WALLMASTER
        }
        for seed in [42, 999, 12345]:
            with self.subTest(seed=seed):
                gw = _load_game_world()
                change_dungeon_enemy_groups(gw, SeededRng(seed))

                for sprite_set, enemies in gw.enemies.cave_groups.items():
                    for enemy in enemies:
                        if enemy.value not in normal_safe_ids:
                            continue
                        frames = gw.enemies.tile_frames.get(enemy)
                        if frames is None or len(frames) == 0:
                            continue
                        for i, slot in enumerate(frames):
                            if slot == 0:
                                continue
                            self.assertGreaterEqual(
                                slot, 158,
                                f"Seed {seed}, {enemy.name} frame[{i}]={slot} "
                                f"below bank region (158)",
                            )
                            self.assertLess(
                                slot, 256,
                                f"Seed {seed}, {enemy.name} frame[{i}]={slot} "
                                f"outside bank region (<256)",
                            )

    def test_sprite_data_matches_source_at_tile_frame_slots(self):
        """For each shuffled enemy, the sprite tile data at its tile_frame
        slots in the destination bank must match one of the enemy's source
        CHR tiles (from obj10).

        This is the cross-verification test recommended in ENEMY_GROUP_SHUFFLE.md.
        It verifies that tile frame redirects and sprite bank writes are
        consistent — each slot the engine will read for this enemy actually
        contains valid sprite data from that enemy's source tiles.

        The shuffler normalizes frame indices (subtract min, add pos_base),
        so frame[fi] does NOT necessarily map to source tile fi. Instead we
        verify that the 16-byte CHR tile at each referenced bank slot matches
        *some* tile from the enemy's source data.
        """
        for seed in [42, 999, 12345]:
            with self.subTest(seed=seed):
                gw_vanilla = _load_game_world()
                gw = _load_game_world()
                change_dungeon_enemy_groups(gw, SeededRng(seed))

                for sprite_set, enemies in gw.enemies.cave_groups.items():
                    bank_attr = _GROUP_SPRITE_ATTR.get(sprite_set)
                    if bank_attr is None:
                        continue
                    bank = getattr(gw.sprites, bank_attr)

                    for enemy in enemies:
                        if enemy not in _ENEMY_TILE_COLUMNS:
                            continue
                        # Skip enemies with 0 tile frame entries
                        if _TILE_FRAME_COUNT.get(enemy, 0) == 0:
                            continue
                        # Skip Wallmaster — special-case writes
                        if enemy == Enemy.WALLMASTER:
                            continue

                        frames = gw.enemies.tile_frames.get(enemy)
                        if frames is None or len(frames) == 0:
                            continue

                        # Build the set of all 16-byte source tiles for this enemy
                        src_data = _read_enemy_tiles(gw_vanilla.sprites, enemy)
                        num_src_tiles = len(src_data) // 16
                        src_tiles = set()
                        for t in range(num_src_tiles):
                            tile = tuple(src_data[t * 16:(t + 1) * 16])
                            src_tiles.add(tile)

                        if not src_tiles:
                            continue

                        # Verify each referenced slot contains a known source tile
                        for fi, slot in enumerate(frames):
                            if slot == 0 or slot < 158 or slot >= 256:
                                continue
                            bank_offset = (slot - 158) * 16
                            if bank_offset + 16 > len(bank):
                                continue
                            bank_tile = tuple(bank[bank_offset:bank_offset + 16])
                            self.assertIn(
                                bank_tile, src_tiles,
                                f"Seed {seed}, {enemy.name}: "
                                f"frame[{fi}] slot {slot} (bank offset "
                                f"{bank_offset}) contains data not matching any "
                                f"source tile in {bank_attr}",
                            )


if __name__ == '__main__':
    unittest.main()
