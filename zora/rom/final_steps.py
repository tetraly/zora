"""The flag-dependent ROM work, as named final steps after the model is written.

serialize_game_world writes the GameWorld model; these steps then change the
ROM image in FINAL_STEPS order, each switched by its own setting:

  dungeon_nothing_code   the engine patch that reads $0E as "no item"
                         (Randomize Magical Sword, GameConfig.dungeon_nothing_code)
  code_patches           ZORA's 6502 patches and the per-level data they read
                         (B10's feature switch; Book is an Atlas, B49, inside it)
  encode_level_data      Encode level data (B82; zora/rom/level_encoding.py)
  slot_identity          Archipelago's slot name (External mode only; zora/rom/slot_identity.py)
  stamp_seed_code        the seed's code (FP-HASH-01), hashing the finished ROM
  player_settings        the player's settings (FP-SET-01), never part of the seed

The order matters: the level encoding comes after every write to the level
data, the seed's code hashes the encoded ROM and the slot name (each player's
code differs), and the player settings come after the code, which they never
change.
"""
from collections.abc import Callable
from dataclasses import dataclass

from ..model.game_world import GameWorld
from . import code_patches, owner_patches, slot_identity
from .game_config import DungeonNothingCode, GameConfig
from .layout import (
    ASM_NOTHING_CODE_PATCH_OFFSET,
    ASM_NOTHING_CODE_PATCH_VALUE,
    LEVEL_INFO_ADDRESS,
    LEVEL_INFO_SIZE,
)
from .player_settings import PlayerSettings, apply_player_settings


@dataclass(frozen=True)
class FinalSettings:
    """What the final steps read: the serialization settings and, for a
    finished ROM a player downloads, the player settings (None leaves them
    unwritten)."""
    config: GameConfig
    player_settings: PlayerSettings | None = None


@dataclass(frozen=True)
class FinalStep:
    """One final ROM step: its name, the setting that switches it, the work
    (on the ROM image, in place) and the predicate that switches it on."""
    name: str
    setting: str
    run: Callable[[bytearray, GameWorld, FinalSettings], None]
    enabled: Callable[[FinalSettings], bool]


def dungeon_nothing_code(rom: bytearray, _world: GameWorld, _settings: FinalSettings) -> None:
    """The engine patch that makes the $0E remap valid: the sentinel comparison
    reads $0E, so $03 can be the magical sword inside dungeons."""
    rom[ASM_NOTHING_CODE_PATCH_OFFSET] = ASM_NOTHING_CODE_PATCH_VALUE


def write_code_patches(rom: bytearray, world: GameWorld, settings: FinalSettings) -> None:
    """B10's CODE patches (features-behavior.md; docs/rom-map.md), with the
    per-level and overworld level-information bytes the patched code reads.
    Book is an Atlas (B49) off leaves its patch out (FL-OFF-05); the progressive
    patches are written only with their ZORA flags on (PI-CODE-01)."""
    for level in world.levels:
        start = LEVEL_INFO_ADDRESS + level.level_num * LEVEL_INFO_SIZE
        info = rom[start:start + LEVEL_INFO_SIZE]
        code_patches.write_level_info_data(world, level, info)
        rom[start:start + LEVEL_INFO_SIZE] = info
    overworld_info = rom[LEVEL_INFO_ADDRESS:LEVEL_INFO_ADDRESS + LEVEL_INFO_SIZE]
    code_patches.write_overworld_level_info_data(overworld_info)
    rom[LEVEL_INFO_ADDRESS:LEVEL_INFO_ADDRESS + LEVEL_INFO_SIZE] = overworld_info
    config = settings.config
    left_out = code_patches.left_out_patches(config.book_is_an_atlas, config.progressive_items,
                                             config.shop_items_in_pool, config.potion_shop_in_pool)
    for address, data in code_patches.code_patch_writes(world, left_out, config.progressive_items,
                                                        config.one_time_places):
        rom[address:address + len(data)] = data
    for address, data in owner_patches.owner_patch_writes(config.owner_flags, config.level_9_entrance_sword):
        rom[address:address + len(data)] = data


def encode_level_data(rom: bytearray, _world: GameWorld, settings: FinalSettings) -> None:
    """After every write to the level data, before the seed's code hashes the ROM."""
    from .level_encoding import encode_rom
    assert settings.config.level_encoding is not None
    rom[:] = encode_rom(bytes(rom), settings.config.level_encoding)


def write_slot_identity(rom: bytearray, _world: GameWorld, settings: FinalSettings) -> None:
    """Archipelago's slot identity record, before the seed's code hashes the ROM."""
    slot_identity.write_slot_identity(rom, settings.config.slot_identity)


def stamp_seed_code(rom: bytearray, _world: GameWorld, _settings: FinalSettings) -> None:
    """Last of the seed's own steps: the code hashes the finished ROM (FP-HASH-01)."""
    code_patches.stamp_seed_code(rom)


def player_settings(rom: bytearray, _world: GameWorld, settings: FinalSettings) -> None:
    """FP-SET-01: after the level encoding and the seed's code, which they never change."""
    assert settings.player_settings is not None
    rom[:] = apply_player_settings(bytes(rom), settings.player_settings)


FINAL_STEPS: tuple[FinalStep, ...] = (
    FinalStep("dungeon_nothing_code", "ZORA randomize_magical_sword", dungeon_nothing_code,
              lambda s: s.config.dungeon_nothing_code == DungeonNothingCode.ZORA_REMAP),
    FinalStep("code_patches", "B10 feature switch (B49 inside)", write_code_patches,
              lambda s: s.config.features_b10),
    FinalStep("encode_level_data", "B82", encode_level_data, lambda s: s.config.level_encoding is not None),
    FinalStep("slot_identity", "Archipelago slot name", write_slot_identity, lambda s: bool(s.config.slot_identity)),
    FinalStep("stamp_seed_code", "B10 feature switch", stamp_seed_code, lambda s: s.config.features_b10),
    FinalStep("player_settings", "player settings", player_settings, lambda s: s.player_settings is not None),
)


def run_final_steps(rom: bytearray, world: GameWorld, settings: FinalSettings) -> None:
    """Every enabled final step, in FINAL_STEPS order, on the ROM image in place."""
    for step in FINAL_STEPS:
        if step.enabled(settings):
            step.run(rom, world, settings)
