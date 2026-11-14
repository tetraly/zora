"""Item Counter (ZORA flag item_counter, version 22; asm/flags2/item-counter/, zora/generate/item_counter.py,
zora/rom/item_counter.py): the table's encoding, the chest tile, which places count under each item shuffle, and
the table written into finished ROMs, alone and beside the flags that draw tiles $50-$5F.
tests/test_item_counter_emulator.py plays it."""
from dataclasses import replace
from functools import cache

import pytest

from tests.needs import needs_base_rom
from zora.flags import codec, zora_flags
from zora.flags.fields import (
    CHANGE_HIDDEN_TILES,
    DUNGEON_LAYOUT_SOURCE,
    ITEM_SHUFFLE_SCOPE,
    DungeonLayoutSource,
    ItemShuffleScope,
    ThreeState,
)
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.item_counter import counter_areas
from zora.generate.pipeline import Built, build, generate_rom, plan, with_item_counter
from zora.rom import inventory
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.graphics_theme import RESERVED_BACKGROUND_TILES
from zora.rom.item_counter import (
    AREAS,
    CHEST,
    CHEST_TILE,
    COMMON_BACKGROUND,
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
FIRST_QUEST_SPOTS = (3, 2, 2, 2, 2, 2, 2, 3, 2)       # levels 1-9 under every shuffle: items and hearts
# The second quest's by CurLevel (the game shows levels 2-3, 4-5 and 7-8 swapped: 2-2-2-3-2-2-2-3-2 as shown)
SECOND_QUEST_SPOTS = (2, 2, 2, 2, 3, 2, 3, 2, 2)
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
    assert CHEST_TILE == 0x60


def test_the_chest_tile_is_blank_in_prg0_and_reserved() -> None:
    """$60 is blank in PRG0, past the tiles other flags draw ($30-$5F), and themes never write it."""
    rom = remember_repo_base_rom()
    start = COMMON_BACKGROUND + CHEST_TILE * TILE_BYTES
    assert rom[start:start + TILE_BYTES] == bytes(TILE_BYTES)
    assert CHEST_TILE in RESERVED_BACKGROUND_TILES and CHEST_TILE not in range(0x30, 0x60)


def test_the_table_encoding() -> None:
    areas = [CounterArea(inventory.room_flags(0), (0x5F, ware_place(1, 0)))]
    areas += [CounterArea(inventory.room_flags(level), (level, 0x10, 0x20)) for level in range(1, AREAS)]
    table = table_bytes(areas)
    assert len(table) <= TABLE_SIZE
    block = table[table[0]:]
    assert list(block[:5]) == [0x7F, 0x06, 2, 0x5F, 0x88]
    level_9 = table[table[9]:]
    assert list(level_9[:6]) == [0x7F, 0x07, 3, 9, 0x10, 0x20]
    assert areas[9].total == 3


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
def test_every_shuffle_counts_every_level_place(scope: ItemShuffleScope) -> None:
    """Every shuffle counts each level's item places, heart containers included, so the levels' totals follow the
    dungeon layout alone, the first quest's here, whatever the shuffle (a shuffle rolled at random stays hidden)."""
    for seed in SEEDS:
        made = built(scope, seed)
        areas = counter_areas(made.places)
        assert areas[0].total == OVERWORLD_SPOTS
        assert tuple(area.total for area in areas[1:]) == FIRST_QUEST_SPOTS, (scope, seed)
        for level, area in enumerate(areas[1:], start=1):
            assert area.flags_address == inventory.room_flags(level)
            assert area.places == tuple(place.room_num for place in made.places if place.level == level)


@needs_base_rom
@pytest.mark.slow
@pytest.mark.parametrize("scope", [ItemShuffleScope.FULL, ItemShuffleScope.DUNGEON_ITEMS_ONLY],
                         ids=["full", "item-only"])
def test_second_quest_dungeons_count_their_own_places(scope: ItemShuffleScope) -> None:
    """With the second quest's dungeons, each level counts its own places: the second quest's totals."""
    flags = codec.encode(codec.decode(with_scope(scope)).updated(
        options={DUNGEON_LAYOUT_SOURCE.id: int(DungeonLayoutSource.SECOND_QUEST)}))
    for seed in SEEDS:
        made = build(plan(flags, seed, ON), remember_repo_base_rom())
        assert tuple(area.total for area in counter_areas(made.places)[1:]) == SECOND_QUEST_SPOTS, (scope, seed)


@needs_base_rom
@pytest.mark.slow
def test_finished_roms_hold_the_table_only_with_the_flag() -> None:
    off = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 4, remember_repo_base_rom()).rom
    on = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 4, remember_repo_base_rom(), zora_flag_string=ON).rom
    config = with_item_counter(build(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 4, ON), remember_repo_base_rom()))
    assert on[TABLE:TABLE + len(config.item_counter_table)] == config.item_counter_table
    assert set(off[TABLE:TABLE + TABLE_SIZE]) == {0xFF}
    start = COMMON_BACKGROUND + CHEST_TILE * TILE_BYTES
    assert off[start:start + TILE_BYTES] == bytes(TILE_BYTES)
    assert on[start:start + TILE_BYTES] == tile_bytes(CHEST)
    assert not with_item_counter(build(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 4), remember_repo_base_rom())) \
        .item_counter_table


@needs_base_rom
@pytest.mark.slow
def test_beside_change_hidden_ow_tiles_and_pegasus_boots() -> None:
    """Change Hidden OW Tiles draws $50-$5F and Pegasus Boots needs $50/$51 blank: with both on, the counter
    still generates, their tiles $50-$5F are as without it, and $60 holds the chest."""
    hidden = codec.encode(codec.decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(
        toggles={CHANGE_HIDDEN_TILES: ThreeState.ON}))
    boots = zora_flags.ZoraFlags(pegasus_boots=ThreeState.ON)
    without = generate_rom(hidden, 4, remember_repo_base_rom(), zora_flag_string=zora_flags.encode(boots)).rom
    with_counter = generate_rom(hidden, 4, remember_repo_base_rom(), zora_flag_string=zora_flags.encode(
        replace(boots, item_counter=ThreeState.ON))).rom
    others = slice(COMMON_BACKGROUND + 0x50 * TILE_BYTES, COMMON_BACKGROUND + CHEST_TILE * TILE_BYTES)
    assert with_counter[others] == without[others] != bytes(0x10 * TILE_BYTES)
    start = COMMON_BACKGROUND + CHEST_TILE * TILE_BYTES
    assert with_counter[start:start + TILE_BYTES] == tile_bytes(CHEST)
