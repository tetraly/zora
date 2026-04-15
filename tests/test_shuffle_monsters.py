"""
Tests for shuffle_monsters.

Uses a real GameWorld parsed from vanilla ROM bin files to verify that the
monster shuffler runs correctly and maintains structural invariants.

Run with:
    python3 -m pytest zora/enemy/test_shuffle_monsters.py -v
"""

import copy
import signal
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from zora.parser import load_bin_files, parse_game_world
from zora.game_config import GameConfig
from zora.rng import SeededRng
from zora.data_model import Enemy, EnemySpec, Item, ItemPosition, RoomAction, Room, RoomType, WallSet, WallType
from zora.enemy.shuffle_monsters import shuffle_monsters as _shuffle_monsters_raw
from zora.enemy.safety_checks import (
    safe_for_lanmola,
    safe_for_rupees,
    safe_for_gannon,
    safe_for_gohma,
    safe_for_dodongo,
    safe_for_traps,
    safe_for_zelda,
)

BIN_DIR = Path(__file__).resolve().parents[1] / 'rom_data'


def shuffle_monsters(world, config, rng):
    """Adapter: tests pass (world, config, rng); new signature is (world, rng, ...)."""
    return _shuffle_monsters_raw(
        world, rng,
        shuffle=config.shuffle_dungeon_monsters,
        shuffle_gannon=config.shuffle_ganon_zelda,
        must_beat_gannon=config.force_ganon,
    )
TIMEOUT = 30


def _timeout_handler(signum, frame):
    raise TimeoutError("test exceeded timeout")


def _load_game_world():
    bins = load_bin_files(BIN_DIR)
    return parse_game_world(bins)


def _snapshot_rooms(gw):
    """Capture (level_index, room_index) -> enemy value before shuffling."""
    snap = {}
    for li, level in enumerate(gw.levels):
        for ri, room in enumerate(level.rooms):
            snap[(li, ri)] = room.enemy_spec.enemy.value
    return snap


class TestShuffleMonsters(unittest.TestCase):

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
                config = GameConfig(shuffle_dungeon_monsters=True)
                result = shuffle_monsters(gw, config, SeededRng(seed))
                self.assertTrue(result, f"Seed {seed}: shuffle_monsters returned False")

    def test_runs_with_ganon_zelda_shuffle(self):
        for seed in [1, 42, 999]:
            with self.subTest(seed=seed):
                gw = _load_game_world()
                config = GameConfig(
                    shuffle_dungeon_monsters=True,
                    shuffle_ganon_zelda=True,
                )
                result = shuffle_monsters(gw, config, SeededRng(seed))
                self.assertTrue(result)

    def test_runs_with_force_ganon(self):
        for seed in [42, 999]:
            with self.subTest(seed=seed):
                gw = _load_game_world()
                config = GameConfig(
                    shuffle_dungeon_monsters=True,
                    shuffle_ganon_zelda=True,
                    force_ganon=True,
                )
                result = shuffle_monsters(gw, config, SeededRng(seed))
                self.assertTrue(result)

    # ------------------------------------------------------------------
    # Noop when disabled
    # ------------------------------------------------------------------

    def test_noop_when_disabled(self):
        gw = _load_game_world()
        orig = _snapshot_rooms(gw)
        config = GameConfig(shuffle_dungeon_monsters=False)
        shuffle_monsters(gw, config, SeededRng(42))
        for key, orig_val in orig.items():
            li, ri = key
            self.assertEqual(
                gw.levels[li].rooms[ri].enemy_spec.enemy.value, orig_val,
                f"Room changed when shuffle disabled: L{li+1} room {ri}",
            )

    # ------------------------------------------------------------------
    # Some rooms should change when shuffling is enabled
    # ------------------------------------------------------------------

    def test_some_rooms_changed(self):
        gw = _load_game_world()
        orig = _snapshot_rooms(gw)
        config = GameConfig(shuffle_dungeon_monsters=True)
        shuffle_monsters(gw, config, SeededRng(42))

        changed = 0
        total = 0
        for key, orig_val in orig.items():
            li, ri = key
            total += 1
            if gw.levels[li].rooms[ri].enemy_spec.enemy.value != orig_val:
                changed += 1

        self.assertGreater(changed, 0, "No rooms were changed by shuffling")

    # ------------------------------------------------------------------
    # Determinism
    # ------------------------------------------------------------------

    def test_deterministic(self):
        gw1 = _load_game_world()
        gw2 = _load_game_world()
        config = GameConfig(shuffle_dungeon_monsters=True)
        shuffle_monsters(gw1, config, SeededRng(42))
        shuffle_monsters(gw2, config, SeededRng(42))

        for li in range(len(gw1.levels)):
            for ri in range(len(gw1.levels[li].rooms)):
                e1 = gw1.levels[li].rooms[ri].enemy_spec.enemy.value
                e2 = gw2.levels[li].rooms[ri].enemy_spec.enemy.value
                self.assertEqual(e1, e2, f"Non-deterministic: L{li+1} room {ri}")

    def test_different_seeds_differ(self):
        gw1 = _load_game_world()
        gw2 = _load_game_world()
        config = GameConfig(shuffle_dungeon_monsters=True)
        shuffle_monsters(gw1, config, SeededRng(1))
        shuffle_monsters(gw2, config, SeededRng(9999))

        any_diff = False
        for li in range(len(gw1.levels)):
            for ri in range(len(gw1.levels[li].rooms)):
                if gw1.levels[li].rooms[ri].enemy_spec.enemy.value != \
                   gw2.levels[li].rooms[ri].enemy_spec.enemy.value:
                    any_diff = True
                    break
            if any_diff:
                break
        self.assertTrue(any_diff, "Two different seeds produced identical results")

    # ------------------------------------------------------------------
    # Safety constraint validation
    # ------------------------------------------------------------------

    def test_lanmola_not_shuffled_into_unsafe_rooms(self):
        """Lanmola (0x3A/0x3B) must not be shuffled INTO a Lanmola-unsafe room.

        Only checks non-group enemies — mixed enemy groups (>= 0x62) whose
        low 6 bits happen to match Lanmola IDs are NOT subject to the Lanmola
        constraint (the C# compares unmasked enemy IDs).

        Note: a Lanmola that was already in an unsafe room in vanilla may stay
        there — the Fisher-Yates only prevents swapping into/from unsafe rooms,
        it doesn't relocate enemies that start in unsafe positions.
        """
        lanmola_ids = {0x3A, 0x3B}
        for seed in [42, 999, 12345]:
            with self.subTest(seed=seed):
                gw_vanilla = _load_game_world()
                gw = _load_game_world()
                config = GameConfig(shuffle_dungeon_monsters=True)
                shuffle_monsters(gw, config, SeededRng(seed))

                # Build vanilla enemy lookup
                vanilla_enemies: dict[tuple[int, int], int] = {}
                for li, level in enumerate(gw_vanilla.levels):
                    for room in level.rooms:
                        vanilla_enemies[(li, room.room_num)] = room.enemy_spec.enemy.value

                for li, level in enumerate(gw.levels):
                    for room in level.rooms:
                        eid = room.enemy_spec.enemy.value
                        # Only check actual Lanmola enemies, not mixed groups
                        if eid not in lanmola_ids:
                            continue
                        # Skip if this Lanmola was already here in vanilla
                        vanilla_eid = vanilla_enemies.get((li, room.room_num), 0)
                        if vanilla_eid in lanmola_ids:
                            continue
                        self.assertTrue(
                            safe_for_lanmola(room.room_type.value),
                            f"Seed {seed}, L{level.level_num} room {room.room_num}: "
                            f"Lanmola (0x{eid:02X}) shuffled into unsafe room "
                            f"type {room.room_type.name}",
                        )

    def test_gannon_not_shuffled_into_unsafe_rooms(self):
        """Gannon (0x3E) must not be shuffled INTO a Gannon-unsafe room.

        Same caveat as Lanmola: Gannon already in an unsafe room in vanilla
        may stay there.
        """
        for seed in [42, 999]:
            with self.subTest(seed=seed):
                gw_vanilla = _load_game_world()
                gw = _load_game_world()
                config = GameConfig(
                    shuffle_dungeon_monsters=True,
                    shuffle_ganon_zelda=True,
                )
                shuffle_monsters(gw, config, SeededRng(seed))

                vanilla_enemies: dict[tuple[int, int], int] = {}
                for li, level in enumerate(gw_vanilla.levels):
                    for room in level.rooms:
                        vanilla_enemies[(li, room.room_num)] = room.enemy_spec.enemy.value

                for li, level in enumerate(gw.levels):
                    for room in level.rooms:
                        eid = room.enemy_spec.enemy.value
                        flag = 0x80 if room.enemy_spec.is_group else 0
                        if eid != 0x3E or flag != 0:
                            continue
                        vanilla_eid = vanilla_enemies.get((li, room.room_num), 0)
                        if vanilla_eid == 0x3E:
                            continue
                        self.assertTrue(
                            safe_for_gannon(room.room_type.value),
                            f"Seed {seed}, L{level.level_num} room {room.room_num}: "
                            f"Gannon shuffled into unsafe room type "
                            f"{room.room_type.name}",
                        )

    # ------------------------------------------------------------------
    # Gannon room post-processing
    # ------------------------------------------------------------------

    def test_gannon_room_has_special_flags(self):
        """After shuffling, the Gannon room in levels 7-9 should have
        the special flags: is_dark=True, boss_cry_1=True, item=Ganon's Triforce."""
        for seed in [42, 999]:
            with self.subTest(seed=seed):
                gw = _load_game_world()
                config = GameConfig(shuffle_dungeon_monsters=True)
                shuffle_monsters(gw, config, SeededRng(seed))

                for level in gw.levels:
                    if level.level_num < 7:
                        continue
                    for room in level.rooms:
                        if (room.enemy_spec.enemy.value & 0x3F) == 0x3E:
                            self.assertTrue(
                                room.is_dark,
                                f"Seed {seed}, L{level.level_num} room "
                                f"{room.room_num}: Gannon room not dark",
                            )
                            self.assertTrue(
                                room.boss_cry_1,
                                f"Seed {seed}, L{level.level_num} room "
                                f"{room.room_num}: Gannon room missing boss_cry_1",
                            )
                            self.assertEqual(
                                room.item.value, 0x0E,
                                f"Seed {seed}, L{level.level_num} room "
                                f"{room.room_num}: Gannon room item should be "
                                f"Ganon's Triforce (0x0E), got {room.item}",
                            )
                            self.assertEqual(
                                room.room_action.value, 0x03,
                                f"Seed {seed}, L{level.level_num} room "
                                f"{room.room_num}: Gannon room action should be 3",
                            )

    def test_boss_cry_bits_cleared_except_gannon_adjacent(self):
        """After post-processing, boss_cry_2 should be False on all rooms.
        boss_cry_1 should only be True on Gannon rooms and their adjacents."""
        gw = _load_game_world()
        config = GameConfig(shuffle_dungeon_monsters=True)
        shuffle_monsters(gw, config, SeededRng(42))

        for level in gw.levels:
            for room in level.rooms:
                self.assertFalse(
                    room.boss_cry_2,
                    f"L{level.level_num} room {room.room_num}: "
                    f"boss_cry_2 should be False after post-processing",
                )

    # ------------------------------------------------------------------
    # Remaining safety constraint validation (#2)
    # ------------------------------------------------------------------

    def _vanilla_enemy_lookup(self, gw):
        """Build {(level_index, room_num): enemy_value} from a fresh game world."""
        lookup: dict[tuple[int, int], int] = {}
        for li, level in enumerate(gw.levels):
            for room in level.rooms:
                lookup[(li, room.room_num)] = room.enemy_spec.enemy.value
        return lookup

    def _vanilla_flag_lookup(self, gw):
        """Build {(level_index, room_num): flag} from a fresh game world."""
        lookup: dict[tuple[int, int], int] = {}
        for li, level in enumerate(gw.levels):
            for room in level.rooms:
                lookup[(li, room.room_num)] = 0x80 if room.enemy_spec.is_group else 0
        return lookup

    def test_gohma_not_shuffled_into_unsafe_rooms(self):
        """Gohma (0x33/0x34) must not be shuffled INTO a Gohma-unsafe room."""
        gohma_ids = {0x33, 0x34}
        for seed in [42, 999, 12345]:
            with self.subTest(seed=seed):
                gw_vanilla = _load_game_world()
                gw = _load_game_world()
                config = GameConfig(shuffle_dungeon_monsters=True)
                shuffle_monsters(gw, config, SeededRng(seed))

                vanilla_enemies = self._vanilla_enemy_lookup(gw_vanilla)

                for li, level in enumerate(gw.levels):
                    for room in level.rooms:
                        eid = room.enemy_spec.enemy.value & 0x3F
                        flag = 0x80 if room.enemy_spec.is_group else 0
                        if not (flag == 0 and eid in gohma_ids):
                            continue
                        # Skip if this Gohma was already here in vanilla
                        vanilla_eid = vanilla_enemies.get((li, room.room_num), 0) & 0x3F
                        vanilla_flag = 0x80 if gw_vanilla.levels[li].rooms[0].enemy_spec.is_group else 0
                        # Re-check vanilla flag properly
                        vanilla_flag_lookup = self._vanilla_flag_lookup(gw_vanilla)
                        v_flag = vanilla_flag_lookup.get((li, room.room_num), 0)
                        if v_flag == 0 and vanilla_eid in gohma_ids:
                            continue
                        self.assertTrue(
                            safe_for_gohma(room.room_type.value),
                            f"Seed {seed}, L{level.level_num} room {room.room_num}: "
                            f"Gohma (0x{eid:02X}) shuffled into unsafe room "
                            f"type {room.room_type.name}",
                        )

    def test_dodongo_not_shuffled_into_unsafe_rooms(self):
        """Dodongo (0x31/0x32) must not be shuffled INTO a Dodongo-unsafe room."""
        dodongo_ids = {0x31, 0x32}
        for seed in [42, 999, 12345]:
            with self.subTest(seed=seed):
                gw_vanilla = _load_game_world()
                gw = _load_game_world()
                config = GameConfig(shuffle_dungeon_monsters=True)
                shuffle_monsters(gw, config, SeededRng(seed))

                vanilla = self._vanilla_enemy_lookup(gw_vanilla)
                vanilla_flags = self._vanilla_flag_lookup(gw_vanilla)

                for li, level in enumerate(gw.levels):
                    for room in level.rooms:
                        eid = room.enemy_spec.enemy.value & 0x3F
                        flag = 0x80 if room.enemy_spec.is_group else 0
                        if not (flag == 0 and eid in dodongo_ids):
                            continue
                        v_eid = vanilla.get((li, room.room_num), 0) & 0x3F
                        v_flag = vanilla_flags.get((li, room.room_num), 0)
                        if v_flag == 0 and v_eid in dodongo_ids:
                            continue
                        self.assertTrue(
                            safe_for_dodongo(room.room_type.value),
                            f"Seed {seed}, L{level.level_num} room {room.room_num}: "
                            f"Dodongo (0x{eid:02X}) shuffled into unsafe room "
                            f"type {room.room_type.name}",
                        )

    def test_traps_not_shuffled_into_unsafe_rooms(self):
        """Blade traps (0x27) must not be shuffled INTO a trap-unsafe room."""
        for seed in [42, 999, 12345]:
            with self.subTest(seed=seed):
                gw_vanilla = _load_game_world()
                gw = _load_game_world()
                config = GameConfig(shuffle_dungeon_monsters=True)
                shuffle_monsters(gw, config, SeededRng(seed))

                vanilla = self._vanilla_enemy_lookup(gw_vanilla)

                for li, level in enumerate(gw.levels):
                    for room in level.rooms:
                        eid = room.enemy_spec.enemy.value & 0x3F
                        if eid != 0x27:  # blade trap
                            continue
                        v_eid = vanilla.get((li, room.room_num), 0) & 0x3F
                        if v_eid == 0x27:
                            continue
                        self.assertTrue(
                            safe_for_traps(room.room_type.value),
                            f"Seed {seed}, L{level.level_num} room {room.room_num}: "
                            f"Trap (0x27) shuffled into unsafe room "
                            f"type {room.room_type.name}",
                        )

    def test_rupee_not_shuffled_into_unsafe_rooms(self):
        """Rupee rooms (0x35) must not be shuffled INTO a Rupee-unsafe room."""
        for seed in [42, 999, 12345]:
            with self.subTest(seed=seed):
                gw_vanilla = _load_game_world()
                gw = _load_game_world()
                config = GameConfig(
                    shuffle_dungeon_monsters=True,
                    shuffle_ganon_zelda=True,
                )
                shuffle_monsters(gw, config, SeededRng(seed))

                vanilla = self._vanilla_enemy_lookup(gw_vanilla)

                for li, level in enumerate(gw.levels):
                    for room in level.rooms:
                        eid = room.enemy_spec.enemy.value
                        if eid != 0x35:
                            continue
                        v_eid = vanilla.get((li, room.room_num), 0)
                        if v_eid == 0x35:
                            continue
                        self.assertTrue(
                            safe_for_rupees(room.room_type.value),
                            f"Seed {seed}, L{level.level_num} room {room.room_num}: "
                            f"Rupee (0x35) shuffled into unsafe room "
                            f"type {room.room_type.name}",
                        )

    def test_zelda_not_shuffled_into_unsafe_rooms(self):
        """Zelda (0x37, flag=0) must not be shuffled INTO a Zelda-unsafe room."""
        for seed in [42, 999, 12345]:
            with self.subTest(seed=seed):
                gw_vanilla = _load_game_world()
                gw = _load_game_world()
                config = GameConfig(
                    shuffle_dungeon_monsters=True,
                    shuffle_ganon_zelda=True,
                )
                shuffle_monsters(gw, config, SeededRng(seed))

                vanilla = self._vanilla_enemy_lookup(gw_vanilla)
                vanilla_flags = self._vanilla_flag_lookup(gw_vanilla)

                for li, level in enumerate(gw.levels):
                    for room in level.rooms:
                        eid = room.enemy_spec.enemy.value
                        flag = 0x80 if room.enemy_spec.is_group else 0
                        if not (eid == 0x37 and flag == 0):
                            continue
                        v_eid = vanilla.get((li, room.room_num), 0)
                        v_flag = vanilla_flags.get((li, room.room_num), 0)
                        if v_eid == 0x37 and v_flag == 0:
                            continue
                        self.assertTrue(
                            safe_for_zelda(room.room_type.value, False),
                            f"Seed {seed}, L{level.level_num} room {room.room_num}: "
                            f"Zelda (0x37) shuffled into unsafe room "
                            f"type {room.room_type.name}",
                        )

    def test_zelda_not_shuffled_into_unsafe_rooms_force_ganon(self):
        """With force_ganon=True, Zelda safety is stricter (adds screens 27/28)."""
        for seed in [42, 999, 12345]:
            with self.subTest(seed=seed):
                gw_vanilla = _load_game_world()
                gw = _load_game_world()
                config = GameConfig(
                    shuffle_dungeon_monsters=True,
                    shuffle_ganon_zelda=True,
                    force_ganon=True,
                )
                shuffle_monsters(gw, config, SeededRng(seed))

                vanilla = self._vanilla_enemy_lookup(gw_vanilla)
                vanilla_flags = self._vanilla_flag_lookup(gw_vanilla)

                for li, level in enumerate(gw.levels):
                    for room in level.rooms:
                        eid = room.enemy_spec.enemy.value
                        flag = 0x80 if room.enemy_spec.is_group else 0
                        if not (eid == 0x37 and flag == 0):
                            continue
                        v_eid = vanilla.get((li, room.room_num), 0)
                        v_flag = vanilla_flags.get((li, room.room_num), 0)
                        if v_eid == 0x37 and v_flag == 0:
                            continue
                        self.assertTrue(
                            safe_for_zelda(room.room_type.value, True),
                            f"Seed {seed}, L{level.level_num} room {room.room_num}: "
                            f"Zelda (0x37) shuffled into unsafe room "
                            f"type {room.room_type.name} (force_ganon=True)",
                        )

    # ------------------------------------------------------------------
    # Edge cases in shuffle logic (#3)
    # ------------------------------------------------------------------

    def test_is_eligible_excludes_correct_enemies(self):
        """0x36 is always excluded. 0x37 (Zelda) and 0x3E (Gannon) are excluded
        unless shuffle_gannon is True. NPCs (OLD_MAN etc.) are excluded."""
        from zora.enemy.shuffle_monsters import _is_eligible

        # Always excluded: enemy 0x00 (NOTHING)
        self.assertFalse(_is_eligible(Enemy.NOTHING, False))
        self.assertFalse(_is_eligible(Enemy.NOTHING, True))

        # 0x36 (HUNGRY_GORIYA): ALWAYS excluded
        self.assertFalse(_is_eligible(Enemy.HUNGRY_GORIYA, False),
                         "HUNGRY_GORIYA should always be excluded")
        self.assertFalse(_is_eligible(Enemy.HUNGRY_GORIYA, True),
                         "HUNGRY_GORIYA should always be excluded even with shuffle_gannon")

        # 0x37 (Zelda), 0x3E (Gannon): excluded unless shuffle_gannon
        for enemy in [Enemy.THE_KIDNAPPED, Enemy.THE_BEAST]:
            self.assertFalse(_is_eligible(enemy, False),
                             f"{enemy.name} should be excluded when shuffle_gannon=False")
            self.assertTrue(_is_eligible(enemy, True),
                            f"{enemy.name} should be included when shuffle_gannon=True")

        # NPCs: always excluded
        for enemy in [Enemy.OLD_MAN, Enemy.BOMB_UPGRADER, Enemy.MUGGER]:
            self.assertFalse(_is_eligible(enemy, False),
                             f"{enemy.name} should be excluded")
            self.assertFalse(_is_eligible(enemy, True),
                             f"{enemy.name} should be excluded even with shuffle_gannon")

        # Normal enemies: always included regardless of shuffle_gannon
        for enemy in [Enemy.STALFOS, Enemy.RED_LANMOLA, Enemy.WALLMASTER]:
            self.assertTrue(_is_eligible(enemy, False),
                            f"{enemy.name} should be eligible")

    def test_group_members_preserved_after_shuffle(self):
        """Mixed-group enemies (is_group=True) must retain their group_members
        list after shuffling, since EnemySpec requires exactly 8 members."""
        for seed in [42, 999]:
            with self.subTest(seed=seed):
                gw = _load_game_world()
                config = GameConfig(shuffle_dungeon_monsters=True)
                shuffle_monsters(gw, config, SeededRng(seed))

                for level in gw.levels:
                    for room in level.rooms:
                        spec = room.enemy_spec
                        if spec.is_group:
                            self.assertIsNotNone(
                                spec.group_members,
                                f"L{level.level_num} room {room.room_num}: "
                                f"is_group=True but group_members is None",
                            )
                            self.assertEqual(
                                len(spec.group_members), 8,
                                f"L{level.level_num} room {room.room_num}: "
                                f"group_members has {len(spec.group_members)} entries, "
                                f"expected 8",
                            )

    def test_gannon_room_wall_fix_applied(self):
        """After shuffle, the Gannon room in levels 7-9 should have its
        wall/palette bytes modified by _fix_gannon_room_walls — specifically,
        enemy count bits should be maxed out for non-door groups."""
        def _room_t0(room):
            return (room.walls.north.value << 5) | (room.walls.south.value << 2) | room.palette_0

        def _room_t1(room):
            return (room.walls.west.value << 5) | (room.walls.east.value << 2) | room.palette_1

        for seed in [42, 999]:
            with self.subTest(seed=seed):
                gw = _load_game_world()
                config = GameConfig(shuffle_dungeon_monsters=True)
                shuffle_monsters(gw, config, SeededRng(seed))

                for level in gw.levels:
                    if level.level_num < 7:
                        continue
                    for room in level.rooms:
                        if room.enemy_spec.enemy != Enemy.THE_BEAST:
                            continue

                        t0 = _room_t0(room)
                        t1 = _room_t1(room)

                        # For each table byte, groups that aren't 1 (door)
                        # or 4 (locked door) should have bits maxed.
                        for label, t in [("t0", t0), ("t1", t1)]:
                            group1 = (t >> 2) & 7
                            group2 = (t >> 5) & 7
                            if group1 != 1 and group1 != 4:
                                self.assertEqual(
                                    t & 0x1C, 0x1C,
                                    f"Seed {seed}, L{level.level_num} room "
                                    f"{room.room_num}: {label} group1 bits not maxed "
                                    f"(group1={group1}, byte=0x{t:02X})",
                                )
                            if group2 != 1 and group2 != 4:
                                self.assertEqual(
                                    t & 0xE0, 0xE0,
                                    f"Seed {seed}, L{level.level_num} room "
                                    f"{room.room_num}: {label} group2 bits not maxed "
                                    f"(group2={group2}, byte=0x{t:02X})",
                                )

    def test_shuffle_returns_true_for_normal_seeds(self):
        """shuffle_monsters should return True (success) for normal seeds.
        Returning False means the retry budget was exhausted."""
        for seed in [1, 42, 100, 999, 12345]:
            with self.subTest(seed=seed):
                gw = _load_game_world()
                config = GameConfig(shuffle_dungeon_monsters=True)
                result = shuffle_monsters(gw, config, SeededRng(seed))
                self.assertTrue(result, f"Seed {seed}: returned False (retry exhausted)")

    def test_gannon_adjacent_rooms_have_boss_cry(self):
        """In levels 7-9, rooms adjacent to the Gannon room should have
        boss_cry_1=True (if they belong to level 9's room set)."""
        from zora.data_model import Direction

        for seed in [42, 999]:
            with self.subTest(seed=seed):
                gw = _load_game_world()
                config = GameConfig(shuffle_dungeon_monsters=True)
                shuffle_monsters(gw, config, SeededRng(seed))

                level_9 = gw.levels[8]
                level_9_room_nums = {r.room_num for r in level_9.rooms}

                # Find Gannon rooms in levels 7-9
                for level in gw.levels:
                    if level.level_num < 7:
                        continue
                    room_by_num = {r.room_num: r for r in level.rooms}
                    for room in level.rooms:
                        if room.enemy_spec.enemy != Enemy.THE_BEAST:
                            continue
                        # Check adjacents
                        for d in (Direction.NORTH, Direction.SOUTH,
                                  Direction.EAST, Direction.WEST):
                            adj_num = room.room_num + d.value
                            if adj_num in level_9_room_nums:
                                adj = room_by_num.get(adj_num)
                                if adj is not None:
                                    self.assertTrue(
                                        adj.boss_cry_1,
                                        f"Seed {seed}, L{level.level_num}: "
                                        f"room {adj_num} adjacent to Gannon "
                                        f"room {room.room_num} missing boss_cry_1",
                                    )


if __name__ == '__main__':
    unittest.main()
