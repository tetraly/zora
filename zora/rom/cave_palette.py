"""The caves' colors: the overworld screen every cave takes its attribute bytes from.

Bank 5's cave entry (LDA #$44 / JSR $83D7 at $B16B) hands screen $44 ($4B with Mirror Overworld,
mirror_overworld.CODE_SITES) to the routine that fills the attribute buffer: that screen's outer palette
(table A bits 1-0) for the walls and its inner palette (table B bits 1-0) for the floor, where a cave's
text is drawn. A cave loads palette 2 white and palette 3 brown, so PRG0's $44 (outer 3, inner 2) gives
brown walls and white text. Extra Raft Blocks paints $44's inner section brown
(steps/overworld_gates.brown_raft_bridge), which turned every cave's text brown (seen in FCEUX,
2026-11-22). So when the screen named there does not hold outer 3 and inner 2, the operand names the
first screen that does; nothing is drawn, and the screens themselves are left as they are.
"""

CAVE_SCREEN_OPERAND = 0x1717C        # the LDA #$44's operand (PRG0 layout, iNES header included)
SCREEN_TABLE_A = 0x18410             # LevelBlockOW table A: bits 1-0 the outer palette
SCREEN_TABLE_B = 0x18490             # table B: bits 1-0 the inner palette
SCREEN_COUNT = 0x80
PALETTE_BITS = 0x03
WALL_PALETTE, TEXT_PALETTE = 3, 2
PRG0_CAVE_SCREEN, MIRRORED_CAVE_SCREEN = 0x44, 0x4B


def screen_palettes(rom: bytes | bytearray, screen: int) -> tuple[int, int]:
    """A screen's (outer, inner) palette, as the image's screen tables hold them."""
    return rom[SCREEN_TABLE_A + screen] & PALETTE_BITS, rom[SCREEN_TABLE_B + screen] & PALETTE_BITS


def cave_screen_writes(rom: bytes | bytearray) -> list[tuple[int, bytes]]:
    """The operand's new screen when the one it names would give caves other colors than PRG0's; none
    when it gives PRG0's, or when no screen does (the caves then keep the colors they had)."""
    wanted = (WALL_PALETTE, TEXT_PALETTE)
    if screen_palettes(rom, rom[CAVE_SCREEN_OPERAND]) == wanted:
        return []
    for screen in range(SCREEN_COUNT):
        if screen_palettes(rom, screen) == wanted:
            return [(CAVE_SCREEN_OPERAND, bytes([screen]))]
    return []


def restore_cave_screen(rom: bytearray, mirrored: bool) -> None:
    """A finished image written again: the operand back to the screen PRG0 (or the flip) names, which
    Mirror Overworld's own check expects before it undoes the flip (mirror_overworld._unflip_code)."""
    rom[CAVE_SCREEN_OPERAND] = MIRRORED_CAVE_SCREEN if mirrored else PRG0_CAVE_SCREEN
