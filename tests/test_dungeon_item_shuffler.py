"""
Tests for dungeon_item_shuffler: intra-dungeon item shuffling.
"""
from flags.flags_generated import Flags, Tristate
from zora.data_model import Item, Level, RoomType
from zora.dungeon_item_shuffler import _DUNGEON_MAJOR_ITEMS, _FIXED_ITEMS, shuffle_dungeon_items
from zora.game_config import GameConfig, resolve_game_config
from zora.game_validator import GameValidator
from zora.item_randomizer import assumed_fill, randomize_items
from zora.parser import parse_game_world
from zora.rng import SeededRng


def _config(flags: Flags, seed: int = 0) -> GameConfig:
    return resolve_game_config(flags, SeededRng(seed))


def _item_staircase_rooms(level: Level) -> list:
    return [sr for sr in level.staircase_rooms if sr.room_type == RoomType.ITEM_STAIRCASE]


# ---------------------------------------------------------------------------
# No-op when flag is off
# ---------------------------------------------------------------------------

def test_shuffle_within_dungeons_off_is_noop(bins):
    """When shuffle_within_dungeons is off, items must not be moved."""
    flags = Flags(shuffle_within_dungeons=Tristate.OFF)
    gw = parse_game_world(bins)
    config = _config(flags)

    # Record items on a fresh (pre-fill) world
    before: dict[tuple[int, int], Item] = {}
    for level in gw.levels:
        for room in level.rooms:
            before[(level.level_num, room.room_num)] = room.item
        for sr in level.staircase_rooms:
            if sr.item is not None:
                before[(level.level_num, sr.room_num)] = sr.item

    shuffle_dungeon_items(gw, config, SeededRng(0))

    for level in gw.levels:
        for room in level.rooms:
            assert room.item == before[(level.level_num, room.room_num)]
        for sr in level.staircase_rooms:
            if sr.item is not None:
                assert sr.item == before[(level.level_num, sr.room_num)]


# ---------------------------------------------------------------------------
# Major items always land in staircase rooms (triforces_in_stairways off)
# ---------------------------------------------------------------------------

def test_major_items_in_staircase_rooms(bins):
    """All item staircase rooms must hold a major item (or heart container) after shuffle."""
    flags = Flags(
        shuffle_within_dungeons=Tristate.ON,
        allow_triforces_in_stairways=Tristate.OFF,
    )
    for seed in range(5):
        gw = parse_game_world(bins)
        config = _config(flags, seed=seed)
        shuffle_dungeon_items(gw, config, SeededRng(seed))
        assumed_fill(gw, config, SeededRng(seed))

        for level in gw.levels:
            for sr in _item_staircase_rooms(level):
                assert sr.item in _DUNGEON_MAJOR_ITEMS, (
                    f"Seed {seed} L{level.level_num}: staircase room {sr.room_num:#04x} "
                    f"has non-major item {sr.item}"
                )


def test_minor_items_not_in_staircase_rooms(bins):
    """Compasses, maps, and triforces (flag off) must not appear in staircase rooms."""
    flags = Flags(
        shuffle_within_dungeons=Tristate.ON,
        allow_triforces_in_stairways=Tristate.OFF,
    )
    _minor = {Item.COMPASS, Item.MAP, Item.TRIFORCE}
    for seed in range(5):
        gw = parse_game_world(bins)
        config = _config(flags, seed=seed)
        shuffle_dungeon_items(gw, config, SeededRng(seed))
        assumed_fill(gw, config, SeededRng(seed))

        for level in gw.levels:
            for sr in _item_staircase_rooms(level):
                assert sr.item not in _minor, (
                    f"Seed {seed} L{level.level_num}: staircase room {sr.room_num:#04x} "
                    f"has minor item {sr.item}"
                )


# ---------------------------------------------------------------------------
# Triforces in stairways flag
# ---------------------------------------------------------------------------

def test_triforces_in_stairways_allows_triforce_in_staircase(bins):
    """With allow_triforces_in_stairways on, at least one seed must place a triforce
    in an item staircase room."""
    flags = Flags(
        shuffle_within_dungeons=Tristate.ON,
        allow_triforces_in_stairways=Tristate.ON,
    )
    for seed in range(20):
        gw = parse_game_world(bins)
        config = _config(flags, seed=seed)
        shuffle_dungeon_items(gw, config, SeededRng(seed))
        assumed_fill(gw, config, SeededRng(seed))

        for level in gw.levels:
            for sr in _item_staircase_rooms(level):
                if sr.item == Item.TRIFORCE:
                    return  # found one — pass

    raise AssertionError("No triforce placed in a staircase room across 20 seeds")


def test_triforces_stay_within_their_dungeon(bins):
    """Each dungeon's triforce(s) must remain in that dungeon after shuffle."""
    flags = Flags(
        shuffle_within_dungeons=Tristate.ON,
        allow_triforces_in_stairways=Tristate.ON,
    )
    for seed in range(5):
        gw = parse_game_world(bins)
        config = _config(flags, seed=seed)

        # Record which levels had triforces before shuffling
        triforce_levels_before: dict[int, int] = {}
        for level in gw.levels:
            count = sum(1 for r in level.rooms if r.item == Item.TRIFORCE)
            count += sum(1 for sr in level.staircase_rooms if sr.item == Item.TRIFORCE)
            triforce_levels_before[level.level_num] = count

        shuffle_dungeon_items(gw, config, SeededRng(seed))
        assumed_fill(gw, config, SeededRng(seed))

        for level in gw.levels:
            count_after = sum(1 for r in level.rooms if r.item == Item.TRIFORCE)
            count_after += sum(1 for sr in level.staircase_rooms if sr.item == Item.TRIFORCE)
            assert count_after == triforce_levels_before[level.level_num], (
                f"Seed {seed} L{level.level_num}: triforce count changed "
                f"({triforce_levels_before[level.level_num]} → {count_after})"
            )


# ---------------------------------------------------------------------------
# Fixed items never move
# ---------------------------------------------------------------------------

def test_triforce_of_power_never_moves(bins):
    """TRIFORCE_OF_POWER must always stay in its original room."""
    flags = Flags(
        shuffle_within_dungeons=Tristate.ON,
        allow_triforces_in_stairways=Tristate.ON,
    )
    for seed in range(5):
        gw = parse_game_world(bins)
        # Find the original room holding TRIFORCE_OF_POWER
        original: dict[tuple[int, int], Item] = {}
        for level in gw.levels:
            for room in level.rooms:
                if room.item == Item.TRIFORCE_OF_POWER:
                    original[(level.level_num, room.room_num)] = room.item

        config = _config(flags, seed=seed)
        shuffle_dungeon_items(gw, config, SeededRng(seed))
        assumed_fill(gw, config, SeededRng(seed))

        for level in gw.levels:
            for room in level.rooms:
                key = (level.level_num, room.room_num)
                if key in original:
                    assert room.item == Item.TRIFORCE_OF_POWER, (
                        f"Seed {seed}: TRIFORCE_OF_POWER moved from L{level.level_num} "
                        f"R{room.room_num:#04x}"
                    )


# ---------------------------------------------------------------------------
# Item multiset preservation
# ---------------------------------------------------------------------------

def test_item_multiset_preserved_per_dungeon(bins):
    """The multiset of items within each dungeon must be identical before and after shuffle."""
    from collections import Counter

    flags = Flags(
        shuffle_within_dungeons=Tristate.ON,
        allow_triforces_in_stairways=Tristate.ON,
    )
    for seed in range(5):
        gw = parse_game_world(bins)
        config = _config(flags, seed=seed)

        def _level_item_counter(level: Level) -> Counter:
            items: list[Item] = [r.item for r in level.rooms if r.item not in _FIXED_ITEMS]
            items += [sr.item for sr in level.staircase_rooms
                      if sr.item is not None and sr.item not in _FIXED_ITEMS]
            return Counter(items)

        before = {level.level_num: _level_item_counter(level) for level in gw.levels}
        shuffle_dungeon_items(gw, config, SeededRng(seed))
        after = {level.level_num: _level_item_counter(level) for level in gw.levels}

        for level_num in before:
            assert before[level_num] == after[level_num], (
                f"Seed {seed} L{level_num}: item multiset changed after shuffle\n"
                f"  before: {dict(before[level_num])}\n"
                f"  after:  {dict(after[level_num])}"
            )


# ---------------------------------------------------------------------------
# End-to-end beatability
# ---------------------------------------------------------------------------

def test_shuffle_within_dungeons_produces_beatable_seeds(bins):
    """Seeds with shuffle_within_dungeons on must be beatable (shuffle before assumed_fill)."""
    flags = Flags(shuffle_within_dungeons=Tristate.ON)
    for seed in range(5):
        gw = parse_game_world(bins)
        config = _config(flags, seed=seed)
        shuffle_dungeon_items(gw, config, SeededRng(seed))
        success = assumed_fill(gw, config, SeededRng(seed))
        assert success, f"Seed {seed}: assumed_fill failed"
        assert GameValidator(gw, config.avoid_required_hard_combat).is_seed_valid(), (
            f"Seed {seed}: seed not beatable"
        )


def test_triforces_in_stairways_produces_beatable_seeds(bins):
    """Seeds with both flags on must be beatable (shuffle before assumed_fill)."""
    flags = Flags(
        shuffle_within_dungeons=Tristate.ON,
        allow_triforces_in_stairways=Tristate.ON,
    )
    for seed in range(5):
        gw = parse_game_world(bins)
        config = _config(flags, seed=seed)
        shuffle_dungeon_items(gw, config, SeededRng(seed))
        randomize_items(gw, config, SeededRng(seed))
        assert GameValidator(gw, config.avoid_required_hard_combat).is_seed_valid(), (
            f"Seed {seed}: seed not beatable with triforces_in_stairways"
        )
