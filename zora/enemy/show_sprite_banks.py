"""
Visualize enemy sprite bank tiles before and after enemy group shuffling.

NES sprites in this ROM use 8x16 mode: each pair of consecutive 8x8 CHR tiles
(even index = top, odd = bottom) forms one 8x16 hardware sprite. Two 8x16
sprites side by side make a 16x16 metasprite, the standard enemy size.

This tool renders the banks grouped as 16x16 metasprites (4 CHR tiles each).

Two output modes:
  (default)  Terminal rendering with Unicode block characters
  --png      Generates a PNG image file (requires Pillow)

Usage:
    python3 -m zora.enemy.show_sprite_banks [--seed 42] [--overworld]
    python3 -m zora.enemy.show_sprite_banks --png --seed 42
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image as PilImage

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from zora.data_model import EnemySpriteSet, GameWorld
from zora.enemy.change_dungeon_enemy_groups import change_dungeon_enemy_groups
from zora.parser import load_bin_files, parse_game_world
from zora.rng import SeededRng

BIN_DIR = Path(__file__).resolve().parents[1] / "rom_data"

# Map SpriteData field names to EnemySpriteSet values for caption lookup
_FIELD_TO_SPRITE_SET = {
    "enemy_set_a": EnemySpriteSet.A,
    "enemy_set_b": EnemySpriteSet.B,
    "enemy_set_c": EnemySpriteSet.C,
    "ow_sprites": EnemySpriteSet.OW,
}

# NES palette -> unicode block shading
SHADE = [" ", "░", "▓", "█"]

# NES-ish greyscale palette for PNG output (color indices 0-3)
NES_PALETTE = [(0, 0, 0), (85, 85, 85), (170, 170, 170), (255, 255, 255)]

CHANGED_BORDER_COLOR = (255, 80, 80)
GRID_COLOR = (40, 40, 40)


def enemies_in_bank(game_world: GameWorld, field: str) -> list[str]:
    """Return sorted list of enemy names assigned to the given sprite bank."""
    sprite_set = _FIELD_TO_SPRITE_SET.get(field)
    if sprite_set is None:
        return []
    enemies = game_world.enemies.cave_groups.get(sprite_set, [])
    return sorted(e.name for e in enemies)


def decode_tile(data: bytes | bytearray, offset: int) -> list[list[int]]:
    """Decode one 16-byte NES CHR tile into 8x8 pixel values (0-3)."""
    pixels = []
    for row in range(8):
        lo = data[offset + row]
        hi = data[offset + row + 8]
        row_pixels = []
        for bit in range(7, -1, -1):
            val = ((hi >> bit) & 1) << 1 | ((lo >> bit) & 1)
            row_pixels.append(val)
        pixels.append(row_pixels)
    return pixels


def decode_metasprite(data: bytes | bytearray, base_tile: int) -> list[list[int]]:
    """Decode a 16x16 metasprite from 4 consecutive CHR tiles.

    NES 8x16 sprite layout: tiles are stored as pairs (top, bottom).
    Two consecutive pairs form one 16x16 metasprite:
        tiles [base+0, base+1] = left column  (top 8x8, bottom 8x8)
        tiles [base+2, base+3] = right column (top 8x8, bottom 8x8)

    Returns 16 rows of 16 pixel values.
    """
    num_tiles = len(data) // 16
    rows: list[list[int]] = []

    def get_tile(idx: int) -> list[list[int]]:
        if idx < num_tiles:
            return decode_tile(data, idx * 16)
        return [[0] * 8 for _ in range(8)]

    tl = get_tile(base_tile)      # top-left
    bl = get_tile(base_tile + 1)  # bottom-left
    tr = get_tile(base_tile + 2)  # top-right
    br = get_tile(base_tile + 3)  # bottom-right

    for py in range(8):
        rows.append(tl[py] + tr[py])
    for py in range(8):
        rows.append(bl[py] + br[py])
    return rows


def metasprite_changed(before: bytes | bytearray, after: bytes | bytearray,
                       base_tile: int) -> bool:
    """Check if any of the 4 tiles in a metasprite changed."""
    for t in range(4):
        s = (base_tile + t) * 16
        e = s + 16
        if s >= len(before):
            break
        if before[s:e] != after[s:e]:
            return True
    return False


def count_metasprites(data: bytes | bytearray) -> int:
    num_tiles = len(data) // 16
    return (num_tiles + 3) // 4


# ---------------------------------------------------------------------------
# Text rendering
# ---------------------------------------------------------------------------

def render_bank_text(data: bytes | bytearray, cols: int = 4) -> list[str]:
    """Render a bank as a grid of 16x16 metasprites using unicode."""
    n_meta = count_metasprites(data)
    n_rows = (n_meta + cols - 1) // cols
    lines: list[str] = []

    for mr in range(n_rows):
        for py in range(16):
            parts = []
            for mc in range(cols):
                mi = mr * cols + mc
                if mi < n_meta:
                    sprite = decode_metasprite(data, mi * 4)
                    parts.append("".join(SHADE[p] for p in sprite[py]))
                else:
                    parts.append(" " * 16)
            lines.append("  ".join(parts))
        lines.append("")  # gap between metasprite rows

    return lines


def side_by_side(left_lines: list[str], right_lines: list[str],
                 left_label: str, right_label: str, gap: int = 6) -> list[str]:
    max_left = max((len(l) for l in left_lines), default=0)
    spacer = " " * gap
    output = [
        f"{left_label:<{max_left}}{spacer}{right_label}",
        f"{'─' * len(left_label):<{max_left}}{spacer}{'─' * len(right_label)}",
    ]
    for i in range(max(len(left_lines), len(right_lines))):
        l = left_lines[i] if i < len(left_lines) else ""
        r = right_lines[i] if i < len(right_lines) else ""
        output.append(f"{l:<{max_left}}{spacer}{r}")
    return output


def diff_summary(before: bytes | bytearray, after: bytes | bytearray) -> str:
    n_meta = count_metasprites(before)
    meta_diffs = sum(
        1 for m in range(n_meta) if metasprite_changed(before, after, m * 4)
    )
    byte_diffs = sum(1 for a, b in zip(before, after) if a != b)
    return f"{meta_diffs}/{n_meta} metasprites changed ({byte_diffs} bytes)"


# ---------------------------------------------------------------------------
# PNG rendering
# ---------------------------------------------------------------------------

def render_bank_image(data: bytes | bytearray, scale: int, cols: int,
                      before: bytes | bytearray | None = None) -> PilImage.Image:
    """Render a sprite bank to a PIL Image, grouped as 16x16 metasprites."""
    from PIL import Image, ImageDraw

    n_meta = count_metasprites(data)
    n_rows = (n_meta + cols - 1) // cols
    sprite_px = 16 * scale
    gap = max(2, scale)
    w = cols * sprite_px + (cols + 1) * gap
    h = n_rows * sprite_px + (n_rows + 1) * gap

    img = Image.new("RGB", (w, h), GRID_COLOR)
    draw = ImageDraw.Draw(img)

    for mi in range(n_meta):
        mr, mc = divmod(mi, cols)
        x0 = gap + mc * (sprite_px + gap)
        y0 = gap + mr * (sprite_px + gap)

        pixels = decode_metasprite(data, mi * 4)
        for py in range(16):
            for px in range(16):
                color = NES_PALETTE[pixels[py][px]]
                rx = x0 + px * scale
                ry = y0 + py * scale
                draw.rectangle([rx, ry, rx + scale - 1, ry + scale - 1], fill=color)

        if before is not None and metasprite_changed(before, data, mi * 4):
            bw = max(1, scale // 3)
            draw.rectangle(
                [x0 - bw, y0 - bw, x0 + sprite_px + bw - 1, y0 + sprite_px + bw - 1],
                outline=CHANGED_BORDER_COLOR, width=bw,
            )

    return img


def make_comparison_image(
    banks: list[tuple[str, str]],
    snapshots: dict[str, bytes],
    game_world: GameWorld,
    scale: int,
    cols: int,
) -> PilImage.Image:
    """Build a single image with BEFORE / AFTER columns for all banks."""
    from PIL import Image, ImageDraw, ImageFont

    label_h = max(24, 5 * scale)
    section_gap = max(12, 3 * scale)
    col_gap = max(20, 5 * scale)

    panels: list[tuple[str, Image.Image, Image.Image, str]] = []
    for label, field in banks:
        before = snapshots[field]
        after = bytes(getattr(game_world.sprites, field))
        img_before = render_bank_image(before, scale, cols)
        img_after = render_bank_image(after, scale, cols, before=before)
        summary = diff_summary(before, after)
        panels.append((label, img_before, img_after, summary))

    panel_w = max(p[1].width for p in panels)
    panel_h = max(p[1].height for p in panels)
    total_w = 2 * panel_w + col_gap + 40
    total_h = len(panels) * (label_h + panel_h + section_gap) + section_gap + label_h

    img = Image.new("RGB", (total_w, total_h), (20, 20, 30))
    draw = ImageDraw.Draw(img)

    font: ImageFont.FreeTypeFont | ImageFont.ImageFont
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", size=max(12, 3 * scale))
    except (OSError, AttributeError):
        font = ImageFont.load_default()

    before_x = 20
    after_x = 20 + panel_w + col_gap
    draw.text((before_x, 4), "BEFORE", fill=(200, 200, 200), font=font)
    draw.text((after_x, 4), "AFTER  (red = changed)", fill=(200, 200, 200), font=font)

    y = label_h
    for label, img_b, img_a, summary in panels:
        draw.text((before_x, y + 2), f"{label}  [{summary}]",
                  fill=(160, 160, 180), font=font)
        y += label_h
        img.paste(img_b, (before_x, y))
        img.paste(img_a, (after_x, y))
        y += panel_h + section_gap

    return img


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Visualize sprite bank 16x16 metasprites before/after enemy group shuffle"
    )
    parser.add_argument("--seed", type=int, default=42, help="RNG seed (default: 42)")
    parser.add_argument("--overworld", action="store_true",
                        help="Also enable overworld enemy randomization")
    parser.add_argument("--cols", type=int, default=4,
                        help="Metasprites per row in the grid (default: 4)")
    parser.add_argument("--png", action="store_true",
                        help="Output a PNG image instead of terminal text")
    parser.add_argument("--scale", type=int, default=4,
                        help="Pixel scale for PNG output (default: 4)")
    parser.add_argument("--out", type=str, default=None,
                        help="PNG output path (default: sprite_banks_seed_<N>.png)")
    args = parser.parse_args()

    bins = load_bin_files(BIN_DIR)
    gw = parse_game_world(bins)

    banks = [
        ("Bank A", "enemy_set_a"),
        ("Bank B", "enemy_set_b"),
        ("Bank C", "enemy_set_c"),
    ]
    if args.overworld:
        banks.append(("Bank OW", "ow_sprites"))

    snapshots = {field: bytes(getattr(gw.sprites, field)) for _, field in banks}

    change_dungeon_enemy_groups(gw, SeededRng(args.seed), overworld=args.overworld)

    # Print enemy group assignments for all banks
    print(f"Seed: {args.seed}   Overworld: {args.overworld}")
    print()
    for label, field in banks:
        names = enemies_in_bank(gw, field)
        if names:
            print(f"{label}: {', '.join(names)}")
        else:
            print(f"{label}: (no assignments)")
    print()

    if args.png:
        img = make_comparison_image(banks, snapshots, gw, args.scale, args.cols)
        out_path = args.out or f"sprite_banks_seed_{args.seed}.png"
        img.save(out_path)
        print(f"Saved: {out_path} ({img.width}x{img.height})")
    else:
        for label, field in banks:
            before = snapshots[field]
            after = bytes(getattr(gw.sprites, field))
            lines = side_by_side(
                render_bank_text(before, cols=args.cols),
                render_bank_text(after, cols=args.cols),
                f"{label} BEFORE", f"{label} AFTER",
            )
            for line in lines:
                print(line)
            print(f"  >> {diff_summary(before, after)}")
            print()


if __name__ == "__main__":
    main()
