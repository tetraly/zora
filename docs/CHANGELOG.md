# ZORA changelog

What changed in each release of ZORA. The same version, flags and seed always make the same game,
apart from the Cosmetic settings.

## Unreleased

## 2.0 beta 2 (2026-10-09)

### New features

- **All Swords No Boards:** Add L4 Sword is now Off / Level 2 / Level 9. Level 2 adds an item staircase to level 2 with one more sword upgrade in the item shuffle, so four sword upgrades found in any order give a level-4 sword (needs Progressive Items and shapes turned on). A new Level 9 Entrance setting requires a level-4 sword (four sword upgrades) for entry instead of the triforce pieces. There is also a new "All Swords No Boards" preset.
- **New hint wording:** a hint that places an item reads "THE RAFT RESTS IN LEVEL-3." (each item by its usual name, with its own verb), and a hint that places a level reads "LEVEL-3 LIES IN THE DEAD WOODS." Up to ten start with an opener such as "IT IS SAID THAT", and people's hints name places the same way ("MEET THE MERCHANT NEAR START"). The same hints appear and point to the same places; only their words change.
- **Level name (player setting):** the word the status bar shows before a level's number in place of LEVEL. Pick one of 28 or type up to six of the game's characters (six-letter words drop the dash, as in PALACE1). Hints that name a level use the same word.
- **Boss-sound label (player setting):** in a dungeon room with a boss sound, the status bar now reads -ROAR-. Its word can be ROAR, one of 22 listed words, your own four letters, or Random (picked by the seed number).

### Changes

- **Add L4 Sword:** the level-4 sword now comes from any sword pickup taken at sword level 3 (caves, shops, dungeon rooms and stairs, the coast and the Armos), not only from a dungeon room, and a shop still sells the fourth upgrade at level 3.
- **Shuffle Blue Potion:** the potion shop's own blue potion now stays, sold again and again as usual. The shuffled place is the shop's empty middle slot: it starts with a blue potion in the item pool, sells whatever item lands there once, and needs the letter as before.
- **Map marker with dark tunics:** a very dark tunic colour (black, dark blue, or another close to a map's background) no longer blends in with a dark minimap. With such a colour, the marker is drawn in his skin colour, and the page says so beside the colour pickers (from a beta report).
- **Refactoring:** Various under-the-hood changes to lay the foundation for future Archipelago multi-world features.

### Bug Fixes

- **Ending:** Fixed a bug causing the ending screen's copyright to be garbled and missing text.
- **Progressive Items with Add L4 Sword:** Fixed a bug where, at sword level 4, taking a sword item in a shop, under an Armos statue or on the coast could give bait instead.
- **Shop Items in the Item Pool:** The randomizer was sometimes placing both arrows or both candles in level 9, which caused circular item dependencies making the seeds unbeatable. ZORA now automatically detects such seeds, rejects them as invalid, and rerolls before generation.
