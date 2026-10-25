# Link sprite sets

A Link sprite set redraws Link (features-behavior.md FP-LINK-02). It is a player setting: it changes
only how Link looks, never the seed, the flag string, generation or the file-select code. The page's
Look and feel tab has a **Link sprite** row: *Link* (the original), a set you load (**Load a set…**),
or *Random* (the original Link or your set, picked by the seed number; offered once a set is loaded).
ZORA ships no sets of its own yet. The setting is single-player only: Archipelago's player settings
do not offer it.

## The file

A set is one UTF-8 JSON file (`.json`) holding one object:

```json
{
  "format": "zora-link-sprite-set",
  "version": 1,
  "name": "Green Hero",
  "author": "Your name",
  "provenance": "Drawn by me for ZORA; anyone may use it.",
  "tiles": "<base64 of exactly 640 bytes>"
}
```

| Key | What |
|---|---|
| `format` | always `zora-link-sprite-set` |
| `version` | `1` |
| `name` | the set's name, shown on the page (not empty) |
| `author` | who made it, shown on the page (not empty) |
| `provenance` | free text: where the art comes from and the permission given (may be empty) |
| `tiles` | the tile data, base64 (standard alphabet, with padding): exactly 640 bytes |

ZORA refuses a file with another format or version, a missing name or author, tile data that is not
base64, or any amount of tile data other than 640 bytes, with a message saying which; no ROM is made
from it. Any tile content is accepted.

## The 640 bytes

Forty 8x8 tiles, 16 bytes each in the console's 2-bit format: eight bytes of the low bit plane, then
eight bytes of the high bit plane, one byte per row from the top, the leftmost pixel in the highest
bit. They are Link's tiles in these six groups of the game's sprite patterns, in this order
(FP-LINK-01; zora/rom/link_sprite.py `LINK_TILE_GROUPS`):

| Set bytes | Tiles | ROM file offsets (with the 16-byte header) |
|---|---|---|
| 0-447 | common sprite tiles $00-$1B (28) | 0x0808F-0x0824E |
| 448-479 | the title story's first pair (2) | 0x04E44-0x04E63 |
| 480-511 | the title story's second pair (2) | 0x04EC4-0x04EE3 |
| 512-543 | common sprite tiles $54 and $55 (2) | 0x085CF-0x085EE |
| 544-607 | common sprite tiles $58-$5B (4) | 0x0860F-0x0864E |
| 608-639 | common sprite tiles $60 and $61 (2) | 0x0868F-0x086AE |

So the original Link is those 640 bytes read from the game, in that order (`link_tiles` reads them
from a ROM); a set made by editing them in a tile editor and writing them back in the same order
keeps every pose where the game expects it. PRG0 and PRG1 hold Link at the same offsets.

## Colors

Link is drawn with sprite palette 0. Color 1 is the tunic, so it follows the tunic colors (green,
blue ring, red ring) and the Tunic colors settings. Colors 2 and 3 are the palette's other two
entries as the game sets them, shared with the items and people drawn in it, so a set cannot change
them. Color 0 is transparent.

## Where it shows

In play, on the file-select screen and in the title story: all three draw from these tiles. Nothing
else changes (the items, the people, the enemies and level 9 keep the original art).

## Art

A set must be its author's own work, or a contribution whose author has given permission, said in
`provenance`. No art from other randomizers' sprite choices may be used in a set ZORA ships.
