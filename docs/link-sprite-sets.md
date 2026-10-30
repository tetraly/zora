# Link sprite sets

A Link sprite set redraws Link (features-behavior.md FP-LINK-02). It is a player setting: it changes
only how Link looks, never the seed, the flag string, generation or the file-select code. The page's
Look and feel tab's **Playable character and colors** section starts with the **Playable character** row:
*Link (original)*, one of ZORA's own sets by name, a set you load (**Load a set…**), or *Random* (the original
Link, one of ZORA's sets or yours, picked by the seed number). Under it, on the left, who drew the
chosen set and the colors it was drawn for, with **Playable character's colors**: *The set's own* (the
default) or *My own* (Colors, below); on the right, a preview of the sprite walking down with the small
shield in each of the three tunic colors (green, blue ring, red ring) and Link's other two colors, as the
ROM will get them. The original Link's preview shows once your ROM is chosen, as does a set drawn partly
from your ROM (`fromGame`, below), and Random has none. The tunic colors,
**Advanced: Playable character's other colors** and the heart color follow. The sprite and Link's other colors are
single-player only: Archipelago's player settings do not offer them.

## ZORA's sets

| Set | By |
|---|---|
| Abobo | Irenepunmaster |
| Agumon | Irenepunmaster |
| Jason Voorhees | Irenepunmaster |
| Mini-Ganon | Irenepunmaster |
| Twilight Sparkle Humanoid Pony Edition | Irenepunmaster |
| Ganon | ZeroMeaning |
| Justin Bailey | ZeroMeaning |
| Kraid | ZeroMeaning |
| Link (Bunny) | ZeroMeaning |
| Link (Female) | ZeroMeaning |
| Link (Invisible) | ZeroMeaning |
| Mother Brain | ZeroMeaning |
| Samus | ZeroMeaning |
| Zelda | ZeroMeaning |

They are files in this format in `zora/rom/link_sprites/`: Irenepunmaster's made from the artist's
sheets with the converter below, ZeroMeaning's from their Z1M1 assets (docs/z1m1/sprites.md) with
`scripts/z1m1_link_sprites.py`, which reads the pinned commits of the Z1M1 clones and places each tile
by its file offset. A new set there is offered on the page, and Random draws from it too (so adding one
changes which sprite Random gives a seed).

ZORA also offers sets drawn from the game's own art (**built-in art**, below):

| Set | Drawn from | Swap |
|---|---|---|
| Darknut | the Darknut | |
| Gibdo | the Gibdo | |
| Goriya | the Goriya | |
| Lynel | the overworld's Lynel | |
| Merchant | the cave Merchant | yes |
| Moblin | the overworld's Moblin | |
| Old Man | the cave Old Man | yes |
| Old Woman | the cave Old Woman | yes |
| Stalfos | the Stalfos | |
| Wizzrobe | the Wizzrobe | |
| Zelda | Zelda, in level 9 | yes |

They follow the ZORA-drawn sets on the page and in Random's draw. A person's set has a **swap**: a
checkbox under the sprite, off by default, that also draws that person as Link (the original Link,
facing down, from your ROM) wherever the game draws them: in every cave and dungeon room for the Old
Man, the Old Woman and the Merchant, and in level 9 for Zelda (her raised-arms pose takes Link's raised
arm). Random never swaps.

## Built-in art

A built-in-art set redraws Link with art the game already has. It ships no tile data: it is an
arrangement of the game's sprite tiles into Link's poses, and the 640 bytes are assembled from your
own ROM when the ROM is made (`zora/rom/link_art.py`), so a ROM with custom graphics gives its own
art. The arrangements are ZORA's own design, made from the game's art and the disassembly's object
animations. A monster's walking frames become Link's walking, attacking and item poses; a cave person,
whom the game draws as one mirrored half, becomes a Link who looks the same in every direction. Only
Link changes: the person or monster itself, the texts and everything else stay as they are.

The page previews a built-in-art set once your ROM is chosen (it is drawn from your ROM).

The file (`zora/rom/link_art/<id>.json`; the page reads the same object):

```json
{
  "format": "zora-link-sprite-arrangement",
  "version": 1,
  "name": "Moblin",
  "author": "ZORA",
  "provenance": "Arranged by ZORA from the game's own Moblin art, read from your ROM when it is made; ...",
  "recommendedColors": {"tunics": [22, 12, 6], "other": [39, 48]},
  "colors": [1, 2, 3],
  "halves": {
    "$00": {"block": "PatternBlockOWSP", "tile": "$F0"},
    "$5A": {"block": "PatternBlockOWSP", "tile": "$FA", "mirror": true},
    ...
  }
}
```

| Key | What |
|---|---|
| `format`, `version` | `zora-link-sprite-arrangement`, `1` |
| `name`, `author`, `provenance`, `recommendedColors` | as in a 640-byte set |
| `halves` | each of Link's 20 halves, by the name the converter below uses (`$00` … `$60`, the 40 tiles in pairs, top and bottom): the `block` it is taken from, its `tile`, and `mirror` (optional, `false` by default) |
| `colors` | optional, `[1, 2, 3]` by default: the Link color each source color 1, 2 and 3 becomes (0 is transparent); color 0 stays transparent |
| `swap` | optional, a person's set only: a list of the person's own halves (`block`, `tile`), each redrawn as one of the original Link's halves (`link`, a half's name), with `mirror` and `colors` as above; written only when the player turns the swap on. A swap may redraw only the people's own halves: PatternBlockOWSP and PatternBlockUWSP $98, $9A and $9C, and PatternBlockUWSPBoss9 $F0 and $F6 (`SWAP_TARGETS`); any other is refused |

A `block` is one of the game's sprite pattern blocks, by the disassembly's label; a `tile` is the
half's top tile as the game numbers it while that block is loaded (an even number, `$XX`; the half is
that tile and the next):

| Block | Tiles | ROM file offset (with the header) |
|---|---|---|
| `CommonSpritePatterns` (Link, items, the status bar's sprites) | $00-$6F | 0x0808F |
| `PatternBlockOWSP` (the overworld's monsters and people) | $8E-$FF | 0x0D16B |
| `PatternBlockUWSP` (the dungeons' shared sprites and people) | $8E-$9D | 0x0DCCB |
| `PatternBlockUWSP127`, `PatternBlockUWSP358`, `PatternBlockUWSP469` (each dungeon group's monsters) | $9E-$BF | 0x0DDCB, 0x0D88B, 0x0DAAB |
| `PatternBlockUWSPBoss1257`, `PatternBlockUWSPBoss3468`, `PatternBlockUWSPBoss9` (the bosses; level 9's holds Zelda) | $C0-$FF | 0x0DFEB, 0x0E3EB, 0x0E7EB |

Each half is the source half's two tiles, mirrored left to right if asked, with its colors replaced
as `colors` says. PRG0 and PRG1 hold every block at the same offset. ZORA refuses a file with another
format or version, a missing name or author, a half missing or named twice, an unknown block, a tile
that is not the top of a half in its block, or `colors` that are not three of 0-3, with a message.

## The file

A set is one UTF-8 JSON file (`.json`) holding one object:

```json
{
  "format": "zora-link-sprite-set",
  "version": 1,
  "name": "Green Hero",
  "author": "Your name",
  "provenance": "Drawn by me for ZORA; anyone may use it.",
  "tiles": "<base64 of exactly 640 bytes>",
  "recommendedColors": {"tunics": [41, 50, 22], "other": [39, 23]},
  "fromGame": [[592, 608]]
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
| `recommendedColors` | optional: the NES colors (0-63, not 13, which is $0D) the art was drawn for: `tunics`, three (green, blue ring, red ring), and `other`, two (Link's colors 2 and 3); and optionally `colorOne`, `"clothing"` (the default) or `"art"`: what color 1 draws (Colors, below) |
| `fromGame` | optional: byte ranges of the 640, `[start, end]` with `end` excluded, in order and apart, where the art keeps the original Link's bytes: the file holds zeros there, and the bytes are read from the player's ROM at the same places when the set is written, so the file carries none of the game's bytes |

ZORA refuses a file with another format or version, a missing name or author, tile data that is not
base64, any amount of tile data other than 640 bytes, recommended colors that are not three and
two NES colors, a `colorOne` other than the two words, or `fromGame` ranges out of order, outside the
640 bytes or over bytes that are not zeros, with a message saying which; no ROM is made from it. Any
tile content is accepted.

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
blue ring, red ring). Colors 2 and 3 are the game's ($27 and $17: his skin, and his hair, belt and
shield; level 3 shows a lighter skin, $37, and the file-select screen a darker color 3, $07) unless
changed. A changed color is written to every palette the game loads Link's from (the ten level
palettes, the title story's and the file-select screen's, zora/rom/player_settings.py
`link_other_colors`); one left at the game's writes nothing, so those keep their own. Color 0 is
transparent.

**Playable character's colors** decides whose colors those are (`player_settings.CharacterColors`,
`shown_link_colors`):

- **The set's own** (the default): a chosen set's `recommendedColors`. Colors 2 and 3 always; the three
  tunic colors too when its `colorOne` is `"art"`, because color 1 then draws a body, scales or a visor
  rather than clothing, so a ring changes it as the set says. With `"clothing"`, the tunic colors stay
  the player's. Random's set brings its own colors the same way.
- **My own**: the tunic colors and **Advanced: Playable character's other colors** as set.

Without a set (Link, original) or with a set that has no `recommendedColors`, both are the player's.
On the page, picking any tunic or other color switches the choice to My own. Settings saved before
the choice existed, and a command line without `character_colors=set|mine`, read as My own when they
hold a Link color of their own, so a player's earlier colors are kept.

Colors 2 and 3 also color what the game draws in Link's palette (`tests/test_z1m1_link_sprites_emulator.py`,
two ROMs differing only in those colors): the items Wood Sword, Wood Arrows, Bow, Raft, Ladder, Magical
Shield and Wood Boomerang (on the floor, as wares, in the inventory and the status bar: the game draws
them all with one palette rule), and Zelda in level 9. The cave people (the old man, the old woman, the
merchant, the Moblin) and a level's old man are drawn in another palette and do not change. So a set's
own colors 2 and 3 recolor those seven items and Zelda as well.

## Where it shows

In play, on the file-select screen and in the title story: all three draw from these tiles. Nothing
else changes (the items, the people, the enemies and level 9 keep the original art).

## From a sprite sheet

Artists usually draw Link's poses on a sheet: a PNG row of 14 cells of 16x16 pixels, each framed by a
1-pixel border (239 pixels wide), one row per variant. `scripts/link_sprite_sheet.py` turns a row of
such a sheet into a set file:

```
python3 scripts/link_sprite_sheet.py SHEET.png OUT.json --name NAME --author AUTHOR --provenance TEXT
    [--row N] [--colors TUNIC,COLOR2,COLOR3] [--background RRGGBB]
```

The cells, left to right: walking down with the small shield (2), walking sideways (2), walking up (2),
attacking down, sideways and up, lifting an item with one hand, walking down with the magical shield
(2), walking sideways with the magical shield (2). Each of the 40 tiles is read from one cell; the game
draws the others from the same tiles (walking up's second frame is the first, mirrored; the lift's
right side is walking down's, mirrored), and the script lists every cell the sheet draws differently
from what the game will show. The background is transparent; each other color becomes the nearest of
`--colors` (default: the game's own green, orange and brown), so a sheet drawn in other colors still
shows in the tunic color and the game's two fixed colors.

## Art

A set must be its author's own work, or a contribution whose author has given permission, said in
`provenance`. No art from other randomizers' sprite choices may be used in a set ZORA ships, and no
tile may copy the original game's (tests/test_link_sprite_built_in.py checks ZORA's sets for any run
of 8 bytes equal to the game's). Abobo's and Jason Voorhees's shield and sword rows match the game's
pixel for pixel in a few runs; they are original art, reviewed and accepted (2026-10-26), and the test
lists those runs, so any other still fails.
