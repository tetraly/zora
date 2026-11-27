# Starter project: custom recorder tunes

A brief you can hand to your AI assistant. Read [CONTRIBUTING.md](../../CONTRIBUTING.md) first: every
step below is one pull request, and each waits for approval before the next one starts.

**The goal:** a cosmetic player setting that plays a tune of the player's choice when Link plays
the recorder. The player loads their own file of tunes on the page and picks one, or Random.

## What the game does

Each fact here was checked against the game's disassembly (`asm/README.md`, "The disassembly").
Check them again yourself before relying on them.

- **The recorder's tune.** `WieldFlute` (bank 7) requests tune $10 on tune channel 1
  (`Tune1Request`) and sets `FluteTimer` to $98 frames. The audio driver in bank 0 plays channel 1:
  `DriveTune1` reads the tune from `TuneScripts1`, which starts with one start offset per tune and then
  holds the tunes' scripts (a byte with bit 7 set gives the next notes' length; 0 ends the tune).
- **The tune never changes gameplay.** Everything the recorder does waits for `FluteTimer`, never
  for the tune. A tune longer than $98 frames keeps playing once play resumes, and, as in the
  original game, any later channel 1 request (a rupee, a found secret, a kill) cuts it off.
- **A longer tune needs a hook.** `TunePtr1`, the driver's place in the tune, is one byte counted
  from `TuneScripts1`, and that table has no spare room. A custom tune lives somewhere else, and
  ZORA's own hook in the driver has to read it from there.

## What ZORA already has nearby

- **Compass Chime** (`asm/flags2/compass-chime/`) is ZORA's own player on tune channel 1, with its
  emulator test (`tests/test_compass_chime_emulator.py`). Read it first: it is the closest model.
  It hooks `DriveTune1`'s first instruction, and no two patches may write the same byte, so the
  recorder's hook uses other sites (or the issue agrees on a way to share that one). Test with
  Compass Chime on.
- **Recorder Kills Dungeon Pols Voice** (`asm/flags2/recorder-pols-voice/`) waits for `FluteTimer`,
  so a custom tune doesn't affect it.
- **Bank 0 is shared with music.** Music's two Random values (standard library, local library)
  apply lozft, which writes bank 0 ($8000-$82A0, $9D46-$9D53, and its `UpdateSoundPart2` at
  $A000-$A1AE). Music: Off's patch is at $A200-$A23F (the half- and quarter-speed low-health beep
  follow it, $A240-$A27F). Test with Music: On, Off and Random (standard library). Step 1 finds out
  whether a ROM with randomized music still plays channel 1 through `DriveTune1`.

## Z1R's recorder tunes, and what you may use

Zelda Randomizer (Z1R) can play a custom recorder tune too, and Z1R ROMs are a handy source of tunes
to test with.

- **Reading is fine.** The Z1R Visualizer (github.com/tetraly/z1r-visualizer) reads a Z1R ROM's tune:
  `rom_reader.py`'s `GetRecorderData` (the tune's script bytes) and `GetRecorderText` (the name it
  credits). Reading a Z1R ROM the same way is fine.
- **Copying the hook is not.** The same repository's `data_extractor.py` (`GetRecorderPatchData`)
  copies Z1R's own playback hook. ZORA must never copy or adapt those bytes. Write ZORA's own hook
  from the disassembly. Z1R's hook also sits in bank 0 at $A000, which is lozft's in ZORA.
- **ZORA ships no tunes**, and no list of Z1R's tunes: players load their own file. If you want an
  index of Z1R's tunes for your own testing, build it by generating Z1R seeds and reading them, never
  from Z1R's source code, and don't commit it.

## The setting

- An ordinary cosmetic player setting (`zora/rom/player_settings.py`; the choices in `asm/settings/`
  are examples), outside the flag string, like Music: Off: the same version, flags and seed make
  the same game with or without it.
- Not affected by Disable Custom Music. That flag exists because custom music can lag the game,
  and a recorder tune doesn't.
- No new Python dependency: `zora/` ships inside the Archipelago world. `zora/` reads no files
  either: the page (or a script) hands it the tune file's contents.

## The steps

Each step is one PR within CONTRIBUTING.md's size limit, and waits for approval.

**Step 0: setup (no code).** Clone the repository, put the base ROM in place and check its hash
(CONTRIBUTING.md section 4), and run `sh scripts/verify.sh`. Post its last lines in the issue and
claim the issue.

**Step 1: a design note.** One page, `docs/design/recorder-tunes.md`, approved before any code:
- the tune file: its format (`.json5` or `.csv`, or both, and how to read JSON5 with no new
  dependency), its fields (a name and the raw tune-script bytes), and its limits;
- the tune-script format as `DriveTune1` reads it, with a short example you wrote yourself;
- the hook: which instructions it replaces (`python3 scripts/asm_patches.py locate`), which bank,
  how many bytes of ROM it needs (the space request, CONTRIBUTING.md section 3), and how it lives
  with Compass Chime and with lozft when music is randomized;
- the setting's name and values as the page will show them, and what Random means;
- the tests for steps 2 to 4.

**Step 2: reading tunes.** Code that turns a tune file (`.json5`, `.csv`) and a Z1R ROM's bytes into
a list of tunes, each a name and its raw tune-script bytes, and refuses what the driver can't play.
No ROM writes yet. Tests use small tune files you write yourself; never commit a ROM or a Z1R tune.

**Step 3: the setting and ZORA's hook.** The player setting, ZORA's own hook written from the
disassembly, and the chosen tune written into the ROM. Emulator tests (`tests/emulator.py`): play the
recorder and check the notes channel 1 plays, with Music: On, Off and Random (standard library),
and with Compass Chime on. With the setting off, the output is identical (the quick check's verdict).

**Step 4: the page.** A file loader for the tune file, the list of its tunes by name, and Random
picking one from the file. Music: Random (local library) already loads the player's own files, so
follow how it does that. Screenshots in the PR.

## Out of scope

Open an issue first for any of these: anything that changes generation, the flag string, the
Archipelago world, a format that writes tunes as note names, or the game's other jingles.

## A possible later step

The game's other channel 1 jingles (a rupee, an item taken, a secret found), opt-in and off by
default. Racers listen for the secret-found jingle as a cue, so a player who doesn't choose a
custom jingle must keep hearing the original.
