"""Triforce Shuffle and Map & Compass Shuffle in single-player seeds (docs/design/archipelago-items.md piece 7):
BUILD, the level items' swaps (zora/generate/solo_assignment.py), then FINISH. Anywhere: Item Shuffle decides how far a
new item reaches; a pinned place keeps its item. Between levels: each level keeps one of each, of a drawn level."""
from collections import Counter
from functools import cache

import pytest

from tests.seed_rotation import chunk_id, chunks, sweep_seeds
from zora import archipelago
from zora.flags.codec import decode as decode_z1r
from zora.flags.codec import encode as encode_z1r
from zora.flags.fields import ItemShuffleScope, PinnedItem, ThreeState
from zora.flags.zora_flags import LevelItemShuffle, ZoraFlags, decode, encode
from zora.generate import pipeline
from zora.generate.finish import Foreign, ItemClass, refusals
from zora.generate.places import item_pool, read_item
from zora.generate.solo_assignment import acts, identity, level_items_moved, solo_assignment
from zora.generate.steps.shuffle_items import MINOR_ITEMS
from zora.model.enums import Item, RoomType
from zora.model.level_items import LEVEL_ITEMS, LevelItemKind, level_of
from zora.model.levels import Level
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom

BOTH_ON = encode(ZoraFlags(triforce_shuffle=LevelItemShuffle.ANYWHERE, map_compass_shuffle=LevelItemShuffle.ANYWHERE))
SEEDS = (1, 2)


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("needs the base ROM")
    return remember_repo_base_rom()


def z1r(scope: ItemShuffleScope, **options: int) -> str:
    return encode_z1r(decode_z1r(archipelago.DEFAULT_FLAGS).updated(options={"C06": int(scope), **options}))


@cache
def _built(flags: str, seed: int, zora: str = BOTH_ON) -> pipeline.Built:
    return pipeline.build(pipeline.plan(flags, seed, zora), remember_repo_base_rom())


def dungeon_codes(rom: bytes, flags: str, seed: int) -> list[tuple[Item, int]]:
    """Each level code a finished ROM holds in a level's room or item cellar, with that data level."""
    world = parse_rom(rom, pipeline.plan(flags, seed, BOTH_ON).config)
    found = []
    for level in world.levels:
        found += [(room.item, level.level_num) for room in level.rooms if room.item in LEVEL_ITEMS]
        found += [(stair.item, level.level_num) for stair in level.block.staircases
                  if stair.return_dest in level.room_nums and stair.item in LEVEL_ITEMS]
    return found


@pytest.mark.parametrize("seed", SEEDS)
def test_within_each_dungeon_keeps_each_item_in_its_level(base: bytes, seed: int) -> None:
    flags = z1r(ItemShuffleScope.WITHIN_EACH_DUNGEON)
    rom = pipeline.generate_rom(flags, seed, base, zora_flag_string=BOTH_ON).rom
    found = dungeon_codes(rom, flags, seed)
    assert sorted(item for item, _ in found) == sorted(LEVEL_ITEMS)       # each of the 26 once
    assert all(LEVEL_ITEMS[item][1] == level for item, level in found)


@pytest.mark.parametrize("seed", SEEDS)
def test_dungeon_items_only_never_reaches_a_heart_room(seed: int) -> None:
    built = _built(z1r(ItemShuffleScope.DUNGEON_ITEMS_ONLY), seed)
    heart_rooms = {place.name for place in built.places
                   if place.is_dungeon and read_item(built.world, place) == Item.HEART_CONTAINER}
    assignment = solo_assignment(built)
    new = level_items_moved(built)
    assert not [name for name in heart_rooms if assignment[name] in new]
    assert Counter(item for item in assignment.values() if item in new) == Counter(new)


@pytest.mark.parametrize("seed", SEEDS)
def test_full_moves_the_items_and_holds_each_once(base: bytes, seed: int) -> None:
    flags = z1r(ItemShuffleScope.FULL)
    built = _built(flags, seed)
    assignment = solo_assignment(built)
    new = level_items_moved(built)
    assert Counter(item for item in assignment.values() if item in new) == Counter(new)
    assert assignment != identity(built)
    rom = pipeline.generate_rom(flags, seed, base, zora_flag_string=BOTH_ON).rom
    found = Counter(item for item, _ in dungeon_codes(rom, flags, seed))
    assert max(found.values()) == 1


def test_a_pinned_place_keeps_its_item() -> None:
    built = _built(z1r(ItemShuffleScope.FULL, C12=int(PinnedItem.BOW)), 1)
    assert identity(built)["Coast"] == Item.BOW
    assert solo_assignment(built)["Coast"] == Item.BOW


def test_item_shuffle_none_leaves_the_switches_idle() -> None:
    assert not acts(_built(z1r(ItemShuffleScope.NONE), 1))
    assert acts(_built(z1r(ItemShuffleScope.FULL), 1))


BETWEEN = encode(ZoraFlags(triforce_shuffle=LevelItemShuffle.BETWEEN_LEVELS,
                           map_compass_shuffle=LevelItemShuffle.BETWEEN_LEVELS))


@pytest.mark.parametrize("seed", SEEDS)
def test_between_levels_gives_each_level_one_of_each_drawn_level(base: bytes, seed: int) -> None:
    """Between levels: each level holds exactly one piece (1-8), map and compass, at the spot Off puts it, written as
    the code of the level the swaps drew; the swaps are no identity, and the same seed draws the same."""
    from zora.model.level_items import level_item
    flags = z1r(ItemShuffleScope.FULL)
    swaps = pipeline.extra_options(pipeline.plan(flags, seed, BETWEEN)).level_swaps
    assert swaps == pipeline.extra_options(pipeline.plan(flags, seed, BETWEEN)).level_swaps
    assert not swaps.is_identity
    off = encode(ZoraFlags())
    off_world = _built(flags, seed, off).world
    rom = pipeline.generate_rom(flags, seed, base, zora_flag_string=BETWEEN).rom
    found = dungeon_codes(rom, flags, seed)
    assert sorted(item for item, _ in found) == sorted(LEVEL_ITEMS)       # each of the 26 once
    kinds: dict[int, set[LevelItemKind]] = {}
    for item, data_level in found:
        kind_level = level_of(item)
        assert kind_level is not None
        kind = kind_level[0]
        assert item == level_item(kind, swaps.code_in(kind, data_level)), (item, data_level)
        kinds.setdefault(data_level, set()).add(kind)
    # the spots are Off's: the same levels hold a piece, a map or a compass as in the seed with both Off
    generic = {LevelItemKind.TRIFORCE: Item.TRIFORCE, LevelItemKind.MAP: Item.MAP, LevelItemKind.COMPASS: Item.COMPASS}
    for off_level in off_world.levels:
        held = {room.item for room in off_level.rooms} | {stair.item for stair in off_level.block.staircases
                                                           if stair.return_dest in off_level.room_nums}
        expected = {kind for kind, code in generic.items() if code in held}
        assert kinds.get(off_level.level_num, set()) == expected, off_level.level_num


def test_the_test_releases_on_reads_as_anywhere() -> None:
    """2.0.2's test release's On (digit 1) is Anywhere, so its strings keep their meaning."""
    assert LevelItemShuffle.ANYWHERE == int(ThreeState.ON)
    assert decode(BOTH_ON).triforce_shuffle is LevelItemShuffle.ANYWHERE


def test_the_same_seed_gives_the_same_rom(base: bytes) -> None:
    flags = z1r(ItemShuffleScope.FULL)
    first = pipeline.generate_rom(flags, 3, base, zora_flag_string=BOTH_ON).rom
    assert pipeline.generate_rom(flags, 3, base, zora_flag_string=BOTH_ON).rom == first


@pytest.mark.parametrize("seed", SEEDS)
def test_a_compass_spot_never_holds_bombs_rupees_or_a_key(base: bytes, seed: int) -> None:
    """Per-level mode (owner, 2026-11-25): the room or item cellar each level's compass marks (Place.compass_spot,
    the piece's original spot) never holds Shuffle Minor Dungeon Drops' filler; the swaps draw again, as for any
    place's forbids. Under Full with the drops on, every place, minor ones too, is a swap partner."""
    flags = encode_z1r(decode_z1r(archipelago.DEFAULT_FLAGS).updated(options={"C06": int(ItemShuffleScope.FULL)},
                                                                    toggles={"B17": ThreeState.ON}))
    built = _built(flags, seed)
    spots = [place for place in built.places if place.compass_spot]
    assert spots and all(place.level in range(1, 9) for place in spots)
    assert any(place.minor for place in built.places)
    assignment = solo_assignment(built)
    assert not [place.name for place in spots if assignment[place.name] in MINOR_ITEMS]
    pool = item_pool(pipeline.extra_options(built.plan))
    for item in MINOR_ITEMS:
        assert refusals(built.places, {**assignment, spots[0].name: item}, pool), item


def test_a_compass_spot_refuses_another_players_filler(base: bytes) -> None:
    """In Archipelago, FINISH refuses any world's filler at a compass spot (the world's item rule keeps it out), and
    takes another player's progression or useful item there."""
    built = _built(z1r(ItemShuffleScope.FULL), SEEDS[0])
    spot = next(place for place in built.places if place.compass_spot)
    assignment = identity(built)
    pool = item_pool(pipeline.extra_options(built.plan))
    assert refusals(built.places, {**assignment, spot.name: Foreign(ItemClass.FILLER)}, pool)
    for item_class in (ItemClass.PROGRESSION, ItemClass.USEFUL):
        assert not refusals(built.places, {**assignment, spot.name: Foreign(item_class)}, pool)


GUARD_SEEDS = range(1, 201)
SHUFFLE_PAIRS = [(triforce, map_compass) for triforce in (LevelItemShuffle.OFF, LevelItemShuffle.BETWEEN_LEVELS)
                 for map_compass in (LevelItemShuffle.OFF, LevelItemShuffle.BETWEEN_LEVELS)]


def level_spots(level: Level) -> dict[str, tuple[int, Item | None]]:
    """Each room and item cellar of LEVEL by a label, with the room it belongs to (a cellar's, the room above it)
    and its item."""
    spots: dict[str, tuple[int, Item | None]] = {f"room ${room.room_num:02X}": (room.room_num, room.item)
                                                 for room in level.rooms}
    spots |= {f"cellar ${stair.room_num:02X}": (stair.return_dest, stair.item) for stair in level.block.staircases
              if stair.return_dest in level.room_nums and stair.room_type == RoomType.ITEM_STAIRCASE}
    return spots


def spot_kind(item: Item | None) -> LevelItemKind | None:
    """The kind of a level item, a level's own code or BUILD's generic one."""
    generic = {Item.TRIFORCE: LevelItemKind.TRIFORCE, Item.MAP: LevelItemKind.MAP, Item.COMPASS: LevelItemKind.COMPASS}
    if item is None:
        return None
    found = level_of(item)
    return found[0] if found else generic.get(item)


@pytest.mark.slow
@pytest.mark.parametrize("triforce, map_compass", SHUFFLE_PAIRS, ids=lambda shuffle: shuffle.name.lower())
@pytest.mark.parametrize("seeds", chunks(sweep_seeds(GUARD_SEEDS)), ids=chunk_id)
def test_each_compass_marks_its_piece_and_each_spot_keeps_its_kind(base: bytes, triforce: LevelItemShuffle,
                                                                   map_compass: LevelItemShuffle,
                                                                   seeds: range) -> None:
    """Guard for the 2026-11-26 report (a compass that seemed to point at a map): Off or Between levels, each,
    with Item Counter On. In each finished ROM every level 1-8's compass marks a room holding a piece, in the room
    itself or in the item cellar under it (Allow Triforces in Stairways, on for odd seeds, can put the piece in the
    cellar while the room holds another item), and every spot BUILD gave a piece, a map or a compass holds a code
    of the same kind."""
    flags = z1r(ItemShuffleScope.FULL)
    for seed in seeds:
        zora = encode(ZoraFlags(triforce_shuffle=triforce, map_compass_shuffle=map_compass,
                                item_counter=ThreeState.ON,
                                allow_triforces_in_stairways=ThreeState.ON if seed % 2 else ThreeState.OFF))
        chosen = pipeline.plan(flags, seed, zora)
        built = pipeline.build(chosen, base)
        world = parse_rom(pipeline.generate_rom(flags, seed, base, zora_flag_string=zora).rom, chosen.config)
        for level in (level for level in world.levels if level.level_num in range(1, 9)):
            marked = [item for room, item in level_spots(level).values() if room == level.triforce_room_ptr]
            assert LevelItemKind.TRIFORCE in map(spot_kind, marked), (seed, level.level_num, marked)
        finished = {level.level_num: level_spots(level) for level in world.levels}
        for level in built.world.levels:
            for label, (_room, item) in level_spots(level).items():
                if spot_kind(item):
                    held = finished[level.level_num][label][1]
                    assert spot_kind(held) is spot_kind(item), (seed, level.level_num, label, item, held)
