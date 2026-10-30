"""Graphics theme (Look and feel; Halloween Mode, owner, 2026-10-29; zora/rom/graphics_theme.py).

The theme's tiles go into a working copy of the player's ROM before generation, so the boss and enemy
art travels with every tile the generation copies; Ganon's palettes and the fireball are written
after. Checked here: the shipped theme file (and the converter reproducing it from the pinned Z1M1
clones); the working copy (the untouched ROM's identity and original-game reads, no reserved tile);
on and off give ROMs that differ only in pattern-tile and palette bytes, with the same seed code and
spoiler log, over the baseline and the settings that move boss and enemy art (Oops All Bosses,
Randomize Boss Groups, Shuffle Enemy Groups, Oops All Enemies), on PRG0 and PRG1; the art lands where a
graphics hack's would; a finished ROM takes no theme; and Archipelago builds the same multiworld with
the theme on and off (P3)."""
from dataclasses import replace
from functools import cache

import pytest

from zora import archipelago
from zora.flags import codec, zora_flags
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import OopsAllBosses, OopsAllEnemies, ZoraFlags
from zora.generate.pipeline import build, finish, generate_rom, plan
from zora.generate.places import read_item
from zora.rom.base_rom import BASE_ROM_PATH, PRG1_ROM_PATH, player_rom_of, remember_repo_base_rom
from zora.rom.graphics_theme import (
    BLOCK_OFFSETS,
    COMMON_BACKGROUND,
    GANON_BLUE_COLORS,
    GANON_BROWN_COLORS,
    GANON_NORMAL_COLORS,
    PALETTE_COLORS,
    RESERVED_BACKGROUND_TILES,
    TILE_BYTES,
    GraphicsTheme,
    load_theme,
    theme_offsets,
    themed_player_rom,
)
from zora.rom.parse.rom_file import parse_rom
from zora.rom.player_settings import PlayerSettingError, PlayerSettings, apply_player_settings
from zora.rom.revision import NES_HEADER_SIZE, identify_rom
from zora_export.seed_document import seed_document_for
from zora_export.spoiler_log import spoiler_log

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

H = GraphicsTheme.HALLOWEEN
HALLOWEEN = PlayerSettings(graphics_theme=H)
FLAGS = MVP_BASELINE_LEVEL_ENCODING_OFF
SEED = 3


def _toggled(flag_string: str, toggle: str) -> str:
    settings = codec.decode(flag_string)
    return codec.encode(type(settings)(dict(settings.options), {**settings.toggles, toggle: ThreeState.ON}))


# The settings that move boss and enemy art: (Z1R flags, ZORA flags)
CASES = {
    "baseline": (FLAGS, ""),
    "oops all bosses": (FLAGS, zora_flags.encode(ZoraFlags(oops_all_bosses=OopsAllBosses.DODONGOS))),
    "boss groups": (_toggled(FLAGS, "B40"), ""),
    "enemy groups": (_toggled(FLAGS, "B42"), ""),
    "oops all enemies": (FLAGS, zora_flags.encode(ZoraFlags(oops_all_enemies=OopsAllEnemies.WIZZROBES))),
}
PALETTES = {offset + color for offset in (GANON_NORMAL_COLORS, GANON_BROWN_COLORS, GANON_BLUE_COLORS)
            for color in range(PALETTE_COLORS)}


@cache
def base(revision: str = "PRG0") -> bytes:
    if revision == "PRG1":
        if not PRG1_ROM_PATH.exists():
            pytest.skip("needs the PRG1 ROM")
        remember_repo_base_rom()
        return PRG1_ROM_PATH.read_bytes()
    return remember_repo_base_rom()


def differing(first: bytes, second: bytes) -> set[int]:
    return {offset for offset, (a, b) in enumerate(zip(first, second, strict=True)) if a != b}


# --- the theme file ----------------------------------------------------------------------------------

def test_the_halloween_file_reads() -> None:
    theme = load_theme(H)
    assert theme.author == "ZeroMeaning" and "MetalMachine" in theme.provenance
    assert len(theme.tiles) == 407
    assert not any(tile.block == COMMON_BACKGROUND and tile.index in RESERVED_BACKGROUND_TILES
                   for tile in theme.tiles)
    assert theme.ganon_normal == (0x05, 0x18, 0x34) and theme.ganon_second == (0x07, 0x15, 0x30)
    assert len(theme.fireball) == 2


def test_the_converter_reproduces_the_shipped_file() -> None:
    # The converter stays in this repo (scripts/ is not released), so a release tree skips this
    converter = pytest.importorskip("scripts.z1m1_holiday_graphics", reason="scripts/ is not released")
    try:
        data = converter.convert(H)
    except converter.AssetError as missing:
        pytest.skip(f"needs the pinned Z1M1 clones: {missing}")
    assert converter.theme_file(data) == converter.DEFAULT_OUT.read_text(encoding="utf-8")


# --- the working copy --------------------------------------------------------------------------------

@pytest.mark.parametrize("revision", ["PRG0", "PRG1"])
def test_the_working_copy_keeps_the_untouched_roms_identity(revision: str) -> None:
    player, themed = player_rom_of(base(revision)), themed_player_rom(base(revision), H)
    assert themed.identity == player.identity == identify_rom(base(revision))
    assert not themed.identity.modified_graphics
    assert themed.layout == player.layout and themed.data == player.data
    changed = differing(themed.layout, themed.canvas)
    tile_places = {tile.offset + position for tile in load_theme(H).tiles for position in range(TILE_BYTES)}
    assert changed and changed <= tile_places
    reserved = {NES_HEADER_SIZE + BLOCK_OFFSETS[COMMON_BACKGROUND] + tile * TILE_BYTES + position
                for tile in RESERVED_BACKGROUND_TILES for position in range(TILE_BYTES)}
    assert not changed & reserved
    assert themed_player_rom(base(revision), GraphicsTheme.OFF) == player


# --- on and off ----------------------------------------------------------------------------------------

@cache
def generated(case: str, theme: GraphicsTheme, revision: str = "PRG0") -> bytes:
    flags, zora = CASES[case]
    return generate_rom(flags, SEED, base(revision), PlayerSettings(graphics_theme=theme), zora).rom


@pytest.mark.parametrize("case", list(CASES))
def test_on_and_off_differ_only_in_tiles_and_palettes(case: str) -> None:
    off, on = generated(case, GraphicsTheme.OFF), generated(case, H)
    changed = differing(off, on)
    assert changed and changed <= theme_offsets(H)
    theme = load_theme(H)
    for offset, colors in ((GANON_NORMAL_COLORS, theme.ganon_normal), (GANON_BROWN_COLORS, theme.ganon_second),
                           (GANON_BLUE_COLORS, theme.ganon_normal)):
        assert on[offset:offset + PALETTE_COLORS] == bytes(colors)
    flags, zora = CASES[case]
    spoilers = [spoiler_log(seed_document_for(rom, flags, SEED, zora)) for rom in (on, off)]
    assert spoilers[0] == spoilers[1]


@pytest.mark.parametrize("case", ["baseline", "oops all bosses"])
def test_on_and_off_differ_only_in_tiles_and_palettes_on_prg1(case: str) -> None:
    off, on = generated(case, GraphicsTheme.OFF, "PRG1"), generated(case, H, "PRG1")
    changed = differing(off, on)
    assert changed and changed <= theme_offsets(H)


@pytest.mark.parametrize("case", list(CASES))
def test_the_art_lands_where_a_graphics_hacks_would(case: str) -> None:
    """Generated from the working copy itself, as a player's ROM with modified graphics, the seed is the
    themed one apart from what the theme writes after generation (Ganon's palettes)."""
    flags, zora = CASES[case]
    hack = themed_player_rom(base(), H).canvas
    assert identify_rom(hack).modified_graphics
    as_hack = generate_rom(flags, SEED, hack, PlayerSettings(), zora).rom
    assert differing(as_hack, generated(case, H)) <= PALETTES


def test_the_seed_code_is_the_same() -> None:
    flags, zora = CASES["oops all bosses"]
    off = generate_rom(flags, SEED, base(), PlayerSettings(), zora)
    assert generate_rom(flags, SEED, base(), HALLOWEEN, zora).code == off.code


# --- a finished ROM takes no theme (P2) ----------------------------------------------------------------

def test_a_finished_rom_takes_no_theme() -> None:
    rom = generated("baseline", GraphicsTheme.OFF)
    with pytest.raises(PlayerSettingError, match="generated"):
        apply_player_settings(rom, HALLOWEEN)


def test_a_build_without_the_theme_refuses_it_at_finish() -> None:
    chosen = plan(FLAGS, SEED)
    with pytest.raises(PlayerSettingError, match="generated"):
        finish(build(chosen, base()), base(), None, HALLOWEEN)


# --- Archipelago (P3) ----------------------------------------------------------------------------------

@cache
def multiworld(theme: str) -> tuple[archipelago.BuildResult, bytes]:
    from tests.test_archipelago_recipe import accepted_assignment
    settings = {"graphicsTheme": theme}
    result = archipelago.build_from_strings(*CASES["oops all bosses"], SEED, base(), settings)
    plain = archipelago.build_from_strings(*CASES["oops all bosses"], SEED, base())
    assignment, received = accepted_assignment(plain, SEED)
    return result, archipelago.finish(result, assignment, received, settings, b"Link")


def test_archipelago_builds_the_same_multiworld_with_the_theme_on_and_off() -> None:
    (off, off_rom), (on, on_rom) = multiworld("off"), multiworld("halloween")
    assert on.places == off.places and on.pool == off.pool and on.triforces == off.triforces
    assert on.logic == off.logic
    changed = differing(off_rom, on_rom)
    assert changed and changed <= theme_offsets(H)
    on_world, off_world = parse_rom(on_rom), parse_rom(off_rom)
    assert ([read_item(on_world, place) for place in on.state.places]
            == [read_item(off_world, place) for place in off.state.places])
    assert archipelago.rom_identity(on_rom) == archipelago.rom_identity(off_rom)


def test_archipelago_finish_needs_the_theme_at_build() -> None:
    from tests.test_archipelago_recipe import accepted_assignment
    plain = archipelago.build_from_strings(*CASES["baseline"], SEED, base())
    assignment, received = accepted_assignment(plain, SEED)
    with pytest.raises(PlayerSettingError, match="generated"):
        archipelago.finish(plain, assignment, received, {"graphicsTheme": "halloween"}, b"Link")


def test_a_recipe_with_the_theme_rebuilds_its_rom() -> None:
    from tests.test_archipelago_recipe import accepted_assignment
    settings = {"graphicsTheme": "halloween"}
    result = archipelago.build_from_strings(*CASES["baseline"], SEED, base(), settings)
    assignment, received = accepted_assignment(result, SEED)
    rom = archipelago.finish(result, assignment, received, settings, b"Link")
    recipe = archipelago.recipe(result, assignment, received, settings, b"Link")
    assert archipelago.rom_from_recipe(recipe, base()) == rom


def test_off_is_the_default_everywhere() -> None:
    assert PlayerSettings().graphics_theme is GraphicsTheme.OFF
    assert replace(HALLOWEEN, graphics_theme=GraphicsTheme.OFF) == PlayerSettings()
