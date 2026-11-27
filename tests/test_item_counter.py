"""Item Counter (ZORA flag item_counter, version 22; asm/flags2/item-counter/, zora/generate/item_counter.py,
zora/rom/item_counter.py): the table's encoding, the chest and slash tiles, which places count under each item
shuffle and each combination of Triforce Shuffle and Map & Compass Shuffle (places, not items: the pool's places,
plus each level's Triforce spot unless Triforce Shuffle is Anywhere; maps and compasses only with Map & Compass
Shuffle: Anywhere), and the table written into finished ROMs, alone and beside Change Hidden OW Tiles and Pegasus
Boots. tests/test_item_counter_emulator.py plays it."""
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
from zora.flags.zora_flags import LevelItemShuffle
from zora.generate.item_counter import counter_areas
from zora.generate.pipeline import Built, build, generate_rom, plan, with_item_counter
from zora.generate.places import triforce_spot_rooms
from zora.rom import hidden_tiles, inventory
from zora.rom.archipelago_logo import LOGO_BACKGROUND_TILES
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.graphics_theme import RESERVED_BACKGROUND_TILES
from zora.rom.item_counter import (
    AREAS,
    CHEST,
    CHEST_TILE,
    COMMON_BACKGROUND,
    SLASH,
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
# Levels 1-9 under every item shuffle, with Map & Compass Shuffle Off or Between levels: items, hearts and levels
# 1-8's Triforce spot
FIRST_QUEST_SPOTS = (4, 3, 3, 3, 3, 3, 3, 4, 2)
# The second quest's by CurLevel (the game shows levels 2-3, 4-5 and 7-8 swapped: 3-3-3-4-3-3-3-4-2 as shown)
SECOND_QUEST_SPOTS = (3, 3, 3, 3, 4, 3, 4, 3, 2)
MAP_AND_COMPASS = 2                                    # each level's, with Map & Compass Shuffle: Anywhere
OVERWORLD_SPOTS = 3                                    # the white sword cave, the Armos and coast items
SHUFFLES = tuple(LevelItemShuffle)


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
    assert (CHEST_TILE, SLASH_TILE) == (0x52, 0x53)
    slash = tile_bytes(SLASH)
    assert not any(slash[TILE_BYTES // 2:])                       # color 1 only: the font's white


def test_the_tiles_are_blank_in_prg0_and_reserved() -> None:
    """$52 and $53 are blank in PRG0, clear of the tiles other flags draw (the bosses' and the hidden squares'
    $30-$4F, Pegasus Boots' blank $50/$51, the logo's $5C-$5F), and themes never write them."""
    rom = remember_repo_base_rom()
    for tile in (CHEST_TILE, SLASH_TILE):
        start = COMMON_BACKGROUND + tile * TILE_BYTES
        assert rom[start:start + TILE_BYTES] == bytes(TILE_BYTES)
        assert tile in RESERVED_BACKGROUND_TILES and tile not in range(0x30, 0x52)
        assert tile not in LOGO_BACKGROUND_TILES


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


def table_totals(table: bytes) -> tuple[int, ...]:
    """Each area's total, as the patch reads it: the block's third byte."""
    return tuple(table[table[area] + 2] for area in range(AREAS))


@needs_base_rom
@pytest.mark.slow
@pytest.mark.parametrize("scope", [ItemShuffleScope.FULL, ItemShuffleScope.DUNGEON_ITEMS_ONLY,
                                   ItemShuffleScope.WITHIN_EACH_DUNGEON, ItemShuffleScope.NONE],
                         ids=["full", "item-only", "within-each-dungeon", "none"])
def test_every_shuffle_counts_every_level_place(scope: ItemShuffleScope) -> None:
    """Every item shuffle counts each level's item places, heart containers included, and its Triforce spot, so the
    levels' totals follow the dungeon layout alone, the first quest's here, whatever the shuffle (a shuffle rolled
    at random stays hidden)."""
    for seed in SEEDS:
        made = built(scope, seed)
        spots = triforce_spot_rooms(made.world)
        areas = counter_areas(made.places, piece_spots=spots)
        assert areas[0].total == OVERWORLD_SPOTS
        assert tuple(area.total for area in areas[1:]) == FIRST_QUEST_SPOTS, (scope, seed)
        assert table_totals(with_item_counter(made).item_counter_table) == (OVERWORLD_SPOTS, *FIRST_QUEST_SPOTS)
        for level, area in enumerate(areas[1:], start=1):
            assert area.flags_address == inventory.room_flags(level)
            own = tuple(place.room_num for place in made.places if place.level == level)
            assert area.places == own + ((spots[level],) if level in spots else ())


def level_totals(flags: str, triforces: LevelItemShuffle, maps_compasses: LevelItemShuffle,
                 seed: int) -> tuple[int, ...]:
    zora = zora_flags.encode(zora_flags.ZoraFlags(item_counter=ThreeState.ON, triforce_shuffle=triforces,
                                                  map_compass_shuffle=maps_compasses))
    table = with_item_counter(build(plan(flags, seed, zora), remember_repo_base_rom())).item_counter_table
    return table_totals(table)[1:]


def expected_totals(spots: tuple[int, ...], maps_compasses: LevelItemShuffle) -> tuple[int, ...]:
    """The levels' totals: the layout's spots, plus the map and compass with Map & Compass Shuffle: Anywhere."""
    extra = MAP_AND_COMPASS if maps_compasses is LevelItemShuffle.ANYWHERE else 0
    return tuple(total + extra for total in spots)


@needs_base_rom
@pytest.mark.slow
@pytest.mark.parametrize("triforces", SHUFFLES, ids=[value.name.lower() for value in SHUFFLES])
@pytest.mark.parametrize("maps_compasses", SHUFFLES, ids=[value.name.lower() for value in SHUFFLES])
@pytest.mark.parametrize("quest", ["first", "second"])
def test_the_totals_under_each_level_item_shuffle(quest: str, maps_compasses: LevelItemShuffle,
                                                 triforces: LevelItemShuffle) -> None:
    """Places, not items (rule of 2026-11-26): the first quest's levels read 4-3-3-3-3-3-3-4-2 with Map & Compass
    Shuffle Off or Between levels and 6-5-5-5-5-5-5-6-4 with Anywhere, whatever Triforce Shuffle says (its pieces'
    spots count as pool places with Anywhere, as spots of their own otherwise); the second quest the same way."""
    flags = with_scope(ItemShuffleScope.FULL)
    spots = FIRST_QUEST_SPOTS
    if quest == "second":
        flags = codec.encode(codec.decode(flags).updated(
            options={DUNGEON_LAYOUT_SOURCE.id: int(DungeonLayoutSource.SECOND_QUEST)}))
        spots = SECOND_QUEST_SPOTS
    for seed in SEEDS[:2]:
        assert level_totals(flags, triforces, maps_compasses, seed) == expected_totals(spots, maps_compasses), \
            (quest, triforces, maps_compasses, seed)


@needs_base_rom
@pytest.mark.slow
def test_finished_roms_hold_the_table_only_with_the_flag() -> None:
    off = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 4, remember_repo_base_rom()).rom
    on = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 4, remember_repo_base_rom(), zora_flag_string=ON).rom
    config = with_item_counter(build(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 4, ON), remember_repo_base_rom()))
    assert on[TABLE:TABLE + len(config.item_counter_table)] == config.item_counter_table
    assert set(off[TABLE:TABLE + TABLE_SIZE]) == {0xFF}
    for tile, drawing in ((CHEST_TILE, CHEST), (SLASH_TILE, SLASH)):
        start = COMMON_BACKGROUND + tile * TILE_BYTES
        assert off[start:start + TILE_BYTES] == bytes(TILE_BYTES)
        assert on[start:start + TILE_BYTES] == tile_bytes(drawing)
    assert not with_item_counter(build(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 4), remember_repo_base_rom())) \
        .item_counter_table


@needs_base_rom
@pytest.mark.slow
def test_beside_change_hidden_ow_tiles_and_pegasus_boots() -> None:
    """Change Hidden OW Tiles shares $30-$3F with the bosses and Pegasus Boots needs $50/$51 blank: with both on,
    the counter still generates, the squares' copy is as without it, $50/$51 stay blank, and $52/$53 hold the
    chest and slash."""
    hidden = codec.encode(codec.decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(
        toggles={CHANGE_HIDDEN_TILES: ThreeState.ON}))
    boots = zora_flags.ZoraFlags(pegasus_boots=ThreeState.ON)
    without = generate_rom(hidden, 4, remember_repo_base_rom(), zora_flag_string=zora_flags.encode(boots)).rom
    with_counter = generate_rom(hidden, 4, remember_repo_base_rom(), zora_flag_string=zora_flags.encode(
        replace(boots, item_counter=ThreeState.ON))).rom
    squares = slice(hidden_tiles.SQUARES_COPY, hidden_tiles.SQUARES_COPY + hidden_tiles.BOSS_TILES_SIZE)
    assert with_counter[squares] == without[squares] == hidden_tiles.marked_tile_bytes()
    blank_pair = slice(COMMON_BACKGROUND + 0x50 * TILE_BYTES, COMMON_BACKGROUND + CHEST_TILE * TILE_BYTES)
    assert with_counter[blank_pair] == without[blank_pair] == bytes(2 * TILE_BYTES)
    for tile, drawing in ((CHEST_TILE, CHEST), (SLASH_TILE, SLASH)):
        start = COMMON_BACKGROUND + tile * TILE_BYTES
        assert with_counter[start:start + TILE_BYTES] == tile_bytes(drawing)
