# ZORA FAQ

Answers to common questions about ZORA 2.0. For what changed in each version, see
[What's new](CHANGELOG.md). For help, ask in the [ZORA Discord](https://discord.gg/zescSjDtme).

## What is ZORA?

ZORA (Zelda One Randomizer App) is a new randomizer for The Legend of Zelda on the NES that combines time-tested randomization features with newly-designed extras. It runs in your web browser at [zora.gg](https://zora.gg). You choose your settings, generate a seed, and download a ROM to play.

## How is ZORA different from Zelda Randomizer?

ZORA is based on Zelda Randomizer by fcoughlin and is designed to use the same flag strings. If you paste a Zelda
Randomizer flag string into the **Z1R** box, its settings will carry over.

ZORA adds:

- **ZORA Extras** like Progressive Items, randomizing the magical sword and shop items, new overworld item blocks, a Link's Awakening-inspired Compass Chime, and more. They have a second flag string of their own, the **ZORA** box. An
  empty ZORA string means every extra is at its default, which is Off.
- **Look and feel** cosmetic settings for how the game looks and sounds: your playable character, tunic colors, music,
  graphics themes and more. These never change the game itself.
- **Multiworld play** through Archipelago.

Please note that while the Z1R flagstring and settings are compatible with Zelda Randomizer, the same Z1R flag string and seed will not yield the same game and code in ZORA.

## Which ROM do I need?

The Legend of Zelda (USA), as a `.nes` file. Either US release works:

- the first release (often labeled PRG0);
- the second release (PRG1, sometimes labeled Rev 1 or Rev A);
- either one with modified graphics, such as a custom sprite set.

Other versions (European, Japanese), other hacks, and ROMs that were already randomized aren't accepted.

## Is my ROM uploaded anywhere?

No. Your ROM is read in the page only and never leaves your browser. The game is generated on your own
computer. The page can remember your ROM in this browser, so you don't have to choose it each time. To use a different ROM, use the **Forget** button next to it and then select a different ROM. 

## How do I share flags and seeds?

There are a few ways:

- **The page's address.** As you change settings, the address in your browser's bar changes to match it.
  After you generate, it includes the seed too. Copy the address and send it: whoever opens it gets the
  same flags and seed.
- **The two flag strings.** Copy the **Z1R** and **ZORA** strings, and paste them into the same boxes on
  someone else's page.
- **Copy race info,** after you generate: a short block with the version, the seed, the flag strings, the
  seed code, whether the level data is encoded and the spoiler log level, ready to paste into a race
  channel.
- **Save / load preset:** save your settings under a name in this browser, or save everything the page
  remembers to a settings file and load it in another browser.

## Will the same flags and seed always give the same game?

With the same ZORA version, yes. Your Look and feel settings (character, colors, music) don't change the
game, so racers can each pick their own.

Between versions, a seed may change, but a flag string always keeps meaning the same settings.

## What is the seed code?

A row of item pictures shown on the file-select screen and on the page after you generate. Two players with
the same seed code have the same game, so it's a quick way to check before a race. **Copy seed code**
copies it as item names. With some Item Sprites settings, the seed code is four characters instead of
pictures.

## What are beta settings?

Some settings are still being tested. Each one reads "(beta)" on the page, and it can't be picked until you
turn on the **Beta settings** switch under the flag strings. With it on, a notice at the top of the page
says so. Seeds that use a beta setting are more likely to fail to generate or to have bugs.

If you paste or load flags that use a beta setting, the switch turns on by itself. The switch is never
part of a flag string, so it doesn't change anyone's seed.

At the time of writing, Universal Drops v2.0 and the Spoiler Log Detail Level's Basic, Medium and Full levels are beta.

## What do the spoiler log levels mean?

**Spoiler Log Detail Level,** on the Misc tab, chooses whether your seed comes with a spoiler log, and how
much it shows:

- **None:** no spoiler log.
- **Basic:** what the original randomizer's log shows: where each major item is, every cave, the shops,
  and a map of each level.
- **Medium:** adds, for each major item, whether it's on the floor or down a stairway, and which room.
- **Full:** adds every room of each level: its layout, monsters, floor item, stairway and doors.
- **Random:** The spoiler log level will be randomly chosen between Basic, Medium, and Full.

A seed made with a spoiler log is a different game from the same seed made with None, so a log can't be
made afterwards for a seed generated without one. If a race wants a log after it's over, choose a level
before generating and keep the log private until then.

## What is "Encode level data"?

It's a setting similar to the Race ROM setting in Zelda Randomizer. With it on, the overworld and dungeon data in the ROM is encoded and obfuscated to make it more difficult for other tools to read it. It's recommended to turn it on for competitive races and to leave it off for casual races.

Note that ROMs with level data encoded are not compatible with the Visualizer tool. 

## Where are the trackers?

The recommended tracker is ZoraTracker by TheGobOne is available at https://github.com/TheGobOne/ZoraTracker. Note that ZoraTracker is based on ZTracker by brianmcn (Brian Lorgon) and is available at https://github.com/brianmcn/Zelda1RandoTools.

Note that when you generate a seed with a spoiler log, **Download tracker file** saves a tracker file at the same
level of detail as the log designed for ZoraTracker. ZTracker opens it too, but it shows a version warning (click "Attempt Load"), and the page tells you what ZTracker won't show for that
seed.

## How do I report a bug?

1. After generating, click **Copy bug report info**. It copies the version, the seed, both flag strings,
   your ROM's release and the seed code, which is everything needed to make the same game again. Any beta
   settings in use are listed near the top.
2. Paste it into the #bug-reports [ZORA Discord](https://discord.gg/zescSjDtme) with what happened, and a screenshot or
   savestate if you have one.
3. You can also report a bug in the [ZORA GitHub bug tracker](https://github.com/tetraly/zora/issues/).


## Can I play ZORA in Archipelago?

Yes. [Archipelago](https://archipelago.gg) is a multiworld randomizer: several players, each in their own
game, share one item pool, and items you find may be sent to other players' games.

1. On ZORA's page, choose **Multiworld (Archipelago)** under "How will you play?".
2. Choose your settings and export your YAML. The page only offers what Archipelago supports.
3. Install `zora.apworld` for your ZORA version (the page links it) and give your YAML to the organizer.

Playing needs Windows or Linux, since the BizHawk emulator doesn't run on a Mac. Beta settings aren't
offered in Archipelago yet. The [Archipelago guide](archipelago-guide.md) covers installing, generating,
hosting and playing step by step.

## Can I try the next version early?

Yes: [zora.gg/test](https://zora.gg/test) is the test channel where new releases with untested features are often launched 
early. However for races and normal play, the production instance at [zora.gg](https://zora.gg) is recommended.

## Who made ZORA?

Tetraly is the lead developer. The [credits](credits.md) list everyone whose work it uses, including the sprite artists and the authors of the features it ports.
