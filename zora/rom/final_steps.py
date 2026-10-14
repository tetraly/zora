"""The flag-dependent ROM work, as named final steps after the model is written.

serialize_game_world writes the GameWorld model (the game's data, the engine's
"no item" byte, the level information and the start table the code patches read
included); these steps then change the ROM image in FINAL_STEPS order, each
switched by its own setting:

  code_patches           ZORA's 6502 patches, with the per-seed bytes inside them
                         (B10's feature switch; Book is an Atlas, B49, inside it)
  encode_level_data      Encode level data (B82; zora/rom/level_encoding.py)
  slot_identity          Archipelago's slot name (External mode only; zora/rom/slot_identity.py)
  stamp_seed_code        the seed's code (FP-HASH-01), from the world and its configuration
  player_settings        the player's settings (FP-SET-01), never part of the seed

The order matters: the level encoding comes after every write to the level
data, and the player settings come after the code, which they never change.
The code covers the configuration (the level encoding's key and the slot name
too: each player's code differs), never the ROM.
"""
from collections.abc import Callable
from dataclasses import dataclass

from ..model.game_world import GameWorld
from . import code_patches, owner_patches, slot_identity
from .game_config import GameConfig
from .player_settings import PlayerSettings, write_player_settings


@dataclass(frozen=True)
class FinalSettings:
    """What the final steps read: the serialization settings and, for a
    finished ROM a player downloads, the player settings (None leaves them
    unwritten)."""
    config: GameConfig
    player_settings: PlayerSettings | None = None
    # Written over a release (a new seed): the seed's code is computed from the world. A finished
    # ROM written again (a round trip) keeps the code it shows.
    new_seed: bool = True


@dataclass(frozen=True)
class FinalStep:
    """One final ROM step: its name, the setting that switches it, the work
    (on the ROM image, in place) and the predicate that switches it on."""
    name: str
    setting: str
    run: Callable[[bytearray, GameWorld, FinalSettings], None]
    enabled: Callable[[FinalSettings], bool]


def write_code_patches(rom: bytearray, world: GameWorld, settings: FinalSettings) -> None:
    """B10's CODE patches (features-behavior.md; docs/rom-map.md); the level-information bytes
    and the start table they read are the model's, which the serializer writes. Book is an Atlas
    (B49) off leaves its patch out (FL-OFF-05); the progressive patches are written only with
    their ZORA flags on (PI-CODE-01), fp-start-02 only with start items (FP-START-03)."""
    config = settings.config
    left_out = code_patches.left_out_patches(config.book_is_an_atlas, config.progressive_items,
                                             config.shop_items_in_pool, config.potion_shop_in_pool,
                                             start_items=bool(world.start_items),
                                             start_rooms_moved=any(level.arrival_code in code_patches.SIDE_ARRIVAL_CODES
                                                                   for level in world.levels),
                                             book_to_understand_npcs=config.book_to_understand_npcs)
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


def stamp_seed_code(rom: bytearray, world: GameWorld, settings: FinalSettings) -> None:
    """Last of the seed's own steps: the code, from the generated world and its configuration
    (FP-HASH-01; code_patches.seed_code_items), never from the ROM."""
    code_patches.stamp_seed_code(rom, world, settings.config)


def player_settings(rom: bytearray, _world: GameWorld, settings: FinalSettings) -> None:
    """FP-SET-01: after the level encoding and the seed's code, which they never change."""
    assert settings.player_settings is not None
    rom[:] = write_player_settings(bytes(rom), settings.player_settings)


FINAL_STEPS: tuple[FinalStep, ...] = (
    FinalStep("code_patches", "B10 feature switch (B49 inside)", write_code_patches,
              lambda s: s.config.features_b10),
    FinalStep("encode_level_data", "B82", encode_level_data, lambda s: s.config.level_encoding is not None),
    FinalStep("slot_identity", "Archipelago slot name", write_slot_identity, lambda s: bool(s.config.slot_identity)),
    FinalStep("stamp_seed_code", "B10 feature switch", stamp_seed_code,
              lambda s: s.config.features_b10 and s.new_seed),
    FinalStep("player_settings", "player settings", player_settings, lambda s: s.player_settings is not None),
)


def run_final_steps(rom: bytearray, world: GameWorld, settings: FinalSettings) -> None:
    """Every enabled final step, in FINAL_STEPS order, on the ROM image in place."""
    for step in FINAL_STEPS:
        if step.enabled(settings):
            step.run(rom, world, settings)
