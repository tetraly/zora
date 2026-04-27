"""
generate_game: core entry point for randomized game generation.

Called by both the API route and the CLI. Accepts resolved flags and a seed,
runs assumed fill, serializes to a Patch, and returns IPS patch bytes.
"""

import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from flags.flags_generated import CosmeticFlags, Flags
from zora.cave_randomizer import randomize_caves
from zora.dungeon_item_shuffler import shuffle_dungeon_items
from zora.dungeon_randomizer import randomize_dungeon_palettes
from zora.dungeon.dungeon import randomize_dungeons
from zora.dungeon.shuffle_dungeon_rooms import _clear_boss_cry_bits, _fix_special_rooms
from zora.enemy.randomize import randomize_enemies
from zora.entrance_randomizer import randomize_entrances
from zora.game_config import resolve_game_config
from zora.hash_code import apply_hash_code, hash_code_display_names
from zora.hint_randomizer import expand_quote_slots, randomize_hints
from zora.item_randomizer import randomize_items
from zora.l4_sword_randomizer import place_l4_sword
from zora.normalizer import normalize_data
from zora.overworld_randomizer import randomize_maze_directions, recalculate_recorder_warp_screens, remap_game_start
from zora.level_gen.orchestrator import generate_dungeon_shapes
from zora.integrity_check import integrity_check
from zora.parser import is_randomizer_rom, load_bin_files, load_bin_files_from_rom, parse_game_world
from zora.patch import build_ips_patch
from zora.patches import build_behavior_patch
from zora.rng import SeededRng
from zora.rom_layout import (
    ARMOS_ITEM_ADDRESS,
    COAST_ITEM_ADDRESS,
    LEVEL_1_6_DATA_ADDRESS,
    LEVEL_7_9_DATA_ADDRESS,
    LEVEL_INFO_ADDRESS,
    MAGICAL_SWORD_REQUIREMENT_ADDRESS,
    OVERWORLD_DATA_ADDRESS,
    WHITE_SWORD_REQUIREMENT_ADDRESS,
)
from zora.serializer import serialize_game_world
from zora.shop_shuffler import randomize_shop_prices, randomize_shops
from zora.spoilers import build_spoiler_data, build_spoiler_log

ROM_DATA = Path(__file__).parent.parent / "rom_data"


# Ordered randomizer pipeline. Each step self-gates on its config flags.
# Order is significant — see CLAUDE.md "Randomizer call ordering".
_RANDOMIZERS = [
    normalize_data,
    randomize_entrances,
    recalculate_recorder_warp_screens,
    place_l4_sword,
    randomize_dungeons,  # before randomize_enemies: room positions must be settled first
    randomize_enemies,   # before randomize_items: boss placement affects reachability
    randomize_shops,
    remap_game_start,
    randomize_dungeon_palettes,
    randomize_maze_directions,
    randomize_caves,     # must run before randomize_hints so heart requirements are set
    shuffle_dungeon_items,
    randomize_items,
    randomize_shop_prices,  # after randomize_items: shop contents are final
    expand_quote_slots,  # adds quote slots 39-43; must run before randomize_hints
    randomize_hints,
]

_CRITICAL_STEPS = {
    randomize_dungeons,
    randomize_enemies,
    shuffle_dungeon_items,
    randomize_items,
}


def generate_game(
    flags: Flags, seed: int, flag_string: str = "",
    rom_version: int | None = None, cosmetic_flags: CosmeticFlags | None = None,
) -> tuple[bytes, list[str], str, dict[str, Any]]:
    """Run assumed fill and serialize to IPS patch bytes.

    Args:
        flags:       Fully resolved Flags instance (no Tristate.RANDOM values).
        seed:        Integer seed for deterministic generation.
        rom_version: ROM revision detected by the client (0 = PRG0, 1 = PRG1, etc.).
                     None if the client did not supply a version. Reserved for
                     future PRG-version-specific patch logic.

    Returns:
        Tuple of (ips_patch_bytes, hash_code_names, spoiler_log, spoiler_data)
        where hash_code_names is a list of 4 display strings for the in-game hash
        code identifier, spoiler_log is a plain-text string, and spoiler_data is a
        structured dict for the interactive spoiler viewer.

    Raises:
        RuntimeError: if assumed fill cannot place all items.
    """
    bins = load_bin_files(ROM_DATA)

    rng = SeededRng(seed)
    config = resolve_game_config(flags, rng, cosmetic_flags)

    original_bins_bytes = {
        "level_1_6_data.bin": bins.level_1_6_data,
        "level_7_9_data.bin": bins.level_7_9_data,
        "level_info.bin":     bins.level_info,
        "overworld_data.bin": bins.overworld_data,
        "armos_item.bin":     bins.armos_item,
        "coast_item.bin":     bins.coast_item,
        "white_sword_requirement.bin":   bins.white_sword_requirement,
        "magical_sword_requirement.bin": bins.magical_sword_requirement,
    }

    # Some cave shuffle arrangements make item placement impossible.
    # Retry with a fresh game world (the RNG has advanced, producing a
    # different cave layout) when the pipeline fails.
    max_pipeline_attempts = 10
    for attempt in range(max_pipeline_attempts):
        game_world = parse_game_world(bins)
        try:
            generate_dungeon_shapes(game_world, bins, config, rng)
            # Apply the same post-shape repair pass that the shuffle pipeline
            # uses. generate_dungeon_shapes can produce rooms with
            # (movable_block, room_action) combinations that violate the
            # pushblock_purpose invariant — most notably
            # TRIFORCE_OF_POWER_OPENS_SHUTTERS rooms with movable_block=True
            # (boss rooms, kidnapped-gate rooms). Block 6 in
            # _fix_special_rooms demotes those movable_blocks to False.
            _clear_boss_cry_bits(game_world)
            for level in game_world.levels:
                _fix_special_rooms(level, game_world)
            integrity_check(game_world, "generate_dungeon_shapes")
            for step in _RANDOMIZERS:
                t0 = time.monotonic()
                step(game_world, config, rng)
                elapsed = time.monotonic() - t0
                if elapsed > 0.5:
                    logger.info("  %s: %.2fs", step.__name__, elapsed)
                if step in _CRITICAL_STEPS:
                    integrity_check(game_world, step.__name__)
            break
        except RuntimeError:
            if attempt == max_pipeline_attempts - 1:
                raise

    data_patch = serialize_game_world(
        game_world,
        original_bins_bytes,
        hint_mode=config.hint_mode,
        change_dungeon_nothing_code=config.shuffle_magical_sword and not config.progressive_items,
    )

    asm_patch = build_behavior_patch(config, rom_version)

    final_patch = data_patch.merge(asm_patch)

    hash_bytes = apply_hash_code(final_patch)
    hash_names = hash_code_display_names(hash_bytes)

    spoiler = build_spoiler_log(game_world, config, seed, flag_string)
    spoiler_json = build_spoiler_data(game_world, config, seed, flag_string)

    records = sorted(final_patch.data.items())
    return build_ips_patch(records), hash_names, spoiler, spoiler_json


def generate_game_from_rom(
    rom_bytes: bytes,
    flags: Flags,
    seed: int,
    flag_string: str = "",
    rom_version: int | None = None,
    cosmetic_flags: CosmeticFlags | None = None,
) -> tuple[bytes, list[str], str, dict[str, Any]]:
    """Run assumed fill against an uploaded ROM and return an IPS patch for it.

    Parses the game world directly from the supplied ROM bytes instead of the
    on-disk .bin files, and builds the serializer base from the same ROM so the
    resulting IPS patch is relative to that ROM.

    Args:
        rom_bytes:   Full .nes file bytes (must pass is_randomizer_rom()).
        flags:       Fully resolved Flags instance (no Tristate.RANDOM values).
        seed:        Integer seed for deterministic generation.
        rom_version: Optional ROM revision hint (unused currently, forwarded to
                     build_behavior_patch for future PRG-specific logic).

    Returns:
        Tuple of (ips_patch_bytes, hash_code_names, spoiler_log, spoiler_data).

    Raises:
        ValueError:   if rom_bytes does not pass the randomizer ROM check.
        RuntimeError: if assumed fill cannot place all items.
    """
    if not is_randomizer_rom(rom_bytes):
        raise ValueError("Uploaded file is not a recognised ZORA-randomized Zelda 1 ROM")

    bins = load_bin_files_from_rom(rom_bytes)

    rng = SeededRng(seed)
    config = resolve_game_config(flags, rng, cosmetic_flags)

    original_bins_bytes = {
        "level_1_6_data.bin": rom_bytes[LEVEL_1_6_DATA_ADDRESS: LEVEL_1_6_DATA_ADDRESS + 0x300],
        "level_7_9_data.bin": rom_bytes[LEVEL_7_9_DATA_ADDRESS: LEVEL_7_9_DATA_ADDRESS + 0x300],
        "level_info.bin":     rom_bytes[LEVEL_INFO_ADDRESS:      LEVEL_INFO_ADDRESS     + 0xA * 0xFC],
        "overworld_data.bin": rom_bytes[OVERWORLD_DATA_ADDRESS:  OVERWORLD_DATA_ADDRESS + 0x500],
        "armos_item.bin":     rom_bytes[ARMOS_ITEM_ADDRESS:      ARMOS_ITEM_ADDRESS     + 1],
        "coast_item.bin":     rom_bytes[COAST_ITEM_ADDRESS:      COAST_ITEM_ADDRESS     + 1],
        "white_sword_requirement.bin": rom_bytes[
            WHITE_SWORD_REQUIREMENT_ADDRESS: WHITE_SWORD_REQUIREMENT_ADDRESS + 1
        ],
        "magical_sword_requirement.bin": rom_bytes[
            MAGICAL_SWORD_REQUIREMENT_ADDRESS: MAGICAL_SWORD_REQUIREMENT_ADDRESS + 1
        ],
    }

    max_pipeline_attempts = 10
    for attempt in range(max_pipeline_attempts):
        game_world = parse_game_world(bins)
        try:
            generate_dungeon_shapes(game_world, bins, config, rng)
            # Apply the same post-shape repair pass that the shuffle pipeline
            # uses. generate_dungeon_shapes can produce rooms with
            # (movable_block, room_action) combinations that violate the
            # pushblock_purpose invariant — most notably
            # TRIFORCE_OF_POWER_OPENS_SHUTTERS rooms with movable_block=True
            # (boss rooms, kidnapped-gate rooms). Block 6 in
            # _fix_special_rooms demotes those movable_blocks to False.
            _clear_boss_cry_bits(game_world)
            for level in game_world.levels:
                _fix_special_rooms(level, game_world)
            integrity_check(game_world, "generate_dungeon_shapes")
            for step in _RANDOMIZERS:
                step(game_world, config, rng)
                if step in _CRITICAL_STEPS:
                    integrity_check(game_world, step.__name__)
            break
        except RuntimeError:
            if attempt == max_pipeline_attempts - 1:
                raise

    data_patch = serialize_game_world(
        game_world,
        original_bins_bytes,
        hint_mode=config.hint_mode,
        change_dungeon_nothing_code=config.shuffle_magical_sword and not config.progressive_items,
    )

    asm_patch = build_behavior_patch(config, rom_version)

    final_patch = data_patch.merge(asm_patch)

    hash_bytes = apply_hash_code(final_patch)
    hash_names = hash_code_display_names(hash_bytes)

    spoiler = build_spoiler_log(game_world, config, seed, flag_string)
    spoiler_json = build_spoiler_data(game_world, config, seed, flag_string)

    records = sorted(final_patch.data.items())
    return build_ips_patch(records), hash_names, spoiler, spoiler_json
