"""The Archipelago logo, which another player's item shows in an Archipelago game's ROM, colored by
the item's class as the swords are: red for progression, blue for useful, Link's color for filler
(docs/design/archipelago-items.md piece 5). FINISH writes such an item as code $34, $35 or $36
(finish.FOREIGN_ITEMS), which asm/flags2/ap-items' FarDraw draws as these tiles and FarTake gives
nothing for. The final steps write the tiles into every Archipelago game's ROM
(GameConfig.archipelago_rom), in PRG0's layout (none of these bytes moves in PRG1).

The logo is a full 16x16 picture, two different 8x16 halves side by side (owner decision 2026-11-13;
up to 2.0.1 it was one 8x16 sprite on the shield's tile $56, the left half of a picture binarybrain11's
world drew mirrored, so half the logo showed). In 8x16 sprite mode an odd tile draws the background
pattern table's pair (tile - 1, tile): the left half is CommonBackgroundPatterns tiles $5C/$5D (tile
$5D) and the right half tiles $5E/$5F (tile $5F). Those tiles are blank in PRG0 and PRG1, loaded in
every mode, and kept for tiles that must be (owner decision 2026-11-14; before then the logo was at
$4C-$4F, which an Archipelago game's boss deal then left out of its common block): themes keep off them
(graphics_theme.RESERVED_BACKGROUND_TILES), Change Hidden OW Tiles shares $30-$3F with the bosses
(hidden_tiles step 4) and the Item Counter takes $52/$53. Up to piece 5 the logo was drawn in the
magical shield's slot, with the look setting "Other players' items look like" (retired).

The art is binarybrain11's (Zachary Gorman), from their Archipelago fork's Legend of Zelda world
(binarybrain11/Archipelago commit c478ba8, worlds/tloz/Rom.py `archipelago_sprite`; Archipelago is
MIT-licensed; docs/credits.md): their half as the left half and its mirror as the right, with white and
light blue traded in the right half, so the six circles go dark blue at 12 and 6 o'clock, light blue at
2 and 8 and white at 4 and 10 (owner design, 2026-11-13)."""

PATTERN_SIZE = 16
# CommonBackgroundPatterns (bank 2, headered file 0x0878F, the background pattern table's tiles
# $00-$6F): tiles $5C-$5F, each its low plane then its high plane.
COMMON_BACKGROUND_PATTERNS = 0x0878F
LOGO_BACKGROUND_TILES = range(0x5C, 0x60)
LOGO_TILES_AT = COMMON_BACKGROUND_PATTERNS + LOGO_BACKGROUND_TILES.start * PATTERN_SIZE
LOGO_TILES = bytes.fromhex(
    "03073f7fffffc6000000387cfefefe7c"      # $5C, left top (binarybrain11's)
    "0003070f0f0f0703fefcf87030000000"      # $5D, left bottom (binarybrain11's)
    "c0e0e0c080801c3e00001c3e7f7f7f3e"      # $5E, right top: the mirror, white and light blue traded
    "7ffffffefcf0e0c07f3f1f0e0c000000")     # $5F, right bottom
# The 8x16 sprites' tile bytes, as ap-items' DrawLogo writes them (AP_ITEMS_LOGO_LEFT / _RIGHT)
LOGO_FRAME_TILE = 0x5D
LOGO_RIGHT_TILE = LOGO_FRAME_TILE + 2
LOGO_SPRITE_TILES = (LOGO_FRAME_TILE, LOGO_RIGHT_TILE)


def logo_writes() -> list[tuple[int, bytes]]:
    """The logo's four background tiles, as (headered file offset, bytes)."""
    return [(LOGO_TILES_AT, LOGO_TILES)]
