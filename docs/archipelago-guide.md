# Playing ZORA in Archipelago

This guide takes you from the YAML you exported on ZORA's page to playing ZORA in a multiworld.
You don't need to have used Archipelago before.

## What Archipelago is

[Archipelago](https://archipelago.gg) is a multiworld randomizer. Several players, each playing
their own game, share one item pool: the items of every game are shuffled across all of the games.
When you pick up an item in ZORA, it may belong to another player, in another game, and the
Archipelago server sends it to them. Their finds can be yours in the same way, and they arrive in
your ZORA game while you play.

A multiworld can mix any games Archipelago supports, and it can have several ZORA players.

In ZORA:

- **Your own items look and work as usual.** An item that belongs to another player looks like a
  five-rupee item.
- **Items sent to you arrive during normal play,** never in the middle of a screen scroll, on the
  item screen, or while text is showing.
- **Your goal** is to rescue Zelda. The server is told when you do.

## The files you'll handle

| File | What it is |
|---|---|
| `zora.apworld` | ZORA's world for Archipelago. Install it once per ZORA version. |
| `<your name>.yaml` | Your settings, exported from ZORA's page. |
| `AP_<numbers>.zip` | The generated game. The organizer hosts it. |
| `AP_<numbers>_P<n>_<your name>.apzora` | Your patch: about 1 KB, which is normal. It holds only the recipe for your game, no game data. The Archipelago Launcher builds your ROM from it. |
| `AP_<numbers>_P<n>_<your name>.nes` | Your playable ZORA game, built by the Launcher next to the `.apzora`. Don't share it. |

## 1. What you need

- **A computer running Windows or Linux** to play. BizHawk, the emulator, doesn't run on a Mac.
  (A Mac can still generate and host a game.)
- **Archipelago 0.6.8**, from its
  [releases page](https://github.com/ArchipelagoMW/Archipelago/releases). On Windows, run the
  installer; on Linux, use the AppImage or the archive.
- **BizHawk 2.9, 2.10 or 2.11**, from [BizHawk's site](https://tasvideos.org/BizHawk/ReleaseHistory).
  On Windows, run BizHawk's prerequisites installer first.
- **`zora.apworld` for your ZORA version.** ZORA's page links it in its multiworld steps: it's the
  file attached to that version's release on
  [ZORA's GitHub releases page](https://github.com/tetraly/zora/releases). Use the same ZORA
  version as the page you exported your YAML from.
- **Your own The Legend of Zelda (USA) ROM**, as a `.nes` file. Either US release works:
  - the first release (often labeled PRG0);
  - the second release (PRG1, sometimes labeled Rev 1 or Rev A);
  - either one with modified graphics, such as a custom sprite set.

  Other versions (European, Japanese) and other hacks aren't recognized. You need the ROM to play,
  and the organizer needs one to generate. Players don't need the same release: each player's
  game is built from their own ROM.

## 2. Install the ZORA world

1. Open the **Archipelago Launcher**.
2. Click **Install APWorld** and choose `zora.apworld`. (Double-clicking the file works too, on
   systems where Archipelago is installed.)
3. Close and reopen the Launcher.

Everyone who generates or plays ZORA in a game must use the **same** `zora.apworld`: a patch can
only be built by the world that generated it. Players of other games don't need it.

To update to a newer ZORA version, install its `zora.apworld` the same way: it replaces the old
one. A game already generated keeps needing the version that generated it.

## 3. Your YAML

ZORA's page, in its Multiworld (Archipelago) mode, exported your YAML: your player name, every
option, and how your game looks and sounds (tunic and heart colors, music, the word before each
level's number, and more). Give it to whoever is organizing the game.

- **Player names** must all be different within a game, 16 characters at most.
- To change your settings, go back to ZORA's page, change them, and export again. The page only
  lets you choose what Archipelago supports, and it refuses combinations ZORA can't make, with the
  reason.

## 4. Generate the game (the organizer)

One person, the organizer, gathers every player's YAML and generates the game. The organizer needs
Archipelago and `zora.apworld` installed, even if they don't play ZORA themselves, and a Zelda ROM.

1. In the Launcher, click **Browse Files** and open the **Players** folder. Move out any YAMLs from
   other games, and put in every player's YAML: any number of players and games.
2. Back in the Launcher, click **Generate**.
3. The first time, Archipelago asks for your Zelda ROM ("The Legend of Zelda (USA) ROM File").
   Pick your `.nes` file. Archipelago keeps a copy of it, named after the first release, whichever
   release it is: that's expected.
4. The game appears in the **output** folder as `AP_<numbers>.zip`.

If ZORA refuses the options, the window says which options conflict. That only happens with a
hand-edited YAML: fix it, or export it again from ZORA's page, and generate again.

## 5. Host the game (the organizer)

Choose one:

- **On archipelago.gg** (the easiest): go to [archipelago.gg](https://archipelago.gg), choose
  **Host Game**, and upload `AP_<numbers>.zip`. The room page shows the address players connect
  to, for example `archipelago.gg:38281`. ZORA doesn't need to be installed on the site.
- **On your own computer:** in the Launcher, click **Host** and choose the zip. Players outside
  your home network need port 38281 forwarded to your computer.

Then send each ZORA player their `.apzora` (inside the zip, named after their player name) and the
room's address. Players of other games get whatever their game uses.

## 6. Play

**Don't open the `.apzora` in BizHawk.** It isn't a ROM, so BizHawk won't recognize it. The
Archipelago Launcher turns it into one.

1. Open the Archipelago Launcher and **drag your `.apzora` onto its window**. (Or click
   **Open Patch** and choose it.)
2. The first time, the Launcher asks for your Zelda ROM, then for `EmuHawk.exe` in your BizHawk
   folder.
3. The Launcher builds your game as a `.nes` file next to the `.apzora`. BizHawk opens with it,
   along with its **Lua Console** (leave that open), and the **BizHawk Client** opens.
4. In the BizHawk Client, type the room's address if it isn't filled in, and click **Connect**.
   You never type a player name: your game carries it.
5. The client says `ZORA world <version>: recognized the ROM for ...`, then that you're connected.
   Start a new file (or load yours) and play.

**Next time,** after closing everything, do the same again: drag the `.apzora` onto the Launcher.
It builds the same game, and your save is kept, because BizHawk keeps it with the game's file name.

**If BizHawk doesn't open by itself:** start EmuHawk, choose **File → Open ROM** and pick the
`.nes` next to your `.apzora`. Then choose **Tools → Lua Console**, **Script → Open Script**, and
pick `connector_bizhawk_generic.lua` from Archipelago's `data/lua` folder. Finally, open the
**BizHawk Client** from the Launcher.

### Good to know while playing

- **Items that look like five rupees** belong to another player. Picking one up sends it to them.
- **Items sent to you** wait until normal play, then arrive one at a time. The client's log lists
  each one, for example `ZORA: gave received item #3, Raft`.
- **Nothing is reported or given** on the title or file-select screens: the client waits until
  you're playing.
- **To save:** with the default Death-warp setting, open the item screen (Start), then hold Up and
  press A on controller 1. (If you changed Death-warp on ZORA's page, use the buttons you chose.)
  Losing all your hearts also brings up the menu. Choose **SAVE**.
- **Some items stay in your own game:** rupees, hearts, fairies, maps, compasses, Triforce pieces
  and the clock are never sent between players. They stay where ZORA puts them.
- **In-game hints** name only your own items; the others say ANOTHER PLAYER'S ITEM. Archipelago's
  `!hint` command, typed in the client, covers the rest.

## 7. If something goes wrong

**BizHawk won't open my `.apzora`, or it's only about 1 KB.**
That's expected: drag it onto the Archipelago Launcher instead (step 6).

**Dragging the `.apzora` onto the Launcher does nothing.**
Check that `zora.apworld` is installed (step 2), then close and reopen the Launcher. Or use
**Open Patch**.

**Archipelago refuses my Zelda ROM ("ROM not recognized").**
ZORA accepts the US releases of The Legend of Zelda (PRG0 or PRG1), with or without modified
graphics. Other versions and other hacks aren't recognized. A ROM that was already randomized
won't work either: use an unmodified one.

**The client says "Waiting to connect to BizHawk...".**
BizHawk's Lua Console must be open and running `connector_bizhawk_generic.lua` (see "If BizHawk
doesn't open by itself" in step 6).

**The client says "No handler was found for this game".**
BizHawk has a plain Zelda ROM loaded, not your ZORA game. Load the `.nes` built next to your
`.apzora`.

**Generating says an option or value isn't known.**
The YAML was exported from another ZORA version than the installed `zora.apworld`. Export it again
from the page of the version you installed, or install the matching `zora.apworld`.

**The client says the game was generated by another ZORA world version, or the ROM was made by
another recipe format.**
Install the `zora.apworld` the game was generated with. Everyone in a game uses the same one.

**An item doesn't arrive.**
Items wait for normal play: close the item screen, finish the scroll or the text. The client's
log says what it gave. If one still doesn't come, please report it.

**Reporting a problem.**
Ask in the [ZORA Discord](https://discord.gg/DVyPXcG5v). It helps to include:

- your YAML and the game's name (`AP_<numbers>`);
- a screenshot of the BizHawk Client window;
- the newest `BizHawkClient` file in Archipelago's `logs` folder (on Windows,
  `C:\ProgramData\Archipelago\logs`);
- a BizHawk savestate from just before the problem, if you have one;
- the spoiler log from inside the zip, if the organizer can share it (it reveals where every item
  is).
