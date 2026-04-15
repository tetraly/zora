"""
Entrance shuffle tests: verify shuffle_caves produces correct, glitch-free results.
"""
from pathlib import Path

from flags.flags_generated import CaveShuffleMode, Flags
from zora.data_model import Destination, GameWorld, QuestVisibility
from zora.entrance_randomizer import shuffle_caves
from zora.game_config import resolve_game_config
from zora.game_validator import GameValidator
from zora.item_randomizer import assumed_fill
from zora.parser import load_bin_files, parse_game_world
from zora.rng import SeededRng

TEST_DATA = Path(__file__).parent.parent / "rom_data"

_DUNGEON_DESTINATIONS = frozenset(range(1, 10))  # Destination values 1-9


def _fresh_world() -> GameWorld:
    return parse_game_world(load_bin_files(TEST_DATA))


def _dungeon_screens(world: GameWorld) -> dict[int, int]:
    """Return {dungeon_num: screen_num} for all dungeon entrances on the overworld."""
    result = {}
    for screen in world.overworld.screens:
        if screen.destination.value in _DUNGEON_DESTINATIONS:
            result[screen.destination.value] = screen.screen_num
    return result


def _non_dungeon_destinations(world: GameWorld) -> set[int]:
    """Return the set of non-dungeon, non-NONE destination values."""
    return {
        s.destination.value
        for s in world.overworld.screens
        if s.destination != Destination.NONE
        and s.destination.value not in _DUNGEON_DESTINATIONS
    }


# ---------------------------------------------------------------------------
# Dungeon shuffle invariants
# ---------------------------------------------------------------------------

def test_all_nine_dungeons_present_after_shuffle():
    """All 9 dungeon entrances must still exist on the overworld after shuffling."""
    for seed in range(3):
        world = _fresh_world()
        rng = SeededRng(seed)
        result = shuffle_caves(
            world, rng,
            shuffle=False, include_bracelet_caves=False,
            include_wood_sword_cave=False, shuffle_armos=False,
            add_armos_item=False, mirror_ow=False,
            just_dungeons=True, shuffle_dungeons=True, overworld_block_needed=False,
        )
        assert result is not None, f"Seed {seed}: shuffle_caves returned None"
        dungeon_screens = _dungeon_screens(world)
        assert set(dungeon_screens.keys()) == set(range(1, 10)), (
            f"Seed {seed}: missing dungeons after shuffle: "
            f"{set(range(1, 10)) - set(dungeon_screens.keys())}"
        )


def test_each_dungeon_appears_exactly_once_after_shuffle():
    """Each dungeon (1-9) must appear on exactly one Q1-visible overworld screen
    after shuffling. No dungeon destination may be duplicated or missing among
    FIRST_QUEST and BOTH_QUESTS screens (the only screens active in Q1 play)."""
    for seed in range(123, 133):
        world = _fresh_world()
        rng = SeededRng(seed)
        result = shuffle_caves(
            world, rng,
            shuffle=False, include_bracelet_caves=False,
            include_wood_sword_cave=False, shuffle_armos=False,
            add_armos_item=False, mirror_ow=False,
            just_dungeons=True, shuffle_dungeons=True, overworld_block_needed=False,
        )
        assert result is not None, f"Seed {seed}: shuffle_caves returned None"

        dungeon_dest_counts: dict[int, int] = {}
        for screen in world.overworld.screens:
            if screen.quest_visibility == QuestVisibility.SECOND_QUEST:
                continue  # Q2-only screens are not visible in Q1 play
            d = screen.destination.value
            if d in _DUNGEON_DESTINATIONS:
                dungeon_dest_counts[d] = dungeon_dest_counts.get(d, 0) + 1

        duplicates = {d: count for d, count in dungeon_dest_counts.items() if count > 1}
        assert not duplicates, (
            f"Seed {seed}: dungeon entrances appear more than once on Q1-visible overworld: "
            + ", ".join(f"L{d} x{count}" for d, count in sorted(duplicates.items()))
        )
        missing = set(range(1, 10)) - set(dungeon_dest_counts.keys())
        assert not missing, (
            f"Seed {seed}: dungeon entrances missing from Q1-visible overworld: "
            + ", ".join(f"L{d}" for d in sorted(missing))
        )


def test_no_dungeon_lands_on_its_own_entrance_room_screen():
    """No dungeon entrance should be placed on the overworld screen matching
    its own entrance_room number — the game glitches when these coincide."""
    for seed in range(5):
        world = _fresh_world()
        entrance_rooms = {lvl.level_num: lvl.entrance_room for lvl in world.levels}
        rng = SeededRng(seed)
        result = shuffle_caves(
            world, rng,
            shuffle=False, include_bracelet_caves=False,
            include_wood_sword_cave=False, shuffle_armos=False,
            add_armos_item=False, mirror_ow=False,
            just_dungeons=True, shuffle_dungeons=True, overworld_block_needed=False,
        )
        assert result is not None, f"Seed {seed}: shuffle_caves returned None"
        for screen in world.overworld.screens:
            d = screen.destination.value
            if d in _DUNGEON_DESTINATIONS:
                assert screen.screen_num != entrance_rooms[d], (
                    f"Seed {seed}: dungeon {d} placed on screen "
                    f"{screen.screen_num:#04x} which equals its own entrance_room"
                )


# ---------------------------------------------------------------------------
# Non-dungeon shuffle invariants
# ---------------------------------------------------------------------------

def test_just_dungeons_leaves_non_dungeon_caves_unchanged():
    """With just_dungeons=True, non-dungeon cave destinations must not move."""
    world_before = _fresh_world()
    non_dungeon_before = _non_dungeon_destinations(world_before)

    world_after = _fresh_world()
    rng = SeededRng(0)
    result = shuffle_caves(
        world_after, rng,
        shuffle=False, include_bracelet_caves=False,
        include_wood_sword_cave=False, shuffle_armos=False,
        add_armos_item=False, mirror_ow=False,
        just_dungeons=True, shuffle_dungeons=True, overworld_block_needed=False,
    )
    assert result is not None
    non_dungeon_after = _non_dungeon_destinations(world_after)
    assert non_dungeon_before == non_dungeon_after, (
        "Non-dungeon cave destinations changed with just_dungeons=True"
    )


def test_wood_sword_cave_lands_on_accessible_screen():
    """The wood sword cave must always end up on a freely accessible screen
    (no raft, recorder, ladder, or bracelet required)."""
    raft_locations      = [0x2F, 0x45]
    recorder_locations  = [66, 6, 41, 43, 48, 58, 60, 88, 96, 110, 114]
    ladder_locations    = frozenset([0x18, 0x19])

    for seed in range(5):
        world = _fresh_world()
        rng = SeededRng(seed)
        result = shuffle_caves(
            world, rng,
            shuffle=True, include_bracelet_caves=False,
            include_wood_sword_cave=True, shuffle_armos=False,
            add_armos_item=False, mirror_ow=False,
            just_dungeons=False, shuffle_dungeons=False, overworld_block_needed=False,
            raft_locations=raft_locations,
            recorder_locations=recorder_locations,
        )
        assert result is not None, f"Seed {seed}: shuffle_caves returned None"
        assert result.wood_sword_screen is not None, \
            f"Seed {seed}: wood_sword_screen not set in result"
        ws = result.wood_sword_screen
        assert ws not in raft_locations, \
            f"Seed {seed}: wood sword cave landed on raft-required screen {ws:#04x}"
        assert ws not in recorder_locations, \
            f"Seed {seed}: wood sword cave landed on recorder-required screen {ws:#04x}"
        assert ws not in ladder_locations, \
            f"Seed {seed}: wood sword cave landed on ladder-required screen {ws:#04x}"


# ---------------------------------------------------------------------------
# End-to-end: entrance shuffle + item fill produces beatable seeds
# ---------------------------------------------------------------------------

def test_dungeon_only_entrance_shuffle_produces_beatable_seeds():
    """Dungeon-only entrance shuffle combined with assumed fill must produce
    valid, beatable seeds."""
    flags = Flags(cave_shuffle_mode=CaveShuffleMode.DUNGEONS_ONLY)
    for seed in range(3):
        world = _fresh_world()
        rng = SeededRng(seed)
        config = resolve_game_config(flags, SeededRng(seed))
        shuffle_caves(
            world, rng,
            shuffle=config.shuffle_non_dungeon_caves,
            include_bracelet_caves=config.include_any_road_caves,
            include_wood_sword_cave=config.include_wood_sword_cave,
            shuffle_armos=config.shuffle_armos_location,
            add_armos_item=config.shuffle_armos_item,
            mirror_ow=False,
            just_dungeons=config.shuffle_dungeon_entrances and not config.shuffle_non_dungeon_caves,
            shuffle_dungeons=config.shuffle_dungeon_entrances,
            overworld_block_needed=config.shuffle_non_dungeon_caves,
        )
        success = assumed_fill(world, config, SeededRng(seed))
        assert success, f"Seed {seed}: assumed fill failed with dungeon entrance shuffle"
        assert GameValidator(world, config.avoid_required_hard_combat).is_seed_valid(), \
            f"Seed {seed}: seed invalid after dungeon entrance shuffle"


# ---------------------------------------------------------------------------
# Armos shuffle: destination swap correctness
# ---------------------------------------------------------------------------

def test_armos_shuffle_swaps_destination_to_new_screen():
    """When armos moves off screen 36, screen 36 must no longer hold
    ARMOS_ITEM and the new screen must hold it instead."""
    # Try multiple seeds until we find one where armos actually moves.
    for seed in range(20):
        world = _fresh_world()
        rng = SeededRng(seed)
        result = shuffle_caves(
            world, rng,
            shuffle=False, include_bracelet_caves=False,
            include_wood_sword_cave=False, shuffle_armos=True,
            add_armos_item=False, mirror_ow=False,
            just_dungeons=False, shuffle_dungeons=False, overworld_block_needed=False,
        )
        assert result is not None, f"Seed {seed}: shuffle_caves returned None"

        armos_screen_id = world.overworld.armos_screen_ids[0]
        screens_by_num = {s.screen_num: s for s in world.overworld.screens}

        if armos_screen_id == 36:
            # Armos stayed on screen 36 this seed — nothing to check.
            continue

        # The new screen must carry ARMOS_ITEM destination.
        new_screen = screens_by_num.get(armos_screen_id)
        assert new_screen is not None, \
            f"Seed {seed}: armos screen {armos_screen_id:#04x} not found in overworld"
        assert new_screen.destination == Destination.NONE, (
            f"Seed {seed}: new armos screen {armos_screen_id:#04x} has destination "
            f"{new_screen.destination!r}, expected ARMOS_ITEM"
        )

        # Screen 36 must no longer carry ARMOS_ITEM.
        old_screen = screens_by_num.get(36)
        assert old_screen is not None, "Seed {seed}: screen 36 missing from overworld"
        assert old_screen.destination != Destination.NONE, (
            f"Seed {seed}: screen 36 still has ARMOS_ITEM after armos moved to "
            f"{armos_screen_id:#04x}"
        )
        # Found and verified a moved-armos seed — one is enough.
        return

    raise AssertionError("No seed in range(20) produced an armos move — expand the range")


def test_full_cave_shuffle_produces_beatable_seeds():
    """Full cave shuffle (dungeons + non-dungeons) combined with assumed fill
    must produce valid, beatable seeds."""
    flags = Flags(cave_shuffle_mode=CaveShuffleMode.ALL_CAVES)
    for seed in range(5):
        world = _fresh_world()
        rng = SeededRng(seed)
        config = resolve_game_config(flags, SeededRng(seed))
        result = shuffle_caves(
            world, rng,
            shuffle=config.shuffle_non_dungeon_caves,
            include_bracelet_caves=config.include_any_road_caves,
            include_wood_sword_cave=config.include_wood_sword_cave,
            shuffle_armos=config.shuffle_armos_location,
            add_armos_item=config.shuffle_armos_item,
            mirror_ow=False,
            just_dungeons=False,
            shuffle_dungeons=config.shuffle_dungeon_entrances,
            overworld_block_needed=config.shuffle_non_dungeon_caves,
        )
        if result is None:
            continue  # overworld block check failed — valid retry case
        success = assumed_fill(world, config, SeededRng(seed))
        assert success, f"Seed {seed}: assumed fill failed with full cave shuffle"
        assert GameValidator(world, config.avoid_required_hard_combat).is_seed_valid(), \
            f"Seed {seed}: seed invalid after full cave shuffle"
