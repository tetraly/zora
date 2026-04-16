"""
Regression tests for enemy pool integrity.

These tests guard against the & 0x3F aliasing bug where NPC Enemy values
(>= 0x40) were masked to 6 bits and aliased onto real combat enemy IDs,
polluting shuffle pools. They also verify that traps (CORNER_TRAPS,
THREE_PAIRS_OF_TRAPS) remain in pools as legitimate shuffle participants.

Run with:
    python3 -m pytest zora/enemy/test_enemy_pool_integrity.py -v
"""

import signal
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from zora.parser import load_bin_files, parse_game_world
from zora.game_config import GameConfig
from zora.rng import SeededRng
from zora.data_model import Enemy, EnemySpec

BIN_DIR = Path(__file__).resolve().parents[1] / "rom_data"
TIMEOUT = 30

# Non-combat entity IDs that must NEVER appear in shuffle pools.
# If masked to 0x3F, these alias onto real combat enemies:
#   OLD_MAN_2 (0x4C) -> BLUE_DARKNUT (0x0C)
#   BOMB_UPGRADER (0x4F) -> BLUE_LEEVER (0x0F)
#   OLD_MAN_5 (0x50) -> RED_LEEVER (0x10)
#   CORNER_TRAPS (0x4A) -> BLUE_OCTOROK_2 (0x0A) — but traps ARE valid!
_NPC_ENEMY_VALUES: frozenset[int] = frozenset([
    Enemy.MIXED_FLAME.value,         # 0x40
    Enemy.FLYING_GLEEOK_HEAD.value,  # 0x46
    Enemy.OLD_MAN.value,             # 0x4B
    Enemy.OLD_MAN_2.value,           # 0x4C
    Enemy.OLD_MAN_3.value,           # 0x4D
    Enemy.OLD_MAN_4.value,           # 0x4E
    Enemy.BOMB_UPGRADER.value,       # 0x4F
    Enemy.OLD_MAN_5.value,           # 0x50
    Enemy.MUGGER.value,              # 0x51
    Enemy.OLD_MAN_6.value,           # 0x52
])

# Trap enemy IDs that MUST remain in shuffle pools.
_TRAP_ENEMY_VALUES: frozenset[int] = frozenset([
    Enemy.CORNER_TRAPS.value,          # 0x4A
    Enemy.THREE_PAIRS_OF_TRAPS.value,  # 0x49
])


def _timeout_handler(signum: int, frame: object) -> None:
    raise TimeoutError("test exceeded timeout")


def _load_game_world():
    bins = load_bin_files(BIN_DIR)
    return parse_game_world(bins)


class TestNpcExclusionFromShuffleMonsters(unittest.TestCase):
    """NPC rooms must never be modified by shuffle_monsters."""

    def setUp(self) -> None:
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(TIMEOUT)

    def tearDown(self) -> None:
        signal.alarm(0)

    def test_npc_rooms_unchanged_after_shuffle_monsters(self) -> None:
        """Rooms containing NPC enemies (OLD_MAN*, BOMB_UPGRADER, MUGGER)
        must not be touched by the within-level shuffler."""
        from zora.enemy.shuffle_monsters import shuffle_monsters

        for seed in [1, 42, 999, 12345]:
            with self.subTest(seed=seed):
                gw_vanilla = _load_game_world()
                gw = _load_game_world()
                config = GameConfig(
                    shuffle_dungeon_monsters=True,
                    shuffle_ganon_zelda=True,
                )
                shuffle_monsters(
                    gw, SeededRng(seed),
                    shuffle=config.shuffle_dungeon_monsters,
                    shuffle_gannon=config.shuffle_ganon_zelda,
                    must_beat_gannon=config.force_ganon,
                )

                for li, level in enumerate(gw.levels):
                    for ri, room in enumerate(level.rooms):
                        vanilla_eid = gw_vanilla.levels[li].rooms[ri].enemy_spec.enemy.value
                        if vanilla_eid in _NPC_ENEMY_VALUES:
                            self.assertEqual(
                                room.enemy_spec.enemy.value,
                                vanilla_eid,
                                f"Seed {seed}, L{level.level_num} room {room.room_num}: "
                                f"NPC enemy 0x{vanilla_eid:02X} "
                                f"({Enemy(vanilla_eid).name}) was changed to "
                                f"0x{room.enemy_spec.enemy.value:02X}",
                            )

    def test_no_npc_appears_after_shuffle_monsters(self) -> None:
        """No room should contain an NPC enemy after shuffling — NPCs must
        not leak into the shuffle pool and get assigned to combat rooms."""
        from zora.enemy.shuffle_monsters import shuffle_monsters

        for seed in [1, 42, 999, 12345]:
            with self.subTest(seed=seed):
                gw_vanilla = _load_game_world()
                gw = _load_game_world()
                config = GameConfig(
                    shuffle_dungeon_monsters=True,
                    shuffle_ganon_zelda=True,
                )
                shuffle_monsters(
                    gw, SeededRng(seed),
                    shuffle=config.shuffle_dungeon_monsters,
                    shuffle_gannon=config.shuffle_ganon_zelda,
                    must_beat_gannon=config.force_ganon,
                )

                for li, level in enumerate(gw.levels):
                    for ri, room in enumerate(level.rooms):
                        eid = room.enemy_spec.enemy.value
                        vanilla_eid = gw_vanilla.levels[li].rooms[ri].enemy_spec.enemy.value
                        # If the room had an NPC in vanilla, it's fine (unchanged).
                        # But a room that DIDN'T have an NPC must not get one.
                        if vanilla_eid not in _NPC_ENEMY_VALUES:
                            self.assertNotIn(
                                eid,
                                _NPC_ENEMY_VALUES,
                                f"Seed {seed}, L{level.level_num} room {room.room_num}: "
                                f"NPC 0x{eid:02X} ({Enemy(eid).name}) appeared in "
                                f"a combat room (was 0x{vanilla_eid:02X})",
                            )


class TestNpcExclusionFromShuffleBetweenLevels(unittest.TestCase):
    """NPC rooms must never be modified by shuffle_monsters_between_levels."""

    def setUp(self) -> None:
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(TIMEOUT)

    def tearDown(self) -> None:
        signal.alarm(0)

    def test_npc_rooms_unchanged_after_between_levels(self) -> None:
        """Rooms containing NPC enemies must not be touched by the
        between-levels shuffler."""
        from zora.enemy.shuffle_monsters_between_levels import (
            shuffle_monsters_between_levels,
        )

        for seed in [1, 42, 999, 12345]:
            with self.subTest(seed=seed):
                gw_vanilla = _load_game_world()
                gw = _load_game_world()
                shuffle_monsters_between_levels(gw, SeededRng(seed))

                for li, level in enumerate(gw.levels):
                    for ri, room in enumerate(level.rooms):
                        vanilla_eid = gw_vanilla.levels[li].rooms[ri].enemy_spec.enemy.value
                        if vanilla_eid in _NPC_ENEMY_VALUES:
                            self.assertEqual(
                                room.enemy_spec.enemy.value,
                                vanilla_eid,
                                f"Seed {seed}, L{level.level_num} room {room.room_num}: "
                                f"NPC enemy 0x{vanilla_eid:02X} "
                                f"({Enemy(vanilla_eid).name}) was changed to "
                                f"0x{room.enemy_spec.enemy.value:02X}",
                            )

    def test_no_npc_appears_after_between_levels(self) -> None:
        """No room should contain an NPC enemy after between-levels shuffling."""
        from zora.enemy.shuffle_monsters_between_levels import (
            shuffle_monsters_between_levels,
        )

        for seed in [1, 42, 999, 12345]:
            with self.subTest(seed=seed):
                gw_vanilla = _load_game_world()
                gw = _load_game_world()
                shuffle_monsters_between_levels(gw, SeededRng(seed))

                for li, level in enumerate(gw.levels):
                    for ri, room in enumerate(level.rooms):
                        eid = room.enemy_spec.enemy.value
                        vanilla_eid = gw_vanilla.levels[li].rooms[ri].enemy_spec.enemy.value
                        if vanilla_eid not in _NPC_ENEMY_VALUES:
                            self.assertNotIn(
                                eid,
                                _NPC_ENEMY_VALUES,
                                f"Seed {seed}, L{level.level_num} room {room.room_num}: "
                                f"NPC 0x{eid:02X} ({Enemy(eid).name}) appeared in "
                                f"a combat room (was 0x{vanilla_eid:02X})",
                            )


class TestTrapPoolMembership(unittest.TestCase):
    """Traps (CORNER_TRAPS, THREE_PAIRS_OF_TRAPS) must remain in shuffle pools."""

    def setUp(self) -> None:
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(TIMEOUT)

    def tearDown(self) -> None:
        signal.alarm(0)

    def test_traps_not_excluded_by_is_eligible(self) -> None:
        """_is_eligible must return True for trap enemies."""
        from zora.enemy.shuffle_monsters import _is_eligible

        for trap_val in sorted(_TRAP_ENEMY_VALUES):
            with self.subTest(enemy=f"0x{trap_val:02X}"):
                self.assertTrue(
                    _is_eligible(Enemy(trap_val), False),
                    f"Trap 0x{trap_val:02X} ({Enemy(trap_val).name}) excluded "
                    f"from shuffle — traps must be eligible",
                )

    def test_traps_not_excluded_by_between_levels_filter(self) -> None:
        """The _EXCLUDED_FROM_ENEMY_SHUFFLING set in shuffle_monsters_between_levels
        must not contain trap enemy IDs."""
        from zora.enemy.shuffle_monsters_between_levels import (
            _EXCLUDED_FROM_ENEMY_SHUFFLING,
        )

        for trap_val in sorted(_TRAP_ENEMY_VALUES):
            with self.subTest(enemy=f"0x{trap_val:02X}"):
                self.assertNotIn(
                    Enemy(trap_val),
                    _EXCLUDED_FROM_ENEMY_SHUFFLING,
                    f"Trap 0x{trap_val:02X} ({Enemy(trap_val).name}) is in "
                    f"_EXCLUDED_FROM_ENEMY_SHUFFLING — traps must stay in pools",
                )

    def test_npcs_excluded_by_both_shufflers(self) -> None:
        """All NPC enemy IDs must be excluded by both shufflers.

        shuffle_monsters excludes NPCs via _NON_COMBAT_ENEMIES (unconditional)
        and _GANNON_GATED (conditional on shuffle_gannon). With shuffle_gannon
        off, all NPC values must be ineligible.
        """
        from zora.enemy.shuffle_monsters import _is_eligible
        from zora.enemy.shuffle_monsters_between_levels import (
            _is_excluded_from_enemy_shuffling,
        )

        for npc_val in sorted(_NPC_ENEMY_VALUES):
            with self.subTest(enemy=f"0x{npc_val:02X}"):
                self.assertFalse(
                    _is_eligible(Enemy(npc_val), shuffle_gannon=False),
                    f"NPC 0x{npc_val:02X} ({Enemy(npc_val).name}) not excluded "
                    f"by shuffle_monsters._is_eligible (shuffle_gannon=False)",
                )
                self.assertTrue(
                    _is_excluded_from_enemy_shuffling(Enemy(npc_val)),
                    f"NPC 0x{npc_val:02X} ({Enemy(npc_val).name}) not excluded "
                    f"by shuffle_monsters_between_levels",
                )


class TestOrchestratorGating(unittest.TestCase):
    """The randomize_enemies orchestrator must respect config flags."""

    def setUp(self) -> None:
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(TIMEOUT)

    def tearDown(self) -> None:
        signal.alarm(0)

    def test_no_changes_when_all_enemy_flags_off(self) -> None:
        """With all enemy randomization flags off, no rooms should change."""
        from zora.enemy.randomize import randomize_enemies

        gw_vanilla = _load_game_world()
        gw = _load_game_world()
        config = GameConfig(
            shuffle_dungeon_monsters=False,
            shuffle_monsters_between_levels=False,
            shuffle_enemy_groups=False,
            change_enemy_hp=0,
            enemy_hp_to_zero=False,
            shuffle_boss_hp=0,
            boss_hp_to_zero=False,
            ganon_hp_to_zero=False,
        )
        randomize_enemies(gw, config, SeededRng(42))

        for li, level in enumerate(gw.levels):
            for ri, room in enumerate(level.rooms):
                self.assertEqual(
                    room.enemy_spec.enemy.value,
                    gw_vanilla.levels[li].rooms[ri].enemy_spec.enemy.value,
                    f"L{level.level_num} room {room.room_num}: enemy changed "
                    f"with all flags off",
                )

    def test_only_between_levels_runs_when_only_that_flag(self) -> None:
        """With only shuffle_monsters_between_levels on, within-level shuffle
        and enemy groups should not run."""
        from zora.enemy.randomize import randomize_enemies

        gw = _load_game_world()
        config = GameConfig(
            shuffle_dungeon_monsters=False,
            shuffle_monsters_between_levels=True,
            shuffle_enemy_groups=False,
        )
        # Should run without error — just between-levels
        randomize_enemies(gw, config, SeededRng(42))


class TestGleeok1NeverPlaced(unittest.TestCase):
    """GLEEOK_1 is visually glitchy and must never appear in the game world."""

    def setUp(self) -> None:
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(TIMEOUT)

    def tearDown(self) -> None:
        signal.alarm(0)

    def test_gleeok_1_not_in_boss_tiers(self) -> None:
        """GLEEOK_1 must not appear in any boss tier pool."""
        from zora.enemy.shuffle_bosses import BOSS_TIERS

        for tier, pool in BOSS_TIERS.items():
            self.assertNotIn(
                Enemy.GLEEOK_1, pool,
                f"GLEEOK_1 found in BOSS_TIERS[{tier.name}] — "
                f"it is glitchy and must not be placed",
            )

    def test_no_gleeok_1_after_randomize_enemies(self) -> None:
        """No room should contain GLEEOK_1 after full enemy randomization."""
        from zora.enemy.randomize import randomize_enemies

        for seed in [1, 42, 999, 12345]:
            with self.subTest(seed=seed):
                gw = _load_game_world()
                config = GameConfig(
                    shuffle_dungeon_monsters=True,
                    shuffle_monsters_between_levels=True,
                    shuffle_ganon_zelda=True,
                    shuffle_enemy_groups=True,
                    shuffle_bosses=True,
                    change_dungeon_boss_groups=True,
                )
                randomize_enemies(gw, config, SeededRng(seed))

                for level in gw.levels:
                    for room in level.rooms:
                        self.assertNotEqual(
                            room.enemy_spec.enemy, Enemy.GLEEOK_1,
                            f"Seed {seed}, L{level.level_num} room {room.room_num}: "
                            f"GLEEOK_1 placed — it is glitchy and must never appear",
                        )

    def test_no_gleeok_1_after_shuffle_bosses_only(self) -> None:
        """GLEEOK_1 must not appear even when only boss shuffling is active."""
        from zora.enemy.randomize import randomize_enemies

        for seed in [1, 42, 999]:
            with self.subTest(seed=seed):
                gw = _load_game_world()
                config = GameConfig(
                    shuffle_bosses=True,
                )
                randomize_enemies(gw, config, SeededRng(seed))

                for level in gw.levels:
                    for room in level.rooms:
                        self.assertNotEqual(
                            room.enemy_spec.enemy, Enemy.GLEEOK_1,
                            f"Seed {seed}, L{level.level_num} room {room.room_num}: "
                            f"GLEEOK_1 placed by shuffle_bosses",
                        )


class TestGleeok4PushBlockSafety(unittest.TestCase):
    """GLEEOK_4 must never be placed in rooms with push blocks."""

    def setUp(self) -> None:
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(TIMEOUT)

    def tearDown(self) -> None:
        signal.alarm(0)

    def test_is_safe_for_room_rejects_gleeok_4_with_push_block(self) -> None:
        """is_safe_for_room must return False for GLEEOK_4 when has_push_block is True."""
        from zora.enemy.safety_checks import is_safe_for_room
        from zora.data_model import RoomType

        # PLAIN_ROOM is otherwise safe for GLEEOK_4
        self.assertTrue(
            is_safe_for_room(Enemy.GLEEOK_4, RoomType.PLAIN_ROOM, has_push_block=False),
            "GLEEOK_4 should be safe in PLAIN_ROOM without push block",
        )
        self.assertFalse(
            is_safe_for_room(Enemy.GLEEOK_4, RoomType.PLAIN_ROOM, has_push_block=True),
            "GLEEOK_4 must not be safe in PLAIN_ROOM with push block",
        )

    def test_other_gleeoks_unaffected_by_push_block(self) -> None:
        """GLEEOK_2 and GLEEOK_3 should still be allowed in push block rooms."""
        from zora.enemy.safety_checks import is_safe_for_room
        from zora.data_model import RoomType

        for gleeok in [Enemy.GLEEOK_2, Enemy.GLEEOK_3]:
            with self.subTest(enemy=gleeok.name):
                self.assertTrue(
                    is_safe_for_room(gleeok, RoomType.PLAIN_ROOM, has_push_block=True),
                    f"{gleeok.name} should be allowed in push block rooms",
                )

    def test_no_gleeok_4_in_push_block_rooms_after_randomize(self) -> None:
        """After full randomization, no GLEEOK_4 should appear in rooms with movable blocks."""
        from zora.enemy.randomize import randomize_enemies

        for seed in [1, 42, 999, 12345]:
            with self.subTest(seed=seed):
                gw = _load_game_world()
                config = GameConfig(
                    shuffle_dungeon_monsters=True,
                    shuffle_monsters_between_levels=True,
                    shuffle_ganon_zelda=True,
                    shuffle_enemy_groups=True,
                    shuffle_bosses=True,
                    change_dungeon_boss_groups=True,
                )
                randomize_enemies(gw, config, SeededRng(seed))

                for level in gw.levels:
                    for room in level.rooms:
                        if room.enemy_spec.enemy == Enemy.GLEEOK_4 and room.movable_block:
                            self.fail(
                                f"Seed {seed}, L{level.level_num} room {room.room_num}: "
                                f"GLEEOK_4 placed in room with push block",
                            )


if __name__ == "__main__":
    unittest.main()
