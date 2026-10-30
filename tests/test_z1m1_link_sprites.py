"""ZeroMeaning's nine Link sprites from Z1M1 (docs/z1m1/sprites.md) and their converter
(scripts/z1m1_link_sprites.py): the shipped sets are the converter's output from the pinned clones; the
tile map puts Z1M1's four second-set tiles at ZORA's title-story pairs by file offset; the colors are
sprites.md 5b's; each set's fromGame bytes are the original Link's, so on PRG0 and PRG1 the set draws
exactly the art ZeroMeaning drew. The emulator side is tests/test_z1m1_link_sprites_emulator.py."""
import pytest

from tests.needs import needs_base_rom
from tests.test_revision import prg1
from zora.rom.base_rom import PRG1_ROM_PATH, remember_repo_base_rom
from zora.rom.link_art import sprite_set_tiles
from zora.rom.link_sprite import LINK_HALVES, built_in_sprite_sets, link_tiles, sprite_set_file

# The converter stays in this repo (scripts/ is not released), so a release tree skips its checks
z1m1 = pytest.importorskip("scripts.z1m1_link_sprites", reason="scripts/z1m1_link_sprites.py is not released")
pytestmark = needs_base_rom
needs_clones = pytest.mark.skipif(not (z1m1.ASSETS_CLONE.is_dir() and z1m1.LAUNCHER_CLONE.is_dir()),
                                  reason="needs the Z1M1 clones (../z1m1/assets, ../z1m1/launcher)")
SET_IDS = ("zeromeaning-ganon", "zeromeaning-justin-bailey", "zeromeaning-kraid", "zeromeaning-link-bunny",
           "zeromeaning-link-female", "zeromeaning-link-invisible", "zeromeaning-mother-brain", "zeromeaning-samus",
           "zeromeaning-zelda")
# sprites.md 5b: the normal row, then the blue and red rings' color 1, in hex; and whether color 1 is art
COLORS = {
    "zeromeaning-ganon": ((0x2C, 0x30, 0x16), 0x2B, 0x27, True),
    "zeromeaning-justin-bailey": ((0x15, 0x36, 0x1A), 0x13, 0x16, False),
    "zeromeaning-kraid": ((0x1B, 0x39, 0x06), 0x1C, 0x17, True),
    "zeromeaning-link-bunny": ((0x25, 0x34, 0x1A), 0x25, 0x25, True),
    "zeromeaning-link-female": ((0x19, 0x27, 0x18), 0x11, 0x16, False),
    "zeromeaning-link-invisible": ((0x18, 0x27, 0x09), 0x18, 0x18, True),
    "zeromeaning-mother-brain": ((0x16, 0x30, 0x0C), 0x1A, 0x14, True),
    "zeromeaning-samus": ((0x1A, 0x27, 0x06), 0x1C, 0x16, True),
    "zeromeaning-zelda": ((0x04, 0x36, 0x17), 0x01, 0x06, False),
}


@needs_clones
def test_the_shipped_sets_are_the_converters_output() -> None:
    converted = z1m1.convert_all()
    assert [entry.set_id for entry in converted] == list(SET_IDS)
    sets = built_in_sprite_sets()
    for entry in converted:
        assert sprite_set_file(sets[entry.set_id]) == sprite_set_file(entry.sprite_set), entry.set_id


@needs_clones
def test_the_second_set_tiles_are_the_title_story_pairs_by_offset() -> None:
    """sprites.md open question 1: Z1M1's #38-39 (set 0, "holding up an item", 0x4E44) and #22-23 (set 0,
    "big shield, east, frame 1", 0x4EC4) are ZORA's halves $78 and $80, DemoSpritePatterns +$80 and
    +$100, the only tiles of the 40 outside the common sprite patterns."""
    places = z1m1.tile_map_places(z1m1.pinned(z1m1.LAUNCHER_CLONE, z1m1.LAUNCHER_COMMIT, z1m1.TILE_MAP))
    offsets = {place: offset for offset, place in z1m1.set_places().items()}
    outside = {index: (places[index], offsets[places[index]]) for index in range(len(places))
               if offsets[places[index]] < 0x8000}
    assert outside == {38: (28, 0x4E44), 39: (29, 0x4E54), 22: (30, 0x4EC4), 23: (31, 0x4ED4)}
    assert (LINK_HALVES[28 // 2], LINK_HALVES[30 // 2]) == ("$78", "$80")


@needs_clones
def test_the_converter_packs_prg0s_link_back() -> None:
    """PRG0's Link unpacked to Z1M1's digits in its tile map's order, converted back: the same bytes."""
    original = link_tiles(remember_repo_base_rom())
    places = z1m1.tile_map_places(z1m1.pinned(z1m1.LAUNCHER_CLONE, z1m1.LAUNCHER_COMMIT, z1m1.TILE_MAP))

    def digits(tile: bytes) -> str:
        return "".join(str((tile[y] >> (7 - x) & 1) | (tile[y + 8] >> (7 - x) & 1) << 1)
                       for y in range(8) for x in range(8))
    in_z1m1_order = [digits(original[16 * place:16 * place + 16]) for place in places]
    assert b"".join(z1m1.packed(in_z1m1_order[places.index(place)]) for place in range(len(places))) == original


def test_the_sets_colors_are_the_spec_s() -> None:
    sets = built_in_sprite_sets()
    for set_id, (normal, blue, red, art) in COLORS.items():
        recommended = sets[set_id].recommended
        assert recommended is not None
        assert (recommended.tunics, recommended.other, recommended.color_one_is_art) == (
            (normal[0], blue, red), normal[1:], art), set_id
        assert sets[set_id].author == "ZeroMeaning" and "ZeroMeaning" in sets[set_id].provenance


@needs_clones
@pytest.mark.parametrize("on_prg1", [pytest.param(False, id="PRG0"), pytest.param(True, id="PRG1", marks=(
    pytest.mark.skipif(not PRG1_ROM_PATH.exists(), reason="no PRG1 ROM beside the base")))])
def test_the_sets_draw_zeromeanings_art_from_the_players_rom(on_prg1: bool) -> None:
    """The fromGame bytes, blank in the file, come from the player's ROM: the drawn tiles are the art
    as drawn, on PRG0 and PRG1 (which hold Link at the same offsets)."""
    base = prg1() if on_prg1 else remember_repo_base_rom()
    sets = built_in_sprite_sets()
    for entry in z1m1.convert_all():
        drawn = sprite_set_tiles(sets[entry.set_id], lambda offset, length: base[offset:offset + length])
        assert drawn == entry.art, entry.set_id


def test_the_blanks_are_where_the_art_keeps_links_bytes() -> None:
    """Six of the nine keep runs of the original Link (mostly the shield, halves $5A and $60); the
    other three keep none."""
    kept = {set_id: sum(end - start for start, end in built_in_sprite_sets()[set_id].from_game) for set_id in SET_IDS}
    assert kept == {"zeromeaning-ganon": 26, "zeromeaning-justin-bailey": 34, "zeromeaning-kraid": 30,
                    "zeromeaning-link-bunny": 0, "zeromeaning-link-female": 38, "zeromeaning-link-invisible": 0,
                    "zeromeaning-mother-brain": 0, "zeromeaning-samus": 8, "zeromeaning-zelda": 0}
