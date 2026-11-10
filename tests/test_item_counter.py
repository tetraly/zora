"""Item Counter (ZORA flag item_counter, version 22; asm/flags2/item-counter/, zora/generate/item_counter.py,
zora/rom/item_counter.py): the table's encoding, the tiles, which places count under each item shuffle, and the
table written into finished ROMs. tests/test_item_counter_emulator.py plays it."""
from functools import cache

import pytest

from tests.needs import needs_base_rom
from zora.flags import codec, zora_flags
from zora.flags.fields import ITEM_SHUFFLE_SCOPE, ItemShuffleScope, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.item_counter import counter_areas, dealt_hearts
from zora.generate.pipeline import Built, build, generate_rom, plan, with_item_counter
from zora.generate.places import read_item
from zora.model.enums import Item
from zora.rom import inventory
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.item_counter import (
    AREAS,
    CHEST,
    CHEST_TILE,
    COMMON_BACKGROUND,
    SLASH_TILE,
    TABLE,
    TABLE_SIZE,
    TILE_BYTES,
    CounterArea,
    table_bytes,
    tile_bytes,
    ware_place,
)

ON = zora_flags.encode(zora_flags.ZoraFlags(item_counter=ThreeState.ON))
SEEDS = range(3)
FIRST_QUEST_SPOTS = (3, 2, 2, 2, 2, 2, 2, 3, 2)       # levels 1-9 under Full: items and hearts
DEALT_SPOTS = (2, 1, 1, 1, 1, 1, 1, 2, 2)             # under Item Only, Within Each Dungeon and None
OVERWORLD_SPOTS = 3                                    # the white sword cave, the Armos and coast items


def with_scope(scope: ItemShuffleScope) -> str:
    flags = codec.decode(MVP_BASELINE_LEVEL_ENCODING_OFF)
    return codec.encode(flags.updated(options={ITEM_SHUFFLE_SCOPE.id: int(scope)}))


def test_the_field_is_version_22_and_off_by_default() -> None:
    field = next(field for field in zora_flags.FIELDS if field.name == zora_flags.ITEM_COUNTER_FIELD)
    assert field.version == 22
    assert zora_flags.ZoraFlags().item_counter is ThreeState.OFF
    assert zora_flags.decode(ON).item_counter is ThreeState.ON


def test_the_tiles() -> None:
    chest = tile_bytes(CHEST)
    assert len(chest) == TILE_BYTES
    assert chest[0] == 0 and chest[TILE_BYTES // 2] == 0          # the top row is black: off the rupee
    assert tile_bytes(["." * 8] * 8) == bytes(TILE_BYTES)
    assert (CHEST_TILE, SLASH_TILE) == (0x50, 0x51)


def test_the_tiles_are_blank_in_prg0() -> None:
    rom = remember_repo_base_rom()
    for tile in (CHEST_TILE, SLASH_TILE):
        start = COMMON_BACKGROUND + tile * TILE_BYTES
        assert rom[start:start + TILE_BYTES] == bytes(TILE_BYTES)


def test_the_table_encoding() -> None:
    areas = [CounterArea(inventory.room_flags(0), (0x5F, ware_place(1, 0)))]
    areas += [CounterArea(inventory.room_flags(level), (level,), (0x10, 0x20), 1) for level in range(1, AREAS)]
    table = table_bytes(areas)
    assert len(table) <= TABLE_SIZE
    block = table[table[0]:]
    assert list(block[:7]) == [0x7F, 0x06, 2, 0, 0, 0x5F, 0x88]
    level_9 = table[table[9]:]
    assert list(level_9[:8]) == [0x7F, 0x07, 1, 2, 1, 9, 0x10, 0x20]
    assert areas[9].total == 2


def test_the_table_refuses_what_it_cannot_show() -> None:
    with pytest.raises(ValueError):
        table_bytes([CounterArea(0x67F, tuple(range(16)))] * AREAS)
    with pytest.raises(ValueError):
        table_bytes([CounterArea(0x67F)] * (AREAS - 1))


@cache
def built(scope: ItemShuffleScope, seed: int) -> Built:
    return build(plan(with_scope(scope), seed, ON), remember_repo_base_rom())


@needs_base_rom
@pytest.mark.slow
@pytest.mark.parametrize("scope", [ItemShuffleScope.FULL, ItemShuffleScope.DUNGEON_ITEMS_ONLY,
                                   ItemShuffleScope.WITHIN_EACH_DUNGEON, ItemShuffleScope.NONE],
                         ids=["full", "item-only", "within-each-dungeon", "none"])
def test_the_counts_follow_the_deal(scope: ItemShuffleScope) -> None:
    """Full counts every heart container; the others count only the hearts the deal itself placed (the coast's),
    so every level keeps its first-quest count of dealt places."""
    for seed in SEEDS:
        made = built(scope, seed)
        assert made.result.item_shuffle_result is not None
        areas = counter_areas(made.world, made.places, made.plan.alternatives.item_deal,
                              dealt_hearts(made.result.item_shuffle_result))
        assert areas[0].total == OVERWORLD_SPOTS
        expected = FIRST_QUEST_SPOTS if scope is ItemShuffleScope.FULL else DEALT_SPOTS
        assert tuple(area.total for area in areas[1:]) == expected, (scope, seed)
        for level, area in enumerate(areas[1:], start=1):
            assert area.flags_address == inventory.room_flags(level)
            hearts = [place for place in made.places if place.level == level
                      and read_item(made.world, place) == Item.HEART_CONTAINER]
            if scope is not ItemShuffleScope.FULL and area.group:
                assert len(area.group) == len(hearts) > area.cap


@needs_base_rom
@pytest.mark.slow
def test_the_coast_heart_counts_where_it_lands() -> None:
    for seed in SEEDS:
        made = built(ItemShuffleScope.DUNGEON_ITEMS_ONLY, seed)
        assert made.result.item_shuffle_result is not None
        hearts = dealt_hearts(made.result.item_shuffle_result)
        assert sum(hearts.values()) <= 1
        areas = counter_areas(made.world, made.places, ItemShuffleScope.DUNGEON_ITEMS_ONLY, hearts)
        for level, count in hearts.items():
            assert any(read_item(made.world, place) == Item.HEART_CONTAINER and place.room_num in
                       areas[level].unique + areas[level].group for place in made.places if place.level == level)
            assert count == 1


@needs_base_rom
@pytest.mark.slow
def test_finished_roms_hold_the_table_only_with_the_flag() -> None:
    off = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 4, remember_repo_base_rom()).rom
    on = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 4, remember_repo_base_rom(), zora_flag_string=ON).rom
    config = with_item_counter(build(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 4, ON), remember_repo_base_rom()))
    assert on[TABLE:TABLE + len(config.item_counter_table)] == config.item_counter_table
    assert set(off[TABLE:TABLE + TABLE_SIZE]) == {0xFF}
    start = COMMON_BACKGROUND + CHEST_TILE * TILE_BYTES
    assert off[start:start + 2 * TILE_BYTES] == bytes(2 * TILE_BYTES)
    assert on[start:start + TILE_BYTES] == tile_bytes(CHEST)
    assert not with_item_counter(build(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 4), remember_repo_base_rom())) \
        .item_counter_table
