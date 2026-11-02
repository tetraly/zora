# ZORA changelog

What changed in each release of ZORA. The same version, flags and seed always make the same game,
apart from the Cosmetic settings.

## 2.0 beta 12 (2026-11-02)

### New Features
- **Compass Chime** (ZORA Extras: On, Off or Random; Off by default): with a level's compass, a four-note chime plays when you enter a room that still holds an item you haven't collected, one that appears after a fight (Ganon's Triforce of Power too) or one down the room's stairway. With it off, ROMs are unchanged; the seed document and spoiler log list it among the ZORA flags.
- **Statistics screen: Self-burns.** A new counter under the heart containers (a flame, then the count): how many times your own fire hurt you, the candle's flame and the wand's with the Book (a hit that kills you counts; cave fires and enemy fireballs do not). It stops at 255. The times move down two rows to make room, and the PUSH START BUTTON line is gone (Start still leaves the screen). Requested by a player. Seeds are unchanged; the statistics screen's bytes change.
- **Statistics screen: Death warps.** A new counter beside Self-burns: how many times you ended the game from the item screen with the death warp (the buttons chosen under Death-warp, Up+A by default). It counts the warp whether you then pick Continue, Save or Retry, and it is not a death: Deaths still counts only real game overs. It stops at 255. Self-burns moves one place right, under the bombs. Seeds are unchanged; the statistics screen's bytes change.

### Changes
- **More graphics hacks are accepted:** a hack may now also recolor Link's tunics (Cactus's hack sets the red ring's color), rewrite Zelda's thank-you at the end, and rearrange the dungeon door pictures (both done by the Legend of Marin hack). Your tunic colors still come from Look and feel, so pick the hack's colors there to keep them. Seeds are unchanged.
- **Use recommended colors** (Look and feel, under Playable character): a button shown with any set that has colors it was drawn for (not under Random) sets your three tunic colors and two other colors to all five of them, so Playable character's colors becomes My own holding the set's colors and every color looks as drawn, even where The set's own keeps your tunic colors. Each of those colors is now labeled with its NES palette value and a name with its brightness ("$06 dark red", "$27 light orange", "$18 olive"), readable on touch screens. Player settings only: seeds are unchanged.
- **Playable character:** the Merchant, the Old Man, the Old Woman and Zelda are no longer offered (an Archipelago YAML naming one gets the original Link), and the Darknut, Gibdo, Goriya, Lynel, Moblin, Stalfos and Wizzrobe, drawn from the game's own art, are credited to Nintendo. Random now draws from the sets left, so a seed with Random may show a different character. Player settings only: seeds are unchanged.
- **Playable character: Agumon** has Irenepunmaster's fixes: a redrawn one-handed lift pose and small touch-ups to walking down and up, attacking down and the small shield. Player settings only: seeds are unchanged.
- **Generating a seed may take up to 30 seconds** on the page (it was 15). With no seed typed, the page still tries a new seed after 5 seconds, so up to six get a try.
