"""How another player's item looks in an Archipelago game's ROM with Other players' items look like
= The Archipelago logo (foreign_item_look = logo; owner decision 2026-10-18; the spec "ZORA
Archipelago beta 5 fixes", item 4). FINISH writes another player's item as the magical shield ($1C)
and turns every shop's real magical shield into a fairy (zora/generate/finish.py); these writes make
$1C look like the logo and do nothing when picked up. Written by the final steps when
GameConfig.foreign_logo is on, in PRG0's layout (none of these bytes moves in PRG1).

The logo sprite is binarybrain11's (Zachary Gorman), from their Archipelago fork's Legend of Zelda
world (binarybrain11/Archipelago commit c478ba8, worlds/tloz/Rom.py `archipelago_sprite`; Archipelago
is MIT-licensed; docs/credits.md)."""
from .inventory import ITEM_ID_TO_DESCRIPTOR

# CommonSpritePatterns (bank 2, headered file 0x0808F, copied to the sprite pattern table) tiles
# $56/$57: the magical shield's 8x16 sprite, each tile its low plane then its high plane.
COMMON_SPRITE_PATTERNS = 0x0808F
PATTERN_SIZE = 16
SHIELD_TILE = 0x56
SHIELD_TILES = COMMON_SPRITE_PATTERNS + SHIELD_TILE * PATTERN_SIZE
LOGO_SPRITE = bytes((
    0x03, 0x07, 0x3F, 0x7F, 0xFF, 0xFF, 0xC6, 0x00, 0x00, 0x00, 0x38, 0x7C, 0xFE, 0xFE, 0xFE, 0x7C,
    0x00, 0x03, 0x07, 0x0F, 0x0F, 0x0F, 0x07, 0x03, 0xFE, 0xFC, 0xF8, 0x70, 0x30, 0x00, 0x00, 0x00,
))
MAGICAL_SHIELD = 0x1C
# ItemIdToDescriptor[$1C]: class 2 (graded) with value 0, so taking it raises nothing.
DO_NOTHING_DESCRIPTOR = 0x20
# ItemSlotToPaletteOffsetsOrValues (bank 1) entry $1F, the shield's slot: palette row 1, the blue
# one, in place of PRG0's 0 (Link's palette).
ITEM_SLOT_PALETTES = 0x06B6C
MAGICAL_SHIELD_SLOT = 0x1F
LOGO_PALETTE = 0x01


def logo_writes() -> list[tuple[int, bytes]]:
    """The three changes, as (headered file offset, bytes)."""
    return [(SHIELD_TILES, LOGO_SPRITE),
            (ITEM_ID_TO_DESCRIPTOR + MAGICAL_SHIELD, bytes((DO_NOTHING_DESCRIPTOR,))),
            (ITEM_SLOT_PALETTES + MAGICAL_SHIELD_SLOT, bytes((LOGO_PALETTE,)))]
