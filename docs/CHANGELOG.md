# ZORA changelog

What changed in each release of ZORA. The same version, flags and seed always make the same game,
apart from the Cosmetic settings.

## 2.0 beta 5 (2026-10-14)

### New Features
- **Multiworld support:** The page now lets you choose between Single Player and Multiworld (Archipelago) modes. In Multiworld mode, the page asks for your player name, lets you choose most ZORA flags (including shapes dungeons), and exports an Archipelago YAML file instead of generating a ROM. Each release now includes the ZORA Archipelago world (zora.apworld), and a new step-by-step guide on the site explains how to set up, generate and join a game, and how to build your ROM from an .apzora file with the Archipelago Launcher. Multiworld currently requires Archipelago 0.6.8 and BizHawk 2.9 through 2.11, on Windows or Linux. All of ZORA’s flags are configurable in Multiworld mode except Encode Level Data (off so that Archipelago can understand the ROM format) and Item Shuffle (always Full since Archipelago places most items). 
- **New domain:** ZORA now lives at <https://zora.gg>. Old links to the previous address redirect automatically.
- **Specify seeds by URL:** You can now share a URL that sets up a specific flag string and seed. For example, <https://zora.gg/?flags=8hq4BeR1JXo7yjOOHjbxryVQW%21UJ3A&zora=4.T9Jvg&seed=12345> opens ZORA with the "All Swords No Boards" preset and seed 12345. In the future, this may be expanded with a short link or permalink feature.
- **PRG1 ROM support:** ZORA now accepts the PRG1 (Rev 1) version of The Legend of Zelda ROM as well as PRG0. The same flags and seed generate the same game, with the same file-select code, on either ROM version and with any cosmetic settings. (Because of this change, every seed's code differs from beta 4's.)
- **Custom sprite support:** ZORA now accepts ROMs with modified graphics for the playable character, enemies, and background tiles. ROMs that also change colors (palettes) aren’t accepted yet but support may be added in a future version if requested.
- **Shuffle Bomb Upgraders can now be turned off:** When off, bomb upgrades are available in levels 5 and 7 like they are in the vanilla game.

### Changes
- Renamed the "Published variant" flag presets: they now appear as Consternation Remastered and Hopla (both with level encoding). The Hopla preset, listed in beta 4's notes, is now actually available in the menu.
- Two flags now have gender-neutral names ("Book to Understand NPCs" and "Shuffle Bomb Upgraders").
- Hints that mentioned the old man or old woman now say "THE ELDER", and hints like "THE PRINCESS NEEDS NO RAFT" now say "THE HERO'S PATH NEEDS NO RAFT", to make them gender-neutral.

### Bug Fixes
- Fixed a bug where the compass in non-shapes 1st Quest or 2nd Quest dungeons pointed at that dungeon's original Triforce room instead of the room the Triforce was moved to. Shoutouts to pdxrex for finding this and several other bugs fixed in this release.
- Fixed a bug where the start screen could be in Westlake Mall, Casino Corner, or West Death Mountain, and the player couldn't leave without the raft or the power bracelet. Those screens are no longer start screens when their respective "Extra ___ Blocks" flag is on.
- Fixed a bug where the start screen could be past a randomized maze in the Lost Hills or Dead Woods when Randomize Lost Hills or Randomize Dead Woods is on, letting the player skip the maze.
- Fixed a bug where the 2Q Dead Woods Door Repair cave's screen (row 7, column 2), which can only be reached from behind the Dead Woods maze when it's randomized, wasn't treated as part of the restricted area. The logic now requires the maze's hint for it and Link never starts there.
- Fixed a bug where the logic treated a maze's path hint as readable without the book when "Book to Understand NPCs" was on even though the hint shop's text can't be read until the book is found.
