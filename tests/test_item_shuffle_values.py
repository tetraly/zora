"""Item Shuffle's other values: None (C06 = 0, PS-ITEM-10), Item Only (C06 = 1, PS-ITEM-09) and
Random (C06 = 4, PS-ITEM-11). The flag tables, the plan, and the deal on synthetic levels run
without the ROM; the finished-ROM checks at the end need the base ROM. The corpus figures come
from `python3 scripts/compare_corpus.py --set c06-none` (and c06-itemonly, c06-random)."""
from collections import Counter
from functools import cache
from types import SimpleNamespace
from typing import cast

import pytest

from zora import archipelago
from zora.archipelago import OptionsConflict, flag_strings
from zora.flags import form as flag_form
from zora.flags.codec import decode, encode
from zora.flags.fields import DUNGEON_LAYOUT_SOURCE, ITEM_SHUFFLE_SCOPE, DungeonLayoutSource, ItemShuffleScope
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.support import Support, support, unsupported_fields
from zora.generate.alternative_values import AlternativeValues
from zora.generate.context import GenerationContext
from zora.generate.extra_options import NO_EXTRAS
from zora.generate.generation_pass import item_shuffle_options, shuffle_items_step
from zora.generate.pipeline import generate_rom, plan
from zora.generate.rng import ScriptedRng
from zora.generate.shapes.tables import cellar_items
from zora.generate.steps.dungeon_quest import ALL_SHAPES, SetSource
from zora.generate.steps.item_shuffle_result import ItemShuffleOptions, ItemShuffleResult
from zora.generate.steps.shuffle_items import (
    POOL_ORDER,
    VANILLA_POOL_ORDER,
    keep_items_in_place,
    shuffle_items,
    vanilla_start_values,
)
from zora.model.enums import BossSpriteSet, Direction, EnemySpriteSet, Item, RoomType
from zora.model.game_world import GameWorld
from zora.model.levels import Level, LevelBlock
from zora.model.rooms import ITEM_MASK, ItemInfo, StaircaseRoom
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora_measure.checkpoints.dungeon_quest import item_invariants, set_sources
from zora_measure.checkpoints.item_shuffle import (
    ITEM_ONLY_FLAGS,
    NO_ITEM_SHUFFLE_FLAGS,
    RANDOM_ITEM_SHUFFLE_FLAGS,
    cave_items_kept,
    dungeon_hearts,
    hearts_in_all,
    progression_items_once_in_levels,
    two_hearts_in_caves,
)

NEW_VALUES = {NO_ITEM_SHUFFLE_FLAGS: ItemShuffleScope.NONE, ITEM_ONLY_FLAGS: ItemShuffleScope.DUNGEON_ITEMS_ONLY,
              RANDOM_ITEM_SHUFFLE_FLAGS: ItemShuffleScope.RANDOM}
PRG0_CAVES = {"armos": Item.POWER_BRACELET, "white_sword": Item.WHITE_SWORD, "coast": Item.HEART_CONTAINER}
needs_rom = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")


# --- the flag string and the support matrix (FL-SUP-01, FL-SUP-02) ---------------------------------

@pytest.mark.parametrize("flags", list(NEW_VALUES))
def test_the_corpus_strings_are_cp5_with_only_c06_changed(flags: str) -> None:
    settings = decode(flags)
    assert settings.option(ITEM_SHUFFLE_SCOPE) == NEW_VALUES[flags]
    assert encode(settings) == flags
    assert settings == decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(options={ITEM_SHUFFLE_SCOPE: NEW_VALUES[flags]})


@pytest.mark.parametrize("flags", list(NEW_VALUES))
def test_each_value_is_supported_alone(flags: str) -> None:
    """FL-SUP-01: every value of C06 is supported; Random because each of 0 to 3 is."""
    assert support(decode(flags))[ITEM_SHUFFLE_SCOPE.id] is Support.SUPPORTED
    assert unsupported_fields(decode(flags)) == []
    assert set(flag_form.supported_values(ITEM_SHUFFLE_SCOPE)) == set(ItemShuffleScope)


# --- the plan (FL-DEP-04, PS-ITEM-11) ---------------------------------------------------------------

@pytest.mark.parametrize("flags", [NO_ITEM_SHUFFLE_FLAGS, ITEM_ONLY_FLAGS])
def test_the_plan_carries_the_scope(flags: str) -> None:
    alternatives = plan_alternatives(flags, 1)
    assert alternatives == AlternativeValues(item_shuffle=NEW_VALUES[flags])
    assert not alternatives.shuffle_items_within_levels


def test_random_scope_draws_each_value_once_per_seed() -> None:
    """PS-ITEM-11: C06 = 4 resolves per seed to 0, 1, 2 or 3 with equal chance."""
    drawn: Counter[ItemShuffleScope] = Counter()
    for seed in range(1, 401):
        scope = plan_alternatives(RANDOM_ITEM_SHUFFLE_FLAGS, seed).item_shuffle
        assert plan_alternatives(RANDOM_ITEM_SHUFFLE_FLAGS, seed).item_shuffle is scope
        drawn[scope] += 1
    assert set(drawn) == {ItemShuffleScope.NONE, ItemShuffleScope.DUNGEON_ITEMS_ONLY,
                          ItemShuffleScope.WITHIN_EACH_DUNGEON, ItemShuffleScope.FULL}
    assert all(60 < count < 140 for count in drawn.values()), drawn


def test_default_plans_are_unchanged() -> None:
    alternatives = plan_alternatives(MVP_BASELINE_LEVEL_ENCODING_OFF, 1)
    assert alternatives == AlternativeValues() and alternatives.item_shuffle is ItemShuffleScope.FULL


def plan_alternatives(flags: str, seed: int) -> AlternativeValues:
    return plan(flags, seed).alternatives


@pytest.mark.parametrize("scope", list(ItemShuffleScope)[:4])
def test_mixed_quest_deals_under_none(scope: ItemShuffleScope) -> None:
    """PS-ITEM-10's exception: under Mixed Quest (C02 = 2) None deals as Item Only; every other
    scope, and None under every other dungeon quest, deals as chosen."""
    for quest in list(DungeonLayoutSource)[:5]:
        deal = AlternativeValues(item_shuffle=scope, dungeon_quest=quest).item_deal
        mixed_none = scope is ItemShuffleScope.NONE and quest is DungeonLayoutSource.MIXED
        assert deal is (ItemShuffleScope.DUNGEON_ITEMS_ONLY if mixed_none else scope)


# --- the deal on synthetic levels -------------------------------------------------------------------

def _level(num: int, block: LevelBlock, room_nums: list[int]) -> Level:
    return Level(
        level_num=num, entrance_room=room_nums[0], entrance_direction=Direction.SOUTH, palette_raw=b"",
        fade_palette_raw=b"", staircase_room_pool=[], room_nums=room_nums, staircase_nums=[], block=block,
        boss_room=0xFF, enemy_sprite_set=EnemySpriteSet.A, boss_sprite_set=BossSpriteSet.A, start_y=0,
        item_position_table=[0] * 4, map_start=0, map_cursor_offset=0, map_data=b"", map_ppu_commands=b"",
        qty_table=[0, 2, 4, 8], stairway_data_raw=b"",
    )


def _toy_levels() -> list[Level]:
    """Level 1 owns rooms 0-5: the wood boomerang in room 0, heart containers in rooms 1 and 4, the
    bow in an item cellar returning to room 2, nothing elsewhere."""
    block = LevelBlock.blank()
    level = _level(1, block, [0, 1, 2, 3, 4, 5])
    for room in level.rooms:
        room.item_info = ItemInfo(Item.NOTHING)
    block.room(0).item = Item.WOOD_BOOMERANG
    block.room(1).item = Item.HEART_CONTAINER
    block.room(4).item = Item.HEART_CONTAINER
    block[6] = StaircaseRoom(room_num=6, room_type=RoomType.ITEM_STAIRCASE, exit_x=6, exit_y=9,
                             item=Item.BOW, return_dest=2)
    return [level]


def _contents(levels: list[Level], state: ItemShuffleResult) -> dict[str, int]:
    block = levels[0].block
    cellar = block.staircase(6).item
    assert cellar is not None
    return {"room 0": int(block.room(0).item), "room 1": int(block.room(1).item), "room 4": int(block.room(4).item),
            "cellar": int(cellar), **{slot: int(item) for slot, item in state.caves.items()}}


def test_none_writes_the_pool_back_without_a_deal() -> None:
    """PS-ITEM-10: the pool is built and written back, every place keeps its content, no number is
    drawn, and the fifteen records name where the items are; the heart rooms are not pooled."""
    levels = _toy_levels()
    state = ItemShuffleResult(caves=dict(PRG0_CAVES))
    before = _contents(levels, state)
    keep_items_in_place(levels, state, ItemShuffleOptions(coast_item=5))   # a pin forces nothing either
    assert _contents(levels, state) == before
    assert state.item_shuffle_iterations == 0
    assert state.pool_size == 5                                  # boomerang, bow, three cave slots
    assert not state.heart_rooms_pooled
    assert [(place.item, place.level, place.slot) for place in state.tracked] == [
        (Item.WOOD_BOOMERANG, 1, None), (Item.BOW, 1, None), (Item.POWER_BRACELET, None, "armos"),
        (Item.WHITE_SWORD, None, "white_sword"), (Item.HEART_CONTAINER, None, "coast")]


def test_item_only_deals_the_fifteen_places_and_leaves_the_heart_rooms() -> None:
    """PS-ITEM-09: the deal of PS-ITEM-01 over the fifteen places alone; the heart rooms keep their
    heart containers, the coast heart can move."""
    levels = _toy_levels()
    state = ItemShuffleResult(caves=dict(PRG0_CAVES))
    # pool: boomerang (room 0), bow (cellar), armos, white sword, coast; position 0 takes the coast
    shuffle_items(levels, state, ScriptedRng([4, 0, 0, 0, 0]), ItemShuffleOptions(dungeon_hearts=False))
    contents = _contents(levels, state)
    assert contents["room 1"] == contents["room 4"] == Item.HEART_CONTAINER
    assert state.pool_size == 5 and not state.heart_rooms_pooled
    assert sorted(contents[place] for place in ("room 0", "cellar", "armos", "white_sword", "coast")) == sorted(
        [Item.WOOD_BOOMERANG, Item.BOW, Item.POWER_BRACELET, Item.WHITE_SWORD, Item.HEART_CONTAINER])
    assert contents["coast"] == Item.WOOD_BOOMERANG and contents["room 0"] == Item.HEART_CONTAINER


def test_full_scope_still_pools_the_heart_rooms() -> None:
    """PS-ITEM-02, unchanged: under full scope the two heart rooms join (seven places)."""
    levels = _toy_levels()
    state = ItemShuffleResult(caves=dict(PRG0_CAVES))
    shuffle_items(levels, state, ScriptedRng([0] * 7), ItemShuffleOptions())
    assert state.pool_size == 7 and state.heart_rooms_pooled


def _context(scope: ItemShuffleScope, quest: DungeonLayoutSource, rng: ScriptedRng) -> GenerationContext:
    """The parts of a generation attempt the item step reads."""
    levels = _toy_levels()
    alternatives = AlternativeValues(item_shuffle=scope, dungeon_quest=quest)
    attempt = SimpleNamespace(settings=SimpleNamespace(alternatives=alternatives, extras=NO_EXTRAS),
                              sets=SimpleNamespace(levels=levels),
                              item_shuffle_result=ItemShuffleResult(caves=dict(PRG0_CAVES)), rng=rng,
                              set_sources=ALL_SHAPES)
    return cast(GenerationContext, attempt)


def test_the_step_draws_nothing_under_none() -> None:
    context = _context(ItemShuffleScope.NONE, DungeonLayoutSource.GENERATED_SHAPES, ScriptedRng([]))
    before = _contents(context.sets.levels, context.item_shuffle_result)
    shuffle_items_step(context)          # an exhausted ScriptedRng raises on any draw
    assert _contents(context.sets.levels, context.item_shuffle_result) == before
    assert not item_shuffle_options(context).dungeon_hearts


def test_the_step_deals_under_none_with_mixed_quest() -> None:
    """PS-ITEM-10's exception: the walk runs, as under Item Only (five draws, heart rooms out)."""
    rng = ScriptedRng([4, 0, 0, 0, 0])
    context = _context(ItemShuffleScope.NONE, DungeonLayoutSource.MIXED, rng)
    shuffle_items_step(context)
    contents = _contents(context.sets.levels, context.item_shuffle_result)
    assert contents["coast"] == Item.WOOD_BOOMERANG and contents["room 1"] == Item.HEART_CONTAINER
    assert context.item_shuffle_result.item_shuffle_iterations == 5


@pytest.mark.parametrize("scope, hearts", [(ItemShuffleScope.DUNGEON_ITEMS_ONLY, False),
                                           (ItemShuffleScope.WITHIN_EACH_DUNGEON, False),
                                           (ItemShuffleScope.FULL, True)])
def test_the_extras_pool_hearts_only_under_full_scope(scope: ItemShuffleScope, hearts: bool) -> None:
    """The ZORA extras' pool takes heart containers only where PS-ITEM-02 pooled them."""
    context = _context(scope, DungeonLayoutSource.GENERATED_SHAPES, ScriptedRng([]))
    assert item_shuffle_options(context).dungeon_hearts is hearts


# --- None with vanilla levels (PS-ITEM-10 and PS-VAN-03, 7372b34) ----------------------------------

def _with(scope: ItemShuffleScope, quest: DungeonLayoutSource) -> str:
    return encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(
        options={ITEM_SHUFFLE_SCOPE.id: scope, DUNGEON_LAYOUT_SOURCE.id: quest}))


@pytest.mark.parametrize("quest", list(DungeonLayoutSource))
@pytest.mark.parametrize("scope", list(ItemShuffleScope))
def test_every_scope_takes_every_dungeon_quest(scope: ItemShuffleScope, quest: DungeonLayoutSource) -> None:
    """The temporary refusal of None with vanilla levels is gone: the spec rules them (7372b34)."""
    assert plan(_with(scope, quest), 1).alternatives.dungeon_quest in (*DungeonLayoutSource,)


FIRST, SECOND = SetSource.FIRST_QUEST, SetSource.SECOND_QUEST
# PS-VAN-03's table: under C02 = 4 with both sets vanilla, the rooms whose start value is not PRG0's
STARTS_UNLIKE_PRG0 = {
    (FIRST, SECOND): {(1, 0x2B): Item.RED_CANDLE, (1, 0x70): Item.BOOK, (1, 0x76): Item.RED_RING,
                      (1, 0x77): Item.SILVER_ARROWS},
    (SECOND, FIRST): {(0, 0x15): Item.BOW, (0, 0x0B): Item.MAGICAL_BOOMERANG, (0, 0x7A): Item.RAFT,
                      (0, 0x6A): Item.LADDER, (0, 0x7F): Item.RECORDER, (0, 0x46): Item.WAND},
}
LEVEL_OF_SET = (1, 7)


def _prg0_items(sources: tuple[SetSource, SetSource]) -> dict[tuple[int, int], int]:
    """PRG0's item (low five bits) in each pool room of the two vanilla sets."""
    world = parse_rom(remember_repo_base_rom())
    items = {}
    for set_index, source in enumerate(sources):
        block = (world.blocks_2q[set_index] if source is SECOND
                 else world.levels[LEVEL_OF_SET[set_index] - 1].block)
        for room_num in VANILLA_POOL_ORDER[source, set_index]:
            items[set_index, room_num] = _item_at(block, room_num)
    return items


def _item_at(block: LevelBlock, room_num: int) -> int:
    cell = block.cells[room_num]
    if isinstance(cell, StaircaseRoom):
        assert cell.item is not None
        return int(cell.item) & ITEM_MASK
    return cell.item_info.item_code & ITEM_MASK


def test_a_shapes_set_keeps_what_its_places_hold() -> None:
    assert vanilla_start_values((SetSource.SHAPES, SECOND)) == {}
    assert vanilla_start_values((FIRST, SetSource.SHAPES)) == {}


@needs_rom
@pytest.mark.parametrize("sources", [(FIRST, FIRST), (SECOND, SECOND), (FIRST, SECOND), (SECOND, FIRST)])
def test_the_start_values_are_prg0s_but_for_the_spec_table(sources: tuple[SetSource, SetSource]) -> None:
    """PS-VAN-03: under C02 = 0 and 1 each start value is PRG0's item in that room; under C02 = 4
    the second-quest set's rooms start with first-quest values, unlike PRG0's exactly in the
    spec's table; each list holds the twelve items once."""
    start = vanilla_start_values(sources)
    assert sorted(start.values()) == sorted(Item(code) for code in POOL_ORDER)
    unlike = {place: value for place, value in start.items() if value != _prg0_items(sources)[place]}
    assert unlike == STARTS_UNLIKE_PRG0.get(sources, {})


def test_shapes_cellars_beside_a_second_quest_set_swap_the_book_and_wand() -> None:
    """SH-STAIR-03's mixed-quest cellars, beside a second-quest set only."""
    assert cellar_items(6) == [Item.WAND] and cellar_items(8) == [Item.BOOK, Item.MAGICAL_KEY]
    assert cellar_items(6, beside_second_quest=True) == [Item.BOOK]
    assert cellar_items(8, beside_second_quest=True) == [Item.WAND, Item.MAGICAL_KEY]
    assert cellar_items(5, beside_second_quest=True) == cellar_items(5)


# Rooms the drop shuffles re-deal (PS-ITEM-10's Check: the former boomerang rooms of levels 1 and 2)
BOOMERANG_ROOMS = {(FIRST, 0x44), (FIRST, 0x4F), (SECOND, 0x78), (SECOND, 0x15)}


@needs_rom
@pytest.mark.parametrize("quest", [DungeonLayoutSource.FIRST_QUEST, DungeonLayoutSource.SECOND_QUEST,
                                   DungeonLayoutSource.MIXED_WITH_SHAPES])
@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5, 6])
def test_none_with_vanilla_levels_writes_the_start_values(quest: DungeonLayoutSource, seed: int) -> None:
    """PS-ITEM-10 (7372b34): each pool room of a vanilla set holds its start value (PRG0's, or
    PS-VAN-03's under C02 = 4 with both sets vanilla) but for the former boomerang rooms, which the
    drop shuffles re-deal; each progression item once over the blocks in use and the caves."""
    gw = _finished(_with(ItemShuffleScope.NONE, quest), seed)
    assert item_invariants(gw)["twelve once"]
    sources = set_sources(gw)
    # with a shapes set beside it, a vanilla set starts with what it holds: PRG0's items
    expected = {place: int(value) for place, value in vanilla_start_values(sources).items()}
    for set_index, source in enumerate(sources):
        if not source.is_vanilla:
            continue
        if not expected:
            expected = _prg0_items((source, source))
        block = gw.levels[LEVEL_OF_SET[set_index] - 1].block
        for room_num in VANILLA_POOL_ORDER[source, set_index]:
            if (source, room_num) not in BOOMERANG_ROOMS:
                assert _item_at(block, room_num) == expected[set_index, room_num]


def test_item_onlys_page_note() -> None:
    assert (flag_form.VALUE_NOTES[(ITEM_SHUFFLE_SCOPE.id, ItemShuffleScope.DUNGEON_ITEMS_ONLY)]
            == "Major items only; Heart Containers stay in place")


# --- the page and Archipelago ----------------------------------------------------------------------

@pytest.mark.parametrize("flags", list(NEW_VALUES))
def test_the_page_offers_each_value(flags: str) -> None:
    state = flag_form.form_state(flags)
    assert not state["fields"][ITEM_SHUFFLE_SCOPE.id]["problem"]
    assert state["generateRefusals"] == []


@pytest.mark.parametrize("value", [ItemShuffleScope.NONE, ItemShuffleScope.DUNGEON_ITEMS_ONLY,
                                   ItemShuffleScope.RANDOM])
def test_archipelago_never_takes_the_new_values(value: ItemShuffleScope) -> None:
    """Item Shuffle is never offered and always Full (FIXED_OPTIONS), so its values are listed as
    not offered, never as held back for a scan."""
    assert ITEM_SHUFFLE_SCOPE.id in archipelago.NOT_OFFERED and ITEM_SHUFFLE_SCOPE.id not in archipelago.HELD_BACK
    with pytest.raises(OptionsConflict, match="C06"):
        flag_strings({ITEM_SHUFFLE_SCOPE.id: int(value)})


# --- finished ROMs (need the base ROM) --------------------------------------------------------------

@cache
def _finished(flags: str, seed: int) -> GameWorld:
    return parse_rom(generate_rom(flags, seed, remember_repo_base_rom()).rom)


@needs_rom
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_none_keeps_every_item_where_the_shapes_put_it(seed: int) -> None:
    """PS-ITEM-10's Check: the cave items PRG0's, each progression item once in the tables, eight
    heart containers there."""
    gw = _finished(NO_ITEM_SHUFFLE_FLAGS, seed)
    assert cave_items_kept(gw) and progression_items_once_in_levels(gw)
    assert dungeon_hearts(gw) == 8


@needs_rom
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_item_only_keeps_nine_hearts_and_at_most_one_in_the_caves(seed: int) -> None:
    """PS-ITEM-09's Check: nine heart containers; never two in the cave slots."""
    gw = _finished(ITEM_ONLY_FLAGS, seed)
    assert hearts_in_all(gw) and not two_hearts_in_caves(gw)
    assert dungeon_hearts(gw) in (8, 9)


@needs_rom
@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_random_scope_builds_its_drawn_value(seed: int) -> None:
    gw = _finished(RANDOM_ITEM_SHUFFLE_FLAGS, seed)
    assert hearts_in_all(gw)
    if plan_alternatives(RANDOM_ITEM_SHUFFLE_FLAGS, seed).item_shuffle is ItemShuffleScope.NONE:
        assert cave_items_kept(gw) and progression_items_once_in_levels(gw)
