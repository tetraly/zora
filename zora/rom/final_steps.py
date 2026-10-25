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
  stamp_seed_number      the seed number the statistics screen shows (ZORA mode)
  player_settings        the player's settings (FP-SET-01), never part of the seed

The order matters: the level encoding comes after every write to the level
data, and the player settings come after the code, which they never change.
The code covers the configuration (the level encoding's key and the slot name
too: each player's code differs), never the ROM.
"""
from collections.abc import Callable
from dataclasses import dataclass

from ..generate.rng import Rng
from ..model.game_world import GameWorld
from . import (
    archipelago_logo,
    bait_count,
    code_patches,
    credits_staff,
    fairy_refill,
    hidden_tiles,
    item_sprites,
    opening_story,
    overworld_crossings,
    owner_patches,
    slot_identity,
    small_settings,
    sword_and_harm,
    sword_states,
    uphill_battle,
)
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
    their ZORA flags on (PI-CODE-01), fp-start-02 only with start items (FP-START-03); with
    Shop Items in the Item Pool on, bait is a count (bait_count); Permanent Sword Beam (B52) and OHKO
    (B53) write their fixed patches (sword_and_harm), Add Bridges to the River (B87) and Add Lost
    Woods Shortcut (B88) their overworld bytes (overworld_crossings), and so do the wooden-sword states (C07,
    sword_states); and in every ROM a bought fairy refills every heart (fairy_refill), the opening
    story is ZORA's, naming level 9's requirement (opening_story), and the ending credits hold the
    Randomizer Staff box (fp-credits-01's tables, credits_staff)."""
    config = settings.config
    left_out = code_patches.left_out_patches(config.book_is_an_atlas, config.progressive_items,
                                             config.shop_items_in_pool, config.potion_shop_in_pool,
                                             start_items=world.uses_start_table,
                                             start_rooms_moved=any(level.arrival_code in code_patches.SIDE_ARRIVAL_CODES
                                                                   for level in world.levels),
                                             book_to_understand_npcs=config.book_to_understand_npcs)
    for address, data in code_patches.code_patch_writes(world, left_out, config.progressive_items,
                                                        config.one_time_places, config.bait_in_pool):
        rom[address:address + len(data)] = data
    for address, data in credits_staff.credits_writes(world.credits_pointers):
        rom[address:address + len(data)] = data
    for address, data in fairy_refill.fairy_refill_writes():
        rom[address:address + len(data)] = data
    for address, data in owner_patches.owner_patch_writes(config.owner_flags, config.level_9_entrance_sword,
                                                          config.archipelago_rom):
        rom[address:address + len(data)] = data
    for address, data in opening_story.story_writes(rom, world.level_9_gate, config.level_9_entrance_sword):
        rom[address:address + len(data)] = data
    if config.foreign_logo:
        for address, data in archipelago_logo.logo_writes():
            rom[address:address + len(data)] = data
    if config.bait_in_pool:
        for address, data in bait_count.bait_count_writes():
            rom[address:address + len(data)] = data
    if config.permanent_sword_beam:
        for address, data in sword_and_harm.permanent_sword_beam_writes():
            rom[address:address + len(data)] = data
    if config.one_hit_knock_out:
        for address, data in sword_and_harm.one_hit_knock_out_writes():
            rom[address:address + len(data)] = data
    if config.river_bridges:
        for address, data in overworld_crossings.river_bridge_writes():
            rom[address:address + len(data)] = data
    if config.lost_woods_shortcut:
        for address, data in overworld_crossings.lost_woods_shortcut_writes():
            rom[address:address + len(data)] = data
    if config.bomb_upgrade_item:
        # after fp-book-01, whose routine it extends (sword_states)
        for address, data in sword_states.bomb_upgrade_writes(config.book_is_an_atlas):
            rom[address:address + len(data)] = data
    if config.wand_fights_ganon:
        for address, data in sword_states.wand_ganon_writes():
            rom[address:address + len(data)] = data
    for address, data in uphill_battle_writes(config, rom):
        rom[address:address + len(data)] = data
    for address, data in small_settings_writes(config):
        # after the beta 8 patches: B80 goes over C19 = 2's routine
        rom[address:address + len(data)] = data
    if config.change_hidden_tiles:
        # after the crossings' bytes (B87, B88), which it leaves as written (FP-VIS-01)
        for address, data in hidden_tiles.hidden_tiles_writes(rom, config.plain_dead_secrets):
            rom[address:address + len(data)] = data
    if config.item_appearance:
        # last of the code patches: the pictures as everything before leaves them (FP-SPRITE-01)
        assert config.item_sprites_key is not None
        for address, data in item_sprites.item_sprite_writes(rom, config.item_appearance,
                                                             Rng(config.item_sprites_key),
                                                             logo=config.foreign_logo):
            rom[address:address + len(data)] = data


def uphill_battle_writes(config: GameConfig, rom: bytes | bytearray) -> list[tuple[int, bytes]]:
    """The beta 8 export's fixed patches (zora/rom/uphill_battle.py) with their fields on, on the
    image `rom` the code patches leave; Hidden Health's come after the player settings
    (write_hidden_health)."""
    writes: list[tuple[int, bytes]] = []
    if config.recorder_to_unbeaten:
        writes += uphill_battle.recorder_to_unbeaten_writes()
    if config.hide_dungeon_numbers:
        writes += uphill_battle.hide_dungeon_numbers_writes()
    if config.red_bubble_curse:
        writes += uphill_battle.red_bubble_writes(config.red_bubble_curse, rom)
    if config.book_explosion:
        writes += uphill_battle.book_explosion_writes()
    if config.enemy_drops_key is not None:
        writes += uphill_battle.enemy_drop_writes(Rng(config.enemy_drops_key), config.important_item_drops,
                                                  config.random_drop_rates, swordless=config.wand_fights_ganon)
    return writes


PEGASUS_BOOTS = "pegasus_boots"       # its ZORA flag's name in GameConfig.owner_flags


def small_settings_writes(config: GameConfig) -> list[tuple[int, bytes]]:
    """The beta 9 export's fixed patches (zora/rom/small_settings.py) with their fields on."""
    writes: list[tuple[int, bytes]] = []
    if config.killable_drop_items:
        writes += small_settings.killable_drop_items_writes()
    if config.hidden_numbers:
        writes += small_settings.hidden_numbers_writes()
    if config.rupees_affect_speed:
        writes += small_settings.rupee_speed_writes(slow_speed=config.red_bubble_curse == uphill_battle.SLOW_SPEED,
                                                    pegasus_boots=PEGASUS_BOOTS in config.owner_flags)
    if config.prevent_clipping:
        writes += small_settings.prevent_clipping_writes()
    return writes


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
    if settings.config.item_appearance:
        # FP-SPRITE-01: no icons; the heading shows the code as four characters
        for address, data in item_sprites.file_select_code_writes(code_patches.seed_code_items(world, settings.config)):
            rom[address:address + len(data)] = data


def stamp_seed_number(rom: bytearray, _world: GameWorld, settings: FinalSettings) -> None:
    """The statistics screen's seed number (code_patches.stamp_seed_number), a new ZORA seed's."""
    assert settings.config.seed_number is not None
    code_patches.stamp_seed_number(rom, settings.config.seed_number)


def player_settings(rom: bytearray, _world: GameWorld, settings: FinalSettings) -> None:
    """FP-SET-01: after the level encoding and the seed's code, which they never change."""
    assert settings.player_settings is not None
    rom[:] = write_player_settings(bytes(rom), settings.player_settings)


def write_hidden_health(rom: bytearray, _world: GameWorld, _settings: FinalSettings) -> None:
    """FP-HIDE-01 (B55): after the player settings' heart colour and beep, which it overrides."""
    for address, data in uphill_battle.hidden_health_writes():
        rom[address:address + len(data)] = data


FINAL_STEPS: tuple[FinalStep, ...] = (
    FinalStep("code_patches", "B10 feature switch (B49 inside)", write_code_patches,
              lambda s: s.config.features_b10),
    FinalStep("encode_level_data", "B82", encode_level_data, lambda s: s.config.level_encoding is not None),
    FinalStep("slot_identity", "Archipelago slot name", write_slot_identity, lambda s: bool(s.config.slot_identity)),
    FinalStep("stamp_seed_code", "B10 feature switch", stamp_seed_code,
              lambda s: s.config.features_b10 and s.new_seed),
    FinalStep("stamp_seed_number", "B10 feature switch", stamp_seed_number,
              lambda s: s.config.features_b10 and s.new_seed and s.config.seed_number is not None),
    FinalStep("player_settings", "player settings", player_settings, lambda s: s.player_settings is not None),
    FinalStep("hidden_health", "B55", write_hidden_health, lambda s: s.config.hidden_health),
)


def run_final_steps(rom: bytearray, world: GameWorld, settings: FinalSettings) -> None:
    """Every enabled final step, in FINAL_STEPS order, on the ROM image in place."""
    for step in FINAL_STEPS:
        if step.enabled(settings):
            step.run(rom, world, settings)
