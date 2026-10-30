# Credits

ZORA is MIT-licensed (see `LICENSE`). This page credits the people and material it builds on.
Third-party material keeps its own license, given with it.

## Z1R Features

- All features controlled by Z1R flags and most Look & Feel flags are based on specifications generated from Zelda Randomizer (Z1R) by Fred Coughlin and re-implemented using AI-assisted clean-room design.

## Community features

| Feature | Credit | ZORA's patch |
|---|---|---|
| Speed Up Dungeon Transitions | fiskbit (the fast scroll) | `asm/flags2/fast-dungeon-scroll/` |
| Speed Up Heart Fill | snarfblam (the Zelda Hack Pack's fast_fill.ips) | `asm/flags2/fast-heart-fill/` |
| Recorder Kills Dungeon Pols Voice | Stratoform (the Zelda Hack Pack's flute_kills_pols.ips) | `asm/flags2/recorder-pols-voice/` |
| Like-Like Eats Rupees | gzip (the Zelda Hack Pack's like_like_rupees.ips) | `asm/flags2/like-like-rupees/` |
| Start With Full Health | ShadowOne333, kalita-kun and gzip (the Zelda Hack Pack's full_health.ips) | `asm/flags2/full-health/` |
| Harder Bosses | MetalMachine (Z1M1's boss_level) | `zora/rom/harder_bosses.py` |
| Harder Ganon | MetalMachine (Z1M1's harder_ganon) | `asm/flags2/harder-ganon/` |
| Offense and Defense Item Pacing, Recorder Warping | MetalMachine (Z1M1's pacing settings) | `zora/generate/acceptance_check.py`, `zora/generate/dungeon_walk.py` |
| Swap Swords and Rings, Swordlish | BogieSmalls | `zora/generate/steps/swap_swords_and_rings.py`, `zora/rom/swordlish.py` |
| Reduce flashing | Z1R community resource |
| Statistics screen (the idea: an end-of-game list of times, deaths and counts) | Z2Randomizer | `asm/fp-stats-01/` |
| Low-health beep at half speed (the idea) | Z2Randomizer | `asm/settings/half-speed-beep/` |

The four Hack Pack rows above come from the **Zelda Hack Pack** by gzip
(https://www.romhacking.net/hacks/5937/), a collection of standalone patches for The Legend of
Zelda. ZORA's versions are its own code, written from the disassembly after reading what each
patch changes; the patches' authors are named in the Hack Pack's readme, and the ending credits
thank them under Additional Technical Contributions.

These features are included with credit to their authors; the owner will remove them if their
authors ask. ZORA's patches for them are its own code, written from the disassembly.

## Z1M1

- **MetalMachine**, author of Z1M1, gave permission to use Z1M1's source code directly to add
  similar features to ZORA. Features taken from Z1M1 are credited to MetalMachine
  (`docs/permissions.md`).
- **ZeroMeaning**, who drew the sprites that ship with Z1M1: permission, through MetalMachine, to
  use them in other projects; nine of their Link sprites ship as playable characters, and their
  Halloween pack as the Graphics theme Halloween (Sprite art, below; `docs/permissions.md`).

## BogieSmalls

- **BogieSmalls**: permission to bring his features into ZORA (2026-10-29), built
  clean-room from a reviewed spec. Swap Swords and Rings and Swordlish are his, by his names, with
  Swordlish's text in his words (docs/permissions.md section 3).

## Community hint texts

The texts people read in caves and from hint people come from the community's submissions on ZORA's
Discord, many of them in the pool since 2.0. Each text added since is credited in the fourth column of
`zora/generate/steps/hint_pool.txt` (never shown in the game). Thank you, Whyforce89887, GrandpaSzabo,
Crump, ultralavos, TheGobOne, Tetra, PDXRex and heccinhayley.

## Sprite art

- **The website logo** (the ZORA character on the page) by Gromfalloon, commissioned for ZORA
  (`web/zora-logo.png`).
- **The Pegasus Boots sprite** by Irenepunmaster. 
- **The playable character sprites** Abobo, Agumon, Jason Voorhees, Mini-Ganon and Twilight Sparkle
  Humanoid Pony Edition by Irenepunmaster (`zora/rom/link_sprites/`).
- **The playable character sprites** Ganon, Justin Bailey, Kraid, Link (Bunny), Link (Female), Link
  (Invisible), Mother Brain, Samus and Zelda by ZeroMeaning, drawn for Z1M1
  (`zora/rom/link_sprites/zeromeaning-*.json`, `docs/z1m1/sprites.md`).
- **The Halloween graphics theme** ("Hallowe'en" for the overworld, the dungeons and the bosses, and
  "Lord of the Flies" for Ganon) by ZeroMeaning, drawn for Z1M1 (`zora/rom/themes/halloween.json`).

## Music

- **Music engine: lozft by TheRealQuantam (MPL 2.0), using bhop by zeta0134 (MIT-0).** Randomized
  music plays through lozft, Quantam's FamiTracker driver for The Legend of Zelda
  (github.com/TheRealQuantam/lozft). For lozft built from source, ZORA uses that repository at
  commit 44b1bb5, which includes the PRG0 build option ZORA contributed (pull request
  TheRealQuantam/lozft#1). `scripts/lozft_build.py` builds it, and
  `zora/rom/music/lozft_patch_data.py` holds the result, lozft's executable form under MPL 2.0.
  Its source is that commit. The pinned `lozft.bps` that ZORA downloads today is
  Quantam's own build, as he sent it.
- **The importer** (`zora/rom/music/`) is a port of Quantam's FtRandoLib and MusicImporter, with his
  permission. **The standard library** of songs is Quantam's ZeldaMusicRandomizer's, fetched from
  his repository and never hosted by ZORA (`docs/music.md`).

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
