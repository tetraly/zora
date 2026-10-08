# ZORA changelog

What changed in each release of ZORA. The same version, flags and seed always make the same game,
apart from the Cosmetic settings.

## Unreleased

## 2.0 beta 1 (2026-10-07)

The first public release of ZORA 2.0, as a beta. (ZORA 1.x was an earlier, separate project.)

**Making a seed**
- Runs in your web browser: pick your own Legend of Zelda (USA, PRG0) file, choose
  your settings and click Generate. Your file never leaves your computer, and there
  is nothing to install.
- The same settings and seed number always make the same game. The title screen
  shows the seed number and "ZORA 2.0 BETA 1"; the file-select screen and the page show
  a four-item seed code, so two players can check that they have the same game.
- Presets: the baseline and three published variants.

**Settings (the Z1R flag string)**
- 31 settings can be changed in this release, across the Dungeons, Monsters,
  Overworld, Items and Misc tabs. Settings that cannot be made yet are greyed
  out, and hovering over one says why.
- Most On/Off settings also offer "?": each seed decides, and neither the page
  nor the game file says which way.
- Highlights: new dungeon shapes every seed, dungeon rooms shuffled between
  levels, monsters moved between levels, shuffled overworld monsters, bosses,
  boss groups and enemy groups, enemy and boss health changes, shuffled shop
  items, Armos item and dungeon drops, extra candles, changed sword-cave
  hearts, money-making games and bomb upgrades, money-or-life rooms, the
  hungry goriya, hint styles (including mixed helpful hints), dungeon
  palettes, starting hearts and items, faster text, and the Book as an atlas.
- Dungeon people's hints: each level's people show that level's own hint
  texts, spread over the level's people as in the original randomizer.
- Encode level data is a plain On/Off switch; a flag string with "?" there is
  refused.
- Shuffle "Take Any Road" Caves can be turned off: the four take-any-road caves
  then stay where the original game has them.

**ZORA extras (the ZORA flag string)**
- A second, short flag string for ZORA's own settings; empty means all off.
- Randomize Magical Sword: the magical sword joins the shuffled major items, and
  the magical-sword cave offers whatever lands there (its old man names the item).
  The cave asks for at most 12 hearts; a highest-hearts setting lowers that.
- Randomize Letter: the letter joins the shuffled major items, and the letter
  cave offers whatever lands there.
- Progressive Items: swords, candles, arrows, rings and boomerangs upgrade one
  level at a time; each one found or bought gives the next level you lack, and
  a shop sells each upgrade once. Hints name the upgrade line.
- Shop Items in the Item Pool: the wooden arrows, blue candle and blue ring join
  the shuffled major items, and a shop may sell the item that takes their
  place. A shop ware holding another item costs 60-80 rupees for an item needed
  to win (the ladder, raft, power bracelet, recorder, bow, a candle or an
  arrow), 200-240 for one that is not (a sword, ring or boomerang, the wand,
  the book, the magical key), and 20-40 for a heart container or the letter.

**More ZORA extras: each On, Off or ?**
- Shuffle Blue Potion: the potion shop's blue potion joins the shuffled major
  items, and the potion shop may sell any major item in its place (never the
  letter). With an item there that you need, the logic needs the letter too.
- Add L4 Sword (needs Progressive Items): level 9 holds one more sword on the
  floor of one of its rooms; picked up with the magical sword it gives sword
  level 4 (picked up earlier, it is your next sword). Never needed to win.
- Extra Raft Blocks: six more cave screens near Westlake Mall and Casino Corner
  are reached only by raft.
- Extra Power Bracelet Blocks: seven more cave screens on West Death Mountain
  sit behind boulders (needs Shuffle "Take Any Road" Caves off).
- Randomize Lost Hills and Randomize Dead Woods: each maze has a new path. The
  hint shop that sells the path in the original game sells the new one for 1
  rupee, and the logic makes the screens beyond each maze need it. The Dead
  Woods' path now ends going south; the west half of the map then needs the
  ladder.
- Speed Up Dungeon Transitions, Speed Up Heart Fill (by snarfblam), Recorder
  Kills Dungeon Pols Voice (by Stratoform), Four Potion Inventory, Auto Show
  Letter, Like-Like Eats Rupees, and Magical Boomerang Does 1 HP Damage.

**Player settings (the Look and feel tab)**
- They change how the game looks, sounds and handles, never the seed or its
  code, so players with different choices still play the same game.
- Select button (pause, swap the B item, or choose on the item screen), the
  low-health beep, the death-warp buttons, reduced flashing, music on or off,
  and the tunic and heart colours.

**Since the 2.0.0 test builds**
- Dungeon stair rooms holding an item now get "kill all enemies for the item" two times in three
  in every layout, as in the original (a push-block stair room with a key never did).
- Level 9: the rooms behind Zelda's shutters, which open only once Ganon is beaten, now hold
  at most a key, bombs, five rupees or the map. Any other item there (such as the compass) moves
  to another level-9 room, replacing its small item, as in the original.
- Moving each level's map now draws the same numbers whatever its new room, so some seeds
  differ from 2.0.0 (no gameplay change).

**After a seed is made** (with "Encode level data" off)
- Download spoiler log: a plain-text list of the seed's settings, major item
  places, every cave and shop with prices, the hint texts with who says them,
  and the requirements.
- View in Visualizer: opens the seed's dungeon maps in the Z1R Visualizer.
- Neither changes the game file.
