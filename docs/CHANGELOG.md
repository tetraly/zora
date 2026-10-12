# ZORA changelog

What changed in each release of ZORA. The same version, flags and seed always make the same game,
apart from the Cosmetic settings.

## 2.0 beta 3 (2026-10-12)

### New Features 

A new ZORA feature has been added: 
 
- **Statistics screen:** A new Look and feel setting. When enabled, pressing START after the end-game credits will bring up a screen with the time spent in the overworld and each level, when each level was completed and when the sword, ladder, bracelet, raft, recorder and silver arrows were found, in the order they happened, plus deaths, heart containers, sword stabs, bombs used, the inventory, and the seed's code. The stats are kept on the cartridge and start over when a new file is registered. Note that the times do not currently account for lag frames. Shoutouts to the Z2Randomizer team for the idea.

The following features from Zelda Randomizer have been re-implemented using AI-assisted clean room development:

- **Dungeon Quest "1st Quest" and "2nd Quest":** 
- **Overworld Quest: "2nd Quest", "Mixed Quest - 1st", "Mixed Quest - 2nd", and "Random":**
- **Start Screen: "Full start shuffle" and "Wood Sword Screen":** 
- **Item Shuffle: "Intra-Dungeon":**
- **Allow OW Blocks of Wood Sword:**
- **Force Overworld Block:**
- **Hint Type: "Helpful":** 
- **Allow Important Items in 9:**
- **Shuffle Dungeon Start Room:** 
- **Start items:** Nine start-item settings now work: Start with Raft, Start with 8 Bombs, Start with Recorder, Start with Bait, Start with Letter, Start with Power Bracelet, Start with Blue Candle, Start with Wood Boomerang and Start with Magical Boomerang. 

### Changes

- **Starting Items tab:** Starting Hearts, Max Start Items and the Start settings now have their own tab on the page, which explains how Max Start Items limits the chosen items and warns when a Start setting is on while Max Start Items is 0 (the default, which keeps none). Flag strings and defaults are unchanged.
- **Flag names:** The UI now uses the Z1R community's names for the flags and their values.

### Bug Fixes

- **Hints with Extra Raft Blocks, Extra Power Bracelet Blocks or the randomized mazes:** Fixed a bug where a hint could incorrectly say THE PRINCESS NEEDS NO RAFT (or NO BRACELET) even though a level's entrance was blocked by that item. Shoutouts to Custom for reporting this.
- **Hints about the graveyard:** Fixed a bug where hints for a level whose entrance is under a gravestone could incorrectly say that its item NEEDS THE BRACELET. It now says THE PATH TO THE ITEM LIES BENEATH A GRAVESTONE (with the item's name).
- **Random boss-sound word with long seed numbers:** Fixed a bug where Random could not pick a word, and the game could not be made, for seed numbers of 20 digits (10000000000000000000 and up), whose title screen shows SEED and the number with no space between them.
- **Randomize Magical Sword with Level 9 Entrance "Level 4 sword":** Fixed a bug where the game could never be made with both settings on (in beta 2 it always failed after 2000 attempts): the magical sword, once it was among the shuffled items, was not counted towards the level-4 sword that opens level 9.
