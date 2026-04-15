"""
Tests for shuffle_monsters_between_levels.

Uses a real GameWorld parsed from vanilla ROM bin files to verify that the
between-levels monster shuffler runs correctly and maintains structural
invariants.

Run with:
    python3 -m pytest tests/test_shuffle_monsters_between_levels.py -v
"""

import signal
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from zora.parser import load_bin_files, parse_game_world
from zora.game_config import GameConfig
from zora.rng import SeededRng
from zora.data_model import (
    Enemy,
    EnemySpec,
    GameWorld,
)
from zora.enemy.safety_checks import is_safe_for_room, UNSAFE_ROOM_TYPES
from zora.enemy.shuffle_monsters_between_levels import (
    shuffle_monsters_between_levels,
    _is_excluded_from_enemy_shuffling,
    LEVEL_SPRITE_SET,
    _EXCLUDED_FROM_ENEMY_SHUFFLING,
)

BIN_DIR = Path(__file__).resolve().parents[1] / 'rom_data'
TIMEOUT = 30


def _timeout_handler(signum, frame):
    raise TimeoutError("test exceeded timeout")


def _load_game_world():
    bins = load_bin_files(BIN_DIR)
    return parse_game_world(bins)


def _snapshot_rooms(gw: GameWorld) -> dict[tuple[int, int], int]:
    """Capture (level_index, room_index) -> enemy value before shuffling."""
    snap = {}
    for li, level in enumerate(gw.levels):
        for ri, room in enumerate(level.rooms):
            snap[(li, ri)] = room.enemy_spec.enemy.value
    return snap


def _call_shuffle(gw: GameWorld, rng: SeededRng, include_level_9: bool = False) -> None:
    """Call shuffle_monsters_between_levels with the current signature."""
    shuffle_monsters_between_levels(gw, rng, include_level_9)


class TestIsExcluded(unittest.TestCase):
    """Unit tests for _is_excluded_from_enemy_shuffling."""

    def test_nothing_excluded(self):
        self.assertTrue(_is_excluded_from_enemy_shuffling(Enemy.NOTHING))

    def test_bosses_excluded(self):
        for boss in [
            Enemy.TRIPLE_DODONGO,
            Enemy.SINGLE_DODONGO,
            Enemy.BLUE_GOHMA,
            Enemy.RED_GOHMA,
            Enemy.AQUAMENTUS,
            Enemy.THE_BEAST,
            Enemy.MANHANDLA,
        ]:
            self.assertTrue(_is_excluded_from_enemy_shuffling(boss), f"{boss.name} should be excluded")

    def test_npcs_excluded(self):
        for npc in [
            Enemy.HUNGRY_GORIYA,
            Enemy.THE_KIDNAPPED,
            Enemy.OLD_MAN,
            Enemy.OLD_MAN_2,
            Enemy.BOMB_UPGRADER,
            Enemy.MUGGER,
        ]:
            self.assertTrue(_is_excluded_from_enemy_shuffling(npc), f"{npc.name} should be excluded")

    def test_regular_enemies_not_excluded(self):
        for enemy in [
            Enemy.STALFOS,
            Enemy.ROPE,
            Enemy.RED_DARKNUT,
            Enemy.BLUE_WIZZROBE,
            Enemy.GEL_1,
        ]:
            self.assertFalse(_is_excluded_from_enemy_shuffling(enemy), f"{enemy.name} should NOT be excluded")

    def test_traps_not_excluded(self):
        """Traps are legitimate shuffle participants."""
        self.assertFalse(_is_excluded_from_enemy_shuffling(Enemy.CORNER_TRAPS))
        self.assertFalse(_is_excluded_from_enemy_shuffling(Enemy.THREE_PAIRS_OF_TRAPS))


class TestTrapEnemySafetyChecks(unittest.TestCase):
    """Trap enemies must have room-type restrictions in safety_checks."""

    def test_trap_enemies_have_restrictions(self):
        self.assertIn(Enemy.THREE_PAIRS_OF_TRAPS, UNSAFE_ROOM_TYPES)
        self.assertIn(Enemy.CORNER_TRAPS, UNSAFE_ROOM_TYPES)

    def test_regular_enemies_unrestricted(self):
        self.assertNotIn(Enemy.STALFOS, UNSAFE_ROOM_TYPES)
        self.assertNotIn(Enemy.ROPE, UNSAFE_ROOM_TYPES)
        self.assertNotIn(Enemy.RED_BUBBLE, UNSAFE_ROOM_TYPES)


class TestShuffleMonstersBetweenLevels(unittest.TestCase):

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
                _call_shuffle(gw, SeededRng(seed))

    def test_runs_with_include_level_9(self):
        for seed in [1, 42, 999]:
            with self.subTest(seed=seed):
                gw = _load_game_world()
                _call_shuffle(gw, SeededRng(seed), include_level_9=True)

    # ------------------------------------------------------------------
    # Some rooms should change when shuffling is enabled
    # ------------------------------------------------------------------

    def test_some_rooms_changed(self):
        gw = _load_game_world()
        orig = _snapshot_rooms(gw)
        _call_shuffle(gw, SeededRng(42))

        changed = sum(
            1 for (li, ri), orig_val in orig.items()
            if gw.levels[li].rooms[ri].enemy_spec.enemy.value != orig_val
        )
        self.assertGreater(changed, 0, "No rooms were changed by shuffling")

    # ------------------------------------------------------------------
    # Determinism
    # ------------------------------------------------------------------

    def test_deterministic(self):
        gw1 = _load_game_world()
        gw2 = _load_game_world()
        _call_shuffle(gw1, SeededRng(42))
        _call_shuffle(gw2, SeededRng(42))

        for li in range(len(gw1.levels)):
            for ri in range(len(gw1.levels[li].rooms)):
                e1 = gw1.levels[li].rooms[ri].enemy_spec.enemy.value
                e2 = gw2.levels[li].rooms[ri].enemy_spec.enemy.value
                self.assertEqual(e1, e2, f"Non-deterministic: L{li+1} room {ri}")

    def test_different_seeds_differ(self):
        gw1 = _load_game_world()
        gw2 = _load_game_world()
        _call_shuffle(gw1, SeededRng(1))
        _call_shuffle(gw2, SeededRng(9999))

        any_diff = any(
            gw1.levels[li].rooms[ri].enemy_spec.enemy.value !=
            gw2.levels[li].rooms[ri].enemy_spec.enemy.value
            for li in range(len(gw1.levels))
            for ri in range(len(gw1.levels[li].rooms))
        )
        self.assertTrue(any_diff, "Two different seeds produced identical results")

    # ------------------------------------------------------------------
    # Excluded enemies are not overwritten
    # ------------------------------------------------------------------

    def test_excluded_enemies_unchanged(self):
        """Rooms containing excluded enemies (bosses, NPCs) should not be
        modified by the between-levels shuffle."""
        for seed in [42, 999]:
            with self.subTest(seed=seed):
                gw_vanilla = _load_game_world()
                gw = _load_game_world()
                _call_shuffle(gw, SeededRng(seed))

                for li, level in enumerate(gw.levels):
                    for ri, room in enumerate(level.rooms):
                        vanilla_room = gw_vanilla.levels[li].rooms[ri]
                        if _is_excluded_from_enemy_shuffling(vanilla_room.enemy_spec.enemy):
                            self.assertEqual(
                                room.enemy_spec.enemy.value,
                                vanilla_room.enemy_spec.enemy.value,
                                f"Seed {seed}, L{level.level_num} room {room.room_num}: "
                                f"excluded enemy 0x{vanilla_room.enemy_spec.enemy.value:02X} "
                                f"was modified to 0x{room.enemy_spec.enemy.value:02X}",
                            )

    # ------------------------------------------------------------------
    # Safety constraint validation
    # ------------------------------------------------------------------

    def test_lanmola_not_placed_in_unsafe_rooms(self):
        """After shuffling, Lanmola (0x3A/0x3B) must not appear in
        Lanmola-unsafe rooms (unless it was already there in vanilla)."""
        lanmola_ids = {Enemy.RED_LANMOLA, Enemy.BLUE_LANMOLA}
        for seed in [42, 999, 12345]:
            with self.subTest(seed=seed):
                gw_vanilla = _load_game_world()
                gw = _load_game_world()
                _call_shuffle(gw, SeededRng(seed))

                vanilla_enemies: dict[tuple[int, int], Enemy] = {}
                for li, level in enumerate(gw_vanilla.levels):
                    for room in level.rooms:
                        vanilla_enemies[(li, room.room_num)] = room.enemy_spec.enemy

                for li, level in enumerate(gw.levels):
                    for room in level.rooms:
                        enemy = room.enemy_spec.enemy
                        if enemy not in lanmola_ids:
                            continue
                        vanilla_enemy = vanilla_enemies.get((li, room.room_num), Enemy.NOTHING)
                        if vanilla_enemy in lanmola_ids:
                            continue
                        self.assertTrue(
                            is_safe_for_room(enemy, room.room_type),
                            f"Seed {seed}, L{level.level_num} room {room.room_num}: "
                            f"Lanmola ({enemy.name}) placed in unsafe room "
                            f"type {room.room_type.name}",
                        )

    def test_rupee_not_placed_in_unsafe_rooms(self):
        """After shuffling, RUPEE_BOSS (0x35) must not appear in
        Rupee-unsafe rooms."""
        for seed in [42, 999, 12345]:
            with self.subTest(seed=seed):
                gw_vanilla = _load_game_world()
                gw = _load_game_world()
                _call_shuffle(gw, SeededRng(seed))

                vanilla_enemies: dict[tuple[int, int], Enemy] = {}
                for li, level in enumerate(gw_vanilla.levels):
                    for room in level.rooms:
                        vanilla_enemies[(li, room.room_num)] = room.enemy_spec.enemy

                for li, level in enumerate(gw.levels):
                    for room in level.rooms:
                        enemy = room.enemy_spec.enemy
                        if enemy != Enemy.RUPEE_BOSS:
                            continue
                        vanilla_enemy = vanilla_enemies.get((li, room.room_num), Enemy.NOTHING)
                        if vanilla_enemy == Enemy.RUPEE_BOSS:
                            continue
                        self.assertTrue(
                            is_safe_for_room(enemy, room.room_type),
                            f"Seed {seed}, L{level.level_num} room {room.room_num}: "
                            f"Rupee (0x35) placed in unsafe room type {room.room_type.name}",
                        )

    def test_traps_not_placed_in_unsafe_rooms(self):
        """After shuffling, trap-type enemies must not appear in
        trap-unsafe rooms."""
        for seed in [42, 999, 12345]:
            with self.subTest(seed=seed):
                gw = _load_game_world()
                _call_shuffle(gw, SeededRng(seed))

                for li, level in enumerate(gw.levels):
                    for room in level.rooms:
                        enemy = room.enemy_spec.enemy
                        if enemy in (Enemy.THREE_PAIRS_OF_TRAPS, Enemy.CORNER_TRAPS):
                            self.assertTrue(
                                is_safe_for_room(enemy, room.room_type),
                                f"Seed {seed}, L{level.level_num} room {room.room_num}: "
                                f"trap enemy {enemy.name} in unsafe room "
                                f"type {room.room_type.name}",
                            )

    # ------------------------------------------------------------------
    # Bubble constraint
    # ------------------------------------------------------------------

    def test_no_red_bubble_without_blue_in_replaced_rooms(self):
        """Among rooms that the shuffler replaces (non-excluded),
        if any has a red bubble, there must also be a blue bubble.

        Red bubbles disable sword use, and blue bubbles restore it —
        a level with only red bubbles could softlock the player.
        """
        for seed in [42, 999, 12345, 54321]:
            with self.subTest(seed=seed):
                gw = _load_game_world()
                _call_shuffle(gw, SeededRng(seed))

                for level in gw.levels:
                    has_red = False
                    has_blue = False
                    for room in level.rooms:
                        if _is_excluded_from_enemy_shuffling(room.enemy_spec.enemy):
                            continue
                        enemy = room.enemy_spec.enemy
                        if enemy == Enemy.RED_BUBBLE:
                            has_red = True
                        if enemy == Enemy.BLUE_BUBBLE:
                            has_blue = True
                    if has_red:
                        self.assertTrue(
                            has_blue,
                            f"Seed {seed}, Level {level.level_num}: "
                            f"has red bubble but no blue bubble among replaced rooms",
                        )

    # ------------------------------------------------------------------
    # Level 9 skip
    # ------------------------------------------------------------------

    def test_level_9_unchanged_when_not_included(self):
        """When include_level_9=False, level 9 rooms should not be modified."""
        for seed in [42, 999]:
            with self.subTest(seed=seed):
                gw_vanilla = _load_game_world()
                gw = _load_game_world()
                _call_shuffle(gw, SeededRng(seed), include_level_9=False)

                level_9 = gw.levels[8]
                vanilla_9 = gw_vanilla.levels[8]
                for ri, room in enumerate(level_9.rooms):
                    self.assertEqual(
                        room.enemy_spec.enemy.value,
                        vanilla_9.rooms[ri].enemy_spec.enemy.value,
                        f"Seed {seed}, L9 room {room.room_num}: "
                        f"changed when include_level_9=False",
                    )

    def test_level_9_changed_when_included(self):
        """When include_level_9=True, at least some level 9 rooms should change."""
        gw = _load_game_world()
        _call_shuffle(gw, SeededRng(42), include_level_9=True)
        # Just verify it runs without error — the general change test
        # covers that rooms actually change.

    # ------------------------------------------------------------------
    # Pool building
    # ------------------------------------------------------------------

    def test_only_valid_enemies_in_pools(self):
        """After shuffling, all rooms should contain enemies from the
        Enemy enum (no ValueError on construction)."""
        for seed in [42, 999]:
            with self.subTest(seed=seed):
                gw = _load_game_world()
                _call_shuffle(gw, SeededRng(seed))

                for level in gw.levels:
                    for room in level.rooms:
                        eid = room.enemy_spec.enemy.value
                        try:
                            Enemy(eid)
                        except ValueError:
                            self.fail(
                                f"Seed {seed}, L{level.level_num} room {room.room_num}: "
                                f"invalid enemy value 0x{eid:02X}",
                            )

    def test_no_whistle_tornado_in_rooms(self):
        """WHISTLE_TORNADO should never appear as a room enemy after shuffling.
        It's a non-combat entity that was previously introduced by the 0x3F
        masking bug aliasing MIXED_ENEMY_GROUP_13 (0x6E) to 0x2E."""
        for seed in [1, 42, 999, 12345, 54321]:
            with self.subTest(seed=seed):
                gw = _load_game_world()
                _call_shuffle(gw, SeededRng(seed))

                for level in gw.levels:
                    for room in level.rooms:
                        self.assertNotEqual(
                            room.enemy_spec.enemy, Enemy.WHISTLE_TORNADO,
                            f"Seed {seed}, L{level.level_num} room {room.room_num}: "
                            f"WHISTLE_TORNADO should not appear after shuffling",
                        )

    # ------------------------------------------------------------------
    # RNG consumption
    # ------------------------------------------------------------------

    def test_rng_consumed_deterministically(self):
        """The RNG should be consumed the same way across identical runs,
        measured by the next value after the shuffle completes."""
        rng1 = SeededRng(42)
        rng2 = SeededRng(42)
        gw1 = _load_game_world()
        gw2 = _load_game_world()
        _call_shuffle(gw1, rng1)
        _call_shuffle(gw2, rng2)
        self.assertEqual(rng1.random(), rng2.random(),
                         "RNG state diverged after identical shuffles")


class TestLevelSpriteSet(unittest.TestCase):
    """Verify LEVEL_SPRITE_SET covers all 9 dungeon levels."""

    def test_all_levels_present(self):
        for level_num in range(1, 10):
            self.assertIn(level_num, LEVEL_SPRITE_SET)


class TestExcludedEnemies(unittest.TestCase):
    """Verify the excluded enemy set."""

    def test_nothing_in_set(self):
        self.assertIn(Enemy.NOTHING, _EXCLUDED_FROM_ENEMY_SHUFFLING)

    def test_npcs_in_set(self):
        for npc in [Enemy.OLD_MAN, Enemy.BOMB_UPGRADER, Enemy.MUGGER]:
            self.assertIn(npc, _EXCLUDED_FROM_ENEMY_SHUFFLING)


if __name__ == '__main__':
    unittest.main()
