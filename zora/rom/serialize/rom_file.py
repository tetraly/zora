"""The ROM-file entry point: a GameWorld written over its base ROM."""

from zora.model.game_world import GameWorld
from zora.rom.base_rom import remember_base_rom
from zora.rom.code_patches import overworld_start_y
from zora.rom.final_steps import FinalSettings, run_final_steps
from zora.rom.game_config import GameConfig
from zora.rom.parse.rom_file import original_bins_from_rom
from zora.rom.player_settings import PlayerSettings


def serialize_to_rom(
    game_world: GameWorld,
    rom: bytes,
    config: GameConfig | None = None,
    player_settings: PlayerSettings | None = None,
) -> bytes:
    """Write a GameWorld onto a ROM image, then run the final ROM steps
    (zora/rom/final_steps.py: the code patches, the level encoding, the
    seed's code and, when given, the player settings); returns the new bytes.

    Vanilla hint mode: the quotes block passes through byte-identically when
    GameWorld.quotes_raw was captured at parse time.
    """
    from zora.rom.serialize.game_world import serialize_game_world
    remember_base_rom(rom)              # PRG0: the source of the patches' original bytes
    cfg = config or GameConfig()
    # FP-ENTR-01: a ROM that already carries ZORA's code patches (a finished
    # ROM parsed again) keeps the start Y in the patch's own byte, where
    # parse_rom read it, even when this call writes no patches.
    start_y_in_patch = cfg.features_b10 or overworld_start_y(rom) is not None
    patch = serialize_game_world(game_world, original_bins_from_rom(rom),
                                hint_mode=cfg.hint_mode, config=config, start_y_in_patch=start_y_in_patch)
    out = bytearray(rom)
    patch.apply(out)
    run_final_steps(out, game_world, FinalSettings(cfg, player_settings))
    return bytes(out)
