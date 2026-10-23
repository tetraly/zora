"""The Uphill Battle set's off values (the 2026-10-22 export, review 68), on generated seeds, each
checked against its entry's Check:

  - Shuffle Level 9 Monsters off (B35; PS-MONLV-07): level 9 keeps PRG0's enemy bank, and every
    Wizzrobe room is in a level with the tier-2 bank.
  - Shuffle Ganon and Zelda off (B33; PS-MONRD-04): Zelda in layout $27, Ganon in $28 with $8E and
    trigger 3; no $28 room in levels 1-8.
  - Force Ganon Fight off (B18; PS-MONRD-05, VA-REJ-03 step 8): Ganon's room is the only level-9
    room with trigger 3; Ganon is still reached and beaten before the last-boss shutters open (E10);
    ZORA makes no stray trigger write (owner ruling).
  - Shuffle Dungeon Monsters off (B32; PS-MONRD-06): FL-DEP-02 rule 3's coin; with B33 and B36 off
    too, the levels keep PRG0's enemy banks and Zelda and Ganon their shape-stage rooms.
  - Add 2nd Quest Rooms off (B20; SH-ROOM-09): none of the eleven second-quest-only layouts.
  - Shuffle Overworld Group off (B43; PS-EGRP-07): no overworld enemy in a dungeon room, no dungeon
    enemy on an overworld screen, PRG0's item-carrier operands and overworld enemy tiles.
  - Each "?" resolves both ways, and all six at "?" generate."""
from functools import cache

import pytest

from tests.needs import needs_base_rom
from zora.flags.codec import decode, encode
from zora.flags.dependencies import meet_monster_prerequisite
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.acceptance_check import AcceptanceCheck
from zora.generate.pipeline import Built, build, finish, plan, shipped_logic_rules
from zora.generate.rng import Rng
from zora.generate.steps.shuffle_enemy_groups import (
    ENEMY_BANK_FIRST_TILE,
    OVERWORLD_BANK_OFFSET,
    OVERWORLD_BANK_TILES,
    OVERWORLD_MONSTERS,
)
from zora.model.enums import Enemy, RoomAction
from zora.model.game_world import GameWorld
from zora.model.levels import GANON_LIST, LEVEL_9, ZELDA_LIST
from zora.model.sprites import TILE_BYTES, PatternBlock
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom

pytestmark = needs_base_rom

OFF, POSSIBLE = ThreeState.OFF, ThreeState.POSSIBLE
SEEDS = range(1, 5)
ZELDA_LAYOUT, GANON_LAYOUT = 0x27, 0x28
GANON_ITEM_BYTE = 0x8E
SECOND_QUEST_ONLY_LAYOUTS = frozenset({0x0B, 0x10, 0x41, 0x46, 0x47, 0x4C, 0x4D, 0x51, 0x5C, 0x5F, 0x60})
WIZZROBES = (Enemy.BLUE_WIZZROBE, Enemy.RED_WIZZROBE)
DUNGEON_ENEMIES = frozenset({Enemy.ZOL, Enemy.RED_GORIYA, Enemy.BLUE_GORIYA, Enemy.RED_DARKNUT, Enemy.BLUE_DARKNUT,
                             Enemy.VIRE, Enemy.POLS_VOICE, Enemy.LIKE_LIKE, *WIZZROBES, Enemy.WALLMASTER,
                             Enemy.ROPE, Enemy.STALFOS, Enemy.GIBDO, Enemy.RED_LANMOLA, Enemy.BLUE_LANMOLA})


def flags(**toggles: ThreeState) -> str:
    return encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(toggles=toggles))


@cache
def built(flag_string: str, seed: int) -> Built:
    return build(plan(flag_string, seed), remember_repo_base_rom())


@cache
def shipped(flag_string: str, seed: int) -> GameWorld:
    """The finished ROM, parsed back."""
    return parse_rom(finish(built(flag_string, seed), remember_repo_base_rom()))


@cache
def base_world() -> GameWorld:
    return parse_rom(remember_repo_base_rom())


def level_rooms(world: GameWorld, level_num: int) -> list:
    level = next(level for level in world.levels if level.level_num == level_num)
    return [level.block.room(number) for number in level.room_nums]


def zelda_and_ganon(world: GameWorld) -> tuple:
    rooms = level_rooms(world, LEVEL_9)
    return (next(room for room in rooms if room.enemy == ZELDA_LIST),
            next(room for room in rooms if room.monster_byte == GANON_LIST))


def bank(world: GameWorld, level_num: int) -> object:
    return next(level for level in world.levels if level.level_num == level_num).enemy_sprite_set


@pytest.mark.parametrize("seed", SEEDS)
def test_level_9_monsters_off_keeps_level_9_s_bank_and_its_wizzrobes(seed: int) -> None:
    world = shipped(flags(B35=OFF), seed)
    assert bank(world, LEVEL_9) == bank(base_world(), LEVEL_9)
    tier_2 = bank(base_world(), LEVEL_9)
    for level_num in range(1, 10):
        if any(room.enemy in WIZZROBES and not room.has_monster_bit for room in level_rooms(world, level_num)):
            assert bank(world, level_num) == tier_2, level_num


@pytest.mark.parametrize("seed", SEEDS)
def test_ganon_and_zelda_off_keep_their_shape_stage_rooms(seed: int) -> None:
    world = shipped(flags(B33=OFF), seed)
    zelda, ganon = zelda_and_ganon(world)
    assert (zelda.layout_code, ganon.layout_code) == (ZELDA_LAYOUT, GANON_LAYOUT)
    assert ganon.item_info.item_byte == GANON_ITEM_BYTE and ganon.room_action == RoomAction.LAST_BOSS
    assert all(room.layout_code != GANON_LAYOUT for level_num in range(1, 9)
               for room in level_rooms(world, level_num))


@pytest.mark.parametrize("seed", SEEDS)
def test_force_ganon_fight_off_walls_nothing_around_zelda(seed: int) -> None:
    flag_string = flags(B18=OFF)
    world = shipped(flag_string, seed)
    _zelda, ganon = zelda_and_ganon(world)
    assert ganon.item_info.item_byte == GANON_ITEM_BYTE
    assert [room for room in level_rooms(world, LEVEL_9) if room.room_action == RoomAction.LAST_BOSS] == [ganon]
    # Ganon is still reached and beaten before his shutters open (E10), and every item collected (E1)
    seed_built = built(flag_string, seed)
    result = seed_built.result
    assert result.item_shuffle_result is not None and result.overworld is not None
    check = AcceptanceCheck(seed_built.world.levels, result.item_shuffle_result, seed_built.world.overworld,
                            result.overworld, shipped_logic_rules(seed_built.plan, seed_built.world))
    assert check.collects_everything() and check.reaches_ganon_before_shutters_open()


@pytest.mark.parametrize("seed", SEEDS)
def test_no_stray_trigger_write(seed: int) -> None:
    """Owner ruling 2026-10-22: the second-quest block's room $17 keeps its trigger."""
    world = shipped(flags(B18=OFF), seed)
    for block, base_block in zip(world.blocks, base_world().blocks, strict=True):
        if block not in [level.block for level in world.levels]:
            assert block.room(0x17).room_action == base_block.room(0x17).room_action


def test_rule_3_s_coin_turns_b32_on_or_b33_and_b36_off() -> None:
    """FL-DEP-02 rule 3: equal chance, and afterwards B32 off never comes with B33 or B36 on."""
    settings = decode(flags(B32=OFF))
    outcomes = set()
    for seed in range(40):
        met = meet_monster_prerequisite(settings, Rng(seed))
        outcomes.add(met.is_on("B32"))
        assert met.is_on("B32") or not (met.is_on("B33") or met.is_on("B36"))
    assert outcomes == {True, False}
    assert {plan(flags(B32=OFF), seed).alternatives.shuffle_dungeon_monsters for seed in range(20)} == {True, False}


@pytest.mark.parametrize("seed", SEEDS)
def test_dungeon_monsters_off_keeps_the_banks_and_the_bosses(seed: int) -> None:
    world = shipped(flags(B32=OFF, B33=OFF, B36=OFF), seed)
    assert [bank(world, level) for level in range(1, 10)] == [bank(base_world(), level) for level in range(1, 10)]
    zelda, ganon = zelda_and_ganon(world)
    assert (zelda.layout_code, ganon.layout_code) == (ZELDA_LAYOUT, GANON_LAYOUT)


@pytest.mark.parametrize("seed", SEEDS)
def test_second_quest_rooms_off_draws_no_second_quest_only_layout(seed: int) -> None:
    world = shipped(flags(B20=OFF), seed)
    layouts = {room.room_type for level_num in range(1, 10) for room in level_rooms(world, level_num)}
    assert not layouts & SECOND_QUEST_ONLY_LAYOUTS


@pytest.mark.parametrize("seed", SEEDS)
def test_overworld_group_off_keeps_the_overworld_apart(seed: int) -> None:
    world = shipped(flags(B43=OFF), seed)
    for level_num in range(1, 10):
        assert not any(room.enemy in OVERWORLD_MONSTERS and not room.has_monster_bit
                       for room in level_rooms(world, level_num)), level_num
    assert not any(screen.enemy_spec.enemy in DUNGEON_ENEMIES for screen in world.overworld.screens)
    assert world.item_carrier_operands == base_world().item_carrier_operands
    assert not world.overworld_wizzrobe_patch
    for tile in OVERWORLD_BANK_TILES:              # the overworld group's packed tiles
        offset = OVERWORLD_BANK_OFFSET + (tile - ENEMY_BANK_FIRST_TILE) * TILE_BYTES
        assert (world.sprites.read_tiles(PatternBlock.OWSP, offset, 1)
                == base_world().sprites.read_tiles(PatternBlock.OWSP, offset, 1)), tile


@pytest.mark.parametrize("field_id", ["B18", "B20", "B32", "B33", "B35", "B43"])
def test_each_random_comes_up_both_ways(field_id: str) -> None:
    resolved = {plan(flags(**{field_id: POSSIBLE}), seed).settings.is_on(field_id) for seed in range(16)}
    assert resolved == {True, False}


@pytest.mark.parametrize("seed", (1, 2))
def test_all_six_at_random_generate(seed: int) -> None:
    flag_string = flags(B18=POSSIBLE, B20=POSSIBLE, B32=POSSIBLE, B33=POSSIBLE, B35=POSSIBLE, B43=POSSIBLE)
    assert shipped(flag_string, seed).levels
