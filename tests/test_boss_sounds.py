"""PS-MONRD-07, the boss-sound end pass (zora/generate/boss_sounds.py): only Ganon's level-9
neighbours keep a boss sound, sound 1, whatever wrote one before: the map move carrying a level-9
roar away from Ganon (SH-MAP-06; the phantom roar, player report, beta 8) and PRG0's own sounds left
beside a moved boss when the late gate is skipped (VA-REJ-02); the finished ROM ships exactly that."""
import pytest

from tests.needs import needs_base_rom, needs_encoder
from zora.flags.zora_flags import GatekeeperBosses, ZoraFlags, encode
from zora.generate.boss_sounds import GATEKEEPER_SOUNDS, boss_sound_problems, check_boss_sounds
from zora.generate.pipeline import build, finish, plan
from zora.model import room_grid
from zora.model.enums import BossSound, Enemy, Item, RoomAction, Side
from zora.model.game_world import GameWorld
from zora.model.levels import Level
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom

# The player's seed (ZORA 2.0 beta 8, 491d4a8): Ganon in level 9's room $01; the map stood in $02,
# beside him, and its move to $54 took $02's roar along, so $54 roared with no boss near.
PLAYER_FLAGS, PLAYER_ZORA_FLAGS, PLAYER_SEED = "oIbnPfPb01Hll3D295I4j47jt9sOjmOASP4MD", "9.7N7lgdC", 399448364
PLAYER_GANON_ROOM, PLAYER_PHANTOM_ROOM = 0x01, 0x54
# The same on the MVP baseline with level encoding off: the map move carried the roar to $15
MAP_MOVE_FLAGS, MAP_MOVE_SEED, MAP_MOVE_PHANTOM_ROOM = "8hq4BeR1JXo89BJ2!TFpTP02u8UJ3A", 5, 0x15
# Every set vanilla (Mixed Quest) and Dungeon Room Shuffle at Vanilla: no late gate, and the monster
# re-deal moved the bosses away from the first quest's own roars in level 8's $3B and $3D (beside
# $3C) and level 9's $43 (beside Ganon's $42)
NO_GATE_FLAGS, NO_GATE_ZORA_FLAGS, NO_GATE_SEED = "HOex8H7vIa1XhP3Ix!9gqr6n8aBeih", "3.6!CBH", 15030716473229726510
NO_GATE_STRAYS = ((8, 0x3B), (8, 0x3D), (9, 0x43))
# PS-MONRD-07's Check string where the late gate does not run (C14 = 0, C02 = 0, B32 and B33 on)
REFERENCE_NO_GATE_FLAGS = "8hq4BeQou4cxYVgPqbtlBZYk41PJ07"


def built_world(flags: str, seed: int, zora_flags: str = "") -> GameWorld:
    return build(plan(flags, seed, zora_flags), remember_repo_base_rom()).world


def ganon_neighbors(level: Level) -> set[int]:
    ganon = next(room.room_num for room in level.rooms if room.enemy == Enemy.THE_BEAST)
    return {number for side in Side if (number := room_grid.neighbor(ganon, side)) in level.room_nums}


def roaring_rooms(level: Level) -> set[int]:
    return {room.room_num for room in level.rooms if room.boss_sound != BossSound.NONE}


@needs_base_rom
@needs_encoder
def test_the_players_seed_roars_only_beside_ganon() -> None:
    level_9 = built_world(PLAYER_FLAGS, PLAYER_SEED, PLAYER_ZORA_FLAGS).levels[8]
    assert ganon_neighbors(level_9) == {0x00, 0x02, 0x11}
    assert next(room.room_num for room in level_9.rooms if room.enemy == Enemy.THE_BEAST) == PLAYER_GANON_ROOM
    assert roaring_rooms(level_9) == ganon_neighbors(level_9)
    assert PLAYER_PHANTOM_ROOM not in roaring_rooms(level_9)


@needs_base_rom
def test_the_map_move_leaves_the_roar_beside_ganon() -> None:
    gw = built_world(MAP_MOVE_FLAGS, MAP_MOVE_SEED)
    assert roaring_rooms(gw.levels[8]) == ganon_neighbors(gw.levels[8])
    assert MAP_MOVE_PHANTOM_ROOM not in roaring_rooms(gw.levels[8])
    assert not boss_sound_problems(gw)


@needs_base_rom
def test_a_skipped_gate_keeps_no_sound_beside_a_moved_boss() -> None:
    gw = built_world(NO_GATE_FLAGS, NO_GATE_SEED, NO_GATE_ZORA_FLAGS)
    assert not boss_sound_problems(gw)
    assert all(gw.levels[level_num - 1].block.room(number).boss_sound == BossSound.NONE
               for level_num, number in NO_GATE_STRAYS)
    assert not any(roaring_rooms(level) for level in gw.levels[:8])


@needs_base_rom
@pytest.mark.parametrize("flags", [MAP_MOVE_FLAGS, REFERENCE_NO_GATE_FLAGS])
def test_the_finished_rom_ships_the_end_pass_boss_sounds(flags: str) -> None:
    """PS-MONRD-07's Result, read back from the finished ROM: sound 1 on Ganon's level-9 neighbours in
    both quests' levels 7-9 blocks (the unused quest's PRG0 level 9 too), none anywhere else; Ganon's
    room holds item byte $8E and trigger byte $03."""
    base = remember_repo_base_rom()
    for seed in range(1, 4):
        world = parse_rom(finish(build(plan(flags, seed), base), base))
        assert not boss_sound_problems(world)
        for block in (world.blocks[1], world.blocks_2q[1]):
            ganons = [room for room in block.rooms if room.monster_byte == Enemy.THE_BEAST]
            assert ganons
            for room in ganons:
                assert room.item_byte == 0x8E and room.item == Item.TRIFORCE_OF_POWER and room.is_dark
                assert room.trigger_byte == RoomAction.LAST_BOSS
        assert all(room.boss_sound == BossSound.NONE for block in (world.blocks[0], world.blocks_2q[0])
                   for room in block.rooms)


@needs_base_rom
def test_the_check_rejects_any_other_boss_sound() -> None:
    gw = built_world(MAP_MOVE_FLAGS, MAP_MOVE_SEED)
    check_boss_sounds(gw)
    gw.levels[8].block.room(MAP_MOVE_PHANTOM_ROOM).boss_sound = BossSound.ROAR_AQUAMENTUS_GLEEOK_GANON
    with pytest.raises(AssertionError, match=r"block 7-9: room \$15"):
        check_boss_sounds(gw)


@needs_base_rom
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_a_gatekeepers_neighbours_roar_with_its_own_sound(seed: int) -> None:
    """Gatekeeper Bosses (owner decision 8, docs/zora-extras.md section 19): in levels 1-8 the rooms
    beside each gatekeeper roar with its boss's own sound, never Ganon's sound 1 (Aquamentus and Gleeok,
    whose own sound it is, and Moldorm and Lanmola stay silent); level 9 still roars only beside Ganon."""
    gatekeepers = encode(ZoraFlags(gatekeeper_bosses=GatekeeperBosses.ANYWHERE))
    gw = built_world(MAP_MOVE_FLAGS, seed, gatekeepers)
    assert not boss_sound_problems(gw)
    for level in gw.levels[:8]:
        gatekeeper = level.gatekeeper_room
        assert gatekeeper is not None
        boss = level.block.room(gatekeeper).enemy
        beside = {number for side in Side if (number := room_grid.neighbor(gatekeeper, side)) in level.room_nums}
        sound = GATEKEEPER_SOUNDS.get(boss, BossSound.NONE)
        assert sound != BossSound.ROAR_AQUAMENTUS_GLEEOK_GANON
        assert {room.room_num: room.boss_sound for room in level.rooms if room.boss_sound != BossSound.NONE} == (
            dict.fromkeys(beside, sound) if sound != BossSound.NONE else {})
        assert level.boss_room == gatekeeper
    assert roaring_rooms(gw.levels[8]) == ganon_neighbors(gw.levels[8])
