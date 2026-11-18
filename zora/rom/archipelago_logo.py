"""How another player's item looks in an Archipelago game's ROM with Other players' items look like
= The Archipelago logo (foreign_item_look = logo; owner decision 2026-10-18; the spec "ZORA
Archipelago beta 5 fixes", item 4). FINISH writes another player's item as the magical shield ($1C)
and turns every shop's real magical shield into a fairy (zora/generate/finish.py); these writes make
$1C look like the logo and do nothing when picked up. Written by the final steps when
GameConfig.foreign_logo is on, in PRG0's layout (none of these bytes moves in PRG1).

The logo is a full 16x16 picture, two different 8x16 halves side by side (owner decision 2026-11-13;
up to 2.0.1 it was one 8x16 sprite on the shield's tile $56, the left half of a picture binarybrain11's
world drew mirrored, so half the logo showed). The shield's frame tile becomes $5D, odd, so the game
draws it from the background pattern table: the left half is CommonBackgroundPatterns tiles $5C/$5D
and the right half, two tiles on ($5D + 2 = $5F), tiles $5E/$5F. Those tiles are blank in PRG0 and
PRG1, loaded in every mode, and kept for tiles that must be (owner decision 2026-11-14; before then the
logo was at $4C-$4F, which an Archipelago game's boss deal then left out of its common block): themes
keep off them (graphics_theme.RESERVED_BACKGROUND_TILES), Change Hidden OW Tiles shares $30-$3F with the
bosses (hidden_tiles step 4) and the Item Counter takes $52/$53. The shield's own sprite tiles keep
PRG0's picture.

Anim_WriteSpecificItemSprites (bank 1, run from RAM) draws a frame tile from $20 to $61 as one narrow
sprite. Its test "below $20: wide" is dead in ZORA (no frame tile is below $20; Pegasus Boots moves
the bound to $1C so the boot is narrow, which the new test keeps), so it becomes "the logo's tile:
draw the pair as it is", a branch to the JMP Anim_WriteSpritePair the mirrored pair ends with: two
sides, 8 pixels apart, unflipped, both in the slot's palette.

The art is binarybrain11's (Zachary Gorman), from their Archipelago fork's Legend of Zelda world
(binarybrain11/Archipelago commit c478ba8, worlds/tloz/Rom.py `archipelago_sprite`; Archipelago is
MIT-licensed; docs/credits.md): their half as the left half and its mirror as the right, with white and
light blue traded in the right half, so the six circles go dark blue at 12 and 6 o'clock, light blue at
2 and 8 and white at 4 and 10 (owner design, 2026-11-13)."""
from .inventory import ITEM_ID_TO_DESCRIPTOR

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
# The 8x16 sprites' tile bytes: an odd tile is the background table's pair (tile - 1, tile).
LOGO_FRAME_TILE = 0x5D
LOGO_RIGHT_TILE = LOGO_FRAME_TILE + 2                 # Anim_WriteSpecificItemSprites' second tile
LOGO_SPRITE_TILES = (LOGO_FRAME_TILE, LOGO_RIGHT_TILE)
# Anim_ItemFrameTiles (bank 1) entry $26, the shield slot's ($1F) first frame tile: $56 in PRG0.
ITEM_FRAME_TILES = 0x0715C
SHIELD_FRAME_ENTRY = ITEM_FRAME_TILES + 0x26
# Anim_WriteSpecificItemSprites' CMP #$20 / BCC @Wide (bank 1 $B1BD-$B1C0, run at RAM $794D): it becomes
# CMP #$5D / BEQ to the JMP Anim_WriteSpritePair at RAM $7983 (file 0x07203), 0x32 bytes past the BEQ.
# Pegasus Boots writes the CMP's operand (0x071CE, $1C); the logo's bytes come after, and its tile
# $1C still falls in the narrow range.
WIDE_BELOW_TEST = 0x071CD
CMP_IMMEDIATE, BEQ = 0xC9, 0xF0
TO_WRITE_SPRITE_PAIR = 0x32
LOGO_TEST = bytes((CMP_IMMEDIATE, LOGO_FRAME_TILE, BEQ, TO_WRITE_SPRITE_PAIR))
MAGICAL_SHIELD = 0x1C
# ItemIdToDescriptor[$1C]: class 1 (an amount) with value 0, so taking it adds 0 to the shield's
# slot ($1F, which class 1 has no special case for). Up to 2.0.1 it was $20, class 2 (graded) with
# value 0, which raised nothing either, but Progressive Items' ResolveProgressive (fp-prog-01) read
# it as an upgrade line already at its top level and hid the ware in every cave and shop; a class 1
# item is no upgrade, so the ware shows and sells.
DO_NOTHING_DESCRIPTOR = 0x10
# ItemSlotToPaletteOffsetsOrValues (bank 1) entry $1F, the shield's slot: palette row 1, the blue
# one, in place of PRG0's 0 (Link's palette).
ITEM_SLOT_PALETTES = 0x06B6C
MAGICAL_SHIELD_SLOT = 0x1F
LOGO_PALETTE = 0x01


def logo_writes() -> list[tuple[int, bytes]]:
    """The logo's changes, as (headered file offset, bytes): its four background tiles, the shield
    slot's frame tile, the drawing test, the do-nothing take and the blue palette."""
    return [(LOGO_TILES_AT, LOGO_TILES),
            (SHIELD_FRAME_ENTRY, bytes((LOGO_FRAME_TILE,))),
            (WIDE_BELOW_TEST, LOGO_TEST),
            (ITEM_ID_TO_DESCRIPTOR + MAGICAL_SHIELD, bytes((DO_NOTHING_DESCRIPTOR,))),
            (ITEM_SLOT_PALETTES + MAGICAL_SHIELD_SLOT, bytes((LOGO_PALETTE,)))]
