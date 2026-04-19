"""
Tests for extra_raft_blocks and extra_power_bracelet_blocks flags.

Coverage:
  1. Entrance type override unit tests — _apply_entrance_type_overrides() directly
  2. Serializer patch tests — correct ASM bytes land in the patch at the right offsets
  3. Validator reachability tests — gated screens require the right items
  4. Flag constraint test — extra_power_bracelet_blocks + include_any_road_caves is invalid
  5. End-to-end beatable seed test — assumed fill + GameValidator passes with each flag on
"""
from pathlib import Path

from flags.flags_generated import CaveShuffleMode, Flags, Tristate
from zora.api.validation import validate_flags_static
from zora.data_model import EntranceType, Item
from zora.entrance_randomizer import (
    _EXTRA_PB_AND_BOMB_SCREENS,
    _EXTRA_RAFT_AND_BOMB_SCREENS,
    _EXTRA_RAFT_SCREENS,
    apply_entrance_type_overrides,
)
from zora.game_config import GameConfig, resolve_game_config
from zora.game_validator import GameValidator
from zora.item_randomizer import assumed_fill
from zora.parser import parse_game_world
from zora.patches import build_behavior_patch
from zora.patches.extra_power_bracelet_blocks import ExtraPowerBraceletBlocks
from zora.patches.extra_raft_blocks import ExtraRaftBlocks
from zora.rng import SeededRng
from zora.serializer import serialize_game_world


TEST_DATA = Path(__file__).parent.parent / "rom_data"


def _load_originals():
    return {
        "level_1_6_data.bin": (TEST_DATA / "level_1_6_data.bin").read_bytes(),
        "level_7_9_data.bin": (TEST_DATA / "level_7_9_data.bin").read_bytes(),
        "level_info.bin":     (TEST_DATA / "level_info.bin").read_bytes(),
        "overworld_data.bin": (TEST_DATA / "overworld_data.bin").read_bytes(),
        "armos_item.bin":     (TEST_DATA / "armos_item.bin").read_bytes(),
        "coast_item.bin":     (TEST_DATA / "coast_item.bin").read_bytes(),
        "white_sword_requirement.bin":   (TEST_DATA / "white_sword_requirement.bin").read_bytes(),
        "magical_sword_requirement.bin": (TEST_DATA / "magical_sword_requirement.bin").read_bytes(),
    }


def _config(flags: Flags, seed: int = 0) -> GameConfig:
    return resolve_game_config(flags, SeededRng(seed))


# =============================================================================
# 1. Entrance type override unit tests
# =============================================================================

def test_overrides_no_op_when_both_flags_off(bins):
    """With neither flag on, apply_entrance_type_overrides leaves all entrance types unchanged."""
    world = parse_game_world(bins)
    vanilla_screens = {s.screen_num: s.entrance_type for s in world.overworld.screens}
    config = _config(Flags())  # both flags default OFF
    apply_entrance_type_overrides(world, config)
    for screen in world.overworld.screens:
        assert screen.entrance_type == vanilla_screens[screen.screen_num]


def test_extra_raft_blocks_sets_raft_on_open_screens(bins):
    """extra_raft_blocks: screens in _EXTRA_RAFT_SCREENS become RAFT."""
    world = parse_game_world(bins)
    config = _config(Flags(extra_raft_blocks=Tristate.ON))
    apply_entrance_type_overrides(world, config)

    screens_by_num = {s.screen_num: s for s in world.overworld.screens}
    for num in _EXTRA_RAFT_SCREENS:
        assert screens_by_num[num].entrance_type == EntranceType.RAFT, (
            f"Screen {num:#04x} should be RAFT, got {screens_by_num[num].entrance_type}"
        )


def test_extra_raft_blocks_sets_raft_and_bomb_on_bomb_screen(bins):
    """extra_raft_blocks: screen 0x1E (vanilla BOMB) becomes RAFT_AND_BOMB."""
    world = parse_game_world(bins)
    config = _config(Flags(extra_raft_blocks=Tristate.ON))
    apply_entrance_type_overrides(world, config)

    screens_by_num = {s.screen_num: s for s in world.overworld.screens}
    for num in _EXTRA_RAFT_AND_BOMB_SCREENS:
        assert screens_by_num[num].entrance_type == EntranceType.RAFT_AND_BOMB, (
            f"Screen {num:#04x} should be RAFT_AND_BOMB, got {screens_by_num[num].entrance_type}"
        )


def test_extra_raft_blocks_does_not_affect_unrelated_screens(bins):
    """extra_raft_blocks: screens outside the affected sets keep their vanilla entrance type."""
    world = parse_game_world(bins)
    vanilla_screens = {s.screen_num: s.entrance_type for s in world.overworld.screens}

    config = _config(Flags(extra_raft_blocks=Tristate.ON))
    apply_entrance_type_overrides(world, config)

    affected = _EXTRA_RAFT_SCREENS | _EXTRA_RAFT_AND_BOMB_SCREENS
    for screen in world.overworld.screens:
        if screen.screen_num not in affected:
            assert screen.entrance_type == vanilla_screens[screen.screen_num], (
                f"Screen {screen.screen_num:#04x} entrance_type changed unexpectedly"
            )


def test_extra_pb_blocks_sets_pb_and_bomb_on_west_death_mountain(bins):
    """extra_power_bracelet_blocks: screens in _EXTRA_PB_AND_BOMB_SCREENS become POWER_BRACELET_AND_BOMB."""
    world = parse_game_world(bins)
    config = _config(Flags(extra_power_bracelet_blocks=Tristate.ON))
    apply_entrance_type_overrides(world, config)

    screens_by_num = {s.screen_num: s for s in world.overworld.screens}
    for num in _EXTRA_PB_AND_BOMB_SCREENS:
        assert screens_by_num[num].entrance_type == EntranceType.POWER_BRACELET_AND_BOMB, (
            f"Screen {num:#04x} should be POWER_BRACELET_AND_BOMB, "
            f"got {screens_by_num[num].entrance_type}"
        )


def test_extra_pb_blocks_does_not_affect_unrelated_screens(bins):
    """extra_power_bracelet_blocks: screens outside the affected set keep their vanilla type."""
    world = parse_game_world(bins)
    vanilla_screens = {s.screen_num: s.entrance_type for s in world.overworld.screens}

    config = _config(Flags(extra_power_bracelet_blocks=Tristate.ON))
    apply_entrance_type_overrides(world, config)

    for screen in world.overworld.screens:
        if screen.screen_num not in _EXTRA_PB_AND_BOMB_SCREENS:
            assert screen.entrance_type == vanilla_screens[screen.screen_num], (
                f"Screen {screen.screen_num:#04x} entrance_type changed unexpectedly"
            )


def test_both_flags_on_applies_both_sets_independently(bins):
    """Both flags on: raft screens get RAFT, PB screens get POWER_BRACELET_AND_BOMB."""
    world = parse_game_world(bins)
    config = _config(Flags(
        extra_raft_blocks=Tristate.ON,
        extra_power_bracelet_blocks=Tristate.ON,
    ))
    apply_entrance_type_overrides(world, config)
    screens_by_num = {s.screen_num: s for s in world.overworld.screens}

    for num in _EXTRA_RAFT_SCREENS:
        assert screens_by_num[num].entrance_type == EntranceType.RAFT
    for num in _EXTRA_RAFT_AND_BOMB_SCREENS:
        assert screens_by_num[num].entrance_type == EntranceType.RAFT_AND_BOMB
    for num in _EXTRA_PB_AND_BOMB_SCREENS:
        assert screens_by_num[num].entrance_type == EntranceType.POWER_BRACELET_AND_BOMB


# =============================================================================
# 2. Serializer patch tests
# =============================================================================

def test_extra_raft_blocks_asm_patch_written(bins):
    """extra_raft_blocks behavior patch: all expected bytes appear at correct offsets."""
    originals = _load_originals()
    gw = parse_game_world(bins)
    config = _config(Flags(extra_raft_blocks=Tristate.ON))
    data_patch = serialize_game_world(gw, originals)
    patch = data_patch.merge(build_behavior_patch(config))

    for edit in ExtraRaftBlocks().get_edits():
        assert edit.offset in patch.data, (
            f"extra_raft_blocks: offset {edit.offset:#x} missing from patch"
        )
        assert patch.data[edit.offset] == edit.new_bytes, (
            f"extra_raft_blocks: offset {edit.offset:#x} has wrong bytes "
            f"(got {patch.data[edit.offset]!r}, expected {edit.new_bytes!r})"
        )


def test_extra_raft_blocks_asm_patch_absent_by_default(bins):
    """Without extra_raft_blocks, none of its offsets appear."""
    originals = _load_originals()
    gw = parse_game_world(bins)
    config = _config(Flags())
    data_patch = serialize_game_world(gw, originals)
    patch = data_patch.merge(build_behavior_patch(config))

    for edit in ExtraRaftBlocks().get_edits():
        assert edit.offset not in patch.data, (
            f"extra_raft_blocks: offset {edit.offset:#x} unexpectedly present in default patch"
        )


def test_extra_pb_blocks_asm_patch_written(bins):
    """extra_power_bracelet_blocks behavior patch: all expected bytes appear at correct offsets."""
    originals = _load_originals()
    gw = parse_game_world(bins)
    config = _config(Flags(extra_power_bracelet_blocks=Tristate.ON))
    data_patch = serialize_game_world(gw, originals)
    patch = data_patch.merge(build_behavior_patch(config))

    for edit in ExtraPowerBraceletBlocks().get_edits():
        assert edit.offset in patch.data, (
            f"extra_power_bracelet_blocks: offset {edit.offset:#x} missing from patch"
        )
        assert patch.data[edit.offset] == edit.new_bytes, (
            f"extra_power_bracelet_blocks: offset {edit.offset:#x} has wrong bytes "
            f"(got {patch.data[edit.offset]!r}, expected {edit.new_bytes!r})"
        )


def test_extra_pb_blocks_asm_patch_absent_by_default(bins):
    """Without extra_power_bracelet_blocks, none of its offsets appear."""
    originals = _load_originals()
    gw = parse_game_world(bins)
    config = _config(Flags())
    data_patch = serialize_game_world(gw, originals)
    patch = data_patch.merge(build_behavior_patch(config))

    for edit in ExtraPowerBraceletBlocks().get_edits():
        assert edit.offset not in patch.data, (
            f"extra_power_bracelet_blocks: offset {edit.offset:#x} unexpectedly present in default patch"
        )


# =============================================================================
# 3. Validator reachability tests
# =============================================================================

def test_extra_raft_blocks_screen_unreachable_without_raft(bins):
    """With extra_raft_blocks on, a screen in _EXTRA_RAFT_SCREENS is inaccessible
    without the raft."""
    world = parse_game_world(bins)
    config = _config(Flags(extra_raft_blocks=Tristate.ON))
    apply_entrance_type_overrides(world, config)

    # Pick one representative screen from the extra raft set
    sample_screen_num = next(iter(sorted(_EXTRA_RAFT_SCREENS)))
    screen = next(s for s in world.overworld.screens if s.screen_num == sample_screen_num)

    validator = GameValidator(world, avoid_required_hard_combat=False)
    # No items in inventory — raft not present
    assert not validator._can_access_screen(screen), (
        f"Screen {sample_screen_num:#04x} should be inaccessible without raft"
    )


def test_extra_raft_blocks_screen_reachable_with_raft(bins):
    """With extra_raft_blocks on, a screen in _EXTRA_RAFT_SCREENS is accessible with raft."""
    world = parse_game_world(bins)
    config = _config(Flags(extra_raft_blocks=Tristate.ON))
    apply_entrance_type_overrides(world, config)

    sample_screen_num = next(iter(sorted(_EXTRA_RAFT_SCREENS)))
    screen = next(s for s in world.overworld.screens if s.screen_num == sample_screen_num)

    validator = GameValidator(world, avoid_required_hard_combat=False)
    validator.inventory.add_item(Item.RAFT)
    assert validator._can_access_screen(screen), (
        f"Screen {sample_screen_num:#04x} should be accessible with raft"
    )


def test_extra_pb_blocks_screen_unreachable_without_bracelet(bins):
    """With extra_power_bracelet_blocks on, a screen in _EXTRA_PB_AND_BOMB_SCREENS
    is inaccessible without the power bracelet."""
    world = parse_game_world(bins)
    config = _config(Flags(extra_power_bracelet_blocks=Tristate.ON))
    apply_entrance_type_overrides(world, config)

    sample_screen_num = next(iter(sorted(_EXTRA_PB_AND_BOMB_SCREENS)))
    screen = next(s for s in world.overworld.screens if s.screen_num == sample_screen_num)

    validator = GameValidator(world, avoid_required_hard_combat=False)
    assert not validator._can_access_screen(screen), (
        f"Screen {sample_screen_num:#04x} should be inaccessible without power bracelet"
    )


def test_extra_pb_blocks_screen_unreachable_with_bracelet_but_no_sword(bins):
    """POWER_BRACELET_AND_BOMB requires both bracelet and a sword/wand.
    Bracelet alone is not sufficient."""
    world = parse_game_world(bins)
    config = _config(Flags(extra_power_bracelet_blocks=Tristate.ON))
    apply_entrance_type_overrides(world, config)

    sample_screen_num = next(iter(sorted(_EXTRA_PB_AND_BOMB_SCREENS)))
    screen = next(s for s in world.overworld.screens if s.screen_num == sample_screen_num)

    validator = GameValidator(world, avoid_required_hard_combat=False)
    validator.inventory.add_item(Item.POWER_BRACELET)
    # No sword — should still be blocked
    assert not validator._can_access_screen(screen), (
        f"Screen {sample_screen_num:#04x} should require a sword in addition to power bracelet"
    )


def test_extra_pb_blocks_screen_reachable_with_bracelet_and_sword(bins):
    """With extra_power_bracelet_blocks on, a PB screen is accessible with bracelet + sword."""
    world = parse_game_world(bins)
    config = _config(Flags(extra_power_bracelet_blocks=Tristate.ON))
    apply_entrance_type_overrides(world, config)

    sample_screen_num = next(iter(sorted(_EXTRA_PB_AND_BOMB_SCREENS)))
    screen = next(s for s in world.overworld.screens if s.screen_num == sample_screen_num)

    validator = GameValidator(world, avoid_required_hard_combat=False)
    validator.inventory.add_item(Item.POWER_BRACELET)
    validator.inventory.add_item(Item.WOOD_SWORD)
    assert validator._can_access_screen(screen), (
        f"Screen {sample_screen_num:#04x} should be accessible with bracelet + sword"
    )


# =============================================================================
# 4. Flag constraint test
# =============================================================================

def test_extra_pb_blocks_incompatible_with_include_any_road_caves(bins):
    """extra_power_bracelet_blocks=ON with include_any_road_caves=ON must fail validation."""
    flags = Flags(
        extra_power_bracelet_blocks=Tristate.ON,
        cave_shuffle_mode=CaveShuffleMode.NON_DUNGEONS_ONLY,
        include_any_road_caves=Tristate.ON,
    )
    errors = validate_flags_static(flags)
    assert errors, "Expected a validation error but got none"
    assert any("Power Bracelet" in e or "any road" in e.lower() or "bracelet" in e.lower()
               for e in errors), (
        f"Expected a PB/any-road conflict error, got: {errors}"
    )


def test_extra_pb_blocks_valid_without_any_road_caves(bins):
    """extra_power_bracelet_blocks=ON without include_any_road_caves must pass validation."""
    flags = Flags(extra_power_bracelet_blocks=Tristate.ON)
    errors = validate_flags_static(flags)
    pb_errors = [e for e in errors if "bracelet" in e.lower() or "any road" in e.lower()]
    assert not pb_errors, f"Unexpected PB-related errors: {pb_errors}"


# =============================================================================
# 5. End-to-end beatable seed tests
# =============================================================================

def test_extra_raft_blocks_produces_beatable_seed(bins):
    """extra_raft_blocks on: assumed fill + GameValidator must pass for a single seed."""
    world = parse_game_world(bins)
    seed = 42
    flags = Flags(extra_raft_blocks=Tristate.ON)
    config = _config(flags, seed)

    apply_entrance_type_overrides(world, config)
    success = assumed_fill(world, config, SeededRng(seed))

    assert success, "assumed_fill failed with extra_raft_blocks"
    assert GameValidator(world, config.avoid_required_hard_combat).is_seed_valid(), (
        "Seed invalid after assumed_fill with extra_raft_blocks"
    )


def test_extra_pb_blocks_produces_beatable_seed(bins):
    """extra_power_bracelet_blocks on: assumed fill + GameValidator must pass for a single seed."""
    world = parse_game_world(bins)
    seed = 42
    flags = Flags(extra_power_bracelet_blocks=Tristate.ON)
    config = _config(flags, seed)

    apply_entrance_type_overrides(world, config)
    success = assumed_fill(world, config, SeededRng(seed))

    assert success, "assumed_fill failed with extra_power_bracelet_blocks"
    assert GameValidator(world, config.avoid_required_hard_combat).is_seed_valid(), (
        "Seed invalid after assumed_fill with extra_power_bracelet_blocks"
    )


def test_both_block_flags_produce_beatable_seed(bins):
    """Both block flags on simultaneously: assumed fill + GameValidator must pass."""
    world = parse_game_world(bins)
    seed = 42
    flags = Flags(
        extra_raft_blocks=Tristate.ON,
        extra_power_bracelet_blocks=Tristate.ON,
    )
    config = _config(flags, seed)

    apply_entrance_type_overrides(world, config)
    success = assumed_fill(world, config, SeededRng(seed))

    assert success, "assumed_fill failed with both block flags on"
    assert GameValidator(world, config.avoid_required_hard_combat).is_seed_valid(), (
        "Seed invalid after assumed_fill with both block flags on"
    )


def test_extra_raft_blocks_with_dungeon_shuffle_produces_beatable_seed(bins):
    """extra_raft_blocks + dungeon entrance shuffle: assumed fill must still produce a beatable seed.

    This is the key ordering regression test: if entrance type overrides were applied
    after shuffle_caves(), the shuffler would place caves without knowing about the new
    raft gates, potentially producing unbeatable seeds.
    """
    from zora.entrance_randomizer import shuffle_caves

    world = parse_game_world(bins)
    seed = 42
    flags = Flags(
        extra_raft_blocks=Tristate.ON,
        cave_shuffle_mode=CaveShuffleMode.DUNGEONS_ONLY,
    )
    config = _config(flags, seed)
    rng = SeededRng(seed)

    # Ordering: overrides first, then shuffle, then fill
    apply_entrance_type_overrides(world, config)

    raft_locations = [0x2F, 0x45] + list(_EXTRA_RAFT_SCREENS) + list(_EXTRA_RAFT_AND_BOMB_SCREENS)
    shuffle_caves(
        world, rng,
        shuffle=config.shuffle_non_dungeon_caves,
        include_bracelet_caves=config.include_any_road_caves,
        include_wood_sword_cave=config.include_wood_sword_cave,
        shuffle_armos=config.shuffle_armos_location,
        add_armos_item=config.shuffle_armos_item,
        mirror_ow=False,
        just_dungeons=True,
        shuffle_dungeons=True,
        overworld_block_needed=False,
        raft_locations=raft_locations,
    )

    success = assumed_fill(world, config, SeededRng(seed))
    assert success, "assumed_fill failed with extra_raft_blocks + dungeon shuffle"
    assert GameValidator(world, config.avoid_required_hard_combat).is_seed_valid(), (
        "Seed invalid after assumed_fill with extra_raft_blocks + dungeon shuffle"
    )
