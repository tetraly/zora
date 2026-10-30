"""Playable character's colors (player_settings.CharacterColors, shown_link_colors): a sprite set's own
colors, the default, or the player's. Under The set's own a set's colors 2 and 3 apply, and its three
tunic colors too when its color 1 is art (recommendedColors' colorOne); under My own, with Link, or
with a set that has no colors, the player's do. The map marker follows the colors applied."""
from dataclasses import replace

import pytest

from tests.needs import needs_base_rom
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.link_art import LinkSpriteSet, built_in_art_sets
from zora.rom.link_sprite import LINK_FIXED_COLORS, SpriteSet, built_in_sprite_sets
from zora.rom.player_settings import (
    MARKER_DOT_LOW_PLANE,
    TUNIC_FILE_SELECT_COPY,
    TUNIC_PICKUP_COPY,
    CharacterColors,
    LinkSprite,
    PlayerSettings,
    apply_player_settings,
    link_palette_color_offsets,
    resolved_player_settings,
    shown_link_colors,
)

GREEN, BLUE, RED = (0x29, 0x32, 0x16)
MINE_TUNICS, MINE_OTHER = (0x21, 0x22, 0x23), (0x36, 0x0F)
CLOTHING = built_in_sprite_sets()["zeromeaning-link-female"]       # colors (0x19, 0x11, 0x16), (0x27, 0x18)
ART = built_in_sprite_sets()["zeromeaning-samus"]                  # colors (0x1A, 0x1C, 0x16), (0x27, 0x06)


def chosen(sprite_set: LinkSpriteSet | None, colors: CharacterColors = CharacterColors.SET,
           **changes: object) -> PlayerSettings:
    return PlayerSettings(link_sprite=LinkSprite.LINK if sprite_set is None else LinkSprite.SET,
                          sprite_set=sprite_set, character_colors=colors, **changes)  # type: ignore[arg-type]


def test_a_clothing_set_gives_its_other_colors_and_keeps_the_tunics() -> None:
    assert shown_link_colors(chosen(CLOTHING)) == ((GREEN, BLUE, RED), (0x27, 0x18))
    assert shown_link_colors(chosen(CLOTHING, tunic_colors=MINE_TUNICS)) == (MINE_TUNICS, (0x27, 0x18))


def test_an_art_set_gives_all_five_colors() -> None:
    assert shown_link_colors(chosen(ART, tunic_colors=MINE_TUNICS)) == ((0x1A, 0x1C, 0x16), (0x27, 0x06))


@pytest.mark.parametrize("sprite_set", [CLOTHING, ART], ids=["clothing", "art"])
def test_my_own_gives_the_players_colors(sprite_set: SpriteSet) -> None:
    settings = chosen(sprite_set, CharacterColors.MINE, tunic_colors=MINE_TUNICS, link_colors=MINE_OTHER)
    assert shown_link_colors(settings) == (MINE_TUNICS, MINE_OTHER)


def test_link_and_a_set_without_colors_give_the_players_colors() -> None:
    plain = replace(ART, recommended=None)
    for settings in (chosen(None, tunic_colors=MINE_TUNICS), chosen(plain, link_colors=MINE_OTHER)):
        assert shown_link_colors(settings) == (settings.tunic_colors, settings.link_colors)
    # a set sent with the Link choice draws nothing, so its colors do not apply either
    assert shown_link_colors(replace(chosen(ART), link_sprite=LinkSprite.LINK)) == ((GREEN, BLUE, RED),
                                                                                     LINK_FIXED_COLORS)


def test_random_gives_the_drawn_sets_colors() -> None:
    """Random's set brings its own colors under The set's own, the default; the original Link the player's."""
    seen = set()
    for seed in range(1, 301):
        resolved = resolved_player_settings(PlayerSettings(link_sprite=LinkSprite.RANDOM), seed)
        recommended = resolved.sprite_set.recommended if resolved.sprite_set is not None else None
        expected_other = recommended.other if recommended is not None else LINK_FIXED_COLORS
        assert shown_link_colors(resolved)[1] == expected_other
        seen.add(recommended is not None and recommended.color_one_is_art)
    assert seen == {True, False}


@pytest.fixture(scope="module")
def finished() -> bytes:
    return generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, remember_repo_base_rom()).rom


@needs_base_rom
def test_the_rom_gets_the_colors_shown(finished: bytes) -> None:
    rom = apply_player_settings(finished, chosen(ART, tunic_colors=MINE_TUNICS))
    for copy in (TUNIC_FILE_SELECT_COPY, TUNIC_PICKUP_COPY):
        assert rom[copy:copy + 3] == bytes((0x1A, 0x1C, 0x16))
    # Samus's color 2 is the game's ($27): written nowhere, so level 3 keeps its lighter skin
    assert {rom[offset] for offset in link_palette_color_offsets(2)} == {0x27, 0x37}
    assert {rom[offset] for offset in link_palette_color_offsets(3)} == {0x06}
    mine = apply_player_settings(finished, chosen(ART, CharacterColors.MINE))
    assert mine[TUNIC_PICKUP_COPY:TUNIC_PICKUP_COPY + 3] == bytes((GREEN, BLUE, RED))
    assert mine == apply_player_settings(finished, chosen(replace(ART, recommended=None)))


@needs_base_rom
def test_the_map_marker_follows_the_colors_applied(finished: bytes) -> None:
    """Moblin's own tunic colors ($16, $0C, $06) include a dark one, so the marker is drawn in Link's
    skin color; under My own, with the game's tunics, it is not."""
    moblin = built_in_art_sets()["moblin"]
    marker = slice(MARKER_DOT_LOW_PLANE, MARKER_DOT_LOW_PLANE + 1)
    own = apply_player_settings(finished, chosen(moblin))
    mine = apply_player_settings(finished, chosen(moblin, CharacterColors.MINE))
    assert own[marker] != mine[marker] == finished[marker]
