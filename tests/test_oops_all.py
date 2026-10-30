"""Oops All Enemies and Oops All Bosses (docs/design/oops-all.md; zora/generate/steps/oops_all.py):
the version-5 fields and the tab, the room and list rewrite, the family's tiles, the overworld
redraw, the Dodongo placement with its boss blocks, and a finished ROM with both on."""
import copy
from functools import cache

import pytest

from zora.flags import zora_flags
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import OopsAllBosses, OopsAllEnemies, ZoraFlags
from zora.flags.zora_form import zora_flags_from_values, zora_metadata, zora_state
from zora.generate.errors import GenerationFailure
from zora.generate.pipeline import extra_options, generate_rom, plan
from zora.generate.rng import Rng
from zora.generate.steps.group_banks import OVERWORLD, Staged
from zora.generate.steps.oops_all import (
    DODONGO,
    FAMILIES,
    FAMILY_SPRITES,
    REWRITTEN_ENEMIES,
    _read_positions,
    dungeon_list_codes,
    family_slots,
    list_starts,
    oops_all_bosses,
    oops_all_enemies,
    overworld_list_codes,
    redraw_overworld,
    rewrite_lists,
    rewrite_rooms,
    stage_family_tiles,
)
from zora.generate.steps.randomize_boss_groups import BOSS_BLOCKS, DODONGOS, OLD_BOSS_GROUPS, is_boss_pick_barred
from zora.generate.steps.shuffle_enemy_groups import (
    BRACELET_SCREENS,
    ENEMY_BANK_BLOCKS,
    ENEMY_OBJECTS,
    GORIYA_FALLBACK_TILE,
    GORIYA_TILE_OFFSET,
    RESERVED_LIST_BYTES,
    EnemyDeal,
)
from zora.model.enums import BossSpriteSet, Enemy, RoomType
from zora.model.game_world import GameWorld
from zora.model.rooms import EnemyInfo, LayoutInfo
from zora.model.sprites import TILE_BYTES, PatternBlock
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

E = Enemy
FAMILY_CHOICES = tuple(FAMILIES)
FIRST_ENEMY_TILE, BOSS_FIRST_TILE = 158, 192


@cache
def _base_world() -> GameWorld:
    return parse_rom(remember_repo_base_rom())


def base_world() -> GameWorld:
    """A fresh copy of the parsed base ROM."""
    return copy.deepcopy(_base_world())


# --- the fields ------------------------------------------------------------------------------

def test_both_fields_are_version_5_and_off_by_default() -> None:
    added = {field.name: field for field in zora_flags.FIELDS if field.version == 5}
    assert {name: field.slots for name, field in added.items()} == {"oops_all_enemies": 4, "oops_all_bosses": 2}
    up_to_5 = tuple(field for field in zora_flags.FIELDS if field.version <= 5)
    assert up_to_5[-2:] == tuple(added.values())                       # appended last in version 5
    assert (ZoraFlags().oops_all_enemies, ZoraFlags().oops_all_bosses) == (OopsAllEnemies.OFF, OopsAllBosses.OFF)
    assert [int(value) for value in OopsAllEnemies] == [0, 1, 2, 3]


OLDER_FLAGS = (ZoraFlags(), ZoraFlags(randomize_letter=True), ZoraFlags(shop_items_in_pool=True),
               ZoraFlags(randomize_dead_woods=ThreeState.POSSIBLE),
               ZoraFlags(progressive_items=True, add_l4_sword=ThreeState.ON, l4_sword_in_level_2=True,
                         level_9_entrance_sword=True))


def test_older_strings_keep_their_meaning_and_spelling() -> None:
    """Each older version's string decodes with both extras Off and keeps its version."""
    for flags in OLDER_FLAGS:
        older = zora_flags.encode(flags)
        assert zora_flags.decode(older) == flags
        assert older == "" or int(older.split(".")[0]) < 5
    assert zora_flags.encode(ZoraFlags(randomize_letter=True)) == "1.2"


@pytest.mark.parametrize("enemies", list(OopsAllEnemies))
@pytest.mark.parametrize("bosses", list(OopsAllBosses))
def test_each_value_round_trips(enemies: OopsAllEnemies, bosses: OopsAllBosses) -> None:
    flags = ZoraFlags(oops_all_enemies=enemies, oops_all_bosses=bosses)
    text = zora_flags.encode(flags)
    assert zora_flags.decode(text) == flags
    assert text.startswith("5.") or (enemies, bosses) == (OopsAllEnemies.OFF, OopsAllBosses.OFF)
    controls = {"oops_all_enemies": str(int(enemies)), "oops_all_bosses": str(int(bosses))}
    assert zora_flags_from_values(controls) == text
    state = zora_state(text, None)
    assert (state["values"]["oops_all_enemies"], state["values"]["oops_all_bosses"]) == (enemies, bosses)


def test_the_tab_shows_both_with_their_values_and_help() -> None:
    fields = {field["name"]: field for field in zora_metadata()["fields"]}
    assert [value["label"] for value in fields["oops_all_enemies"]["values"]] == \
        ["Off", "Wizzrobes", "Keese", "Bouncers"]
    assert [value["label"] for value in fields["oops_all_bosses"]["values"]] == ["Off", "Dodongos"]
    assert (fields["oops_all_enemies"]["label"], fields["oops_all_bosses"]["label"]) == \
        ("Oops All Enemies", "Oops All Bosses")
    assert all(fields[name]["help"] for name in ("oops_all_enemies", "oops_all_bosses"))


def test_the_extras_reach_the_generation_on_their_own_stream() -> None:
    text = zora_flags.encode(ZoraFlags(oops_all_enemies=OopsAllEnemies.KEESE, oops_all_bosses=OopsAllBosses.DODONGOS))
    chosen = plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 7, text)
    extras = extra_options(chosen)
    assert (extras.oops_all_enemies, extras.oops_all_bosses) == (OopsAllEnemies.KEESE, OopsAllBosses.DODONGOS)
    assert extras.oops_all_seed == zora_flags.oops_all_seed(7, chosen.flag_string, text)
    assert extras.oops_all_seed not in (7, chosen.generation_seed)
    assert not extra_options(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 7)).oops_all


# --- the rooms and the lists -----------------------------------------------------------------

@pytest.mark.parametrize("choice", FAMILY_CHOICES)
def test_single_type_rooms_take_the_family_and_keep_their_counts(choice: OopsAllEnemies) -> None:
    world = base_world()
    before = {(level.level_num, room.room_num): room.enemy_info for level in world.levels for room in level.rooms}
    rewritten = rewrite_rooms(world.levels, FAMILIES[choice], Rng(1))
    drawn = set()
    for level in world.levels:
        for room in level.rooms:
            old = before[level.level_num, room.room_num]
            if old.enemy in REWRITTEN_ENEMIES and not old.has_monster_bit:
                assert room.enemy in FAMILIES[choice] and room.count_index == old.count_index
                drawn.add(room.enemy)
            else:                      # bosses, people, traps, lists, the goriya, Zelda, Ganon, empty
                assert room.enemy_info == old
    assert drawn == set(FAMILIES[choice])                 # every member is drawn somewhere
    assert rewritten == sum(1 for old in before.values() if old.enemy in REWRITTEN_ENEMIES)


@pytest.mark.parametrize("choice", FAMILY_CHOICES)
def test_the_dungeon_lists_take_the_family_and_the_overworld_lists_stay(choice: OopsAllEnemies) -> None:
    world, staged = base_world(), Staged()
    original = bytes(world.enemies.mixed_enemy_data)
    rewrite_lists(world, world.levels, world.overworld, FAMILIES[choice], Rng(1), staged)
    assert staged.mixed_lists is not None
    starts = list_starts(world)
    dungeon = _read_positions(dungeon_list_codes(world.levels), starts, len(original))
    overworld = _read_positions(overworld_list_codes(world.overworld, staged), starts, len(original))
    values = {enemy.value for enemy in FAMILIES[choice]}
    for position, (old, new) in enumerate(zip(original, staged.mixed_lists, strict=True)):
        if position in dungeon and old not in RESERVED_LIST_BYTES:
            assert new in values
        else:
            assert new == old, position
    assert overworld and not dungeon & overworld - {p for p in overworld if original[p] in RESERVED_LIST_BYTES}


def test_the_lists_start_from_shuffle_enemy_groups_lists() -> None:
    world, staged = base_world(), Staged()
    staged.mixed_lists = bytearray(world.enemies.mixed_enemy_data)
    staged.mixed_lists[0] = 0x07                              # an overworld list's byte B42 changed
    rewrite_lists(world, world.levels, world.overworld, FAMILIES[OopsAllEnemies.KEESE], Rng(1), staged)
    assert staged.mixed_lists[0] == 0x07


# --- the tiles ---------------------------------------------------------------------------------

def _staged_tile(staged: Staged, block: PatternBlock, offset: int) -> bytes:
    return [data for staged_block, staged_offset, data in staged.tiles
            if (staged_block, staged_offset) == (block, offset)][-1]


@pytest.mark.parametrize("choice", [OopsAllEnemies.WIZZROBES, OopsAllEnemies.BOUNCERS])
def test_the_family_draws_from_the_same_tiles_in_every_enemy_bank(choice: OopsAllEnemies) -> None:
    world, staged = base_world(), Staged()
    slots = stage_family_tiles(world, choice, staged)
    assert max(tile for tiles in slots.values() for tile in tiles) == 191
    for enemy, tiles in slots.items():
        sprite_object = ENEMY_OBJECTS[enemy]
        source = world.sprites.read_tiles(*sprite_object.source, sprite_object.tiles)
        for bank in ENEMY_BANK_BLOCKS.values():
            assert [_staged_tile(staged, bank, (tile - FIRST_ENEMY_TILE) * TILE_BYTES) for tile in tiles] == source
        offset, count = sprite_object.frames
        frames = [staged.frames[offset + step] for step in range(count)]
        assert min(frames) == tiles[0] and max(frames) <= tiles[-1]


def test_red_wizzrobe_draws_as_blue_and_the_goriya_takes_its_tile() -> None:
    world = base_world()
    staged = Staged()
    oops_all_enemies(world, world.levels, world.overworld, None, OopsAllEnemies.WIZZROBES, Rng(1), staged)
    assert [staged.frames[140 + step] for step in range(4)] == [staged.frames[136 + step] for step in range(4)]
    assert staged.frames[GORIYA_TILE_OFFSET] == family_slots(OopsAllEnemies.WIZZROBES)[E.BLUE_WIZZROBE][0]
    staged = Staged()
    oops_all_enemies(world, world.levels, world.overworld, None, OopsAllEnemies.BOUNCERS, Rng(1), staged)
    assert staged.frames[GORIYA_TILE_OFFSET] == GORIYA_FALLBACK_TILE     # neither is a goriya candidate


def test_keese_need_no_sprite_work() -> None:
    world, staged = base_world(), Staged()
    oops_all_enemies(world, world.levels, world.overworld, None, OopsAllEnemies.KEESE, Rng(1), staged)
    assert FAMILY_SPRITES[OopsAllEnemies.KEESE] == ()
    assert staged.tiles == [] and staged.frames == {}


# --- the overworld ---------------------------------------------------------------------------------

def test_the_family_leaves_the_overworld_group() -> None:
    """B42 dealt the Wizzrobes into its overworld group: the screens and list bytes holding them
    get the group's other members, never a blue Moblin on a bracelet screen."""
    world = base_world()
    deal = EnemyDeal(order=[], seed=E.ZOL, groups={0: [], 1: [], 2: [],
                                                   OVERWORLD: [E.BLUE_WIZZROBE, E.BLUE_MOBLIN, E.STALFOS]})
    staged = Staged(red_wizzrobe_overworld=True)
    bracelet = min(BRACELET_SCREENS)
    staged.overworld_monsters = {bracelet: E.RED_WIZZROBE, 0x40: E.BLUE_WIZZROBE, 0x41: E.STALFOS}
    staged.mixed_lists = bytearray(world.enemies.mixed_enemy_data)
    starts = list_starts(world)
    overworld = _read_positions(overworld_list_codes(world.overworld, staged), starts, len(staged.mixed_lists))
    for position in sorted(overworld)[:6]:
        if staged.mixed_lists[position] not in RESERVED_LIST_BYTES:
            staged.mixed_lists[position] = E.RED_WIZZROBE.value
    family = FAMILIES[OopsAllEnemies.WIZZROBES]
    for seed in range(20):
        result = copy.deepcopy(staged)
        redraw_overworld(world, world.overworld, deal, family, Rng(seed), result)
        # PS-EGRP-05 bars only the blue Moblin there; the red one joins as its partner
        assert result.overworld_monsters[bracelet] in (E.RED_MOBLIN, E.STALFOS)
        assert result.overworld_monsters[0x40] in (E.BLUE_MOBLIN, E.RED_MOBLIN, E.STALFOS)
        assert result.overworld_monsters[0x41] == E.STALFOS
        assert result.mixed_lists is not None
        assert not {value.value for value in family} & {result.mixed_lists[p] for p in overworld}
        assert not result.red_wizzrobe_overworld


def test_no_other_overworld_enemy_restarts() -> None:
    world = base_world()
    deal = EnemyDeal(order=[], seed=E.ZOL, groups={0: [], 1: [], 2: [], OVERWORLD: [E.POLS_VOICE]})
    staged = Staged(overworld_monsters={0x40: E.POLS_VOICE}, mixed_lists=bytearray(world.enemies.mixed_enemy_data))
    with pytest.raises(GenerationFailure):
        redraw_overworld(world, world.overworld, deal, FAMILIES[OopsAllEnemies.BOUNCERS], Rng(1), staged)


# --- Oops All Bosses ---------------------------------------------------------------------------

def _boss_sets(world: GameWorld) -> dict[int, BossSpriteSet]:
    return {level.level_num: level.boss_sprite_set for level in world.levels}


def test_every_boss_room_that_allows_dodongos_gets_them() -> None:
    world, staged = base_world(), Staged()
    before = {(level.level_num, room.room_num): room.enemy_info for level in world.levels for room in level.rooms}
    placed = oops_all_bosses(world, world.levels, _boss_sets(world), None, Rng(3), staged)
    variants = set()
    for level in world.levels:
        for room in level.rooms:
            old = before[level.level_num, room.room_num]
            if level.level_num <= 8 and old.enemy in OLD_BOSS_GROUPS:
                assert room.enemy_info in (EnemyInfo(E.TRIPLE_DODONGO), EnemyInfo(E.SINGLE_DODONGO))
                variants.add(room.enemy)
            else:                      # level 9's bosses, Ganon and every other room stay
                assert room.enemy_info == old
    assert variants == set(DODONGOS)
    assert placed == sum(1 for (level_num, _room), old in before.items()
                         if level_num <= 8 and old.enemy in OLD_BOSS_GROUPS)
    assert staged.boss_sprite_sets == {}                       # no level 1-8 on block C here


def _dodongo_run(staged: Staged) -> list[int]:
    offset, count = DODONGO.frames
    lowest = min(staged.frames[offset + step] for step in range(count))
    return list(range(lowest, lowest + DODONGO.tiles))


def test_dodongo_goes_into_blocks_a_and_b_at_its_vanilla_tiles() -> None:
    world, staged = base_world(), Staged()
    oops_all_bosses(world, world.levels, _boss_sets(world), None, Rng(3), staged)
    source = world.sprites.read_tiles(*DODONGO.source, DODONGO.tiles)
    run = _dodongo_run(staged)
    assert run == list(range(220, 256))
    for block in (PatternBlock.BOSS1257, PatternBlock.BOSS3468):
        assert [_staged_tile(staged, block, (tile - BOSS_FIRST_TILE) * TILE_BYTES) for tile in run] == source
    offset, count = DODONGO.frames
    assert [staged.frames[offset + step] for step in range(count)] == world.enemies.frame_bytes(offset, count)


def test_a_level_on_block_c_moves_to_a_and_a_kept_boss_keeps_its_tiles() -> None:
    """Level 4 on block C, with a Patra in a T room (Dodongo-barred): the level moves to block A,
    Patra's tiles (248-255 in block C) are copied there, and Dodongo's run avoids them."""
    world, staged = base_world(), Staged()
    level = world.levels[3]
    room = next(room for room in level.rooms if room.enemy in OLD_BOSS_GROUPS)
    room.enemy_info, room.layout_info = EnemyInfo(E.PATRA_1), LayoutInfo(RoomType.T_ROOM)
    boss_sets = _boss_sets(world) | {4: BossSpriteSet.C}
    oops_all_bosses(world, world.levels, boss_sets, None, Rng(3), staged)
    assert room.enemy == E.PATRA_1
    assert staged.boss_sprite_sets == {4: BossSpriteSet.A}
    run = _dodongo_run(staged)
    assert not set(run) & set(range(248, 256)) and run[0] % 2 == 0
    patra = world.sprites.read_tiles(BOSS_BLOCKS[2], (248 - BOSS_FIRST_TILE) * TILE_BYTES, 8)
    assert [_staged_tile(staged, BOSS_BLOCKS[0], (tile - BOSS_FIRST_TILE) * TILE_BYTES)
            for tile in range(248, 256)] == patra


def test_no_room_for_dodongo_beside_a_kept_boss_restarts() -> None:
    """A kept Gleeok in block B (tiles 192-223 and 238-239) leaves no 36-tile run."""
    world = base_world()
    level = world.levels[2]                                       # level 3, block B
    room = next(room for room in level.rooms if room.enemy in OLD_BOSS_GROUPS)
    room.enemy_info, room.layout_info = EnemyInfo(E.GLEEOK_2), LayoutInfo(RoomType.CIRCLE_WALL)
    assert is_boss_pick_barred(E.TRIPLE_DODONGO, RoomType.CIRCLE_WALL, False)
    with pytest.raises(GenerationFailure):
        oops_all_bosses(world, world.levels, _boss_sets(world), None, Rng(3), Staged())


def test_kept_bosses_share_a_tile_by_its_home_never_by_its_bytes() -> None:
    """Levels 1 and 2 (both block A) keep Aquamentus (block A, tiles 192-211) and Gleeok (block B,
    192-223): both need tiles 192-211 in block A. Equal bytes in both blocks still restart, so the
    player's graphics (Halloween Mode's art, a graphics hack) never change a seed's game."""
    world = base_world()
    for level, boss in ((world.levels[0], E.AQUAMENTUS), (world.levels[1], E.GLEEOK_2)):
        room = next(room for room in level.rooms if room.enemy in OLD_BOSS_GROUPS)
        room.enemy_info, room.layout_info = EnemyInfo(boss), LayoutInfo(RoomType.T_ROOM)
    assert {level.boss_sprite_set for level in world.levels[:2]} == {BossSpriteSet.A}
    same = bytes(range(TILE_BYTES))
    for block in (PatternBlock.BOSS1257, PatternBlock.BOSS3468):
        for tile in range(BOSS_FIRST_TILE, 212):
            world.sprites.write_tile(block, (tile - BOSS_FIRST_TILE) * TILE_BYTES, same)
    with pytest.raises(GenerationFailure, match="two kept bosses need one tile"):
        oops_all_bosses(world, world.levels, _boss_sets(world), None, Rng(3), Staged())


# --- a finished ROM ----------------------------------------------------------------------------

@pytest.mark.parametrize("enemies", [OopsAllEnemies.WIZZROBES, OopsAllEnemies.BOUNCERS])
def test_a_finished_rom(enemies: OopsAllEnemies) -> None:
    """Both extras on: every regular room holds the family, every list a dungeon room names reads
    only the family or reserved bytes, the family's tiles are in all three enemy banks, levels
    1-8 draw Dodongos from block A or B, and every boss room that allows Dodongos holds them."""
    text = zora_flags.encode(ZoraFlags(oops_all_enemies=enemies, oops_all_bosses=OopsAllBosses.DODONGOS))
    world = parse_rom(generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 3, remember_repo_base_rom(),
                                   zora_flag_string=text).rom)
    base = _base_world()
    family = FAMILIES[enemies]
    starts = list_starts(world)
    dungeon = _read_positions(dungeon_list_codes(world.levels), starts, len(world.enemies.mixed_enemy_data))
    assert {world.enemies.mixed_enemy_data[p] for p in dungeon} <= {e.value for e in family} | RESERVED_LIST_BYTES
    for enemy, tiles in family_slots(enemies).items():
        sprite_object = ENEMY_OBJECTS[enemy]
        source = base.sprites.read_tiles(*sprite_object.source, sprite_object.tiles)
        for bank in ENEMY_BANK_BLOCKS.values():
            assert world.sprites.read_tiles(bank, (tiles[0] - FIRST_ENEMY_TILE) * TILE_BYTES, len(tiles)) == source
    offset, count = DODONGO.frames
    lowest = min(world.enemies.frame_bytes(offset, count))
    dodongo = base.sprites.read_tiles(*DODONGO.source, DODONGO.tiles)
    for block in (PatternBlock.BOSS1257, PatternBlock.BOSS3468):
        assert world.sprites.read_tiles(block, (lowest - BOSS_FIRST_TILE) * TILE_BYTES, DODONGO.tiles) == dodongo
    for level in world.levels:
        for room in level.rooms:
            if not room.has_monster_bit and room.enemy in REWRITTEN_ENEMIES:
                assert room.enemy in family
            if level.level_num <= 8 and room.enemy in OLD_BOSS_GROUPS:
                allowed = any(not is_boss_pick_barred(pick, room.room_type, room.movable_block) for pick in DODONGOS)
                assert room.enemy in DODONGOS or not allowed
        if level.level_num <= 8:
            assert level.boss_sprite_set is not BossSpriteSet.C


def test_the_spoiler_log_names_them_only_when_set() -> None:
    """A seed without Oops keeps its seed document; with it, the settings list names the value."""
    from zora_export.seed_document import zora_entry_shown, zora_entry_text
    off = ZoraFlags()
    assert not zora_entry_shown(off, "oops_all_enemies") and not zora_entry_shown(off, "oops_all_bosses")
    flags = ZoraFlags(oops_all_enemies=OopsAllEnemies.BOUNCERS, oops_all_bosses=OopsAllBosses.DODONGOS)
    assert [zora_entry_text(flags, name) for name in ("oops_all_enemies", "oops_all_bosses")] == \
        ["bouncers", "dodongos"]
