"""The ROM-file entry point: a GameWorld written over its base ROM."""

from dataclasses import replace

from ...model.game_world import GameWorld
from ..base_rom import PlayerRom, recognized_player_rom, using_player_rom
from ..code_patches import SEED_CODE_ADDRESS, SEED_CODE_LENGTH, overworld_start_y
from ..final_steps import FinalSettings, run_final_steps
from ..game_config import GameConfig
from ..graphics_theme import GraphicsTheme
from ..parse.rom_file import original_bins_from_rom
from ..player_settings import PlayerSettingError, PlayerSettings
from ..revision import Revision, back_to_revision, layout_of, moved_to_prg0_layout


def serialize_to_rom(
    game_world: GameWorld,
    rom: bytes | PlayerRom,
    config: GameConfig | None = None,
    player_settings: PlayerSettings | None = None,
) -> bytes:
    """Write a GameWorld onto a ROM image, then run the final ROM steps
    (zora/rom/final_steps.py: the code patches, the level encoding, the
    seed's code and, when given, the player settings); returns the new bytes.

    Vanilla hint mode: the quotes block passes through byte-identically when
    GameWorld.quotes_raw was captured at parse time.

    A release (revision.identify_rom) is written in PRG0's layout and the result moved back to
    its own (PlayerRom.finished); the config then records its revision and whether its
    graphics are modified. Any other ROM (a finished ROM written again) is written in PRG0's
    layout too, moved back when it was made from PRG1 (revision.layout_of), and keeps the seed's
    code it shows (the code comes from the generated world, which a parsed ROM only reflects).
    A graphics theme comes with the PlayerRom (graphics_theme.themed_player_rom), whose canvas is
    written over; settings naming another theme are refused (check_graphics_theme).
    """
    player = rom if isinstance(rom, PlayerRom) else recognized_player_rom(rom)
    check_graphics_theme(player, player_settings)
    if player is None:
        assert not isinstance(rom, PlayerRom)
        if layout_of(rom) is Revision.PRG1:          # a finished PRG1 ROM written again
            image = moved_to_prg0_layout(rom)
            return back_to_revision(rom, Revision.PRG1, image,
                                    _serialize(game_world, image, config or GameConfig(), player_settings, False))
        return _serialize(game_world, rom, config or GameConfig(), player_settings, False)
    with using_player_rom(player):
        cfg = replace(config or GameConfig(), revision=player.revision,
                      modified_graphics=player.identity.modified_graphics)
        return player.finished(_serialize(game_world, player.canvas, cfg, player_settings, True))


def check_graphics_theme(player: PlayerRom | None, player_settings: PlayerSettings | None) -> None:
    """A graphics theme's tiles go in before generation (graphics_theme.themed_player_rom), so the
    settings may name a theme only when the ROM was generated from that theme's working copy: never
    a finished ROM written again, never a build made without it."""
    if player_settings is None or player_settings.graphics_theme is GraphicsTheme.OFF:
        return
    if player is None or player.theme != player_settings.graphics_theme.value:
        raise PlayerSettingError(f"Graphics theme {player_settings.graphics_theme.value}: it applies only when "
                                 "the ROM is generated with it, not to a finished ROM or another build")


def _serialize(game_world: GameWorld, rom: bytes, cfg: GameConfig, player_settings: PlayerSettings | None,
               new_seed: bool) -> bytes:
    """serialize_to_rom on an image in PRG0's layout; `new_seed` when it is a release's (the
    seed's code is computed, final_steps.FinalSettings)."""
    from .game_world import serialize_game_world
    # FP-ENTR-01: a ROM that already carries ZORA's code patches (a finished
    # ROM parsed again) keeps the start Y in the patch's own byte, where
    # parse_rom read it, even when this call writes no patches.
    start_y_in_patch = cfg.features_b10 or overworld_start_y(rom) is not None
    patch = serialize_game_world(game_world, original_bins_from_rom(rom),
                                hint_mode=cfg.hint_mode, config=cfg, start_y_in_patch=start_y_in_patch)
    out = bytearray(rom)
    patch.apply(out)
    shown_code = rom[SEED_CODE_ADDRESS:SEED_CODE_ADDRESS + SEED_CODE_LENGTH]
    run_final_steps(out, game_world, FinalSettings(cfg, player_settings, new_seed))
    if not new_seed and cfg.features_b10:
        out[SEED_CODE_ADDRESS:SEED_CODE_ADDRESS + SEED_CODE_LENGTH] = shown_code   # the code patches rewrote it
    return bytes(out)
