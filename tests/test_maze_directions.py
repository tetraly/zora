"""
Tests for Lost Hills and Dead Woods maze direction randomization.

Coverage:
  1. Round-trip: parse → serialize produces vanilla direction bytes unchanged
  2. Direction randomization: correct length, valid values, fixed terminal direction
  3. Determinism: same seed produces same directions
  4. No-op when flags are off
  5. Hint text generation: correct format for all direction values
  6. Hint integration: quote slots updated iff flag is on
  7. Serializer patch: direction bytes land at correct ROM address
  8. Behavior patches: screen layout bytes present iff flag is on
  9. Flag constraints: randomize_lost/dead_woods requires hint_mode in {community, helpful}
  10. End-to-end smoke test: full generation completes with both flags on
"""
from pathlib import Path

import pytest

from flags.flags_generated import Flags, Tristate
from flags.flags_generated import HintMode as FlagHintMode
from zora.api.validation import validate_flags_static
from zora.data_model import GameWorld, OverworldDirection
from zora.game_config import GameConfig, HintMode, resolve_game_config
from zora.generate_game import generate_game
from zora.hint_randomizer import (
    HintType,
    _dead_woods_hint_text,
    _lost_hills_hint_text,
    expand_quote_slots,
    randomize_hints,
)
from zora.overworld_randomizer import randomize_maze_directions
from zora.parser import load_bin_files, parse_game_world
from zora.patches import build_behavior_patch
from zora.patches.randomize_dead_woods import RandomizeDeadWoods
from zora.patches.randomize_lost_hills import RandomizeLostHills
from zora.rng import SeededRng
from zora.rom_layout import MAZE_DIRECTIONS_ADDRESS
from zora.serializer import serialize_game_world

TEST_DATA = Path(__file__).parent.parent / "rom_data"

VANILLA_DEAD_WOODS = [
    OverworldDirection.UP_NORTH,
    OverworldDirection.LEFT_WEST,
    OverworldDirection.DOWN_SOUTH,
    OverworldDirection.LEFT_WEST,
]
VANILLA_LOST_HILLS = [
    OverworldDirection.UP_NORTH,
    OverworldDirection.UP_NORTH,
    OverworldDirection.UP_NORTH,
    OverworldDirection.UP_NORTH,
]


def _fresh_world():
    return parse_game_world(load_bin_files(TEST_DATA))


def _load_originals():
    names = [
        "level_1_6_data.bin", "level_7_9_data.bin", "level_info.bin",
        "overworld_data.bin", "armos_item.bin", "coast_item.bin",
        "white_sword_requirement.bin", "magical_sword_requirement.bin",
    ]
    return {n: (TEST_DATA / n).read_bytes() for n in names}


def _config(flags: Flags, seed: int = 0) -> GameConfig:
    return resolve_game_config(flags, SeededRng(seed))


# =============================================================================
# 1. Round-trip: vanilla direction bytes survive parse → serialize unchanged
# =============================================================================

def test_maze_directions_roundtrip():
    """Parse → serialize must reproduce the vanilla direction bytes at MAZE_DIRECTIONS_ADDRESS."""
    originals = _load_originals()
    gw = _fresh_world()
    patch = serialize_game_world(gw, originals)

    got = patch.data[MAZE_DIRECTIONS_ADDRESS]
    # Dead Woods: North, West, South, West  →  0x08 0x02 0x04 0x02
    # Lost Hills: Up, Up, Up, Up            →  0x08 0x08 0x08 0x08
    expected = bytes([0x08, 0x02, 0x04, 0x02,  0x08, 0x08, 0x08, 0x08])
    assert got == expected, (
        f"maze_directions mismatch: got {list(got)!r}, expected {list(expected)!r}"
    )


def test_maze_directions_parsed_correctly():
    """Parser populates direction lists with correct OverworldDirection values."""
    gw = _fresh_world()
    assert gw.overworld.dead_woods_directions == VANILLA_DEAD_WOODS
    assert gw.overworld.lost_hills_directions == VANILLA_LOST_HILLS


# =============================================================================
# 2. Direction randomization: structure constraints
# =============================================================================

def test_randomize_lost_hills_length_and_terminal():
    """Lost Hills sequence must be length 4 with UP_NORTH as the final step."""
    gw = _fresh_world()
    flags = Flags(randomize_lost_hills=Tristate.ON, hint_mode=FlagHintMode.COMMUNITY)
    config = _config(flags)
    randomize_maze_directions(gw, config, SeededRng(42))

    dirs = gw.overworld.lost_hills_directions
    assert len(dirs) == 4
    assert dirs[-1] == OverworldDirection.UP_NORTH
    assert all(d in (OverworldDirection.UP_NORTH, OverworldDirection.DOWN_SOUTH,
                     OverworldDirection.RIGHT_EAST) for d in dirs)


def test_randomize_dead_woods_length_and_terminal():
    """Dead Woods sequence must be length 4 with DOWN_SOUTH as the final step."""
    gw = _fresh_world()
    flags = Flags(randomize_dead_woods=Tristate.ON, hint_mode=FlagHintMode.COMMUNITY)
    config = _config(flags)
    randomize_maze_directions(gw, config, SeededRng(42))

    dirs = gw.overworld.dead_woods_directions
    assert len(dirs) == 4
    assert dirs[-1] == OverworldDirection.DOWN_SOUTH
    assert all(d in (OverworldDirection.UP_NORTH, OverworldDirection.DOWN_SOUTH,
                     OverworldDirection.LEFT_WEST) for d in dirs)


# =============================================================================
# 3. Determinism: same seed → same directions
# =============================================================================

def test_lost_hills_deterministic():
    flags = Flags(randomize_lost_hills=Tristate.ON, hint_mode=FlagHintMode.COMMUNITY)
    config = _config(flags)

    gw1 = _fresh_world()
    randomize_maze_directions(gw1, config, SeededRng(99))

    gw2 = _fresh_world()
    randomize_maze_directions(gw2, config, SeededRng(99))

    assert gw1.overworld.lost_hills_directions == gw2.overworld.lost_hills_directions


def test_dead_woods_deterministic():
    flags = Flags(randomize_dead_woods=Tristate.ON, hint_mode=FlagHintMode.COMMUNITY)
    config = _config(flags)

    gw1 = _fresh_world()
    randomize_maze_directions(gw1, config, SeededRng(99))

    gw2 = _fresh_world()
    randomize_maze_directions(gw2, config, SeededRng(99))

    assert gw1.overworld.dead_woods_directions == gw2.overworld.dead_woods_directions


# =============================================================================
# 4. No-op when flags are off
# =============================================================================

def test_randomize_maze_directions_noop_when_both_off():
    """randomize_maze_directions must not mutate directions when both flags are off."""
    gw = _fresh_world()
    flags = Flags()  # both off by default
    config = _config(flags)
    randomize_maze_directions(gw, config, SeededRng(0))

    assert gw.overworld.lost_hills_directions == VANILLA_LOST_HILLS
    assert gw.overworld.dead_woods_directions == VANILLA_DEAD_WOODS


def test_randomize_lost_hills_only_leaves_dead_woods_unchanged():
    gw = _fresh_world()
    flags = Flags(randomize_lost_hills=Tristate.ON, hint_mode=FlagHintMode.COMMUNITY)
    config = _config(flags)
    randomize_maze_directions(gw, config, SeededRng(7))

    assert gw.overworld.dead_woods_directions == VANILLA_DEAD_WOODS


def test_randomize_dead_woods_only_leaves_lost_hills_unchanged():
    gw = _fresh_world()
    flags = Flags(randomize_dead_woods=Tristate.ON, hint_mode=FlagHintMode.COMMUNITY)
    config = _config(flags)
    randomize_maze_directions(gw, config, SeededRng(7))

    assert gw.overworld.lost_hills_directions == VANILLA_LOST_HILLS


# =============================================================================
# 5. Hint text generation
# =============================================================================

def test_lost_hills_hint_text_all_directions():
    """_lost_hills_hint_text produces correct format for each direction value."""
    dirs = [OverworldDirection.UP_NORTH, OverworldDirection.DOWN_SOUTH,
            OverworldDirection.RIGHT_EAST, OverworldDirection.UP_NORTH]
    assert _lost_hills_hint_text(dirs) == "GO UP, DOWN,|RIGHT, UP|THE MOUNTAIN AHEAD"


def test_lost_hills_hint_text_vanilla():
    assert _lost_hills_hint_text(VANILLA_LOST_HILLS) == \
        "GO UP, UP,|UP, UP|THE MOUNTAIN AHEAD"


def test_dead_woods_hint_text_all_directions():
    """_dead_woods_hint_text produces correct format for each direction value."""
    dirs = [OverworldDirection.UP_NORTH, OverworldDirection.LEFT_WEST,
            OverworldDirection.DOWN_SOUTH, OverworldDirection.DOWN_SOUTH]
    assert _dead_woods_hint_text(dirs) == "GO NORTH, WEST,|SOUTH, SOUTH TO|THE FOREST OF MAZE"


def test_dead_woods_hint_text_vanilla():
    assert _dead_woods_hint_text(VANILLA_DEAD_WOODS) == \
        "GO NORTH, WEST,|SOUTH, WEST TO|THE FOREST OF MAZE"


# =============================================================================
# 6. Hint integration: directional hints go to the right quote slots
# =============================================================================

def _quote_text_for_id(gw: GameWorld, quote_id: int) -> str:
    return str(next(q.text for q in gw.quotes if q.quote_id == quote_id))


def test_lost_hills_quote_updated_when_flag_on():
    gw = _fresh_world()
    flags = Flags(randomize_lost_hills=Tristate.ON, hint_mode=FlagHintMode.COMMUNITY)
    config = _config(flags, seed=5)
    randomize_maze_directions(gw, config, SeededRng(5))
    expand_quote_slots(gw, config, SeededRng(5))
    randomize_hints(gw, config, SeededRng(5))

    expected = _lost_hills_hint_text(gw.overworld.lost_hills_directions)
    assert _quote_text_for_id(gw, HintType.LOST_HILLS_HINT) == expected


def test_dead_woods_quote_updated_when_flag_on():
    gw = _fresh_world()
    flags = Flags(randomize_dead_woods=Tristate.ON, hint_mode=FlagHintMode.COMMUNITY)
    config = _config(flags, seed=5)
    randomize_maze_directions(gw, config, SeededRng(5))
    expand_quote_slots(gw, config, SeededRng(5))
    randomize_hints(gw, config, SeededRng(5))

    expected = _dead_woods_hint_text(gw.overworld.dead_woods_directions)
    assert _quote_text_for_id(gw, HintType.DEAD_WOODS_HINT) == expected


def test_lost_hills_quote_unchanged_when_flag_off():
    """When randomize_lost_hills is off, the Lost Hills cave quote is not overwritten."""
    gw = _fresh_world()
    _original_text = _quote_text_for_id(gw, HintType.LOST_HILLS_HINT)

    flags = Flags(hint_mode=FlagHintMode.COMMUNITY)
    config = _config(flags)
    expand_quote_slots(gw, config, SeededRng(0))
    randomize_hints(gw, config, SeededRng(0))

    # In community mode the slot gets a community hint, not the directional text
    # — just verify it's not the directional hint format
    text = _quote_text_for_id(gw, HintType.LOST_HILLS_HINT)
    assert "THE MOUNTAIN AHEAD" not in text


def test_dead_woods_quote_unchanged_when_flag_off():
    gw = _fresh_world()

    flags = Flags(hint_mode=FlagHintMode.COMMUNITY)
    config = _config(flags)
    expand_quote_slots(gw, config, SeededRng(0))
    randomize_hints(gw, config, SeededRng(0))

    text = _quote_text_for_id(gw, HintType.DEAD_WOODS_HINT)
    assert "THE FOREST OF MAZE" not in text


# =============================================================================
# 7. Serializer patch: direction bytes land at the correct ROM address
# =============================================================================

def test_serializer_writes_randomized_lost_hills_directions():
    originals = _load_originals()
    gw = _fresh_world()
    flags = Flags(randomize_lost_hills=Tristate.ON, hint_mode=FlagHintMode.COMMUNITY)
    config = _config(flags, seed=3)
    randomize_maze_directions(gw, config, SeededRng(3))

    patch = serialize_game_world(gw, originals, hint_mode=HintMode.COMMUNITY)
    got_lost_hills = patch.data[MAZE_DIRECTIONS_ADDRESS][4:8]
    expected = bytes(d.value for d in gw.overworld.lost_hills_directions)
    assert got_lost_hills == expected


def test_serializer_writes_randomized_dead_woods_directions():
    originals = _load_originals()
    gw = _fresh_world()
    flags = Flags(randomize_dead_woods=Tristate.ON, hint_mode=FlagHintMode.COMMUNITY)
    config = _config(flags, seed=3)
    randomize_maze_directions(gw, config, SeededRng(3))

    patch = serialize_game_world(gw, originals, hint_mode=HintMode.COMMUNITY)
    got_dead_woods = patch.data[MAZE_DIRECTIONS_ADDRESS][0:4]
    expected = bytes(d.value for d in gw.overworld.dead_woods_directions)
    assert got_dead_woods == expected


# =============================================================================
# 8. Behavior patches: screen layout bytes present iff flag is on
# =============================================================================

def test_lost_hills_behavior_patches_present_when_flag_on():
    flags = Flags(randomize_lost_hills=Tristate.ON, hint_mode=FlagHintMode.COMMUNITY)
    config = _config(flags)

    originals = _load_originals()
    gw = _fresh_world()
    data_patch = serialize_game_world(gw, originals, hint_mode=HintMode.COMMUNITY)
    asm_patch = build_behavior_patch(config)
    patch = data_patch.merge(asm_patch)
    for edit in RandomizeLostHills().get_edits():
        assert patch.data.get(edit.offset) == edit.new_bytes, (
            f"Lost Hills patch missing or wrong at {edit.offset:#x}: "
            f"got {patch.data.get(edit.offset)!r}, expected {edit.new_bytes!r}"
        )


def test_lost_hills_behavior_patches_absent_when_flag_off():
    flags = Flags()
    config = _config(flags)

    originals = _load_originals()
    gw = _fresh_world()
    data_patch = serialize_game_world(gw, originals)
    asm_patch = build_behavior_patch(config)
    patch = data_patch.merge(asm_patch)
    for edit in RandomizeLostHills().get_edits():
        assert edit.offset not in patch.data, (
            f"Lost Hills patch unexpectedly present at {edit.offset:#x}"
        )


def test_dead_woods_behavior_patches_present_when_flag_on():
    flags = Flags(randomize_dead_woods=Tristate.ON, hint_mode=FlagHintMode.COMMUNITY)
    config = _config(flags)

    originals = _load_originals()
    gw = _fresh_world()
    data_patch = serialize_game_world(gw, originals, hint_mode=HintMode.COMMUNITY)
    asm_patch = build_behavior_patch(config)
    patch = data_patch.merge(asm_patch)
    for edit in RandomizeDeadWoods().get_edits():
        assert patch.data.get(edit.offset) == edit.new_bytes, (
            f"Dead Woods patch missing or wrong at {edit.offset:#x}: "
            f"got {patch.data.get(edit.offset)!r}, expected {edit.new_bytes!r}"
        )


def test_dead_woods_behavior_patches_absent_when_flag_off():
    flags = Flags()
    config = _config(flags)

    originals = _load_originals()
    gw = _fresh_world()
    data_patch = serialize_game_world(gw, originals)
    asm_patch = build_behavior_patch(config)
    patch = data_patch.merge(asm_patch)
    for edit in RandomizeDeadWoods().get_edits():
        assert edit.offset not in patch.data, (
            f"Dead Woods patch unexpectedly present at {edit.offset:#x}"
        )


# =============================================================================
# 9. Flag constraints
# =============================================================================

@pytest.mark.parametrize("maze_flag,label", [
    ("randomize_lost_hills", "Lost Hills"),
    ("randomize_dead_woods", "Dead Woods"),
])
@pytest.mark.parametrize("maze_value", [Tristate.ON, Tristate.RANDOM])
def test_maze_flag_incompatible_with_hint_mode_vanilla(maze_flag, label, maze_value):
    """randomize_lost/dead_woods ON or RANDOM must be rejected when hint_mode=vanilla."""
    flags = Flags(**{
        maze_flag: maze_value,
        "hint_mode": FlagHintMode.VANILLA,
    })
    errors = validate_flags_static(flags)
    assert errors, f"{label} with hint_mode=vanilla should produce a constraint error"
    assert any("hint" in e.lower() for e in errors), (
        f"Expected a hint-mode error, got: {errors}"
    )


@pytest.mark.parametrize("maze_flag,label", [
    ("randomize_lost_hills", "Lost Hills"),
    ("randomize_dead_woods", "Dead Woods"),
])
@pytest.mark.parametrize("maze_value", [Tristate.ON, Tristate.RANDOM])
def test_maze_flag_incompatible_with_hint_mode_blank(maze_flag, label, maze_value):
    """randomize_lost/dead_woods ON or RANDOM must be rejected when hint_mode=blank."""
    flags = Flags(**{
        maze_flag: maze_value,
        "hint_mode": FlagHintMode.BLANK,
    })
    errors = validate_flags_static(flags)
    assert errors, f"{label} with hint_mode=blank should produce a constraint error"
    assert any("hint" in e.lower() for e in errors), (
        f"Expected a hint-mode error, got: {errors}"
    )


def test_maze_flags_valid_when_hint_mode_community():
    """Both maze flags ON with hint_mode=community should pass constraint validation."""
    flags = Flags(
        randomize_lost_hills=Tristate.ON,
        randomize_dead_woods=Tristate.ON,
        hint_mode=FlagHintMode.COMMUNITY,
    )
    errors = validate_flags_static(flags)
    assert not errors, f"Expected no errors, got: {errors}"


def test_maze_flags_valid_when_hint_mode_helpful():
    """Both maze flags ON with hint_mode=helpful should pass constraint validation."""
    flags = Flags(
        randomize_lost_hills=Tristate.ON,
        randomize_dead_woods=Tristate.ON,
        hint_mode=FlagHintMode.HELPFUL,
    )
    errors = validate_flags_static(flags)
    assert not errors, f"Expected no errors, got: {errors}"


# =============================================================================
# 10. End-to-end smoke test
# =============================================================================

def test_full_generation_with_both_maze_flags():
    """Full generate_game pipeline completes without error with both maze flags on."""

    flags = Flags(
        randomize_lost_hills=Tristate.ON,
        randomize_dead_woods=Tristate.ON,
        hint_mode=FlagHintMode.COMMUNITY,
    )
    ips_bytes, hash_names, *_ = generate_game(flags, seed=12345)
    assert len(ips_bytes) > 0
    assert len(hash_names) == 4
