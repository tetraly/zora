from zora.data_model import GameWorld
from zora.game_config import GameConfig
from zora.rng import Rng

# ---------------------------------------------------------------------------
# Color templates 
# ---------------------------------------------------------------------------
PALETTE_OPTIONS: list[list[int]]  = [
    [0x0F, 0x11, 0x21, 0x3C,  0x0F, 0x12, 0x21, 0x3C],
    [0x0F, 0x11, 0x21, 0x3C,  0x0F, 0x11, 0x21, 0x3C],
    [0x0F, 0x0B, 0x1A, 0x29,  0x0F, 0x18, 0x1A, 0x29],
    [0x0F, 0x0B, 0x1A, 0x29,  0x0F, 0x12, 0x1A, 0x29],
    [0x0F, 0x18, 0x28, 0x38,  0x0F, 0x16, 0x28, 0x38],
    [0x0F, 0x18, 0x28, 0x38,  0x0F, 0x18, 0x28, 0x38],
    [0x0F, 0x04, 0x15, 0x26,  0x0F, 0x04, 0x15, 0x26],
    [0x0F, 0x0E, 0x2D, 0x3D,  0x0F, 0x0A, 0x2D, 0x3D],
    [0x0F, 0x0E, 0x2D, 0x3D,  0x0F, 0x07, 0x2D, 0x3D],
    [0x0F, 0x00, 0x1D, 0x13,  0x0F, 0x04, 0x1D, 0x13],
    [0x0F, 0x1D, 0x18, 0x3D,  0x0F, 0x09, 0x18, 0x3D],
    [0x0F, 0x3D, 0x22, 0x20,  0x0F, 0x31, 0x22, 0x20],
    [0x0F, 0x05, 0x24, 0x30,  0x0F, 0x32, 0x24, 0x30],
    [0x0F, 0x01, 0x2D, 0x3D,  0x0F, 0x0F, 0x01, 0x3D],
]


READ_COUNT     = 8
TEMPLATE_COUNT = 14
TOTAL_SLOTS    = READ_COUNT + 1 + TEMPLATE_COUNT  # 23

# Offsets within palette_raw (36 bytes total)
PALETTE1_START = 3   # skip 3-byte PPU header
PALETTE1_END   = 35  # 32 bytes of color data (byte 35 is the 0xFF end byte)
PALETTE1_LEN   = 32

PALETTE2_LEN   = 96  # full fade_palette_raw

REPLACEMENT_NIBBLE = 4  # 0x0C low-nibble -> 0x04

# NES color values with low nibble 0xC are invalid (not real colors).
# These must not appear in fade_palette_raw after randomization.
COLOR_FIXES: frozenset[int] = frozenset({0x0C, 0x1C, 0x2C, 0x3C})


def _nibble_remap(val: int) -> int:
    """Replace low nibble with REPLACEMENT_NIBBLE if low nibble == 0x0C."""
    if (val & 0x0F) == 0x0C:
        return (val & 0xF0) | REPLACEMENT_NIBBLE
    return val


def _exact_remap(orig_val: int, tpl: list[int]) -> int | None:
    """
    Return the template substitution for a dungeon-0 exact value,
    or None if no substitution applies.
      12 -> tpl[1],  28 -> tpl[2],  44 -> tpl[3]
    """
    if orig_val == 12:
        return tpl[1]
    if orig_val == 28:
        return tpl[2]
    if orig_val == 44:
        return tpl[3]
    return None


def randomize_dungeon_palettes(game_world: GameWorld, config: GameConfig, rng: Rng) -> None:
    """
    Shuffle dungeon palettes (non-blackout variant) and write results
    back into game_world.levels[0..8].palette_raw / fade_palette_raw.

    Args:
        game_world:  GameWorld instance (mutated in place)
        config: Game configuration
        rng:    Rng protocol instance
    """

    if not config.randomize_dungeon_palettes:
        return

    # Step 1: Discard 3 RNG values (seed is a no-op in original)
    rng.random()
    rng.random()
    rng.random()

    # Allocate slot arrays (each slot: list-of-int for easy mutation)
    all_palette1: list[list[int]] = [[] for _ in range(TOTAL_SLOTS)]
    all_palette2: list[list[int]] = [[] for _ in range(TOTAL_SLOTS)]

    # -----------------------------------------------------------------------
    # Phase 1: Read 8 dungeons' palette data from game_world.levels[0..7]
    # -----------------------------------------------------------------------
    for d in range(READ_COUNT):
        raw1 = game_world.levels[d].palette_raw
        raw2 = game_world.levels[d].fade_palette_raw

        all_palette1[d] = list(raw1[PALETTE1_START:PALETTE1_END])
        all_palette2[d] = list(raw2[:PALETTE2_LEN])

    # -----------------------------------------------------------------------
    # Phase 2: Slot 8 = copy of dungeon 0 with low-nibble 0x0C -> 0x04 remap
    # -----------------------------------------------------------------------
    all_palette1[8] = [_nibble_remap(v) for v in all_palette1[0]]
    all_palette2[8] = [_nibble_remap(v) for v in all_palette2[0]]

    # -----------------------------------------------------------------------
    # Phase 3 & 4: Build template slots 9..22
    # -----------------------------------------------------------------------
    for t, tpl in enumerate(PALETTE_OPTIONS):
        slot = 9 + t

        # Start from a copy of dungeon 0
        p1 = list(all_palette1[0])
        p2 = list(all_palette2[0])

        # Apply template colors to palette1 positions 8..15
        for i, v in enumerate(tpl):
            p1[8 + i] = v

        # Apply template[0..3] to palette1 positions 28..31
        p1[28] = tpl[0]
        p1[29] = tpl[1]
        p1[30] = tpl[2]
        p1[31] = tpl[3]

        # Apply template to palette2 positions 0..7 and 64..71
        for i, v in enumerate(tpl):
            p2[i]      = v
            p2[64 + i] = v

        # Exact-value remap for palette1 (check original dungeon-0 values)
        for i in range(PALETTE1_LEN):
            sub = _exact_remap(all_palette1[0][i], tpl)
            if sub is not None:
                p1[i] = sub

        # Exact-value remap for palette2 (check original dungeon-0 values)
        for i in range(PALETTE2_LEN):
            sub = _exact_remap(all_palette2[0][i], tpl)
            if sub is not None:
                p2[i] = sub

        all_palette1[slot] = p1
        all_palette2[slot] = p2

    # -----------------------------------------------------------------------
    # Phase 5: Shuffle of all 23 slots
    # -----------------------------------------------------------------------
    indices = list(range(TOTAL_SLOTS))
    rng.shuffle(indices)

    # -----------------------------------------------------------------------
    # Phase 6: Write shuffled[1..9] back into game_world.levels[0..8]
    # -----------------------------------------------------------------------
    for out_level in range(9):
        src = indices[1 + out_level]  # slots 1..9 of shuffled result

        p1 = all_palette1[src]
        p2 = all_palette2[src]

        # Reconstruct palette_raw: preserve PPU header and end byte
        old_raw1 = game_world.levels[out_level].palette_raw
        new_raw1 = (
            old_raw1[:PALETTE1_START]           # 3-byte PPU header (unchanged)
            + bytes(p1)                          # 32 bytes of new palette data
            + old_raw1[PALETTE1_END:]            # 0xFF end byte (unchanged)
        )

        # Reconstruct fade_palette_raw: full 96 bytes replaced
        new_raw2 = bytes(p2)

        game_world.levels[out_level].palette_raw      = new_raw1
        game_world.levels[out_level].fade_palette_raw = new_raw2

