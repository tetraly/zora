# Trying the ZORA beta

> **Beta.** ZORA 2.0 has been tested by automated checks but not yet tested by hand. Expect
> there to be bugs and unbeatable seeds. Please don't use it for races yet. If something looks
> wrong, report it with the seed, flags and version in the
> [ZORA Discord](https://discord.gg/DVyPXcG5v).

Thank you for helping test ZORA! ZORA makes new, shuffled versions of the
original Legend of Zelda for the NES. This beta is a single file that runs
in your web browser. There is nothing to install.

## Known limitations (2.0 beta 2)

- Some flag values are not made yet: the page shows them greyed out as "Not yet implemented".
- "Encode level data" is not available in the public build.
- This beta has not been playtested by hand. Its seeds are checked by automated tests only.
- To report a bug, give the seed, the flags, the version and the spoiler log (see below).

## Opening it

1. Save the file you were sent (its name starts with `zora-2.0-beta-`)
   somewhere easy to find, such as your Desktop.
2. Double-click it. It opens in your usual web browser: Chrome, Firefox,
   Edge or Safari, on Windows, Mac or Linux.
3. The first time, it needs an internet connection for about a minute,
   while it downloads the parts it runs on. When it is ready, the message
   next to the Generate button says "Ready". After that it usually starts
   faster.

The version of the beta is shown at the top right of the page. Please
mention it when you report anything.

## The game file you need

ZORA does not come with the game. You need your own legally obtained copy
of The Legend of Zelda (USA) as a `.nes` file. It has to be the first
release, sometimes called "PRG0" or "revision 0". Later revisions will not
work.

The page checks your file for you. If it is the right one, the page says
"Base ROM verified". If you want to check it beforehand, this is its
SHA-1 fingerprint (of the whole file):

```
dab79c84934f9aa5db4e7dad390e5d0c12443fa2
```

Your file stays on your computer. The page reads it in the browser and
never uploads it anywhere.

## What to try

1. Click **Choose file** and pick your Zelda file.
2. Leave the settings as they are, or click **Presets** and load one.
3. Click **Generate**. It takes a few seconds.
4. Click the **Download** link to save your new game, then play it in your
   NES emulator.
5. Try a few more: click **New** for a different seed, or try another
   preset or some of the settings.

## The settings

The flag settings are split into tabs: Dungeons, Monsters, Overworld, Items,
Misc and ZORA Extras. Settings that this beta cannot make yet are greyed out, and
hovering over one says why.

**On, Off and ?** Many settings have three buttons:

- **On** and **Off** do what they say.
- **?** lets each seed decide: the game is made with the setting either on
  or off, at random. The page never tells you which, and neither does the
  game file, so a "?" stays a surprise until you play. The same seed and
  flags always decide the same way.

**Encode level data** is a plain On/Off switch: it cannot be "?". A flag
string with "?" there is refused ("Encode level data is on or off; it cannot
be random").

**ZORA Extras tab.** ZORA's own settings. They are kept in a second, short
flag string, the **ZORA flag string** box next to the usual one (empty
means all of them off). Turning any of them on changes the seed and its
code.

- **Randomize Magical Sword**: the magical sword is shuffled with the other
  major items, and the magical-sword cave offers whatever item lands there
  (the old man's text names it). The cave then asks for at most 12 hearts.
  If your other settings allow more (B10, Change sword hearts, on, with the
  cap below at "Follow the Z1R flags", 13 or 14), the page shows a red
  message at those settings and will not generate until you change one of
  them yourself: turn B10 off, or set the cap to 12 or lower.
  The logic counts the heart containers you can reach without the cave's
  item, plus those of all but two of the take-any caves you can reach. It
  assumes sensible take-any choices: taking, say, a candle and two potions
  from three take-any caves can make the seed unbeatable.
- **Randomize Letter**: the letter is shuffled with the other major items,
  and the letter cave offers whatever item lands there.
- **Magical-sword hearts, highest**: the most hearts the magical-sword cave
  may ask for.

**Cosmetic tab.** These change how the game looks, sounds and handles, never
the seed itself. The same seed and flags give the same dungeons and the
same seed code whatever you pick here, so you can race someone who uses
different ones. The page remembers your choices.

- Select button: off (Select pauses, as in the original), swap only (Select
  switches your B item), or toggle (the item screen lets you choose).
- Low-health beep: removed or kept.
- Death-warp: which buttons, held on the item screen, end the game and take
  you to the Continue screen.
- Reduce flashing: turns off the game's bright flashes.
- Music: on or off (sound effects stay on).
- Tunic colours and heart colour: pick any colour from the palette.

## The seed code

After you click Generate, the page shows the seed's code: four items, such
as "Seed code: Bow · Raft · Clock · Fairy". The game shows the same four
items on its file-select screen. Two players with the same code are playing
the same game. Please include the code when you report a problem.

## What you notice

Anything you notice is useful. For example, a game that won't start, gets
stuck, or can't be finished, something on the page that's confusing or
looks wrong, or a page that never says "Ready".

## Reporting a problem

Please report it in the [ZORA Discord](https://discord.gg/DVyPXcG5v), with:

- the version from the top right of the page;
- your computer (Windows, Mac or Linux) and your browser;
- the **Seed**, **Flags**, **ZORA flags** (if any) and **Seed code** shown
  after you clicked Generate, if you got that far, and any Cosmetic settings you changed;
- the spoiler log: click **Download spoiler log** after generating and attach the file;
- what you did, what happened, and what you expected;
- a screenshot, if you can.
