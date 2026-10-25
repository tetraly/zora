# ZORA changelog

What changed in each release of ZORA. The same version, flags and seed always make the same game,
apart from the Cosmetic settings.

## 2.0 beta 10 (2026-10-25)

- A bug-fix release for beta 9. Seeds do not otherwise change: the same flags and seed give the same game as in beta 9 (the dungeons, items and hints); only the version line, the seed code that follows it and a Random tunic color differ.
- The "-ROAR-" status-bar label shows only in level 9's rooms beside Ganon (player report, seed 555594931); a Gatekeeper Bosses roar still sounds, with the usual "-LIFE-" label.
- Bug fix (beta 9, Music: Random): taking an item from any cave or shop (a take-any cave's heart container, a sword cave's item, a shop's ware) could freeze or crash the game; the bought fairy's refill routine sat where the custom music's code goes, and now sits clear of it. Seeds with the original music were never affected.
- Look and feel: a Random tunic color is now any color of the palette (54, each color once: one black, one white), not one of eleven, so it comes out the original green 1 time in 54 rather than 1 in 11; two Random tunics are still never alike. Seeds with a Random tunic may show another color.
