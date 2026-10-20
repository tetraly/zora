# Credits

ZORA is MIT-licensed (see `LICENSE`). This page credits the people and material it builds on.
Third-party material keeps its own license, given with it.

## Z1R Features

- All features controlled by Z1R flags and most Look & Feel flags are based on specifications generated from Zelda Randomizer (Z1R) by Fred Coughlin and re-implemented using AI-assisted clean-room design.

## Community features

| Feature | Credit | ZORA's patch |
|---|---|---|
| Speed Up Heart Fill | snarfblam | `asm/flags2/fast-heart-fill/` |
| Recorder Kills Dungeon Pols Voice | Stratoform | `asm/flags2/recorder-pols-voice/` |
| Reduce flashing | Z1R community resource |
| Statistics screen (the idea: an end-of-game list of times, deaths and counts) | Z2Randomizer | `asm/fp-stats-01/` |

These features are included with credit to their authors; the owner will remove them if their
authors ask. ZORA's patches for them are its own code, written from the disassembly.

## Sprite art

- **The Pegasus Boots sprite** by Irenepunmaster. 

## Fonts and colors

- **Fonts:** DM Sans and DM Mono, under the SIL Open Font License 1.1. The license text ships with
  them as `web/fonts/OFL.txt`, and the single-file page carries it too.
- **NES palette:** the page's and the seed document's NES colors come from cynes, under the MIT
  license. Its notice is kept beside the table (`web/zora-web.js`, `zora_export/nes_palette.py`).

## Archipelago

- **Archipelago** (archipelago.gg, MIT license), the multiworld randomizer framework: ZORA's
  Archipelago world (`archipelago/`, released as `zora.apworld`) is written for it and runs inside
  it, using its world, patch and BizHawk client interfaces. No Archipelago code is copied into ZORA,
  the logo sprite below aside.
- **The Archipelago logo sprite** by binarybrain11 (Zachary Gorman), from their Archipelago fork's
  Legend of Zelda world (github.com/binarybrain11/Archipelago, commit c478ba8; MIT license): the
  32 bytes of tile data an Archipelago game draws another player's item with when its player
  chooses "Other players' items look like: The Archipelago logo" (`zora/rom/archipelago_logo.py`).
- **Archipelago's The Legend of Zelda world**, for research: how it handles the player's ROM and
  the patch file informed the world's ROM handling. Nothing was copied from it.

## Special Thanks

- grandpaszabo, heccinhayley, pdxrex, and thegobone for help with playtesting many buggy ZORA seeds. 
- bogiesmalls for various technical assistance.
- Anthropic for their Claude AI models used to assist with development
  
## Flag Names

Flag names follow the Z1R community's conventions on z1r.wiki (`docs/flag-names.md`).
